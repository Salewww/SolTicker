"""
Billing routes — Stripe integration for subscription management.
"""

from __future__ import annotations

import os
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Request

logger = logging.getLogger(__name__)

router = APIRouter()

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_BASIC = os.getenv("STRIPE_PRICE_BASIC", "")  # $29/mo
STRIPE_PRICE_PRO = os.getenv("STRICE_PRICE_PRO", "")  # $59/mo

# User tier management
_USER_TIERS: dict[str, str] = {}  # email -> tier

try:
    import stripe
    stripe.api_key = STRIPE_SECRET_KEY
    HAS_STRIPE = True
except ImportError:
    HAS_STRIPE = False
    logger.warning("stripe not available, billing disabled")

# Tier limits
TIER_LIMITS = {
    "free": {"lookups_per_day": 5, "history_days": 0, "alerts": 0},
    "basic": {"lookups_per_day": 100, "history_days": 30, "alerts": 5},
    "pro": {"lookups_per_day": 1000, "history_days": 90, "alerts": 50},
}


async def get_current_user(request: Request) -> dict:
    """Extract user from JWT token."""
    from .auth import get_current_user as _get_user
    try:
        auth = request.headers.get("authorization")
        if auth:
            return await _get_user(auth)
    except Exception:
        pass
    return {"email": "anonymous", "tier": "free"}


def check_tier_limit(user: dict, feature: str) -> bool:
    """Check if user's tier allows a feature."""
    tier = user.get("tier", "free")
    return tier in TIER_LIMITS


@router.get("/tiers")
async def list_tiers():
    """List available subscription tiers."""
    return {
        "tiers": {
            "free": {
                "name": "Free",
                "price": 0,
                "limits": TIER_LIMITS["free"],
            },
            "basic": {
                "name": "Price Insight Basic",
                "price": 29,
                "limits": TIER_LIMITS["basic"],
            },
            "pro": {
                "name": "Pro Insights Package",
                "price": 59,
                "limits": TIER_LIMITS["pro"],
            },
        },
    }


@router.get("/status")
async def billing_status(user: dict = Depends(get_current_user)):
    """Get current user's billing status."""
    tier = user.get("tier", "free")
    return {
        "tier": tier,
        "limits": TIER_LIMITS.get(tier, TIER_LIMITS["free"]),
    }


@router.post("/checkout")
async def create_checkout(
    tier: str,
    user: dict = Depends(get_current_user),
):
    """
    Create a Stripe checkout session.
    tier: 'basic' or 'pro'
    """
    if not HAS_STRIPE:
        raise HTTPException(status_code=503, detail="Billing not available")

    if tier not in ("basic", "pro"):
        raise HTTPException(status_code=400, detail="Invalid tier. Choose 'basic' or 'pro'.")

    price_id = STRIPE_PRICE_BASIC if tier == "basic" else STRIPE_PRICE_PRO
    if not price_id:
        raise HTTPException(status_code=503, detail="Stripe price not configured")

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer_email=user.get("email"),
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=os.getenv("APP_URL", "https://solticker.app") + "/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=os.getenv("APP_URL", "https://solticker.app") + "/pricing",
            metadata={"email": user.get("email", ""), "tier": tier},
        )
        return {"checkout_url": session.url}
    except Exception as e:
        logger.error(f"Stripe checkout error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create checkout session")


@router.post("/portal")
async def customer_portal(user: dict = Depends(get_current_user)):
    """Open Stripe customer portal for subscription management."""
    if not HAS_STRIPE:
        raise HTTPException(status_code=503, detail="Billing not available")

    try:
        # Find customer by email
        customers = stripe.Customer.list(email=user.get("email"), limit=1)
        if not customers.data:
            raise HTTPException(status_code=404, detail="No subscription found")

        session = stripe.billing_portal.Session.create(
            customer=customers.data[0].id,
            return_url=os.getenv("APP_URL", "https://solticker.app"),
        )
        return {"portal_url": session.url}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Stripe portal error: {e}")
        raise HTTPException(status_code=500, detail="Failed to open billing portal")


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events."""
    if not HAS_STRIPE:
        raise HTTPException(status_code=503, detail="Billing not available")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        logger.error(f"Webhook signature verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Handle subscription events
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        email = session.get("metadata", {}).get("email")
        tier = session.get("metadata", {}).get("tier", "basic")
        if email:
            _USER_TIERS[email] = tier
            logger.info(f"Subscription activated: {email} -> {tier}")

    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        customer_id = subscription.get("customer")
        if customer_id:
            customer = stripe.Customer.retrieve(customer_id)
            email = customer.get("email")
            if email:
                _USER_TIERS[email] = "free"
                logger.info(f"Subscription cancelled: {email} -> free")

    return {"status": "ok"}
