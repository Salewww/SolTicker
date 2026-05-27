"""
Shopify store scraper.
Uses the public products.json API to extract product data from Shopify stores.

Data extracted:
- Product title
- Current price
- Compare-at price (original/sale price)
- Inventory quantity
- Product images
- Tags / categories
- Variants
- Product handle/URL
"""

from __future__ import annotations

import re
import json
import logging
from dataclasses import dataclass, field
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass
class ShopifyVariant:
    """Represents a product variant (size, color, etc.)."""
    id: int
    title: str
    price: float
    compare_at_price: Optional[float]
    sku: str
    inventory_quantity: Optional[int]
    available: bool

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "price": self.price,
            "compare_at_price": self.compare_at_price,
            "sku": self.sku,
            "inventory_quantity": self.inventory_quantity,
            "available": self.available,
        }


@dataclass
class ShopifyProduct:
    """Represents a product from a Shopify store."""
    id: int
    title: str
    handle: str
    vendor: str
    product_type: str
    tags: list[str]
    variants: list[ShopifyVariant]
    image_url: str
    url: str
    store_domain: str
    created_at: str = ""
    updated_at: str = ""

    @property
    def price(self) -> Optional[float]:
        """Lowest variant price."""
        if not self.variants:
            return None
        return min(v.price for v in self.variants)

    @property
    def compare_at_price(self) -> Optional[float]:
        """Highest compare-at price (original price before sale)."""
        prices = [v.compare_at_price for v in self.variants if v.compare_at_price]
        return max(prices) if prices else None

    @property
    def total_inventory(self) -> int:
        """Total inventory across all variants."""
        return sum(
            v.inventory_quantity or 0
            for v in self.variants
            if v.inventory_quantity is not None
        )

    @property
    def is_on_sale(self) -> bool:
        """Check if any variant is on sale."""
        return any(
            v.compare_at_price and v.compare_at_price > v.price
            for v in self.variants
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "handle": self.handle,
            "vendor": self.vendor,
            "product_type": self.product_type,
            "tags": self.tags,
            "price": self.price,
            "compare_at_price": self.compare_at_price,
            "is_on_sale": self.is_on_sale,
            "total_inventory": self.total_inventory,
            "variants": [v.to_dict() for v in self.variants],
            "image_url": self.image_url,
            "url": self.url,
            "store_domain": self.store_domain,
            "platform": "shopify",
        }


class ShopifyScraper:
    """Scrapes Shopify stores via the public products.json API."""

    def __init__(self, headers: Optional[dict] = None):
        self.headers = headers or DEFAULT_HEADERS
        self._request_count = 0

    def _fetch_json(self, url: str) -> Optional[dict]:
        """Fetch URL and return parsed JSON."""
        try:
            req = Request(url, headers=self.headers)
            with urlopen(req, timeout=15) as resp:
                data = resp.read().decode("utf-8", errors="ignore")
                self._request_count += 1
                return json.loads(data)
        except (HTTPError, URLError, json.JSONDecodeError, OSError) as e:
            logger.warning(f"Shopify fetch failed for {url}: {e}")
            return None

    def _resolve_domain(self, store_input: str) -> str:
        """Resolve store input to a myshopify.com domain."""
        store = store_input.strip().lower()
        # Remove protocol and path
        store = re.sub(r"^https?://", "", store)
        store = store.split("/")[0]
        # If it's a custom domain, try to find the myshopify domain
        if ".myshopify.com" not in store:
            # Try the custom domain first, then try as myshopify subdomain
            return store
        return store

    def _find_myshopify_domain(self, custom_domain: str) -> Optional[str]:
        """Try to find the myshopify.com domain for a custom domain."""
        # Fetch the store's HTML and look for myshopify.com references
        try:
            req = Request(
                f"https://{custom_domain}",
                headers={"User-Agent": self.headers["User-Agent"]},
            )
            with urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                match = re.search(r"([a-z0-9-]+\.myshopify\.com)", html)
                if match:
                    return match.group(1)
        except Exception:
            pass
        return None

    def scrape_products(
        self,
        store: str,
        limit: int = 50,
        collection_id: Optional[str] = None,
    ) -> list[ShopifyProduct]:
        """
        Scrape products from a Shopify store.
        
        Args:
            store: Store domain (e.g., 'gymshark.com' or 'store.myshopify.com')
            limit: Max products to fetch (max 250 per request)
            collection_id: Optional collection ID to filter by
            
        Returns:
            List of ShopifyProduct objects
        """
        domain = self._resolve_domain(store)

        # Try products.json endpoint
        url = f"https://{domain}/products.json?limit={min(limit, 250)}"
        if collection_id:
            url += f"&collection_id={collection_id}"

        data = self._fetch_json(url)

        # If custom domain failed, try to find myshopify domain
        if not data and ".myshopify.com" not in domain:
            myshopify = self._find_myshopify_domain(domain)
            if myshopify:
                url = f"https://{myshopify}/products.json?limit={min(limit, 250)}"
                data = self._fetch_json(url)
                if data:
                    domain = myshopify

        if not data:
            logger.warning(f"Could not fetch products from {store}")
            return []

        products = []
        for p in data.get("products", []):
            product = self._parse_product(p, domain)
            if product:
                products.append(product)

        logger.info(f"Shopify/{domain}: scraped {len(products)} products")
        return products

    def _parse_product(self, data: dict, domain: str) -> Optional[ShopifyProduct]:
        """Parse a product from the Shopify JSON API response."""
        try:
            variants = []
            for v in data.get("variants", []):
                variants.append(ShopifyVariant(
                    id=v.get("id", 0),
                    title=v.get("title", ""),
                    price=float(v.get("price", 0)),
                    compare_at_price=(
                        float(v["compare_at_price"])
                        if v.get("compare_at_price")
                        else None
                    ),
                    sku=v.get("sku", ""),
                    inventory_quantity=v.get("inventory_quantity"),
                    available=v.get("available", True),
                ))

            # Get first image
            images = data.get("images", [])
            image_url = images[0].get("src", "") if images else ""

            handle = data.get("handle", "")
            url = f"https://{domain}/products/{handle}"

            return ShopifyProduct(
                id=data.get("id", 0),
                title=data.get("title", ""),
                handle=handle,
                vendor=data.get("vendor", ""),
                product_type=data.get("product_type", ""),
                tags=data.get("tags", []),
                variants=variants,
                image_url=image_url,
                url=url,
                store_domain=domain,
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Failed to parse Shopify product: {e}")
            return None

    def get_product_by_handle(self, store: str, handle: str) -> Optional[ShopifyProduct]:
        """Fetch a single product by its handle."""
        domain = self._resolve_domain(store)
        url = f"https://{domain}/products/{handle}.json"
        data = self._fetch_json(url)
        if data and "product" in data:
            return self._parse_product(data["domain"], domain)
        return None

    def search_collections(self, store: str) -> list[dict]:
        """Get all collections from a Shopify store."""
        domain = self._resolve_domain(store)
        url = f"https://{domain}/collections.json?limit=50"
        data = self._fetch_json(url)
        if data:
            return data.get("collections", [])
        return []

    @property
    def request_count(self) -> int:
        return self._request_count
