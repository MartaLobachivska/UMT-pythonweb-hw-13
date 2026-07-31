"""Password hashing and JWT helpers for the Contacts API.

This module owns three responsibilities:

- hashing/verifying user passwords with bcrypt;
- minting and validating short-lived JWTs for the access, refresh, email
  verification and password reset flows;
- the :func:`get_current_user` / :func:`get_current_admin_user` FastAPI
  dependencies used to authenticate and authorize requests.
"""
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from redis.asyncio import Redis
from sqlalchemy.orm import Session

import models
import schemas
from cache import cache_user, get_cached_user, get_redis
from config import settings
from database import get_db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_password_hash(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a plaintext password against a previously stored bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def _create_token(data: dict, expires_delta: timedelta, token_type: str) -> str:
    """Encode a JWT carrying ``data`` plus an expiry and a purpose tag.

    The ``token_type`` claim (``"access"``, ``"refresh"``, ``"verify_email"``
    or ``"password_reset"``) lets every consumer reject a token minted for a
    different purpose, even if it is otherwise well-formed and unexpired.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire, "token_type": token_type})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_access_token(data: dict) -> str:
    """Mint a short-lived access token used to authenticate API requests."""
    return _create_token(data, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES), "access")


def create_refresh_token(data: dict) -> str:
    """Mint a longer-lived refresh token used to obtain new access tokens."""
    return _create_token(data, timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS), "refresh")


def create_email_token(data: dict) -> str:
    """Mint a token used only to confirm ownership of an email address."""
    return _create_token(data, timedelta(hours=settings.VERIFY_EMAIL_EXPIRE_HOURS), "verify_email")


def create_password_reset_token(data: dict) -> str:
    """Mint a token used only to authorize a single password reset."""
    return _create_token(
        data, timedelta(minutes=settings.RESET_PASSWORD_EXPIRE_MINUTES), "password_reset"
    )


def get_email_from_token(token: str, expected_type: str) -> str | None:
    """Return the ``sub`` (email) claim if ``token`` is valid, unexpired and
    was minted for ``expected_type``; otherwise return ``None``.

    Every failure mode (garbage token, expired token, wrong purpose) is
    treated the same way on purpose: callers only need to branch on
    "is this a usable, correctly-scoped token or not".
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None
    if payload.get("token_type") != expected_type:
        return None
    email = payload.get("sub")
    return email if isinstance(email, str) else None


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> schemas.CachedUser:
    """Resolve the caller's identity from a bearer access token.

    The user is looked up in the Redis cache first (see ``cache.py``); only
    on a cache miss does this fall back to the database, after which the
    result is written back into the cache for subsequent requests.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        user_id = payload.get("user_id")
        if payload.get("token_type") != "access" or not isinstance(user_id, int):
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    cached_user = await get_cached_user(redis, user_id)
    if cached_user is not None:
        return cached_user

    if db is None:
        raise credentials_exception
    user = db.get(models.User, user_id)
    if user is None:
        raise credentials_exception

    cached_user = schemas.CachedUser.model_validate(user)
    await cache_user(redis, cached_user)
    return cached_user


def get_current_admin_user(
    current_user: Annotated[schemas.CachedUser, Depends(get_current_user)],
) -> schemas.CachedUser:
    """Require the caller to hold the ``"admin"`` role; raise 403 otherwise."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user