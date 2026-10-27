"""
Comprehensive tests for Entity Memory Service to reach 90% coverage.

Tests:
- update_summary async method
- extract_key_events async method
- AI client integration
- Error handling in AI calls
- JSON parsing edge cases
- Database operations
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import json

from api.services.entity_memory import (
    EntityMemoryService,
    entity_memory_service,
    SUMMARY_UPDATE_INTERVAL,
    MIN_NEW_CONTENT_LENGTH,
    SUMMARY_PROMPT,
    KEY_EVENTS_PROMPT
)


class TestEntityMemoryServiceInit:
    """Tests for EntityMemoryService initialization."""

    def test_init_creates_instance(self):
        """Test that EntityMemoryService initializes correctly."""
        service = EntityMemoryService()

        assert service._client is None
        assert service.model == "claude-sonnet-4-6"

    def test_client_property_lazy_loads(self):
        """Test that client property lazy loads AsyncAnthropic."""
        service = EntityMemoryService()

        with patch('api.services.entity_memory.settings') as mock_settings:
            # Сервис читает settings.anthropic_api_key (строчными).
            mock_settings.anthropic_api_key = "test-key"

            with patch('api.services.entity_memory.anthropic.AsyncAnthropic') as mock_anthropic:
                mock_client = MagicMock()
                mock_anthropic.return_value = mock_client

                client = service.client
                assert client is mock_client

                # Should be cached
                client2 = service.client
                assert client2 is mock_client

                mock_anthropic.assert_called_once_with(api_key="test-key")

    def test_singleton_instance_exists(self):
        """Test that entity_memory_service singleton is available."""
        assert entity_memory_service is not None
        assert isinstance(entity_memory_service, EntityMemoryService)


class TestUpdateSummary:
    """Tests for update_summary async method."""

    @pytest.mark.asyncio
    async def test_update_summary_basic(self):
        """Test basic summary update."""
        service = EntityMemoryService()

        entity = MagicMock()
        entity.id = 1
        entity.ai_summary = None
        entity.key_events = None

        db_session = AsyncMock()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Updated summary of the entity")]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch.object(service, '_client', mock_client):
            result = await service.update_summary(
                entity=entity,
                new_content="New interaction data",
                db_session=db_session
            )

            assert result == "Updated summary of the entity"
            assert entity.ai_summary == "Updated summary of the entity"
            assert entity.ai_summary_updated_at is not None
            db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_summary_with_existing_summary(self):
        """Test updating when entity already has a summary."""
        service = EntityMemoryService()

        entity = MagicMock()
        entity.id = 1
        entity.ai_summary = "Old summary"
        entity.key_events = [
            {"date": "2024-01-15", "event": "hired", "details": "Hired as developer"}
        ]

        db_session = AsyncMock()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Enhanced summary with new info")]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch.object(service, '_client', mock_client):
            result = await service.update_summary(
                entity=entity,
                new_content="New important information",
                db_session=db_session
            )

            # Verify prompt included old summary and key events
            call_kwargs = mock_client.messages.create.call_args[1]
            prompt = call_kwargs['messages'][0]['content']

            assert "Old summary" in prompt
            assert "Hired as developer" in prompt

    @pytest.mark.asyncio
    async def test_update_summary_truncates_long_content(self):
        """Test that very long new content is truncated."""
        service = EntityMemoryService()

        entity = MagicMock()
        entity.id = 1
        entity.ai_summary = None
        entity.key_events = None

        db_session = AsyncMock()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Summary")]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch.object(service, '_client', mock_client):
            long_content = "A" * 10000

            await service.update_summary(
                entity=entity,
                new_content=long_content,
                db_session=db_session
            )

            # Verify content was truncated to 8000 chars
            call_kwargs = mock_client.messages.create.call_args[1]
            prompt = call_kwargs['messages'][0]['content']

            # Prompt should not contain full 10000 chars
            assert len(prompt) < 10000

    @pytest.mark.asyncio
    async def test_update_summary_error_handling(self):
        """Test error handling during summary update."""
        service = EntityMemoryService()

        entity = MagicMock()
        entity.id = 1
        entity.ai_summary = "Existing summary"
        entity.key_events = None

        db_session = AsyncMock()

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("API Error"))

        with patch.object(service, '_client', mock_client):
            result = await service.update_summary(
                entity=entity,
                new_content="New content",
                db_session=db_session
            )

            # Should return existing summary on error
            assert result == "Existing summary"
            # Should not commit
            db_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_summary_no_existing_summary_on_error(self):
        """Test error handling when entity has no existing summary."""
        service = EntityMemoryService()

        entity = MagicMock()
        entity.id = 1
        entity.ai_summary = None
        entity.key_events = None

        db_session = AsyncMock()

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("API Error"))

        with patch.object(service, '_client', mock_client):
            result = await service.update_summary(
                entity=entity,
                new_content="New content",
                db_session=db_session
            )

            # Should return empty string on error with no existing summary
            assert result == ""


class TestExtractKeyEvents:
    """Tests for extract_key_events async method."""

    @pytest.mark.asyncio
    async def test_extract_key_events_basic(self):
        """Test basic key events extraction."""
        service = EntityMemoryService()

        entity = MagicMock()
        entity.id = 1
        entity.key_events = None

        db_session = AsyncMock()

        # Mock AI response with JSON
        new_events = [
            {"date": "2024-01-15", "event": "hired", "details": "Joined company"}
        ]

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(new_events))]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch.object(service, '_client', mock_client):
            result = await service.extract_key_events(
                entity=entity,
                content="Discussed joining the company on Jan 15",
                db_session=db_session
            )

            assert len(result) == 1
            assert result[0]["event"] == "hired"
            assert entity.key_events == new_events
            db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_key_events_adds_to_existing(self):
        """Test adding new events to existing ones."""
        service = EntityMemoryService()

        entity = MagicMock()
        entity.id = 1
        entity.key_events = [
            {"date": "2024-01-01", "event": "interview", "details": "First interview"}
        ]

        db_session = AsyncMock()

        new_events = [
            {"date": "2024-01-15", "event": "hired", "details": "Got hired"}
        ]

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(new_events))]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch.object(service, '_client', mock_client):
            await service.extract_key_events(
                entity=entity,
                content="Got hired on Jan 15",
                db_session=db_session
            )

            # Should have both events
            assert len(entity.key_events) == 2

    @pytest.mark.asyncio
    async def test_extract_key_events_sorts_by_date(self):
        """Test that events are sorted by date."""
        service = EntityMemoryService()

        entity = MagicMock()
        entity.id = 1
        entity.key_events = [
            {"date": "2024-03-01", "event": "meeting", "details": "Meeting"}
        ]

        db_session = AsyncMock()

        # Add events with dates before and after existing
        new_events = [
            {"date": "2024-01-15", "event": "hired", "details": "Hired"},
            {"date": "2024-05-01", "event": "promotion", "details": "Promoted"}
        ]

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(new_events))]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch.object(service, '_client', mock_client):
            await service.extract_key_events(
                entity=entity,
                content="Events",
                db_session=db_session
            )

            # Should be sorted by date
            assert entity.key_events[0]["date"] == "2024-01-15"
            assert entity.key_events[1]["date"] == "2024-03-01"
            assert entity.key_events[2]["date"] == "2024-05-01"

    @pytest.mark.asyncio
    async def test_extract_key_events_handles_markdown_json(self):
        """Test parsing JSON wrapped in markdown code blocks."""
        service = EntityMemoryService()

        entity = MagicMock()
        entity.id = 1
        entity.key_events = None

        db_session = AsyncMock()

        new_events = [
            {"date": "2024-01-15", "event": "hired", "details": "Hired"}
        ]

        # JSON wrapped in markdown code block
        markdown_json = f"```json\n{json.dumps(new_events)}\n```"

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=markdown_json)]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch.object(service, '_client', mock_client):
            result = await service.extract_key_events(
                entity=entity,
                content="Content",
                db_session=db_session
            )

            assert len(result) == 1
            assert result[0]["event"] == "hired"

    @pytest.mark.asyncio
    async def test_extract_key_events_empty_response(self):
        """Test handling empty event list response."""
        service = EntityMemoryService()

        entity = MagicMock()
        entity.id = 1
        entity.key_events = None

        db_session = AsyncMock()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="[]")]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch.object(service, '_client', mock_client):
            result = await service.extract_key_events(
                entity=entity,
                content="Nothing significant",
                db_session=db_session
            )

            assert result == []
            # Entity should not be modified
            assert entity.key_events is None
            db_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_extract_key_events_error_handling(self):
        """Test error handling during event extraction."""
        service = EntityMemoryService()

        entity = MagicMock()
        entity.id = 1
        entity.key_events = None

        db_session = AsyncMock()

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("API Error"))

        with patch.object(service, '_client', mock_client):
            result = await service.extract_key_events(
                entity=entity,
                content="Content",
                db_session=db_session
            )

            # Should return empty list on error
            assert result == []
            db_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_extract_key_events_invalid_json(self):
        """Test handling invalid JSON response."""
        service = EntityMemoryService()

        entity = MagicMock()
        entity.id = 1
        entity.key_events = None

        db_session = AsyncMock()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Not valid JSON at all")]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch.object(service, '_client', mock_client):
            result = await service.extract_key_events(
                entity=entity,
                content="Content",
                db_session=db_session
            )

            # Should handle gracefully
            assert result == []

    @pytest.mark.asyncio
    async def test_extract_key_events_truncates_content(self):
        """Test that content is truncated to 5000 chars."""
        service = EntityMemoryService()

        entity = MagicMock()
        entity.id = 1
        entity.key_events = None

        db_session = AsyncMock()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="[]")]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch.object(service, '_client', mock_client):
            long_content = "A" * 10000

            await service.extract_key_events(
                entity=entity,
                content=long_content,
                db_session=db_session
            )

            # Verify content was truncated
            call_kwargs = mock_client.messages.create.call_args[1]
            prompt = call_kwargs['messages'][0]['content']

            # Should not contain all 10000 chars
            assert len(prompt) < 10000


class TestBuildMemoryContext:
    """Tests for build_memory_context method (already tested in test_entity_memory.py, adding edge cases)."""

    def test_build_memory_context_with_many_events(self):
        """Test that only last 10 events are included."""
        service = EntityMemoryService()

        entity = MagicMock()
        entity.ai_summary = None
        entity.key_events = [
            {"date": f"2024-{i:02d}-01", "event": "meeting", "details": f"Event {i}"}
            for i in range(1, 20)  # 19 events
        ]

        context = service.build_memory_context(entity)

        # Should show last 10 (events 10-19)
        assert "Event 19" in context
        assert "Event 10" in context
        # Should not show first 9 (сравнение по строкам: «Event 1» — подстрока «Event 19»)
        import re
        shown = {int(n) for n in re.findall(r"Event (\d+)$", context, re.M)}
        assert shown == set(range(10, 20))

    def test_build_memory_context_event_emojis(self):
        """Test that different event types get correct emojis."""
        service = EntityMemoryService()

        entity = MagicMock()
        entity.ai_summary = None
        entity.key_events = [
            {"date": "2024-01-01", "event": "hired", "details": "Test"},
            {"date": "2024-01-02", "event": "fired", "details": "Test"},
            {"date": "2024-01-03", "event": "promotion", "details": "Test"},
            {"date": "2024-01-04", "event": "demotion", "details": "Test"},
            {"date": "2024-01-05", "event": "transfer", "details": "Test"},
            {"date": "2024-01-06", "event": "warning", "details": "Test"},
            {"date": "2024-01-07", "event": "achievement", "details": "Test"},
            {"date": "2024-01-08", "event": "meeting", "details": "Test"},
            {"date": "2024-01-09", "event": "offer", "details": "Test"},
            {"date": "2024-01-10", "event": "rejection", "details": "Test"},
            {"date": "2024-01-11", "event": "interview", "details": "Test"},
            {"date": "2024-01-12", "event": "unknown", "details": "Test"},
        ]

        context = service.build_memory_context(entity)

        # Only last 10 events shown: hired и fired (первые два) не попадают
        assert "✅" not in context  # hired
        assert "❌" not in context  # fired
        assert "⬆️" in context  # promotion
        assert "🎤" in context  # interview
        assert "📌" in context  # unknown → значок по умолчанию

    def test_build_memory_context_event_without_details(self):
        """Test event formatting when details are missing."""
        service = EntityMemoryService()

        entity = MagicMock()
        entity.ai_summary = None
        entity.key_events = [
            {"date": "2024-01-01", "event": "hired"}  # No details
        ]

        context = service.build_memory_context(entity)

        # Should still work, using event type as fallback
        assert "hired" in context


class TestPromptConstants:
    """Tests for prompt template constants."""

    def test_summary_prompt_has_placeholders(self):
        """Test SUMMARY_PROMPT has required placeholders."""
        assert "{current_summary}" in SUMMARY_PROMPT
        assert "{new_content}" in SUMMARY_PROMPT
        assert "{key_events}" in SUMMARY_PROMPT

    def test_key_events_prompt_has_placeholders(self):
        """Test KEY_EVENTS_PROMPT has required placeholders."""
        assert "{content}" in KEY_EVENTS_PROMPT
        assert "{existing_events}" in KEY_EVENTS_PROMPT

    def test_summary_prompt_in_russian(self):
        """Test SUMMARY_PROMPT is in Russian."""
        cyrillic_count = sum(1 for c in SUMMARY_PROMPT if '\u0400' <= c <= '\u04FF')
        assert cyrillic_count > 50

    def test_key_events_prompt_in_russian(self):
        """Test KEY_EVENTS_PROMPT is in Russian."""
        cyrillic_count = sum(1 for c in KEY_EVENTS_PROMPT if '\u0400' <= c <= '\u04FF')
        assert cyrillic_count > 20


class TestConstants:
    """Tests for module constants."""

    def test_summary_update_interval_is_timedelta(self):
        """Test SUMMARY_UPDATE_INTERVAL is a timedelta."""
        assert isinstance(SUMMARY_UPDATE_INTERVAL, timedelta)
        assert SUMMARY_UPDATE_INTERVAL == timedelta(hours=24)

    def test_min_new_content_length_is_positive(self):
        """Test MIN_NEW_CONTENT_LENGTH is positive."""
        assert MIN_NEW_CONTENT_LENGTH > 0
        assert MIN_NEW_CONTENT_LENGTH == 500


class TestShouldUpdateSummaryEdgeCases:
    """Additional edge cases for should_update_summary."""

    def test_should_update_with_significant_new_content(self):
        """Test update when there's significant new content."""
        service = EntityMemoryService()

        entity = MagicMock()
        entity.ai_summary = "Existing"
        entity.ai_summary_updated_at = datetime.utcnow() - timedelta(hours=1)

        # Double the min threshold
        assert service.should_update_summary(entity, MIN_NEW_CONTENT_LENGTH * 2) is True

    def test_should_update_no_updated_at_timestamp(self):
        """Test when entity has summary but no updated_at timestamp."""
        service = EntityMemoryService()

        entity = MagicMock()
        entity.ai_summary = "Existing"
        entity.ai_summary_updated_at = None

        # Should not update without timestamp (treat as recent)
        assert service.should_update_summary(entity, 100) is False

        # Unless there's significant new content
        assert service.should_update_summary(entity, MIN_NEW_CONTENT_LENGTH * 2) is True
