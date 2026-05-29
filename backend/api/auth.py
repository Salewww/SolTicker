"""
Authentication routes - simplified, no external dependencies beyond fastapi/pydantic.
Uses HMAC-based tokens instead of JWT (no python-jose needed).
"""
from __future__ import annotations

import os
import hmac
import hashlib
import base64
import json
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

# Settings
JWT_SECRET = os.getenv("JWT_SECRET", "solticker-dev-secret-change-in-production")
TOKEN_EXPIRY_DAYS = 30

# In-memory user store
_USERS: dict = {}


class SignupRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tier: str = "free"


def _simple_hash(password: str) -> str:
    """Simple HMAC-based password hashing (good enough for MVP)."""
    return hmac.new(
        JWT_SECRET.encode(), password.encode(), hashlib.sha256
    ).hexdigest()


def _create_token(email: str, tier: str = "free") -> str:
    """Create a simple signed token."""
    payload = json.dumps({"sub": email, "tier": tier, "iat": datetime.utcnow().isoformat()})
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    sig = hmac.new(JWT_SECRET.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()[:16]
    return payload_b64 + "." + sig


def _verify_token(token: str) -> Optional[dict]:
    """Verify a simple signed token."""
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, sig = parts
        expected_sig = hmac.new(JWT_SECRET.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()[:16]
        if sig != expected_sig:
            return None
        # Add padding back
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode()))
        return payload
    except Exception:
        return None


async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid auth scheme")
    payload = _verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    email = payload.get("sub")
    if email not in _USERS:
        raise HTTPException(status_code=401, detail="User not found")
    return {"email": email, "tier": payload.get("tier", "free")}


@router.post("/signup", response_model=TokenResponse)
async def signup(req: SignupRequest):
    if req.email in _USERS:
        raise HTTPException(status_code=409, detail="Email already registered")
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    _USERS[req.email] = {
        "password": _simple_hash(req.password),
        "tier": "free",
        "created_at": datetime.utcnow().isoformat(),
    }
    token = _create_token(req.email, "free")
    logger.info("New signup: " + req.email)
    return TokenResponse(access_token=token, tier="free")


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    user = _USERS.get(req.email)
    if not user or _simple_hash(req.password) != user["password"]:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = _create_token(req.email, user.get("tier", "free"))
    return TokenResponse(access_token=token, tier=user.get("tier", "free"))


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    return {"email": user["email"], "tier": user["tier"]}
