"""
Tests for External Links API routes.

Tests:
1. POST /api/external/process-url - Processing external URLs
2. GET /api/external/status/{id} - Get processing status with progress
3. Duplicate URL detection and handling
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient

from api.models.database import (
    CallRecording, CallSource, CallStatus, User, UserRole
)


# ============================================================================
# TEST PROCESS URL ENDPOINT
# ============================================================================

class TestProcessURLEndpoint:
    """Tests for POST /api/external/process-url endpoint."""

    @pytest.mark.asyncio
    async def test_process_fireflies_url_returns_immediately(
        self, client: AsyncClient, admin_token, get_auth_headers, db_session, organization, admin_user, org_owner  # без членства в орге ручка отвечает 400
    ):
        """Test that Fireflies URL processing returns immediately with pending status."""
        url = "https://app.fireflies.ai/view/TEST123"

        with patch('api.routes.external_links.external_link_processor.create_pending_call') as mock_create, \
             patch('api.routes.external_links.external_link_processor.process_fireflies_async'):

            mock_call = MagicMock()
            mock_call.id = 123
            mock_call.title = "Test Call"
            mock_call.status = CallStatus.pending
            mock_create.return_value = mock_call

            response = await client.post(
                "/api/external/process-url",
                json={"url": url},
                headers=get_auth_headers(admin_token)
            )

        assert response.status_code == 200
        data = response.json()
        assert data["call_id"] == 123
        assert data["status"] == "pending"
        assert data["source_type"] == "fireflies"
        assert "1-2 minutes" in data["message"]

    @pytest.mark.asyncio
    async def test_duplicate_url_returns_existing_call(
        self, client: AsyncClient, admin_token, get_auth_headers, db_session, organization, admin_user, org_owner  # без членства в орге ручка отвечает 400
    ):
        """Test that submitting the same URL within 5 minutes returns existing call."""
        url = "https://app.fireflies.ai/view/DUPLICATE123"

        # Create existing call with same URL from 2 minutes ago
        existing_call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            source_url=url,
            source_type=CallSource.fireflies,
            status=CallStatus.pending,
            progress=50,
            progress_stage="Processing...",
            title="Existing Call",
            created_at=datetime.utcnow() - timedelta(minutes=2)
        )
        db_session.add(existing_call)
        await db_session.commit()
        await db_session.refresh(existing_call)

        response = await client.post(
            "/api/external/process-url",
            json={"url": url},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["call_id"] == existing_call.id
        assert "already being processed" in data["message"]

    @pytest.mark.asyncio
    async def test_old_duplicate_url_creates_new_call(
        self, client: AsyncClient, admin_token, get_auth_headers, db_session, organization, admin_user, org_owner  # без членства в орге ручка отвечает 400
    ):
        """Test that same URL after 5 minutes creates new call."""
        url = "https://app.fireflies.ai/view/OLD123"

        # Create existing call with same URL from 10 minutes ago
        old_call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            source_url=url,
            source_type=CallSource.fireflies,
            status=CallStatus.done,
            title="Old Call",
            created_at=datetime.utcnow() - timedelta(minutes=10)
        )
        db_session.add(old_call)
        await db_session.commit()
        await db_session.refresh(old_call)

        with patch('api.routes.external_links.external_link_processor.create_pending_call') as mock_create, \
             patch('api.routes.external_links.external_link_processor.process_fireflies_async'):

            mock_call = MagicMock()
            mock_call.id = 999
            mock_call.title = "New Call"
            mock_call.status = CallStatus.pending
            mock_create.return_value = mock_call

            response = await client.post(
                "/api/external/process-url",
                json={"url": url},
                headers=get_auth_headers(admin_token)
            )

        assert response.status_code == 200
        data = response.json()
        # Should create new call, not return old one
        assert data["call_id"] == 999

    @pytest.mark.asyncio
    async def test_process_url_requires_auth(self, client: AsyncClient):
        """Test that processing URL requires authentication."""
        response = await client.post(
            "/api/external/process-url",
            json={"url": "https://app.fireflies.ai/view/TEST"}
        )
        assert response.status_code == 401


# ============================================================================
# TEST STATUS ENDPOINT
# ============================================================================

class TestStatusEndpoint:
    """Tests for GET /api/external/status/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_status_returns_progress(
        self, client: AsyncClient, admin_token, get_auth_headers, db_session, organization, admin_user
    ):
        """Test that status endpoint returns progress and progress_stage."""
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            source_url="https://app.fireflies.ai/view/TEST",
            source_type=CallSource.fireflies,
            status=CallStatus.transcribing,
            progress=50,
            progress_stage="Извлечение транскрипта...",
            title="Test Call",
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        response = await client.get(
            f"/api/external/status/{call.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == call.id
        assert data["status"] == "transcribing"
        assert data["progress"] == 50
        assert data["progress_stage"] == "Извлечение транскрипта..."

    @pytest.mark.asyncio
    async def test_status_returns_zero_progress_when_null(
        self, client: AsyncClient, admin_token, get_auth_headers, db_session, organization, admin_user
    ):
        """Test that status returns 0 progress when progress is null."""
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            source_url="https://app.fireflies.ai/view/TEST",
            source_type=CallSource.fireflies,
            status=CallStatus.pending,
            progress=None,  # Null progress
            progress_stage=None,
            title="Test Call",
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        response = await client.get(
            f"/api/external/status/{call.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["progress"] == 0
        assert data["progress_stage"] == ""

    @pytest.mark.asyncio
    async def test_status_done_returns_100_progress(
        self, client: AsyncClient, admin_token, get_auth_headers, db_session, organization, admin_user
    ):
        """Test that done status returns 100% progress."""
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            source_url="https://app.fireflies.ai/view/TEST",
            source_type=CallSource.fireflies,
            status=CallStatus.done,
            progress=100,
            progress_stage="Готово",
            title="Test Call",
            transcript="Test transcript",
            summary="Test summary",
            created_at=datetime.utcnow(),
            processed_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        response = await client.get(
            f"/api/external/status/{call.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "done"
        assert data["progress"] == 100
        assert data["has_summary"] is True
        assert data["transcript_length"] > 0

    @pytest.mark.asyncio
    async def test_status_not_found(self, client: AsyncClient, admin_token, get_auth_headers):
        """Test that status returns 404 for non-existent call."""
        response = await client.get(
            "/api/external/status/99999",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_status_access_denied_other_org(
        self, client: AsyncClient, db_session, organization, admin_user, second_organization
    ):
        """Test that status returns 403 for call from different organization."""
        # Create call in first organization
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            source_url="https://app.fireflies.ai/view/TEST",
            source_type=CallSource.fireflies,
            status=CallStatus.pending,
            title="Test Call",
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        # Create user in second organization
        other_user = User(
            email="other@example.com",
            password_hash="hash",
            name="Other User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(other_user)
        await db_session.commit()

        # Try to access with user from different org
        from api.services.auth import create_access_token
        other_token = create_access_token(data={"sub": str(other_user.id)})
        other_headers = {"Cookie": f"access_token={other_token}"}

        response = await client.get(
            f"/api/external/status/{call.id}",
            headers=other_headers
        )

        assert response.status_code == 403


# ============================================================================
# TEST PROGRESS FLOW
# ============================================================================

class TestProgressFlow:
    """Tests for progress updates during processing."""

    @pytest.mark.asyncio
    async def test_progress_increases_over_time(
        self, client: AsyncClient, admin_token, get_auth_headers, db_session, organization, admin_user
    ):
        """Test that progress can be tracked and increases."""
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            source_url="https://app.fireflies.ai/view/TEST",
            source_type=CallSource.fireflies,
            status=CallStatus.pending,
            progress=5,
            progress_stage="Запуск...",
            title="Test Call",
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        # Check initial progress
        response1 = await client.get(
            f"/api/external/status/{call.id}",
            headers=get_auth_headers(admin_token)
        )
        data1 = response1.json()
        assert data1["progress"] == 5

        # Simulate progress update
        call.progress = 50
        call.progress_stage = "AI анализ..."
        await db_session.commit()
        await db_session.refresh(call)

        # Check updated progress
        response2 = await client.get(
            f"/api/external/status/{call.id}",
            headers=get_auth_headers(admin_token)
        )
        data2 = response2.json()
        assert data2["progress"] == 50
        assert data2["progress_stage"] == "AI анализ..."

    @pytest.mark.asyncio
    async def test_failed_status_resets_progress(
        self, client: AsyncClient, admin_token, get_auth_headers, db_session, organization, admin_user
    ):
        """Test that failed status shows 0 progress with error stage."""
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            source_url="https://app.fireflies.ai/view/TEST",
            source_type=CallSource.fireflies,
            status=CallStatus.failed,
            progress=0,
            progress_stage="Ошибка",
            error_message="Test error message",
            title="Test Call",
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        response = await client.get(
            f"/api/external/status/{call.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["progress"] == 0
        assert data["progress_stage"] == "Ошибка"
        assert data["error_message"] == "Test error message"
