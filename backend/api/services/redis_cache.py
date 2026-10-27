"""
Redis-backed cache service for HR-bot.

Provides:
- Async Redis connection with connection pooling
- Hash-based caching for AI analysis results
- Scoring cache for vacancy matching
- Automatic TTL-based expiration
- Fallback to in-memory cache if Redis unavailable
"""

import json
import logging
from typing import Optional, Dict, Any
from datetime import timedelta

from ..config import settings

logger = logging.getLogger("hr-analyzer.redis")

# Redis client singleton
_redis_client = None
_redis_available = None


async def get_redis():
    """Get Redis client with lazy initialization and connection pooling."""
    global _redis_client, _redis_available

    # Return cached availability status
    if _redis_available is False:
        return None

    if _redis_client is not None:
        return _redis_client

    try:
        import redis.asyncio as redis

        # Parse Redis URL and create client with connection pool
        _redis_client = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )

        # Test connection
        await _redis_client.ping()
        _redis_available = True
        logger.info(f"Redis connected: {settings.redis_url.split('@')[-1] if '@' in settings.redis_url else 'localhost'}")
        return _redis_client

    except ImportError:
        logger.warning("redis package not installed, using in-memory cache")
        _redis_available = False
        return None
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}, using in-memory cache")
        _redis_available = False
        return None


async def close_redis():
    """Close Redis connection on shutdown."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
        logger.info("Redis connection closed")


class RedisCacheService:
    """
    Redis-backed cache with automatic fallback to in-memory.

    Key prefixes:
    - analysis:{chat_id}:{hash} - AI analysis results
    - score:{entity_id}:{vacancy_id} - Compatibility scores
    - entity:{entity_id}:profile - Entity AI profiles
    """

    # In-memory fallback cache
    _memory_cache: Dict[str, Dict[str, Any]] = {}

    @classmethod
    async def get(cls, key: str) -> Optional[str]:
        """Get value from cache."""
        redis = await get_redis()

        if redis:
            try:
                value = await redis.get(key)
                if value:
                    logger.debug(f"Redis cache hit: {key}")
                return value
            except Exception as e:
                logger.warning(f"Redis get error: {e}")

        # Fallback to memory cache
        entry = cls._memory_cache.get(key)
        if entry:
            logger.debug(f"Memory cache hit: {key}")
            return entry.get('value')
        return None

    @classmethod
    async def set(cls, key: str, value: str, ttl_seconds: int = 3600) -> bool:
        """Set value in cache with TTL."""
        redis = await get_redis()

        if redis:
            try:
                await redis.setex(key, ttl_seconds, value)
                logger.debug(f"Redis cache set: {key} (TTL: {ttl_seconds}s)")
                return True
            except Exception as e:
                logger.warning(f"Redis set error: {e}")

        # Fallback to memory cache
        from datetime import datetime
        cls._memory_cache[key] = {
            'value': value,
            'expires_at': datetime.utcnow() + timedelta(seconds=ttl_seconds)
        }
        logger.debug(f"Memory cache set: {key}")
        return True

    @classmethod
    async def delete(cls, key: str) -> bool:
        """Delete key from cache."""
        redis = await get_redis()

        if redis:
            try:
                await redis.delete(key)
                logger.debug(f"Redis cache delete: {key}")
            except Exception as e:
                logger.warning(f"Redis delete error: {e}")

        # Also remove from memory cache
        cls._memory_cache.pop(key, None)
        return True

    @classmethod
    async def delete_pattern(cls, pattern: str) -> int:
        """Delete all keys matching pattern (e.g., 'score:123:*')."""
        count = 0
        redis = await get_redis()

        if redis:
            try:
                async for key in redis.scan_iter(match=pattern):
                    await redis.delete(key)
                    count += 1
                logger.info(f"Redis deleted {count} keys matching: {pattern}")
            except Exception as e:
                logger.warning(f"Redis delete pattern error: {e}")

        # Also clean memory cache
        keys_to_delete = [
            k for k in cls._memory_cache.keys()
            if cls._match_pattern(k, pattern)
        ]
        for key in keys_to_delete:
            del cls._memory_cache[key]
            count += 1

        return count

    @staticmethod
    def _match_pattern(key: str, pattern: str) -> bool:
        """Simple pattern matching for memory cache (supports * wildcard)."""
        if '*' not in pattern:
            return key == pattern

        parts = pattern.split('*')
        if len(parts) == 2:
            prefix, suffix = parts
            return key.startswith(prefix) and key.endswith(suffix)
        return False

    @classmethod
    async def get_json(cls, key: str) -> Optional[Dict[str, Any]]:
        """Get JSON value from cache."""
        value = await cls.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return None
        return None

    @classmethod
    async def set_json(cls, key: str, value: Dict[str, Any], ttl_seconds: int = 3600) -> bool:
        """Set JSON value in cache."""
        return await cls.set(key, json.dumps(value, default=str), ttl_seconds)

    @classmethod
    async def exists(cls, key: str) -> bool:
        """Check if key exists."""
        redis = await get_redis()

        if redis:
            try:
                return await redis.exists(key) > 0
            except Exception as e:
                logger.warning(f"Redis exists error: {e}")

        return key in cls._memory_cache

    @classmethod
    async def incr(cls, key: str, ttl_seconds: int = None) -> int:
        """Increment counter (useful for rate limiting)."""
        redis = await get_redis()

        if redis:
            try:
                value = await redis.incr(key)
                if ttl_seconds and value == 1:
                    await redis.expire(key, ttl_seconds)
                return value
            except Exception as e:
                logger.warning(f"Redis incr error: {e}")

        # Memory fallback
        entry = cls._memory_cache.get(key, {'value': '0'})
        new_value = int(entry.get('value', 0)) + 1
        cls._memory_cache[key] = {'value': str(new_value)}
        return new_value

    @classmethod
    async def clear_all(cls) -> int:
        """Clear all cache (use with caution!)."""
        count = 0
        redis = await get_redis()

        if redis:
            try:
                # Only clear our app's keys, not entire Redis
                async for key in redis.scan_iter(match="analysis:*"):
                    await redis.delete(key)
                    count += 1
                async for key in redis.scan_iter(match="score:*"):
                    await redis.delete(key)
                    count += 1
                async for key in redis.scan_iter(match="entity:*"):
                    await redis.delete(key)
                    count += 1
                logger.info(f"Redis cleared {count} app cache entries")
            except Exception as e:
                logger.warning(f"Redis clear error: {e}")

        # Clear memory cache
        memory_count = len(cls._memory_cache)
        cls._memory_cache.clear()

        return count + memory_count

    @classmethod
    async def get_stats(cls) -> Dict[str, Any]:
        """Get cache statistics."""
        stats = {
            "redis_available": _redis_available,
            "memory_cache_size": len(cls._memory_cache),
        }

        redis = await get_redis()
        if redis:
            try:
                info = await redis.info("memory")
                stats["redis_memory_used"] = info.get("used_memory_human", "unknown")
                stats["redis_keys"] = await redis.dbsize()
            except Exception as e:
                stats["redis_error"] = str(e)

        return stats


# Singleton instance
redis_cache = RedisCacheService()
