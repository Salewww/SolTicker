"""
Authentication routes — JWT-based auth for API and Chrome extension.
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, EmailStr

logger = logging.getLogger(__name__)

router = APIRouter()

# JWT settings
JWT_SECRET = os.getenv("JWT_SECRET", "solticker-dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24 * 30  # 30 days

# In-memory user store for MVP (replace with Supabase in production)
# Format: {email: {password_hash, tier, created_at}}
_USERS: dict[str, dict] = {}

try:
    from jose import jwt, JWTError
    HAS_JOSE = True
except ImportError:
    HAS_JOSE = False
    logger.warning("python-jose not available, using basic token auth")

try:
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    HAS_PASSLIB = True
except ImportError:
    HAS_PASSLIB = False
    logger.warning("passlib not available, storing passwords in plaintext (DEV ONLY)")


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


def _hash_password(password: str) -> str:
    if HAS_PASSLIB:
        return pwd_context.hash(password)
    return password  # DEV ONLY


def _verify_password(password: str, hashed: str) -> bool:
    if HAS_PASSLIB:
        return pwd_context.verify(password, hashed)
    return password == hashed  # DEV ONLY


def _create_token(email: str, tier: str = "free") -> str:
    if HAS_JOSE:
        payload = {
            "sub": email,
            "tier": tier,
            "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
        }
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    # Fallback: simple token
    return f"dev-token-{email}-{tier}"


def _verify_token(token: str) -> Optional[dict]:
    if HAS_JOSE:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return payload
        except JWTError:
            return None
    # Fallback: parse dev token
    if token.startswith("dev-token-"):
        parts = token.split("-")
        if len(parts) >= 4:
            return {"sub": parts[2], "tier": parts[3]}
    return None


async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """Dependency to get the current authenticated user."""
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
    """Create a new account."""
    if req.email in _USERS:
        raise HTTPException(status_code=409, detail="Email already registered")

    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    _USERS[req.email] = {
        "password": _hash_password(req.password),
        "tier": "free",
        "created_at": datetime.utcnow().isoformat(),
    }

    token = _create_token(req.email, "free")
    logger.info(f"New signup: {req.email}")
    return TokenResponse(access_token=token, tier="free")


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    """Log in to an existing account."""
    user = _USERS.get(req.email)
    if not user or not _verify_password(req.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = _create_token(req.email, user.get("tier", "free"))
    return TokenResponse(access_token=token, tier=user.get("tier", "free"))


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Get current user info."""
    return {
        "email": user["email"],
        "tier": user["tier"],
    }
