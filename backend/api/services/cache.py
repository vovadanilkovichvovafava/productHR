"""
Cache Service for AI analysis results.

Provides:
- Hash-based caching to avoid re-analyzing unchanged data
- Automatic cache invalidation on new messages
- Memory-efficient context management
- Redis-backed storage with in-memory fallback
- Thread-safe operations using asyncio.Lock
"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from ..config import settings
from .redis_cache import redis_cache, get_redis, close_redis

logger = logging.getLogger("hr-analyzer.cache")


class AnalysisCacheService:
    """Service for caching AI analysis results with hash-based invalidation."""

    # In-memory cache for quick lookups (will be replaced with Redis later)
    _cache: Dict[str, Dict[str, Any]] = {}

    # Lock for thread-safe cache operations
    _lock: asyncio.Lock = None

    @classmethod
    @property
    def DEFAULT_TTL_SECONDS(cls) -> int:
        """Default TTL for cached results (configurable via CACHE_TTL_DEFAULT env var)."""
        return settings.cache_ttl_default

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        """Get or create the asyncio lock (lazy initialization for event loop compatibility)."""
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock

    @staticmethod
    def compute_messages_hash(messages: list, criteria: list = None) -> str:
        """
        Compute hash of messages + criteria for cache key.

        Hash changes when:
        - Any message content changes
        - Messages are added/removed
        - Criteria change
        """
        # Extract essential data for hashing
        messages_data = []
        for msg in messages:
            if hasattr(msg, 'id'):
                # SQLAlchemy Message object
                messages_data.append({
                    'id': msg.id,
                    'content': msg.content[:200] if msg.content else '',  # First 200 chars
                    'timestamp': msg.timestamp.isoformat() if msg.timestamp else ''
                })
            elif isinstance(msg, dict):
                # Dict message
                messages_data.append({
                    'content': str(msg.get('content', ''))[:200],
                    'role': msg.get('role', '')
                })

        # Include criteria in hash
        criteria_data = json.dumps(criteria or [], sort_keys=True)

        # Combine and hash
        combined = json.dumps({
            'messages': messages_data,
            'criteria': criteria_data,
            'count': len(messages_data)
        }, sort_keys=True, default=str)

        return hashlib.md5(combined.encode()).hexdigest()

    @staticmethod
    def compute_entity_hash(
        entity,
        chats: list,
        calls: list
    ) -> str:
        """
        Compute hash for entity context (all chats + calls).

        Hash changes when:
        - Entity info changes
        - Any chat messages change
        - Any call transcripts change
        """
        entity_data = {
            'id': entity.id,
            'name': entity.name,
            'status': entity.status.value if entity.status else '',
            'type': entity.type.value if entity.type else ''
        }

        # Hash all chats
        chats_data = []
        for chat in chats:
            msg_count = len(chat.messages) if hasattr(chat, 'messages') and chat.messages else 0
            last_msg_ts = ''
            if msg_count > 0:
                last_msg = max(chat.messages, key=lambda m: m.timestamp if m.timestamp else datetime.min)
                last_msg_ts = last_msg.timestamp.isoformat() if last_msg.timestamp else ''

            chats_data.append({
                'id': chat.id,
                'msg_count': msg_count,
                'last_msg': last_msg_ts
            })

        # Hash all calls
        calls_data = []
        for call in calls:
            calls_data.append({
                'id': call.id,
                'status': call.status.value if call.status else '',
                'transcript_len': len(call.transcript) if call.transcript else 0
            })

        combined = json.dumps({
            'entity': entity_data,
            'chats': chats_data,
            'calls': calls_data
        }, sort_keys=True, default=str)

        return hashlib.md5(combined.encode()).hexdigest()

    @classmethod
    async def get_cached_analysis(
        cls,
        cache_key: str,
        content_hash: str
    ) -> Optional[str]:
        """
        Get cached analysis if hash matches.

        Returns None if:
        - No cache exists
        - Hash doesn't match (content changed)
        - Cache expired

        Uses Redis if available, falls back to in-memory cache.
        """
        redis_key = f"analysis:{cache_key}"

        # Try Redis first
        cache_entry = await redis_cache.get_json(redis_key)

        # Fall back to in-memory if Redis miss
        if not cache_entry:
            async with cls._get_lock():
                cache_entry = cls._cache.get(cache_key)

        if not cache_entry:
            logger.debug(f"Cache miss: {cache_key} (no entry)")
            return None

        # Check hash match
        if cache_entry.get('hash') != content_hash:
            logger.info(f"Cache invalidated: {cache_key} (hash mismatch)")
            # Clean up both caches
            await redis_cache.delete(redis_key)
            async with cls._get_lock():
                cls._cache.pop(cache_key, None)
            return None

        # Check expiry (only for in-memory, Redis handles TTL)
        expires_at = cache_entry.get('expires_at')
        if expires_at and isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if expires_at and datetime.utcnow() > expires_at:
            logger.info(f"Cache expired: {cache_key}")
            await redis_cache.delete(redis_key)
            async with cls._get_lock():
                cls._cache.pop(cache_key, None)
            return None

        logger.info(f"Cache hit: {cache_key}")
        return cache_entry.get('result')

    @classmethod
    async def set_cached_analysis(
        cls,
        cache_key: str,
        content_hash: str,
        result: str,
        ttl_seconds: int = None
    ):
        """Store analysis result in cache with hash for validation.

        Stores in both Redis (if available) and in-memory cache.
        """
        ttl = ttl_seconds or cls.DEFAULT_TTL_SECONDS
        redis_key = f"analysis:{cache_key}"

        cache_data = {
            'hash': content_hash,
            'result': result,
            'created_at': datetime.utcnow().isoformat(),
            'expires_at': (datetime.utcnow() + timedelta(seconds=ttl)).isoformat()
        }

        # Store in Redis (primary)
        await redis_cache.set_json(redis_key, cache_data, ttl)

        # Also store in memory (backup/fast access)
        async with cls._get_lock():
            cls._cache[cache_key] = {
                'hash': content_hash,
                'result': result,
                'created_at': datetime.utcnow(),
                'expires_at': datetime.utcnow() + timedelta(seconds=ttl)
            }

        logger.info(f"Cached: {cache_key} (TTL: {ttl}s)")

    @classmethod
    async def invalidate_chat_cache(cls, chat_id: int):
        """Invalidate all cache entries for a chat."""
        # Invalidate in Redis
        await redis_cache.delete_pattern(f"analysis:*chat:{chat_id}*")

        # Invalidate in memory
        async with cls._get_lock():
            keys_to_delete = [k for k in cls._cache.keys() if f"chat:{chat_id}" in k]
            for key in keys_to_delete:
                del cls._cache[key]
                logger.info(f"Invalidated: {key}")

    @classmethod
    async def invalidate_entity_cache(cls, entity_id: int):
        """Invalidate all cache entries for an entity."""
        # Invalidate in Redis
        await redis_cache.delete_pattern(f"analysis:*entity:{entity_id}*")

        # Invalidate in memory
        async with cls._get_lock():
            keys_to_delete = [k for k in cls._cache.keys() if f"entity:{entity_id}" in k]
            for key in keys_to_delete:
                del cls._cache[key]
                logger.info(f"Invalidated: {key}")

    @classmethod
    async def clear_all(cls):
        """Clear entire cache (both Redis and in-memory)."""
        # Clear Redis analysis keys
        await redis_cache.delete_pattern("analysis:*")

        # Clear in-memory
        async with cls._get_lock():
            count = len(cls._cache)
            cls._cache.clear()
        logger.info(f"Cleared {count} in-memory cache entries")

    @classmethod
    def clear_all_sync(cls):
        """Clear entire cache (sync version for testing setup)."""
        count = len(cls._cache)
        cls._cache.clear()
        logger.info(f"Cleared {count} cache entries (sync)")


def smart_truncate(content: str, max_length: int = 500) -> str:
    """
    Smart truncate that preserves beginning and end of content.

    Unlike simple truncation, this keeps:
    - First 60% of max_length (important context)
    - Last 30% of max_length (recent info)
    - Marker showing how much was skipped
    """
    if not content or len(content) <= max_length:
        return content or ""

    # Calculate split points
    start_len = int(max_length * 0.6)
    end_len = int(max_length * 0.3)

    start = content[:start_len].strip()
    end = content[-end_len:].strip()

    skipped = len(content) - start_len - end_len

    return f"{start}\n... [пропущено {skipped} символов] ...\n{end}"


def format_messages_optimized(
    messages: list,
    max_per_message: int = 500,
    participants: Optional[Dict[int, Dict]] = None
) -> str:
    """
    Format messages with optimized token usage.

    Optimizations:
    - Smart truncate long messages
    - Skip media without text content
    - Compact timestamp format
    - Show participant roles if provided

    Args:
        messages: List of Message objects
        max_per_message: Max chars per message content
        participants: Optional dict from identify_participants() to show roles

    Returns:
        Formatted messages string
    """
    lines = []

    for msg in messages:
        # Skip media-only messages (they don't add value to text analysis)
        if msg.content_type in ('photo', 'video', 'sticker') and not msg.content:
            continue

        # Build name with role icon if participants provided
        if participants and msg.telegram_user_id in participants:
            from .participants import get_role_icon
            participant = participants[msg.telegram_user_id]
            icon = get_role_icon(participant["role"])
            name = f"{icon} {participant['name']}"
        else:
            # Build name without role
            name = f"{msg.first_name or ''} {msg.last_name or ''}".strip() or msg.username or "?"

        # Compact timestamp (just time if today, date+time otherwise)
        ts = msg.timestamp.strftime("%d.%m %H:%M") if msg.timestamp else ""

        # Content with type prefix
        content = msg.content or ""

        if msg.content_type == "voice":
            prefix = "[🎤] "
        elif msg.content_type == "video_note":
            prefix = "[📹] "
        elif msg.content_type == "document":
            prefix = f"[📄 {msg.file_name or 'файл'}] "
        else:
            prefix = ""

        # Smart truncate content
        content = smart_truncate(content, max_per_message)

        lines.append(f"[{ts}] {name}: {prefix}{content}")

    return "\n".join(lines)


# Singleton instance
cache_service = AnalysisCacheService()


class ScoringCacheService:
    """
    In-memory cache for AI compatibility scores.

    Used when VacancyApplication doesn't exist to avoid re-calculating scores.
    Scores are cached with TTL and invalidated when entity or vacancy changes.
    """

    # In-memory cache storage
    _cache: Dict[str, Dict[str, Any]] = {}

    # Lock for thread-safe operations
    _lock: asyncio.Lock = None

    @classmethod
    @property
    def DEFAULT_TTL_SECONDS(cls) -> int:
        """Default TTL for scoring cache (configurable via CACHE_TTL_SCORING env var)."""
        return settings.cache_ttl_scoring

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        """Get or create the asyncio lock (lazy initialization)."""
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock

    @staticmethod
    def make_score_key(entity_id: int, vacancy_id: int) -> str:
        """Generate cache key for entity-vacancy score pair."""
        return f"score:{entity_id}:{vacancy_id}"

    @classmethod
    async def get_cached_score(
        cls,
        entity_id: int,
        vacancy_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached compatibility score if exists and not expired.

        Args:
            entity_id: Candidate entity ID
            vacancy_id: Vacancy ID

        Returns:
            Cached score dict or None if not found/expired

        Uses Redis if available, falls back to in-memory cache.
        """
        cache_key = cls.make_score_key(entity_id, vacancy_id)

        # Try Redis first
        cache_entry = await redis_cache.get_json(cache_key)

        # Fall back to in-memory
        if not cache_entry:
            async with cls._get_lock():
                cache_entry = cls._cache.get(cache_key)

        if not cache_entry:
            logger.debug(f"Score cache miss: {cache_key} (no entry)")
            return None

        # Check expiry (only for in-memory, Redis handles TTL)
        expires_at = cache_entry.get('expires_at')
        if expires_at and isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if expires_at and datetime.utcnow() > expires_at:
            logger.info(f"Score cache expired: {cache_key}")
            await redis_cache.delete(cache_key)
            async with cls._get_lock():
                cls._cache.pop(cache_key, None)
            return None

        logger.info(f"Score cache hit: {cache_key}")
        return cache_entry.get('score')

    @classmethod
    async def set_cached_score(
        cls,
        entity_id: int,
        vacancy_id: int,
        score: Dict[str, Any],
        ttl_seconds: int = None
    ) -> None:
        """
        Cache compatibility score with TTL.

        Stores in both Redis (if available) and in-memory cache.

        Args:
            entity_id: Candidate entity ID
            vacancy_id: Vacancy ID
            score: Score dict to cache
            ttl_seconds: Optional TTL override (default 1 hour)
        """
        cache_key = cls.make_score_key(entity_id, vacancy_id)
        ttl = ttl_seconds or cls.DEFAULT_TTL_SECONDS

        cache_data = {
            'score': score,
            'entity_id': entity_id,
            'vacancy_id': vacancy_id,
            'created_at': datetime.utcnow().isoformat(),
            'expires_at': (datetime.utcnow() + timedelta(seconds=ttl)).isoformat()
        }

        # Store in Redis (primary)
        await redis_cache.set_json(cache_key, cache_data, ttl)

        # Also store in memory (backup)
        async with cls._get_lock():
            cls._cache[cache_key] = {
                'score': score,
                'entity_id': entity_id,
                'vacancy_id': vacancy_id,
                'created_at': datetime.utcnow(),
                'expires_at': datetime.utcnow() + timedelta(seconds=ttl)
            }

        logger.info(f"Score cached: {cache_key} (TTL: {ttl}s)")

    @classmethod
    async def invalidate_entity_scores(cls, entity_id: int) -> int:
        """
        Invalidate all cached scores for an entity.

        Called when entity data changes (skills, experience, salary, etc.).

        Args:
            entity_id: Entity ID to invalidate

        Returns:
            Number of cache entries invalidated
        """
        prefix = f"score:{entity_id}:"
        count = 0

        # Invalidate in Redis
        redis_count = await redis_cache.delete_pattern(f"{prefix}*")
        count += redis_count

        # Invalidate in memory
        async with cls._get_lock():
            keys_to_delete = [
                k for k in cls._cache.keys()
                if k.startswith(prefix)
            ]
            for key in keys_to_delete:
                del cls._cache[key]
                count += 1
                logger.info(f"Score cache invalidated: {key}")

        if count > 0:
            logger.info(f"Invalidated {count} score cache entries for entity {entity_id}")
        return count

    @classmethod
    async def invalidate_vacancy_scores(cls, vacancy_id: int) -> int:
        """
        Invalidate all cached scores for a vacancy.

        Called when vacancy data changes (requirements, salary, etc.).

        Args:
            vacancy_id: Vacancy ID to invalidate

        Returns:
            Number of cache entries invalidated
        """
        suffix = f":{vacancy_id}"
        count = 0

        # Invalidate in Redis
        redis_count = await redis_cache.delete_pattern(f"score:*:{vacancy_id}")
        count += redis_count

        # Invalidate in memory
        async with cls._get_lock():
            keys_to_delete = [
                k for k in cls._cache.keys()
                if k.startswith("score:") and k.endswith(suffix)
            ]
            for key in keys_to_delete:
                del cls._cache[key]
                count += 1
                logger.info(f"Score cache invalidated: {key}")

        if count > 0:
            logger.info(f"Invalidated {count} score cache entries for vacancy {vacancy_id}")
        return count

    @classmethod
    async def invalidate_score(cls, entity_id: int, vacancy_id: int) -> bool:
        """
        Invalidate a specific entity-vacancy score.

        Args:
            entity_id: Entity ID
            vacancy_id: Vacancy ID

        Returns:
            True if entry was invalidated, False if not found
        """
        cache_key = cls.make_score_key(entity_id, vacancy_id)

        # Invalidate in Redis
        await redis_cache.delete(cache_key)

        # Invalidate in memory
        async with cls._get_lock():
            if cache_key in cls._cache:
                del cls._cache[cache_key]
                logger.info(f"Score cache invalidated: {cache_key}")
                return True
            return False

    @classmethod
    async def clear_all(cls) -> int:
        """Clear entire scoring cache (both Redis and in-memory)."""
        # Clear Redis scoring keys
        redis_count = await redis_cache.delete_pattern("score:*")

        # Clear in-memory
        async with cls._get_lock():
            memory_count = len(cls._cache)
            cls._cache.clear()

        total = redis_count + memory_count
        logger.info(f"Cleared {total} score cache entries (Redis: {redis_count}, memory: {memory_count})")
        return total

    @classmethod
    def clear_all_sync(cls) -> int:
        """Clear entire cache (sync version for testing setup)."""
        count = len(cls._cache)
        cls._cache.clear()
        logger.info(f"Cleared {count} score cache entries (sync)")
        return count

    @classmethod
    def get_cache_stats(cls) -> Dict[str, Any]:
        """Get cache statistics for monitoring."""
        return {
            "total_entries": len(cls._cache),
            "keys": list(cls._cache.keys())
        }


# Singleton instance for scoring cache
scoring_cache = ScoringCacheService()
