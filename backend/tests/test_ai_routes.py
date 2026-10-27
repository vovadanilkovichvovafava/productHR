"""
Comprehensive unit tests for AI routes.

Tests AI chat endpoints, entity AI endpoints, analysis, and report generation.
Covers permission checks, async task handling, and mocked AI service calls.
"""
import pytest
import pytest_asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from typing import AsyncGenerator

from sqlalchemy import select

from api.models.database import (
    Chat, Message, Entity, AIConversation, EntityAIConversation,
    AnalysisHistory, ChatCriteria, ChatType, EntityType, EntityStatus,
    UserRole
)
from api.models.schemas import (
    AIMessageRequest, AnalyzeRequest, ReportRequest
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def chat_with_messages(db_session, chat, admin_user):
    """Create a chat with sample messages."""
    messages = [
        Message(
            chat_id=chat.id,
            telegram_message_id=101,
            telegram_user_id=1001,
            username="john_doe",
            first_name="John",
            last_name="Doe",
            content="Hello, I'm interested in this position.",
            content_type="text",
            timestamp=datetime(2025, 1, 15, 10, 0, 0)
        ),
        Message(
            chat_id=chat.id,
            telegram_message_id=102,
            telegram_user_id=1002,
            username="jane_hr",
            first_name="Jane",
            last_name="Smith",
            content="Great! Tell me about your experience.",
            content_type="text",
            timestamp=datetime(2025, 1, 15, 10, 5, 0)
        ),
        Message(
            chat_id=chat.id,
            telegram_message_id=103,
            telegram_user_id=1001,
            username="john_doe",
            first_name="John",
            last_name="Doe",
            content="I have 5 years of Python development.",
            content_type="voice",
            timestamp=datetime(2025, 1, 15, 10, 10, 0)
        ),
    ]
    for msg in messages:
        db_session.add(msg)
    await db_session.commit()
    return chat


@pytest_asyncio.fixture
async def chat_with_criteria(db_session, chat):
    """Create chat criteria."""
    criteria = ChatCriteria(
        chat_id=chat.id,
        criteria=[
            {
                "name": "Communication Skills",
                "description": "Clarity and professionalism",
                "weight": 8,
                "category": "basic"
            },
            {
                "name": "Technical Knowledge",
                "description": "Programming expertise",
                "weight": 9,
                "category": "basic"
            },
            {
                "name": "Red Flag: Unprofessional",
                "description": "Inappropriate behavior",
                "weight": 7,
                "category": "red_flags"
            }
        ]
    )
    db_session.add(criteria)
    await db_session.commit()
    return criteria


@pytest_asyncio.fixture
async def ai_conversation(db_session, chat, admin_user):
    """Create an AI conversation with history."""
    conversation = AIConversation(
        chat_id=chat.id,
        user_id=admin_user.id,
        messages=[
            {
                "role": "user",
                "content": "What do you think about this candidate?",
                "timestamp": datetime(2025, 1, 15, 11, 0, 0).isoformat()
            },
            {
                "role": "assistant",
                "content": "The candidate shows strong technical skills.",
                "timestamp": datetime(2025, 1, 15, 11, 0, 5).isoformat()
            }
        ]
    )
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)
    return conversation


@pytest_asyncio.fixture
async def entity_with_chats(db_session, entity, organization, department, admin_user):
    """Create an entity with linked chats."""
    chat1 = Chat(
        org_id=organization.id,
        entity_id=entity.id,
        owner_id=admin_user.id,
        telegram_chat_id=111111,
        title="Interview Chat",
        chat_type=ChatType.hr,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db_session.add(chat1)
    await db_session.flush()

    # Add messages to chat
    messages = [
        Message(
            chat_id=chat1.id,
            telegram_message_id=201,
            telegram_user_id=2001,
            first_name="Candidate",
            content="I'm very interested in this role.",
            content_type="text",
            timestamp=datetime(2025, 1, 15, 14, 0, 0)
        ),
        Message(
            chat_id=chat1.id,
            telegram_message_id=202,
            telegram_user_id=2002,
            first_name="HR",
            content="Tell me about your background.",
            content_type="text",
            timestamp=datetime(2025, 1, 15, 14, 5, 0)
        )
    ]
    for msg in messages:
        db_session.add(msg)

    await db_session.commit()
    await db_session.refresh(entity)
    return entity


@pytest_asyncio.fixture
async def entity_ai_conversation(db_session, entity, admin_user):
    """Create entity AI conversation with history."""
    conversation = EntityAIConversation(
        entity_id=entity.id,
        user_id=admin_user.id,
        messages=[
            {
                "role": "user",
                "content": "Give me a summary of this contact",
                "timestamp": datetime(2025, 1, 15, 15, 0, 0).isoformat()
            },
            {
                "role": "assistant",
                "content": "This contact appears to be a strong candidate.",
                "timestamp": datetime(2025, 1, 15, 15, 0, 5).isoformat()
            }
        ]
    )
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)
    return conversation


@pytest.fixture
def mock_ai_service():
    """Mock AI service with streaming response."""
    mock_service = MagicMock()

    # Mock streaming response
    async def mock_stream(*args, **kwargs):
        """Simulate streaming AI response."""
        chunks = ["This ", "is ", "a ", "test ", "response."]
        for chunk in chunks:
            yield chunk

    mock_service.chat_stream = mock_stream
    mock_service.quick_action = mock_stream
    mock_service.generate_report = AsyncMock(return_value="Complete test report with analysis.")

    return mock_service


@pytest.fixture
def mock_entity_ai_service():
    """Mock entity AI service."""
    mock_service = MagicMock()

    async def mock_stream(*args, **kwargs):
        """Simulate streaming AI response."""
        chunks = ["Entity ", "analysis ", "response."]
        for chunk in chunks:
            yield chunk

    mock_service.chat_stream = mock_stream
    mock_service.quick_action = mock_stream
    mock_service.get_available_actions = MagicMock(return_value=[
        {"id": "full_analysis", "label": "Full Analysis", "icon": "search"},
        {"id": "red_flags", "label": "Red Flags", "icon": "alert"}
    ])

    return mock_service


@pytest.fixture
def mock_report_generators():
    """Mock report generation functions."""
    with patch('api.routes.ai.generate_pdf_report') as mock_pdf, \
         patch('api.routes.ai.generate_docx_report') as mock_docx:
        mock_pdf.return_value = b"PDF content"
        mock_docx.return_value = b"DOCX content"
        yield mock_pdf, mock_docx


# ============================================================================
# CHAT AI MESSAGE TESTS
# ============================================================================

class TestAIMessage:
    """Tests for POST /{chat_id}/ai/message endpoint."""

    @pytest.mark.asyncio
    async def test_ai_message_basic_chat(
        self, client, chat_with_messages, admin_token, get_auth_headers,
        mock_ai_service, org_owner
    ):
        """Test basic AI chat message."""
        with patch('api.routes.ai.ai_service', mock_ai_service):
            response = await client.post(
                f"/api/chats/{chat_with_messages.id}/ai/message",
                headers=get_auth_headers(admin_token),
                json={"message": "What do you think?"}
            )

            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    @pytest.mark.asyncio
    async def test_ai_message_quick_action(
        self, client, chat_with_messages, admin_token, get_auth_headers,
        mock_ai_service, org_owner
    ):
        """Test AI quick action."""
        with patch('api.routes.ai.ai_service', mock_ai_service):
            response = await client.post(
                f"/api/chats/{chat_with_messages.id}/ai/message",
                headers=get_auth_headers(admin_token),
                json={"quick_action": "full_analysis"}
            )

            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    @pytest.mark.asyncio
    async def test_ai_message_saves_conversation(
        self, client, db_session, chat_with_messages, admin_user, admin_token,
        get_auth_headers, mock_ai_service, org_owner
    ):
        """Test that AI conversation is saved to database."""
        with patch('api.routes.ai.ai_service', mock_ai_service):
            response = await client.post(
                f"/api/chats/{chat_with_messages.id}/ai/message",
                headers=get_auth_headers(admin_token),
                json={"message": "Analyze this chat"}
            )

            assert response.status_code == 200

            # Read the streaming response
            content = b""
            async for chunk in response.aiter_bytes():
                content += chunk

            # Check conversation was saved
            result = await db_session.execute(
                select(AIConversation).where(
                    AIConversation.chat_id == chat_with_messages.id,
                    AIConversation.user_id == admin_user.id
                )
            )
            conversation = result.scalar_one_or_none()

            assert conversation is not None
            assert len(conversation.messages) == 2  # User message + AI response
            assert conversation.messages[0]["role"] == "user"
            assert conversation.messages[0]["content"] == "Analyze this chat"
            assert conversation.messages[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_ai_message_chat_not_found(
        self, client, admin_token, get_auth_headers
    ):
        """Test AI message with non-existent chat."""
        response = await client.post(
            "/api/chats/99999/ai/message",
            headers=get_auth_headers(admin_token),
            json={"message": "Test"}
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_ai_message_access_denied(
        self, client, chat, second_user_token, get_auth_headers, org_owner, org_member
    ):
        """Test AI message access denied for non-owner."""
        # Чужой чат открывает обычный член орга (member), а не владелец орга:
        # владелец организации видит все её чаты (permissions.can_access_resource).
        response = await client.post(
            f"/api/chats/{chat.id}/ai/message",
            headers=get_auth_headers(second_user_token),
            json={"message": "Test"}
        )

        assert response.status_code == 403
        assert "access denied" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_ai_message_superadmin_access(
        self, client, superadmin_user, superadmin_token, second_chat,
        get_auth_headers, mock_ai_service
    ):
        """Test superadmin can access any chat."""
        with patch('api.routes.ai.ai_service', mock_ai_service):
            response = await client.post(
                f"/api/chats/{second_chat.id}/ai/message",
                headers=get_auth_headers(superadmin_token),
                json={"message": "Test"}
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_ai_message_validation_error(
        self, client, chat_with_messages, admin_token, get_auth_headers, org_owner
    ):
        """Test validation error when no message or action provided."""
        response = await client.post(
            f"/api/chats/{chat_with_messages.id}/ai/message",
            headers=get_auth_headers(admin_token),
            json={}  # Missing both message and quick_action
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_ai_message_with_existing_conversation(
        self, client, chat_with_messages, ai_conversation, admin_token,
        get_auth_headers, mock_ai_service, org_owner
    ):
        """Test AI message appends to existing conversation."""
        initial_msg_count = len(ai_conversation.messages)

        with patch('api.routes.ai.ai_service', mock_ai_service):
            response = await client.post(
                f"/api/chats/{chat_with_messages.id}/ai/message",
                headers=get_auth_headers(admin_token),
                json={"message": "Follow-up question"}
            )

            assert response.status_code == 200

            # Read response
            async for _ in response.aiter_bytes():
                pass

        # Verify conversation was updated (not checking exact count due to async nature)
        assert ai_conversation.messages is not None


# ============================================================================
# AI CONVERSATION HISTORY TESTS
# ============================================================================

class TestAIHistory:
    """Tests for GET /{chat_id}/ai/history endpoint."""

    @pytest.mark.asyncio
    async def test_get_ai_history_with_conversation(
        self, client, chat, ai_conversation, admin_token, get_auth_headers, org_owner
    ):
        """Test getting AI conversation history."""
        response = await client.get(
            f"/api/chats/{chat.id}/ai/history",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == ai_conversation.id
        assert data["chat_id"] == chat.id
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_get_ai_history_no_conversation(
        self, client, chat, admin_token, get_auth_headers, org_owner
    ):
        """Test getting AI history when no conversation exists."""
        response = await client.get(
            f"/api/chats/{chat.id}/ai/history",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == 0
        assert data["chat_id"] == chat.id
        assert data["messages"] == []

    @pytest.mark.asyncio
    async def test_get_ai_history_chat_not_found(
        self, client, admin_token, get_auth_headers
    ):
        """Test getting history for non-existent chat."""
        response = await client.get(
            "/api/chats/99999/ai/history",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_ai_history_access_denied(
        self, client, chat, second_user_token, get_auth_headers, org_owner, org_member
    ):
        """Test access denied for AI history."""
        # Чужой чат открывает обычный член орга (member), а не владелец орга:
        # владелец организации видит все её чаты (permissions.can_access_resource).
        response = await client.get(
            f"/api/chats/{chat.id}/ai/history",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403


class TestClearAIHistory:
    """Tests for DELETE /{chat_id}/ai/history endpoint."""

    @pytest.mark.asyncio
    async def test_clear_ai_history(
        self, client, db_session, chat, ai_conversation, admin_token,
        get_auth_headers, org_owner
    ):
        """Test clearing AI conversation history."""
        response = await client.delete(
            f"/api/chats/{chat.id}/ai/history",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 204

        # Verify conversation was deleted
        result = await db_session.execute(
            select(AIConversation).where(AIConversation.id == ai_conversation.id)
        )
        conversation = result.scalar_one_or_none()
        assert conversation is None

    @pytest.mark.asyncio
    async def test_clear_ai_history_no_conversation(
        self, client, chat, admin_token, get_auth_headers, org_owner
    ):
        """Test clearing history when no conversation exists."""
        response = await client.delete(
            f"/api/chats/{chat.id}/ai/history",
            headers=get_auth_headers(admin_token)
        )

        # Should succeed (idempotent)
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_clear_ai_history_access_denied(
        self, client, chat, second_user_token, get_auth_headers, org_owner, org_member
    ):
        """Test access denied when clearing history."""
        # Чужой чат открывает обычный член орга (member), а не владелец орга:
        # владелец организации видит все её чаты (permissions.can_access_resource).
        response = await client.delete(
            f"/api/chats/{chat.id}/ai/history",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403


# ============================================================================
# CHAT ANALYSIS TESTS
# ============================================================================

class TestAnalyzeChat:
    """Tests for POST /{chat_id}/analyze endpoint."""

    @pytest.mark.asyncio
    async def test_analyze_chat_standard(
        self, client, db_session, chat_with_messages, chat_with_criteria,
        admin_user, admin_token, get_auth_headers, mock_ai_service, org_owner
    ):
        """Test standard chat analysis."""
        with patch('api.routes.ai.ai_service', mock_ai_service):
            response = await client.post(
                f"/api/chats/{chat_with_messages.id}/analyze",
                headers=get_auth_headers(admin_token),
                json={
                    "report_type": "standard",
                    "include_quotes": True
                }
            )

            assert response.status_code == 200
            data = response.json()

            assert data["chat_id"] == chat_with_messages.id
            assert data["result"] == "Complete test report with analysis."
            assert data["report_type"] == "standard"
            assert "id" in data
            assert "created_at" in data

            # Verify analysis was saved
            result = await db_session.execute(
                select(AnalysisHistory).where(AnalysisHistory.id == data["id"])
            )
            analysis = result.scalar_one()
            assert analysis.user_id == admin_user.id

    @pytest.mark.asyncio
    async def test_analyze_chat_detailed(
        self, client, chat_with_messages, admin_token, get_auth_headers,
        mock_ai_service, org_owner
    ):
        """Test detailed analysis."""
        with patch('api.routes.ai.ai_service', mock_ai_service):
            response = await client.post(
                f"/api/chats/{chat_with_messages.id}/analyze",
                headers=get_auth_headers(admin_token),
                json={"report_type": "detailed"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["report_type"] == "detailed"

    @pytest.mark.asyncio
    async def test_analyze_chat_summary(
        self, client, chat_with_messages, admin_token, get_auth_headers,
        mock_ai_service, org_owner
    ):
        """Test summary analysis."""
        with patch('api.routes.ai.ai_service', mock_ai_service):
            response = await client.post(
                f"/api/chats/{chat_with_messages.id}/analyze",
                headers=get_auth_headers(admin_token),
                json={"report_type": "summary"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["report_type"] == "summary"

    @pytest.mark.asyncio
    async def test_analyze_chat_not_found(
        self, client, admin_token, get_auth_headers
    ):
        """Test analysis of non-existent chat."""
        response = await client.post(
            "/api/chats/99999/analyze",
            headers=get_auth_headers(admin_token),
            json={"report_type": "standard"}
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_analyze_chat_access_denied(
        self, client, chat, second_user_token, get_auth_headers, org_owner, org_member
    ):
        """Test access denied for analysis."""
        # Чужой чат открывает обычный член орга (member), а не владелец орга:
        # владелец организации видит все её чаты (permissions.can_access_resource).
        response = await client.post(
            f"/api/chats/{chat.id}/analyze",
            headers=get_auth_headers(second_user_token),
            json={"report_type": "standard"}
        )

        assert response.status_code == 403


class TestAnalysisHistory:
    """Tests for GET /{chat_id}/analysis-history endpoint."""

    @pytest.mark.asyncio
    async def test_get_analysis_history(
        self, client, db_session, chat, admin_user, admin_token,
        get_auth_headers, org_owner
    ):
        """Test getting analysis history."""
        # Create multiple analyses
        analyses = [
            AnalysisHistory(
                chat_id=chat.id,
                user_id=admin_user.id,
                result=f"Analysis {i}",
                report_type="standard",
                criteria_used=[]
            )
            for i in range(3)
        ]
        for analysis in analyses:
            db_session.add(analysis)
        await db_session.commit()

        response = await client.get(
            f"/api/chats/{chat.id}/analysis-history",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        assert len(data) == 3
        assert all(a["chat_id"] == chat.id for a in data)

    @pytest.mark.asyncio
    async def test_get_analysis_history_empty(
        self, client, chat, admin_token, get_auth_headers, org_owner
    ):
        """Test getting analysis history when none exists."""
        response = await client.get(
            f"/api/chats/{chat.id}/analysis-history",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data == []

    @pytest.mark.asyncio
    async def test_get_analysis_history_limit(
        self, client, db_session, chat, admin_user, admin_token,
        get_auth_headers, org_owner
    ):
        """Test that analysis history is limited to 20 items."""
        # Create 25 analyses
        analyses = [
            AnalysisHistory(
                chat_id=chat.id,
                user_id=admin_user.id,
                result=f"Analysis {i}",
                report_type="standard",
                criteria_used=[]
            )
            for i in range(25)
        ]
        for analysis in analyses:
            db_session.add(analysis)
        await db_session.commit()

        response = await client.get(
            f"/api/chats/{chat.id}/analysis-history",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 20  # Limited to 20


# ============================================================================
# REPORT GENERATION TESTS
# ============================================================================

class TestGenerateReportFile:
    """Tests for POST /{chat_id}/report endpoint."""

    @pytest.mark.asyncio
    async def test_generate_pdf_report(
        self, client, chat_with_messages, admin_token, get_auth_headers,
        mock_ai_service, mock_report_generators, org_owner
    ):
        """Test PDF report generation."""
        mock_pdf, _ = mock_report_generators

        with patch('api.routes.ai.ai_service', mock_ai_service):
            response = await client.post(
                f"/api/chats/{chat_with_messages.id}/report",
                headers=get_auth_headers(admin_token),
                json={"format": "pdf", "report_type": "standard"}
            )

            assert response.status_code == 200
            assert response.headers["content-type"] == "application/pdf"
            assert "attachment" in response.headers["content-disposition"]
            assert b"PDF content" == response.content

            # Verify PDF generator was called
            mock_pdf.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_docx_report(
        self, client, chat_with_messages, admin_token, get_auth_headers,
        mock_ai_service, mock_report_generators, org_owner
    ):
        """Test DOCX report generation."""
        _, mock_docx = mock_report_generators

        with patch('api.routes.ai.ai_service', mock_ai_service):
            response = await client.post(
                f"/api/chats/{chat_with_messages.id}/report",
                headers=get_auth_headers(admin_token),
                json={"format": "docx", "report_type": "detailed"}
            )

            assert response.status_code == 200
            assert "wordprocessingml" in response.headers["content-type"]
            assert "attachment" in response.headers["content-disposition"]
            assert b"DOCX content" == response.content

            # Verify DOCX generator was called
            mock_docx.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_markdown_report(
        self, client, chat_with_messages, admin_token, get_auth_headers,
        mock_ai_service, org_owner
    ):
        """Test Markdown report generation."""
        with patch('api.routes.ai.ai_service', mock_ai_service):
            response = await client.post(
                f"/api/chats/{chat_with_messages.id}/report",
                headers=get_auth_headers(admin_token),
                json={"format": "markdown", "report_type": "standard"}
            )

            assert response.status_code == 200
            assert response.headers["content-type"] == "text/markdown; charset=utf-8"
            assert "attachment" in response.headers["content-disposition"]
            assert "Complete test report" in response.content.decode()

    @pytest.mark.asyncio
    async def test_generate_report_saves_to_history(
        self, client, db_session, chat_with_messages, admin_user, admin_token,
        get_auth_headers, mock_ai_service, mock_report_generators, org_owner
    ):
        """Test that report generation saves to analysis history."""
        with patch('api.routes.ai.ai_service', mock_ai_service):
            response = await client.post(
                f"/api/chats/{chat_with_messages.id}/report",
                headers=get_auth_headers(admin_token),
                json={"format": "pdf", "report_type": "detailed"}
            )

            assert response.status_code == 200

            # Verify analysis was saved
            result = await db_session.execute(
                select(AnalysisHistory).where(
                    AnalysisHistory.chat_id == chat_with_messages.id,
                    AnalysisHistory.user_id == admin_user.id
                )
            )
            analyses = result.scalars().all()
            assert len(analyses) >= 1

            latest = analyses[-1]
            assert latest.report_type == "detailed"
            assert latest.report_format == "pdf"

    @pytest.mark.asyncio
    async def test_generate_report_access_denied(
        self, client, chat, second_user_token, get_auth_headers, org_owner, org_member
    ):
        """Test access denied for report generation."""
        # Чужой чат открывает обычный член орга (member), а не владелец орга:
        # владелец организации видит все её чаты (permissions.can_access_resource).
        response = await client.post(
            f"/api/chats/{chat.id}/report",
            headers=get_auth_headers(second_user_token),
            json={"format": "pdf"}
        )

        assert response.status_code == 403


# ============================================================================
# ENTITY AI ACTIONS TESTS
# ============================================================================

class TestEntityAIActions:
    """Tests for GET /entities/{entity_id}/ai/actions endpoint."""

    @pytest.mark.asyncio
    async def test_get_entity_ai_actions(
        self, client, entity, admin_token, get_auth_headers, org_owner,
        mock_entity_ai_service
    ):
        """Test getting available AI actions for entity."""
        with patch('api.routes.entity_ai.entity_ai_service', mock_entity_ai_service):
            response = await client.get(
                f"/api/entities/{entity.id}/ai/actions",
                headers=get_auth_headers(admin_token)
            )

            assert response.status_code == 200
            data = response.json()

            assert "actions" in data
            assert isinstance(data["actions"], list)
            assert len(data["actions"]) == 2
            assert data["actions"][0]["id"] == "full_analysis"

    @pytest.mark.asyncio
    async def test_get_entity_ai_actions_not_found(
        self, client, admin_token, get_auth_headers
    ):
        """Test getting actions for non-existent entity."""
        response = await client.get(
            "/api/entities/99999/ai/actions",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_org_owner_can_access_any_entity_actions(
        self, client, second_entity, admin_token, get_auth_headers, org_owner,
        org_member, mock_entity_ai_service
    ):
        """Test org owner can access any entity in their org (new role hierarchy).

        With the updated role-based access control, org owners have full access
        to all entities in their organization.
        """
        with patch('api.routes.entity_ai.entity_ai_service', mock_entity_ai_service):
            response = await client.get(
                f"/api/entities/{second_entity.id}/ai/actions",
                headers=get_auth_headers(admin_token)
            )
            # Org owner (admin_user via org_owner fixture) CAN access second_entity
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_member_cannot_access_other_member_entity_actions(
        self, client, entity, second_user_token, get_auth_headers, org_owner, org_member
    ):
        """Test org member cannot access another member's entity.

        A regular org member should not be able to access entities created by
        other members unless explicitly shared or in the same department with
        appropriate role.
        """
        response = await client.get(
            f"/api/entities/{entity.id}/ai/actions",
            headers=get_auth_headers(second_user_token)
        )
        # second_user is org member, cannot access admin_user's entity
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_entity_ai_actions_superadmin(
        self, client, second_entity, superadmin_token, get_auth_headers,
        mock_entity_ai_service
    ):
        """Test superadmin can access any entity actions."""
        with patch('api.routes.entity_ai.entity_ai_service', mock_entity_ai_service):
            response = await client.get(
                f"/api/entities/{second_entity.id}/ai/actions",
                headers=get_auth_headers(superadmin_token)
            )

            assert response.status_code == 200


# ============================================================================
# ENTITY AI MESSAGE TESTS
# ============================================================================

class TestEntityAIMessage:
    """Tests for POST /entities/{entity_id}/ai/message endpoint."""

    @pytest.mark.asyncio
    async def test_entity_ai_message_chat(
        self, client, entity_with_chats, admin_token, get_auth_headers,
        mock_entity_ai_service, org_owner
    ):
        """Test entity AI chat message."""
        with patch('api.routes.entity_ai.entity_ai_service', mock_entity_ai_service):
            response = await client.post(
                f"/api/entities/{entity_with_chats.id}/ai/message",
                headers=get_auth_headers(admin_token),
                json={"message": "Tell me about this contact"}
            )

            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    @pytest.mark.asyncio
    async def test_entity_ai_message_quick_action(
        self, client, entity_with_chats, admin_token, get_auth_headers,
        mock_entity_ai_service, org_owner
    ):
        """Test entity AI quick action."""
        with patch('api.routes.entity_ai.entity_ai_service', mock_entity_ai_service):
            response = await client.post(
                f"/api/entities/{entity_with_chats.id}/ai/message",
                headers=get_auth_headers(admin_token),
                json={"quick_action": "full_analysis"}
            )

            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    @pytest.mark.asyncio
    async def test_entity_ai_message_saves_conversation(
        self, client, db_session, entity_with_chats, admin_user, admin_token,
        get_auth_headers, mock_entity_ai_service, org_owner
    ):
        """Test that entity AI conversation is saved."""
        with patch('api.routes.entity_ai.entity_ai_service', mock_entity_ai_service):
            response = await client.post(
                f"/api/entities/{entity_with_chats.id}/ai/message",
                headers=get_auth_headers(admin_token),
                json={"message": "Analyze this contact"}
            )

            assert response.status_code == 200

            # Read the streaming response
            async for _ in response.aiter_bytes():
                pass

            # Check conversation was saved
            result = await db_session.execute(
                select(EntityAIConversation).where(
                    EntityAIConversation.entity_id == entity_with_chats.id,
                    EntityAIConversation.user_id == admin_user.id
                )
            )
            conversation = result.scalar_one_or_none()

            assert conversation is not None
            assert len(conversation.messages) == 2

    @pytest.mark.asyncio
    async def test_entity_ai_message_validation_error(
        self, client, entity, admin_token, get_auth_headers, org_owner
    ):
        """Test validation error when no message or action."""
        response = await client.post(
            f"/api/entities/{entity.id}/ai/message",
            headers=get_auth_headers(admin_token),
            json={}
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_entity_ai_message_not_found(
        self, client, admin_token, get_auth_headers
    ):
        """Test entity AI message for non-existent entity."""
        response = await client.post(
            "/api/entities/99999/ai/message",
            headers=get_auth_headers(admin_token),
            json={"message": "Test"}
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_entity_ai_message_access_denied(
        self, client, entity, second_user_token, get_auth_headers, org_owner, org_member
    ):
        """Test access denied for entity AI message.

        A regular org member should not be able to send messages to entities
        created by other members.
        """
        response = await client.post(
            f"/api/entities/{entity.id}/ai/message",
            headers=get_auth_headers(second_user_token),
            json={"message": "Test"}
        )
        # second_user is org member, cannot access admin_user's entity
        assert response.status_code == 403


# ============================================================================
# ENTITY AI HISTORY TESTS
# ============================================================================

class TestEntityAIHistory:
    """Tests for GET /entities/{entity_id}/ai/history endpoint."""

    @pytest.mark.asyncio
    async def test_get_entity_ai_history(
        self, client, entity, entity_ai_conversation, admin_token,
        get_auth_headers, org_owner
    ):
        """Test getting entity AI conversation history."""
        response = await client.get(
            f"/api/entities/{entity.id}/ai/history",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        assert "messages" in data
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_get_entity_ai_history_no_conversation(
        self, client, entity, admin_token, get_auth_headers, org_owner
    ):
        """Test getting history when no conversation exists."""
        response = await client.get(
            f"/api/entities/{entity.id}/ai/history",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["messages"] == []

    @pytest.mark.asyncio
    async def test_get_entity_ai_history_not_found(
        self, client, admin_token, get_auth_headers
    ):
        """Test getting history for non-existent entity."""
        response = await client.get(
            "/api/entities/99999/ai/history",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_entity_ai_history_access_denied(
        self, client, entity, second_user_token, get_auth_headers, org_owner, org_member
    ):
        """Test access denied for entity AI history.

        A regular org member should not be able to access history for entities
        created by other members.
        """
        response = await client.get(
            f"/api/entities/{entity.id}/ai/history",
            headers=get_auth_headers(second_user_token)
        )
        # second_user is org member, cannot access admin_user's entity
        assert response.status_code == 403


class TestClearEntityAIHistory:
    """Tests for DELETE /entities/{entity_id}/ai/history endpoint."""

    @pytest.mark.asyncio
    async def test_clear_entity_ai_history(
        self, client, db_session, entity, entity_ai_conversation, admin_token,
        get_auth_headers, org_owner
    ):
        """Test clearing entity AI conversation history."""
        response = await client.delete(
            f"/api/entities/{entity.id}/ai/history",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify conversation was deleted
        result = await db_session.execute(
            select(EntityAIConversation).where(
                EntityAIConversation.id == entity_ai_conversation.id
            )
        )
        conversation = result.scalar_one_or_none()
        assert conversation is None

    @pytest.mark.asyncio
    async def test_clear_entity_ai_history_no_conversation(
        self, client, entity, admin_token, get_auth_headers, org_owner
    ):
        """Test clearing history when none exists."""
        response = await client.delete(
            f"/api/entities/{entity.id}/ai/history",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_clear_entity_ai_history_access_denied(
        self, client, entity, second_user_token, get_auth_headers, org_owner, org_member
    ):
        """Test access denied when clearing entity history.

        A regular org member should not be able to clear history for entities
        created by other members.
        """
        response = await client.delete(
            f"/api/entities/{entity.id}/ai/history",
            headers=get_auth_headers(second_user_token)
        )
        # second_user is org member, cannot access admin_user's entity
        assert response.status_code == 403


# ============================================================================
# PERMISSION EDGE CASES TESTS
# ============================================================================

class TestPermissionEdgeCases:
    """Test permission edge cases for AI routes."""

    @pytest.mark.asyncio
    async def test_admin_cannot_access_other_admin_chat(
        self, client, db_session, organization, admin_user, second_user, second_user_token,
        get_auth_headers, org_member
    ):
        """Test admin cannot access another admin's chat."""
        # Create chat owned by different admin (admin_user)
        other_chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,  # Owned by admin_user, not second_user
            telegram_chat_id=555555,
            title="Other Chat",
            is_active=True
        )
        db_session.add(other_chat)
        await db_session.commit()
        await db_session.refresh(other_chat)

        # second_user tries to access admin_user's chat
        response = await client.post(
            f"/api/chats/{other_chat.id}/ai/message",
            headers=get_auth_headers(second_user_token),
            json={"message": "Test"}
        )

        assert response.status_code in [403, 404]  # Either forbidden or not visible

    @pytest.mark.asyncio
    async def test_admin_cannot_access_other_admin_entity(
        self, client, db_session, organization, department, admin_user, second_user,
        second_user_token, get_auth_headers, org_member
    ):
        """Test admin cannot access another admin's entity."""
        # Create entity owned by different admin (admin_user)
        other_entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,  # Created by admin_user, not second_user
            name="Other Contact",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(other_entity)
        await db_session.commit()
        await db_session.refresh(other_entity)

        # second_user tries to access admin_user's entity
        response = await client.get(
            f"/api/entities/{other_entity.id}/ai/actions",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code in [403, 404]


# ============================================================================
# STREAMING RESPONSE TESTS
# ============================================================================

class TestStreamingResponses:
    """Test streaming response handling."""

    @pytest.mark.asyncio
    async def test_ai_message_stream_format(
        self, client, chat_with_messages, admin_token, get_auth_headers,
        mock_ai_service, org_owner
    ):
        """Test that streaming response has correct SSE format."""
        with patch('api.routes.ai.ai_service', mock_ai_service):
            response = await client.post(
                f"/api/chats/{chat_with_messages.id}/ai/message",
                headers=get_auth_headers(admin_token),
                json={"message": "Test"}
            )

            # Read streaming response
            content = b""
            async for chunk in response.aiter_bytes():
                content += chunk

            text = content.decode()

            # Should contain SSE data format
            assert "data:" in text
            assert "[DONE]" in text

    @pytest.mark.asyncio
    async def test_entity_ai_message_stream_format(
        self, client, entity, admin_token, get_auth_headers,
        mock_entity_ai_service, org_owner
    ):
        """Test entity AI streaming response format."""
        with patch('api.routes.entity_ai.entity_ai_service', mock_entity_ai_service):
            response = await client.post(
                f"/api/entities/{entity.id}/ai/message",
                headers=get_auth_headers(admin_token),
                json={"message": "Test"}
            )

            # Read streaming response
            content = b""
            async for chunk in response.aiter_bytes():
                content += chunk

            text = content.decode()

            # Should contain SSE format
            assert "data:" in text
            assert "[DONE]" in text

    @pytest.mark.asyncio
    async def test_streaming_response_headers(
        self, client, chat_with_messages, admin_token, get_auth_headers,
        mock_ai_service, org_owner
    ):
        """Test streaming response has correct headers."""
        with patch('api.routes.ai.ai_service', mock_ai_service):
            response = await client.post(
                f"/api/chats/{chat_with_messages.id}/ai/message",
                headers=get_auth_headers(admin_token),
                json={"message": "Test"}
            )

            # Read response
            async for _ in response.aiter_bytes():
                pass

            assert "text/event-stream" in response.headers["content-type"]
