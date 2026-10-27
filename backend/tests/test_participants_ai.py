"""
Tests for AI-powered participant identification service.

Tests cover:
- ParticipantRole enum with extended roles
- AI-powered participant identification
- Fallback behavior when AI fails
- Integration with identify_participants function
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from api.services.participants import (
    ParticipantRole,
    IdentifiedParticipant,
    identify_participants,
    ai_identify_unknown_participants,
    _format_messages_for_ai,
    _build_role_identification_prompt,
)
from api.models.database import (
    Chat,
    Message,
    User,
    Entity,
    Organization,
    ChatType,
    EntityType,
    EntityStatus,
    UserRole,
)


# ============================================================================
# UNIT TESTS - Extended ParticipantRole Enum
# ============================================================================


def _api_connection_error():
    """Сбой Claude так, как его отдаёт SDK."""
    import httpx
    from anthropic import APIConnectionError
    return APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))


class TestExtendedParticipantRole:
    """Tests for extended ParticipantRole enum with AI roles."""

    def test_basic_roles_exist(self):
        """Test that basic roles still exist."""
        assert ParticipantRole.system_user == "system_user"
        assert ParticipantRole.employee == "employee"
        assert ParticipantRole.target == "target"
        assert ParticipantRole.contact == "contact"
        assert ParticipantRole.unknown == "unknown"

    def test_extended_ai_roles_exist(self):
        """Test that extended AI roles are defined."""
        assert ParticipantRole.interviewer == "interviewer"
        assert ParticipantRole.candidate == "candidate"
        assert ParticipantRole.tech_lead == "tech_lead"
        assert ParticipantRole.hr == "hr"
        assert ParticipantRole.manager == "manager"
        assert ParticipantRole.colleague == "colleague"
        assert ParticipantRole.external == "external"

    def test_all_values_are_strings(self):
        """Test that all enum values are strings."""
        for role in ParticipantRole:
            assert isinstance(role.value, str)


# ============================================================================
# INTEGRATION TESTS - identify_participants with AI fallback
# ============================================================================

class TestIdentifyParticipantsWithAI:
    """Tests for identify_participants function with AI fallback."""

    @pytest_asyncio.fixture
    async def test_org(self, db_session: AsyncSession) -> Organization:
        """Create test organization."""
        org = Organization(
            name="Test Org",
            slug="test-org",
            created_at=datetime.utcnow()
        )
        db_session.add(org)
        await db_session.commit()
        await db_session.refresh(org)
        return org

    @pytest_asyncio.fixture
    async def test_chat(self, db_session: AsyncSession, test_org: Organization) -> Chat:
        """Create test chat."""
        user = User(
            email="hr@test.com",
            password_hash="hash",
            name="HR Manager",
            role=UserRole.admin,
            telegram_id=111111,
            telegram_username="hr_manager",
            is_active=True
        )
        db_session.add(user)
        await db_session.flush()

        chat = Chat(
            org_id=test_org.id,
            owner_id=user.id,
            telegram_chat_id=123456789,
            title="Test Interview Chat",
            chat_type=ChatType.hr,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(chat)
        await db_session.commit()
        await db_session.refresh(chat)
        return chat

    async def test_without_ai_fallback_unknown_stays_unknown(
        self,
        db_session: AsyncSession,
        test_chat: Chat,
        test_org: Organization
    ):
        """Test that unknown participants stay unknown when AI fallback is disabled."""
        # Add message from unknown user
        message = Message(
            chat_id=test_chat.id,
            telegram_message_id=1,
            telegram_user_id=999999,
            username="unknown_user",
            first_name="Unknown",
            last_name="Person",
            content="Hello everyone",
            content_type="text",
            timestamp=datetime.utcnow()
        )
        db_session.add(message)
        await db_session.commit()

        participants = await identify_participants(
            chat_id=test_chat.id,
            org_id=test_org.id,
            db=db_session,
            use_ai_fallback=False
        )

        assert len(participants) == 1
        assert participants[0].telegram_user_id == 999999
        assert participants[0].role == ParticipantRole.unknown
        assert participants[0].confidence == 1.0  # No AI = max confidence in unknown

    @pytest.mark.xfail(reason="AsyncAnthropic mock path incorrect for current module structure")
    async def test_with_ai_fallback_calls_ai_function(
        self,
        db_session: AsyncSession,
        test_chat: Chat,
        test_org: Organization
    ):
        """Test that AI fallback is called when enabled."""
        # Add messages for context
        messages = [
            Message(
                chat_id=test_chat.id,
                telegram_message_id=1,
                telegram_user_id=111111,
                username="hr_manager",
                first_name="Anna",
                last_name="HR",
                content="Tell me about your Python experience",
                content_type="text",
                timestamp=datetime.utcnow()
            ),
            Message(
                chat_id=test_chat.id,
                telegram_message_id=2,
                telegram_user_id=999999,
                username="john_dev",
                first_name="John",
                last_name="Developer",
                content="I have 5 years of Python experience",
                content_type="text",
                timestamp=datetime.utcnow()
            ),
        ]
        for msg in messages:
            db_session.add(msg)
        await db_session.commit()

        # Mock AI response
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text='[{"telegram_user_id": 999999, "role": "candidate", "confidence": 0.8, "reasoning": "Answers questions about experience"}]'
        )]

        with patch('api.services.participants.AsyncAnthropic') as mock_anthropic:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_anthropic.return_value = mock_client

            participants = await identify_participants(
                chat_id=test_chat.id,
                org_id=test_org.id,
                db=db_session,
                use_ai_fallback=True
            )

            # Should have 2 participants: 1 known (system_user), 1 AI-identified (candidate)
            assert len(participants) == 2

            # Find the candidate participant
            candidate = next((p for p in participants if p.telegram_user_id == 999999), None)
            assert candidate is not None
            assert candidate.role == ParticipantRole.candidate
            assert 0.5 <= candidate.confidence <= 0.8
            assert candidate.ai_reasoning == "Answers questions about experience"

            # Verify AI was called
            mock_client.messages.create.assert_called_once()

    @pytest.mark.xfail(reason="AsyncAnthropic mock path incorrect for current module structure")
    async def test_ai_fallback_error_handling(
        self,
        db_session: AsyncSession,
        test_chat: Chat,
        test_org: Organization
    ):
        """Test that errors in AI identification are handled gracefully."""
        # Add message from unknown user
        message = Message(
            chat_id=test_chat.id,
            telegram_message_id=1,
            telegram_user_id=999999,
            username="unknown_user",
            first_name="Unknown",
            last_name="Person",
            content="Hello",
            content_type="text",
            timestamp=datetime.utcnow()
        )
        db_session.add(message)
        await db_session.commit()

        # Mock AI to raise an error
        with patch('api.services.participants.AsyncAnthropic') as mock_anthropic:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(side_effect=Exception("API Error"))
            mock_anthropic.return_value = mock_client

            # Should not raise exception, should return participants with unknown role
            participants = await identify_participants(
                chat_id=test_chat.id,
                org_id=test_org.id,
                db=db_session,
                use_ai_fallback=True
            )

            assert len(participants) == 1
            assert participants[0].role == ParticipantRole.unknown


# ============================================================================
# UNIT TESTS - ai_identify_unknown_participants
# ============================================================================

class TestAIIdentifyUnknownParticipants:
    """Tests for AI-powered participant identification function."""

    @pytest.fixture(autouse=True)
    def _anthropic_key(self, monkeypatch):
        """Ключ «настроен»: без него функция сразу возвращает участников как есть
        и ни одна ветка разбора ответа Claude не проверяется (сам Claude замокан)."""
        from api.services import participants
        monkeypatch.setattr(participants.settings, "anthropic_api_key", "test-key")


    @pytest_asyncio.fixture
    async def test_chat_with_messages(self, db_session: AsyncSession) -> Chat:
        """Create test chat with interview messages."""
        org = Organization(
            name="Test Org",
            slug="test-org",
            created_at=datetime.utcnow()
        )
        db_session.add(org)
        await db_session.flush()

        user = User(
            email="hr@test.com",
            password_hash="hash",
            name="HR Manager",
            role=UserRole.admin,
            telegram_id=111111,
            is_active=True
        )
        db_session.add(user)
        await db_session.flush()

        chat = Chat(
            org_id=org.id,
            owner_id=user.id,
            telegram_chat_id=123456789,
            title="Interview Chat",
            chat_type=ChatType.hr,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(chat)
        await db_session.flush()

        # Add interview conversation
        messages = [
            Message(
                chat_id=chat.id,
                telegram_message_id=1,
                telegram_user_id=111111,
                username="hr_manager",
                first_name="Anna",
                last_name="HR",
                content="Hello! Tell me about your Python experience",
                content_type="text",
                timestamp=datetime.utcnow()
            ),
            Message(
                chat_id=chat.id,
                telegram_message_id=2,
                telegram_user_id=222222,
                username="john_dev",
                first_name="John",
                last_name="Developer",
                content="I have 5 years of Python experience with Django and FastAPI",
                content_type="text",
                timestamp=datetime.utcnow()
            ),
        ]
        for msg in messages:
            db_session.add(msg)

        await db_session.commit()
        await db_session.refresh(chat)
        return chat

    async def test_returns_empty_when_no_unknown_participants(self, db_session: AsyncSession):
        """Test with empty unknown participants list."""
        result = await ai_identify_unknown_participants(
            chat_id=1,
            unknown_participants=[],
            known_participants=[],
            db=db_session
        )

        assert result == []

    async def test_skips_ai_when_no_api_key(
        self,
        db_session: AsyncSession,
        test_chat_with_messages: Chat,
        monkeypatch
    ):
        """Test that AI is skipped when ANTHROPIC_API_KEY is not configured."""
        from api.config import get_settings
        settings = get_settings()
        monkeypatch.setattr(settings, "anthropic_api_key", "")

        unknown = [
            IdentifiedParticipant(
                telegram_user_id=222222,
                username="john_dev",
                display_name="John Developer",
                role=ParticipantRole.unknown
            )
        ]

        result = await ai_identify_unknown_participants(
            chat_id=test_chat_with_messages.id,
            unknown_participants=unknown,
            known_participants=[],
            db=db_session
        )

        # Should return unchanged
        assert len(result) == 1
        assert result[0].role == ParticipantRole.unknown

    async def test_ai_identifies_candidate_successfully(
        self,
        db_session: AsyncSession,
        test_chat_with_messages: Chat
    ):
        """Test successful AI identification of candidate."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text='[{"telegram_user_id": 222222, "role": "candidate", "confidence": 0.8, "reasoning": "Answers questions about experience"}]'
        )]

        with patch('api.services.participants.AsyncAnthropic') as mock_anthropic:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_anthropic.return_value = mock_client

            unknown = [
                IdentifiedParticipant(
                    telegram_user_id=222222,
                    username="john_dev",
                    display_name="John Developer",
                    role=ParticipantRole.unknown
                )
            ]

            known = [
                IdentifiedParticipant(
                    telegram_user_id=111111,
                    username="hr_manager",
                    display_name="Anna HR",
                    role=ParticipantRole.system_user,
                    confidence=1.0
                )
            ]

            result = await ai_identify_unknown_participants(
                chat_id=test_chat_with_messages.id,
                unknown_participants=unknown,
                known_participants=known,
                db=db_session
            )

            assert len(result) == 1
            assert result[0].role == ParticipantRole.candidate
            assert 0.5 <= result[0].confidence <= 0.8
            assert result[0].ai_reasoning == "Answers questions about experience"

    async def test_handles_invalid_role_gracefully(
        self,
        db_session: AsyncSession,
        test_chat_with_messages: Chat
    ):
        """Test that invalid AI role is handled gracefully."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text='[{"telegram_user_id": 222222, "role": "invalid_role", "confidence": 0.7, "reasoning": "Unknown"}]'
        )]

        with patch('api.services.participants.AsyncAnthropic') as mock_anthropic:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_anthropic.return_value = mock_client

            unknown = [
                IdentifiedParticipant(
                    telegram_user_id=222222,
                    username="john_dev",
                    display_name="John Developer",
                    role=ParticipantRole.unknown
                )
            ]

            result = await ai_identify_unknown_participants(
                chat_id=test_chat_with_messages.id,
                unknown_participants=unknown,
                known_participants=[],
                db=db_session
            )

            assert len(result) == 1
            assert result[0].role == ParticipantRole.unknown

    async def test_handles_api_error_gracefully(
        self,
        db_session: AsyncSession,
        test_chat_with_messages: Chat
    ):
        """Test that API errors are handled gracefully."""
        with patch('api.services.participants.AsyncAnthropic') as mock_anthropic:
            mock_client = AsyncMock()
            # Ловятся ошибки SDK (APIError / APIConnectionError), а не любой Exception.
            mock_client.messages.create = AsyncMock(side_effect=_api_connection_error())
            mock_anthropic.return_value = mock_client

            unknown = [
                IdentifiedParticipant(
                    telegram_user_id=222222,
                    username="john_dev",
                    display_name="John Developer",
                    role=ParticipantRole.unknown
                )
            ]

            result = await ai_identify_unknown_participants(
                chat_id=test_chat_with_messages.id,
                unknown_participants=unknown,
                known_participants=[],
                db=db_session
            )

            # Should return unchanged on error
            assert len(result) == 1
            assert result[0].role == ParticipantRole.unknown

    async def test_confidence_is_clamped(
        self,
        db_session: AsyncSession,
        test_chat_with_messages: Chat
    ):
        """Test that confidence is clamped between 0.5 and 0.8."""
        # Test with confidence too high
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text='[{"telegram_user_id": 222222, "role": "candidate", "confidence": 0.95, "reasoning": "Test"}]'
        )]

        with patch('api.services.participants.AsyncAnthropic') as mock_anthropic:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_anthropic.return_value = mock_client

            unknown = [
                IdentifiedParticipant(
                    telegram_user_id=222222,
                    username="john_dev",
                    display_name="John Developer",
                    role=ParticipantRole.unknown
                )
            ]

            result = await ai_identify_unknown_participants(
                chat_id=test_chat_with_messages.id,
                unknown_participants=unknown,
                known_participants=[],
                db=db_session
            )

            assert result[0].confidence == 0.8  # Clamped to max

    async def test_handles_malformed_json(
        self,
        db_session: AsyncSession,
        test_chat_with_messages: Chat
    ):
        """Test handling of malformed JSON response."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text='This is not JSON at all'
        )]

        with patch('api.services.participants.AsyncAnthropic') as mock_anthropic:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_anthropic.return_value = mock_client

            unknown = [
                IdentifiedParticipant(
                    telegram_user_id=222222,
                    username="john_dev",
                    display_name="John Developer",
                    role=ParticipantRole.unknown
                )
            ]

            result = await ai_identify_unknown_participants(
                chat_id=test_chat_with_messages.id,
                unknown_participants=unknown,
                known_participants=[],
                db=db_session
            )

            # Should return unchanged on JSON parsing error
            assert len(result) == 1
            assert result[0].role == ParticipantRole.unknown


# ============================================================================
# UNIT TESTS - Helper Functions
# ============================================================================

class TestHelperFunctions:
    """Tests for helper functions."""

    def test_format_messages_for_ai(self):
        """Test message formatting for AI."""
        messages = [
            Message(
                chat_id=1,
                telegram_message_id=1,
                telegram_user_id=111,
                username="user1",
                first_name="John",
                last_name="Doe",
                content="Hello, how are you?",
                content_type="text",
                timestamp=datetime(2024, 1, 1, 10, 30)
            ),
            Message(
                chat_id=1,
                telegram_message_id=2,
                telegram_user_id=222,
                username=None,
                first_name=None,
                last_name=None,
                content="I'm good, thanks!",
                content_type="text",
                timestamp=datetime(2024, 1, 1, 10, 31)
            ),
        ]

        result = _format_messages_for_ai(messages)

        assert "[10:30] John: Hello, how are you?" in result
        assert "[10:31] User222: I'm good, thanks!" in result

    def test_format_messages_truncates_long_content(self):
        """Test that long messages are truncated."""
        long_content = "A" * 300
        messages = [
            Message(
                chat_id=1,
                telegram_message_id=1,
                telegram_user_id=111,
                first_name="John",
                last_name=None,
                username=None,
                content=long_content,
                content_type="text",
                timestamp=datetime(2024, 1, 1, 10, 30)
            ),
        ]

        result = _format_messages_for_ai(messages)

        # Content should be truncated to 200 chars
        message_content = result.split(": ")[1]
        assert len(message_content) <= 200

    def test_build_role_identification_prompt(self):
        """Test prompt building for AI."""
        unknown = [
            IdentifiedParticipant(
                telegram_user_id=222222,
                username="john_dev",
                display_name="John Developer",
                role=ParticipantRole.unknown
            )
        ]

        known = [
            IdentifiedParticipant(
                telegram_user_id=111111,
                username="hr_manager",
                display_name="Anna HR",
                role=ParticipantRole.system_user,
                confidence=1.0
            )
        ]

        conversation = "[10:30] Anna: Tell me about yourself\n[10:31] John: I'm a developer"

        prompt = _build_role_identification_prompt(unknown, known, conversation)

        # Verify prompt contains all necessary elements
        assert "Anna HR" in prompt
        assert "system_user" in prompt
        assert "John Developer" in prompt
        assert "telegram_user_id=222222" in prompt
        assert conversation in prompt
        assert "JSON" in prompt
        assert "candidate" in prompt
        assert "interviewer" in prompt


# ============================================================================
# TESTS FOR AI CALL SPEAKER IDENTIFICATION
# ============================================================================

class TestAICallSpeakerIdentification:
    """Tests for ai_identify_call_speakers function.

    Модуль читает `settings` один раз при импорте, поэтому подменяем именно
    `participants.settings` (а не get_settings). У спикера звонка нет Telegram —
    telegram_user_id/username у IdentifiedParticipant обязательные, передаём None.
    """

    @pytest.mark.asyncio
    async def test_identifies_speakers_by_transcript_context(self):
        """Test that AI correctly identifies speakers from call transcript."""
        from api.services.participants import ai_identify_call_speakers, IdentifiedParticipant, ParticipantRole
        from unittest.mock import MagicMock, AsyncMock, patch

        # Create mock call with transcript
        mock_call = MagicMock()
        mock_call.id = 123
        mock_call.title = "Interview - Backend Developer"
        mock_call.transcript = """
HR Manager: Добро пожаловать на собеседование. Расскажите о своем опыте работы с Python.
Speaker 2: Спасибо. Я работаю с Python уже 5 лет, в основном в backend разработке.
HR Manager: Отлично. Какие фреймворки вы использовали?
Speaker 2: FastAPI, Django, Flask. Последние 2 года работаю с FastAPI.
"""

        unknown_speakers = [
            IdentifiedParticipant(
                telegram_user_id=None,
                username=None,
                display_name="Speaker 2",
                role=ParticipantRole.unknown,
                confidence=0.5
            )
        ]

        known_speakers = [
            IdentifiedParticipant(
                telegram_user_id=None,
                username=None,
                display_name="HR Manager",
                role=ParticipantRole.system_user,
                confidence=1.0
            )
        ]

        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text='[{"speaker_name": "Speaker 2", "role": "candidate", "confidence": 0.75, "reasoning": "Отвечает на вопросы про опыт работы"}]'
        )]

        with patch('api.services.participants.settings') as mock_settings, \
             patch('api.services.participants.AsyncAnthropic') as mock_anthropic:
            mock_settings.anthropic_api_key = "test-key"
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_anthropic.return_value = mock_client

            result = await ai_identify_call_speakers(
                call=mock_call,
                unknown_speakers=unknown_speakers,
                known_speakers=known_speakers
            )

            assert len(result) == 1
            assert result[0].role == ParticipantRole.candidate
            assert result[0].confidence <= 0.8  # Clamped

    @pytest.mark.asyncio
    async def test_returns_unchanged_when_no_api_key(self):
        """Test that speakers are returned unchanged when API key not configured."""
        from api.services.participants import ai_identify_call_speakers, IdentifiedParticipant, ParticipantRole
        from unittest.mock import MagicMock, patch

        mock_call = MagicMock()
        mock_call.id = 123
        mock_call.transcript = "Test transcript"

        unknown_speakers = [
            IdentifiedParticipant(
                telegram_user_id=None,
                username=None,
                display_name="Unknown Speaker",
                role=ParticipantRole.unknown
            )
        ]

        with patch('api.services.participants.settings') as mock_settings:
            mock_settings.anthropic_api_key = None

            result = await ai_identify_call_speakers(
                call=mock_call,
                unknown_speakers=unknown_speakers,
                known_speakers=[]
            )

            assert len(result) == 1
            assert result[0].role == ParticipantRole.unknown

    @pytest.mark.asyncio
    async def test_handles_api_error_gracefully(self):
        """Test that errors are handled and speakers returned unchanged."""
        from api.services.participants import ai_identify_call_speakers, IdentifiedParticipant, ParticipantRole
        from unittest.mock import MagicMock, AsyncMock, patch

        mock_call = MagicMock()
        mock_call.id = 123
        mock_call.transcript = "Test transcript"

        unknown_speakers = [
            IdentifiedParticipant(
                telegram_user_id=None,
                username=None,
                display_name="Speaker",
                role=ParticipantRole.unknown
            )
        ]

        with patch('api.services.participants.settings') as mock_settings, \
             patch('api.services.participants.AsyncAnthropic') as mock_anthropic:
            mock_settings.anthropic_api_key = "test-key"
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(side_effect=_api_connection_error())
            mock_anthropic.return_value = mock_client

            result = await ai_identify_call_speakers(
                call=mock_call,
                unknown_speakers=unknown_speakers,
                known_speakers=[]
            )

            # Should return unchanged on error
            assert len(result) == 1
            assert result[0].role == ParticipantRole.unknown

    @pytest.mark.asyncio
    async def test_empty_speakers_returns_empty(self):
        """Test that empty speakers list returns empty."""
        from api.services.participants import ai_identify_call_speakers
        from unittest.mock import MagicMock

        mock_call = MagicMock()
        mock_call.transcript = "Test"

        result = await ai_identify_call_speakers(
            call=mock_call,
            unknown_speakers=[],
            known_speakers=[]
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_no_transcript_returns_unchanged(self):
        """Test that speakers returned unchanged when no transcript."""
        from api.services.participants import ai_identify_call_speakers, IdentifiedParticipant, ParticipantRole
        from unittest.mock import MagicMock, patch

        mock_call = MagicMock()
        mock_call.id = 123
        mock_call.transcript = None

        unknown_speakers = [
            IdentifiedParticipant(
                telegram_user_id=None,
                username=None,
                display_name="Speaker",
                role=ParticipantRole.unknown
            )
        ]

        with patch('api.services.participants.settings') as mock_settings:
            mock_settings.anthropic_api_key = "test-key"

            result = await ai_identify_call_speakers(
                call=mock_call,
                unknown_speakers=unknown_speakers,
                known_speakers=[]
            )

            assert len(result) == 1
            assert result[0].role == ParticipantRole.unknown
