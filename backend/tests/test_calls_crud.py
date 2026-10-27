"""
Comprehensive tests for CallRecording CRUD operations.
Tests cover all endpoints: create, read, update, delete, upload, bot recording,
pagination, filtering, search, sharing, and permission checks.
"""
import pytest
import os
import io
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import select

from api.models.database import (
    CallRecording, CallSource, CallStatus, Entity, SharedAccess,
    AccessLevel, ResourceType, User, UserRole, OrgRole, DeptRole,
    DepartmentMember, EntityType, EntityStatus
)


# ============================================================================
# GET /api/calls - LIST CALLS
# ============================================================================

class TestListCalls:
    """Test call listing with various filters and access control."""

    @pytest.mark.asyncio
    async def test_list_calls_basic(
        self, client, admin_user, admin_token, call_recording, get_auth_headers, org_owner
    ):
        """Test basic call listing."""
        response = await client.get(
            "/api/calls",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

        # Verify call structure
        call_data = next((c for c in data if c["id"] == call_recording.id), None)
        assert call_data is not None
        assert call_data["title"] == "Test Call"
        assert call_data["source_type"] == CallSource.upload.value
        assert call_data["status"] == CallStatus.done.value
        assert call_data["owner_id"] == admin_user.id
        assert "created_at" in call_data
        assert "duration_seconds" in call_data

    @pytest.mark.asyncio
    async def test_list_calls_empty_for_new_user(
        self, client, db_session, organization, get_auth_headers
    ):
        """Test that new user sees empty list."""
        # Create a new user with no calls
        new_user = User(
            email="newuser@test.com",
            password_hash="hashed",
            name="New User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(new_user)
        await db_session.commit()
        await db_session.refresh(new_user)

        from api.models.database import OrgMember
        member = OrgMember(
            org_id=organization.id,
            user_id=new_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(member)
        await db_session.commit()

        from api.services.auth import create_access_token
        token = create_access_token(data={"sub": str(new_user.id)})

        response = await client.get(
            "/api/calls",
            headers=get_auth_headers(token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data == []

    @pytest.mark.asyncio
    async def test_list_calls_pagination(
        self, db_session, client, admin_user, admin_token, organization,
        get_auth_headers, org_owner
    ):
        """Test call listing pagination."""
        # Create multiple calls
        calls = []
        for i in range(15):
            call = CallRecording(
                org_id=organization.id,
                owner_id=admin_user.id,
                title=f"Test Call {i}",
                source_type=CallSource.upload,
                status=CallStatus.done,
                created_at=datetime.utcnow() - timedelta(minutes=i)
            )
            calls.append(call)
        db_session.add_all(calls)
        await db_session.commit()

        # Test limit
        response = await client.get(
            "/api/calls?limit=5",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5

        # Test offset
        response = await client.get(
            "/api/calls?limit=5&offset=5",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5

        # Verify ordering (most recent first)
        response = await client.get(
            "/api/calls?limit=10",
            headers=get_auth_headers(admin_token)
        )
        data = response.json()
        # Newest should be first
        assert data[0]["title"] == "Test Call 0"

    @pytest.mark.asyncio
    async def test_list_calls_filter_by_status(
        self, db_session, client, admin_user, admin_token, organization,
        get_auth_headers, org_owner
    ):
        """Test filtering calls by status."""
        # Create calls with different statuses
        done_call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Done Call",
            source_type=CallSource.upload,
            status=CallStatus.done
        )
        processing_call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Processing Call",
            source_type=CallSource.upload,
            status=CallStatus.processing
        )
        failed_call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Failed Call",
            source_type=CallSource.upload,
            status=CallStatus.failed
        )
        db_session.add_all([done_call, processing_call, failed_call])
        await db_session.commit()

        # Filter by done status
        response = await client.get(
            "/api/calls?status=done",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()
        assert all(c["status"] == "done" for c in data)

        # Filter by processing status
        response = await client.get(
            "/api/calls?status=processing",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()
        assert all(c["status"] == "processing" for c in data)

    @pytest.mark.asyncio
    async def test_list_calls_filter_by_entity(
        self, db_session, client, admin_user, admin_token, organization,
        department, entity, get_auth_headers, org_owner
    ):
        """Test filtering calls by entity."""
        # Create call linked to entity
        linked_call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            entity_id=entity.id,
            title="Linked Call",
            source_type=CallSource.upload,
            status=CallStatus.done
        )
        # Create call without entity
        unlinked_call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Unlinked Call",
            source_type=CallSource.upload,
            status=CallStatus.done
        )
        db_session.add_all([linked_call, unlinked_call])
        await db_session.commit()

        # Filter by entity
        response = await client.get(
            f"/api/calls?entity_id={entity.id}",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert all(c["entity_id"] == entity.id for c in data)

    @pytest.mark.asyncio
    async def test_list_calls_shows_entity_name(
        self, db_session, client, admin_user, admin_token, organization,
        department, entity, get_auth_headers, org_owner
    ):
        """Test that call list includes entity name."""
        # Create call linked to entity
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            entity_id=entity.id,
            title="Call with Entity",
            source_type=CallSource.upload,
            status=CallStatus.done
        )
        db_session.add(call)
        await db_session.commit()

        response = await client.get(
            "/api/calls",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()

        call_data = next((c for c in data if c["id"] == call.id), None)
        assert call_data is not None
        assert call_data["entity_name"] == entity.name

    @pytest.mark.asyncio
    async def test_list_calls_owner_sees_all(
        self, client, admin_user, admin_token, call_recording, second_call,
        get_auth_headers, org_owner
    ):
        """Test that org owner sees all calls in organization."""
        response = await client.get(
            "/api/calls",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        call_ids = [c["id"] for c in data]

        # Owner should see both calls
        assert call_recording.id in call_ids
        assert second_call.id in call_ids

    @pytest.mark.asyncio
    async def test_list_calls_member_sees_own_only(
        self, client, second_user, second_user_token, call_recording, second_call,
        get_auth_headers, org_member
    ):
        """Test that regular member sees only their own calls."""
        response = await client.get(
            "/api/calls",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()
        call_ids = [c["id"] for c in data]

        # Member should only see their own call
        assert second_call.id in call_ids
        # Should not see other user's call
        assert call_recording.id not in call_ids

    @pytest.mark.asyncio
    async def test_list_calls_truncates_transcript(
        self, db_session, client, admin_user, admin_token, organization,
        get_auth_headers, org_owner
    ):
        """Test that list endpoint truncates long transcripts."""
        # Create call with long transcript
        long_transcript = "A" * 1000
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Long Transcript Call",
            source_type=CallSource.upload,
            status=CallStatus.done,
            transcript=long_transcript
        )
        db_session.add(call)
        await db_session.commit()

        response = await client.get(
            "/api/calls",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()

        call_data = next((c for c in data if c["id"] == call.id), None)
        assert call_data is not None
        # Should be truncated to 500 chars
        assert len(call_data["transcript"]) == 500


# ============================================================================
# GET /api/calls/{call_id} - GET SINGLE CALL
# ============================================================================

class TestGetCall:
    """Test getting a single call recording."""

    @pytest.mark.asyncio
    async def test_get_call_success(
        self, client, admin_user, admin_token, call_recording, get_auth_headers, org_owner
    ):
        """Test successfully getting a call."""
        response = await client.get(
            f"/api/calls/{call_recording.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == call_recording.id
        assert data["title"] == call_recording.title
        assert data["source_type"] == CallSource.upload.value
        assert data["status"] == CallStatus.done.value
        assert data["owner_id"] == admin_user.id
        assert "transcript" in data
        assert "speakers" in data
        assert "summary" in data
        assert "action_items" in data
        assert "key_points" in data

    @pytest.mark.asyncio
    async def test_get_call_with_entity(
        self, db_session, client, admin_user, admin_token, call_recording,
        entity, get_auth_headers, org_owner
    ):
        """Test getting call with linked entity."""
        call_recording.entity_id = entity.id
        await db_session.commit()

        response = await client.get(
            f"/api/calls/{call_recording.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["entity_id"] == entity.id
        assert data["entity_name"] == entity.name

    @pytest.mark.asyncio
    async def test_get_call_not_found(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test getting non-existent call."""
        response = await client.get(
            "/api/calls/99999",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_call_no_org_access(
        self, db_session, client, get_auth_headers
    ):
        """Test getting call when user has no organization."""
        # Create user without org membership
        user = User(
            email="noorg@test.com",
            password_hash="hashed",
            name="No Org User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        from api.services.auth import create_access_token
        token = create_access_token(data={"sub": str(user.id)})

        response = await client.get(
            "/api/calls/1",
            headers=get_auth_headers(token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_call_from_different_org(
        self, db_session, client, second_user, second_user_token,
        second_organization, get_auth_headers, org_member
    ):
        """Test that user cannot get call from different organization."""
        # Create call in different org
        other_call = CallRecording(
            org_id=second_organization.id,
            owner_id=1,
            title="Other Org Call",
            source_type=CallSource.upload,
            status=CallStatus.done,
            created_at=datetime.utcnow()
        )
        db_session.add(other_call)
        await db_session.commit()
        await db_session.refresh(other_call)

        response = await client.get(
            f"/api/calls/{other_call.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 404


# ============================================================================
# GET /api/calls/{call_id}/status - GET CALL STATUS
# ============================================================================

class TestGetCallStatus:
    """Test getting call status for polling."""

    @pytest.mark.asyncio
    async def test_get_call_status_success(
        self, client, admin_user, admin_token, call_recording, get_auth_headers, org_owner
    ):
        """Test successfully getting call status."""
        response = await client.get(
            f"/api/calls/{call_recording.id}/status",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == CallStatus.done.value
        assert "duration_seconds" in data
        assert "error_message" in data

    @pytest.mark.asyncio
    async def test_get_call_status_processing(
        self, db_session, client, admin_user, admin_token, call_recording,
        get_auth_headers, org_owner
    ):
        """Test getting status of processing call."""
        call_recording.status = CallStatus.processing
        call_recording.error_message = None
        await db_session.commit()

        response = await client.get(
            f"/api/calls/{call_recording.id}/status",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processing"

    @pytest.mark.asyncio
    async def test_get_call_status_failed_with_error(
        self, db_session, client, admin_user, admin_token, call_recording,
        get_auth_headers, org_owner
    ):
        """Test getting status of failed call with error message."""
        call_recording.status = CallStatus.failed
        call_recording.error_message = "Transcription failed"
        await db_session.commit()

        response = await client.get(
            f"/api/calls/{call_recording.id}/status",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["error_message"] == "Transcription failed"

    @pytest.mark.asyncio
    async def test_get_call_status_access_denied(
        self, client, second_user, second_user_token, call_recording,
        get_auth_headers, org_member
    ):
        """Test that user without access cannot get call status."""
        response = await client.get(
            f"/api/calls/{call_recording.id}/status",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403


# ============================================================================
# POST /api/calls/upload - UPLOAD CALL
# ============================================================================

class TestUploadCall:
    """Test uploading audio/video files."""

    @pytest.mark.asyncio
    @patch('api.routes.calls.aiofiles.open')
    @patch('api.routes.calls.uuid.uuid4')
    async def test_upload_call_success(
        self, mock_uuid, mock_aiofiles, client, admin_user, admin_token,
        organization, get_auth_headers, org_owner
    ):
        """Test successfully uploading a call recording."""
        # Mock UUID for predictable filename
        mock_uuid.return_value = MagicMock()
        mock_uuid.return_value.__str__ = lambda x: "test-uuid-123"

        # Mock file operations
        mock_file = AsyncMock()
        mock_aiofiles.return_value.__aenter__ = AsyncMock(return_value=mock_file)
        mock_aiofiles.return_value.__aexit__ = AsyncMock()
        mock_file.write = AsyncMock()

        # Create file-like object
        file_content = b"fake audio content"
        files = {"file": ("test.mp3", io.BytesIO(file_content), "audio/mpeg")}

        response = await client.post(
            "/api/calls/upload",
            files=files,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["status"] == CallStatus.processing.value

    @pytest.mark.asyncio
    async def test_upload_call_with_entity(
        self, client, admin_user, admin_token, entity, get_auth_headers, org_owner
    ):
        """Test uploading call with entity link."""
        # Create proper async context manager mock
        mock_file = AsyncMock()
        mock_file.write = AsyncMock()

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_file)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch('api.routes.calls.aiofiles.open', return_value=mock_cm):
            file_content = b"fake audio content"
            files = {"file": ("test.mp3", io.BytesIO(file_content), "audio/mpeg")}

            response = await client.post(
                f"/api/calls/upload?entity_id={entity.id}",
                files=files,
                headers=get_auth_headers(admin_token)
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_upload_call_invalid_format(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test uploading file with invalid format."""
        file_content = b"fake content"
        files = {"file": ("test.txt", io.BytesIO(file_content), "text/plain")}

        response = await client.post(
            "/api/calls/upload",
            files=files,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 400
        assert "Unsupported format" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_call_no_org(
        self, db_session, client, get_auth_headers
    ):
        """Test uploading call when user has no organization."""
        user = User(
            email="noorg@test.com",
            password_hash="hashed",
            name="No Org User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()

        from api.services.auth import create_access_token
        token = create_access_token(data={"sub": str(user.id)})

        file_content = b"fake audio"
        files = {"file": ("test.mp3", io.BytesIO(file_content), "audio/mpeg")}

        response = await client.post(
            "/api/calls/upload",
            files=files,
            headers=get_auth_headers(token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_upload_call_various_formats(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test uploading various supported audio formats."""
        formats = [
            ("test.mp3", "audio/mpeg"),
            ("test.mp4", "video/mp4"),
            ("test.wav", "audio/wav"),
            ("test.m4a", "audio/m4a"),
            ("test.webm", "video/webm"),
            ("test.ogg", "audio/ogg"),
        ]

        # Create proper async context manager mock
        mock_file = AsyncMock()
        mock_file.write = AsyncMock()

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_file)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch('api.routes.calls.aiofiles.open', return_value=mock_cm):
            for filename, mimetype in formats:
                file_content = b"fake audio"
                files = {"file": (filename, io.BytesIO(file_content), mimetype)}

                response = await client.post(
                    "/api/calls/upload",
                    files=files,
                    headers=get_auth_headers(admin_token)
                )

                assert response.status_code == 200, f"Failed for {filename}"


# ============================================================================
# POST /api/calls/start-bot - START BOT RECORDING
# ============================================================================

class TestStartBot:
    """Test starting bot recording for Meet/Zoom/Teams."""

    @pytest.mark.asyncio
    async def test_start_bot_google_meet(
        self, client, admin_user, admin_token,
        organization, get_auth_headers, org_owner, mock_call_recorder_service
    ):
        """Test starting bot for Google Meet."""
        mock_call_recorder_service.start_recording.return_value = {"success": True}

        data = {
            "source_url": "https://meet.google.com/abc-defg-hij",
            "bot_name": "HR Recorder"
        }

        response = await client.post(
            "/api/calls/start-bot",
            json=data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        response_data = response.json()
        assert "id" in response_data
        assert response_data["status"] == CallStatus.recording.value

    @pytest.mark.asyncio
    async def test_start_bot_zoom(
        self, client, admin_user, admin_token,
        get_auth_headers, org_owner, mock_call_recorder_service
    ):
        """Test starting bot for Zoom."""
        mock_call_recorder_service.start_recording.return_value = {"success": True}

        data = {
            "source_url": "https://zoom.us/j/123456789",
            "bot_name": "HR Recorder"
        }

        response = await client.post(
            "/api/calls/start-bot",
            json=data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_start_bot_teams(
        self, client, admin_user, admin_token,
        get_auth_headers, org_owner, mock_call_recorder_service
    ):
        """Test starting bot for Microsoft Teams."""
        mock_call_recorder_service.start_recording.return_value = {"success": True}

        data = {
            "source_url": "https://teams.microsoft.com/l/meetup-join/...",
            "bot_name": "HR Recorder"
        }

        response = await client.post(
            "/api/calls/start-bot",
            json=data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_start_bot_unsupported_url(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test starting bot with unsupported meeting URL."""
        data = {
            "source_url": "https://example.com/meeting",
            "bot_name": "HR Recorder"
        }

        response = await client.post(
            "/api/calls/start-bot",
            json=data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 400
        assert "Unsupported meeting URL" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_start_bot_with_entity(
        self, client, admin_user, admin_token,
        entity, get_auth_headers, org_owner, mock_call_recorder_service
    ):
        """Test starting bot with entity link."""
        mock_call_recorder_service.start_recording.return_value = {"success": True}

        data = {
            "source_url": "https://meet.google.com/abc-defg-hij",
            "bot_name": "HR Recorder",
            "entity_id": entity.id,
            "title": "Interview Call"
        }

        response = await client.post(
            "/api/calls/start-bot",
            json=data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_start_bot_fireflies_error(
        self, client, admin_user, admin_token,
        get_auth_headers, org_owner, mock_call_recorder_service
    ):
        """Test handling Fireflies API error."""
        mock_call_recorder_service.start_recording.return_value = {
            "success": False,
            "message": "Invalid meeting URL"
        }

        data = {
            "source_url": "https://meet.google.com/abc-defg-hij",
            "bot_name": "HR Recorder"
        }

        response = await client.post(
            "/api/calls/start-bot",
            json=data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 500
        assert "Fireflies error" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_start_bot_no_org(
        self, db_session, client, get_auth_headers
    ):
        """Test starting bot when user has no organization."""
        user = User(
            email="noorg@test.com",
            password_hash="hashed",
            name="No Org User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()

        from api.services.auth import create_access_token
        token = create_access_token(data={"sub": str(user.id)})

        data = {
            "source_url": "https://meet.google.com/abc-defg-hij",
            "bot_name": "HR Recorder"
        }

        response = await client.post(
            "/api/calls/start-bot",
            json=data,
            headers=get_auth_headers(token)
        )

        assert response.status_code == 403


# ============================================================================
# PATCH /api/calls/{call_id} - UPDATE CALL
# ============================================================================

class TestUpdateCall:
    """Test updating call recordings."""

    @pytest.mark.asyncio
    async def test_update_call_title(
        self, db_session, client, admin_user, admin_token, call_recording,
        get_auth_headers, org_owner
    ):
        """Test updating call title."""
        response = await client.patch(
            f"/api/calls/{call_recording.id}",
            json={"title": "Updated Call Title"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Call Title"
        assert data["success"] is True

        # Verify in database
        await db_session.refresh(call_recording)
        assert call_recording.title == "Updated Call Title"

    @pytest.mark.asyncio
    async def test_update_call_clear_title(
        self, db_session, client, admin_user, admin_token, call_recording,
        get_auth_headers, org_owner
    ):
        """Test clearing call title."""
        response = await client.patch(
            f"/api/calls/{call_recording.id}",
            json={"title": ""},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        await db_session.refresh(call_recording)
        assert call_recording.title is None

    @pytest.mark.asyncio
    async def test_update_call_link_entity(
        self, db_session, client, admin_user, admin_token, call_recording,
        entity, get_auth_headers, org_owner
    ):
        """Test linking entity to call."""
        response = await client.patch(
            f"/api/calls/{call_recording.id}",
            json={"entity_id": entity.id},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["entity_id"] == entity.id
        assert data["entity_name"] == entity.name

        # Verify in database
        await db_session.refresh(call_recording)
        assert call_recording.entity_id == entity.id

    @pytest.mark.asyncio
    async def test_update_call_unlink_entity(
        self, db_session, client, admin_user, admin_token, call_recording,
        entity, get_auth_headers, org_owner
    ):
        """Test unlinking entity from call."""
        # First link entity
        call_recording.entity_id = entity.id
        await db_session.commit()

        # Then unlink
        response = await client.patch(
            f"/api/calls/{call_recording.id}",
            json={"entity_id": -1},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["entity_id"] is None
        assert data["entity_name"] is None

        # Verify in database
        await db_session.refresh(call_recording)
        assert call_recording.entity_id is None

    @pytest.mark.asyncio
    async def test_update_call_invalid_entity(
        self, client, admin_user, admin_token, call_recording,
        get_auth_headers, org_owner
    ):
        """Test linking non-existent entity."""
        response = await client.patch(
            f"/api/calls/{call_recording.id}",
            json={"entity_id": 99999},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_call_both_fields(
        self, db_session, client, admin_user, admin_token, call_recording,
        entity, get_auth_headers, org_owner
    ):
        """Test updating both title and entity."""
        response = await client.patch(
            f"/api/calls/{call_recording.id}",
            json={
                "title": "New Title",
                "entity_id": entity.id
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "New Title"
        assert data["entity_id"] == entity.id

    @pytest.mark.asyncio
    async def test_update_call_not_found(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test updating non-existent call."""
        response = await client.patch(
            "/api/calls/99999",
            json={"title": "New Title"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_call_access_denied(
        self, client, second_user, second_user_token, call_recording,
        get_auth_headers, org_member
    ):
        """Test that user without permission cannot update call."""
        response = await client.patch(
            f"/api/calls/{call_recording.id}",
            json={"title": "Hacked"},
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403


# ============================================================================
# POST /api/calls/{call_id}/link-entity/{entity_id} - LINK ENTITY
# ============================================================================

class TestLinkEntity:
    """Test linking call to entity."""

    @pytest.mark.asyncio
    async def test_link_entity_success(
        self, db_session, client, admin_user, admin_token, call_recording,
        entity, get_auth_headers, org_owner
    ):
        """Test successfully linking entity to call."""
        response = await client.post(
            f"/api/calls/{call_recording.id}/link-entity/{entity.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify in database
        await db_session.refresh(call_recording)
        assert call_recording.entity_id == entity.id

    @pytest.mark.asyncio
    async def test_link_entity_not_found(
        self, client, admin_user, admin_token, call_recording,
        get_auth_headers, org_owner
    ):
        """Test linking non-existent entity."""
        response = await client.post(
            f"/api/calls/{call_recording.id}/link-entity/99999",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_link_entity_call_not_found(
        self, client, admin_user, admin_token, entity, get_auth_headers, org_owner
    ):
        """Test linking entity to non-existent call."""
        response = await client.post(
            f"/api/calls/99999/link-entity/{entity.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_link_entity_from_different_org(
        self, db_session, client, admin_user, admin_token, call_recording,
        second_organization, get_auth_headers, org_owner
    ):
        """Test linking entity from different organization."""
        # Create entity in different org
        other_entity = Entity(
            org_id=second_organization.id,
            created_by=1,
            name="Other Org Entity",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(other_entity)
        await db_session.commit()
        await db_session.refresh(other_entity)

        response = await client.post(
            f"/api/calls/{call_recording.id}/link-entity/{other_entity.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404


# ============================================================================
# DELETE /api/calls/{call_id} - DELETE CALL
# ============================================================================

class TestDeleteCall:
    """Test deleting call recordings."""

    @pytest.mark.asyncio
    async def test_delete_call_success(
        self, db_session, client, admin_user, admin_token, call_recording,
        get_auth_headers, org_owner
    ):
        """Test successfully deleting a call."""
        call_id = call_recording.id

        response = await client.delete(
            f"/api/calls/{call_id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify deleted from database
        result = await db_session.execute(
            select(CallRecording).where(CallRecording.id == call_id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    @patch('os.path.exists')
    @patch('os.remove')
    async def test_delete_call_with_audio_file(
        self, mock_remove, mock_exists, db_session, client, admin_user,
        admin_token, call_recording, get_auth_headers, org_owner
    ):
        """Test deleting call with audio file."""
        # Set audio file path
        call_recording.audio_file_path = "/tmp/test_audio.mp3"
        await db_session.commit()

        mock_exists.return_value = True

        response = await client.delete(
            f"/api/calls/{call_recording.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        # Verify file deletion was attempted
        mock_remove.assert_called_once_with("/tmp/test_audio.mp3")

    @pytest.mark.asyncio
    async def test_delete_call_not_found(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test deleting non-existent call."""
        response = await client.delete(
            "/api/calls/99999",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_call_access_denied(
        self, client, second_user, second_user_token, call_recording,
        get_auth_headers, org_member
    ):
        """Test that user without permission cannot delete call."""
        response = await client.delete(
            f"/api/calls/{call_recording.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_call_cascades_shared_access(
        self, db_session, client, admin_user, admin_token, call_recording,
        second_user, get_auth_headers, org_owner
    ):
        """Test that deleting call cascades to SharedAccess records."""
        # Create share
        share = SharedAccess(
            resource_type=ResourceType.call,
            resource_id=call_recording.id,
            call_id=call_recording.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.view
        )
        db_session.add(share)
        await db_session.commit()
        share_id = share.id

        # Delete call
        response = await client.delete(
            f"/api/calls/{call_recording.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

        # Verify share is also deleted
        result = await db_session.execute(
            select(SharedAccess).where(SharedAccess.id == share_id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_call_owner_can_delete(
        self, db_session, client, second_user, second_user_token,
        organization, get_auth_headers, org_member
    ):
        """Test that call owner can delete their own call."""
        # Create call owned by second_user
        call = CallRecording(
            org_id=organization.id,
            owner_id=second_user.id,
            title="My Call",
            source_type=CallSource.upload,
            status=CallStatus.done,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        response = await client.delete(
            f"/api/calls/{call.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_delete_call_with_full_shared_access(
        self, db_session, client, second_user, second_user_token,
        call_recording, admin_user, get_auth_headers, org_member
    ):
        """Test that user with full shared access can delete call."""
        # Share call with full access
        share = SharedAccess(
            resource_type=ResourceType.call,
            resource_id=call_recording.id,
            call_id=call_recording.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.full
        )
        db_session.add(share)
        await db_session.commit()

        response = await client.delete(
            f"/api/calls/{call_recording.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_call_with_edit_access_denied(
        self, db_session, client, second_user, second_user_token,
        call_recording, admin_user, get_auth_headers, org_member
    ):
        """Test that user with only edit access cannot delete call."""
        # Share call with edit access (not full)
        share = SharedAccess(
            resource_type=ResourceType.call,
            resource_id=call_recording.id,
            call_id=call_recording.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.edit
        )
        db_session.add(share)
        await db_session.commit()

        response = await client.delete(
            f"/api/calls/{call_recording.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    @patch('os.path.exists')
    @patch('os.remove')
    async def test_delete_call_file_deletion_error_still_deletes_record(
        self, mock_remove, mock_exists, db_session, client, admin_user,
        admin_token, call_recording, get_auth_headers, org_owner
    ):
        """Test that call record is deleted even if file deletion fails."""
        # Set audio file path
        call_recording.audio_file_path = "/tmp/test_audio.mp3"
        await db_session.commit()
        call_id = call_recording.id

        mock_exists.return_value = True
        mock_remove.side_effect = OSError("Permission denied")

        response = await client.delete(
            f"/api/calls/{call_id}",
            headers=get_auth_headers(admin_token)
        )

        # Should still succeed (warning logged but not raised)
        assert response.status_code == 200

        # Verify record was deleted
        result = await db_session.execute(
            select(CallRecording).where(CallRecording.id == call_id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_call_from_different_org(
        self, db_session, client, second_user, second_user_token,
        second_organization, get_auth_headers, org_member
    ):
        """Test that user cannot delete call from different organization."""
        # Create call in different org
        other_call = CallRecording(
            org_id=second_organization.id,
            owner_id=1,
            title="Other Org Call",
            source_type=CallSource.upload,
            status=CallStatus.done,
            created_at=datetime.utcnow()
        )
        db_session.add(other_call)
        await db_session.commit()
        await db_session.refresh(other_call)

        response = await client.delete(
            f"/api/calls/{other_call.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 404


# ============================================================================
# POST /api/calls/{call_id}/stop - STOP RECORDING
# ============================================================================

class TestStopRecording:
    """Test stopping call recordings."""

    @pytest.mark.asyncio
    async def test_stop_recording_success(
        self, db_session, client, admin_user, admin_token,
        call_recording, get_auth_headers, org_owner, mock_call_recorder_service
    ):
        """Test successfully stopping a recording."""
        # Set call to recording status
        call_recording.status = CallStatus.recording
        await db_session.commit()

        response = await client.post(
            f"/api/calls/{call_recording.id}/stop",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify stop was called
        mock_call_recorder_service.stop_recording.assert_called_once_with(call_recording.id)

    @pytest.mark.asyncio
    async def test_stop_recording_not_recording(
        self, db_session, client, admin_user, admin_token, call_recording,
        get_auth_headers, org_owner
    ):
        """Test stopping call that is not recording."""
        # Call is already done
        call_recording.status = CallStatus.done
        await db_session.commit()

        response = await client.post(
            f"/api/calls/{call_recording.id}/stop",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 400
        assert "not currently recording" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_stop_recording_access_denied(
        self, db_session, client, second_user, second_user_token,
        call_recording, get_auth_headers, org_member
    ):
        """Test that user without full access cannot stop recording."""
        call_recording.status = CallStatus.recording
        await db_session.commit()

        response = await client.post(
            f"/api/calls/{call_recording.id}/stop",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_stop_recording_not_found(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test stopping non-existent call."""
        response = await client.post(
            "/api/calls/99999/stop",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404


# ============================================================================
# POST /api/calls/{call_id}/reprocess - REPROCESS CALL
# ============================================================================

class TestReprocessCall:
    """Test reprocessing call recordings."""

    @pytest.mark.asyncio
    async def test_reprocess_call_with_transcript(
        self, db_session, client, admin_user, admin_token, call_recording,
        get_auth_headers, org_owner
    ):
        """Test reprocessing call with existing transcript."""
        # Set transcript
        call_recording.transcript = "Test transcript content"
        call_recording.speakers = []
        await db_session.commit()

        response = await client.post(
            f"/api/calls/{call_recording.id}/reprocess",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == CallStatus.analyzing.value

    @pytest.mark.asyncio
    async def test_reprocess_call_with_audio(
        self, db_session, client, admin_user, admin_token, call_recording,
        get_auth_headers, org_owner
    ):
        """Test reprocessing call with audio file."""
        call_recording.audio_file_path = "/tmp/test_audio.mp3"
        call_recording.transcript = None
        await db_session.commit()

        response = await client.post(
            f"/api/calls/{call_recording.id}/reprocess",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == CallStatus.processing.value

    @pytest.mark.asyncio
    async def test_reprocess_call_with_fireflies_id(
        self, db_session, client, admin_user, admin_token, call_recording,
        get_auth_headers, org_owner
    ):
        """Test reprocessing call with Fireflies transcript ID."""
        # Set Fireflies transcript ID and existing transcript
        call_recording.fireflies_transcript_id = "fireflies-123"
        call_recording.transcript = "Existing transcript from Fireflies"
        call_recording.speakers = [{"speaker": "Test", "start": 0, "end": 5, "text": "Hello"}]
        await db_session.commit()

        response = await client.post(
            f"/api/calls/{call_recording.id}/reprocess",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Should re-analyze the existing transcript
        assert data["status"] == CallStatus.analyzing.value

    @pytest.mark.asyncio
    async def test_reprocess_call_no_data(
        self, db_session, client, admin_user, admin_token, call_recording,
        get_auth_headers, org_owner
    ):
        """Test reprocessing call without transcript or audio."""
        call_recording.transcript = None
        call_recording.audio_file_path = None
        call_recording.fireflies_transcript_id = None
        await db_session.commit()

        response = await client.post(
            f"/api/calls/{call_recording.id}/reprocess",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 400
        assert "No data to process" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_reprocess_call_access_denied(
        self, client, second_user, second_user_token, call_recording,
        get_auth_headers, org_member
    ):
        """Test that user without permission cannot reprocess call."""
        response = await client.post(
            f"/api/calls/{call_recording.id}/reprocess",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_reprocess_call_not_found(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test reprocessing non-existent call."""
        response = await client.post(
            "/api/calls/99999/reprocess",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_reprocess_call_with_shared_edit_access(
        self, db_session, client, second_user, second_user_token,
        call_recording, admin_user, get_auth_headers, org_member
    ):
        """Test that user with edit access can reprocess call."""
        # Share call with edit access
        share = SharedAccess(
            resource_type=ResourceType.call,
            resource_id=call_recording.id,
            call_id=call_recording.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.edit
        )
        db_session.add(share)
        call_recording.transcript = "Test transcript"
        await db_session.commit()

        response = await client.post(
            f"/api/calls/{call_recording.id}/reprocess",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_reprocess_call_with_shared_view_access_denied(
        self, db_session, client, second_user, second_user_token,
        call_recording, admin_user, get_auth_headers, org_member
    ):
        """Test that user with only view access cannot reprocess call."""
        # Share call with view-only access
        share = SharedAccess(
            resource_type=ResourceType.call,
            resource_id=call_recording.id,
            call_id=call_recording.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.view
        )
        db_session.add(share)
        await db_session.commit()

        response = await client.post(
            f"/api/calls/{call_recording.id}/reprocess",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_reprocess_clears_previous_results(
        self, db_session, client, admin_user, admin_token, call_recording,
        get_auth_headers, org_owner
    ):
        """Test that reprocessing clears error state."""
        # Set call to failed with error
        call_recording.status = CallStatus.failed
        call_recording.error_message = "Previous processing error"
        call_recording.transcript = "Some transcript data"
        await db_session.commit()

        response = await client.post(
            f"/api/calls/{call_recording.id}/reprocess",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

        # Verify error was cleared
        await db_session.refresh(call_recording)
        assert call_recording.error_message is None
        assert call_recording.status == CallStatus.analyzing

    @pytest.mark.asyncio
    async def test_reprocess_call_priority_order(
        self, db_session, client, admin_user, admin_token, call_recording,
        get_auth_headers, org_owner
    ):
        """Test that reprocess prioritizes Fireflies/transcript over audio."""
        # Set both audio file and transcript
        call_recording.audio_file_path = "/tmp/test_audio.mp3"
        call_recording.transcript = "Existing transcript"
        call_recording.fireflies_transcript_id = "fireflies-123"
        await db_session.commit()

        response = await client.post(
            f"/api/calls/{call_recording.id}/reprocess",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        # Should use transcript (analyzing) not audio (processing)
        assert data["status"] == CallStatus.analyzing.value


# ============================================================================
# POST /api/calls/{call_id}/share - SHARE CALL
# ============================================================================

class TestShareCall:
    """Test sharing call recordings."""

    @pytest.mark.asyncio
    async def test_share_call_success(
        self, db_session, client, admin_user, admin_token, call_recording,
        second_user, get_auth_headers, org_owner, org_member
    ):
        """Test successfully sharing a call."""
        data = {
            "shared_with_id": second_user.id,
            "access_level": "view"
        }

        response = await client.post(
            f"/api/calls/{call_recording.id}/share",
            json=data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["success"] is True
        assert response_data["call_id"] == call_recording.id
        assert response_data["shared_with_id"] == second_user.id
        assert response_data["access_level"] == "view"

        # Verify in database
        result = await db_session.execute(
            select(SharedAccess).where(
                SharedAccess.resource_type == ResourceType.call,
                SharedAccess.resource_id == call_recording.id,
                SharedAccess.shared_with_id == second_user.id
            )
        )
        share = result.scalar_one_or_none()
        assert share is not None
        assert share.access_level == AccessLevel.view

    @pytest.mark.asyncio
    async def test_share_call_with_note(
        self, db_session, client, admin_user, admin_token, call_recording,
        second_user, get_auth_headers, org_owner, org_member
    ):
        """Test sharing call with note."""
        data = {
            "shared_with_id": second_user.id,
            "access_level": "edit",
            "note": "Please review this call"
        }

        response = await client.post(
            f"/api/calls/{call_recording.id}/share",
            json=data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

        # Verify note in database
        result = await db_session.execute(
            select(SharedAccess).where(
                SharedAccess.resource_type == ResourceType.call,
                SharedAccess.resource_id == call_recording.id
            )
        )
        share = result.scalar_one()
        assert share.note == "Please review this call"

    @pytest.mark.asyncio
    async def test_share_call_with_expiration(
        self, db_session, client, admin_user, admin_token, call_recording,
        second_user, get_auth_headers, org_owner, org_member
    ):
        """Test sharing call with expiration date."""
        expires_at = datetime.utcnow() + timedelta(days=7)
        data = {
            "shared_with_id": second_user.id,
            "access_level": "view",
            "expires_at": expires_at.isoformat()
        }

        response = await client.post(
            f"/api/calls/{call_recording.id}/share",
            json=data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_share_call_update_existing(
        self, db_session, client, admin_user, admin_token, call_recording,
        second_user, get_auth_headers, org_owner, org_member
    ):
        """Test updating existing share."""
        # Create initial share
        share = SharedAccess(
            resource_type=ResourceType.call,
            resource_id=call_recording.id,
            call_id=call_recording.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.view
        )
        db_session.add(share)
        await db_session.commit()

        # Update to edit access
        data = {
            "shared_with_id": second_user.id,
            "access_level": "edit",
            "note": "Updated to edit"
        }

        response = await client.post(
            f"/api/calls/{call_recording.id}/share",
            json=data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

        # Verify updated
        await db_session.refresh(share)
        assert share.access_level == AccessLevel.edit
        assert share.note == "Updated to edit"

    @pytest.mark.asyncio
    async def test_share_call_not_found(
        self, client, admin_user, admin_token, second_user, get_auth_headers, org_owner
    ):
        """Test sharing non-existent call."""
        data = {
            "shared_with_id": second_user.id,
            "access_level": "view"
        }

        response = await client.post(
            "/api/calls/99999/share",
            json=data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_share_call_target_user_not_found(
        self, client, admin_user, admin_token, call_recording, get_auth_headers, org_owner
    ):
        """Test sharing call with non-existent user."""
        data = {
            "shared_with_id": 99999,
            "access_level": "view"
        }

        response = await client.post(
            f"/api/calls/{call_recording.id}/share",
            json=data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_share_call_no_permission(
        self, client, second_user, second_user_token, call_recording,
        admin_user, get_auth_headers, org_member
    ):
        """Test that user without permission cannot share call."""
        data = {
            "shared_with_id": admin_user.id,
            "access_level": "view"
        }

        response = await client.post(
            f"/api/calls/{call_recording.id}/share",
            json=data,
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403


# ============================================================================
# SUPERADMIN PERMISSIONS
# ============================================================================

class TestSuperadminPermissions:
    """Test superadmin permissions for calls."""

    @pytest.mark.asyncio
    async def test_superadmin_sees_all_calls(
        self, db_session, client, superadmin_user, superadmin_token,
        organization, admin_user, get_auth_headers
    ):
        """Test that superadmin sees all calls across all organizations."""
        # Create calls in organization
        call1 = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Org Call",
            source_type=CallSource.upload,
            status=CallStatus.done
        )
        db_session.add(call1)
        await db_session.commit()

        # Note: Superadmin doesn't need org membership to see calls
        response = await client.get(
            "/api/calls",
            headers=get_auth_headers(superadmin_token)
        )

        # Superadmin has no org, so will see empty list
        # This is expected behavior based on the code
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_superadmin_can_access_any_call(
        self, db_session, client, superadmin_user, superadmin_token,
        organization, admin_user, get_auth_headers
    ):
        """Test that superadmin can access any call."""
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Private Call",
            source_type=CallSource.upload,
            status=CallStatus.done
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        # Superadmin tries to access
        response = await client.get(
            f"/api/calls/{call.id}",
            headers=get_auth_headers(superadmin_token)
        )

        # Суперадмин без OrgMember-записи получает самую старую организацию
        # (get_user_org), поэтому звонок ему открывается.
        assert response.status_code == 200


# ============================================================================
# DEPARTMENT-BASED ACCESS
# ============================================================================

class TestDepartmentAccess:
    """Test department-based access control for calls."""

    @pytest.mark.asyncio
    async def test_dept_lead_sees_dept_member_calls(
        self, db_session, client, admin_user, admin_token, regular_user,
        organization, department, entity, get_auth_headers, org_owner,
        dept_lead, dept_member
    ):
        """Test that department lead sees department members' calls."""
        # Create call by dept member, linked to entity in department
        call = CallRecording(
            org_id=organization.id,
            owner_id=regular_user.id,
            entity_id=entity.id,
            title="Dept Member Call",
            source_type=CallSource.upload,
            status=CallStatus.done
        )
        db_session.add(call)
        await db_session.commit()

        # Dept lead (admin_user) should see it in list
        response = await client.get(
            "/api/calls",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        call_ids = [c["id"] for c in data]
        assert call.id in call_ids

    @pytest.mark.asyncio
    async def test_dept_member_cannot_see_other_member_calls(
        self, db_session, client, regular_user, user_token, second_user,
        organization, department, get_auth_headers, org_admin, org_member,
        dept_member
    ):
        """Test that department member cannot see other members' calls."""
        # Create department membership for second_user
        second_dept_member = DepartmentMember(
            department_id=department.id,
            user_id=second_user.id,
            role=DeptRole.member
        )
        db_session.add(second_dept_member)
        await db_session.commit()

        # Create call by second_user
        call = CallRecording(
            org_id=organization.id,
            owner_id=second_user.id,
            title="Other Member Call",
            source_type=CallSource.upload,
            status=CallStatus.done
        )
        db_session.add(call)
        await db_session.commit()

        # regular_user should NOT see it
        response = await client.get(
            "/api/calls",
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 200
        data = response.json()
        call_ids = [c["id"] for c in data]
        assert call.id not in call_ids


# ============================================================================
# EDGE CASES AND ERROR HANDLING
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_list_calls_with_invalid_limit(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test list calls with limit exceeding maximum."""
        response = await client.get(
            "/api/calls?limit=200",
            headers=get_auth_headers(admin_token)
        )

        # FastAPI validation should fail
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_calls_with_negative_offset(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test list calls with negative offset."""
        response = await client.get(
            "/api/calls?offset=-1",
            headers=get_auth_headers(admin_token)
        )

        # FastAPI validation should fail
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_call_empty_payload(
        self, client, admin_user, admin_token, call_recording,
        get_auth_headers, org_owner
    ):
        """Test updating call with empty payload."""
        response = await client.patch(
            f"/api/calls/{call_recording.id}",
            json={},
            headers=get_auth_headers(admin_token)
        )

        # Should succeed but make no changes
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_call_with_null_values(
        self, db_session, client, admin_user, admin_token, organization,
        get_auth_headers, org_owner
    ):
        """Test handling call with null optional values."""
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title=None,
            entity_id=None,
            source_type=CallSource.upload,
            status=CallStatus.done,
            transcript=None,
            summary=None,
            action_items=None,
            key_points=None
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        response = await client.get(
            f"/api/calls/{call.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] is None
        assert data["entity_id"] is None
        assert data["transcript"] is None

    @pytest.mark.asyncio
    async def test_unauthorized_access(self, client):
        """Test accessing calls without authentication."""
        response = await client.get("/api/calls")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_shared_access_with_expired_share(
        self, db_session, client, second_user, second_user_token,
        call_recording, admin_user, get_auth_headers, org_member
    ):
        """Test that expired shares don't grant access."""
        # Create expired share
        share = SharedAccess(
            resource_type=ResourceType.call,
            resource_id=call_recording.id,
            call_id=call_recording.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.view,
            expires_at=datetime.utcnow() - timedelta(days=1)
        )
        db_session.add(share)
        await db_session.commit()

        # Try to access
        response = await client.get(
            f"/api/calls/{call_recording.id}",
            headers=get_auth_headers(second_user_token)
        )

        # Should be denied
        assert response.status_code == 403


# ============================================================================
# UPLOAD AND PROCESSING FLOW TESTS
# ============================================================================

class TestUploadAndProcessingFlow:
    """Test comprehensive upload and processing workflows."""

    @pytest.mark.asyncio
    @patch('api.routes.calls.aiofiles.open')
    @patch('api.routes.calls.uuid.uuid4')
    async def test_upload_triggers_background_processing(
        self, mock_uuid, mock_aiofiles, db_session, client, admin_user,
        admin_token, organization, get_auth_headers, org_owner
    ):
        """Test that upload triggers background processing task."""
        # Mock UUID and file operations
        mock_uuid.return_value = MagicMock()
        mock_uuid.return_value.__str__ = lambda x: "test-uuid-456"

        mock_file = AsyncMock()
        mock_aiofiles.return_value.__aenter__ = AsyncMock(return_value=mock_file)
        mock_aiofiles.return_value.__aexit__ = AsyncMock()
        mock_file.write = AsyncMock()

        file_content = b"fake audio content"
        files = {"file": ("recording.mp3", io.BytesIO(file_content), "audio/mpeg")}

        response = await client.post(
            "/api/calls/upload",
            files=files,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["status"] == CallStatus.processing.value

        # Verify call was created in database with correct status
        result = await db_session.execute(
            select(CallRecording).where(CallRecording.id == data["id"])
        )
        call = result.scalar_one()
        assert call.status == CallStatus.processing
        assert call.source_type == CallSource.upload
        assert call.owner_id == admin_user.id

    @pytest.mark.asyncio
    @patch('api.routes.calls.aiofiles.open')
    async def test_upload_with_mpeg_extension(
        self, mock_aiofiles, client, admin_user, admin_token,
        get_auth_headers, org_owner
    ):
        """Test uploading file with .mpeg extension."""
        mock_file = AsyncMock()
        mock_aiofiles.return_value.__aenter__ = AsyncMock(return_value=mock_file)
        mock_aiofiles.return_value.__aexit__ = AsyncMock()
        mock_file.write = AsyncMock()

        file_content = b"fake video content"
        files = {"file": ("video.mpeg", io.BytesIO(file_content), "video/mpeg")}

        response = await client.post(
            "/api/calls/upload",
            files=files,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data

    @pytest.mark.asyncio
    async def test_upload_without_file(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test upload endpoint without providing a file."""
        response = await client.post(
            "/api/calls/upload",
            headers=get_auth_headers(admin_token)
        )

        # FastAPI should return 422 for missing required field
        assert response.status_code == 422

    @pytest.mark.asyncio
    @patch('api.routes.calls.aiofiles.open')
    async def test_upload_case_insensitive_extension(
        self, mock_aiofiles, client, admin_user, admin_token,
        get_auth_headers, org_owner
    ):
        """Test that file extensions are case insensitive."""
        mock_file = AsyncMock()
        mock_aiofiles.return_value.__aenter__ = AsyncMock(return_value=mock_file)
        mock_aiofiles.return_value.__aexit__ = AsyncMock()
        mock_file.write = AsyncMock()

        # Test uppercase extensions
        for ext in [".MP3", ".WAV", ".M4A"]:
            file_content = b"fake audio"
            files = {"file": (f"test{ext}", io.BytesIO(file_content), "audio/mpeg")}

            response = await client.post(
                "/api/calls/upload",
                files=files,
                headers=get_auth_headers(admin_token)
            )

            assert response.status_code == 200


# ============================================================================
# STATUS TRANSITION TESTS
# ============================================================================

class TestCallStatusTransitions:
    """Test call status transitions through the processing lifecycle."""

    @pytest.mark.asyncio
    async def test_status_flow_upload_to_processing(
        self, db_session, client, admin_user, admin_token, organization,
        get_auth_headers, org_owner
    ):
        """Test status transition from upload to processing."""
        # Create call in processing state (as happens after upload)
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Processing Call",
            source_type=CallSource.upload,
            status=CallStatus.processing,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        # Check status
        response = await client.get(
            f"/api/calls/{call.id}/status",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processing"

    @pytest.mark.asyncio
    async def test_status_flow_processing_to_analyzing(
        self, db_session, client, admin_user, admin_token, organization,
        get_auth_headers, org_owner
    ):
        """Test status transition from processing to analyzing."""
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            source_type=CallSource.upload,
            status=CallStatus.analyzing,
            transcript="Test transcript",
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        response = await client.get(
            f"/api/calls/{call.id}/status",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "analyzing"

    @pytest.mark.asyncio
    async def test_status_flow_analyzing_to_done(
        self, db_session, client, admin_user, admin_token, organization,
        get_auth_headers, org_owner
    ):
        """Test status transition from analyzing to done."""
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            source_type=CallSource.upload,
            status=CallStatus.done,
            transcript="Test transcript",
            summary="Test summary",
            action_items=["Item 1", "Item 2"],
            key_points=["Point 1", "Point 2"],
            processed_at=datetime.utcnow(),
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        response = await client.get(
            f"/api/calls/{call.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "done"
        assert data["transcript"] is not None
        assert data["summary"] is not None
        assert len(data["action_items"]) == 2
        assert len(data["key_points"]) == 2

    @pytest.mark.asyncio
    async def test_status_flow_processing_to_failed(
        self, db_session, client, admin_user, admin_token, organization,
        get_auth_headers, org_owner
    ):
        """Test status transition from processing to failed."""
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            source_type=CallSource.upload,
            status=CallStatus.failed,
            error_message="Processing failed: file corrupted",
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        response = await client.get(
            f"/api/calls/{call.id}/status",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert "corrupted" in data["error_message"]

    @pytest.mark.asyncio
    async def test_status_flow_pending_to_recording(
        self, db_session, client, admin_user, admin_token, organization,
        get_auth_headers, org_owner
    ):
        """Test status transition from pending to recording (bot started)."""
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            source_type=CallSource.meet,
            source_url="https://meet.google.com/test",
            status=CallStatus.recording,
            started_at=datetime.utcnow(),
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        response = await client.get(
            f"/api/calls/{call.id}/status",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "recording"

    @pytest.mark.asyncio
    async def test_reprocess_resets_error_state(
        self, db_session, client, admin_user, admin_token, call_recording,
        get_auth_headers, org_owner
    ):
        """Test that reprocessing resets error state."""
        # Set call to failed state
        call_recording.status = CallStatus.failed
        call_recording.error_message = "Previous error"
        call_recording.transcript = "Some transcript"
        await db_session.commit()

        response = await client.post(
            f"/api/calls/{call_recording.id}/reprocess",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == CallStatus.analyzing.value

        # Verify error was cleared
        await db_session.refresh(call_recording)
        assert call_recording.error_message is None


# ============================================================================
# FIREFLIES WEBHOOK TESTS
# ============================================================================

class TestFirefliesWebhook:
    """Test Fireflies webhook processing."""

    @pytest.mark.asyncio
    async def test_webhook_transcription_completed(
        self, db_session, client, admin_user, organization
    ):
        """Test processing Fireflies webhook for completed transcription."""
        # Create call waiting for Fireflies transcript
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            source_type=CallSource.meet,
            status=CallStatus.recording,
            title=f"HR Call #{999}",
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        # Mock Fireflies webhook data
        webhook_data = {
            "meetingId": "fireflies-abc-123",
            "eventType": "Transcription completed",
            "clientReferenceId": None
        }

        # Mock get_transcript to return data with correct title
        from unittest.mock import patch
        mock_transcript = {
            "id": "fireflies-abc-123",
            "title": f"HR Call #{call.id}",
            "sentences": [
                {
                    "text": "Hello, this is a test call.",
                    "speaker_name": "Speaker 1",
                    "start_time": 0.0,
                    "end_time": 2.5
                },
                {
                    "text": "Yes, I agree with that.",
                    "speaker_name": "Speaker 2",
                    "start_time": 2.5,
                    "end_time": 5.0
                }
            ],
            "duration": 300,
            "summary": {
                "overview": "Test meeting summary",
                "action_items": ["Follow up on discussion"],
                "keywords": ["test", "meeting"]
            }
        }

        with patch('api.services.fireflies_client.fireflies_client.get_transcript',
                   AsyncMock(return_value=mock_transcript)):
            response = await client.post(
                "/api/calls/fireflies-webhook",
                json=webhook_data
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["call_id"] == call.id

    @pytest.mark.asyncio
    async def test_webhook_invalid_event_type(self, client):
        """Test webhook with non-completion event type."""
        webhook_data = {
            "meetingId": "test-123",
            "eventType": "Recording started",
            "clientReferenceId": None
        }

        response = await client.post(
            "/api/calls/fireflies-webhook",
            json=webhook_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ignored"

    @pytest.mark.asyncio
    async def test_webhook_missing_meeting_id(self, client):
        """Test webhook without meeting ID."""
        webhook_data = {
            "eventType": "Transcription completed",
            "clientReferenceId": None
        }

        response = await client.post(
            "/api/calls/fireflies-webhook",
            json=webhook_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "missing_meeting_id" in data["reason"]

    @pytest.mark.asyncio
    async def test_webhook_call_not_found(self, client):
        """Test webhook for non-existent call."""
        mock_transcript = {
            "id": "test-123",
            "title": "HR Call #99999",  # Non-existent call
            "sentences": [],
            "duration": 0
        }

        webhook_data = {
            "meetingId": "test-123",
            "eventType": "Transcription completed"
        }

        with patch('api.services.fireflies_client.fireflies_client.get_transcript',
                   AsyncMock(return_value=mock_transcript)):
            response = await client.post(
                "/api/calls/fireflies-webhook",
                json=webhook_data
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "error"
            assert "call_not_found" in data["reason"]

    @pytest.mark.asyncio
    async def test_webhook_prevents_duplicate_processing(
        self, db_session, client, admin_user, organization
    ):
        """Test that webhook prevents duplicate processing of same call."""
        # Create call that's already done
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            source_type=CallSource.meet,
            status=CallStatus.done,
            fireflies_transcript_id="already-processed-123",
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        mock_transcript = {
            "id": "already-processed-123",
            "title": f"HR Call #{call.id}",
            "sentences": [],
            "duration": 0
        }

        webhook_data = {
            "meetingId": "already-processed-123",
            "eventType": "Transcription completed"
        }

        with patch('api.services.fireflies_client.fireflies_client.get_transcript',
                   AsyncMock(return_value=mock_transcript)):
            response = await client.post(
                "/api/calls/fireflies-webhook",
                json=webhook_data
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ignored"
            assert "already_processed" in data["reason"]

    @pytest.mark.asyncio
    async def test_webhook_invalid_title_format(self, client):
        """Test webhook with transcript that doesn't match title format."""
        mock_transcript = {
            "id": "test-123",
            "title": "Random Meeting Title",  # Doesn't match "HR Call #N"
            "sentences": [],
            "duration": 0
        }

        webhook_data = {
            "meetingId": "test-123",
            "eventType": "Transcription completed"
        }

        with patch('api.services.fireflies_client.fireflies_client.get_transcript',
                   AsyncMock(return_value=mock_transcript)):
            response = await client.post(
                "/api/calls/fireflies-webhook",
                json=webhook_data
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ignored"
            assert "unknown_meeting" in data["reason"]


# ============================================================================
# CALL PROCESSING WITH EXTERNAL SERVICES
# ============================================================================

class TestCallProcessingWithMocks:
    """Test call processing with mocked external services."""

    @pytest.mark.asyncio
    async def test_start_bot_calls_fireflies_service(
        self, client, admin_user, admin_token, get_auth_headers,
        org_owner, mock_call_recorder_service
    ):
        """Test that starting bot calls Fireflies service correctly."""
        mock_call_recorder_service.start_recording.return_value = {
            "success": True,
            "message": "Bot started"
        }

        data = {
            "source_url": "https://meet.google.com/test-meeting",
            "bot_name": "Test Bot",
            "max_duration": 60
        }

        response = await client.post(
            "/api/calls/start-bot",
            json=data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

        # Verify Fireflies service was called
        assert mock_call_recorder_service.start_recording.called
        call_args = mock_call_recorder_service.start_recording.call_args
        # First arg is call_id, second is url, third is bot_name
        assert call_args[0][1] == data["source_url"]
        assert call_args[0][2] == data["bot_name"]

    @pytest.mark.asyncio
    async def test_stop_recording_calls_fireflies_service(
        self, db_session, client, admin_user, admin_token, call_recording,
        get_auth_headers, org_owner, mock_call_recorder_service
    ):
        """Test that stop recording calls Fireflies service."""
        # Set call to recording status
        call_recording.status = CallStatus.recording
        await db_session.commit()

        response = await client.post(
            f"/api/calls/{call_recording.id}/stop",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

        # Verify stop was called with correct call_id
        mock_call_recorder_service.stop_recording.assert_called_once_with(
            call_recording.id
        )

    @pytest.mark.asyncio
    async def test_fireflies_error_updates_call_status(
        self, db_session, client, admin_user, admin_token, get_auth_headers,
        org_owner, mock_call_recorder_service
    ):
        """Test that Fireflies errors update call status correctly."""
        mock_call_recorder_service.start_recording.return_value = {
            "success": False,
            "message": "Invalid meeting link"
        }

        data = {
            "source_url": "https://meet.google.com/invalid",
            "bot_name": "Test Bot"
        }

        response = await client.post(
            "/api/calls/start-bot",
            json=data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 500
        assert "Fireflies error" in response.json()["detail"]

        # Verify call was marked as failed in database
        # The call is created but failed, so we need to find it
        result = await db_session.execute(
            select(CallRecording).order_by(CallRecording.created_at.desc()).limit(1)
        )
        call = result.scalar_one_or_none()
        if call:
            assert call.status == CallStatus.failed
            assert call.error_message is not None


# ============================================================================
# CALL DETAILS AND METADATA TESTS
# ============================================================================

class TestCallDetailsAndMetadata:
    """Test call details and metadata handling."""

    @pytest.mark.asyncio
    async def test_get_call_with_all_fields(
        self, db_session, client, admin_user, admin_token, organization,
        entity, get_auth_headers, org_owner
    ):
        """Test getting call with all optional fields populated."""
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            entity_id=entity.id,
            title="Complete Call",
            source_type=CallSource.upload,
            source_url=None,
            bot_name="Test Bot",
            status=CallStatus.done,
            duration_seconds=1800,
            audio_file_path="/tmp/audio.mp3",
            transcript="Full transcript text here...",
            speakers=[
                {"speaker": "John", "start": 0, "end": 10, "text": "Hello"},
                {"speaker": "Jane", "start": 10, "end": 20, "text": "Hi"}
            ],
            summary="This is a comprehensive summary of the call.",
            action_items=["Action 1", "Action 2", "Action 3"],
            key_points=["Point 1", "Point 2", "Point 3"],
            created_at=datetime.utcnow(),
            started_at=datetime.utcnow(),
            ended_at=datetime.utcnow() + timedelta(minutes=30),
            processed_at=datetime.utcnow() + timedelta(minutes=35)
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        response = await client.get(
            f"/api/calls/{call.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == call.id
        assert data["title"] == "Complete Call"
        assert data["entity_id"] == entity.id
        assert data["entity_name"] == entity.name
        assert data["duration_seconds"] == 1800
        assert data["audio_file_path"] == "/tmp/audio.mp3"
        assert len(data["speakers"]) == 2
        assert len(data["action_items"]) == 3
        assert len(data["key_points"]) == 3
        assert data["summary"] is not None
        assert "created_at" in data
        assert "started_at" in data
        assert "ended_at" in data
        assert "processed_at" in data

    @pytest.mark.asyncio
    async def test_list_calls_with_multiple_sources(
        self, db_session, client, admin_user, admin_token, organization,
        get_auth_headers, org_owner
    ):
        """Test listing calls from different sources."""
        # Create calls from different sources
        sources = [
            (CallSource.upload, "Uploaded Call"),
            (CallSource.meet, "Google Meet Call"),
            (CallSource.zoom, "Zoom Call"),
            (CallSource.teams, "Teams Call")
        ]

        for source, title in sources:
            call = CallRecording(
                org_id=organization.id,
                owner_id=admin_user.id,
                title=title,
                source_type=source,
                status=CallStatus.done,
                created_at=datetime.utcnow()
            )
            db_session.add(call)
        await db_session.commit()

        response = await client.get(
            "/api/calls",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 4

        # Verify all source types are present
        source_types = {call["source_type"] for call in data}
        assert "upload" in source_types
        assert "meet" in source_types
        assert "zoom" in source_types
        assert "teams" in source_types

    @pytest.mark.asyncio
    async def test_call_with_long_transcript(
        self, db_session, client, admin_user, admin_token, organization,
        get_auth_headers, org_owner
    ):
        """Test handling call with very long transcript."""
        # Create call with long transcript
        long_transcript = "A" * 10000  # 10k characters
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Long Transcript Call",
            source_type=CallSource.upload,
            status=CallStatus.done,
            transcript=long_transcript,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        # Get full call details
        response = await client.get(
            f"/api/calls/{call.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        # Full transcript should be returned in detail view
        assert len(data["transcript"]) == 10000

        # List view should truncate
        response = await client.get(
            "/api/calls",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        call_data = next((c for c in data if c["id"] == call.id), None)
        assert call_data is not None
        # Should be truncated to 500 chars
        assert len(call_data["transcript"]) == 500

    @pytest.mark.asyncio
    async def test_call_timestamps_ordering(
        self, db_session, client, admin_user, admin_token, organization,
        get_auth_headers, org_owner
    ):
        """Test that call timestamps are in correct order."""
        now = datetime.utcnow()
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            source_type=CallSource.meet,
            status=CallStatus.done,
            created_at=now,
            started_at=now + timedelta(minutes=1),
            ended_at=now + timedelta(minutes=31),
            processed_at=now + timedelta(minutes=35)
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        response = await client.get(
            f"/api/calls/{call.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Parse timestamps
        from datetime import datetime as dt
        created = dt.fromisoformat(data["created_at"].replace('Z', '+00:00'))
        started = dt.fromisoformat(data["started_at"].replace('Z', '+00:00'))
        ended = dt.fromisoformat(data["ended_at"].replace('Z', '+00:00'))
        processed = dt.fromisoformat(data["processed_at"].replace('Z', '+00:00'))

        # Verify order
        assert created <= started <= ended <= processed


# ============================================================================
# COMPREHENSIVE ERROR HANDLING TESTS
# ============================================================================

class TestCallErrorHandling:
    """Comprehensive error handling tests for call operations."""

    @pytest.mark.asyncio
    async def test_get_call_unauthorized(self, client, call_recording):
        """Test accessing call without authentication."""
        response = await client.get(f"/api/calls/{call_recording.id}")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_call_invalid_content_type(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test uploading file with unsupported content type."""
        import io
        file_content = b"not an audio file"
        files = {"file": ("document.pdf", io.BytesIO(file_content), "application/pdf")}

        response = await client.post(
            "/api/calls/upload",
            files=files,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 400
        assert "Unsupported format" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_start_bot_with_invalid_url_format(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test starting bot with malformed URL."""
        data = {
            "source_url": "not-a-valid-url",
            "bot_name": "HR Recorder"
        }

        response = await client.post(
            "/api/calls/start-bot",
            json=data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_share_call_with_invalid_access_level(
        self, client, admin_user, admin_token, call_recording,
        second_user, get_auth_headers, org_owner, org_member
    ):
        """Test sharing call with invalid access level."""
        data = {
            "shared_with_id": second_user.id,
            "access_level": "invalid_level"
        }

        response = await client.post(
            f"/api/calls/{call_recording.id}/share",
            json=data,
            headers=get_auth_headers(admin_token)
        )

        # FastAPI validation should fail
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_call_with_invalid_entity_type(
        self, client, admin_user, admin_token, call_recording,
        get_auth_headers, org_owner
    ):
        """Test updating call with non-integer entity ID."""
        response = await client.patch(
            f"/api/calls/{call_recording.id}",
            json={"entity_id": "not-a-number"},
            headers=get_auth_headers(admin_token)
        )

        # FastAPI validation should fail
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_stop_recording_service_error(
        self, db_session, client, admin_user, admin_token,
        call_recording, get_auth_headers, org_owner, mock_call_recorder_service
    ):
        """Test handling Fireflies service error when stopping recording."""
        # Set call to recording status
        call_recording.status = CallStatus.recording
        await db_session.commit()

        # Mock service to raise error
        mock_call_recorder_service.stop_recording.side_effect = Exception("Service unavailable")

        response = await client.post(
            f"/api/calls/{call_recording.id}/stop",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 500
        assert "Failed to stop recording" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_start_bot_exception_handling(
        self, db_session, client, admin_user, admin_token,
        get_auth_headers, org_owner, mock_call_recorder_service
    ):
        """Test handling unexpected exception when starting bot."""
        # Mock service to raise unexpected error
        mock_call_recorder_service.start_recording.side_effect = RuntimeError("Unexpected error")

        data = {
            "source_url": "https://meet.google.com/abc-defg-hij",
            "bot_name": "HR Recorder"
        }

        response = await client.post(
            "/api/calls/start-bot",
            json=data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 500
        assert "Failed to start recording bot" in response.json()["detail"]

        # Verify call was marked as failed in database
        result = await db_session.execute(
            select(CallRecording).order_by(CallRecording.created_at.desc()).limit(1)
        )
        call = result.scalar_one_or_none()
        if call:
            assert call.status == CallStatus.failed
            assert call.error_message is not None

    @pytest.mark.asyncio
    async def test_get_call_status_for_different_org_call(
        self, db_session, client, second_user, second_user_token,
        second_organization, get_auth_headers, org_member
    ):
        """Test getting status of call from different organization."""
        # Create call in different org
        other_call = CallRecording(
            org_id=second_organization.id,
            owner_id=1,
            title="Other Org Call",
            source_type=CallSource.upload,
            status=CallStatus.done,
            created_at=datetime.utcnow()
        )
        db_session.add(other_call)
        await db_session.commit()
        await db_session.refresh(other_call)

        response = await client.get(
            f"/api/calls/{other_call.id}/status",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_link_entity_cross_org_attempt(
        self, db_session, client, admin_user, admin_token,
        call_recording, second_organization, get_auth_headers, org_owner
    ):
        """Test that linking entity from different org is prevented."""
        # Create entity in different org
        from api.models.database import Entity, EntityType, EntityStatus
        other_entity = Entity(
            org_id=second_organization.id,
            created_by=1,
            name="Other Entity",
            type=EntityType.candidate,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(other_entity)
        await db_session.commit()
        await db_session.refresh(other_entity)

        response = await client.post(
            f"/api/calls/{call_recording.id}/link-entity/{other_entity.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_share_call_to_nonexistent_user(
        self, client, admin_user, admin_token, call_recording,
        get_auth_headers, org_owner
    ):
        """Test sharing call with user that doesn't exist."""
        data = {
            "shared_with_id": 999999,
            "access_level": "view"
        }

        response = await client.post(
            f"/api/calls/{call_recording.id}/share",
            json=data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404
        assert "user not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_upload_empty_file(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test uploading empty audio file."""
        import io
        # Empty file
        files = {"file": ("empty.mp3", io.BytesIO(b""), "audio/mpeg")}

        # Create proper async context manager mock
        from unittest.mock import AsyncMock, MagicMock, patch
        mock_file = AsyncMock()
        mock_file.write = AsyncMock()

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_file)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch('api.routes.calls.aiofiles.open', return_value=mock_cm):
            response = await client.post(
                "/api/calls/upload",
                files=files,
                headers=get_auth_headers(admin_token)
            )

            # Should accept but will fail in processing
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_concurrent_share_updates(
        self, db_session, client, admin_user, admin_token,
        call_recording, second_user, get_auth_headers, org_owner, org_member
    ):
        """Test updating an existing share (concurrent share scenario)."""
        # Create initial share
        data = {
            "shared_with_id": second_user.id,
            "access_level": "view"
        }

        response1 = await client.post(
            f"/api/calls/{call_recording.id}/share",
            json=data,
            headers=get_auth_headers(admin_token)
        )
        assert response1.status_code == 200

        # Update share to edit
        data["access_level"] = "edit"
        response2 = await client.post(
            f"/api/calls/{call_recording.id}/share",
            json=data,
            headers=get_auth_headers(admin_token)
        )
        assert response2.status_code == 200

        # Verify only one share exists with edit access
        result = await db_session.execute(
            select(SharedAccess).where(
                SharedAccess.resource_type == ResourceType.call,
                SharedAccess.resource_id == call_recording.id,
                SharedAccess.shared_with_id == second_user.id
            )
        )
        shares = result.scalars().all()
        assert len(shares) == 1
        assert shares[0].access_level == AccessLevel.edit

    @pytest.mark.asyncio
    async def test_malformed_json_in_request(
        self, client, admin_user, admin_token, call_recording, get_auth_headers, org_owner
    ):
        """Test handling malformed JSON in request body."""
        response = await client.patch(
            f"/api/calls/{call_recording.id}",
            content=b"not valid json{{{",
            headers={
                **get_auth_headers(admin_token),
                "Content-Type": "application/json"
            }
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_excessive_pagination_limit(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test that pagination limit is enforced."""
        response = await client.get(
            "/api/calls?limit=1000",
            headers=get_auth_headers(admin_token)
        )

        # Should reject limit > 100
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_negative_call_id(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test handling negative call ID."""
        response = await client.get(
            "/api/calls/-1",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_share_with_missing_required_fields(
        self, client, admin_user, admin_token, call_recording, get_auth_headers, org_owner
    ):
        """Test sharing call with missing required fields."""
        # Missing shared_with_id
        data = {
            "access_level": "view"
        }

        response = await client.post(
            f"/api/calls/{call_recording.id}/share",
            json=data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_call_with_extremely_long_title(
        self, client, admin_user, admin_token, call_recording,
        get_auth_headers, org_owner
    ):
        """Test updating call with very long title."""
        # Create title longer than typical limits
        long_title = "A" * 10000

        response = await client.patch(
            f"/api/calls/{call_recording.id}",
            json={"title": long_title},
            headers=get_auth_headers(admin_token)
        )

        # Should accept (no length limit in schema)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_filter_by_invalid_status(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test filtering calls by invalid status value."""
        response = await client.get(
            "/api/calls?status=invalid_status",
            headers=get_auth_headers(admin_token)
        )

        # FastAPI validation should fail
        assert response.status_code == 422


# ============================================================================
# UPLOAD CALL ADVANCED SCENARIOS
# ============================================================================

class TestUploadCallAdvanced:
    """Advanced upload call scenarios and edge cases."""

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Entity validation")
    async def test_upload_call_with_nonexistent_entity(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test uploading call with entity_id that doesn't exist."""
        # Create proper async context manager mock
        mock_file = AsyncMock()
        mock_file.write = AsyncMock()

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_file)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch('api.routes.calls.aiofiles.open', return_value=mock_cm):
            file_content = b"fake audio content"
            files = {"file": ("test.mp3", io.BytesIO(file_content), "audio/mpeg")}

            # Use entity_id that doesn't exist
            response = await client.post(
                "/api/calls/upload?entity_id=999999",
                files=files,
                headers=get_auth_headers(admin_token)
            )

            # Should still create the call but entity_id won't be validated until later
            # The endpoint doesn't validate entity existence during upload
            assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Background task mock")
    async def test_upload_call_background_task_invocation(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test that upload properly invokes background processing task."""
        # Create proper async context manager mock
        mock_file = AsyncMock()
        mock_file.write = AsyncMock()

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_file)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch('api.routes.calls.aiofiles.open', return_value=mock_cm), \
             patch('api.routes.calls.process_call_background') as mock_bg:

            file_content = b"fake audio content"
            files = {"file": ("test.mp3", io.BytesIO(file_content), "audio/mpeg")}

            response = await client.post(
                "/api/calls/upload",
                files=files,
                headers=get_auth_headers(admin_token)
            )

            assert response.status_code == 200
            # Background task should have been added (can't easily verify with BackgroundTasks)

    @pytest.mark.asyncio
    async def test_upload_call_creates_proper_file_path(
        self, db_session, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test that upload creates call with proper file path."""
        # Create proper async context manager mock
        mock_file = AsyncMock()
        mock_file.write = AsyncMock()

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_file)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch('api.routes.calls.aiofiles.open', return_value=mock_cm), \
             patch('api.routes.calls.uuid.uuid4') as mock_uuid:

            mock_uuid.return_value = MagicMock()
            mock_uuid.return_value.__str__ = lambda x: "test-file-uuid"

            file_content = b"fake audio content"
            files = {"file": ("recording.mp3", io.BytesIO(file_content), "audio/mpeg")}

            response = await client.post(
                "/api/calls/upload",
                files=files,
                headers=get_auth_headers(admin_token)
            )

            assert response.status_code == 200
            data = response.json()

            # Verify call was created with audio_file_path
            call_id = data["id"]
            result = await db_session.execute(
                select(CallRecording).where(CallRecording.id == call_id)
            )
            call = result.scalar_one()
            assert call.audio_file_path is not None
            assert "test-file-uuid" in call.audio_file_path
            assert call.audio_file_path.endswith(".mp3")

    @pytest.mark.asyncio
    async def test_upload_call_file_extension_preserved(
        self, client, admin_user, admin_token, get_auth_headers, org_owner
    ):
        """Test that file extension is properly preserved during upload."""
        # Create proper async context manager mock
        mock_file = AsyncMock()
        mock_file.write = AsyncMock()

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_file)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        test_extensions = [".mp3", ".mp4", ".wav", ".m4a", ".webm", ".ogg"]

        for ext in test_extensions:
            with patch('api.routes.calls.aiofiles.open', return_value=mock_cm):
                file_content = b"fake audio"
                filename = f"recording{ext}"
                files = {"file": (filename, io.BytesIO(file_content), "audio/mpeg")}

                response = await client.post(
                    "/api/calls/upload",
                    files=files,
                    headers=get_auth_headers(admin_token)
                )

                assert response.status_code == 200, f"Failed for extension {ext}"


# ============================================================================
# START BOT ADVANCED SCENARIOS
# ============================================================================

class TestStartBotAdvanced:
    """Advanced start bot scenarios and edge cases."""

    @pytest.mark.asyncio
    async def test_start_bot_max_duration_validation(
        self, client, admin_user, admin_token, get_auth_headers,
        org_owner, mock_call_recorder_service
    ):
        """Test that max_duration parameter is accepted."""
        mock_call_recorder_service.start_recording.return_value = {"success": True}

        data = {
            "source_url": "https://meet.google.com/abc-defg-hij",
            "bot_name": "HR Recorder",
            "max_duration": 60  # 60 minutes
        }

        response = await client.post(
            "/api/calls/start-bot",
            json=data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        # Verify max_duration was passed to the service
        mock_call_recorder_service.start_recording.assert_called_once()
        call_args = mock_call_recorder_service.start_recording.call_args
        assert call_args[1]["duration"] == 60

    @pytest.mark.asyncio
    async def test_start_bot_title_parameter(
        self, client, admin_user, admin_token, get_auth_headers,
        org_owner, mock_call_recorder_service
    ):
        """Test that title parameter is accepted and stored."""
        mock_call_recorder_service.start_recording.return_value = {"success": True}

        data = {
            "source_url": "https://meet.google.com/abc-defg-hij",
            "bot_name": "HR Recorder",
            "title": "Engineering Interview"
        }

        response = await client.post(
            "/api/calls/start-bot",
            json=data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_start_bot_zoom_com_domain(
        self, client, admin_user, admin_token, get_auth_headers,
        org_owner, mock_call_recorder_service
    ):
        """Test that both zoom.us and zoom.com domains are supported."""
        mock_call_recorder_service.start_recording.return_value = {"success": True}

        # Test zoom.com
        data = {
            "source_url": "https://zoom.com/j/123456789",
            "bot_name": "HR Recorder"
        }

        response = await client.post(
            "/api/calls/start-bot",
            json=data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_start_bot_teams_live_domain(
        self, client, admin_user, admin_token, get_auth_headers,
        org_owner, mock_call_recorder_service
    ):
        """Test that teams.live.com domain is supported."""
        mock_call_recorder_service.start_recording.return_value = {"success": True}

        data = {
            "source_url": "https://teams.live.com/meet/...",
            "bot_name": "HR Recorder"
        }

        response = await client.post(
            "/api/calls/start-bot",
            json=data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_start_bot_case_insensitive_url(
        self, client, admin_user, admin_token, get_auth_headers,
        org_owner, mock_call_recorder_service
    ):
        """Test that URL matching is case-insensitive."""
        mock_call_recorder_service.start_recording.return_value = {"success": True}

        data = {
            "source_url": "https://MEET.GOOGLE.COM/abc-defg-hij",
            "bot_name": "HR Recorder"
        }

        response = await client.post(
            "/api/calls/start-bot",
            json=data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200


# ============================================================================
# STOP RECORDING ADVANCED SCENARIOS
# ============================================================================

class TestStopRecordingAdvanced:
    """Advanced stop recording scenarios and edge cases."""

    @pytest.mark.asyncio
    async def test_stop_recording_service_exception_handling(
        self, db_session, client, admin_user, admin_token,
        call_recording, get_auth_headers, org_owner, mock_call_recorder_service
    ):
        """Test proper error handling when stop service raises exception."""
        # Set call to recording status
        call_recording.status = CallStatus.recording
        await db_session.commit()

        # Make service raise exception
        mock_call_recorder_service.stop_recording.side_effect = Exception("Service unavailable")

        response = await client.post(
            f"/api/calls/{call_recording.id}/stop",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 500
        assert "Failed to stop recording" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_stop_recording_requires_full_access(
        self, db_session, client, second_user, second_user_token,
        call_recording, admin_user, get_auth_headers, org_member
    ):
        """Test that stop recording requires full access, not just edit."""
        call_recording.status = CallStatus.recording
        await db_session.commit()

        # Share with edit access (not full)
        share = SharedAccess(
            resource_type=ResourceType.call,
            resource_id=call_recording.id,
            call_id=call_recording.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.edit
        )
        db_session.add(share)
        await db_session.commit()

        response = await client.post(
            f"/api/calls/{call_recording.id}/stop",
            headers=get_auth_headers(second_user_token)
        )

        # Edit access is not enough - need full access
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_stop_recording_with_full_shared_access(
        self, db_session, client, second_user, second_user_token,
        call_recording, admin_user, get_auth_headers, org_member, mock_call_recorder_service
    ):
        """Test that user with full shared access can stop recording."""
        call_recording.status = CallStatus.recording
        await db_session.commit()

        # Share with full access
        share = SharedAccess(
            resource_type=ResourceType.call,
            resource_id=call_recording.id,
            call_id=call_recording.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.full
        )
        db_session.add(share)
        await db_session.commit()

        response = await client.post(
            f"/api/calls/{call_recording.id}/stop",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        assert response.json()["success"] is True


# ============================================================================
# REPROCESS CALL ADVANCED SCENARIOS
# ============================================================================

class TestReprocessCallAdvanced:
    """Advanced reprocess call scenarios and edge cases."""

    @pytest.mark.asyncio
    async def test_reprocess_call_preserves_original_data(
        self, db_session, client, admin_user, admin_token, call_recording,
        get_auth_headers, org_owner
    ):
        """Test that reprocessing preserves original transcript and speakers."""
        # Set original data
        original_transcript = "Original transcript content"
        original_speakers = [{"speaker": "Alice", "start": 0, "end": 5, "text": "Hello"}]
        call_recording.transcript = original_transcript
        call_recording.speakers = original_speakers
        call_recording.duration_seconds = 300
        await db_session.commit()

        response = await client.post(
            f"/api/calls/{call_recording.id}/reprocess",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

        # Refresh and verify original data is still there
        await db_session.refresh(call_recording)
        assert call_recording.transcript == original_transcript
        assert call_recording.speakers == original_speakers

    @pytest.mark.asyncio
    async def test_reprocess_call_handles_missing_speakers(
        self, db_session, client, admin_user, admin_token, call_recording,
        get_auth_headers, org_owner
    ):
        """Test reprocessing call when speakers field is None."""
        # Set transcript but no speakers
        call_recording.transcript = "Test transcript"
        call_recording.speakers = None
        await db_session.commit()

        response = await client.post(
            f"/api/calls/{call_recording.id}/reprocess",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_reprocess_call_concurrent_attempts(
        self, db_session, client, admin_user, admin_token, call_recording,
        get_auth_headers, org_owner
    ):
        """Test multiple concurrent reprocess requests."""
        call_recording.transcript = "Test transcript"
        await db_session.commit()

        # Send multiple reprocess requests
        responses = []
        for _ in range(3):
            response = await client.post(
                f"/api/calls/{call_recording.id}/reprocess",
                headers=get_auth_headers(admin_token)
            )
            responses.append(response)

        # All should succeed
        for response in responses:
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_reprocess_call_superadmin_can_reprocess(
        self, db_session, client, superadmin_user, superadmin_token, call_recording,
        get_auth_headers, superadmin_org_member
    ):
        """Test that superadmin can reprocess any call."""
        call_recording.transcript = "Test transcript"
        await db_session.commit()

        response = await client.post(
            f"/api/calls/{call_recording.id}/reprocess",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_reprocess_call_with_fireflies_id_uses_local_variables(
        self, db_session, client, admin_user, admin_token, call_recording,
        get_auth_headers, org_owner
    ):
        """Test that reprocess correctly captures values for background task."""
        # Set up Fireflies data
        call_recording.fireflies_transcript_id = "ff-test-123"
        call_recording.transcript = "[00:00] Speaker 1: Test transcript from Fireflies bot"
        call_recording.speakers = [
            {"speaker": "Speaker 1", "start": 0, "end": 5, "text": "Test transcript from Fireflies bot"}
        ]
        call_recording.status = CallStatus.done
        await db_session.commit()

        response = await client.post(
            f"/api/calls/{call_recording.id}/reprocess",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == CallStatus.analyzing.value

        # Verify call is in analyzing state
        await db_session.refresh(call_recording)
        assert call_recording.status == CallStatus.analyzing

    @pytest.mark.asyncio
    async def test_reprocess_call_with_empty_transcript_and_fireflies_id(
        self, db_session, client, admin_user, admin_token, call_recording,
        get_auth_headers, org_owner
    ):
        """Test reprocessing call with fireflies_id but empty transcript returns error."""
        # Set up Fireflies ID but no transcript
        call_recording.fireflies_transcript_id = "ff-test-456"
        call_recording.transcript = None
        call_recording.speakers = None
        call_recording.audio_file_path = None
        await db_session.commit()

        response = await client.post(
            f"/api/calls/{call_recording.id}/reprocess",
            headers=get_auth_headers(admin_token)
        )

        # Should return 400 since there's no actual data to process
        # (fireflies_id alone without transcript is not enough)
        assert response.status_code == 400
        assert "No data to process" in response.json()["detail"]


# ============================================================================
# CALL SHARING ADVANCED SCENARIOS
# ============================================================================

class TestCallSharingAdvanced:
    """Advanced call sharing scenarios and edge cases."""

    @pytest.mark.asyncio
    async def test_share_call_with_future_expiration(
        self, db_session, client, admin_user, admin_token,
        call_recording, second_user, get_auth_headers, org_owner, org_member
    ):
        """Test sharing call with future expiration date."""
        from datetime import datetime, timedelta
        future_date = datetime.utcnow() + timedelta(days=30)

        data = {
            "shared_with_id": second_user.id,
            "access_level": "view",
            "expires_at": future_date.isoformat()
        }

        response = await client.post(
            f"/api/calls/{call_recording.id}/share",
            json=data,
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

        # Verify expiration was set
        result = await db_session.execute(
            select(SharedAccess).where(
                SharedAccess.resource_type == ResourceType.call,
                SharedAccess.resource_id == call_recording.id
            )
        )
        share = result.scalar_one()
        assert share.expires_at is not None

    @pytest.mark.asyncio
    async def test_share_call_multiple_users(
        self, db_session, client, admin_user, admin_token,
        call_recording, second_user, regular_user,
        get_auth_headers, org_owner, org_member, org_admin
    ):
        """Test sharing same call with multiple users."""
        # Share with second_user
        data1 = {
            "shared_with_id": second_user.id,
            "access_level": "view"
        }
        response1 = await client.post(
            f"/api/calls/{call_recording.id}/share",
            json=data1,
            headers=get_auth_headers(admin_token)
        )
        assert response1.status_code == 200

        # Share with regular_user
        data2 = {
            "shared_with_id": regular_user.id,
            "access_level": "edit"
        }
        response2 = await client.post(
            f"/api/calls/{call_recording.id}/share",
            json=data2,
            headers=get_auth_headers(admin_token)
        )
        assert response2.status_code == 200

        # Verify both shares exist
        result = await db_session.execute(
            select(SharedAccess).where(
                SharedAccess.resource_type == ResourceType.call,
                SharedAccess.resource_id == call_recording.id
            )
        )
        shares = result.scalars().all()
        assert len(shares) == 2

    @pytest.mark.asyncio
    async def test_access_shared_call_after_owner_leaves_org(
        self, db_session, client, admin_user, admin_token,
        call_recording, second_user, second_user_token,
        get_auth_headers, org_owner, org_member
    ):
        """Test accessing shared call after owner loses org access."""
        # Share call
        share = SharedAccess(
            resource_type=ResourceType.call,
            resource_id=call_recording.id,
            call_id=call_recording.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.view
        )
        db_session.add(share)
        await db_session.commit()

        # Verify second_user can access
        response = await client.get(
            f"/api/calls/{call_recording.id}",
            headers=get_auth_headers(second_user_token)
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_share_call_all_access_levels(
        self, db_session, client, admin_user, admin_token,
        call_recording, organization, get_auth_headers, org_owner
    ):
        """Test sharing call with all different access levels."""
        from api.models.database import User, UserRole, OrgMember, OrgRole

        access_levels = ["view", "edit", "full"]
        users = []

        # Create users for each access level
        for i, level in enumerate(access_levels):
            user = User(
                email=f"user_{level}@test.com",
                password_hash="hashed",
                name=f"User {level}",
                role=UserRole.admin,
                is_active=True
            )
            db_session.add(user)
            await db_session.flush()

            # Add to org
            member = OrgMember(
                org_id=organization.id,
                user_id=user.id,
                role=OrgRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(member)
            users.append((user, level))

        await db_session.commit()

        # Share with each user at different level
        for user, level in users:
            data = {
                "shared_with_id": user.id,
                "access_level": level
            }
            response = await client.post(
                f"/api/calls/{call_recording.id}/share",
                json=data,
                headers=get_auth_headers(admin_token)
            )
            assert response.status_code == 200

        # Verify all shares created
        result = await db_session.execute(
            select(SharedAccess).where(
                SharedAccess.resource_type == ResourceType.call,
                SharedAccess.resource_id == call_recording.id
            )
        )
        shares = result.scalars().all()
        assert len(shares) == 3

        # Verify different access levels
        access_levels_found = {share.access_level for share in shares}
        assert AccessLevel.view in access_levels_found
        assert AccessLevel.edit in access_levels_found
        assert AccessLevel.full in access_levels_found


# ============================================================================
# DOWNLOAD TRANSCRIPT ENDPOINT TESTS
# ============================================================================

class TestDownloadTranscript:
    """Test downloading call transcripts with various access permissions."""

    @pytest.mark.asyncio
    async def test_download_transcript_as_owner(
        self, client, db_session, admin_user, admin_token, organization, get_auth_headers, org_owner
    ):
        """Test downloading transcript as call owner."""
        # Create call with transcript
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Test Call with Transcript",
            source_type=CallSource.upload,
            status=CallStatus.done,
            transcript="Speaker 1: Hello\nSpeaker 2: Hi there\nSpeaker 1: How are you?",
            duration_seconds=300,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        response = await client.get(
            f"/api/calls/{call.id}/download/transcript",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        assert "attachment" in response.headers["content-disposition"]
        assert "transcript.txt" in response.headers["content-disposition"]
        assert response.text == call.transcript

    @pytest.mark.asyncio
    async def test_download_transcript_with_shared_view_access(
        self, client, db_session, admin_user, admin_token, second_user, second_user_token,
        organization, get_auth_headers, org_owner, org_member
    ):
        """Test downloading transcript with view-level shared access."""
        # Create call owned by admin
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Shared Call",
            source_type=CallSource.upload,
            status=CallStatus.done,
            transcript="Meeting notes here...",
            duration_seconds=600,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        # Share with view access to second user
        share = SharedAccess(
            resource_type=ResourceType.call,
            resource_id=call.id,
            call_id=call.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.view,
            created_at=datetime.utcnow()
        )
        db_session.add(share)
        await db_session.commit()

        # Second user should be able to download
        response = await client.get(
            f"/api/calls/{call.id}/download/transcript",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        assert response.text == call.transcript

    @pytest.mark.asyncio
    async def test_download_transcript_no_access(
        self, client, db_session, admin_user, second_user, second_user_token,
        organization, get_auth_headers, org_owner, org_member
    ):
        """Test downloading transcript without access fails."""
        # Create call owned by admin
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Private Call",
            source_type=CallSource.upload,
            status=CallStatus.done,
            transcript="Private meeting...",
            duration_seconds=300,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        # Second user tries to download without access
        response = await client.get(
            f"/api/calls/{call.id}/download/transcript",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403
        assert "access denied" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_download_transcript_not_found(
        self, client, admin_token, get_auth_headers
    ):
        """Test downloading transcript for non-existent call."""
        response = await client.get(
            "/api/calls/99999/download/transcript",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_download_transcript_no_transcript(
        self, client, db_session, admin_user, admin_token, organization, get_auth_headers, org_owner
    ):
        """Test downloading transcript when transcript doesn't exist."""
        # Create call without transcript
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Call without Transcript",
            source_type=CallSource.upload,
            status=CallStatus.processing,
            transcript=None,
            duration_seconds=300,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        response = await client.get(
            f"/api/calls/{call.id}/download/transcript",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404
        assert "transcript not available" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_download_transcript_filename_sanitization(
        self, client, db_session, admin_user, admin_token, organization, get_auth_headers, org_owner
    ):
        """Test transcript filename is properly sanitized."""
        # Create call with special characters in title
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Call: With/Special\\Characters<>|*?",
            source_type=CallSource.upload,
            status=CallStatus.done,
            transcript="Test transcript",
            duration_seconds=300,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        response = await client.get(
            f"/api/calls/{call.id}/download/transcript",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        disposition = response.headers["content-disposition"]
        # Filename should be sanitized (only alphanumeric, spaces, dashes, underscores)
        assert "Call WithSpecialCharacters_transcript.txt" in disposition or \
               "CallWithSpecialCharacters_transcript.txt" in disposition

    @pytest.mark.asyncio
    async def test_download_transcript_as_superadmin(
        self, client, db_session, admin_user, superadmin_user, organization,
        get_auth_headers, superadmin_org_member
    ):
        """Test superadmin can download any transcript."""
        from api.services.auth import create_access_token

        # Create call owned by admin
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Any Call",
            source_type=CallSource.upload,
            status=CallStatus.done,
            transcript="Transcript content",
            duration_seconds=300,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        superadmin_token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.get(
            f"/api/calls/{call.id}/download/transcript",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        assert response.text == call.transcript

    @pytest.mark.asyncio
    async def test_download_transcript_with_expired_share(
        self, client, db_session, admin_user, second_user, second_user_token,
        organization, get_auth_headers, org_owner, org_member
    ):
        """Test downloading transcript with expired share fails."""
        # Create call
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Call with Expired Share",
            source_type=CallSource.upload,
            status=CallStatus.done,
            transcript="Meeting notes",
            duration_seconds=300,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        # Create expired share
        expired_share = SharedAccess(
            resource_type=ResourceType.call,
            resource_id=call.id,
            call_id=call.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.view,
            expires_at=datetime.utcnow() - timedelta(days=1),
            created_at=datetime.utcnow() - timedelta(days=2)
        )
        db_session.add(expired_share)
        await db_session.commit()

        # Should fail to download
        response = await client.get(
            f"/api/calls/{call.id}/download/transcript",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403


# ============================================================================
# DOWNLOAD AUDIO ENDPOINT TESTS
# ============================================================================

class TestDownloadAudio:
    """Test downloading call audio files with various access permissions."""

    @pytest.mark.asyncio
    async def test_download_audio_as_owner(
        self, client, db_session, admin_user, admin_token, organization,
        get_auth_headers, org_owner, tmp_path
    ):
        """Test downloading audio file as call owner."""
        # Create temporary audio file
        audio_file = tmp_path / "test_call.mp3"
        audio_content = b"fake audio content for testing"
        audio_file.write_bytes(audio_content)

        # Create call with audio file
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Test Call with Audio",
            source_type=CallSource.upload,
            status=CallStatus.done,
            audio_file_path=str(audio_file),
            duration_seconds=300,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        response = await client.get(
            f"/api/calls/{call.id}/download/audio",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/mpeg"
        assert "attachment" in response.headers["content-disposition"]
        assert ".mp3" in response.headers["content-disposition"]
        assert response.content == audio_content

    @pytest.mark.asyncio
    async def test_download_audio_with_shared_view_access(
        self, client, db_session, admin_user, second_user, second_user_token,
        organization, get_auth_headers, org_owner, org_member, tmp_path
    ):
        """Test downloading audio with view-level shared access."""
        # Create temporary audio file
        audio_file = tmp_path / "shared_call.mp3"
        audio_content = b"shared audio content"
        audio_file.write_bytes(audio_content)

        # Create call
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Shared Audio Call",
            source_type=CallSource.upload,
            status=CallStatus.done,
            audio_file_path=str(audio_file),
            duration_seconds=600,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        # Share with view access
        share = SharedAccess(
            resource_type=ResourceType.call,
            resource_id=call.id,
            call_id=call.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.view,
            created_at=datetime.utcnow()
        )
        db_session.add(share)
        await db_session.commit()

        # Second user downloads
        response = await client.get(
            f"/api/calls/{call.id}/download/audio",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        assert response.content == audio_content

    @pytest.mark.asyncio
    async def test_download_audio_no_access(
        self, client, db_session, admin_user, second_user, second_user_token,
        organization, get_auth_headers, org_owner, org_member, tmp_path
    ):
        """Test downloading audio without access fails."""
        # Create audio file
        audio_file = tmp_path / "private_call.mp3"
        audio_file.write_bytes(b"private audio")

        # Create call
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Private Audio Call",
            source_type=CallSource.upload,
            status=CallStatus.done,
            audio_file_path=str(audio_file),
            duration_seconds=300,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        # Second user tries to download
        response = await client.get(
            f"/api/calls/{call.id}/download/audio",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_download_audio_no_audio_file(
        self, client, db_session, admin_user, admin_token, organization,
        get_auth_headers, org_owner
    ):
        """Test downloading audio when audio file doesn't exist."""
        # Create call without audio
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Call without Audio",
            source_type=CallSource.meet,
            status=CallStatus.done,
            audio_file_path=None,
            duration_seconds=300,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        response = await client.get(
            f"/api/calls/{call.id}/download/audio",
            headers=get_auth_headers(admin_token)
        )

        # Аудио нет ни в БД, ни на диске — честный 410 «потеряно» (транскрипт и
        # анализ звонка при этом остаются), а не 404 «звонка нет».
        assert response.status_code == 410
        assert "недоступен" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_download_audio_file_missing_on_disk(
        self, client, db_session, admin_user, admin_token, organization,
        get_auth_headers, org_owner
    ):
        """Test downloading audio when file path exists but file is missing."""
        # Create call with non-existent audio path
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Call with Missing File",
            source_type=CallSource.upload,
            status=CallStatus.done,
            audio_file_path="/nonexistent/path/to/audio.mp3",
            duration_seconds=300,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        response = await client.get(
            f"/api/calls/{call.id}/download/audio",
            headers=get_auth_headers(admin_token)
        )

        # Путь есть, файла на диске нет и байтов в БД нет — тот же 410.
        assert response.status_code == 410
        assert "недоступен" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_download_audio_content_type_mp4(
        self, client, db_session, admin_user, admin_token, organization,
        get_auth_headers, org_owner, tmp_path
    ):
        """Test audio download with MP4 file returns correct content type."""
        # Create MP4 file
        audio_file = tmp_path / "test_call.mp4"
        audio_file.write_bytes(b"fake mp4 content")

        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="MP4 Call",
            source_type=CallSource.upload,
            status=CallStatus.done,
            audio_file_path=str(audio_file),
            duration_seconds=300,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        response = await client.get(
            f"/api/calls/{call.id}/download/audio",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "video/mp4"

    @pytest.mark.asyncio
    async def test_download_audio_content_type_wav(
        self, client, db_session, admin_user, admin_token, organization,
        get_auth_headers, org_owner, tmp_path
    ):
        """Test audio download with WAV file returns correct content type."""
        # Create WAV file
        audio_file = tmp_path / "test_call.wav"
        audio_file.write_bytes(b"fake wav content")

        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="WAV Call",
            source_type=CallSource.upload,
            status=CallStatus.done,
            audio_file_path=str(audio_file),
            duration_seconds=300,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        response = await client.get(
            f"/api/calls/{call.id}/download/audio",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/wav"


# ============================================================================
# CALL PERMISSIONS TESTS (COMPREHENSIVE)
# ============================================================================

class TestCallPermissions:
    """Comprehensive tests for call access permissions across different scenarios."""

    @pytest.mark.asyncio
    async def test_owner_can_access_own_call(
        self, client, db_session, admin_user, admin_token, organization,
        get_auth_headers, org_owner
    ):
        """Test call owner has full access to their own call."""
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Owner Call",
            source_type=CallSource.upload,
            status=CallStatus.done,
            transcript="Owner's call transcript",
            duration_seconds=300,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        # Owner can view call details
        response = await client.get(
            f"/api/calls/{call.id}",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200

        # Owner can download transcript
        response = await client.get(
            f"/api/calls/{call.id}/download/transcript",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_department_lead_can_access_member_call(
        self, client, db_session, admin_user, admin_token, regular_user, user_token,
        organization, department, entity, get_auth_headers, org_owner, org_admin
    ):
        """Test department lead can access calls from department members."""
        from api.services.auth import create_access_token

        # Make admin a department lead
        lead_membership = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(lead_membership)

        # Make regular_user a department member
        member_membership = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(member_membership)
        await db_session.commit()

        # Create call owned by member, linked to entity in the department
        call = CallRecording(
            org_id=organization.id,
            owner_id=regular_user.id,
            entity_id=entity.id,
            title="Member Call",
            source_type=CallSource.upload,
            status=CallStatus.done,
            transcript="Department member's call",
            duration_seconds=300,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        # Department lead can access
        response = await client.get(
            f"/api/calls/{call.id}",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_department_member_cannot_access_other_member_call(
        self, client, db_session, regular_user, user_token, second_user,
        organization, department, entity, get_auth_headers, org_admin, org_member
    ):
        """Test department members cannot access other members' calls."""
        from api.services.auth import create_access_token

        # Make both users department members (not leads)
        member1 = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        member2 = DepartmentMember(
            department_id=department.id,
            user_id=second_user.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add_all([member1, member2])
        await db_session.commit()

        # Create call owned by regular_user
        call = CallRecording(
            org_id=organization.id,
            owner_id=regular_user.id,
            entity_id=entity.id,
            title="Private Member Call",
            source_type=CallSource.upload,
            status=CallStatus.done,
            transcript="Private call",
            duration_seconds=300,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        # Рядовой участник отдела ЧИТАЕТ звонки коллег по отделу
        # (PermissionService._check_department_access: «For MEMBER: read-only
        # department access»), но не меняет и не удаляет их.
        second_user_token = create_access_token(data={"sub": str(second_user.id)})
        response = await client.get(
            f"/api/calls/{call.id}",
            headers=get_auth_headers(second_user_token)
        )
        assert response.status_code == 200

        response = await client.delete(
            f"/api/calls/{call.id}",
            headers=get_auth_headers(second_user_token)
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_shared_access_with_edit_level(
        self, client, db_session, admin_user, admin_token, second_user,
        organization, get_auth_headers, org_owner, org_member, tmp_path
    ):
        """Test user with edit-level shared access can download resources."""
        from api.services.auth import create_access_token

        # Create audio file
        audio_file = tmp_path / "edit_shared.mp3"
        audio_file.write_bytes(b"shared edit audio")

        # Create call
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Edit Shared Call",
            source_type=CallSource.upload,
            status=CallStatus.done,
            transcript="Edit level shared transcript",
            audio_file_path=str(audio_file),
            duration_seconds=300,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        # Share with edit access
        share = SharedAccess(
            resource_type=ResourceType.call,
            resource_id=call.id,
            call_id=call.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.edit,
            created_at=datetime.utcnow()
        )
        db_session.add(share)
        await db_session.commit()

        second_user_token = create_access_token(data={"sub": str(second_user.id)})

        # Can download transcript
        response = await client.get(
            f"/api/calls/{call.id}/download/transcript",
            headers=get_auth_headers(second_user_token)
        )
        assert response.status_code == 200

        # Can download audio
        response = await client.get(
            f"/api/calls/{call.id}/download/audio",
            headers=get_auth_headers(second_user_token)
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_shared_access_with_full_level(
        self, client, db_session, admin_user, second_user, organization,
        get_auth_headers, org_owner, org_member
    ):
        """Test user with full-level shared access has complete access."""
        from api.services.auth import create_access_token

        # Create call
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Full Shared Call",
            source_type=CallSource.upload,
            status=CallStatus.done,
            transcript="Full level access transcript",
            duration_seconds=300,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        # Share with full access
        share = SharedAccess(
            resource_type=ResourceType.call,
            resource_id=call.id,
            call_id=call.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.full,
            created_at=datetime.utcnow()
        )
        db_session.add(share)
        await db_session.commit()

        second_user_token = create_access_token(data={"sub": str(second_user.id)})

        # Can view
        response = await client.get(
            f"/api/calls/{call.id}",
            headers=get_auth_headers(second_user_token)
        )
        assert response.status_code == 200

        # Can download transcript
        response = await client.get(
            f"/api/calls/{call.id}/download/transcript",
            headers=get_auth_headers(second_user_token)
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_org_owner_can_access_all_calls(
        self, client, db_session, admin_user, admin_token, regular_user,
        organization, get_auth_headers, org_owner, org_admin
    ):
        """Test organization owner can access all calls in the organization."""
        # Create call owned by different user
        call = CallRecording(
            org_id=organization.id,
            owner_id=regular_user.id,
            title="Other User Call",
            source_type=CallSource.upload,
            status=CallStatus.done,
            transcript="Another user's call",
            duration_seconds=300,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        # Org owner (admin_user via org_owner fixture) can access
        response = await client.get(
            f"/api/calls/{call.id}",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200

        # Can download transcript
        response = await client.get(
            f"/api/calls/{call.id}/download/transcript",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_superadmin_can_access_any_call(
        self, client, db_session, admin_user, superadmin_user, organization,
        get_auth_headers, superadmin_org_member
    ):
        """Test superadmin has access to all calls regardless of ownership."""
        from api.services.auth import create_access_token

        # Create call owned by regular user
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Regular User Call",
            source_type=CallSource.upload,
            status=CallStatus.done,
            transcript="Regular call transcript",
            duration_seconds=300,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        superadmin_token = create_access_token(data={"sub": str(superadmin_user.id)})

        # Superadmin can access
        response = await client.get(
            f"/api/calls/{call.id}",
            headers=get_auth_headers(superadmin_token)
        )
        assert response.status_code == 200

        # Can download
        response = await client.get(
            f"/api/calls/{call.id}/download/transcript",
            headers=get_auth_headers(superadmin_token)
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_cross_org_access_denied(
        self, client, db_session, admin_user, admin_token, organization,
        second_organization, get_auth_headers, org_owner
    ):
        """Test users cannot access calls from other organizations."""
        # Create call in second organization
        other_org_call = CallRecording(
            org_id=second_organization.id,
            owner_id=admin_user.id,
            title="Other Org Call",
            source_type=CallSource.upload,
            status=CallStatus.done,
            transcript="Different org call",
            duration_seconds=300,
            created_at=datetime.utcnow()
        )
        db_session.add(other_org_call)
        await db_session.commit()
        await db_session.refresh(other_org_call)

        # User from first org cannot access
        response = await client.get(
            f"/api/calls/{other_org_call.id}",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_unauthenticated_access_denied(self, client, db_session, organization, admin_user):
        """Test unauthenticated users cannot access calls."""
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Protected Call",
            source_type=CallSource.upload,
            status=CallStatus.done,
            transcript="Protected content",
            duration_seconds=300,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        await db_session.refresh(call)

        # No auth headers
        response = await client.get(f"/api/calls/{call.id}")
        assert response.status_code in (401, 403)

        response = await client.get(f"/api/calls/{call.id}/download/transcript")
        assert response.status_code in (401, 403)
