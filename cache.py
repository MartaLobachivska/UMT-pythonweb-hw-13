"""Redis-backed cache for the current authenticated user.

Storing the pared-down :class:`schemas.CachedUser` representation in Redis
lets ``security.get_current_user`` skip a database round-trip on almost
every authenticated request. The cache is explicitly invalidated in
``main.py`` whenever the underlying user record changes (avatar, password
or role update), so it can never serve stale data for longer than that.
"""
from redis.asyncio import Redis

from config import settings
from schemas import CachedUser

CACHE_PREFIX = "contacts_api:user"


def user_cache_key(user_id: int) -> str:
    """Build the namespaced Redis key used to cache a given user."""
    return f"{CACHE_PREFIX}:{user_id}"


async def get_redis() -> Redis:
    """FastAPI dependency that provides a Redis client for the request."""
    return Redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)


async def cache_user(redis: Redis, user: CachedUser) -> None:
    """Store ``user`` in Redis as JSON, with a TTL from settings."""
    await redis.set(
        user_cache_key(user.id),
        user.model_dump_json(),
        ex=settings.USER_CACHE_EXPIRE_SECONDS,
    )


async def get_cached_user(redis: Redis, user_id: int) -> CachedUser | None:
    """Return the cached user, or ``None`` on a miss or corrupted payload.

    A corrupted (non-JSON) payload is treated as a miss and the bad key is
    deleted so it does not keep failing on every subsequent request.
    """
    raw = await redis.get(user_cache_key(user_id))
    if raw is None:
        return None
    try:
        return CachedUser.model_validate_json(raw)
    except ValueError:
        await redis.delete(user_cache_key(user_id))
        return None


async def invalidate_user_cache(redis: Redis, user_id: int) -> None:
    """Remove a user's cached entry, e.g. after an avatar/password/role change."""
    await redis.delete(user_cache_key(user_id))