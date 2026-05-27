"""
Product lookup routes — cross-platform price search.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query

from scrapers import AmazonScraper, ShopifyScraper, TikTokShopScraper
from utils.matching import match_products
from utils.cache import Cache

logger = logging.getLogger(__name__)

router = APIRouter()
cache = Cache(default_ttl=300)


@router.get("/search")
async def search_products(
    q: str = Query(..., min_length=2, max_length=200),
    platform: str = Query("amazon", regex="^(amazon|shopify|tiktok|all)$"),
    limit: int = Query(10, ge=1, le=50),
    shopify_store: Optional[str] = None,
):
    """
    Search for products across platforms.
    
    - **q**: Search query (product name, keywords)
    - **platform**: Which platform to search (amazon, shopify, tiktok, all)
    - **limit**: Max results per platform
    - **shopify_store**: Shopify store domain (required if platform=shopify)
    """
    cache_key = f"search:{q}:{platform}:{limit}:{shopify_store}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    results = {"query": q, "results": []}

    if platform in ("amazon", "all"):
        try:
            az = AmazonScraper()
            az_results = az.search_products(q, max_results=limit)
            results["results"].extend([p.to_dict() for p in az_results])
        except Exception as e:
            logger.error(f"Amazon search error: {e}")

    if platform in ("shopify", "all"):
        if shopify_store:
            try:
                sf = ShopifyScraper()
                sf_results = sf.scrape_products(shopify_store, limit=limit)
                results["results"].extend([p.to_dict() for p in sf_results])
            except Exception as e:
                logger.error(f"Shopify search error: {e}")
        elif platform == "shopify":
            raise HTTPException(
                status_code=400,
                detail="shopify_store parameter is required for Shopify search",
            )

    if platform in ("tiktok", "all"):
        # TikTok Shop requires specific product IDs
        results["tiktok_note"] = (
            "TikTok Shop requires a product ID. "
            "Browse to a product page and use the extension popup to look it up."
        )

    # Match and rank results
    if results["results"]:
        results["total"] = len(results["results"])
        # Sort by relevance (exact title match first)
        query_lower = q.lower()
        results["results"].sort(
            key=lambda r: (
                query_lower in r.get("title", "").lower(),
                r.get("price", 0) or 0,
            ),
            reverse=True,
        )

    cache.set(cache_key, results, ttl=300)
    return results


@router.get("/compare/{asin}")
async def compare_product(
    asin: str,
    shopify_store: Optional[str] = None,
):
    """
    Compare an Amazon product (by ASIN) with the same product on other platforms.
    Best for Amazon-first cross-platform comparison.
    """
    cache_key = f"compare:{asin}:{shopify_store}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Get Amazon product info
    az = AmazonScraper()
    # We need to search for the ASIN or use Best Sellers
    # For MVP, we'll return the ASIN info and let the frontend handle it

    result = {
        "asin": asin,
        "amazon_url": f"https://www.amazon.com/dp/{asin}",
        "note": "Full cross-product comparison coming soon",
    }

    cache.set(cache_key, result, ttl=600)
    return result
