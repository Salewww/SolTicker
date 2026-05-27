"""
Amazon Best Sellers scraper.
Extracts product data from Amazon Best Sellers pages using static HTML parsing.

Data extracted:
- Product title
- Current price
- Best Seller rank
- Category
- ASIN
- Rating (if available)
- Review count (if available)
"""

from __future__ import annotations

import re
import gzip
import logging
from dataclasses import dataclass, field
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from html import unescape

logger = logging.getLogger(__name__)

# Amazon Best Sellers category URLs
AMAZON_BS_CATEGORIES = {
    "electronics": "/Best-Sellers-Electronics/zgbs/electronics/",
    "home_kitchen": "/Best-Sellers-Home-Kitchen/zgbs/home-garden/",
    "sports": "/Best-Sellers-Sports-Outdoors/zgbs/sporting-goods/",
    "clothing": "/Best-Sellers-Clothing-Shoes-Jewelry/zgbs/fashion/",
    "beauty": "/Best-Sellers-Beauty/zgbs/beauty/",
    "toys": "/Best-Sellers-Toys-Games/zgbs/toys-and-games/",
    "books": "/Best-Sellers-Books/zgbs/books/",
    "pet": "/Best-Sellers-Pet-Supplies/zgbs/pet-supplies/",
    "tools": "/Best-Sellers-Tools-Home-Improvement/zgbs/hi/",
    "garden": "/Best-Sellers-Garden-Outdoor/zgbs/lawn-and-garden/",
    "health": "/Best-Sellers-Health-Household/zgbs/hpc/",
    "baby": "/Best-Sellers-Baby/zgbs/baby-products/",
    "grocery": "/Best-Sellers-Grocery-Gourmet-Food/zgbs/grocery/",
    "office": "/Best-Sellers-Office-Products/zgbs/office-products/",
    "automotive": "/Best-Sellers-Automotive/zgbs/automotive/",
}

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


@dataclass
class AmazonProduct:
    """Represents a product from Amazon Best Sellers."""
    asin: str
    title: str
    price: Optional[float] = None
    original_price: Optional[float] = None
    rank: Optional[int] = None
    category: str = ""
    rating: Optional[float] = None
    review_count: Optional[int] = None
    url: str = ""
    image_url: str = ""
    platform: str = "amazon"

    def to_dict(self) -> dict:
        return {
            "asin": self.asin,
            "title": self.title,
            "price": self.price,
            "original_price": self.original_price,
            "rank": self.rank,
            "category": self.category,
            "rating": self.rating,
            "review_count": self.review_count,
            "url": self.url,
            "image_url": self.image_url,
            "platform": "amazon",
        }


class AmazonScraper:
    """Scrapes Amazon Best Sellers pages for product pricing data."""

    BASE_URL = "https://www.amazon.com"

    def __init__(self, headers: Optional[dict] = None):
        self.headers = headers or DEFAULT_HEADERS
        self._request_count = 0

    def _fetch(self, url: str) -> Optional[str]:
        """Fetch URL and return HTML content."""
        try:
            req = Request(url, headers=self.headers)
            with urlopen(req, timeout=15) as resp:
                data = resp.read()
                if resp.info().get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
                self._request_count += 1
                return data.decode("utf-8", errors="ignore")
        except (HTTPError, URLError, OSError) as e:
            logger.warning(f"Amazon fetch failed for {url}: {e}")
            return None

    @staticmethod
    def _parse_price(text: str) -> Optional[float]:
        """Parse price string like '$29.99' or 'EUR 10.31' to float."""
        if not text:
            return None
        cleaned = re.sub(r"[^\d.]", "", text.strip().replace(",", ""))
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None

    def scrape_category(self, category_key: str, top_n: int = 50) -> list[AmazonProduct]:
        """
        Scrape a Best Sellers category page.
        
        Args:
            category_key: Key from AMAZON_BS_CATEGORIES
            top_n: Max number of products to return
            
        Returns:
            List of AmazonProduct objects
        """
        path = AMAZON_BS_CATEGORIES.get(category_key)
        if not path:
            logger.error(f"Unknown category: {category_key}")
            return []

        url = f"{self.BASE_URL}{path}"
        html = self._fetch(url)
        if not html:
            return []

        products = self._parse_bestsellers_page(html, category_key)
        logger.info(f"Amazon/{category_key}: scraped {len(products)} products")
        return products[:top_n]

    def _parse_bestsellers_page(self, html: str, category: str) -> list[AmazonProduct]:
        """Parse Amazon Best Sellers HTML to extract product data."""
        products = []

        # Find all list items in the ordered list
        # Amazon uses <li> items with data-asin attributes
        item_pattern = re.compile(
            r'<li[^>]*id="[^"]*"[^>]*>.*?<div[^>]*class="[^"]*zg-grid-general-faceout[^"]*"[^>]*>(.*?)</div>\s*</li>',
            re.DOTALL,
        )

        # Simpler approach: extract all grid items
        # Amazon Best Sellers page structure
        grid_items = re.findall(
            r'<div[^>]*id="gridItemRoot"[^>]*>(.*?)(?=<div[^>]*id="gridItemRoot"|</ol>)',
            html,
            re.DOTALL,
        )

        if not grid_items:
            # Fallback: try the ordered list approach
            grid_items = re.findall(
                r'<li class="zg-item-immersion"[^>]*>(.*?)</li>',
                html,
                re.DOTALL,
            )

        for idx, item_html in enumerate(grid_items):
            product = self._parse_grid_item(item_html, idx + 1, category)
            if product and product.title:
                products.append(product)

        return products

    def _parse_grid_item(self, html: str, rank: int, category: str) -> Optional[AmazonProduct]:
        """Parse a single Best Sellers grid item."""
        # Extract ASIN
        asin_match = re.search(r'data-asin="([A-Z0-9]{10})"', html)
        asin = asin_match.group(1) if asin_match else ""

        # Extract title — try multiple patterns
        title = ""
        title_patterns = [
            r'class="[^"]*p13n-sc-truncated[^"]*"[^>]*>([^<]+)',
            r'<span[^>]*class="[^"]*a-text-normal[^"]*"[^>]*>([^<]+)',
            r'<div[^>]*class="[^"]*_cDEzb_p13n-sc-css-line-clamp[^"]*"[^>]*>([^<]+)',
            r'alt="([^"]+)"',  # Image alt text as fallback
        ]
        for pattern in title_patterns:
            match = re.search(pattern, html)
            if match:
                title = unescape(match.group(1).strip())
                if len(title) > 5:  # Avoid garbage matches
                    break

        if not title:
            return None

        # Extract price
        price = None
        original_price = None
        price_match = re.search(r'class="[^"]*p13n-sc-price[^"]*"[^>]*>(?:EUR|GBP|USD|CAD|AUD|\$)?\s?([0-9,.]+)', html)
        if price_match:
            price = self._parse_price(price_match.group(1))

        # Check for strikethrough (original) price
        orig_match = re.search(r'class="[^"]*p13n-sc-price[^"]*a-text-strike[^"]*"[^>]*>(?:EUR|GBP|USD|CAD|AUD|\$)?\s?([0-9,.]+)', html)
        if orig_match:
            original_price = price
            price = self._parse_price(orig_match.group(1))

        # Extract rating
        rating = None
        rating_match = re.search(r'class="[^"]*a-icon-alt[^"]*"[^>]*>([0-9.]+) out of 5', html)
        if rating_match:
            rating = float(rating_match.group(1))

        # Extract review count
        review_count = None
        review_match = re.search(r'class="[^"]*a-size-small[^"]*"[^>]*>\(([0-9,]+)\)', html)
        if review_match:
            review_count = int(review_match.group(1).replace(",", ""))

        # Extract product URL
        url = ""
        url_match = re.search(r'href="(/dp/[A-Z0-9]+[^"]*)"', html)
        if url_match:
            url = f"{self.BASE_URL}{url_match.group(1).split('?')[0]}"

        # Extract image URL
        image_url = ""
        img_match = re.search(r'src="([^"]*\.jpg[^"]*)"', html)
        if img_match:
            image_url = img_match.group(1)

        return AmazonProduct(
            asin=asin,
            title=title,
            price=price,
            original_price=original_price,
            rank=rank,
            category=category,
            rating=rating,
            review_count=review_count,
            url=url,
            image_url=image_url,
        )

    def search_products(self, query: str, max_results: int = 10) -> list[AmazonProduct]:
        """
        Search Amazon for products matching a query.
        Uses Amazon search results page.
        """
        search_url = f"{self.BASE_URL}/s?k={query.replace(' ', '+')}"
        html = self._fetch(search_url)
        if not html:
            return []

        products = []
        # Split by search result markers to get individual result blocks
        parts = re.split(r'(?=<div[^>]*data-component-type="s-search-result")', html)
        search_results = [p for p in parts if 'data-asin="' in p[:500]]

        for block in search_results[:max_results]:
            # ASIN
            asin_m = re.search(r'data-asin="([A-Z0-9]{10})"', block)
            if not asin_m:
                continue
            asin = asin_m.group(1)

            # Title
            title = ""
            for pat in [
                r'<h2[^>]*>.*?<span[^>]*>([^<]+)</span>',
                r'class="[^"]*a-text-normal[^"]*"[^>]*>([^<]+)',
            ]:
                m = re.search(pat, block, re.DOTALL)
                if m:
                    title = unescape(m.group(1).strip())
                    if len(title) > 3:
                        break

            if not title:
                continue

            # Price
            price = None
            pm = re.search(r'class="a-price-whole"[^>]*>([0-9,]+)', block)
            if pm:
                price = self._parse_price(pm.group(1))

            # Rating
            rating = None
            rm = re.search(r'class="[^"]*a-icon-alt[^"]*"[^>]*>([0-9.]+) out of 5', block)
            if rm:
                rating = float(rm.group(1))

            # Review count
            review_count = None
            rvm = re.search(r'<span[^>]*aria-label="([0-9,]+) ratings?"', block)
            if not rvm:
                rvm = re.search(r'\(([0-9,]+)\)', block)
            if rvm:
                review_count = int(rvm.group(1).replace(",", ""))

            # Image
            image_url = ""
            im = re.search(r'<img[^>]*src="([^"]*\.(?:jpg|jpeg|png|webp)[^"]*)"', block, re.IGNORECASE)
            if im:
                image_url = im.group(1)

            url = f"{self.BASE_URL}/dp/{asin}"

            products.append(AmazonProduct(
                asin=asin,
                title=title,
                price=price,
                rating=rating,
                review_count=review_count,
                url=url,
                image_url=image_url,
                platform="amazon",
            ))

        logger.info(f"Amazon/search: found {len(products)} products for '{query}'")
        return products

    @property
    def request_count(self) -> int:
        return self._request_count
