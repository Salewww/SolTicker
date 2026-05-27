"""
TikTok Shop scraper.
Uses Steel Browser (self-hosted Playwright/CDP) to scrape TikTok Shop product pages
since TikTok Shop is JS-rendered and blocks direct HTTP requests.

Data extracted:
- Product title
- Current price
- Original price (if on sale)
- Units sold
- Seller name
- Product images
- Rating
"""

from __future__ import annotations

import re
import json
import logging
import time
from dataclasses import dataclass
from typing import Optional
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# Steel Browser endpoint (self-hosted)
STEEL_BROWSER_URL = "http://localhost:3001"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass
class TikTokProduct:
    """Represents a product from TikTok Shop."""
    product_id: str
    title: str
    price: Optional[float] = None
    original_price: Optional[float] = None
    currency: str = "USD"
    units_sold: Optional[int] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    seller_name: str = ""
    seller_id: str = ""
    image_url: str = ""
    url: str = ""

    def to_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "title": self.title,
            "price": self.price,
            "original_price": self.original_price,
            "currency": self.currency,
            "units_sold": self.units_sold,
            "rating": self.rating,
            "review_count": self.review_count,
            "seller_name": self.seller_name,
            "image_url": self.image_url,
            "url": self.url,
            "platform": "tiktok",
        }


class TikTokShopScraper:
    """
    Scrapes TikTok Shop product pages.
    Requires Steel Browser running on localhost:3001.
    """

    def __init__(self, steel_url: str = STEEL_BROWSER_URL):
        self.steel_url = steel_url
        self.headers = DEFAULT_HEADERS
        self._request_count = 0

    def _steel_fetch(self, url: str, wait_for: str = "networkidle", timeout: int = 30) -> Optional[str]:
        """
        Fetch a page via Steel Browser (Playwright/CDP).
        Returns the rendered HTML after JS execution.
        """
        try:
            payload = json.dumps({
                "url": url,
                "waitUntil": wait_for,
                "timeout": timeout * 1000,
            }).encode()

            req = Request(
                f"{self.steel_url}/content",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=timeout + 5) as resp:
                result = json.loads(resp.read().decode())
                self._request_count += 1
                return result.get("html") or result.get("content")
        except Exception as e:
            logger.warning(f"Steel Browser fetch failed for {url}: {e}")
            return None

    def _extract_json_ld(self, html: str) -> list[dict]:
        """Extract JSON-LD structured data from HTML."""
        pattern = r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>'
        results = []
        for match in re.finditer(pattern, html, re.DOTALL):
            try:
                data = json.loads(match.group(1))
                results.append(data)
            except json.JSONDecodeError:
                pass
        return results

    def _extract_next_data(self, html: str) -> Optional[dict]:
        """Extract Next.js __NEXT_DATA__ JSON from HTML."""
        match = re.search(
            r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        return None

    def scrape_product(self, product_id: str) -> Optional[TikTokProduct]:
        """
        Scrape a single TikTok Shop product.
        
        Args:
            product_id: TikTok Shop product ID
            
        Returns:
            TikTokProduct or None if scraping failed
        """
        url = f"https://www.tiktok.com/shop/product/{product_id}"
        html = self._steel_fetch(url, wait_for="domcontentloaded", timeout=20)

        if not html:
            # Fallback: try the product page with different URL format
            url = f"https://www.tiktok.com/@shop/product/{product_id}"
            html = self._steel_fetch(url, wait_for="domcontentloaded", timeout=20)

        if not html:
            logger.error(f"Could not fetch TikTok Shop product {product_id}")
            return None

        product = self._parse_product_html(html, product_id, url)
        if product:
            logger.info(f"TikTok/{product_id}: scraped '{product.title[:50]}' @ ${product.price}")
        return product

    def _parse_product_html(self, html: str, product_id: str, url: str) -> Optional[TikTokProduct]:
        """Parse TikTok Shop product HTML to extract product data."""

        # Method 1: Try __NEXT_DATA__ (Next.js apps)
        next_data = self._extract_next_data(html)
        if next_data:
            product = self._parse_next_data(next_data, product_id, url)
            if product:
                return product

        # Method 2: Try JSON-LD structured data
        json_ld = self._extract_json_ld(html)
        for data in json_ld:
            if data.get("@type") == "Product":
                return self._parse_json_ld(data, product_id, url)

        # Method 3: Regex extraction from rendered HTML
        return self._parse_regex(html, product_id, url)

    def _parse_next_data(self, data: dict, product_id: str, url: str) -> Optional[TikTokProduct]:
        """Parse product data from Next.js __NEXT_DATA__."""
        try:
            props = data.get("props", {}).get("pageProps", {})
            product_data = props.get("product") or props.get("initialState", {}).get("product", {})

            if not product_data:
                return None

            title = product_data.get("title", "")
            if not title:
                return None

            price_info = product_data.get("price", {})
            price = None
            currency = "USD"
            if price_info:
                amount = price_info.get("amount") or price_info.get("min_price") or price_info.get("price")
                if amount:
                    price = float(amount) / 100  # TikTok uses cents
                currency = price_info.get("currency", "USD")

            original_price = None
            original = price_info.get("original_price") or price_info.get("max_price")
            if original:
                original_price = float(original) / 100

            # Sales data
            sold_info = product_data.get("sales", {}) or product_data.get("sold_count", {})
            units_sold = None
            if isinstance(sold_info, dict):
                units_sold = sold_info.get("count") or sold_info.get("total")
            elif isinstance(sold_info, int):
                units_sold = sold_info

            # Rating
            rating = None
            review_count = None
            review_info = product_data.get("rating", {})
            if review_info:
                rating = review_info.get("average") or review_info.get("score")
                review_count = review_info.get("count")

            # Seller
            seller = product_data.get("seller", {}) or product_data.get("shop", {})
            seller_name = seller.get("name", "") or seller.get("seller_name", "")
            seller_id = str(seller.get("id", ""))

            # Image
            images = product_data.get("images", [])
            image_url = ""
            if images:
                image_url = images[0].get("url", "") or images[0].get("url_list", [""])[0]

            return TikTokProduct(
                product_id=product_id,
                title=title,
                price=price,
                original_price=original_price,
                currency=currency,
                units_sold=units_sold,
                rating=float(rating) if rating else None,
                review_count=int(review_count) if review_count else None,
                seller_name=seller_name,
                seller_id=seller_id,
                image_url=image_url,
                url=url,
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Failed to parse Next.js data: {e}")
            return None

    def _parse_json_ld(self, data: dict, product_id: str, url: str) -> Optional[TikTokProduct]:
        """Parse product from JSON-LD structured data."""
        try:
            title = data.get("name", "")
            if not title:
                return None

            offers = data.get("offers", {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}

            price = None
            price_str = offers.get("price") or offers.get("lowPrice")
            if price_str:
                price = float(price_str)

            currency = offers.get("priceCurrency", "USD")

            # Aggregate rating
            rating = None
            review_count = None
            agg_rating = data.get("aggregateRating", {})
            if agg_rating:
                rating = agg_rating.get("ratingValue")
                review_count = agg_rating.get("reviewCount")

            # Image
            images = data.get("image", [])
            image_url = images[0] if isinstance(images, list) and images else str(images) if images else ""

            # Seller
            seller = data.get("seller", {})
            seller_name = seller.get("name", "") if isinstance(seller, dict) else ""

            return TikTokProduct(
                product_id=product_id,
                title=title,
                price=price,
                currency=currency,
                rating=float(rating) if rating else None,
                review_count=int(review_count) if review_count else None,
                seller_name=seller_name,
                image_url=image_url,
                url=url,
            )
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse JSON-LD: {e}")
            return None

    def _parse_regex(self, html: str, product_id: str, url: str) -> Optional[TikTokProduct]:
        """Fallback: extract product data via regex from rendered HTML."""
        title = ""
        title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
        if title_match:
            title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()

        if not title:
            # Try meta tags
            title_match = re.search(r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"', html)
            if title_match:
                title = title_match.group(1)

        if not title:
            return None

        # Price
        price = None
        price_patterns = [
            r'"price":\s*\{\s*"amount":\s*"?([0-9.]+)"?',
            r'"price":\s*"?\$([0-9,.]+)"?',
            r'class="[^"]*price[^"]*"[^>]*>\$?([0-9,.]+)',
            r'data-price="([0-9.]+)"',
        ]
        for pattern in price_patterns:
            match = re.search(pattern, html)
            if match:
                try:
                    price = float(match.group(1).replace(",", ""))
                    if price > 1000:  # Likely cents
                        price = price / 100
                    break
                except ValueError:
                    continue

        # Units sold
        units_sold = None
        sold_patterns = [r'([0-9,]+)\s+sold', r'"sale":\s*([0-9]+)', r'"units_sold":\s*([0-9]+)']
        for pattern in sold_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                try:
                    units_sold = int(match.group(1).replace(",", ""))
                    break
                except ValueError:
                    continue

        # Rating
        rating = None
        rating_match = re.search(r'"rating":\s*"?([0-9.]+)"?', html)
        if rating_match:
            rating = float(rating_match.group(1))

        return TikTokProduct(
            product_id=product_id,
            title=title,
            price=price,
            units_sold=units_sold,
            rating=rating,
            url=url,
        )

    def scrape_seller_products(
        self,
        seller_id: str,
        max_products: int = 20,
    ) -> list[TikTokProduct]:
        """
        Scrape products from a TikTok Shop seller's store.
        
        Args:
            seller_id: TikTok seller/shop ID
            max_products: Maximum products to scrape
            
        Returns:
            List of TikTokProduct objects
        """
        url = f"https://www.tiktok.com/shop/store/{seller_id}"
        html = self._steel_fetch(url, timeout=20)
        if not html:
            return []

        # Extract product IDs from the store page
        product_ids = re.findall(
            r'/shop/product/(\d+)',
            html,
        )[:max_products]

        products = []
        for pid in product_ids:
            product = self.scrape_product(pid)
            if product:
                products.append(product)
            time.sleep(1)  # Rate limit between requests

        return products

    @property
    def request_count(self) -> int:
        return self._request_count
