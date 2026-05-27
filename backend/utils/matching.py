"""
Product matching engine.
Matches similar products across platforms using title similarity and metadata.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from rapidfuzz import fuzz, process
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False
    logger.warning("rapidfuzz not available, using basic matching")


@dataclass
class ProductMatch:
    """Represents a match between products across platforms."""
    query_title: str
    amazon_asin: Optional[str]
    amazon_title: Optional[str]
    amazon_price: Optional[float]
    shopify_handle: Optional[str]
    shopify_title: Optional[str]
    shopify_price: Optional[float]
    tiktok_id: Optional[str]
    tiktok_title: Optional[str]
    tiktok_price: Optional[float]
    match_score: float  # 0-100

    def to_dict(self) -> dict:
        return {
            "query": self.query_title,
            "match_score": self.match_score,
            "amazon": {
                "asin": self.amazon_asin,
                "title": self.amazon_title,
                "price": self.amazon_price,
            } if self.amazon_asin else None,
            "shopify": {
                "handle": self.shopify_handle,
                "title": self.shopify_title,
                "price": self.shopify_price,
            } if self.shopify_handle else None,
            "tiktok": {
                "id": self.tiktok_id,
                "title": self.tiktok_title,
                "price": self.tiktok_price,
            } if self.tiktok_id else None,
        }


def normalize_title(title: str) -> str:
    """Normalize a product title for comparison."""
    # Lowercase
    title = title.lower().strip()
    # Remove special chars but keep spaces
    title = re.sub(r"[^\w\s]", " ", title)
    # Remove extra whitespace
    title = re.sub(r"\s+", " ", title)
    # Remove common filler words
    filler_words = {
        "the", "a", "an", "and", "or", "but", "for", "with",
        "new", "hot", "best", "seller", "premium", "original",
        "official", "brand", "genuine", "authentic",
    }
    words = [w for w in title.split() if w not in filler_words]
    return " ".join(words)


def title_similarity(title1: str, title2: str) -> float:
    """Calculate similarity between two product titles (0-100)."""
    if HAS_RAPIDFUZZ:
        return fuzz.ratio(normalize_title(title1), normalize_title(title2))
    else:
        # Basic fallback: word overlap ratio
        words1 = set(normalize_title(title1).split())
        words2 = set(normalize_title(title2).split())
        if not words1 or not words2:
            return 0.0
        overlap = len(words1 & words2)
        return (overlap / max(len(words1), len(words2))) * 100


def find_best_match(
    query: str,
    candidates: list[dict],
    threshold: float = 60.0,
) -> Optional[dict]:
    """
    Find the best matching product from a list of candidates.
    
    Args:
        query: Search query / product title
        candidates: List of product dicts with 'title' key
        threshold: Minimum similarity score (0-100)
        
    Returns:
        Best matching candidate dict with '_score' key added, or None
    """
    if not candidates:
        return None

    if HAS_RAPIDFUZZ:
        titles = [c.get("title", "") for c in candidates]
        result = process.extractOne(
            query,
            titles,
            scorer=fuzz.ratio,
            score_cutoff=threshold,
        )
        if result:
            matched_title, score, idx = result
            candidate = dict(candidates[idx])
            candidate["_score"] = score
            return candidate
    else:
        best_score = 0
        best_candidate = None
        for candidate in candidates:
            score = title_similarity(query, candidate.get("title", ""))
            if score > best_score and score >= threshold:
                best_score = score
                best_candidate = dict(candidate)
                best_candidate["_score"] = score
        return best_candidate

    return None


def match_products(
    query: str,
    amazon_results: list[dict],
    shopify_results: list[dict],
    tiktok_results: list[dict],
    threshold: float = 55.0,
) -> ProductMatch:
    """
    Match a query across all three platforms.
    
    Args:
        query: Product search query
        amazon_results: List of Amazon product dicts
        shopify_results: List of Shopify product dicts
        tiktok_results: List of TikTok product dicts
        threshold: Minimum match score
        
    Returns:
        ProductMatch with best matches from each platform
    """
    amazon_match = find_best_match(query, amazon_results, threshold)
    shopify_match = find_best_match(query, shopify_results, threshold)
    tiktok_match = find_best_match(query, tiktok_results, threshold)

    # Calculate overall match score
    scores = []
    if amazon_match:
        scores.append(amazon_match.get("_score", 0))
    if shopify_match:
        scores.append(shopify_match.get("_score", 0))
    if tiktok_match:
        scores.append(tiktok_match.get("_score", 0))
    avg_score = sum(scores) / len(scores) if scores else 0

    return ProductMatch(
        query_title=query,
        amazon_asin=amazon_match.get("asin") if amazon_match else None,
        amazon_title=amazon_match.get("title") if amazon_match else None,
        amazon_price=amazon_match.get("price") if amazon_match else None,
        shopify_handle=shopify_match.get("handle") if shopify_match else None,
        shopify_title=shopify_match.get("title") if shopify_match else None,
        shopify_price=shopify_match.get("price") if shopify_match else None,
        tiktok_id=tiktok_match.get("product_id") if tiktok_match else None,
        tiktok_title=tiktok_match.get("title") if tiktok_match else None,
        tiktok_price=tiktok_match.get("price") if tiktok_match else None,
        match_score=avg_score,
    )
