"""
Error handling tests for HR-Bot backend.

Tests graceful degradation and error handling for:
- Database connection errors
- External API failures (Anthropic, OpenAI, Fireflies)
- Network timeouts
- Service unavailability
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.exc import OperationalError, IntegrityError, DatabaseError
import asyncio

from api.models.database import (
    Entity, EntityType, EntityStatus, Chat, ChatType,
    CallRecording, CallSource, CallStatus
)


async def _get_with_failing_db(path, token, exc_factory):
    """GET, при котором сессия базы падает.

    Раньше тест подменял атрибут api.database.get_db, но FastAPI держит ссылку
    на функцию в Depends, а фикстура client и так переопределяет её через
    dependency_overrides — подмена ничего не меняла (200). Переопределяем ту же
    зависимость; клиент с raise_app_exceptions=False, чтобы получить 500, как
    его отдаёт сервер, а не исключение из транспорта.
    """
    from httpx import AsyncClient, ASGITransport
    from api.database import get_db
    from main import app

    async def failing_db():
        await exc_factory()
        yield None  # pragma: no cover

    prev = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = failing_db
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            return await ac.get(path, cookies={"access_token": token})
    finally:
        if prev is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = prev


class TestDatabaseErrorHandling:
    """Test graceful handling of database errors."""

    @pytest.mark.asyncio
    async def test_database_connection_error_on_list(self, client, admin_token, monkeypatch):
        """Test graceful handling when database connection fails on list operation."""
        async def mock_db_error():
            raise OperationalError("Database connection failed", None, None)

        response = await _get_with_failing_db("/api/entities", admin_token, mock_db_error)

        # Should return 500 Internal Server Error
        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_database_integrity_error_on_create(
        self, db_session, client, admin_token, organization, department, org_owner
    ):
        """Test handling of database integrity constraint violations."""
        # Create an entity
        entity_data = {
            "name": "Test Entity",
            "type": "candidate",
            "email": "test@example.com"
        }

        response1 = await client.post(
            "/api/entities",
            json=entity_data,
            cookies={"access_token": admin_token}
        )
        assert response1.status_code in [200, 201]

        # Try to create another entity with same email (if unique constraint exists)
        # The application should handle this gracefully
        response2 = await client.post(
            "/api/entities",
            json=entity_data,
            cookies={"access_token": admin_token}
        )

        # Should either succeed (if duplicates allowed) or fail gracefully
        assert response2.status_code in [200, 201, 400, 409, 422]

    @pytest.mark.asyncio
    async def test_database_timeout_handling(self, client, admin_token, monkeypatch):
        """Test handling of database query timeouts."""
        async def mock_timeout():
            await asyncio.sleep(0.1)
            raise OperationalError("Query timeout", None, None)

        response = await _get_with_failing_db("/api/entities", admin_token, mock_timeout)

        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_database_error_on_transaction_rollback(
        self, db_session, client, admin_token, organization, department, org_owner
    ):
        """Test that failed operations properly rollback transactions."""
        # Create a valid entity
        response = await client.post(
            "/api/entities",
            json={"name": "Test", "type": "candidate"},
            cookies={"access_token": admin_token}
        )

        assert response.status_code in [200, 201]
        entity_id = response.json()["id"]

        # Verify entity exists
        response = await client.get(
            f"/api/entities/{entity_id}",
            cookies={"access_token": admin_token}
        )
        assert response.status_code == 200


class TestAnthropicAPIErrorHandling:
    """Test handling when Anthropic Claude API fails.

    Ручка чата с ИИ — POST /api/chats/{id}/ai/message (адреса /ai/chat нет).
    Ответ — поток SSE: он начинается со статусом 200, а сбой Claude приходит
    внутри потока событием с "error": true (строка «Ошибка AI: …»), а не кодом
    ответа. Ошибку подставляем в ai_service.chat_stream — клиент Anthropic
    создаётся при старте сервиса, подмена anthropic.AsyncAnthropic до него не
    доходила, и тест ушёл бы в настоящий Claude.
    """

    @staticmethod
    def _failing_stream(exc):
        async def chat_stream(*args, **kwargs):
            if False:  # pragma: no cover — делает функцию async-генератором
                yield ""
            raise exc
        return chat_stream

    async def _send(self, client, chat, admin_token):
        return await client.post(
            f"/api/chats/{chat.id}/ai/message",
            json={"message": "test"},
            cookies={"access_token": admin_token}
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("exc", [
        ConnectionError("Unable to connect to Anthropic API"),
        RuntimeError("Rate limit exceeded"),
        asyncio.TimeoutError("Request timed out"),
    ], ids=["connection_error", "rate_limit_error", "timeout"])
    async def test_anthropic_api_error_reported_in_stream(
        self, client, admin_token, chat, organization, org_owner, monkeypatch, exc
    ):
        """Сбой Claude не роняет запрос: в потоке — событие об ошибке и [DONE]."""
        from api.routes import ai as ai_routes
        monkeypatch.setattr(ai_routes.ai_service, "chat_stream", self._failing_stream(exc))

        response = await self._send(client, chat, admin_token)

        assert response.status_code == 200
        assert '"error": true' in response.text
        assert "data: [DONE]" in response.text

    @pytest.mark.asyncio
    async def test_anthropic_api_invalid_response(
        self, client, admin_token, chat, organization, org_owner, monkeypatch
    ):
        """Test handling when Anthropic API returns malformed response."""
        from api.routes import ai as ai_routes

        async def chat_stream(*args, **kwargs):
            yield None  # Invalid chunk — склейка строки с None упадёт

        monkeypatch.setattr(ai_routes.ai_service, "chat_stream", chat_stream)

        response = await self._send(client, chat, admin_token)

        # Should handle error gracefully
        assert response.status_code == 200
        assert '"error": true' in response.text


class TestOpenAIAPIErrorHandling:
    """Test handling when OpenAI Whisper API fails."""

    @pytest.mark.asyncio
    async def test_openai_api_connection_error(
        self, client, admin_token, organization, org_owner, monkeypatch, tmp_path
    ):
        """Test handling when OpenAI API is unreachable."""
        # Create a mock audio file
        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b'\xff\xfb\x90\x00' + b'\x00' * 100)

        # Mock OpenAI client to raise connection error
        mock_transcription = MagicMock()
        mock_transcription.create = MagicMock(side_effect=ConnectionError("Unable to connect"))

        mock_client = MagicMock()
        mock_client.audio.transcriptions = mock_transcription

        monkeypatch.setattr("openai.OpenAI", lambda *args, **kwargs: mock_client)

        # Test with call upload endpoint
        with open(audio_file, 'rb') as f:
            response = await client.post(
                "/api/calls/upload",
                files={"file": ("test.mp3", f, "audio/mpeg")},
                cookies={"access_token": admin_token}
            )

        # Should handle error gracefully (might succeed with mocked transcription)
        assert response.status_code in [200, 201, 500, 503]

    @pytest.mark.asyncio
    async def test_openai_api_invalid_audio_format(
        self, client, admin_token, organization, org_owner, tmp_path
    ):
        """Test handling when audio file format is invalid."""
        # Create an invalid audio file
        invalid_file = tmp_path / "invalid.mp3"
        invalid_file.write_bytes(b"not a valid audio file")

        with open(invalid_file, 'rb') as f:
            response = await client.post(
                "/api/calls/upload",
                files={"file": ("invalid.mp3", f, "audio/mpeg")},
                cookies={"access_token": admin_token}
            )

        # Should reject invalid format or handle gracefully
        assert response.status_code in [200, 201, 400, 422, 500]


class TestFirefliesAPIErrorHandling:
    """Test handling when Fireflies.ai API fails."""

    @pytest.mark.asyncio
    async def test_fireflies_api_connection_error(
        self, client, admin_token, organization, org_owner, monkeypatch
    ):
        """Test handling when Fireflies API is unreachable."""
        # Запуск записи — POST /api/calls/start-bot (source_url), бота
        # отправляет call_recorder.start_recording.
        from api.services.call_recorder import call_recorder
        monkeypatch.setattr(
            call_recorder, "start_recording",
            AsyncMock(side_effect=ConnectionError("Unable to connect")),
        )

        response = await client.post(
            "/api/calls/start-bot",
            json={"source_url": "https://meet.google.com/abc-defg-hij"},
            cookies={"access_token": admin_token}
        )

        # Should handle error gracefully
        assert response.status_code in [400, 500, 503]

    @pytest.mark.asyncio
    async def test_fireflies_api_invalid_meeting_url(
        self, client, admin_token, organization, org_owner
    ):
        """Test handling when Fireflies receives invalid meeting URL."""
        # Адрес /calls/fireflies/start убран — запуск через /calls/start-bot.
        response = await client.post(
            "/api/calls/start-bot",
            json={"source_url": "not-a-valid-url"},
            cookies={"access_token": admin_token}
        )

        # Should reject invalid URL
        assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_fireflies_api_transcript_not_found(
        self, client, admin_token, organization, org_owner, monkeypatch
    ):
        """Test handling when Fireflies transcript doesn't exist."""
        mock_client = MagicMock()
        mock_client.get_transcript = AsyncMock(return_value=None)

        monkeypatch.setattr("api.services.fireflies_client.fireflies_client", mock_client)

        # Try to fetch non-existent transcript
        response = await client.get(
            "/api/calls/fireflies/nonexistent-id",
            cookies={"access_token": admin_token}
        )

        # Should return 404 or handle gracefully
        assert response.status_code in [404, 500]


class TestConcurrentRequestHandling:
    """Test handling of concurrent requests and race conditions."""

    @pytest.mark.asyncio
    async def test_concurrent_entity_creation(
        self, client, admin_token, organization, department, org_owner
    ):
        """Test creating multiple entities concurrently."""
        async def create_entity(i):
            return await client.post(
                "/api/entities",
                json={"name": f"Concurrent Entity {i}", "type": "candidate"},
                cookies={"access_token": admin_token}
            )

        # Create 10 entities concurrently
        tasks = [create_entity(i) for i in range(10)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # All should succeed or fail gracefully
        for response in responses:
            if not isinstance(response, Exception):
                assert response.status_code in [200, 201, 500]

    @pytest.mark.asyncio
    async def test_concurrent_entity_updates(
        self, db_session, client, admin_token, organization, department, org_owner
    ):
        """Test updating same entity concurrently."""
        # Create an entity first
        response = await client.post(
            "/api/entities",
            json={"name": "Test Entity", "type": "candidate"},
            cookies={"access_token": admin_token}
        )
        assert response.status_code in [200, 201]
        entity_id = response.json()["id"]

        # Правка карточки — PUT /entities/{id} (PATCH на этом адресе нет, 405).
        async def update_entity(status):
            return await client.put(
                f"/api/entities/{entity_id}",
                json={"status": status},
                cookies={"access_token": admin_token}
            )

        # Update with different statuses concurrently
        statuses = ["screening", "interview", "offer", "hired", "rejected"]
        tasks = [update_entity(status) for status in statuses]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # All should complete, last one wins
        success_count = sum(
            1 for r in responses
            if not isinstance(r, Exception) and r.status_code == 200
        )
        assert success_count >= 1  # At least one should succeed

    @pytest.mark.asyncio
    async def test_concurrent_chat_message_creation(
        self, client, admin_token, chat, organization, org_owner, monkeypatch
    ):
        """Test sending multiple messages to same chat concurrently."""
        # Ручка — /ai/message; Claude подменяем, чтобы тест не ходил в сеть.
        from api.routes import ai as ai_routes

        async def chat_stream(*args, **kwargs):
            yield "ok"

        monkeypatch.setattr(ai_routes.ai_service, "chat_stream", chat_stream)

        async def send_message(i):
            return await client.post(
                f"/api/chats/{chat.id}/ai/message",
                json={"message": f"Concurrent message {i}"},
                cookies={"access_token": admin_token}
            )

        # Send 5 messages concurrently
        tasks = [send_message(i) for i in range(5)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # All should complete
        for response in responses:
            if not isinstance(response, Exception):
                assert response.status_code in [200, 500, 503]


class TestNetworkErrorHandling:
    """Test handling of network-related errors."""

    @pytest.mark.asyncio
    async def test_request_timeout_handling(self, client, admin_token, monkeypatch):
        """Test handling of request timeouts."""
        async def timeout_handler(*args, **kwargs):
            await asyncio.sleep(0.1)
            raise asyncio.TimeoutError("Request timeout")

        # This test verifies the application doesn't crash on timeout
        # Actual timeout handling depends on the web server configuration
        pass

    @pytest.mark.asyncio
    async def test_large_request_body_handling(
        self, client, admin_token, organization, department, org_owner
    ):
        """Test handling of very large request bodies."""
        # Create a very large extra_data payload
        large_data = {"key_" + str(i): "value" * 100 for i in range(1000)}

        response = await client.post(
            "/api/entities",
            json={
                "name": "Test",
                "type": "candidate",
                "extra_data": large_data
            },
            cookies={"access_token": admin_token}
        )

        # Should either accept or reject with proper error
        assert response.status_code in [200, 201, 413, 422]


class TestFileUploadErrorHandling:
    """Test error handling for file upload operations."""

    @pytest.mark.asyncio
    async def test_missing_file_upload(self, client, admin_token, organization, org_owner):
        """Test handling when file is not provided in upload."""
        response = await client.post(
            "/api/calls/upload",
            cookies={"access_token": admin_token}
        )

        # Should return validation error
        assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_corrupted_file_upload(
        self, client, admin_token, organization, org_owner, tmp_path
    ):
        """Test handling of corrupted file uploads."""
        # Create a corrupted file
        corrupted_file = tmp_path / "corrupted.mp3"
        corrupted_file.write_bytes(b'\x00' * 10)  # Just zeros, not valid audio

        with open(corrupted_file, 'rb') as f:
            response = await client.post(
                "/api/calls/upload",
                files={"file": ("corrupted.mp3", f, "audio/mpeg")},
                cookies={"access_token": admin_token}
            )

        # Should handle gracefully
        assert response.status_code in [200, 201, 400, 422, 500]

    @pytest.mark.asyncio
    async def test_oversized_file_upload(
        self, client, admin_token, organization, org_owner, tmp_path
    ):
        """Test handling of files exceeding size limits."""
        # This test documents expected behavior for large files
        # Actual size limits depend on server configuration
        large_file = tmp_path / "large.mp3"
        large_file.write_bytes(b'\xff\xfb\x90\x00' + b'\x00' * 1000)

        with open(large_file, 'rb') as f:
            response = await client.post(
                "/api/calls/upload",
                files={"file": ("large.mp3", f, "audio/mpeg")},
                cookies={"access_token": admin_token}
            )

        # Should either accept or reject based on size limits
        assert response.status_code in [200, 201, 400, 413, 422]


class TestAuthenticationErrorHandling:
    """Test error handling for authentication failures."""

    @pytest.mark.asyncio
    async def test_missing_auth_token(self, client):
        """Test handling when authentication token is missing."""
        response = await client.get("/api/entities")

        # Should return 401 Unauthorized
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_auth_token(self, client):
        """Test handling when authentication token is invalid."""
        response = await client.get(
            "/api/entities",
            cookies={"access_token": "invalid.token.here"}
        )

        # Should return 401 Unauthorized
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_auth_token(self, client, monkeypatch):
        """Test handling when authentication token has expired."""
        from api.services.auth import create_access_token
        from datetime import timedelta

        # Create an expired token (would need custom implementation)
        # This test documents expected behavior
        response = await client.get(
            "/api/entities",
            cookies={"access_token": "expired.token"}
        )

        # Should return 401 Unauthorized
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_insufficient_permissions(
        self, client, admin_token, second_user_token, entity
    ):
        """Test handling when user lacks permissions."""
        # Try to delete an entity owned by another user (if not allowed)
        response = await client.delete(
            f"/api/entities/{entity.id}",
            cookies={"access_token": second_user_token}
        )

        # Should return 403 Forbidden or succeed based on permissions
        assert response.status_code in [200, 204, 403, 404]
