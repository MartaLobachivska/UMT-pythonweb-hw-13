"""Unit tests for security.py (password hashing and JWT helpers)."""
from datetime import timedelta

import pytest
from fastapi import HTTPException
from jose import jwt

import security
from cache import cache_user
from config import settings
from schemas import CachedUser


class TestPasswordHashing:
    def test_hash_and_verify_roundtrip(self):
        hashed = security.get_password_hash("mypassword1")
        assert hashed != "mypassword1"
        assert security.verify_password("mypassword1", hashed) is True

    def test_verify_rejects_wrong_password(self):
        hashed = security.get_password_hash("mypassword1")
        assert security.verify_password("wrongpassword", hashed) is False


class TestTokens:
    def test_access_token_roundtrip(self):
        token = security.create_access_token({"sub": "a@example.com", "user_id": 1})
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        assert payload["sub"] == "a@example.com"
        assert payload["user_id"] == 1
        assert payload["token_type"] == "access"

    def test_refresh_token_has_refresh_type(self):
        token = security.create_refresh_token({"sub": "a@example.com", "user_id": 1})
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        assert payload["token_type"] == "refresh"

    def test_email_token_extracts_email_for_matching_type(self):
        token = security.create_email_token({"sub": "a@example.com"})
        assert security.get_email_from_token(token, "verify_email") == "a@example.com"

    def test_email_token_rejected_for_wrong_purpose(self):
        token = security.create_email_token({"sub": "a@example.com"})
        # Token was minted for email verification, not password reset.
        assert security.get_email_from_token(token, "password_reset") is None

    def test_password_reset_token_roundtrip(self):
        token = security.create_password_reset_token({"sub": "a@example.com"})
        assert security.get_email_from_token(token, "password_reset") == "a@example.com"

    def test_garbage_token_returns_none(self):
        assert security.get_email_from_token("not-a-jwt", "verify_email") is None

    def test_expired_token_returns_none(self):
        expired = security._create_token(
            {"sub": "a@example.com"}, timedelta(seconds=-1), "verify_email"
        )
        assert security.get_email_from_token(expired, "verify_email") is None


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_returns_cached_user_without_hitting_db(self, fake_redis, make_user):
        user = make_user()
        cached = CachedUser.model_validate(user)
        await cache_user(fake_redis, cached)
        token = security.create_access_token({"sub": user.email, "user_id": user.id})

        result = await security.get_current_user(token=token, db=None, redis=fake_redis)
        assert result.id == user.id
        assert result.email == user.email

    @pytest.mark.asyncio
    async def test_falls_back_to_db_and_populates_cache(self, fake_redis, make_user, db_session):
        user = make_user()
        token = security.create_access_token({"sub": user.email, "user_id": user.id})

        result = await security.get_current_user(token=token, db=db_session, redis=fake_redis)
        assert result.id == user.id
        # The cache should now be populated for next time.
        from cache import get_cached_user

        cached = await get_cached_user(fake_redis, user.id)
        assert cached is not None
        assert cached.id == user.id

    @pytest.mark.asyncio
    async def test_rejects_invalid_token(self, fake_redis):
        with pytest.raises(HTTPException) as exc_info:
            await security.get_current_user(token="garbage", db=None, redis=fake_redis)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_rejects_refresh_token_used_as_access_token(self, fake_redis, make_user):
        user = make_user()
        refresh_token = security.create_refresh_token({"sub": user.email, "user_id": user.id})
        with pytest.raises(HTTPException) as exc_info:
            await security.get_current_user(token=refresh_token, db=None, redis=fake_redis)
        assert exc_info.value.status_code == 401


class TestGetCurrentAdminUser:
    def test_allows_admin(self, make_user):
        user = make_user(role="admin")
        cached = CachedUser.model_validate(user)
        assert security.get_current_admin_user(cached).role == "admin"

    def test_rejects_regular_user(self, make_user):
        user = make_user(role="user")
        cached = CachedUser.model_validate(user)
        with pytest.raises(HTTPException) as exc_info:
            security.get_current_admin_user(cached)
        assert exc_info.value.status_code == 403