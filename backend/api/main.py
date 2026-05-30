"""
SolTicker — Main FastAPI application.
"""

from __future__ import annotations

import os
import sys
import logging
import pathlib
from contextlib import asynccontextmanager
from typing import Optional

# Ensure backend/ is in Python path for imports
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from scrapers import AmazonScraper, ShopifyScraper, TikTokShopScraper
from utils.matching import match_products
from utils.cache import Cache

logger = logging.getLogger(__name__)

# Import API routers with error handling
try:
    from api import auth, billing, lookup
except ImportError as e:
    logger.error(f"Failed to import API routers: {e}")
    auth = billing = lookup = None

# Global cache instance
cache = Cache(default_ttl=300)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("SolTicker API starting up")
    yield
    logger.info("SolTicker API shutting down")


app = FastAPI(
    title="SolTicker API",
    description="Cross-platform pricing intelligence for TikTok Shop sellers",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow Chrome extension and frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "chrome-extension://*",
        "http://localhost:*",
        "https://solticker.app",
        "https://*.solticker.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
if auth:
    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
if billing:
    app.include_router(billing.router, prefix="/api/billing", tags=["billing"])
if lookup:
    app.include_router(lookup.router, prefix="/api", tags=["lookup"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "solticker-api"}


@app.get("/api/lookup")
async def lookup_product(
    q: str = Query(..., min_length=2, max_length=200, description="Product search query"),
    platforms: str = Query("all", description="Platforms: amazon, shopify, tiktok, all"),
    shopify_store: Optional[str] = Query(None, description="Shopify store domain"),
):
    """
    Look up a product across platforms.
    Returns matching products from Amazon, Shopify, and/or TikTok Shop.
    """
    # Check cache
    cache_key = f"lookup:{q}:{platforms}:{shopify_store}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    results = {"query": q, "platforms": {}}

    platform_list = ["amazon", "shopify", "tiktok"] if platforms == "all" else platforms.split(",")

    amazon_results = []
    shopify_results = []
    tiktok_results = []

    if "amazon" in platform_list:
        try:
            az = AmazonScraper()
            amazon_results = [p.to_dict() for p in az.search_products(q, max_results=5)]
            results["platforms"]["amazon"] = amazon_results
        except Exception as e:
            logger.error(f"Amazon lookup error: {e}")
            results["platforms"]["amazon"] = {"error": str(e)}

    if "shopify" in platform_list:
        try:
            sf = ShopifyScraper()
            # If a specific store is provided, search there; otherwise return empty
            if shopify_store:
                shopify_results = [p.to_dict() for p in sf.scrape_products(shopify_store, limit=20)]
            results["platforms"]["shopify"] = shopify_results
        except Exception as e:
            logger.error(f"Shopify lookup error: {e}")
            results["platforms"]["shopify"] = {"error": str(e)}

    if "tiktok" in platform_list:
        try:
            tt = TikTokShopScraper()
            # For TikTok, we need a product ID, not a search query
            # Return a message explaining this
            results["platforms"]["tiktok"] = {
                "info": "TikTok Shop requires a specific product URL/ID. Use /api/lookup/tiktok/{product_id}."
            }
        except Exception as e:
            logger.error(f"TikTok lookup error: {e}")
            results["platforms"]["tiktok"] = {"error": str(e)}

    # Cross-platform matching
    if amazon_results or shopify_results:
        match = match_products(q, amazon_results, shopify_results, tiktok_results)
        results["match"] = match.to_dict()

    # Cache for 5 minutes
    cache.set(cache_key, results, ttl=300)

    return results


@app.get("/api/lookup/tiktok/{product_id}")
async def lookup_tiktok_product(product_id: str):
    """Look up a specific TikTok Shop product by ID."""
    cache_key = f"tiktok:{product_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    scraper = TikTokShopScraper()
    product = scraper.scrape_product(product_id)

    if not product:
        raise HTTPException(status_code=404, detail="Product not found or scraping failed")

    result = product.to_dict()
    cache.set(cache_key, result, ttl=600)
    return result


@app.get("/api/categories")
async def list_categories():
    """List available Amazon Best Sellers categories."""
    return {"categories": list(AMAZON_BS_CATEGORIES.keys())}


@app.get("/api/scrape/amazon/{category}")
async def scrape_amazon_category(
    category: str,
    limit: int = Query(20, ge=1, le=100),
):
    """Scrape an Amazon Best Sellers category."""
    from scrapers.amazon import AMAZON_BS_CATEGORIES
    if category not in AMAZON_BS_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown category. Available: {list(AMAZON_BS_CATEGORIES.keys())}",
        )

    scraper = AmazonScraper()
    products = scraper.scrape_category(category, top_n=limit)
    return {
        "category": category,
        "count": len(products),
        "products": [p.to_dict() for p in products],
    }


@app.get("/api/scrape/shopify/{store}")
async def scrape_shopify_store(
    store: str,
    limit: int = Query(50, ge=1, le=250),
):
    """Scrape products from a Shopify store."""
    scraper = ShopifyScraper()
    products = scraper.scrape_products(store, limit=limit)
    return {
        "store": store,
        "count": len(products),
        "products": [p.to_dict() for p in products],
    }


# Re-export for convenience
from scrapers.amazon import AMAZON_BS_CATEGORIES


# ── Static Files ──
_STATIC_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "static"

@app.get("/og-image.png", include_in_schema=False)
async def og_image():
    p = _STATIC_DIR / "og-image.png"
    if p.exists():
        return FileResponse(str(p), media_type="image/png")
    raise HTTPException(status_code=404)

@app.get("/favicon-32x32.png", include_in_schema=False)
async def favicon():
    p = _STATIC_DIR / "favicon-32x32.png"
    if p.exists():
        return FileResponse(str(p), media_type="image/png")
    raise HTTPException(status_code=404)

@app.get("/apple-touch-icon.png", include_in_schema=False)
async def apple_touch_icon():
    p = _STATIC_DIR / "apple-touch-icon.png"
    if p.exists():
        return FileResponse(str(p), media_type="image/png")
    raise HTTPException(status_code=404)

@app.get("/favicon.ico", include_in_schema=False)
async def favicon_ico():
    p = _STATIC_DIR / "favicon.ico"
    if p.exists():
        return FileResponse(str(p), media_type="image/x-icon")
    raise HTTPException(status_code=404)


# ── Landing Page ──

_LANDING_HTML = pathlib.Path(__file__).resolve().parent.parent.parent / "infra" / "landing.html"

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def landing_page():
    """Serve the landing page."""
    if _LANDING_HTML.exists():
        return HTMLResponse(content=_LANDING_HTML.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>SolTicker</h1><p>API is running. Docs at <a href='/docs'>/docs</a></p>")
