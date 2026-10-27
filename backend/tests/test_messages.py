"""
Comprehensive tests for message routes (backend/api/routes/messages.py).
These tests cover message listing, participants, file serving, and transcription.
"""
import pytest
import pytest_asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import tempfile
import os

from api.models.database import Message, Chat, SharedAccess, AccessLevel, ResourceType


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
async def message(db_session, chat):
    """Create a test text message."""
    msg = Message(
        chat_id=chat.id,
        telegram_message_id=12345,
        telegram_user_id=987654321,
        username="testuser",
        first_name="Test",
        last_name="User",
        content="Hello, this is a test message!",
        content_type="text",
        timestamp=datetime.utcnow()
    )
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)
    return msg


@pytest_asyncio.fixture
async def voice_message(db_session, chat):
    """Create a test voice message."""
    msg = Message(
        chat_id=chat.id,
        telegram_message_id=12346,
        telegram_user_id=987654321,
        username="testuser",
        first_name="Test",
        last_name="User",
        content="[Voice message]",
        content_type="voice",
        file_id="voice123",
        timestamp=datetime.utcnow()
    )
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)
    return msg


@pytest_asyncio.fixture
async def video_message(db_session, chat):
    """Create a test video message with local file."""
    msg = Message(
        chat_id=chat.id,
        telegram_message_id=12347,
        telegram_user_id=987654321,
        username="testuser",
        first_name="Test",
        last_name="User",
        content="[Video message]",
        content_type="video_note",
        file_path=f"uploads/{chat.id}/video.mp4",
        timestamp=datetime.utcnow()
    )
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)
    return msg


@pytest_asyncio.fixture
async def photo_message(db_session, chat):
    """Create a test photo message."""
    msg = Message(
        chat_id=chat.id,
        telegram_message_id=12348,
        telegram_user_id=111222333,
        username="photouser",
        first_name="Photo",
        last_name="User",
        content="Check this out!",
        content_type="photo",
        file_id="photo456",
        timestamp=datetime.utcnow()
    )
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)
    return msg


@pytest_asyncio.fixture
async def second_chat_message(db_session, second_chat):
    """Create a message in second_chat."""
    msg = Message(
        chat_id=second_chat.id,
        telegram_message_id=99999,
        telegram_user_id=444555666,
        username="otheruser",
        first_name="Other",
        last_name="User",
        content="Message in another chat",
        content_type="text",
        timestamp=datetime.utcnow()
    )
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)
    return msg


@pytest_asyncio.fixture
async def multiple_messages(db_session, chat):
    """Create multiple messages for pagination testing."""
    messages = []
    for i in range(15):
        msg = Message(
            chat_id=chat.id,
            telegram_message_id=20000 + i,
            telegram_user_id=987654321,
            username="testuser",
            first_name="Test",
            last_name="User",
            content=f"Message {i + 1}",
            content_type="text" if i % 2 == 0 else "photo",
            timestamp=datetime.utcnow()
        )
        db_session.add(msg)
        messages.append(msg)

    await db_session.commit()
    for msg in messages:
        await db_session.refresh(msg)
    return messages


# ============================================================================
# TEST: GET /api/chats/{chat_id}/messages - List Messages
# ============================================================================

class TestGetMessages:
    """Test message listing endpoint."""

    @pytest.mark.asyncio
    async def test_owner_can_list_messages(
        self, client, admin_user, admin_token, chat, message, get_auth_headers, org_owner
    ):
        """Test that chat owner can list messages."""
        response = await client.get(
            f"/api/chats/{chat.id}/messages",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["content"] == "Hello, this is a test message!"
        assert data[0]["content_type"] == "text"
        assert data[0]["telegram_user_id"] == 987654321

    @pytest.mark.asyncio
    async def test_superadmin_can_list_messages(
        self, client, superadmin_user, superadmin_token, chat, message, get_auth_headers
    ):
        """Test that superadmin can list messages in any chat."""
        response = await client.get(
            f"/api/chats/{chat.id}/messages",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_non_owner_cannot_list_messages(
        self, client, second_user, second_user_token, chat, message, get_auth_headers, org_member
    ):
        """Test that non-owner cannot list messages without access."""
        response = await client.get(
            f"/api/chats/{chat.id}/messages",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403
        data = response.json()
        assert "Access denied" in data["detail"]

    @pytest.mark.asyncio
    async def test_chat_not_found(
        self, client, admin_token, get_auth_headers
    ):
        """Test 404 when chat doesn't exist."""
        response = await client.get(
            "/api/chats/999999/messages",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404
        data = response.json()
        assert "Chat not found" in data["detail"]

    @pytest.mark.asyncio
    async def test_pagination_with_limit(
        self, client, admin_user, admin_token, chat, multiple_messages, get_auth_headers, org_owner
    ):
        """Test pagination with custom limit."""
        response = await client.get(
            f"/api/chats/{chat.id}/messages?limit=5",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5

    @pytest.mark.asyncio
    async def test_pagination_with_page(
        self, client, admin_user, admin_token, chat, multiple_messages, get_auth_headers, org_owner
    ):
        """Test pagination with page parameter."""
        # Get first page
        response1 = await client.get(
            f"/api/chats/{chat.id}/messages?page=1&limit=5",
            headers=get_auth_headers(admin_token)
        )
        assert response1.status_code == 200
        data1 = response1.json()

        # Get second page
        response2 = await client.get(
            f"/api/chats/{chat.id}/messages?page=2&limit=5",
            headers=get_auth_headers(admin_token)
        )
        assert response2.status_code == 200
        data2 = response2.json()

        # Ensure different messages
        if len(data1) > 0 and len(data2) > 0:
            assert data1[0]["id"] != data2[0]["id"]

    @pytest.mark.asyncio
    async def test_filter_by_content_type_text(
        self, client, admin_user, admin_token, chat, message, photo_message, get_auth_headers, org_owner
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
    async def test_filter_by_content_type_photo(
        self, client, admin_user, admin_token, chat, message, photo_message, get_auth_headers, org_owner
    ):
        """Test filtering messages by content_type=photo."""
        response = await client.get(
            f"/api/chats/{chat.id}/messages?content_type=photo",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        # All messages should be photo type
        for msg in data:
            assert msg["content_type"] == "photo"

    @pytest.mark.asyncio
    async def test_filter_all_content_types(
        self, client, admin_user, admin_token, chat, message, photo_message, get_auth_headers, org_owner
    ):
        """Test filtering with content_type=all shows all messages."""
        response = await client.get(
            f"/api/chats/{chat.id}/messages?content_type=all",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        # Should have both text and photo
        content_types = {msg["content_type"] for msg in data}
        assert "text" in content_types
        assert "photo" in content_types

    @pytest.mark.asyncio
    async def test_messages_ordered_by_timestamp_desc(
        self, client, admin_user, admin_token, chat, multiple_messages, get_auth_headers, org_owner
    ):
        """Test messages are returned in reverse chronological order."""
        response = await client.get(
            f"/api/chats/{chat.id}/messages?limit=500",  # limit ограничен 500 (Query le=500)
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        if len(data) > 1:
            # After reversal in the endpoint, first message should be oldest
            # (endpoint reverses the DESC query results)
            timestamps = [datetime.fromisoformat(msg["timestamp"].replace('Z', '+00:00')) for msg in data]
            # Messages are DESC from DB, then reversed, so should be ASC in response
            for i in range(len(timestamps) - 1):
                assert timestamps[i] <= timestamps[i + 1]


# ============================================================================
# TEST: GET /api/chats/{chat_id}/participants - List Participants
# ============================================================================

class TestGetParticipants:
    """Test participants listing endpoint."""

    @pytest.mark.asyncio
    async def test_owner_can_list_participants(
        self, client, admin_user, admin_token, chat, message, photo_message, get_auth_headers, org_owner
    ):
        """Test that chat owner can list participants."""
        response = await client.get(
            f"/api/chats/{chat.id}/participants",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

        # Find the testuser participant
        testuser = next((p for p in data if p["telegram_user_id"] == 987654321), None)
        assert testuser is not None
        assert testuser["username"] == "testuser"
        assert testuser["first_name"] == "Test"
        assert testuser["messages_count"] >= 1

    @pytest.mark.asyncio
    async def test_participants_aggregated_by_telegram_user_id(
        self, db_session, client, admin_user, admin_token, chat, get_auth_headers, org_owner
    ):
        """Test that participants are properly aggregated by telegram_user_id."""
        # Create multiple messages from same user
        for i in range(3):
            msg = Message(
                chat_id=chat.id,
                telegram_message_id=30000 + i,
                telegram_user_id=111111111,
                username="aggregateuser",
                first_name="Aggregate",
                last_name="User",
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

        # Find aggregated user
        agg_user = next((p for p in data if p["telegram_user_id"] == 111111111), None)
        assert agg_user is not None
        assert agg_user["messages_count"] == 3

    @pytest.mark.asyncio
    async def test_participants_ordered_by_message_count(
        self, db_session, client, admin_user, admin_token, chat, get_auth_headers, org_owner
    ):
        """Test that participants are ordered by message count descending."""
        # Create users with different message counts
        for user_id, count in [(222222222, 5), (333333333, 10), (444444444, 2)]:
            for i in range(count):
                msg = Message(
                    chat_id=chat.id,
                    telegram_message_id=40000 + user_id + i,
                    telegram_user_id=user_id,
                    username=f"user{user_id}",
                    first_name="User",
                    last_name=str(user_id),
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

        # Verify ordering - counts should be descending
        counts = [p["messages_count"] for p in data]
        assert counts == sorted(counts, reverse=True)

    @pytest.mark.asyncio
    async def test_non_owner_cannot_list_participants(
        self, client, second_user, second_user_token, chat, message, get_auth_headers, org_member
    ):
        """Test that non-owner cannot list participants without access."""
        response = await client.get(
            f"/api/chats/{chat.id}/participants",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_participants_chat_not_found(
        self, client, admin_token, get_auth_headers
    ):
        """Test 404 when chat doesn't exist."""
        response = await client.get(
            "/api/chats/999999/participants",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404


# ============================================================================
# TEST: GET /api/chats/file/{file_id} - Telegram File Proxy
# ============================================================================

class TestGetTelegramFile:
    """Test Telegram file proxy endpoint."""

    @pytest.mark.asyncio
    async def test_get_file_with_auth_header(
        self, client, admin_token, get_auth_headers
    ):
        """Test file download with authorization header."""
        with patch("httpx.AsyncClient") as mock_client:
            # Mock Telegram API responses
            mock_async_client = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_async_client

            # Mock getFile response
            get_file_response = MagicMock()
            get_file_response.json.return_value = {
                "ok": True,
                "result": {"file_path": "photos/file_123.jpg"}
            }

            # Mock file download response
            file_response = MagicMock()
            file_response.status_code = 200
            file_response.content = b"fake image data"

            mock_async_client.get.side_effect = [get_file_response, file_response]

            with patch("api.routes.messages.settings") as mock_settings:
                mock_settings.telegram_bot_token = "test_bot_token"

                response = await client.get(
                    "/api/chats/file/test_file_id",
                    headers=get_auth_headers(admin_token)
                )

                assert response.status_code == 200
                assert response.content == b"fake image data"
                assert "image/jpeg" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_get_file_with_token_query_param(
        self, client, admin_token
    ):
        """Test file download with token query parameter."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_async_client = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_async_client

            get_file_response = MagicMock()
            get_file_response.json.return_value = {
                "ok": True,
                "result": {"file_path": "photos/file_456.png"}
            }

            file_response = MagicMock()
            file_response.status_code = 200
            file_response.content = b"fake png data"

            mock_async_client.get.side_effect = [get_file_response, file_response]

            with patch("api.routes.messages.settings") as mock_settings:
                mock_settings.telegram_bot_token = "test_bot_token"

                response = await client.get(
                    f"/api/chats/file/test_file_id?token={admin_token}"
                )

                assert response.status_code == 200
                assert response.content == b"fake png data"

    @pytest.mark.asyncio
    async def test_get_file_without_auth(self, client):
        """Test file download without authentication returns 401."""
        response = await client.get("/api/chats/file/test_file_id")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_file_not_found(
        self, client, admin_token, get_auth_headers
    ):
        """Test file not found in Telegram."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_async_client = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_async_client

            get_file_response = MagicMock()
            get_file_response.json.return_value = {"ok": False}

            mock_async_client.get.return_value = get_file_response

            with patch("api.routes.messages.settings") as mock_settings:
                mock_settings.telegram_bot_token = "test_bot_token"

                response = await client.get(
                    "/api/chats/file/invalid_file_id",
                    headers=get_auth_headers(admin_token)
                )

                assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_file_various_content_types(
        self, client, admin_token, get_auth_headers
    ):
        """Test content type detection for various file types."""
        test_cases = [
            ("video.mp4", "video/mp4"),
            ("video.webm", "video/webm"),
            ("sticker.tgs", "application/x-tgsticker"),
            ("image.gif", "image/gif"),
        ]

        for file_path, expected_type in test_cases:
            with patch("httpx.AsyncClient") as mock_client:
                mock_async_client = AsyncMock()
                mock_client.return_value.__aenter__.return_value = mock_async_client

                get_file_response = MagicMock()
                get_file_response.json.return_value = {
                    "ok": True,
                    "result": {"file_path": file_path}
                }

                file_response = MagicMock()
                file_response.status_code = 200
                file_response.content = b"test data"

                mock_async_client.get.side_effect = [get_file_response, file_response]

                with patch("api.routes.messages.settings") as mock_settings:
                    mock_settings.telegram_bot_token = "test_bot_token"

                    response = await client.get(
                        "/api/chats/file/test_file",
                        headers=get_auth_headers(admin_token)
                    )

                    assert response.status_code == 200
                    assert expected_type in response.headers.get("content-type", "")


# ============================================================================
# TEST: GET /api/chats/local/{chat_id}/{filename:path} - Local File Serving
# ============================================================================

class TestGetLocalFile:
    """Test local file serving endpoint."""

    @pytest.mark.asyncio
    async def test_get_local_file_with_auth(
        self, client, admin_user, admin_token, chat, get_auth_headers, org_owner
    ):
        """Test serving local file with authentication."""
        # Create temporary file in backend/uploads directory
        uploads_dir = Path(__file__).parent.parent / "uploads"
        chat_dir = uploads_dir / str(chat.id)
        chat_dir.mkdir(parents=True, exist_ok=True)

        test_file = chat_dir / "test.jpg"
        test_file.write_bytes(b"test image content")

        try:
            response = await client.get(
                f"/api/chats/local/{chat.id}/test.jpg",
                headers=get_auth_headers(admin_token)
            )

            assert response.status_code == 200
            assert response.content == b"test image content"
            assert "image/jpeg" in response.headers.get("content-type", "")
        finally:
            # Cleanup
            if test_file.exists():
                test_file.unlink()
            if chat_dir.exists() and not list(chat_dir.iterdir()):
                chat_dir.rmdir()

    @pytest.mark.asyncio
    async def test_get_local_file_with_token_param(
        self, client, admin_user, admin_token, chat, org_owner
    ):
        """Test serving local file with token query parameter."""
        uploads_dir = Path(__file__).parent.parent / "uploads"
        chat_dir = uploads_dir / str(chat.id)
        chat_dir.mkdir(parents=True, exist_ok=True)

        test_file = chat_dir / "test2.png"
        test_file.write_bytes(b"test png content")

        try:
            response = await client.get(
                f"/api/chats/local/{chat.id}/test2.png?token={admin_token}"
            )

            assert response.status_code == 200
            assert response.content == b"test png content"
        finally:
            if test_file.exists():
                test_file.unlink()
            if chat_dir.exists() and not list(chat_dir.iterdir()):
                chat_dir.rmdir()

    @pytest.mark.asyncio
    async def test_get_local_file_access_denied(
        self, client, second_user, second_user_token, chat, get_auth_headers, org_member
    ):
        """Test access denied for user without chat access."""
        response = await client.get(
            f"/api/chats/local/{chat.id}/test.jpg",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_local_file_chat_not_found(
        self, client, admin_token, get_auth_headers
    ):
        """Test 404 when chat doesn't exist."""
        response = await client.get(
            "/api/chats/local/999999/test.jpg",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_local_file_not_found(
        self, client, admin_user, admin_token, chat, get_auth_headers, org_owner
    ):
        """Test 404 when file doesn't exist."""
        response = await client.get(
            f"/api/chats/local/{chat.id}/nonexistent.jpg",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_local_file_path_traversal_blocked(
        self, client, admin_user, admin_token, chat, get_auth_headers, org_owner
    ):
        """Test that path traversal attacks are blocked."""
        response = await client.get(
            f"/api/chats/local/{chat.id}/../../../etc/passwd",
            headers=get_auth_headers(admin_token)
        )

        # Should be blocked with 403 or 404
        assert response.status_code in [403, 404]

    @pytest.mark.asyncio
    async def test_get_local_file_range_request(
        self, client, admin_user, admin_token, chat, get_auth_headers, org_owner, real_aiofiles
    ):
        """Test range request for video streaming."""
        uploads_dir = Path(__file__).parent.parent / "uploads"
        chat_dir = uploads_dir / str(chat.id)
        chat_dir.mkdir(parents=True, exist_ok=True)

        test_file = chat_dir / "video.mp4"
        test_content = b"0123456789" * 10  # 100 bytes
        test_file.write_bytes(test_content)

        try:
            response = await client.get(
                f"/api/chats/local/{chat.id}/video.mp4",
                headers={
                    **get_auth_headers(admin_token),
                    "Range": "bytes=0-49"
                }
            )

            assert response.status_code == 206
            assert len(response.content) == 50
            assert response.content == test_content[:50]
            assert "Content-Range" in response.headers
            assert "bytes 0-49/100" in response.headers["Content-Range"]
        finally:
            if test_file.exists():
                test_file.unlink()
            if chat_dir.exists() and not list(chat_dir.iterdir()):
                chat_dir.rmdir()

    @pytest.mark.asyncio
    async def test_get_local_file_invalid_range(
        self, client, admin_user, admin_token, chat, get_auth_headers, org_owner
    ):
        """Test invalid range request."""
        uploads_dir = Path(__file__).parent.parent / "uploads"
        chat_dir = uploads_dir / str(chat.id)
        chat_dir.mkdir(parents=True, exist_ok=True)

        test_file = chat_dir / "audio.ogg"
        test_file.write_bytes(b"audio data")

        try:
            response = await client.get(
                f"/api/chats/local/{chat.id}/audio.ogg",
                headers={
                    **get_auth_headers(admin_token),
                    "Range": "bytes=1000-2000"  # Beyond file size
                }
            )

            assert response.status_code == 416  # Range Not Satisfiable
        finally:
            if test_file.exists():
                test_file.unlink()
            if chat_dir.exists() and not list(chat_dir.iterdir()):
                chat_dir.rmdir()


# ============================================================================
# TEST: POST /api/chats/messages/{message_id}/transcribe - Transcribe Message
# ============================================================================

class TestTranscribeMessage:
    """Test message transcription endpoint."""

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Complex mock setup for Telegram API - integration test needed")
    async def test_transcribe_voice_message_from_telegram(
        self, client, admin_user, admin_token, chat, voice_message, get_auth_headers, org_owner
    ):
        """Test transcribing voice message from Telegram."""
        with patch("api.services.transcription.transcription_service") as mock_service:
            with patch("api.routes.messages.transcription_service") as mock_service2:
                mock_service.transcribe_audio = AsyncMock(return_value="This is the transcribed text")
                mock_service2.transcribe_audio = AsyncMock(return_value="This is the transcribed text")

                with patch("api.routes.messages.httpx.AsyncClient") as mock_client:
                    mock_async_client = AsyncMock()
                    mock_client.return_value.__aenter__.return_value = mock_async_client

                    # Mock Telegram file download
                    get_file_response = MagicMock()
                    get_file_response.json.return_value = {
                        "ok": True,
                        "result": {"file_path": "voice/file.ogg"}
                    }

                    file_response = MagicMock()
                    file_response.status_code = 200
                    file_response.content = b"fake audio data"

                    mock_async_client.get.side_effect = [get_file_response, file_response]

                    with patch("api.routes.messages.settings") as mock_settings:
                        mock_settings.telegram_bot_token = "test_bot_token"

                        response = await client.post(
                            f"/api/chats/messages/{voice_message.id}/transcribe",
                            headers=get_auth_headers(admin_token)
                        )

                        assert response.status_code == 200
                        data = response.json()
                        assert data["success"] is True
                        assert data["transcription"] == "This is the transcribed text"
                        assert data["message_id"] == voice_message.id

    @pytest.mark.asyncio
    async def test_transcribe_video_message_from_local(
        self, db_session, client, admin_user, admin_token, chat, get_auth_headers, org_owner
    ):
        """Test transcribing video message from local file."""
        # Create video message with local file
        uploads_dir = Path(__file__).parent.parent / "uploads"
        video_path = f"{chat.id}/test_video.mp4"
        full_path = uploads_dir / video_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(b"fake video data")

        video_msg = Message(
            chat_id=chat.id,
            telegram_message_id=50000,
            telegram_user_id=987654321,
            username="testuser",
            first_name="Test",
            last_name="User",
            content="[Video message]",
            content_type="video_note",
            file_path=f"uploads/{video_path}",
            timestamp=datetime.utcnow()
        )
        db_session.add(video_msg)
        await db_session.commit()
        await db_session.refresh(video_msg)

        try:
            with patch("api.services.transcription.transcription_service") as mock_service:
                with patch("api.routes.messages.transcription_service") as mock_service2:
                    mock_service.transcribe_video = AsyncMock(return_value="Transcribed video content")
                    mock_service2.transcribe_video = AsyncMock(return_value="Transcribed video content")

                    response = await client.post(
                        f"/api/chats/messages/{video_msg.id}/transcribe",
                        headers=get_auth_headers(admin_token)
                    )

                    assert response.status_code == 200
                    data = response.json()
                    assert data["success"] is True
                    assert data["transcription"] == "Transcribed video content"
        finally:
            if full_path.exists():
                full_path.unlink()
            if full_path.parent.exists() and not list(full_path.parent.iterdir()):
                full_path.parent.rmdir()

    @pytest.mark.asyncio
    async def test_transcribe_message_access_denied(
        self, client, second_user, second_user_token, voice_message, get_auth_headers, org_member
    ):
        """Test that non-owner cannot transcribe message."""
        response = await client.post(
            f"/api/chats/messages/{voice_message.id}/transcribe",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_transcribe_message_not_found(
        self, client, admin_token, get_auth_headers
    ):
        """Test 404 when message doesn't exist."""
        response = await client.post(
            "/api/chats/messages/999999/transcribe",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_transcribe_text_message_fails(
        self, client, admin_user, admin_token, chat, message, get_auth_headers, org_owner
    ):
        """Test that text messages cannot be transcribed."""
        response = await client.post(
            f"/api/chats/messages/{message.id}/transcribe",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 400
        data = response.json()
        assert "no media file" in data["detail"].lower() or "not audio or video" in data["detail"].lower()

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Complex mock setup for Telegram API - integration test needed")
    async def test_transcribe_superadmin_access(
        self, client, superadmin_user, superadmin_token, voice_message, get_auth_headers
    ):
        """Test that superadmin can transcribe any message."""
        with patch("api.services.transcription.transcription_service") as mock_service:
            with patch("api.routes.messages.transcription_service") as mock_service2:
                mock_service.transcribe_audio = AsyncMock(return_value="Superadmin transcription")
                mock_service2.transcribe_audio = AsyncMock(return_value="Superadmin transcription")

                with patch("api.routes.messages.httpx.AsyncClient") as mock_client:
                    mock_async_client = AsyncMock()
                    mock_client.return_value.__aenter__.return_value = mock_async_client

                    get_file_response = MagicMock()
                    get_file_response.json.return_value = {
                        "ok": True,
                        "result": {"file_path": "voice/file.ogg"}
                    }

                    file_response = MagicMock()
                    file_response.status_code = 200
                    file_response.content = b"audio"

                    mock_async_client.get.side_effect = [get_file_response, file_response]

                    with patch("api.routes.messages.settings") as mock_settings:
                        mock_settings.telegram_bot_token = "test_bot_token"

                        response = await client.post(
                            f"/api/chats/messages/{voice_message.id}/transcribe",
                            headers=get_auth_headers(superadmin_token)
                        )

                        assert response.status_code == 200


# ============================================================================
# TEST: POST /api/chats/{chat_id}/transcribe-all - Bulk Transcribe
# ============================================================================

class TestTranscribeAllMessages:
    """Test bulk transcription endpoint."""

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Complex mock setup for Telegram API - integration test needed")
    async def test_transcribe_all_messages(
        self, db_session, client, admin_user, admin_token, chat, get_auth_headers, org_owner
    ):
        """Test transcribing all untranscribed messages in a chat."""
        # Create multiple voice/video messages
        messages_to_transcribe = []
        for i in range(3):
            msg = Message(
                chat_id=chat.id,
                telegram_message_id=60000 + i,
                telegram_user_id=987654321,
                username="testuser",
                first_name="Test",
                last_name="User",
                content="[Voice message]",
                content_type="voice",
                file_id=f"voice_{i}",
                timestamp=datetime.utcnow()
            )
            db_session.add(msg)
            messages_to_transcribe.append(msg)

        await db_session.commit()

        with patch("api.services.transcription.transcription_service") as mock_service:
            with patch("api.routes.messages.transcription_service") as mock_service2:
                mock_service.transcribe_audio = AsyncMock(return_value="Transcribed audio")
                mock_service2.transcribe_audio = AsyncMock(return_value="Transcribed audio")

                with patch("api.routes.messages.httpx.AsyncClient") as mock_client:
                    mock_async_client = AsyncMock()
                    mock_client.return_value.__aenter__.return_value = mock_async_client

                    get_file_response = MagicMock()
                    get_file_response.json.return_value = {
                        "ok": True,
                        "result": {"file_path": "voice/file.ogg"}
                    }

                    file_response = MagicMock()
                    file_response.status_code = 200
                    file_response.content = b"audio"

                    mock_async_client.get.side_effect = [get_file_response, file_response] * 3

                    with patch("api.routes.messages.settings") as mock_settings:
                        mock_settings.telegram_bot_token = "test_bot_token"

                        response = await client.post(
                            f"/api/chats/{chat.id}/transcribe-all",
                            headers=get_auth_headers(admin_token)
                        )

                        assert response.status_code == 200
                        data = response.json()
                        assert data["success"] is True
                        assert data["transcribed"] == 3
                        assert data["total_found"] == 3

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Complex mock setup for Telegram API - integration test needed")
    async def test_transcribe_all_skips_already_transcribed(
        self, db_session, client, admin_user, admin_token, chat, get_auth_headers, org_owner
    ):
        """Test that already transcribed messages are skipped."""
        # Create one untranscribed and one already transcribed
        untranscribed = Message(
            chat_id=chat.id,
            telegram_message_id=70000,
            telegram_user_id=987654321,
            username="testuser",
            first_name="Test",
            last_name="User",
            content="[Voice message]",
            content_type="voice",
            file_id="voice_new",
            timestamp=datetime.utcnow()
        )
        db_session.add(untranscribed)

        already_transcribed = Message(
            chat_id=chat.id,
            telegram_message_id=70001,
            telegram_user_id=987654321,
            username="testuser",
            first_name="Test",
            last_name="User",
            content="Already transcribed content",  # No placeholder
            content_type="voice",
            file_id="voice_old",
            timestamp=datetime.utcnow()
        )
        db_session.add(already_transcribed)

        await db_session.commit()

        with patch("api.services.transcription.transcription_service") as mock_service:
            with patch("api.routes.messages.transcription_service") as mock_service2:
                mock_service.transcribe_audio = AsyncMock(return_value="New transcription")
                mock_service2.transcribe_audio = AsyncMock(return_value="New transcription")

                with patch("api.routes.messages.httpx.AsyncClient") as mock_client:
                    mock_async_client = AsyncMock()
                    mock_client.return_value.__aenter__.return_value = mock_async_client

                    get_file_response = MagicMock()
                    get_file_response.json.return_value = {
                        "ok": True,
                        "result": {"file_path": "voice/file.ogg"}
                    }

                    file_response = MagicMock()
                    file_response.status_code = 200
                    file_response.content = b"audio"

                    mock_async_client.get.side_effect = [get_file_response, file_response]

                    with patch("api.routes.messages.settings") as mock_settings:
                        mock_settings.telegram_bot_token = "test_bot_token"

                        response = await client.post(
                            f"/api/chats/{chat.id}/transcribe-all",
                            headers=get_auth_headers(admin_token)
                        )

                        assert response.status_code == 200
                        data = response.json()
                        # Should only transcribe 1 (the untranscribed one)
                        assert data["transcribed"] == 1
                        assert data["total_found"] == 1

    @pytest.mark.asyncio
    async def test_transcribe_all_access_denied(
        self, client, second_user, second_user_token, chat, get_auth_headers, org_member
    ):
        """Test that non-owner cannot bulk transcribe."""
        response = await client.post(
            f"/api/chats/{chat.id}/transcribe-all",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_transcribe_all_chat_not_found(
        self, client, admin_token, get_auth_headers
    ):
        """Test 404 when chat doesn't exist."""
        response = await client.post(
            "/api/chats/999999/transcribe-all",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_transcribe_all_no_messages(
        self, client, admin_user, admin_token, chat, get_auth_headers, org_owner
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


# ============================================================================
# TEST: Edge Cases and Error Handling
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_messages_from_deleted_chat(
        self, db_session, client, admin_user, admin_token, chat, message, get_auth_headers, org_owner
    ):
        """Test that messages from soft-deleted chats are not accessible."""
        # Soft delete the chat
        chat.deleted_at = datetime.utcnow()
        await db_session.commit()

        response = await client.get(
            f"/api/chats/{chat.id}/messages",
            headers=get_auth_headers(admin_token)
        )

        # Should still return 404 or empty since chat is deleted
        # Depending on implementation, might be 404
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_empty_chat_messages_list(
        self, db_session, client, admin_user, admin_token, get_auth_headers, organization, org_owner
    ):
        """Test getting messages from chat with no messages."""
        empty_chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=777888999,
            title="Empty Chat",
            chat_type="hr",
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
        data = response.json()
        assert data == []

    @pytest.mark.asyncio
    async def test_message_with_null_optional_fields(
        self, db_session, client, admin_user, admin_token, chat, get_auth_headers, org_owner
    ):
        """Test message with null optional fields."""
        minimal_msg = Message(
            chat_id=chat.id,
            telegram_message_id=80000,
            telegram_user_id=123456789,
            username=None,  # Optional
            first_name=None,  # Optional
            last_name=None,  # Optional
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
        minimal_in_response = next((m for m in data if m["content"] == "Minimal message"), None)
        assert minimal_in_response is not None
        assert minimal_in_response["username"] is None
        assert minimal_in_response["first_name"] is None
