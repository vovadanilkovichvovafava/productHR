"""
Comprehensive tests for Entity AI Service to reach 90% coverage.

Tests:
- chat_stream method with full entity context
- quick_action method with all actions
- Context building with chats and calls
- Streaming error handling
- Long transcript truncation
- Entity without data scenarios
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from api.services.entity_ai import EntityAIService, ENTITY_QUICK_ACTIONS, entity_ai_service
from api.models.database import Entity, Chat, CallRecording, Message


class TestEntityAIServiceInitialization:
    """Tests for EntityAIService initialization."""

    def test_init_creates_instance(self):
        """Test that EntityAIService initializes correctly."""
        service = EntityAIService()

        assert service._client is None
        assert service.model == "claude-sonnet-4-6"

    def test_client_property_lazy_loads(self):
        """Test that client property lazy loads AsyncAnthropic."""
        service = EntityAIService()

        with patch('api.services.entity_ai.settings') as mock_settings:
            mock_settings.anthropic_api_key = "test-key"

            with patch('api.services.entity_ai.AsyncAnthropic') as mock_anthropic:
                mock_client = MagicMock()
                mock_anthropic.return_value = mock_client

                # First access
                client = service.client
                assert client is mock_client

                # Second access (should reuse)
                client2 = service.client
                assert client2 is mock_client

                mock_anthropic.assert_called_once()

    def test_client_property_raises_without_api_key(self):
        """Test that client raises error when API key is missing."""
        service = EntityAIService()

        with patch('api.services.entity_ai.settings') as mock_settings:
            mock_settings.anthropic_api_key = None

            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY не настроен"):
                _ = service.client

    def test_singleton_instance_exists(self):
        """Test that entity_ai_service singleton is available."""
        assert entity_ai_service is not None
        assert isinstance(entity_ai_service, EntityAIService)


class TestBuildEntityContext:
    """Tests for _build_entity_context method."""

    async def test_build_context_basic_entity(self):
        """Test building context with basic entity info."""
        service = EntityAIService()

        entity = MagicMock()
        entity.name = "John Doe"
        entity.type = MagicMock(value="candidate")
        entity.status = MagicMock(value="active")
        entity.company = "Test Corp"
        entity.position = "Developer"
        entity.email = "john@test.com"
        entity.phone = "+1234567890"
        entity.tags = ["python", "senior"]
        entity.ai_summary = None
        entity.key_events = None

        context = await service._build_entity_context(entity, [], [])

        assert "John Doe" in context
        assert "candidate" in context
        assert "active" in context
        assert "Test Corp" in context
        assert "Developer" in context
        assert "john@test.com" in context
        assert "+1234567890" in context
        assert "python" in context
        assert "senior" in context

    async def test_build_context_with_chats(self):
        """Test building context with linked chats."""
        service = EntityAIService()

        entity = MagicMock()
        entity.name = "Test User"
        entity.type = MagicMock(value="candidate")
        entity.status = MagicMock(value="active")
        entity.company = None
        entity.position = None
        entity.email = None
        entity.phone = None
        entity.tags = []
        entity.ai_summary = None
        entity.key_events = None

        # Create chat with messages
        chat = MagicMock()
        chat.custom_name = None
        chat.title = "Interview Chat"
        chat.chat_type = MagicMock(value="hr")
        chat.id = 1
        chat.org_id = 1
        chat.owner_id = 1

        msg = MagicMock()
        msg.telegram_user_id = 123
        msg.username = "testuser"
        msg.first_name = "Test"
        msg.last_name = "User"
        msg.content = "Hello from chat"
        msg.content_type = "text"
        msg.timestamp = datetime(2025, 1, 1, 10, 0)
        msg.file_name = None

        chat.messages = [msg]

        context = await service._build_entity_context(entity, [chat], [])

        assert "ПЕРЕПИСКИ:" in context
        assert "Interview Chat" in context
        assert "Hello from chat" in context

    async def test_build_context_with_calls(self):
        """Test building context with call recordings."""
        service = EntityAIService()

        entity = MagicMock()
        entity.name = "Test User"
        entity.type = MagicMock(value="candidate")
        entity.status = MagicMock(value="active")
        entity.company = None
        entity.position = None
        entity.email = None
        entity.phone = None
        entity.tags = []
        entity.ai_summary = None
        entity.key_events = None

        call = MagicMock()
        call.created_at = datetime(2025, 1, 15, 14, 30)
        call.title = "Phone Interview"
        call.duration_seconds = 1800  # 30 minutes
        call.summary = "Discussed technical background"
        call.key_points = ["Strong Python skills", "5 years experience"]
        call.transcript = "Interviewer: Tell me about yourself. Candidate: I have been..."

        context = await service._build_entity_context(entity, [], [call])

        assert "ЗВОНКИ:" in context
        assert "Phone Interview" in context
        assert "30м 0с" in context  # Duration formatted
        assert "Discussed technical background" in context
        assert "Strong Python skills" in context
        assert "I have been..." in context

    async def test_build_context_truncates_long_transcript(self):
        """Test that long call transcripts are truncated."""
        service = EntityAIService()

        entity = MagicMock()
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

        call = MagicMock()
        call.created_at = datetime(2025, 1, 15)
        call.title = "Call"
        call.duration_seconds = 3600
        call.summary = None
        call.key_points = []
        call.transcript = "A" * 50000  # Very long transcript
        call.participant_roles = None
        call.speaker_stats = None

        context = await service._build_entity_context(entity, [], [call])

        # build_smart_context: у длинного звонка транскрипт больше 40 000 знаков
        # режется на начало и конец с пометкой «пропущено» (раньше — 5000 и
        # «транскрипт обрезан»).
        assert "пропущено" in context
        assert "A" * 50000 not in context

    async def test_build_context_with_memory(self):
        """Test that context includes AI memory (summary + key events)."""
        service = EntityAIService()

        entity = MagicMock()
        entity.name = "Test"
        entity.type = MagicMock(value="candidate")
        entity.status = MagicMock(value="active")
        entity.company = None
        entity.position = None
        entity.email = None
        entity.phone = None
        entity.tags = []
        entity.ai_summary = "Experienced developer with strong background"
        entity.key_events = [
            {"date": "2024-01-15", "event": "hired", "details": "Started as Junior"}
        ]

        context = await service._build_entity_context(entity, [], [])

        # Should include memory sections
        assert "📋 Резюме контакта" in context
        assert "Experienced developer" in context
        assert "📅 Ключевые события" in context
        assert "Started as Junior" in context

    async def test_build_context_limits_messages_per_chat(self):
        """Test that only last 300 messages per chat are included."""
        service = EntityAIService()

        entity = MagicMock()
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

        # Create chat with many messages
        chat = MagicMock()
        chat.custom_name = None
        chat.title = "Long Chat"
        chat.chat_type = MagicMock(value="work")
        chat.id = 1
        chat.org_id = 1
        chat.owner_id = 1

        # 350 сообщений: в контекст идут последние 300 (было 100)
        messages = []
        for i in range(350):
            msg = MagicMock()
            msg.telegram_user_id = 123
            msg.username = "user"
            msg.first_name = "User"
            msg.last_name = ""
            msg.content = f"Message {i}"
            msg.content_type = "text"
            msg.timestamp = datetime(2025, 1, 1, 10, 0) + timedelta(minutes=i)
            msg.file_name = None
            messages.append(msg)

        chat.messages = messages

        context = await service._build_entity_context(entity, [chat], [])

        import re
        shown = {int(n) for n in re.findall(r"Message (\d+)$", context, re.M)}
        # Последние 300 (Message 50 onwards)
        assert 349 in shown
        assert 50 in shown
        # Первые 50 не попадают
        assert 0 not in shown
        assert 49 not in shown

    async def test_build_context_no_chats_or_calls(self):
        """Test context when entity has no linked chats or calls."""
        service = EntityAIService()

        entity = MagicMock()
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

        context = await service._build_entity_context(entity, [], [])

        # Should have warning message
        # Подсказка теперь упоминает и файлы.
        assert "не привязаны чаты, звонки или файлы" in context


class TestBuildSystemPrompt:
    """Tests for _build_system_prompt method."""

    def test_build_system_prompt_structure(self):
        """Test that system prompt has correct structure."""
        service = EntityAIService()

        prompt = service._build_system_prompt("Test context")

        assert "AI-ассистент для HR-аналитики" in prompt
        assert "Test context" in prompt
        assert "ПРАВИЛА:" in prompt

    def test_system_prompt_includes_humor_instructions(self):
        """Test that system prompt includes instructions about humor."""
        service = EntityAIService()

        prompt = service._build_system_prompt("Test")

        # Should mention humor/sarcasm handling
        assert "юмор" in prompt.lower() or "сарказм" in prompt.lower()


class TestChatStream:
    """Tests for chat_stream method."""

    @pytest.mark.asyncio
    async def test_chat_stream_basic(self):
        """Test basic chat streaming with entity context."""
        service = EntityAIService()

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
            chunks = ["Test ", "streaming ", "response"]
            for chunk in chunks:
                yield chunk

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
                user_message="Tell me about this person",
                entity=entity,
                chats=[],
                calls=[],
                conversation_history=[]
            ):
                chunks.append(chunk)

            assert len(chunks) == 3
            assert "".join(chunks) == "Test streaming response"

    @pytest.mark.asyncio
    async def test_chat_stream_uses_cache_control(self):
        """Test that chat_stream uses prompt caching."""
        service = EntityAIService()

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
                user_message="Test",
                entity=entity,
                chats=[],
                calls=[],
                conversation_history=[]
            ):
                pass

            call_kwargs = mock_client.messages.stream.call_args[1]
            system = call_kwargs['system']

            # Should use cache_control
            assert isinstance(system, list)
            assert system[0]['cache_control']['type'] == 'ephemeral'

    @pytest.mark.asyncio
    async def test_chat_stream_error_handling(self):
        """Test error handling during streaming."""
        service = EntityAIService()

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
        mock_client.messages.stream.side_effect = Exception("API Error")

        with patch.object(service, '_client', mock_client):
            with pytest.raises(Exception, match="API Error"):
                async for _ in service.chat_stream(
                    user_message="Test",
                    entity=entity,
                    chats=[],
                    calls=[],
                    conversation_history=[]
                ):
                    pass


class TestQuickAction:
    """Tests for quick_action method."""

    @pytest.mark.asyncio
    async def test_quick_action_full_analysis(self):
        """Test full_analysis quick action."""
        service = EntityAIService()

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
            yield "Analysis result"

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
                action="full_analysis",
                entity=entity,
                chats=[],
                calls=[]
            ):
                chunks.append(chunk)

            assert len(chunks) > 0
            assert "Analysis result" in "".join(chunks)

    @pytest.mark.asyncio
    async def test_quick_action_unknown_action(self):
        """Test quick_action with unknown action."""
        service = EntityAIService()

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

        chunks = []
        async for chunk in service.quick_action(
            action="unknown_action_xyz",
            entity=entity,
            chats=[],
            calls=[]
        ):
            chunks.append(chunk)

        # Should yield error message
        assert len(chunks) > 0
        assert "Неизвестное действие" in "".join(chunks)

    @pytest.mark.asyncio
    async def test_all_quick_actions_work(self):
        """Test that all defined quick actions work."""
        service = EntityAIService()

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
            yield "result"

        def create_stream(*args, **kwargs):
            mock_stream = MagicMock()
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock(return_value=None)
            mock_stream.text_stream = mock_text_stream()
            return mock_stream

        mock_client.messages.stream = MagicMock(side_effect=create_stream)

        actions = ["full_analysis", "red_flags", "comparison", "prediction", "summary", "questions"]

        for action in actions:
            with patch.object(service, '_client', mock_client):
                chunks = []
                async for chunk in service.quick_action(
                    action=action,
                    entity=entity,
                    chats=[],
                    calls=[]
                ):
                    chunks.append(chunk)

                assert len(chunks) > 0


class TestGetAvailableActions:
    """Tests for get_available_actions method."""

    def test_get_available_actions_returns_list(self):
        """Test that get_available_actions returns correct structure."""
        service = EntityAIService()

        actions = service.get_available_actions()

        assert isinstance(actions, list)
        assert len(actions) == 6

    def test_available_actions_have_required_fields(self):
        """Test that each action has required fields."""
        service = EntityAIService()

        actions = service.get_available_actions()

        for action in actions:
            assert "id" in action
            assert "label" in action
            assert "icon" in action
            assert isinstance(action["id"], str)
            assert isinstance(action["label"], str)
            assert isinstance(action["icon"], str)

    def test_available_actions_ids_match_prompts(self):
        """Test that action IDs match ENTITY_QUICK_ACTIONS keys."""
        service = EntityAIService()

        actions = service.get_available_actions()
        action_ids = [a["id"] for a in actions]

        for action_id in action_ids:
            assert action_id in ENTITY_QUICK_ACTIONS


class TestEntityQuickActionPrompts:
    """Tests for ENTITY_QUICK_ACTIONS constant."""

    def test_all_actions_defined(self):
        """Test that all expected actions are defined."""
        expected = ["full_analysis", "red_flags", "comparison", "prediction", "summary", "questions"]

        for action in expected:
            assert action in ENTITY_QUICK_ACTIONS

    def test_prompts_are_non_empty(self):
        """Test that all prompts have content."""
        for action, prompt in ENTITY_QUICK_ACTIONS.items():
            assert len(prompt) > 50, f"Action {action} prompt too short"

    def test_prompts_in_russian(self):
        """Test that all prompts are in Russian."""
        for action, prompt in ENTITY_QUICK_ACTIONS.items():
            # Count Cyrillic characters
            cyrillic_count = sum(1 for c in prompt if '\u0400' <= c <= '\u04FF')
            assert cyrillic_count > 20, f"Action {action} should be in Russian"


class TestEdgeCases:
    """Tests for edge cases."""

    async def test_build_context_with_empty_chat_messages(self):
        """Test context building with chat that has no messages."""
        service = EntityAIService()

        entity = MagicMock()
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

        chat = MagicMock()
        chat.custom_name = "Empty Chat"
        chat.title = "Test"
        chat.chat_type = MagicMock(value="hr")
        chat.id = 1
        chat.org_id = 1
        chat.owner_id = 1
        chat.messages = []  # No messages

        context = await service._build_entity_context(entity, [chat], [])

        assert "Empty Chat" in context
        assert "(нет сообщений)" in context

    async def test_build_context_with_none_optional_fields(self):
        """Test context building with None values in optional fields."""
        service = EntityAIService()

        entity = MagicMock()
        entity.name = "Test"
        entity.type = MagicMock(value="candidate")
        entity.status = MagicMock(value="active")
        entity.company = None
        entity.position = None
        entity.email = None
        entity.phone = None
        entity.tags = None  # None instead of []
        entity.ai_summary = None
        entity.key_events = None

        context = await service._build_entity_context(entity, [], [])

        # Should handle None gracefully
        assert "Test" in context
        assert "Не указана" in context  # For None company
        assert "Не указан" in context   # For None email

    async def test_build_context_call_without_optional_fields(self):
        """Test building context with call missing optional fields."""
        service = EntityAIService()

        entity = MagicMock()
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

        call = MagicMock()
        call.created_at = None  # No date
        call.title = None       # No title
        call.duration_seconds = None  # No duration
        call.summary = None
        call.key_points = None
        call.transcript = None

        context = await service._build_entity_context(entity, [], [call])

        # Should handle None values
        assert "ЗВОНКИ:" in context
        assert "дата неизвестна" in context or "Звонок" in context

    async def test_build_context_limits_key_points(self):
        """Test that only first 10 key points are included."""
        service = EntityAIService()

        entity = MagicMock()
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

        call = MagicMock()
        call.created_at = datetime(2025, 1, 1)
        call.title = "Call"
        call.duration_seconds = 600
        call.summary = None
        call.key_points = [f"Point {i}" for i in range(20)]  # 20 points
        call.transcript = None

        context = await service._build_entity_context(entity, [], [call])

        # Should include first 10 points
        assert "Point 0" in context
        assert "Point 9" in context
        # Should not include points beyond 10
        assert "Point 10" not in context
        assert "Point 19" not in context
