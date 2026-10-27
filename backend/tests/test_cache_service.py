"""
Tests for AI Cache Service - token optimization utilities.

Tests:
- smart_truncate function
- format_messages_optimized function
- AnalysisCacheService hash computation
- Cache storage and retrieval
- Cache invalidation
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import sys
sys.path.insert(0, '/home/user/HR-bot-/backend')

from api.services.cache import (
    smart_truncate,
    format_messages_optimized,
    AnalysisCacheService,
    cache_service
)

pytestmark = pytest.mark.asyncio


class TestSmartTruncate:
    """Tests for smart_truncate function."""

    def test_short_content_unchanged(self):
        """Short content should not be truncated."""
        content = "Short message"
        result = smart_truncate(content, max_length=500)
        assert result == content

    def test_exact_length_unchanged(self):
        """Content at exact max length should not be truncated."""
        content = "x" * 500
        result = smart_truncate(content, max_length=500)
        assert result == content

    def test_long_content_truncated(self):
        """Long content should be truncated with marker."""
        content = "A" * 300 + "B" * 400 + "C" * 300  # 1000 chars
        result = smart_truncate(content, max_length=500)

        # Should contain start
        assert result.startswith("A" * 50)
        # Should contain end
        assert result.endswith("C" * 50)
        # Should contain skip marker
        assert "пропущено" in result

    def test_preserves_start_and_end(self):
        """Should preserve beginning and end of content."""
        start = "START_IMPORTANT_"
        middle = "x" * 1000
        end = "_END_IMPORTANT"
        content = start + middle + end

        result = smart_truncate(content, max_length=200)

        # Start should be partially preserved
        assert "START" in result
        # End should be partially preserved
        assert "END" in result

    def test_empty_content(self):
        """Empty content should return empty string."""
        assert smart_truncate("", 500) == ""
        assert smart_truncate(None, 500) == ""

    def test_skip_count_accurate(self):
        """Skip count in marker should be accurate."""
        content = "A" * 1000
        result = smart_truncate(content, max_length=500)

        # Extract skipped count from marker
        import re
        match = re.search(r'пропущено (\d+) символов', result)
        assert match is not None

        skipped = int(match.group(1))
        # Total - start (60%) - end (30%) = skipped
        expected_start = int(500 * 0.6)
        expected_end = int(500 * 0.3)
        expected_skipped = 1000 - expected_start - expected_end
        assert skipped == expected_skipped


class TestFormatMessagesOptimized:
    """Tests for format_messages_optimized function."""

    def test_formats_text_messages(self):
        """Should format text messages correctly."""
        msg = MagicMock()
        msg.content = "Hello world"
        msg.content_type = "text"
        msg.first_name = "John"
        msg.last_name = "Doe"
        msg.username = "johnd"
        msg.timestamp = datetime(2024, 1, 15, 10, 30)
        msg.file_name = None

        result = format_messages_optimized([msg])

        assert "John Doe" in result
        assert "Hello world" in result
        assert "15.01 10:30" in result

    def test_skips_media_without_content(self):
        """Should skip photo/video/sticker without text."""
        photo_msg = MagicMock()
        photo_msg.content = ""
        photo_msg.content_type = "photo"
        photo_msg.first_name = "User"
        photo_msg.last_name = ""
        photo_msg.username = None
        photo_msg.timestamp = datetime.now()

        text_msg = MagicMock()
        text_msg.content = "Text message"
        text_msg.content_type = "text"
        text_msg.first_name = "User"
        text_msg.last_name = ""
        text_msg.username = None
        text_msg.timestamp = datetime.now()
        text_msg.file_name = None

        result = format_messages_optimized([photo_msg, text_msg])

        assert "Text message" in result
        # Photo without content should be skipped

    def test_voice_message_prefix(self):
        """Voice messages should have audio prefix."""
        msg = MagicMock()
        msg.content = "Transcribed voice content"
        msg.content_type = "voice"
        msg.first_name = "User"
        msg.last_name = ""
        msg.username = None
        msg.timestamp = datetime.now()
        msg.file_name = None

        result = format_messages_optimized([msg])

        assert "[🎤]" in result
        assert "Transcribed voice content" in result

    def test_document_message_prefix(self):
        """Document messages should have file prefix with name."""
        msg = MagicMock()
        msg.content = "Document content"
        msg.content_type = "document"
        msg.first_name = "User"
        msg.last_name = ""
        msg.username = None
        msg.timestamp = datetime.now()
        msg.file_name = "report.pdf"

        result = format_messages_optimized([msg])

        assert "[📄 report.pdf]" in result

    def test_truncates_long_messages(self):
        """Long messages should be truncated."""
        msg = MagicMock()
        msg.content = "A" * 1000
        msg.content_type = "text"
        msg.first_name = "User"
        msg.last_name = ""
        msg.username = None
        msg.timestamp = datetime.now()
        msg.file_name = None

        result = format_messages_optimized([msg], max_per_message=200)

        # Should be truncated
        assert len(result) < 1000
        assert "пропущено" in result


class TestAnalysisCacheService:
    """Tests for AnalysisCacheService."""

    def setup_method(self):
        """Clear cache before each test."""
        cache_service.clear_all_sync()

    async def test_compute_messages_hash_consistent(self):
        """Same messages should produce same hash."""
        msg1 = MagicMock()
        msg1.id = 1
        msg1.content = "Hello"
        msg1.timestamp = datetime(2024, 1, 1, 10, 0)

        hash1 = cache_service.compute_messages_hash([msg1])
        hash2 = cache_service.compute_messages_hash([msg1])

        assert hash1 == hash2

    def test_compute_messages_hash_changes_on_content(self):
        """Different content should produce different hash."""
        msg1 = MagicMock()
        msg1.id = 1
        msg1.content = "Hello"
        msg1.timestamp = datetime(2024, 1, 1, 10, 0)

        msg2 = MagicMock()
        msg2.id = 1
        msg2.content = "Goodbye"
        msg2.timestamp = datetime(2024, 1, 1, 10, 0)

        hash1 = cache_service.compute_messages_hash([msg1])
        hash2 = cache_service.compute_messages_hash([msg2])

        assert hash1 != hash2

    def test_compute_messages_hash_changes_on_new_message(self):
        """Adding a message should change hash."""
        msg1 = MagicMock()
        msg1.id = 1
        msg1.content = "Hello"
        msg1.timestamp = datetime(2024, 1, 1, 10, 0)

        msg2 = MagicMock()
        msg2.id = 2
        msg2.content = "World"
        msg2.timestamp = datetime(2024, 1, 1, 10, 1)

        hash1 = cache_service.compute_messages_hash([msg1])
        hash2 = cache_service.compute_messages_hash([msg1, msg2])

        assert hash1 != hash2

    def test_compute_messages_hash_includes_criteria(self):
        """Different criteria should produce different hash."""
        msg = MagicMock()
        msg.id = 1
        msg.content = "Hello"
        msg.timestamp = datetime(2024, 1, 1, 10, 0)

        criteria1 = [{"name": "Skills", "weight": 8}]
        criteria2 = [{"name": "Skills", "weight": 10}]

        hash1 = cache_service.compute_messages_hash([msg], criteria1)
        hash2 = cache_service.compute_messages_hash([msg], criteria2)

        assert hash1 != hash2

    async def test_cache_set_and_get(self):
        """Should store and retrieve cached results."""
        cache_key = "test:chat:1"
        content_hash = "abc123"
        result = "Analysis result text"

        await cache_service.set_cached_analysis(cache_key, content_hash, result)
        cached = await cache_service.get_cached_analysis(cache_key, content_hash)

        assert cached == result

    async def test_cache_miss_no_entry(self):
        """Should return None for non-existent cache."""
        cached = await cache_service.get_cached_analysis("nonexistent", "hash")
        assert cached is None

    async def test_cache_miss_wrong_hash(self):
        """Should return None when hash doesn't match."""
        cache_key = "test:chat:1"
        await cache_service.set_cached_analysis(cache_key, "hash1", "result")

        # Try to get with different hash
        cached = await cache_service.get_cached_analysis(cache_key, "hash2")
        assert cached is None

    async def test_cache_expiry(self):
        """Should return None for expired cache."""
        import asyncio
        cache_key = "test:chat:1"
        content_hash = "abc123"

        # Set with very short TTL
        await cache_service.set_cached_analysis(
            cache_key, content_hash, "result", ttl_seconds=0
        )

        # Wait a small amount to ensure expiration
        await asyncio.sleep(0.01)

        # Should be expired
        cached = await cache_service.get_cached_analysis(cache_key, content_hash)
        assert cached is None

    async def test_invalidate_chat_cache(self):
        """Should invalidate all cache for a chat."""
        # Set multiple cache entries for same chat
        await cache_service.set_cached_analysis("chat:1:report:quick", "h1", "r1")
        await cache_service.set_cached_analysis("chat:1:report:full", "h2", "r2")
        await cache_service.set_cached_analysis("chat:2:report:quick", "h3", "r3")

        # Invalidate chat 1
        await cache_service.invalidate_chat_cache(1)

        # Chat 1 entries should be gone
        assert await cache_service.get_cached_analysis("chat:1:report:quick", "h1") is None
        assert await cache_service.get_cached_analysis("chat:1:report:full", "h2") is None

        # Chat 2 should still exist
        assert await cache_service.get_cached_analysis("chat:2:report:quick", "h3") == "r3"

    async def test_invalidate_entity_cache(self):
        """Should invalidate all cache for an entity."""
        await cache_service.set_cached_analysis("entity:1:analysis", "h1", "r1")
        await cache_service.set_cached_analysis("entity:2:analysis", "h2", "r2")

        await cache_service.invalidate_entity_cache(1)

        assert await cache_service.get_cached_analysis("entity:1:analysis", "h1") is None
        assert await cache_service.get_cached_analysis("entity:2:analysis", "h2") == "r2"

    async def test_clear_all(self):
        """Should clear entire cache."""
        await cache_service.set_cached_analysis("key1", "h1", "r1")
        await cache_service.set_cached_analysis("key2", "h2", "r2")

        await cache_service.clear_all()

        assert await cache_service.get_cached_analysis("key1", "h1") is None
        assert await cache_service.get_cached_analysis("key2", "h2") is None


class TestEntityHashComputation:
    """Tests for entity context hash computation."""

    def setup_method(self):
        """Clear cache before each test."""
        cache_service.clear_all_sync()

    def test_entity_hash_includes_entity_info(self):
        """Entity info changes should change hash."""
        entity1 = MagicMock()
        entity1.id = 1
        entity1.name = "John"
        entity1.status = MagicMock(value="new")
        entity1.type = MagicMock(value="candidate")

        entity2 = MagicMock()
        entity2.id = 1
        entity2.name = "John Updated"
        entity2.status = MagicMock(value="new")
        entity2.type = MagicMock(value="candidate")

        hash1 = cache_service.compute_entity_hash(entity1, [], [])
        hash2 = cache_service.compute_entity_hash(entity2, [], [])

        assert hash1 != hash2

    def test_entity_hash_includes_chats(self):
        """Chat message count changes should change hash."""
        entity = MagicMock()
        entity.id = 1
        entity.name = "John"
        entity.status = MagicMock(value="new")
        entity.type = MagicMock(value="candidate")

        chat1 = MagicMock()
        chat1.id = 1
        chat1.messages = []

        chat2 = MagicMock()
        chat2.id = 1
        msg = MagicMock()
        msg.timestamp = datetime.now()
        chat2.messages = [msg]

        hash1 = cache_service.compute_entity_hash(entity, [chat1], [])
        hash2 = cache_service.compute_entity_hash(entity, [chat2], [])

        assert hash1 != hash2

    def test_entity_hash_includes_calls(self):
        """Call changes should change hash."""
        entity = MagicMock()
        entity.id = 1
        entity.name = "John"
        entity.status = MagicMock(value="new")
        entity.type = MagicMock(value="candidate")

        call1 = MagicMock()
        call1.id = 1
        call1.status = MagicMock(value="done")
        call1.transcript = "Short"

        call2 = MagicMock()
        call2.id = 1
        call2.status = MagicMock(value="done")
        call2.transcript = "Much longer transcript content"

        hash1 = cache_service.compute_entity_hash(entity, [], [call1])
        hash2 = cache_service.compute_entity_hash(entity, [], [call2])

        assert hash1 != hash2
