"""
Comprehensive tests for Cache Service to reach 90% coverage.

Tests:
- format_messages_optimized with participant roles
- Cache TTL and expiration edge cases
- Concurrent cache operations
- Hash computation edge cases
- Smart truncate edge cases
"""
import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from api.services.cache import (
    smart_truncate,
    format_messages_optimized,
    AnalysisCacheService,
    cache_service
)

pytestmark = pytest.mark.asyncio


class TestSmartTruncateEdgeCases:
    """Additional edge cases for smart_truncate."""

    def test_smart_truncate_very_short_limit(self):
        """Test truncation with very short max_length."""
        content = "Hello World This Is A Test"

        result = smart_truncate(content, max_length=10)

        # Should have start, marker, and end
        assert "пропущено" in result

    def test_smart_truncate_preserves_percentages(self):
        """Test that truncation preserves correct percentages."""
        content = "A" * 1000
        result = smart_truncate(content, max_length=500)

        # Start should be ~60% = 300 chars
        # End should be ~30% = 150 chars
        # Total visible should be ~450 chars + marker

        # Count A's in result (excluding marker text)
        a_count = result.count("A")

        # Should be approximately 300 + 150 = 450
        assert 400 <= a_count <= 500

    def test_smart_truncate_unicode_content(self):
        """Test smart truncate with Unicode characters."""
        content = "Привет мир! " * 100  # Russian text

        result = smart_truncate(content, max_length=100)

        # Should handle Unicode correctly
        assert "Привет" in result
        assert "пропущено" in result

    def test_smart_truncate_newlines_preserved(self):
        """Test that newlines in content are handled."""
        content = "Line 1\nLine 2\n" * 100

        result = smart_truncate(content, max_length=200)

        # Should preserve newlines
        assert "\n" in result


class TestFormatMessagesOptimizedWithParticipants:
    """Tests for format_messages_optimized with participant roles."""

    def test_format_with_participant_roles(self):
        """Test message formatting includes participant roles."""
        msg = MagicMock()
        msg.telegram_user_id = 123
        msg.username = "testuser"
        msg.first_name = "Test"
        msg.last_name = "User"
        msg.content = "Hello"
        msg.content_type = "text"
        msg.timestamp = datetime(2025, 1, 1, 10, 0)
        msg.file_name = None

        # Participant info with role
        participants = {
            123: {
                "name": "Test User",
                "role": "candidate",  # Role should add icon
                "source": "entity"
            }
        }

        result = format_messages_optimized([msg], participants=participants)

        # Should include participant name and role icon
        assert "Test User" in result
        assert "Hello" in result

    def test_format_without_participant_match(self):
        """Test formatting when user not in participants dict."""
        msg = MagicMock()
        msg.telegram_user_id = 999  # Not in participants
        msg.username = "unknown"
        msg.first_name = "Unknown"
        msg.last_name = "Person"
        msg.content = "Message"
        msg.content_type = "text"
        msg.timestamp = datetime(2025, 1, 1)
        msg.file_name = None

        participants = {
            123: {"name": "Other User", "role": "system_user", "source": "user"}
        }

        result = format_messages_optimized([msg], participants=participants)

        # Should fall back to message fields
        assert "Unknown Person" in result or "unknown" in result
        assert "Message" in result

    def test_format_with_different_roles(self):
        """Test formatting with different participant roles."""
        messages = []

        # Create messages from different roles
        for i, role in enumerate(["candidate", "system_user", "unknown"]):
            msg = MagicMock()
            msg.telegram_user_id = 100 + i
            msg.username = f"user{i}"
            msg.first_name = f"User{i}"
            msg.last_name = ""
            msg.content = f"Message {i}"
            msg.content_type = "text"
            msg.timestamp = datetime(2025, 1, 1, 10, i)
            msg.file_name = None
            messages.append(msg)

        participants = {
            100: {"name": "User0", "role": "candidate", "source": "entity"},
            101: {"name": "User1", "role": "system_user", "source": "user"},
            102: {"name": "User2", "role": "unknown", "source": "unknown"},
        }

        result = format_messages_optimized(messages, participants=participants)

        # All messages should be formatted
        assert "Message 0" in result
        assert "Message 1" in result
        assert "Message 2" in result

    def test_format_participants_none(self):
        """Test formatting with participants=None."""
        msg = MagicMock()
        msg.telegram_user_id = 123
        msg.username = "test"
        msg.first_name = "Test"
        msg.last_name = "User"
        msg.content = "Hello"
        msg.content_type = "text"
        msg.timestamp = datetime(2025, 1, 1)
        msg.file_name = None

        result = format_messages_optimized([msg], participants=None)

        # Should work without participants
        assert "Test User" in result or "test" in result
        assert "Hello" in result


class TestCacheTTLEdgeCases:
    """Tests for cache TTL and expiration edge cases."""

    def setup_method(self):
        """Clear cache before each test."""
        cache_service.clear_all_sync()

    async def test_cache_with_custom_ttl(self):
        """Test setting cache with custom TTL."""
        await cache_service.set_cached_analysis(
            "test:key",
            "hash123",
            "result",
            ttl_seconds=3600
        )

        cached = await cache_service.get_cached_analysis("test:key", "hash123")
        assert cached == "result"

    async def test_cache_with_zero_ttl_expires_immediately(self):
        """Test that zero TTL expires immediately."""
        await cache_service.set_cached_analysis(
            "test:key",
            "hash123",
            "result",
            ttl_seconds=0
        )

        # Wait a small amount to ensure expiration
        await asyncio.sleep(0.01)

        # Should be expired
        cached = await cache_service.get_cached_analysis("test:key", "hash123")
        assert cached is None

    async def test_cache_default_ttl(self):
        """Test that default TTL is used when not specified."""
        await cache_service.set_cached_analysis("test:key", "hash123", "result")

        # Should use DEFAULT_TTL_SECONDS
        entry = cache_service._cache.get("test:key")
        assert entry is not None
        assert "expires_at" in entry

        # Expiration should be in the future
        assert entry["expires_at"] > datetime.utcnow()

    async def test_cache_entry_structure(self):
        """Test that cache entry has correct structure."""
        await cache_service.set_cached_analysis(
            "test:key",
            "hash123",
            "result",
            ttl_seconds=3600
        )

        entry = cache_service._cache.get("test:key")

        assert "hash" in entry
        assert "result" in entry
        assert "created_at" in entry
        assert "expires_at" in entry

        assert entry["hash"] == "hash123"
        assert entry["result"] == "result"


class TestCacheConcurrency:
    """Tests for concurrent cache operations."""

    def setup_method(self):
        """Clear cache before each test."""
        cache_service.clear_all_sync()

    async def test_multiple_writes_last_wins(self):
        """Test that last write wins for same key."""
        await cache_service.set_cached_analysis("key", "hash1", "result1")
        await cache_service.set_cached_analysis("key", "hash2", "result2")

        # Should have hash2
        cached = await cache_service.get_cached_analysis("key", "hash2")
        assert cached == "result2"

        # hash1 should not match
        cached = await cache_service.get_cached_analysis("key", "hash1")
        assert cached is None

    async def test_different_keys_independent(self):
        """Test that different cache keys are independent."""
        await cache_service.set_cached_analysis("key1", "hash1", "result1")
        await cache_service.set_cached_analysis("key2", "hash2", "result2")

        assert await cache_service.get_cached_analysis("key1", "hash1") == "result1"
        assert await cache_service.get_cached_analysis("key2", "hash2") == "result2"

    async def test_invalidate_does_not_affect_others(self):
        """Test that invalidating one key doesn't affect others."""
        await cache_service.set_cached_analysis("chat:1:report", "h1", "r1")
        await cache_service.set_cached_analysis("chat:2:report", "h2", "r2")
        await cache_service.set_cached_analysis("entity:1:analysis", "h3", "r3")

        await cache_service.invalidate_chat_cache(1)

        # Chat 1 gone
        assert await cache_service.get_cached_analysis("chat:1:report", "h1") is None

        # Others still there
        assert await cache_service.get_cached_analysis("chat:2:report", "h2") == "r2"
        assert await cache_service.get_cached_analysis("entity:1:analysis", "h3") == "r3"


class TestHashComputationEdgeCases:
    """Tests for hash computation edge cases."""

    def test_compute_messages_hash_with_empty_content(self):
        """Test hash computation with empty message content."""
        msg = MagicMock()
        msg.id = 1
        msg.content = ""  # Empty
        msg.timestamp = datetime(2025, 1, 1)

        hash_result = cache_service.compute_messages_hash([msg])
        assert hash_result is not None
        assert len(hash_result) == 32  # MD5 hex digest length

    def test_compute_messages_hash_with_none_timestamp(self):
        """Test hash computation with None timestamp."""
        msg = MagicMock()
        msg.id = 1
        msg.content = "Test"
        msg.timestamp = None

        hash_result = cache_service.compute_messages_hash([msg])
        assert hash_result is not None

    def test_compute_messages_hash_dict_messages(self):
        """Test hash computation with dict messages instead of objects."""
        messages = [
            {"content": "Hello", "role": "user"},
            {"content": "Hi", "role": "assistant"}
        ]

        hash_result = cache_service.compute_messages_hash(messages)
        assert hash_result is not None

    def test_compute_messages_hash_consistent_with_dict(self):
        """Test that same dict messages produce same hash."""
        messages = [{"content": "Test", "role": "user"}]

        hash1 = cache_service.compute_messages_hash(messages)
        hash2 = cache_service.compute_messages_hash(messages)

        assert hash1 == hash2

    def test_compute_messages_hash_empty_criteria(self):
        """Test hash with empty criteria list."""
        msg = MagicMock()
        msg.id = 1
        msg.content = "Test"
        msg.timestamp = datetime(2025, 1, 1)

        hash_result = cache_service.compute_messages_hash([msg], criteria=[])
        assert hash_result is not None

    def test_compute_messages_hash_none_criteria(self):
        """Test hash with None criteria."""
        msg = MagicMock()
        msg.id = 1
        msg.content = "Test"
        msg.timestamp = datetime(2025, 1, 1)

        hash_result = cache_service.compute_messages_hash([msg], criteria=None)
        assert hash_result is not None

    def test_compute_entity_hash_with_no_messages_in_chat(self):
        """Test entity hash when chat has no messages."""
        entity = MagicMock()
        entity.id = 1
        entity.name = "Test"
        entity.status = MagicMock(value="active")
        entity.type = MagicMock(value="candidate")

        chat = MagicMock()
        chat.id = 1
        chat.messages = None  # No messages attribute

        # Should handle gracefully
        hash_result = cache_service.compute_entity_hash(entity, [chat], [])
        assert hash_result is not None

    def test_compute_entity_hash_with_none_status(self):
        """Test entity hash when entity has None status/type."""
        entity = MagicMock()
        entity.id = 1
        entity.name = "Test"
        entity.status = None
        entity.type = None

        hash_result = cache_service.compute_entity_hash(entity, [], [])
        assert hash_result is not None

    def test_compute_entity_hash_with_none_call_fields(self):
        """Test entity hash when call has None fields."""
        entity = MagicMock()
        entity.id = 1
        entity.name = "Test"
        entity.status = MagicMock(value="active")
        entity.type = MagicMock(value="candidate")

        call = MagicMock()
        call.id = 1
        call.status = None
        call.transcript = None

        hash_result = cache_service.compute_entity_hash(entity, [], [call])
        assert hash_result is not None


class TestInvalidation:
    """Tests for cache invalidation methods."""

    def setup_method(self):
        """Clear cache before each test."""
        cache_service.clear_all_sync()

    async def test_invalidate_chat_cache_no_matches(self):
        """Test invalidating chat when no entries exist."""
        await cache_service.set_cached_analysis("entity:1:report", "h1", "r1")

        # Should not raise error
        await cache_service.invalidate_chat_cache(999)

        # Entity cache should still exist
        assert await cache_service.get_cached_analysis("entity:1:report", "h1") == "r1"

    async def test_invalidate_entity_cache_no_matches(self):
        """Test invalidating entity when no entries exist."""
        await cache_service.set_cached_analysis("chat:1:report", "h1", "r1")

        # Should not raise error
        await cache_service.invalidate_entity_cache(999)

        # Chat cache should still exist
        assert await cache_service.get_cached_analysis("chat:1:report", "h1") == "r1"

    async def test_invalidate_partial_key_match(self):
        """Test that invalidation uses substring matching correctly."""
        await cache_service.set_cached_analysis("chat:10:report", "h1", "r1")
        await cache_service.set_cached_analysis("chat:1:report", "h2", "r2")
        await cache_service.set_cached_analysis("chat:100:report", "h3", "r3")

        # Invalidate chat 1 - should only affect exact chat:1
        await cache_service.invalidate_chat_cache(1)

        # Chat 10 and 100 should still exist
        assert await cache_service.get_cached_analysis("chat:10:report", "h1") == "r1"
        assert await cache_service.get_cached_analysis("chat:100:report", "h3") == "r3"

        # Chat 1 should be gone
        assert await cache_service.get_cached_analysis("chat:1:report", "h2") is None

    async def test_clear_all_removes_everything(self):
        """Test that clear_all removes all cache entries."""
        # Add various types
        await cache_service.set_cached_analysis("chat:1:report", "h1", "r1")
        await cache_service.set_cached_analysis("entity:1:analysis", "h2", "r2")
        await cache_service.set_cached_analysis("custom:key", "h3", "r3")

        await cache_service.clear_all()

        # All should be gone
        assert await cache_service.get_cached_analysis("chat:1:report", "h1") is None
        assert await cache_service.get_cached_analysis("entity:1:analysis", "h2") is None
        assert await cache_service.get_cached_analysis("custom:key", "h3") is None

    async def test_clear_all_returns_count(self):
        """Test that clear_all returns count (implicitly via logging)."""
        await cache_service.set_cached_analysis("key1", "h1", "r1")
        await cache_service.set_cached_analysis("key2", "h2", "r2")

        # Clear should work without error
        await cache_service.clear_all()

        # Cache should be empty
        assert len(cache_service._cache) == 0


class TestDefaultTTL:
    """Tests for default TTL constant."""

    def test_default_ttl_is_positive(self):
        """Test that DEFAULT_TTL_SECONDS is positive."""
        assert AnalysisCacheService.DEFAULT_TTL_SECONDS > 0

    def test_default_ttl_is_reasonable(self):
        """Test that DEFAULT_TTL_SECONDS is reasonable (not too short/long)."""
        # Should be between 1 minute and 24 hours
        assert 60 <= AnalysisCacheService.DEFAULT_TTL_SECONDS <= 86400


class TestFormatMessagesOptimizedContentTypes:
    """Tests for different content types in format_messages_optimized."""

    def test_format_video_note_message(self):
        """Test formatting video note messages."""
        msg = MagicMock()
        msg.telegram_user_id = 123
        msg.username = "test"
        msg.first_name = "Test"
        msg.last_name = ""
        msg.content = "Video content"
        msg.content_type = "video_note"
        msg.timestamp = datetime(2025, 1, 1)
        msg.file_name = None

        result = format_messages_optimized([msg])

        assert "[📹]" in result
        assert "Video content" in result

    def test_format_document_without_filename(self):
        """Test formatting document without filename."""
        msg = MagicMock()
        msg.telegram_user_id = 123
        msg.username = "test"
        msg.first_name = "Test"
        msg.last_name = ""
        msg.content = "Document content"
        msg.content_type = "document"
        msg.timestamp = datetime(2025, 1, 1)
        msg.file_name = None

        result = format_messages_optimized([msg])

        # Should use default file name
        assert "[📄 файл]" in result

    def test_format_mixed_content_types(self):
        """Test formatting mix of different content types."""
        messages = []

        types = [
            ("text", None, "Text message"),
            ("voice", None, "Voice transcription"),
            ("video_note", None, "Video note"),
            ("document", "file.pdf", "Document"),
            ("photo", None, "Photo caption"),
        ]

        for i, (ctype, fname, content) in enumerate(types):
            msg = MagicMock()
            msg.telegram_user_id = 123
            msg.username = "test"
            msg.first_name = "User"
            msg.last_name = ""
            msg.content = content
            msg.content_type = ctype
            msg.timestamp = datetime(2025, 1, 1, 10, i)
            msg.file_name = fname
            messages.append(msg)

        result = format_messages_optimized(messages)

        # All content should be present
        assert "Text message" in result
        assert "Voice transcription" in result
        assert "Video note" in result
        assert "Document" in result
        assert "Photo caption" in result


class TestMessageTimestampFormatting:
    """Tests for timestamp formatting in messages."""

    def test_format_messages_timestamp_format(self):
        """Test that timestamps are formatted as DD.MM HH:MM."""
        msg = MagicMock()
        msg.telegram_user_id = 123
        msg.username = "test"
        msg.first_name = "User"
        msg.last_name = ""
        msg.content = "Test"
        msg.content_type = "text"
        msg.timestamp = datetime(2025, 3, 15, 14, 30, 45)
        msg.file_name = None

        result = format_messages_optimized([msg])

        # Should have date and time
        assert "15.03 14:30" in result

    def test_format_messages_none_timestamp(self):
        """Test formatting with None timestamp."""
        msg = MagicMock()
        msg.telegram_user_id = 123
        msg.username = "test"
        msg.first_name = "User"
        msg.last_name = ""
        msg.content = "Test"
        msg.content_type = "text"
        msg.timestamp = None
        msg.file_name = None

        result = format_messages_optimized([msg])

        # Should still work, just without timestamp
        assert "Test" in result


class TestConcurrentCacheAccess:
    """Tests for thread-safe concurrent cache operations using asyncio.Lock."""

    def setup_method(self):
        """Clear cache before each test."""
        cache_service.clear_all_sync()
        # Reset the lock to ensure fresh state
        AnalysisCacheService._lock = None

    async def test_concurrent_writes_no_data_corruption(self):
        """Test that concurrent writes don't corrupt cache data."""
        num_tasks = 100
        results = []

        async def write_task(i: int):
            key = f"concurrent:key:{i}"
            await cache_service.set_cached_analysis(key, f"hash{i}", f"result{i}")
            results.append(i)

        # Run all writes concurrently
        tasks = [write_task(i) for i in range(num_tasks)]
        await asyncio.gather(*tasks)

        # All writes should have completed
        assert len(results) == num_tasks

        # All values should be correctly stored
        for i in range(num_tasks):
            cached = await cache_service.get_cached_analysis(f"concurrent:key:{i}", f"hash{i}")
            assert cached == f"result{i}", f"Key {i} has wrong value"

    async def test_concurrent_reads_and_writes(self):
        """Test that concurrent reads and writes work correctly."""
        # Pre-populate some data
        for i in range(10):
            await cache_service.set_cached_analysis(f"rw:key:{i}", f"hash{i}", f"result{i}")

        read_results = []
        write_results = []

        async def read_task(i: int):
            result = await cache_service.get_cached_analysis(f"rw:key:{i % 10}", f"hash{i % 10}")
            read_results.append((i, result))

        async def write_task(i: int):
            await cache_service.set_cached_analysis(f"rw:new:{i}", f"newhash{i}", f"newresult{i}")
            write_results.append(i)

        # Mix reads and writes
        tasks = []
        for i in range(50):
            tasks.append(read_task(i))
            tasks.append(write_task(i))

        await asyncio.gather(*tasks)

        # All operations should complete
        assert len(read_results) == 50
        assert len(write_results) == 50

        # All reads should return expected values
        for i, result in read_results:
            expected = f"result{i % 10}"
            assert result == expected, f"Read {i} returned {result}, expected {expected}"

    async def test_concurrent_invalidation_safety(self):
        """Test that concurrent invalidation doesn't cause errors."""
        # Pre-populate cache with multiple entries for same chat
        for i in range(20):
            await cache_service.set_cached_analysis(f"chat:1:report:{i}", f"h{i}", f"r{i}")
            await cache_service.set_cached_analysis(f"chat:2:report:{i}", f"h{i}", f"r{i}")

        invalidation_count = [0]
        write_count = [0]

        async def invalidate_task():
            await cache_service.invalidate_chat_cache(1)
            invalidation_count[0] += 1

        async def write_task(i: int):
            await cache_service.set_cached_analysis(f"chat:3:report:{i}", f"h{i}", f"r{i}")
            write_count[0] += 1

        # Run invalidations and writes concurrently
        tasks = []
        for i in range(10):
            tasks.append(invalidate_task())
            tasks.append(write_task(i))

        await asyncio.gather(*tasks)

        # All operations should complete without errors
        assert invalidation_count[0] == 10
        assert write_count[0] == 10

        # Chat 1 should be invalidated
        for i in range(20):
            assert await cache_service.get_cached_analysis(f"chat:1:report:{i}", f"h{i}") is None

        # Chat 2 and 3 should still have data
        for i in range(20):
            assert await cache_service.get_cached_analysis(f"chat:2:report:{i}", f"h{i}") == f"r{i}"
        for i in range(10):
            assert await cache_service.get_cached_analysis(f"chat:3:report:{i}", f"h{i}") == f"r{i}"

    async def test_concurrent_clear_all_safety(self):
        """Test that concurrent clear_all doesn't cause errors."""
        errors = []

        async def populate_and_clear():
            try:
                for i in range(5):
                    await cache_service.set_cached_analysis(f"clear:key:{i}", f"h{i}", f"r{i}")
                await cache_service.clear_all()
            except Exception as e:
                errors.append(str(e))

        # Run multiple clear_all operations concurrently
        tasks = [populate_and_clear() for _ in range(10)]
        await asyncio.gather(*tasks)

        # No errors should have occurred
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Cache should be empty after all clears
        assert len(cache_service._cache) == 0

    async def test_lock_is_shared_across_operations(self):
        """Test that the lock is properly shared across all cache operations."""
        # This test verifies that operations are serialized by checking
        # that interleaved operations produce consistent results

        operation_order = []

        async def set_and_record(key: str, delay: float):
            operation_order.append(f"start_set_{key}")
            await cache_service.set_cached_analysis(key, "hash", f"value_{key}")
            await asyncio.sleep(delay)
            operation_order.append(f"end_set_{key}")

        async def get_and_record(key: str, delay: float):
            operation_order.append(f"start_get_{key}")
            await asyncio.sleep(delay)
            result = await cache_service.get_cached_analysis(key, "hash")
            operation_order.append(f"end_get_{key}")
            return result

        # Set initial values
        await cache_service.set_cached_analysis("locktest:1", "hash", "value_locktest:1")
        await cache_service.set_cached_analysis("locktest:2", "hash", "value_locktest:2")

        # Run concurrent operations
        results = await asyncio.gather(
            get_and_record("locktest:1", 0.001),
            set_and_record("locktest:3", 0.001),
            get_and_record("locktest:2", 0.001),
        )

        # All get operations should return correct values
        assert results[0] == "value_locktest:1"
        assert results[2] == "value_locktest:2"

        # New key should be set correctly
        assert await cache_service.get_cached_analysis("locktest:3", "hash") == "value_locktest:3"

    async def test_high_contention_scenario(self):
        """Test cache under high contention with many concurrent operations."""
        num_operations = 200
        success_count = [0]
        error_count = [0]

        async def random_operation(i: int):
            try:
                op = i % 4
                if op == 0:
                    await cache_service.set_cached_analysis(f"hc:{i}", f"h{i}", f"r{i}")
                elif op == 1:
                    await cache_service.get_cached_analysis(f"hc:{i // 2}", f"h{i // 2}")
                elif op == 2:
                    await cache_service.invalidate_chat_cache(i % 10)
                else:
                    await cache_service.invalidate_entity_cache(i % 10)
                success_count[0] += 1
            except Exception as e:
                error_count[0] += 1

        tasks = [random_operation(i) for i in range(num_operations)]
        await asyncio.gather(*tasks)

        # All operations should succeed without errors
        assert success_count[0] == num_operations, f"Only {success_count[0]}/{num_operations} succeeded"
        assert error_count[0] == 0, f"{error_count[0]} errors occurred"
