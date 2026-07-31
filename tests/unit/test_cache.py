"""Unit tests for cache.py (Redis helpers for the current-user cache)."""
import pytest

from cache import cache_user, get_cached_user, invalidate_user_cache, user_cache_key
from schemas import CachedUser


def _cached_user(user_id=1):
    return CachedUser(
        id=user_id,
        username="anna",
        email="anna@example.com",
        avatar=None,
        confirmed=True,
        role="user",
    )


class TestUserCacheKey:
    def test_key_is_stable_and_namespaced(self):
        assert user_cache_key(42) == "contacts_api:user:42"


class TestCacheRoundtrip:
    @pytest.mark.asyncio
    async def test_cache_then_get_returns_same_user(self, fake_redis):
        user = _cached_user()
        await cache_user(fake_redis, user)
        result = await get_cached_user(fake_redis, user.id)
        assert result == user

    @pytest.mark.asyncio
    async def test_get_missing_key_returns_none(self, fake_redis):
        assert await get_cached_user(fake_redis, 999) is None

    @pytest.mark.asyncio
    async def test_invalidate_removes_entry(self, fake_redis):
        user = _cached_user()
        await cache_user(fake_redis, user)
        await invalidate_user_cache(fake_redis, user.id)
        assert await get_cached_user(fake_redis, user.id) is None

    @pytest.mark.asyncio
    async def test_get_cached_user_with_corrupted_payload_self_heals(self, fake_redis):
        await fake_redis.set(user_cache_key(7), "{not-valid-json")
        result = await get_cached_user(fake_redis, 7)
        assert result is None
        # The corrupted key should have been cleaned up.
        assert await fake_redis.get(user_cache_key(7)) is None