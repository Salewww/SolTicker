"""
Daily scraper scheduler.
Run via cron to update prices for all tracked products.
"""

from __future__ import annotations

import logging
import asyncio
from datetime import date
from scrapers import AmazonScraper, ShopifyScraper

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Tracked Shopify stores for daily scraping
TRACKED_STORES = [
    "gymshark.com",
    "allbirds.com",
    "chubbiesshorts.com",
    "tenthandporter.com",
    # Add more as needed
]

# Amazon categories to track
TRACKED_CATEGORIES = [
    "electronics",
    "home_kitchen",
    "clothing",
    "beauty",
    "sports",
]


async def update_amazon_prices():
    """Scrape Best Sellers prices for tracked categories."""
    az = AmazonScraper()
    all_products = []
    
    for category in TRACKED_CATEGORIES:
        try:
            products = az.scrape_category(category, top_n=50)
            all_products.extend(products)
            logger.info(f"Amazon/{category}: {len(products)} products")
        except Exception as e:
            logger.error(f"Amazon/{category} failed: {e}")
    
    # Here you would upsert into DB
    # For now, just log
    logger.info(f"Total Amazon products scraped: {len(all_products)}")
    return all_products


async def update_shopify_prices():
    """Scrape prices from tracked Shopify stores."""
    sf = ShopifyScraper()
    all_products = []
    
    for store in TRACKED_STORES:
        try:
            products = sf.scrape_products(store, limit=50)
            all_products.extend(products)
            logger.info(f"Shopify/{store}: {len(products)} products")
        except Exception as e:
            logger.error(f"Shopify/{store} failed: {e}")
    
    logger.info(f"Total Shopify products scraped: {len(all_products)}")
    return all_products


async def daily_update():
    """Run the full daily update."""
    logger.info(f"=== Daily price update starting — {date.today()} ===")
    
    amazon_products = await update_amazon_prices()
    shopify_products = await update_shopify_prices()
    
    # TODO: Upsert products and price snapshots into database
    # TODO: Check price alerts and send notifications
    
    logger.info(f"=== Daily update complete — {date.today()} ===")
    return {
        "amazon": len(amazon_products),
        "shopify": len(shopify_products),
        "date": str(date.today()),
    }


if __name__ == "__main__":
    result = asyncio.run(daily_update())
    print(result)
