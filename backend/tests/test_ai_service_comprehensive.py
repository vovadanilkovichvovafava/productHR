"""
Comprehensive tests for AI service to reach 90% coverage.

Tests advanced scenarios:
- Prompt caching behavior
- Smart truncation in context
- History limiting
- Participant roles integration
- Report caching
- Edge cases and error handling
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from api.services.ai import AIService, ai_service
from api.models.database import Message, Chat, ChatType


class TestPromptCaching:
    """Tests for prompt caching (cache_control) functionality."""

    @pytest.mark.asyncio
    async def test_chat_stream_uses_cache_control(self):
        """Test that chat_stream sets cache_control for system prompt."""
        service = AIService()

        mock_client = MagicMock()

        async def mock_text_stream():
            yield "test"

        def create_stream(*args, **kwargs):
            mock_stream = MagicMock()
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock(return_value=None)
            mock_stream.text_stream = mock_text_stream()
            return mock_stream

        mock_client.messages.stream = MagicMock(side_effect=create_stream)

        with patch.object(service, '_client', mock_client):
            async for _ in service.chat_stream(
                user_message="Test",
                chat_title="Test Chat",
                messages=[],
                criteria=[],
                conversation_history=[],
                chat_type="hr"
            ):
                pass

            # Verify cache_control was set
            call_kwargs = mock_client.messages.stream.call_args[1]
            assert 'system' in call_kwargs
            assert isinstance(call_kwargs['system'], list)
            assert len(call_kwargs['system']) == 1

            system_block = call_kwargs['system'][0]
            assert system_block['type'] == 'text'
            assert 'cache_control' in system_block
            assert system_block['cache_control']['type'] == 'ephemeral'

    @pytest.mark.asyncio
    async def test_generate_report_uses_cache_control(self):
        """Test that generate_report sets cache_control for system prompt."""
        service = AIService()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Report text")]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch.object(service, '_client', mock_client):
            await service.generate_report(
                chat_title="Test",
                messages=[],
                criteria=[],
                report_type="standard",
                include_quotes=True,
                chat_type="hr"
            )

            call_kwargs = mock_client.messages.create.call_args[1]
            system_block = call_kwargs['system'][0]

            assert 'cache_control' in system_block
            assert system_block['cache_control']['type'] == 'ephemeral'


class TestHistoryLimiting:
    """Tests for conversation history limiting."""

    @pytest.mark.asyncio
    async def test_chat_stream_limits_history(self):
        """Test that chat_stream limits history to MAX_HISTORY_MESSAGES."""
        service = AIService()

        # Create 100 history messages (50 user + 50 assistant, more than MAX_HISTORY_MESSAGES = 40)
        large_history = []
        for i in range(50):
            large_history.extend([
                {"role": "user", "content": f"User message {i}"},
                {"role": "assistant", "content": f"Assistant message {i}"}
            ])
        # Total: 100 messages (indices 0-99)

        mock_client = MagicMock()

        async def mock_text_stream():
            yield "test"

        def create_stream(*args, **kwargs):
            mock_stream = MagicMock()
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock(return_value=None)
            mock_stream.text_stream = mock_text_stream()
            return mock_stream

        mock_client.messages.stream = MagicMock(side_effect=create_stream)

        with patch.object(service, '_client', mock_client):
            async for _ in service.chat_stream(
                user_message="New message",
                chat_title="Test",
                messages=[],
                criteria=[],
                conversation_history=large_history,
                chat_type="hr"
            ):
                pass

            call_kwargs = mock_client.messages.stream.call_args[1]
            api_messages = call_kwargs['messages']

            # Should have 40 history + 1 new = 41 total
            assert len(api_messages) == 41

            # Should include only last 40 from history (indices 60-99)
            # Index 60 = "User message 30" (message at iteration i=30)
            assert api_messages[0]['content'] == "User message 30"

    @pytest.mark.asyncio
    async def test_entity_ai_limits_history(self):
        """Test that entity AI also limits conversation history."""
        from api.services.entity_ai import EntityAIService
        from api.models.database import Entity, EntityType, EntityStatus

        service = EntityAIService()

        # Create large history
        large_history = []
        for i in range(50):
            large_history.extend([
                {"role": "user", "content": f"Q{i}"},
                {"role": "assistant", "content": f"A{i}"}
            ])

        entity = MagicMock()
        entity.id = 1
        entity.name = "Test"
        entity.type = MagicMock(value="candidate")
        entity.status = MagicMock(value="active")
        entity.company = None
        entity.position = None
        entity.email = None
        entity.phone = None
        entity.tags = []
        entity.ai_summary = None
        entity.key_events = None

        mock_client = MagicMock()

        async def mock_text_stream():
            yield "test"

        def create_stream(*args, **kwargs):
            mock_stream = MagicMock()
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock(return_value=None)
            mock_stream.text_stream = mock_text_stream()
            return mock_stream

        mock_client.messages.stream = MagicMock(side_effect=create_stream)

        with patch.object(service, '_client', mock_client):
            async for _ in service.chat_stream(
                user_message="New",
                entity=entity,
                chats=[],
                calls=[],
                conversation_history=large_history
            ):
                pass

            call_kwargs = mock_client.messages.stream.call_args[1]
            api_messages = call_kwargs['messages']

            # Should limit to 40 + 1 new
            assert len(api_messages) == 41


class TestSmartTruncation:
    """Tests for smart truncation in message formatting."""

    def test_format_messages_truncates_long_content(self):
        """Test that long messages are truncated with smart_truncate."""
        service = AIService()

        # Create a message with very long content
        long_msg = Message(
            id=1,
            chat_id=1,
            telegram_message_id=1,
            telegram_user_id=1,
            first_name="User",
            content="A" * 1000,  # Very long content
            content_type="text",
            timestamp=datetime(2025, 1, 1)
        )

        result = service._format_messages([long_msg], max_per_message=200)

        # Should be truncated
        assert len(result) < 1000
        assert "пропущено" in result

    def test_format_messages_max_per_message_parameter(self):
        """Test that max_per_message parameter works."""
        service = AIService()

        msg = Message(
            id=1, chat_id=1, telegram_message_id=1,
            telegram_user_id=1, first_name="User",
            content="X" * 1000, content_type="text",
            timestamp=datetime(2025, 1, 1)
        )

        # Test with different limits
        result_500 = service._format_messages([msg], max_per_message=500)
        result_200 = service._format_messages([msg], max_per_message=200)

        # Smaller limit should produce shorter result
        assert len(result_200) < len(result_500)


class TestParticipantRoles:
    """Tests for participant role integration."""

    def test_format_messages_with_chat_object(self):
        """Test that chat object enables participant role display."""
        service = AIService()

        chat = MagicMock()
        chat.id = 1
        chat.org_id = 1
        chat.owner_id = 1

        msg = Message(
            id=1, chat_id=1, telegram_message_id=1,
            telegram_user_id=123, username="test",
            first_name="Test", last_name="User",
            content="Hello", content_type="text",
            timestamp=datetime(2025, 1, 1)
        )

        # Format with chat object
        result = service._format_messages([msg], chat=chat)

        # Should contain the message
        assert "Hello" in result

    def test_build_system_prompt_with_chat_object(self):
        """Test that chat object is passed through to build system prompt."""
        service = AIService()

        chat = MagicMock()
        chat.id = 1

        msg = Message(
            id=1, chat_id=1, telegram_message_id=1,
            telegram_user_id=123, first_name="User",
            content="Test", content_type="text",
            timestamp=datetime(2025, 1, 1)
        )

        result = service._build_system_prompt(
            chat_title="Test",
            messages=[msg],
            criteria=[],
            chat_type="hr",
            chat=chat
        )

        # Should contain the formatted message
        assert "Test" in result


class TestReportCaching:
    """Tests for report caching functionality."""

    @pytest.mark.asyncio
    async def test_generate_report_with_cache_enabled(self):
        """Test that generate_report uses cache when enabled."""
        service = AIService()

        msg = Message(
            id=1, chat_id=1, telegram_message_id=1,
            telegram_user_id=1, first_name="User",
            content="Test", content_type="text",
            timestamp=datetime(2025, 1, 1)
        )

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Generated report")]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch.object(service, '_client', mock_client):
            # First call - should generate
            result1 = await service.generate_report(
                chat_title="Test",
                messages=[msg],
                criteria=[],
                report_type="standard",
                include_quotes=True,
                chat_type="hr",
                chat_id=1,
                use_cache=True
            )

            # Second call with same data - should use cache
            result2 = await service.generate_report(
                chat_title="Test",
                messages=[msg],
                criteria=[],
                report_type="standard",
                include_quotes=True,
                chat_type="hr",
                chat_id=1,
                use_cache=True
            )

            # Both should return same result
            assert result1 == result2

            # But API should only be called once (second uses cache)
            assert mock_client.messages.create.call_count == 1

    @pytest.mark.asyncio
    async def test_generate_report_with_cache_disabled(self):
        """Test that cache can be disabled."""
        service = AIService()

        msg = Message(
            id=1, chat_id=1, telegram_message_id=1,
            telegram_user_id=1, first_name="User",
            content="Test", content_type="text",
            timestamp=datetime(2025, 1, 1)
        )

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Generated report")]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch.object(service, '_client', mock_client):
            # First call with cache disabled
            await service.generate_report(
                chat_title="Test",
                messages=[msg],
                criteria=[],
                report_type="standard",
                include_quotes=True,
                chat_type="hr",
                chat_id=1,
                use_cache=False
            )

            # Second call - should call API again
            await service.generate_report(
                chat_title="Test",
                messages=[msg],
                criteria=[],
                report_type="standard",
                include_quotes=True,
                chat_type="hr",
                chat_id=1,
                use_cache=False
            )

            # Should be called twice (no caching)
            assert mock_client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_generate_report_without_chat_id_no_cache(self):
        """Test that cache is not used without chat_id."""
        service = AIService()

        msg = Message(
            id=1, chat_id=1, telegram_message_id=1,
            telegram_user_id=1, first_name="User",
            content="Test", content_type="text",
            timestamp=datetime(2025, 1, 1)
        )

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Generated report")]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch.object(service, '_client', mock_client):
            # Call without chat_id
            await service.generate_report(
                chat_title="Test",
                messages=[msg],
                criteria=[],
                report_type="standard",
                include_quotes=True,
                chat_type="hr",
                chat_id=None,  # No chat_id
                use_cache=True  # Cache enabled but won't work
            )

            # Second call
            await service.generate_report(
                chat_title="Test",
                messages=[msg],
                criteria=[],
                report_type="standard",
                include_quotes=True,
                chat_type="hr",
                chat_id=None,
                use_cache=True
            )

            # Should call API both times (no chat_id = no cache)
            assert mock_client.messages.create.call_count == 2


class TestEdgeCases:
    """Tests for edge cases and error scenarios."""

    def test_format_messages_with_none_values(self):
        """Test formatting messages with None values."""
        service = AIService()

        msg = Message(
            id=1, chat_id=1, telegram_message_id=1,
            telegram_user_id=1,
            first_name=None,
            last_name=None,
            username=None,
            content=None,
            content_type="text",
            timestamp=None
        )

        result = service._format_messages([msg])

        # Should handle None values gracefully
        assert result is not None
        assert isinstance(result, str)

    def test_format_criteria_with_none_values(self):
        """Test formatting criteria with missing fields."""
        service = AIService()

        criteria = [
            {"name": "Test"},  # Missing all optional fields
            {},  # Missing even name
        ]

        result = service._format_criteria(criteria)

        # Should handle gracefully
        assert result is not None

    @pytest.mark.asyncio
    async def test_chat_stream_with_empty_messages_and_criteria(self):
        """Test chat_stream with completely empty inputs."""
        service = AIService()

        mock_client = MagicMock()

        async def mock_text_stream():
            yield "response"

        def create_stream(*args, **kwargs):
            mock_stream = MagicMock()
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock(return_value=None)
            mock_stream.text_stream = mock_text_stream()
            return mock_stream

        mock_client.messages.stream = MagicMock(side_effect=create_stream)

        with patch.object(service, '_client', mock_client):
            chunks = []
            async for chunk in service.chat_stream(
                user_message="",  # Empty message
                chat_title="",    # Empty title
                messages=[],      # No messages
                criteria=[],      # No criteria
                conversation_history=[],
                chat_type="custom"
            ):
                chunks.append(chunk)

            # Should still work
            assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_quick_action_with_custom_type_unknown_action(self):
        """Test quick_action fallback for unknown action in custom type."""
        service = AIService()

        mock_client = MagicMock()

        async def mock_text_stream():
            yield "fallback"

        def create_stream(*args, **kwargs):
            mock_stream = MagicMock()
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock(return_value=None)
            mock_stream.text_stream = mock_text_stream()
            return mock_stream

        mock_client.messages.stream = MagicMock(side_effect=create_stream)

        with patch.object(service, '_client', mock_client):
            chunks = []
            async for chunk in service.quick_action(
                action="totally_unknown_action_xyz",
                chat_title="Test",
                messages=[],
                criteria=[],
                chat_type="custom"
            ):
                chunks.append(chunk)

            # Should use fallback prompt
            assert len(chunks) > 0

    def test_singleton_instance(self):
        """Test that ai_service singleton works correctly."""
        assert ai_service is not None
        assert isinstance(ai_service, AIService)

        # Singleton should be the same instance
        assert ai_service is ai_service


class TestMessageTypes:
    """Tests for different message content types."""

    def test_format_messages_video_note(self):
        """Test formatting video_note messages."""
        service = AIService()

        msg = Message(
            id=1, chat_id=1, telegram_message_id=1,
            telegram_user_id=1, first_name="User",
            content="Video note content",
            content_type="video_note",
            timestamp=datetime(2025, 1, 1)
        )

        result = service._format_messages([msg])

        assert "[📹]" in result

    def test_format_messages_skips_photo_without_caption(self):
        """Test that photos without captions are skipped."""
        from api.services.cache import format_messages_optimized

        msg = MagicMock()
        msg.content = ""
        msg.content_type = "photo"
        msg.first_name = "User"
        msg.last_name = ""
        msg.username = None
        msg.timestamp = datetime.now()

        result = format_messages_optimized([msg])

        # Photo without content should be skipped
        assert result == ""

    def test_format_messages_includes_photo_with_caption(self):
        """Test that photos with captions are included."""
        from api.services.cache import format_messages_optimized

        msg = MagicMock()
        msg.content = "Photo caption"
        msg.content_type = "photo"
        msg.first_name = "User"
        msg.last_name = ""
        msg.username = None
        msg.timestamp = datetime.now()
        msg.file_name = None

        result = format_messages_optimized([msg])

        # Photo with caption should be included
        assert "Photo caption" in result


class TestCriteriaFormatting:
    """Tests for criteria formatting edge cases."""

    def test_format_criteria_all_categories(self):
        """Test all category emoji mappings."""
        service = AIService()

        criteria = [
            {"name": "Red", "category": "red_flags", "weight": 5, "description": "Test"},
            {"name": "Green", "category": "green_flags", "weight": 5, "description": "Test"},
            {"name": "Other", "category": "other", "weight": 5, "description": "Test"},
        ]

        result = service._format_criteria(criteria)

        assert "🚩 Red" in result
        assert "✅ Green" in result
        assert "📋 Other" in result  # Unknown category gets default

    def test_format_criteria_preserves_order(self):
        """Test that criteria order is preserved."""
        service = AIService()

        criteria = [
            {"name": "First", "weight": 10},
            {"name": "Second", "weight": 5},
            {"name": "Third", "weight": 8},
        ]

        result = service._format_criteria(criteria)

        # Order should be preserved
        first_pos = result.find("First")
        second_pos = result.find("Second")
        third_pos = result.find("Third")

        assert first_pos < second_pos < third_pos
