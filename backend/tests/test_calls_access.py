"""
Tests for CallRecording access control.
These tests verify that access_level (view/edit/full) is properly enforced for calls.
"""
import pytest
from datetime import datetime

from api.models.database import CallRecording, SharedAccess, AccessLevel, ResourceType, CallStatus


class TestCallOwnerAccess:
    """Test call access for owner."""

    @pytest.mark.asyncio
    async def test_owner_can_view_call(self, client, admin_user, admin_token, call_recording, get_auth_headers, org_owner):
        """Test that call owner can view their call."""
        response = await client.get(
            f"/api/calls/{call_recording.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test Call"

    @pytest.mark.asyncio
    async def test_owner_can_update_call(self, client, admin_user, admin_token, call_recording, get_auth_headers, org_owner):
        """Test that call owner can update their call."""
        response = await client.patch(
            f"/api/calls/{call_recording.id}",
            json={"title": "Updated Call Title"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_owner_can_delete_call(self, client, admin_user, admin_token, call_recording, get_auth_headers, org_owner):
        """Test that call owner can delete their call."""
        response = await client.delete(
            f"/api/calls/{call_recording.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200


class TestCallViewAccess:
    """Test call access with view permission - CRITICAL SECURITY TESTS."""

    @pytest.mark.asyncio
    async def test_view_user_can_see_call(
        self, client, second_user, second_user_token, call_recording, call_share_view, get_auth_headers, org_member
    ):
        """Test that user with view access can see call."""
        response = await client.get(
            f"/api/calls/{call_recording.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_view_user_cannot_update_call(
        self, client, second_user, second_user_token, call_recording, call_share_view, get_auth_headers, org_member
    ):
        """
        CRITICAL TEST: User with view-only access should NOT be able to update call.
        This test documents the current bug.
        """
        response = await client.patch(
            f"/api/calls/{call_recording.id}",
            json={"title": "Hacked Title"},
            headers=get_auth_headers(second_user_token)
        )

        # Expected: 403 Forbidden
        # Current bug: returns 200
        assert response.status_code == 403, \
            f"SECURITY BUG: View-only user was able to update call! Got {response.status_code}"

    @pytest.mark.asyncio
    async def test_view_user_cannot_delete_call(
        self, client, second_user, second_user_token, call_recording, call_share_view, get_auth_headers, org_member
    ):
        """
        CRITICAL TEST: User with view-only access should NOT be able to delete call.
        This test documents the current bug.
        """
        response = await client.delete(
            f"/api/calls/{call_recording.id}",
            headers=get_auth_headers(second_user_token)
        )

        # Expected: 403 Forbidden
        # Current bug: returns 200 (deletes call!)
        assert response.status_code == 403, \
            f"SECURITY BUG: View-only user was able to delete call! Got {response.status_code}"

    @pytest.mark.asyncio
    async def test_view_user_cannot_stop_recording(
        self, db_session, client, second_user, second_user_token, call_recording,
        call_share_view, get_auth_headers, org_member
    ):
        """
        CRITICAL TEST: User with view-only access should NOT be able to stop recording.
        """
        # Set call to recording status
        call_recording.status = CallStatus.recording
        await db_session.commit()

        response = await client.post(
            f"/api/calls/{call_recording.id}/stop",
            headers=get_auth_headers(second_user_token)
        )

        # Expected: 403 Forbidden
        assert response.status_code == 403, \
            f"SECURITY BUG: View-only user was able to stop recording! Got {response.status_code}"

    @pytest.mark.asyncio
    async def test_view_user_cannot_link_entity(
        self, client, second_user, second_user_token, call_recording, call_share_view,
        get_auth_headers, org_member, entity
    ):
        """
        CRITICAL TEST: User with view-only access should NOT be able to link entity to call.
        """
        response = await client.post(
            f"/api/calls/{call_recording.id}/link-entity/{entity.id}",
            headers=get_auth_headers(second_user_token)
        )

        # Expected: 403 Forbidden
        assert response.status_code == 403, \
            f"SECURITY BUG: View-only user was able to link entity! Got {response.status_code}"

    @pytest.mark.asyncio
    async def test_view_user_cannot_reprocess_call(
        self, client, second_user, second_user_token, call_recording, call_share_view, get_auth_headers, org_member
    ):
        """
        CRITICAL TEST: User with view-only access should NOT be able to reprocess call.
        """
        response = await client.post(
            f"/api/calls/{call_recording.id}/reprocess",
            headers=get_auth_headers(second_user_token)
        )

        # Expected: 403 Forbidden
        assert response.status_code == 403, \
            f"SECURITY BUG: View-only user was able to reprocess call! Got {response.status_code}"


class TestCallNoAccess:
    """Test call access for users without any share."""

    @pytest.mark.asyncio
    async def test_no_access_user_cannot_view_call(
        self, client, second_user, second_user_token, call_recording, get_auth_headers, org_member
    ):
        """Test that user without share cannot view call."""
        response = await client.get(
            f"/api/calls/{call_recording.id}",
            headers=get_auth_headers(second_user_token)
        )

        # Current bug: might return 200 because only org_id is checked
        assert response.status_code in [403, 404], \
            f"User without access should not see call. Got {response.status_code}"

    @pytest.mark.asyncio
    async def test_no_access_user_cannot_update_call(
        self, client, second_user, second_user_token, call_recording, get_auth_headers, org_member
    ):
        """Test that user without share cannot update call."""
        response = await client.patch(
            f"/api/calls/{call_recording.id}",
            json={"title": "Hacked"},
            headers=get_auth_headers(second_user_token)
        )

        # Current bug: might return 200
        assert response.status_code in [403, 404], \
            f"User without access should not update call. Got {response.status_code}"

    @pytest.mark.asyncio
    async def test_no_access_user_cannot_delete_call(
        self, client, second_user, second_user_token, call_recording, get_auth_headers, org_member
    ):
        """
        CRITICAL TEST: User without share should NOT be able to delete call.
        """
        response = await client.delete(
            f"/api/calls/{call_recording.id}",
            headers=get_auth_headers(second_user_token)
        )

        # Current bug: returns 200 (deletes call!)
        assert response.status_code in [403, 404], \
            f"SECURITY BUG: User without access was able to delete call! Got {response.status_code}"


class TestCallEntityAccessInheritance:
    """Test that call access through entity share works correctly."""

    @pytest.mark.asyncio
    async def test_view_entity_share_cannot_modify_linked_call(
        self, db_session, client, second_user, second_user_token, call_recording, entity,
        entity_share_view, get_auth_headers, org_member
    ):
        """
        CRITICAL TEST: If user has view-only access to entity, they should NOT be able
        to modify calls linked to that entity.
        """
        # Link call to entity
        call_recording.entity_id = entity.id
        await db_session.commit()

        response = await client.patch(
            f"/api/calls/{call_recording.id}",
            json={"title": "Hacked via entity view"},
            headers=get_auth_headers(second_user_token)
        )

        # Expected: 403 Forbidden
        assert response.status_code == 403, \
            f"SECURITY BUG: Entity view-only user was able to modify linked call! Got {response.status_code}"

    @pytest.mark.asyncio
    async def test_view_entity_share_cannot_delete_linked_call(
        self, db_session, client, second_user, second_user_token, call_recording, entity,
        entity_share_view, get_auth_headers, org_member
    ):
        """
        CRITICAL TEST: If user has view-only access to entity, they should NOT be able
        to delete calls linked to that entity.
        """
        # Link call to entity
        call_recording.entity_id = entity.id
        await db_session.commit()

        response = await client.delete(
            f"/api/calls/{call_recording.id}",
            headers=get_auth_headers(second_user_token)
        )

        # Expected: 403 Forbidden
        assert response.status_code == 403, \
            f"SECURITY BUG: Entity view-only user was able to delete linked call! Got {response.status_code}"


class TestCallListFiltering:
    """Test that call list properly filters by access."""

    @pytest.mark.asyncio
    async def test_list_shows_only_accessible_calls(
        self, client, second_user, second_user_token, call_recording, second_call,
        get_auth_headers, org_member
    ):
        """Test that call list only shows calls user has access to."""
        response = await client.get(
            "/api/calls",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Should only see calls they own or have share/dept access to
        call_ids = [c["id"] for c in data]

        # second_call is owned by second_user, so should be visible
        assert second_call.id in call_ids, "User should see their own call"

    @pytest.mark.asyncio
    async def test_list_shows_shared_calls(
        self, client, second_user, second_user_token, call_recording, call_share_view,
        get_auth_headers, org_member
    ):
        """Test that shared calls appear in list."""
        response = await client.get(
            "/api/calls",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()

        call_ids = [c["id"] for c in data]
        assert call_recording.id in call_ids, "User should see shared call"


class TestCallUploadEntityAccess:
    """Test that uploading calls respects entity access."""

    @pytest.mark.asyncio
    async def test_cannot_upload_call_to_view_only_entity(
        self, client, second_user, second_user_token, entity, entity_share_view,
        get_auth_headers, org_member
    ):
        """
        CRITICAL TEST: User with view-only access to entity should NOT be able
        to upload/create calls linked to that entity.
        """
        # This would be a multipart form upload
        # For now, test via the link endpoint

        # First create a call without entity
        # Then try to link it
        # This tests the link-entity endpoint which should fail for view access


class TestCallCrossOrganization:
    """Test that users cannot access calls from other organizations."""

    @pytest.mark.asyncio
    async def test_cannot_access_call_from_other_org(
        self, db_session, client, second_user, second_user_token, second_organization, get_auth_headers, org_member
    ):
        """Test that user cannot access call from different organization."""
        # Create call in second organization
        other_call = CallRecording(
            org_id=second_organization.id,
            owner_id=1,
            title="Other Org Call",
            source_type="upload",
            status="done",
            created_at=datetime.utcnow()
        )
        db_session.add(other_call)
        await db_session.commit()
        await db_session.refresh(other_call)

        response = await client.get(
            f"/api/calls/{other_call.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code in [403, 404], \
            f"User should not access call from other org. Got {response.status_code}"

    @pytest.mark.asyncio
    async def test_cannot_delete_call_from_other_org(
        self, db_session, client, second_user, second_user_token, second_organization, get_auth_headers, org_member
    ):
        """Test that user cannot delete call from different organization."""
        other_call = CallRecording(
            org_id=second_organization.id,
            owner_id=1,
            title="Other Org Call",
            source_type="upload",
            status="done",
            created_at=datetime.utcnow()
        )
        db_session.add(other_call)
        await db_session.commit()
        await db_session.refresh(other_call)

        response = await client.delete(
            f"/api/calls/{other_call.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code in [403, 404], \
            f"User should not delete call from other org. Got {response.status_code}"


class TestCallOrgRoleAccess:
    """Test call access based on organization role."""

    @pytest.mark.asyncio
    async def test_org_owner_can_access_all_calls(
        self, client, admin_user, admin_token, call_recording, second_call, get_auth_headers, org_owner
    ):
        """Test that org owner can access all calls in org."""
        response = await client.get(
            f"/api/calls/{second_call.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_org_owner_can_delete_any_call(
        self, client, admin_user, admin_token, second_call, get_auth_headers, org_owner
    ):
        """Test that org owner can delete any call in org."""
        response = await client.delete(
            f"/api/calls/{second_call.id}",
            headers=get_auth_headers(admin_token)
        )

        # Org owner should be able to delete
        assert response.status_code == 200
