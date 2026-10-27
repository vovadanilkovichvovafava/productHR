"""
Comprehensive unit tests for AI service.
Tests AI analysis functions, prompt generation, response parsing, and error handling.
"""
import pytest
import pytest_asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from typing import List

from api.services.ai import AIService, QUICK_ACTION_PROMPTS, ai_service
from api.models.database import Message


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_settings():
    """Mock settings with API key."""
    with patch('api.services.ai.settings') as mock_settings:
        mock_settings.anthropic_api_key = "test-api-key-12345"
        # Модель берётся из settings.claude_model (а не зашита в сервис).
        mock_settings.claude_model = "claude-sonnet-4-6"
        yield mock_settings


@pytest.fixture
def mock_settings_no_key():
    """Mock settings without API key."""
    with patch('api.services.ai.settings') as mock_settings:
        mock_settings.anthropic_api_key = None
        yield mock_settings


@pytest.fixture
def sample_messages() -> List[Message]:
    """Create sample messages for testing."""
    base_time = datetime(2025, 1, 15, 10, 0, 0)

    messages = [
        Message(
            id=1,
            chat_id=1,
            telegram_message_id=101,
            telegram_user_id=1001,
            username="john_doe",
            first_name="John",
            last_name="Doe",
            content="Hello, I'm interested in the position.",
            content_type="text",
            timestamp=base_time
        ),
        Message(
            id=2,
            chat_id=1,
            telegram_message_id=102,
            telegram_user_id=1002,
            username="jane_smith",
            first_name="Jane",
            last_name="Smith",
            content="Great! Can you tell me about your experience?",
            content_type="text",
            timestamp=datetime(2025, 1, 15, 10, 5, 0)
        ),
        Message(
            id=3,
            chat_id=1,
            telegram_message_id=103,
            telegram_user_id=1001,
            username="john_doe",
            first_name="John",
            last_name="Doe",
            content="I have 5 years of Python development experience.",
            content_type="voice",
            timestamp=datetime(2025, 1, 15, 10, 10, 0)
        ),
        Message(
            id=4,
            chat_id=1,
            telegram_message_id=104,
            telegram_user_id=1003,
            username=None,
            first_name="Bob",
            last_name=None,
            content="Here's my portfolio",
            content_type="document",
            file_name="portfolio.pdf",
            timestamp=datetime(2025, 1, 15, 10, 15, 0)
        ),
    ]

    return messages


@pytest.fixture
def sample_criteria() -> List[dict]:
    """Create sample criteria for testing."""
    return [
        {
            "name": "Communication Skills",
            "description": "Clarity and professionalism",
            "weight": 8,
            "category": "basic"
        },
        {
            "name": "Technical Knowledge",
            "description": "Demonstrated expertise",
            "weight": 9,
            "category": "basic"
        },
        {
            "name": "Red Flag: Inconsistencies",
            "description": "Contradictions in statements",
            "weight": 7,
            "category": "red_flags"
        },
        {
            "name": "Green Flag: Initiative",
            "description": "Proactive engagement",
            "weight": 6,
            "category": "green_flags"
        },
    ]


@pytest.fixture
def mock_anthropic_client():
    """Mock AsyncAnthropic client."""
    # Mock for non-streaming responses
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Complete test response with analysis.")]

    async def mock_text_stream():
        """Simulate streaming text chunks."""
        chunks = ["This ", "is ", "a ", "test ", "response."]
        for chunk in chunks:
            yield chunk

    # Function to create a fresh stream each time
    def create_stream(*args, **kwargs):
        """Create a fresh mock stream with a new generator."""
        mock_stream = MagicMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=None)
        mock_stream.text_stream = mock_text_stream()
        return mock_stream

    # Create the mock client with messages attribute
    mock_client = MagicMock()
    mock_client.messages = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)
    mock_client.messages.stream = MagicMock(side_effect=create_stream)

    return mock_client


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================

class TestAIServiceInitialization:
    """Tests for AIService initialization."""

    def test_init_creates_instance(self):
        """Test that AIService initializes correctly."""
        service = AIService()

        assert service._client is None
        assert service.model == "claude-sonnet-4-6"

    def test_client_property_lazy_loads(self, mock_settings):
        """Test that client property lazy loads AsyncAnthropic."""
        service = AIService()

        with patch('api.services.ai.AsyncAnthropic') as mock_anthropic:
            mock_anthropic.return_value = MagicMock()

            # First access should create client
            client = service.client

            assert client is not None
            mock_anthropic.assert_called_once_with(api_key="test-api-key-12345")

            # Second access should return same client
            client2 = service.client
            assert client2 is client
            mock_anthropic.assert_called_once()  # Still only called once

    def test_client_property_raises_without_api_key(self, mock_settings_no_key):
        """Test that client property raises error when API key is missing."""
        service = AIService()

        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY не настроен"):
            _ = service.client

    def test_singleton_instance_exists(self):
        """Test that ai_service singleton is available."""
        assert ai_service is not None
        assert isinstance(ai_service, AIService)


# ============================================================================
# MESSAGE FORMATTING TESTS
# ============================================================================

class TestFormatMessages:
    """Tests for _format_messages method."""

    def test_format_messages_basic(self, sample_messages):
        """Test basic message formatting."""
        service = AIService()
        result = service._format_messages(sample_messages[:2])

        # Format is now: [timestamp] Name: content (without username in parentheses)
        assert "[15.01 10:00] John Doe: Hello, I'm interested in the position." in result
        assert "[15.01 10:05] Jane Smith: Great! Can you tell me about your experience?" in result

    def test_format_messages_voice_prefix(self, sample_messages):
        """Test that voice messages have correct prefix."""
        service = AIService()
        result = service._format_messages([sample_messages[2]])

        # Voice prefix is [🎤]
        assert "[🎤]" in result
        assert "I have 5 years of Python development experience." in result

    def test_format_messages_document_prefix(self, sample_messages):
        """Test that documents have correct prefix with filename."""
        service = AIService()
        result = service._format_messages([sample_messages[3]])

        # Document prefix includes filename
        assert "[📄" in result and "portfolio.pdf" in result
        assert "Here's my portfolio" in result

    def test_format_messages_no_username(self, sample_messages):
        """Test formatting message without username."""
        service = AIService()
        result = service._format_messages([sample_messages[3]])

        # Should only have name, no @username
        assert "Bob:" in result
        assert "@" not in result

    def test_format_messages_content_types(self):
        """Test all supported content type prefixes."""
        service = AIService()

        messages = [
            Message(
                id=1, chat_id=1, telegram_user_id=1,
                first_name="Test", content="test",
                content_type="voice", timestamp=datetime(2025, 1, 1)
            ),
            Message(
                id=2, chat_id=1, telegram_user_id=1,
                first_name="Test", content="test",
                content_type="video_note", timestamp=datetime(2025, 1, 1)
            ),
            Message(
                id=3, chat_id=1, telegram_user_id=1,
                first_name="Test", content="test",
                content_type="photo", timestamp=datetime(2025, 1, 1)
            ),
            Message(
                id=4, chat_id=1, telegram_user_id=1,
                first_name="Test", content="test",
                content_type="text", timestamp=datetime(2025, 1, 1)
            ),
        ]

        result = service._format_messages(messages)

        # Updated format: shorter prefixes without Russian text
        assert "[🎤]" in result  # voice
        assert "[📹]" in result  # video_note
        # Photo is included only if it has text content
        # Text messages should not have a prefix
        lines = result.split('\n')
        text_line = [l for l in lines if "test" in l and "🎤" not in l and "📹" not in l]
        assert len(text_line) > 0

    def test_format_messages_empty_list(self):
        """Test formatting empty message list."""
        service = AIService()
        result = service._format_messages([])

        assert result == ""

    def test_format_messages_unknown_user(self):
        """Test formatting message with no name fields."""
        service = AIService()

        msg = Message(
            id=1, chat_id=1, telegram_user_id=1,
            first_name=None, last_name=None, username=None,
            content="Anonymous message", content_type="text",
            timestamp=datetime(2025, 1, 1, 12, 0)
        )

        result = service._format_messages([msg])

        # When no name/username, shows "?" as fallback
        assert "?:" in result
        assert "Anonymous message" in result


# ============================================================================
# CRITERIA FORMATTING TESTS
# ============================================================================

class TestFormatCriteria:
    """Tests for _format_criteria method."""

    def test_format_criteria_basic(self, sample_criteria):
        """Test basic criteria formatting."""
        service = AIService()
        result = service._format_criteria(sample_criteria)

        assert "Критерии оценки" in result
        assert "Communication Skills | 8/10 | Clarity and professionalism" in result
        assert "Technical Knowledge | 9/10 | Demonstrated expertise" in result

    def test_format_criteria_with_emojis(self, sample_criteria):
        """Test criteria formatting includes category emojis."""
        service = AIService()
        result = service._format_criteria(sample_criteria)

        # Red flags should have 🚩
        assert "🚩 Red Flag: Inconsistencies" in result

        # Green flags should have ✅
        assert "✅ Green Flag: Initiative" in result

        # Basic criteria should have 📋
        assert "📋 Communication Skills" in result

    def test_format_criteria_empty_list(self):
        """Test formatting empty criteria list."""
        service = AIService()
        result = service._format_criteria([])

        assert result == ""

    def test_format_criteria_missing_fields(self):
        """Test formatting criteria with missing optional fields."""
        service = AIService()

        criteria = [
            {"name": "Test Criterion"},  # Missing weight, description, category
        ]

        result = service._format_criteria(criteria)

        # Should use defaults: weight=5, description="", category uses default emoji
        assert "Test Criterion | 5/10 |" in result
        assert "📋" in result

    def test_format_criteria_unknown_category(self):
        """Test criteria with unknown category gets default emoji."""
        service = AIService()

        criteria = [
            {
                "name": "Custom Criterion",
                "weight": 7,
                "description": "Some description",
                "category": "unknown_category"
            }
        ]

        result = service._format_criteria(criteria)

        assert "📋 Custom Criterion" in result


# ============================================================================
# SYSTEM PROMPT BUILDING TESTS
# ============================================================================

class TestBuildSystemPrompt:
    """Tests for _build_system_prompt method."""

    def test_build_system_prompt_hr_type(self, sample_messages, sample_criteria):
        """Test building system prompt for HR chat type."""
        service = AIService()

        result = service._build_system_prompt(
            chat_title="Candidate Interview",
            messages=sample_messages,
            criteria=sample_criteria,
            chat_type="hr"
        )

        assert "HR expert analyzing candidate conversations" in result
        assert "Candidate Interview" in result
        assert "Communication Skills" in result
        # Переписка теперь в теге <chat_transcript> (защита от prompt injection),
        # а не под заголовком «ПЕРЕПИСКА:».
        assert "<chat_transcript>" in result
        assert "John Doe" in result
        assert "ПРАВИЛА:" in result

    def test_build_system_prompt_custom_type(self, sample_messages, sample_criteria):
        """Test building system prompt for custom chat type with description."""
        service = AIService()

        custom_desc = "Analyze team collaboration and productivity"

        result = service._build_system_prompt(
            chat_title="Team Chat",
            messages=sample_messages,
            criteria=sample_criteria,
            chat_type="custom",
            custom_description=custom_desc
        )

        assert custom_desc in result
        assert "Team Chat" in result

    def test_build_system_prompt_all_chat_types(self, sample_messages):
        """Test that system prompt can be built for all chat types."""
        service = AIService()

        chat_types = ["hr", "project", "client", "contractor", "sales", "support", "custom"]

        for chat_type in chat_types:
            result = service._build_system_prompt(
                chat_title=f"Test {chat_type}",
                messages=sample_messages,
                criteria=[],
                chat_type=chat_type
            )

            assert result is not None
            assert len(result) > 100
            assert f"Test {chat_type}" in result

    def test_build_system_prompt_includes_formatted_messages(self, sample_messages):
        """Test that system prompt includes formatted messages."""
        service = AIService()

        result = service._build_system_prompt(
            chat_title="Test Chat",
            messages=sample_messages,
            criteria=[],
            chat_type="hr"
        )

        # Should include formatted messages (without username in parentheses)
        assert "John Doe" in result
        assert "Hello, I'm interested in the position" in result
        assert "[🎤]" in result  # Voice message prefix

    def test_build_system_prompt_includes_criteria(self, sample_messages, sample_criteria):
        """Test that system prompt includes formatted criteria."""
        service = AIService()

        result = service._build_system_prompt(
            chat_title="Test Chat",
            messages=sample_messages,
            criteria=sample_criteria,
            chat_type="hr"
        )

        assert "Критерии оценки" in result
        assert "Communication Skills" in result
        assert "8/10" in result


# ============================================================================
# CHAT STREAM TESTS
# ============================================================================

class TestChatStream:
    """Tests for chat_stream method."""

    @pytest.mark.asyncio
    async def test_chat_stream_basic(self, mock_settings, mock_anthropic_client, sample_messages):
        """Test basic chat streaming functionality."""
        service = AIService()

        with patch.object(service, '_client', mock_anthropic_client):
            chunks = []
            async for chunk in service.chat_stream(
                user_message="Tell me about the candidates",
                chat_title="Interview",
                messages=sample_messages,
                criteria=[],
                conversation_history=[],
                chat_type="hr"
            ):
                chunks.append(chunk)

            # Should have received all chunks
            assert len(chunks) == 5
            assert "".join(chunks) == "This is a test response."

    @pytest.mark.asyncio
    async def test_chat_stream_with_conversation_history(self, mock_settings, mock_anthropic_client, sample_messages):
        """Test chat streaming with conversation history."""
        service = AIService()

        conversation_history = [
            {"role": "user", "content": "Previous question"},
            {"role": "assistant", "content": "Previous answer"}
        ]

        with patch.object(service, '_client', mock_anthropic_client):
            chunks = []
            async for chunk in service.chat_stream(
                user_message="Follow-up question",
                chat_title="Interview",
                messages=sample_messages,
                criteria=[],
                conversation_history=conversation_history,
                chat_type="hr"
            ):
                chunks.append(chunk)

            assert len(chunks) > 0

            # Verify API was called with correct messages
            mock_anthropic_client.messages.stream.assert_called_once()
            call_kwargs = mock_anthropic_client.messages.stream.call_args[1]

            # Should include history + new message
            assert len(call_kwargs['messages']) == 3
            assert call_kwargs['messages'][0]['content'] == "Previous question"
            assert call_kwargs['messages'][2]['content'] == "Follow-up question"

    @pytest.mark.asyncio
    async def test_chat_stream_model_parameters(self, mock_settings, mock_anthropic_client, sample_messages):
        """Test that chat stream uses correct model parameters."""
        service = AIService()

        with patch.object(service, '_client', mock_anthropic_client):
            async for _ in service.chat_stream(
                user_message="Test",
                chat_title="Test Chat",
                messages=sample_messages,
                criteria=[],
                conversation_history=[],
                chat_type="hr"
            ):
                pass

            call_kwargs = mock_anthropic_client.messages.stream.call_args[1]

            assert call_kwargs['model'] == "claude-sonnet-4-6"
            assert call_kwargs['max_tokens'] == 4096
            assert 'system' in call_kwargs
            assert 'messages' in call_kwargs


# ============================================================================
# QUICK ACTION TESTS
# ============================================================================

class TestQuickAction:
    """Tests for quick_action method."""

    @pytest.mark.asyncio
    async def test_quick_action_hr_full_analysis(self, mock_settings, mock_anthropic_client, sample_messages):
        """Test quick action for HR full analysis."""
        service = AIService()

        with patch.object(service, '_client', mock_anthropic_client):
            chunks = []
            async for chunk in service.quick_action(
                action="full_analysis",
                chat_title="Interview",
                messages=sample_messages,
                criteria=[],
                chat_type="hr"
            ):
                chunks.append(chunk)

            assert len(chunks) > 0

            # Verify the correct prompt was used
            call_kwargs = mock_anthropic_client.messages.stream.call_args[1]
            user_message = call_kwargs['messages'][0]['content']

            # Should include the HR full_analysis prompt
            assert "HR-анализ" in user_message or "Коммуникативные навыки" in user_message

    @pytest.mark.asyncio
    async def test_quick_action_project_blockers(self, mock_settings, mock_anthropic_client, sample_messages):
        """Test quick action for project blockers."""
        service = AIService()

        with patch.object(service, '_client', mock_anthropic_client):
            chunks = []
            async for chunk in service.quick_action(
                action="blockers",
                chat_title="Project Chat",
                messages=sample_messages,
                criteria=[],
                chat_type="project"
            ):
                chunks.append(chunk)

            assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_quick_action_fallback_to_other_types(self, mock_settings, mock_anthropic_client, sample_messages):
        """Test that quick action falls back to other types if action not found."""
        service = AIService()

        with patch.object(service, '_client', mock_anthropic_client):
            # Use "summary" action which exists in multiple types
            chunks = []
            async for chunk in service.quick_action(
                action="summary",
                chat_title="Test Chat",
                messages=sample_messages,
                criteria=[],
                chat_type="project"  # project doesn't have summary, should fallback
            ):
                chunks.append(chunk)

            assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_quick_action_unknown_action(self, mock_settings, mock_anthropic_client, sample_messages):
        """Test quick action with completely unknown action."""
        service = AIService()

        with patch.object(service, '_client', mock_anthropic_client):
            chunks = []
            async for chunk in service.quick_action(
                action="nonexistent_action_12345",
                chat_title="Test Chat",
                messages=sample_messages,
                criteria=[],
                chat_type="hr"
            ):
                chunks.append(chunk)

            # Should still work with default prompt
            assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_quick_action_all_hr_actions(self, mock_settings, mock_anthropic_client, sample_messages):
        """Test all HR quick actions work."""
        service = AIService()

        hr_actions = ["full_analysis", "red_flags", "strengths", "recommendation", "culture_fit"]

        for action in hr_actions:
            with patch.object(service, '_client', mock_anthropic_client):
                chunks = []
                async for chunk in service.quick_action(
                    action=action,
                    chat_title="Test",
                    messages=sample_messages,
                    criteria=[],
                    chat_type="hr"
                ):
                    chunks.append(chunk)

                assert len(chunks) > 0


# ============================================================================
# REPORT GENERATION TESTS
# ============================================================================

class TestGenerateReport:
    """Tests for generate_report method."""

    @pytest.mark.asyncio
    async def test_generate_report_standard(self, mock_settings, mock_anthropic_client, sample_messages, sample_criteria):
        """Test generating a standard report."""
        service = AIService()

        with patch.object(service, '_client', mock_anthropic_client):
            result = await service.generate_report(
                chat_title="Interview",
                messages=sample_messages,
                criteria=sample_criteria,
                report_type="standard",
                include_quotes=True,
                chat_type="hr"
            )

            assert result == "Complete test response with analysis."

            # Verify API call
            mock_anthropic_client.messages.create.assert_called_once()
            call_kwargs = mock_anthropic_client.messages.create.call_args[1]

            assert call_kwargs['model'] == "claude-sonnet-4-6"
            assert call_kwargs['max_tokens'] == 8192

    @pytest.mark.asyncio
    async def test_generate_report_quick(self, mock_settings, mock_anthropic_client, sample_messages):
        """Test generating a quick report."""
        service = AIService()

        with patch.object(service, '_client', mock_anthropic_client):
            result = await service.generate_report(
                chat_title="Interview",
                messages=sample_messages,
                criteria=[],
                report_type="quick",
                include_quotes=False,
                chat_type="hr"
            )

            assert result is not None

            call_kwargs = mock_anthropic_client.messages.create.call_args[1]
            prompt = call_kwargs['messages'][0]['content']

            # Should mention quick/brief style
            assert "Краткий" in prompt or "1 страницу" in prompt

    @pytest.mark.asyncio
    async def test_generate_report_detailed(self, mock_settings, mock_anthropic_client, sample_messages):
        """Test generating a detailed report."""
        service = AIService()

        with patch.object(service, '_client', mock_anthropic_client):
            result = await service.generate_report(
                chat_title="Interview",
                messages=sample_messages,
                criteria=[],
                report_type="detailed",
                include_quotes=True,
                chat_type="hr"
            )

            assert result is not None

            call_kwargs = mock_anthropic_client.messages.create.call_args[1]
            prompt = call_kwargs['messages'][0]['content']

            # Should mention detailed style
            assert "Подробный" in prompt

    @pytest.mark.asyncio
    async def test_generate_report_without_quotes(self, mock_settings, mock_anthropic_client, sample_messages):
        """Test generating report without quotes."""
        service = AIService()

        with patch.object(service, '_client', mock_anthropic_client):
            result = await service.generate_report(
                chat_title="Interview",
                messages=sample_messages,
                criteria=[],
                report_type="standard",
                include_quotes=False,
                chat_type="hr"
            )

            call_kwargs = mock_anthropic_client.messages.create.call_args[1]
            prompt = call_kwargs['messages'][0]['content']

            assert "Без цитат" in prompt

    @pytest.mark.asyncio
    async def test_generate_report_all_chat_types(self, mock_settings, mock_anthropic_client, sample_messages):
        """Test generating reports for all chat types."""
        service = AIService()

        chat_types = ["hr", "project", "client", "contractor", "sales", "support", "custom"]

        for chat_type in chat_types:
            with patch.object(service, '_client', mock_anthropic_client):
                result = await service.generate_report(
                    chat_title=f"Test {chat_type}",
                    messages=sample_messages,
                    criteria=[],
                    report_type="standard",
                    include_quotes=True,
                    chat_type=chat_type
                )

                assert result is not None

    @pytest.mark.asyncio
    async def test_generate_report_hr_structure(self, mock_settings, mock_anthropic_client, sample_messages):
        """Test that HR report includes correct structure."""
        service = AIService()

        with patch.object(service, '_client', mock_anthropic_client):
            await service.generate_report(
                chat_title="Interview",
                messages=sample_messages,
                criteria=[],
                report_type="standard",
                include_quotes=True,
                chat_type="hr"
            )

            call_kwargs = mock_anthropic_client.messages.create.call_args[1]
            prompt = call_kwargs['messages'][0]['content']

            # Should include HR-specific sections
            assert "РЕЗЮМЕ" in prompt
            assert "ОЦЕНКИ ПО КРИТЕРИЯМ" in prompt
            assert "RED FLAGS" in prompt
            assert "GREEN FLAGS" in prompt
            assert "РЕКОМЕНДАЦИИ" in prompt

    @pytest.mark.asyncio
    async def test_generate_report_project_structure(self, mock_settings, mock_anthropic_client, sample_messages):
        """Test that project report includes correct structure."""
        service = AIService()

        with patch.object(service, '_client', mock_anthropic_client):
            await service.generate_report(
                chat_title="Project",
                messages=sample_messages,
                criteria=[],
                report_type="standard",
                include_quotes=True,
                chat_type="project"
            )

            call_kwargs = mock_anthropic_client.messages.create.call_args[1]
            prompt = call_kwargs['messages'][0]['content']

            # Should include project-specific sections
            assert "СТАТУС ПРОЕКТА" in prompt
            assert "БЛОКЕРЫ И РИСКИ" in prompt
            assert "ACTION ITEMS" in prompt


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestErrorHandling:
    """Tests for error handling in AI service."""

    def test_missing_api_key_raises_error(self, mock_settings_no_key):
        """Test that missing API key raises appropriate error."""
        service = AIService()

        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY не настроен"):
            _ = service.client

    @pytest.mark.asyncio
    async def test_chat_stream_api_error(self, mock_settings, sample_messages):
        """Test error handling during chat stream."""
        service = AIService()

        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = Exception("API Error")

        with patch.object(service, '_client', mock_client):
            with pytest.raises(Exception, match="API Error"):
                async for _ in service.chat_stream(
                    user_message="Test",
                    chat_title="Test",
                    messages=sample_messages,
                    criteria=[],
                    conversation_history=[],
                    chat_type="hr"
                ):
                    pass

    @pytest.mark.asyncio
    async def test_generate_report_api_error(self, mock_settings, sample_messages):
        """Test error handling during report generation."""
        service = AIService()

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("API Error"))

        with patch.object(service, '_client', mock_client):
            with pytest.raises(Exception, match="API Error"):
                await service.generate_report(
                    chat_title="Test",
                    messages=sample_messages,
                    criteria=[],
                    report_type="standard",
                    include_quotes=True,
                    chat_type="hr"
                )

    @pytest.mark.asyncio
    async def test_empty_messages_handled(self, mock_settings, mock_anthropic_client):
        """Test that empty messages list is handled correctly."""
        service = AIService()

        with patch.object(service, '_client', mock_anthropic_client):
            chunks = []
            async for chunk in service.chat_stream(
                user_message="Analyze empty chat",
                chat_title="Empty Chat",
                messages=[],  # Empty messages
                criteria=[],
                conversation_history=[],
                chat_type="hr"
            ):
                chunks.append(chunk)

            # Should still work, just with no message content
            assert len(chunks) > 0


# ============================================================================
# QUICK ACTION PROMPTS TESTS
# ============================================================================

class TestQuickActionPrompts:
    """Tests for QUICK_ACTION_PROMPTS constant."""

    def test_quick_action_prompts_structure(self):
        """Test that QUICK_ACTION_PROMPTS has expected structure."""
        assert isinstance(QUICK_ACTION_PROMPTS, dict)

        # Check all expected chat types exist
        expected_types = ["work", "hr", "project", "client", "contractor", "sales", "support", "custom"]
        for chat_type in expected_types:
            assert chat_type in QUICK_ACTION_PROMPTS
            assert isinstance(QUICK_ACTION_PROMPTS[chat_type], dict)

    def test_hr_quick_action_prompts(self):
        """Test HR quick action prompts exist."""
        hr_prompts = QUICK_ACTION_PROMPTS["hr"]

        expected_actions = ["full_analysis", "red_flags", "strengths", "recommendation", "culture_fit"]
        for action in expected_actions:
            assert action in hr_prompts
            assert isinstance(hr_prompts[action], str)
            assert len(hr_prompts[action]) > 10

    def test_project_quick_action_prompts(self):
        """Test project quick action prompts exist."""
        project_prompts = QUICK_ACTION_PROMPTS["project"]

        expected_actions = ["project_status", "blockers", "responsibilities", "deadlines", "action_items"]
        for action in expected_actions:
            assert action in project_prompts
            assert isinstance(project_prompts[action], str)

    def test_all_prompts_are_russian(self):
        """Test that all prompts are in Russian."""
        for chat_type, actions in QUICK_ACTION_PROMPTS.items():
            for action_name, prompt in actions.items():
                # Check for Cyrillic characters (Russian)
                assert any(ord(char) >= 0x400 and ord(char) <= 0x4FF for char in prompt), \
                    f"Prompt for {chat_type}.{action_name} should be in Russian"

    def test_prompts_have_reasonable_length(self):
        """Test that prompts have reasonable length (not too short, not too long)."""
        for chat_type, actions in QUICK_ACTION_PROMPTS.items():
            for action_name, prompt in actions.items():
                # Prompts should be at least 20 chars and at most 2000 chars
                assert 20 <= len(prompt) <= 2000, \
                    f"Prompt for {chat_type}.{action_name} has unreasonable length: {len(prompt)}"


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """Integration tests combining multiple components."""

    @pytest.mark.asyncio
    async def test_full_workflow_chat_stream(self, mock_settings, mock_anthropic_client, sample_messages, sample_criteria):
        """Test complete workflow: create service, build prompt, stream response."""
        service = AIService()

        with patch.object(service, '_client', mock_anthropic_client):
            full_response = []
            async for chunk in service.chat_stream(
                user_message="Give me a detailed analysis of all candidates",
                chat_title="Technical Interview - Senior Python Developer",
                messages=sample_messages,
                criteria=sample_criteria,
                conversation_history=[],
                chat_type="hr",
                custom_description=None
            ):
                full_response.append(chunk)

            # Verify we got a complete response
            assert len(full_response) == 5
            assert "".join(full_response) == "This is a test response."

            # Verify the system prompt was built correctly
            call_kwargs = mock_anthropic_client.messages.stream.call_args[1]
            system_prompt = call_kwargs['system']

            # system_prompt is now a list with cache control, extract the text
            prompt_text = system_prompt[0]['text'] if isinstance(system_prompt, list) else system_prompt

            assert "HR expert" in prompt_text
            assert "Technical Interview - Senior Python Developer" in prompt_text
            assert "Communication Skills" in prompt_text
            assert "John Doe" in prompt_text

    @pytest.mark.asyncio
    async def test_full_workflow_quick_action(self, mock_settings, mock_anthropic_client, sample_messages, sample_criteria):
        """Test complete quick action workflow."""
        service = AIService()

        with patch.object(service, '_client', mock_anthropic_client):
            full_response = []
            async for chunk in service.quick_action(
                action="full_analysis",
                chat_title="Interview",
                messages=sample_messages,
                criteria=sample_criteria,
                chat_type="hr"
            ):
                full_response.append(chunk)

            assert len(full_response) > 0

    @pytest.mark.asyncio
    async def test_full_workflow_generate_report(self, mock_settings, mock_anthropic_client, sample_messages, sample_criteria):
        """Test complete report generation workflow."""
        service = AIService()

        with patch.object(service, '_client', mock_anthropic_client):
            report = await service.generate_report(
                chat_title="Candidate Evaluation",
                messages=sample_messages,
                criteria=sample_criteria,
                report_type="detailed",
                include_quotes=True,
                chat_type="hr"
            )

            assert report == "Complete test response with analysis."
            assert isinstance(report, str)
            assert len(report) > 0
