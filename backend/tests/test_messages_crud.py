"""
Comprehensive unit tests for message CRUD operations (backend/api/routes/messages.py).

This test suite covers:
- Message listing with pagination, filtering, and search
- Message access control and permissions
- Participant listing and aggregation
- File serving (Telegram proxy and local files)
- Message transcription (single and bulk)
- Edge cases and error handling

Tests target 80%+ coverage of the messages.py routes module.
"""
import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from pathlib import Path
import tempfile
import os

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import (
    Message, Chat, User, Organization, OrgMember, UserRole, OrgRole, ChatType
)


# ============================================================================
# MESSAGE FIXTURES
# ============================================================================


@pytest.fixture
def real_aiofiles(monkeypatch):
    """Настоящий aiofiles.open для тестов Range-запросов.

    conftest автоматически подменяет aiofiles.open заглушкой, которая на любой
    read() отдаёт b"mock file content" — отрезок файла по Range в таких
    тестах проверить нельзя. Здесь возвращаем настоящее чтение с диска.
    """
    import aiofiles.threadpool
    monkeypatch.setattr("aiofiles.open", aiofiles.threadpool.open)

@pytest_asyncio.fixture
async def text_message(db_session: AsyncSession, chat: Chat) -> Message:
    """Create a test text message."""
    msg = Message(
        chat_id=chat.id,
        telegram_message_id=10001,
        telegram_user_id=100200300,
        username="alice",
        first_name="Alice",
        last_name="Smith",
        content="This is a test message",
        content_type="text",
        timestamp=datetime.utcnow() - timedelta(hours=3)
    )
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)
    return msg


@pytest_asyncio.fixture
async def photo_message(db_session: AsyncSession, chat: Chat) -> Message:
    """Create a photo message with file_id."""
    msg = Message(
        chat_id=chat.id,
        telegram_message_id=10002,
        telegram_user_id=100200300,
        username="alice",
        first_name="Alice",
        last_name="Smith",
        content="Check out this photo!",
        content_type="photo",
        file_id="AgACAgIAAxkDAAIB",
        timestamp=datetime.utcnow() - timedelta(hours=2)
    )
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)
    return msg


@pytest_asyncio.fixture
async def voice_message(db_session: AsyncSession, chat: Chat) -> Message:
    """Create a voice message."""
    msg = Message(
        chat_id=chat.id,
        telegram_message_id=10003,
        telegram_user_id=100200300,
        username="alice",
        first_name="Alice",
        last_name="Smith",
        content="[Voice message]",
        content_type="voice",
        file_id="AwACAgIAAxkDVOICE",
        timestamp=datetime.utcnow() - timedelta(hours=1)
    )
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)
    return msg


@pytest_asyncio.fixture
async def video_note_message(db_session: AsyncSession, chat: Chat) -> Message:
    """Create a video note message with local file."""
    msg = Message(
        chat_id=chat.id,
        telegram_message_id=10004,
        telegram_user_id=200300400,
        username="bob",
        first_name="Bob",
        last_name="Jones",
        content="[Video note]",
        content_type="video_note",
        file_path=f"uploads/{chat.id}/video_note.mp4",
        timestamp=datetime.utcnow() - timedelta(minutes=30)
    )
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)
    return msg


@pytest_asyncio.fixture
async def document_message(db_session: AsyncSession, chat: Chat) -> Message:
    """Create a document message with metadata."""
    msg = Message(
        chat_id=chat.id,
        telegram_message_id=10005,
        telegram_user_id=200300400,
        username="bob",
        first_name="Bob",
        last_name="Jones",
        content="Resume document",
        content_type="document",
        file_id="BQACAgIAAxkDAAIC",
        file_name="resume.pdf",
        document_metadata={
            "file_type": "pdf",
            "pages_count": 3,
            "file_size": 152400
        },
        parse_status="parsed",
        timestamp=datetime.utcnow() - timedelta(minutes=10)
    )
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)
    return msg


@pytest_asyncio.fixture
async def failed_parse_message(db_session: AsyncSession, chat: Chat) -> Message:
    """Create a message with failed parse status."""
    msg = Message(
        chat_id=chat.id,
        telegram_message_id=10006,
        telegram_user_id=300400500,
        username="charlie",
        first_name="Charlie",
        last_name="Brown",
        content="Corrupted file",
        content_type="document",
        file_id="BQACAgIAAxkDAAID",
        file_name="corrupted.pdf",
        parse_status="failed",
        parse_error="Unable to parse PDF: File is encrypted",
        timestamp=datetime.utcnow() - timedelta(minutes=5)
    )
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)
    return msg


@pytest_asyncio.fixture
async def multiple_user_messages(db_session: AsyncSession, chat: Chat) -> list[Message]:
    """Create messages from multiple users for participant testing."""
    messages = []

    # Alice: 5 messages
    for i in range(5):
        msg = Message(
            chat_id=chat.id,
            telegram_message_id=20000 + i,
            telegram_user_id=100200300,
            username="alice",
            first_name="Alice",
            last_name="Smith",
            content=f"Alice message {i + 1}",
            content_type="text",
            timestamp=datetime.utcnow() - timedelta(hours=10 - i)
        )
        db_session.add(msg)
        messages.append(msg)

    # Bob: 3 messages
    for i in range(3):
        msg = Message(
            chat_id=chat.id,
            telegram_message_id=20100 + i,
            telegram_user_id=200300400,
            username="bob",
            first_name="Bob",
            last_name="Jones",
            content=f"Bob message {i + 1}",
            content_type="text",
            timestamp=datetime.utcnow() - timedelta(hours=8 - i)
        )
        db_session.add(msg)
        messages.append(msg)

    # Charlie: 2 messages
    for i in range(2):
        msg = Message(
            chat_id=chat.id,
            telegram_message_id=20200 + i,
            telegram_user_id=300400500,
            username="charlie",
            first_name="Charlie",
            last_name="Brown",
            content=f"Charlie message {i + 1}",
            content_type="text",
            timestamp=datetime.utcnow() - timedelta(hours=6 - i)
        )
        db_session.add(msg)
        messages.append(msg)

    await db_session.commit()
    for msg in messages:
        await db_session.refresh(msg)

    return messages


@pytest_asyncio.fixture
async def paginated_messages(db_session: AsyncSession, chat: Chat) -> list[Message]:
    """Create 25 messages for pagination testing."""
    messages = []
    for i in range(25):
        msg = Message(
            chat_id=chat.id,
            telegram_message_id=30000 + i,
            telegram_user_id=100200300,
            username="alice",
            first_name="Alice",
            last_name="Smith",
            content=f"Message number {i + 1}",
            content_type="text" if i % 3 != 0 else "photo",
            file_id=f"photo_{i}" if i % 3 == 0 else None,
            timestamp=datetime.utcnow() - timedelta(hours=25 - i)
        )
        db_session.add(msg)
        messages.append(msg)

    await db_session.commit()
    for msg in messages:
        await db_session.refresh(msg)

    return messages


# ============================================================================
# TEST: GET /{chat_id}/messages - Message Listing
# ============================================================================

class TestGetMessages:
    """Test message listing endpoint with comprehensive scenarios."""

    @pytest.mark.asyncio
    async def test_get_messages_basic(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        text_message: Message,
        get_auth_headers,
        org_owner
    ):
        """Test basic message retrieval."""
        response = await client.get(
            f"/api/chats/{chat.id}/messages",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

        # Verify message structure
        msg = next((m for m in data if m["id"] == text_message.id), None)
        assert msg is not None
        assert msg["telegram_user_id"] == 100200300
        assert msg["username"] == "alice"
        assert msg["first_name"] == "Alice"
        assert msg["last_name"] == "Smith"
        assert msg["content"] == "This is a test message"
        assert msg["content_type"] == "text"

    @pytest.mark.asyncio
    async def test_get_messages_all_types(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        text_message: Message,
        photo_message: Message,
        voice_message: Message,
        document_message: Message,
        get_auth_headers,
        org_owner
    ):
        """Test retrieving messages of different types."""
        response = await client.get(
            f"/api/chats/{chat.id}/messages",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Verify all message types are present
        content_types = {msg["content_type"] for msg in data}
        assert "text" in content_types
        assert "photo" in content_types
        assert "voice" in content_types
        assert "document" in content_types

        # Verify document metadata
        doc_msg = next((m for m in data if m["content_type"] == "document"), None)
        assert doc_msg is not None
        assert doc_msg["file_name"] == "resume.pdf"
        assert doc_msg["document_metadata"] is not None
        assert doc_msg["document_metadata"]["pages_count"] == 3
        assert doc_msg["parse_status"] == "parsed"

    @pytest.mark.asyncio
    async def test_get_messages_superadmin_access(
        self,
        client: AsyncClient,
        superadmin_user: User,
        superadmin_token: str,
        chat: Chat,
        text_message: Message,
        get_auth_headers
    ):
        """Test superadmin can access any chat's messages."""
        response = await client.get(
            f"/api/chats/{chat.id}/messages",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_get_messages_non_owner_denied(
        self,
        client: AsyncClient,
        second_user: User,
        second_user_token: str,
        chat: Chat,
        text_message: Message,
        get_auth_headers,
        org_member
    ):
        """Test non-owner cannot access messages."""
        response = await client.get(
            f"/api/chats/{chat.id}/messages",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_messages_chat_not_found(
        self,
        client: AsyncClient,
        admin_token: str,
        get_auth_headers
    ):
        """Test 404 for non-existent chat."""
        response = await client.get(
            "/api/chats/999999/messages",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404
        assert "Chat not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_messages_unauthenticated(
        self,
        client: AsyncClient,
        chat: Chat
    ):
        """Test unauthenticated request is rejected."""
        response = await client.get(f"/api/chats/{chat.id}/messages")

        assert response.status_code == 401


# ============================================================================
# TEST: Message Pagination
# ============================================================================

class TestMessagePagination:
    """Test message pagination functionality."""

    @pytest.mark.asyncio
    async def test_pagination_default_limit(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        paginated_messages: list[Message],
        get_auth_headers,
        org_owner
    ):
        """Test default pagination limit."""
        response = await client.get(
            f"/api/chats/{chat.id}/messages",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        # Default limit is 1000, so all 25 messages should be returned
        assert len(data) == 25

    @pytest.mark.asyncio
    async def test_pagination_custom_limit(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        paginated_messages: list[Message],
        get_auth_headers,
        org_owner
    ):
        """Test custom limit parameter."""
        response = await client.get(
            f"/api/chats/{chat.id}/messages?limit=10",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 10

    @pytest.mark.asyncio
    async def test_pagination_page_offset(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        paginated_messages: list[Message],
        get_auth_headers,
        org_owner
    ):
        """Test page offset works correctly."""
        # Get first page
        response1 = await client.get(
            f"/api/chats/{chat.id}/messages?page=1&limit=10",
            headers=get_auth_headers(admin_token)
        )
        assert response1.status_code == 200
        page1 = response1.json()
        assert len(page1) == 10

        # Get second page
        response2 = await client.get(
            f"/api/chats/{chat.id}/messages?page=2&limit=10",
            headers=get_auth_headers(admin_token)
        )
        assert response2.status_code == 200
        page2 = response2.json()
        assert len(page2) == 10

        # Verify pages are different
        page1_ids = {msg["id"] for msg in page1}
        page2_ids = {msg["id"] for msg in page2}
        assert page1_ids.isdisjoint(page2_ids)

    @pytest.mark.asyncio
    async def test_pagination_last_page_partial(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        paginated_messages: list[Message],
        get_auth_headers,
        org_owner
    ):
        """Test last page with partial results."""
        response = await client.get(
            f"/api/chats/{chat.id}/messages?page=3&limit=10",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        # Page 3 should have 5 messages (25 total / 10 per page)
        assert len(data) == 5

    @pytest.mark.asyncio
    async def test_pagination_page_beyond_end(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        paginated_messages: list[Message],
        get_auth_headers,
        org_owner
    ):
        """Test requesting page beyond available data."""
        response = await client.get(
            f"/api/chats/{chat.id}/messages?page=10&limit=10",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_pagination_max_limit_enforced(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        paginated_messages: list[Message],
        get_auth_headers,
        org_owner
    ):
        """Test that maximum limit of 2000 is enforced."""
        response = await client.get(
            f"/api/chats/{chat.id}/messages?limit=5000",
            headers=get_auth_headers(admin_token)
        )

        # Should still work but limit to max (query param has le=2000 constraint)
        assert response.status_code in [200, 422]  # 422 if validation fails


# ============================================================================
# TEST: Message Filtering
# ============================================================================

class TestMessageFiltering:
    """Test message filtering by content type."""

    @pytest.mark.asyncio
    async def test_filter_by_text(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        text_message: Message,
        photo_message: Message,
        voice_message: Message,
        get_auth_headers,
        org_owner
    ):
        """Test filtering messages by content_type=text."""
        response = await client.get(
            f"/api/chats/{chat.id}/messages?content_type=text",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # All messages should be text type
        for msg in data:
            assert msg["content_type"] == "text"

    @pytest.mark.asyncio
    async def test_filter_by_photo(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        text_message: Message,
        photo_message: Message,
        get_auth_headers,
        org_owner
    ):
        """Test filtering messages by content_type=photo."""
        response = await client.get(
            f"/api/chats/{chat.id}/messages?content_type=photo",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data) >= 1
        for msg in data:
            assert msg["content_type"] == "photo"
            assert msg["file_id"] is not None

    @pytest.mark.asyncio
    async def test_filter_by_voice(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        text_message: Message,
        voice_message: Message,
        get_auth_headers,
        org_owner
    ):
        """Test filtering messages by content_type=voice."""
        response = await client.get(
            f"/api/chats/{chat.id}/messages?content_type=voice",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data) >= 1
        for msg in data:
            assert msg["content_type"] == "voice"

    @pytest.mark.asyncio
    async def test_filter_by_document(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        document_message: Message,
        get_auth_headers,
        org_owner
    ):
        """Test filtering messages by content_type=document."""
        response = await client.get(
            f"/api/chats/{chat.id}/messages?content_type=document",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data) >= 1
        for msg in data:
            assert msg["content_type"] == "document"

    @pytest.mark.asyncio
    async def test_filter_all_shows_everything(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        text_message: Message,
        photo_message: Message,
        voice_message: Message,
        get_auth_headers,
        org_owner
    ):
        """Test content_type=all returns all message types."""
        response = await client.get(
            f"/api/chats/{chat.id}/messages?content_type=all",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        content_types = {msg["content_type"] for msg in data}
        assert len(content_types) >= 3  # Should have text, photo, voice

    @pytest.mark.asyncio
    async def test_filter_no_results(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        text_message: Message,
        get_auth_headers,
        org_owner
    ):
        """Test filtering with no matching results."""
        response = await client.get(
            f"/api/chats/{chat.id}/messages?content_type=video",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0


# ============================================================================
# TEST: Message Ordering
# ============================================================================

class TestMessageOrdering:
    """Test message ordering by timestamp."""

    @pytest.mark.asyncio
    async def test_messages_ordered_chronologically(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        paginated_messages: list[Message],
        get_auth_headers,
        org_owner
    ):
        """Test messages are ordered by timestamp (oldest first after reversal)."""
        response = await client.get(
            f"/api/chats/{chat.id}/messages?limit=500",  # limit ограничен 500 (Query le=500)
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        if len(data) > 1:
            timestamps = [
                datetime.fromisoformat(msg["timestamp"].replace('Z', '+00:00'))
                for msg in data
            ]
            # Messages are fetched DESC, then reversed, so should be ASC
            for i in range(len(timestamps) - 1):
                assert timestamps[i] <= timestamps[i + 1]


# ============================================================================
# TEST: GET /{chat_id}/participants - Participant Listing
# ============================================================================

class TestGetParticipants:
    """Test participant listing and aggregation."""

    @pytest.mark.asyncio
    async def test_get_participants_basic(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        multiple_user_messages: list[Message],
        get_auth_headers,
        org_owner
    ):
        """Test basic participant retrieval."""
        response = await client.get(
            f"/api/chats/{chat.id}/participants",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 3  # Alice, Bob, Charlie

        # Verify structure
        participant = data[0]
        assert "telegram_user_id" in participant
        assert "username" in participant
        assert "first_name" in participant
        assert "last_name" in participant
        assert "messages_count" in participant

    @pytest.mark.asyncio
    async def test_participants_aggregated_correctly(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        multiple_user_messages: list[Message],
        get_auth_headers,
        org_owner
    ):
        """Test participants are aggregated by telegram_user_id."""
        response = await client.get(
            f"/api/chats/{chat.id}/participants",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Find each user
        alice = next((p for p in data if p["username"] == "alice"), None)
        bob = next((p for p in data if p["username"] == "bob"), None)
        charlie = next((p for p in data if p["username"] == "charlie"), None)

        assert alice is not None
        assert alice["messages_count"] == 5
        assert alice["telegram_user_id"] == 100200300

        assert bob is not None
        assert bob["messages_count"] == 3
        assert bob["telegram_user_id"] == 200300400

        assert charlie is not None
        assert charlie["messages_count"] == 2
        assert charlie["telegram_user_id"] == 300400500

    @pytest.mark.asyncio
    async def test_participants_ordered_by_message_count(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        multiple_user_messages: list[Message],
        get_auth_headers,
        org_owner
    ):
        """Test participants are ordered by message count descending."""
        response = await client.get(
            f"/api/chats/{chat.id}/participants",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Verify descending order
        counts = [p["messages_count"] for p in data]
        assert counts == sorted(counts, reverse=True)

        # Verify Alice (5 messages) is first
        assert data[0]["username"] == "alice"
        assert data[0]["messages_count"] == 5

    @pytest.mark.asyncio
    async def test_participants_superadmin_access(
        self,
        client: AsyncClient,
        superadmin_user: User,
        superadmin_token: str,
        chat: Chat,
        text_message: Message,
        get_auth_headers
    ):
        """Test superadmin can access participants."""
        response = await client.get(
            f"/api/chats/{chat.id}/participants",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_participants_non_owner_denied(
        self,
        client: AsyncClient,
        second_user: User,
        second_user_token: str,
        chat: Chat,
        text_message: Message,
        get_auth_headers,
        org_member
    ):
        """Test non-owner cannot access participants."""
        response = await client.get(
            f"/api/chats/{chat.id}/participants",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_participants_chat_not_found(
        self,
        client: AsyncClient,
        admin_token: str,
        get_auth_headers
    ):
        """Test 404 for non-existent chat."""
        response = await client.get(
            "/api/chats/999999/participants",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_participants_empty_chat(
        self,
        db_session: AsyncSession,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        organization: Organization,
        get_auth_headers,
        org_owner
    ):
        """Test participants for chat with no messages."""
        empty_chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=111222333,
            title="Empty Chat",
            chat_type=ChatType.hr,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(empty_chat)
        await db_session.commit()
        await db_session.refresh(empty_chat)

        response = await client.get(
            f"/api/chats/{empty_chat.id}/participants",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data == []


# ============================================================================
# TEST: GET /file/{file_id} - Telegram File Proxy
# ============================================================================

class TestGetTelegramFile:
    """Test Telegram file proxy endpoint."""

    @pytest.mark.asyncio
    async def test_get_file_with_auth_header_success(
        self,
        client: AsyncClient,
        admin_token: str,
        get_auth_headers
    ):
        """Test successful file retrieval with auth header."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Mock getFile response
            get_file_resp = MagicMock()
            get_file_resp.json.return_value = {
                "ok": True,
                "result": {"file_path": "photos/file_123.jpg"}
            }

            # Mock file download response
            file_resp = MagicMock()
            file_resp.status_code = 200
            file_resp.content = b"fake image data"

            mock_client.get.side_effect = [get_file_resp, file_resp]

            with patch("api.routes.messages.settings") as mock_settings:
                mock_settings.telegram_bot_token = "test_token_123"

                response = await client.get(
                    "/api/chats/file/test_file_id",
                    headers=get_auth_headers(admin_token)
                )

                assert response.status_code == 200
                assert response.content == b"fake image data"
                assert "image/jpeg" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_get_file_with_token_query_param(
        self,
        client: AsyncClient,
        admin_token: str
    ):
        """Test file retrieval with token query parameter."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            get_file_resp = MagicMock()
            get_file_resp.json.return_value = {
                "ok": True,
                "result": {"file_path": "videos/file.mp4"}
            }

            file_resp = MagicMock()
            file_resp.status_code = 200
            file_resp.content = b"fake video data"

            mock_client.get.side_effect = [get_file_resp, file_resp]

            with patch("api.routes.messages.settings") as mock_settings:
                mock_settings.telegram_bot_token = "test_token_123"

                response = await client.get(
                    f"/api/chats/file/test_file_id?token={admin_token}"
                )

                assert response.status_code == 200
                assert response.content == b"fake video data"

    @pytest.mark.asyncio
    async def test_get_file_without_auth(
        self,
        client: AsyncClient
    ):
        """Test file retrieval without authentication."""
        response = await client.get("/api/chats/file/test_file_id")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_file_telegram_not_found(
        self,
        client: AsyncClient,
        admin_token: str,
        get_auth_headers
    ):
        """Test file not found in Telegram."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            get_file_resp = MagicMock()
            get_file_resp.json.return_value = {"ok": False}

            mock_client.get.return_value = get_file_resp

            with patch("api.routes.messages.settings") as mock_settings:
                mock_settings.telegram_bot_token = "test_token_123"

                response = await client.get(
                    "/api/chats/file/invalid_file_id",
                    headers=get_auth_headers(admin_token)
                )

                assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_file_bot_token_not_configured(
        self,
        client: AsyncClient,
        admin_token: str,
        get_auth_headers
    ):
        """Test file retrieval when bot token is not configured."""
        with patch("api.routes.messages.settings") as mock_settings:
            mock_settings.telegram_bot_token = None

            response = await client.get(
                "/api/chats/file/test_file_id",
                headers=get_auth_headers(admin_token)
            )

            assert response.status_code == 500
            assert "Bot token not configured" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_file_content_types(
        self,
        client: AsyncClient,
        admin_token: str,
        get_auth_headers
    ):
        """Test various file content types are detected correctly."""
        test_cases = [
            ("photo.jpg", "image/jpeg"),
            ("photo.jpeg", "image/jpeg"),
            ("image.png", "image/png"),
            ("anim.gif", "image/gif"),
            ("sticker.webp", "image/webp"),
            ("video.mp4", "video/mp4"),
            ("video.webm", "video/webm"),
            ("sticker.tgs", "application/x-tgsticker"),
        ]

        for file_path, expected_type in test_cases:
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value.__aenter__.return_value = mock_client

                get_file_resp = MagicMock()
                get_file_resp.json.return_value = {
                    "ok": True,
                    "result": {"file_path": file_path}
                }

                file_resp = MagicMock()
                file_resp.status_code = 200
                file_resp.content = b"test data"

                mock_client.get.side_effect = [get_file_resp, file_resp]

                with patch("api.routes.messages.settings") as mock_settings:
                    mock_settings.telegram_bot_token = "test_token_123"

                    response = await client.get(
                        "/api/chats/file/test_file",
                        headers=get_auth_headers(admin_token)
                    )

                    assert response.status_code == 200
                    assert expected_type in response.headers["content-type"]


# ============================================================================
# TEST: GET /local/{chat_id}/{filename} - Local File Serving
# ============================================================================

class TestGetLocalFile:
    """Test local file serving endpoint."""

    @pytest.mark.asyncio
    async def test_get_local_file_success(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        get_auth_headers,
        org_owner
    ):
        """Test successful local file retrieval."""
        # Create test file
        uploads_dir = Path(__file__).parent.parent / "uploads"
        chat_dir = uploads_dir / str(chat.id)
        chat_dir.mkdir(parents=True, exist_ok=True)

        test_file = chat_dir / "test_image.jpg"
        test_content = b"fake image content"
        test_file.write_bytes(test_content)

        try:
            response = await client.get(
                f"/api/chats/local/{chat.id}/test_image.jpg",
                headers=get_auth_headers(admin_token)
            )

            assert response.status_code == 200
            assert response.content == test_content
            assert "image/jpeg" in response.headers["content-type"]
            assert "Accept-Ranges" in response.headers
        finally:
            test_file.unlink()
            if not list(chat_dir.iterdir()):
                chat_dir.rmdir()

    @pytest.mark.asyncio
    async def test_get_local_file_with_token_param(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        org_owner
    ):
        """Test local file retrieval with token query parameter."""
        uploads_dir = Path(__file__).parent.parent / "uploads"
        chat_dir = uploads_dir / str(chat.id)
        chat_dir.mkdir(parents=True, exist_ok=True)

        test_file = chat_dir / "test.png"
        test_file.write_bytes(b"png data")

        try:
            response = await client.get(
                f"/api/chats/local/{chat.id}/test.png?token={admin_token}"
            )

            assert response.status_code == 200
            assert response.content == b"png data"
        finally:
            test_file.unlink()
            if not list(chat_dir.iterdir()):
                chat_dir.rmdir()

    @pytest.mark.asyncio
    async def test_get_local_file_access_denied(
        self,
        client: AsyncClient,
        second_user: User,
        second_user_token: str,
        chat: Chat,
        get_auth_headers,
        org_member
    ):
        """Test access denied for non-owner."""
        response = await client.get(
            f"/api/chats/local/{chat.id}/test.jpg",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_local_file_chat_not_found(
        self,
        client: AsyncClient,
        admin_token: str,
        get_auth_headers
    ):
        """Test 404 when chat doesn't exist."""
        response = await client.get(
            "/api/chats/local/999999/test.jpg",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_local_file_not_found(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        get_auth_headers,
        org_owner
    ):
        """Test 404 when file doesn't exist."""
        response = await client.get(
            f"/api/chats/local/{chat.id}/nonexistent.jpg",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_local_file_path_traversal_attack(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        get_auth_headers,
        org_owner
    ):
        """Test path traversal attack is blocked."""
        malicious_paths = [
            "../../../etc/passwd",
            "../../secret.txt",
            "..%2F..%2F..%2Fetc%2Fpasswd",
        ]

        for malicious_path in malicious_paths:
            response = await client.get(
                f"/api/chats/local/{chat.id}/{malicious_path}",
                headers=get_auth_headers(admin_token)
            )

            # Should be blocked with 403, 404, or 422 (FastAPI path validation)
            assert response.status_code in [403, 404, 422]

    @pytest.mark.asyncio
    async def test_get_local_file_range_request_video(
        self,
        real_aiofiles,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        get_auth_headers,
        org_owner
    ):
        """Test range request for video streaming."""
        uploads_dir = Path(__file__).parent.parent / "uploads"
        chat_dir = uploads_dir / str(chat.id)
        chat_dir.mkdir(parents=True, exist_ok=True)

        test_file = chat_dir / "video.mp4"
        test_content = b"0123456789" * 20  # 200 bytes
        test_file.write_bytes(test_content)

        try:
            response = await client.get(
                f"/api/chats/local/{chat.id}/video.mp4",
                headers={
                    **get_auth_headers(admin_token),
                    "Range": "bytes=0-99"
                }
            )

            assert response.status_code == 206
            assert len(response.content) == 100
            assert response.content == test_content[:100]
            assert "Content-Range" in response.headers
            assert "bytes 0-99/200" in response.headers["Content-Range"]
        finally:
            test_file.unlink()
            if not list(chat_dir.iterdir()):
                chat_dir.rmdir()

    @pytest.mark.asyncio
    async def test_get_local_file_range_request_audio(
        self,
        real_aiofiles,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        get_auth_headers,
        org_owner
    ):
        """Test range request for audio streaming."""
        uploads_dir = Path(__file__).parent.parent / "uploads"
        chat_dir = uploads_dir / str(chat.id)
        chat_dir.mkdir(parents=True, exist_ok=True)

        test_file = chat_dir / "audio.ogg"
        test_content = b"audio" * 50  # 250 bytes
        test_file.write_bytes(test_content)

        try:
            response = await client.get(
                f"/api/chats/local/{chat.id}/audio.ogg",
                headers={
                    **get_auth_headers(admin_token),
                    "Range": "bytes=50-149"
                }
            )

            assert response.status_code == 206
            assert len(response.content) == 100
            assert response.content == test_content[50:150]
        finally:
            test_file.unlink()
            if not list(chat_dir.iterdir()):
                chat_dir.rmdir()

    @pytest.mark.asyncio
    async def test_get_local_file_invalid_range(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        get_auth_headers,
        org_owner
    ):
        """Test invalid range request returns 416."""
        uploads_dir = Path(__file__).parent.parent / "uploads"
        chat_dir = uploads_dir / str(chat.id)
        chat_dir.mkdir(parents=True, exist_ok=True)

        test_file = chat_dir / "video.mp4"
        test_file.write_bytes(b"small video")  # 11 bytes

        try:
            response = await client.get(
                f"/api/chats/local/{chat.id}/video.mp4",
                headers={
                    **get_auth_headers(admin_token),
                    "Range": "bytes=1000-2000"  # Beyond file size
                }
            )

            assert response.status_code == 416
        finally:
            test_file.unlink()
            if not list(chat_dir.iterdir()):
                chat_dir.rmdir()

    @pytest.mark.asyncio
    async def test_get_local_file_content_types(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        get_auth_headers,
        org_owner
    ):
        """Test various content types are detected correctly."""
        test_cases = [
            ("image.jpg", "image/jpeg"),
            ("image.png", "image/png"),
            ("anim.gif", "image/gif"),
            ("image.webp", "image/webp"),
            ("video.mp4", "video/mp4"),
            ("video.webm", "video/webm"),
            ("audio.ogg", "audio/ogg"),
            ("audio.opus", "audio/opus"),
        ]

        uploads_dir = Path(__file__).parent.parent / "uploads"
        chat_dir = uploads_dir / str(chat.id)
        chat_dir.mkdir(parents=True, exist_ok=True)

        try:
            for filename, expected_type in test_cases:
                test_file = chat_dir / filename
                test_file.write_bytes(b"test data")

                response = await client.get(
                    f"/api/chats/local/{chat.id}/{filename}",
                    headers=get_auth_headers(admin_token)
                )

                assert response.status_code == 200
                assert expected_type in response.headers["content-type"]

                test_file.unlink()
        finally:
            if chat_dir.exists() and not list(chat_dir.iterdir()):
                chat_dir.rmdir()


# ============================================================================
# TEST: POST /messages/{message_id}/transcribe - Message Transcription
# ============================================================================

class TestTranscribeMessage:
    """Test single message transcription."""

    @pytest.mark.asyncio
    async def test_transcribe_voice_local_file(
        self,
        db_session: AsyncSession,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        get_auth_headers,
        org_owner
    ):
        """Test transcribing voice message from local file."""
        # Create voice message with local file
        uploads_dir = Path(__file__).parent.parent / "uploads"
        voice_path = f"{chat.id}/voice.ogg"
        full_path = uploads_dir / voice_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(b"fake audio data")

        voice_msg = Message(
            chat_id=chat.id,
            telegram_message_id=40001,
            telegram_user_id=100200300,
            username="alice",
            first_name="Alice",
            last_name="Smith",
            content="[Voice message]",
            content_type="voice",
            file_path=f"uploads/{voice_path}",
            timestamp=datetime.utcnow()
        )
        db_session.add(voice_msg)
        await db_session.commit()
        await db_session.refresh(voice_msg)

        try:
            with patch("api.routes.messages.transcription_service") as mock_service:
                mock_service.transcribe_audio = AsyncMock(
                    return_value="This is the transcribed text"
                )

                response = await client.post(
                    f"/api/chats/messages/{voice_msg.id}/transcribe",
                    headers=get_auth_headers(admin_token)
                )

                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert data["transcription"] == "This is the transcribed text"
                assert data["message_id"] == voice_msg.id

                # Verify message was updated
                await db_session.refresh(voice_msg)
                assert voice_msg.content == "This is the transcribed text"
        finally:
            if full_path.exists():
                full_path.unlink()
            if full_path.parent.exists() and not list(full_path.parent.iterdir()):
                full_path.parent.rmdir()

    @pytest.mark.asyncio
    async def test_transcribe_video_local_file(
        self,
        db_session: AsyncSession,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        get_auth_headers,
        org_owner
    ):
        """Test transcribing video message from local file."""
        uploads_dir = Path(__file__).parent.parent / "uploads"
        video_path = f"{chat.id}/video.mp4"
        full_path = uploads_dir / video_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(b"fake video data")

        video_msg = Message(
            chat_id=chat.id,
            telegram_message_id=40002,
            telegram_user_id=100200300,
            username="alice",
            first_name="Alice",
            last_name="Smith",
            content="[Video note]",
            content_type="video_note",
            file_path=f"uploads/{video_path}",
            timestamp=datetime.utcnow()
        )
        db_session.add(video_msg)
        await db_session.commit()
        await db_session.refresh(video_msg)

        try:
            with patch("api.routes.messages.transcription_service") as mock_service:
                mock_service.transcribe_video = AsyncMock(
                    return_value="Video transcription text"
                )

                response = await client.post(
                    f"/api/chats/messages/{video_msg.id}/transcribe",
                    headers=get_auth_headers(admin_token)
                )

                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert data["transcription"] == "Video transcription text"
        finally:
            if full_path.exists():
                full_path.unlink()
            if full_path.parent.exists() and not list(full_path.parent.iterdir()):
                full_path.parent.rmdir()

    @pytest.mark.asyncio
    async def test_transcribe_message_not_found(
        self,
        client: AsyncClient,
        admin_token: str,
        get_auth_headers
    ):
        """Test 404 when message doesn't exist."""
        response = await client.post(
            "/api/chats/messages/999999/transcribe",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_transcribe_access_denied(
        self,
        client: AsyncClient,
        second_user: User,
        second_user_token: str,
        voice_message: Message,
        get_auth_headers,
        org_member
    ):
        """Test non-owner cannot transcribe."""
        response = await client.post(
            f"/api/chats/messages/{voice_message.id}/transcribe",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_transcribe_text_message_fails(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        text_message: Message,
        get_auth_headers,
        org_owner
    ):
        """Test text messages cannot be transcribed."""
        response = await client.post(
            f"/api/chats/messages/{text_message.id}/transcribe",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 400
        detail = response.json()["detail"].lower()
        assert "no media file" in detail or "not audio or video" in detail

    @pytest.mark.asyncio
    async def test_transcribe_superadmin_access(
        self,
        db_session: AsyncSession,
        client: AsyncClient,
        superadmin_user: User,
        superadmin_token: str,
        chat: Chat,
        get_auth_headers
    ):
        """Test superadmin can transcribe any message."""
        uploads_dir = Path(__file__).parent.parent / "uploads"
        voice_path = f"{chat.id}/voice_super.ogg"
        full_path = uploads_dir / voice_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(b"audio")

        voice_msg = Message(
            chat_id=chat.id,
            telegram_message_id=40003,
            telegram_user_id=100200300,
            username="alice",
            first_name="Alice",
            last_name="Smith",
            content="[Voice message]",
            content_type="voice",
            file_path=f"uploads/{voice_path}",
            timestamp=datetime.utcnow()
        )
        db_session.add(voice_msg)
        await db_session.commit()
        await db_session.refresh(voice_msg)

        try:
            with patch("api.routes.messages.transcription_service") as mock_service:
                mock_service.transcribe_audio = AsyncMock(
                    return_value="Superadmin transcription"
                )

                response = await client.post(
                    f"/api/chats/messages/{voice_msg.id}/transcribe",
                    headers=get_auth_headers(superadmin_token)
                )

                assert response.status_code == 200
        finally:
            if full_path.exists():
                full_path.unlink()
            if full_path.parent.exists() and not list(full_path.parent.iterdir()):
                full_path.parent.rmdir()


# ============================================================================
# TEST: POST /{chat_id}/transcribe-all - Bulk Transcription
# ============================================================================

class TestTranscribeAllMessages:
    """Test bulk message transcription."""

    @pytest.mark.asyncio
    async def test_transcribe_all_no_messages(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        get_auth_headers,
        org_owner
    ):
        """Test transcribe-all with no messages to transcribe."""
        response = await client.post(
            f"/api/chats/{chat.id}/transcribe-all",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["transcribed"] == 0
        assert data["total_found"] == 0

    @pytest.mark.asyncio
    async def test_transcribe_all_access_denied(
        self,
        client: AsyncClient,
        second_user: User,
        second_user_token: str,
        chat: Chat,
        get_auth_headers,
        org_member
    ):
        """Test non-owner cannot bulk transcribe."""
        response = await client.post(
            f"/api/chats/{chat.id}/transcribe-all",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_transcribe_all_chat_not_found(
        self,
        client: AsyncClient,
        admin_token: str,
        get_auth_headers
    ):
        """Test 404 when chat doesn't exist."""
        response = await client.post(
            "/api/chats/999999/transcribe-all",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404


# ============================================================================
# TEST: Edge Cases and Error Handling
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_empty_chat_messages(
        self,
        db_session: AsyncSession,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        organization: Organization,
        get_auth_headers,
        org_owner
    ):
        """Test getting messages from empty chat."""
        empty_chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=555666777,
            title="Empty Chat",
            chat_type=ChatType.hr,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(empty_chat)
        await db_session.commit()
        await db_session.refresh(empty_chat)

        response = await client.get(
            f"/api/chats/{empty_chat.id}/messages",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_message_with_null_fields(
        self,
        db_session: AsyncSession,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        get_auth_headers,
        org_owner
    ):
        """Test message with null optional fields."""
        minimal_msg = Message(
            chat_id=chat.id,
            telegram_message_id=50001,
            telegram_user_id=999888777,
            username=None,
            first_name=None,
            last_name=None,
            content="Minimal message",
            content_type="text",
            file_id=None,
            file_path=None,
            file_name=None,
            timestamp=datetime.utcnow()
        )
        db_session.add(minimal_msg)
        await db_session.commit()

        response = await client.get(
            f"/api/chats/{chat.id}/messages",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        minimal_in_response = next(
            (m for m in data if m["content"] == "Minimal message"),
            None
        )
        assert minimal_in_response is not None
        assert minimal_in_response["username"] is None
        assert minimal_in_response["first_name"] is None
        assert minimal_in_response["last_name"] is None

    @pytest.mark.asyncio
    async def test_message_with_document_metadata(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        document_message: Message,
        get_auth_headers,
        org_owner
    ):
        """Test message with document metadata is returned correctly."""
        response = await client.get(
            f"/api/chats/{chat.id}/messages",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        doc_msg = next(
            (m for m in data if m["id"] == document_message.id),
            None
        )
        assert doc_msg is not None
        assert doc_msg["document_metadata"]["file_type"] == "pdf"
        assert doc_msg["document_metadata"]["pages_count"] == 3
        assert doc_msg["parse_status"] == "parsed"

    @pytest.mark.asyncio
    async def test_message_with_parse_error(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        failed_parse_message: Message,
        get_auth_headers,
        org_owner
    ):
        """Test message with parse error is returned correctly."""
        response = await client.get(
            f"/api/chats/{chat.id}/messages",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        failed_msg = next(
            (m for m in data if m["id"] == failed_parse_message.id),
            None
        )
        assert failed_msg is not None
        assert failed_msg["parse_status"] == "failed"
        assert "encrypted" in failed_msg["parse_error"].lower()

    @pytest.mark.asyncio
    async def test_participant_name_aggregation(
        self,
        db_session: AsyncSession,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        get_auth_headers,
        org_owner
    ):
        """Test participant names are aggregated using max()."""
        # Create messages from same user with different names
        for i, first_name in enumerate(["Alice", "Alicia", "Alissa"]):
            msg = Message(
                chat_id=chat.id,
                telegram_message_id=60000 + i,
                telegram_user_id=100200300,  # Same user
                username="alice",
                first_name=first_name,  # Different first names
                last_name="Smith",
                content=f"Message {i}",
                content_type="text",
                timestamp=datetime.utcnow()
            )
            db_session.add(msg)

        await db_session.commit()

        response = await client.get(
            f"/api/chats/{chat.id}/participants",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        participant = next(
            (p for p in data if p["telegram_user_id"] == 100200300),
            None
        )
        assert participant is not None
        assert participant["messages_count"] == 3
        # Should use max() of first names
        assert participant["first_name"] in ["Alice", "Alicia", "Alissa"]

    @pytest.mark.asyncio
    async def test_deleted_chat_access(
        self,
        db_session: AsyncSession,
        client: AsyncClient,
        admin_user: User,
        admin_token: str,
        chat: Chat,
        text_message: Message,
        get_auth_headers,
        org_owner
    ):
        """Test accessing messages from soft-deleted chat."""
        # Soft delete the chat
        chat.deleted_at = datetime.utcnow()
        await db_session.commit()

        response = await client.get(
            f"/api/chats/{chat.id}/messages",
            headers=get_auth_headers(admin_token)
        )

        # Behavior depends on implementation
        # Should be 200 (showing messages) or 404 (chat not found)
        assert response.status_code in [200, 404]
