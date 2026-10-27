"""
Comprehensive CRUD tests for sharing API routes.

Tests cover:
1. Create shares (POST /api/sharing) - all resource types and access levels
2. Read shares (GET /api/sharing/*) - my-shares, shared-with-me, resource shares
3. Update shares (PATCH /api/sharing/{id}) - access levels, notes, expiration
4. Delete shares (DELETE /api/sharing/{id}) - revocation
5. Get sharable users (GET /api/sharing/users)
6. Permission checks and error handling
7. Response structure validation
8. Filter parameters
"""
import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient

from api.models.database import (
    SharedAccess, AccessLevel, ResourceType, User, UserRole,
    OrgMember, OrgRole, Organization, Department, DepartmentMember, DeptRole,
    Entity, Chat, CallRecording, EntityType, EntityStatus, ChatType, CallStatus, CallSource
)
from api.services.auth import hash_password, create_access_token


# ============================================================================
# CREATE TESTS - POST /api/sharing
# ============================================================================

class TestCreateShare:
    """Test share creation for all resource types and access levels."""

    @pytest.mark.asyncio
    async def test_create_entity_share_view(
        self, client: AsyncClient, admin_user, admin_token, entity, second_user,
        get_auth_headers, org_owner, org_member
    ):
        """Test creating entity share with view access."""
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": second_user.id,
                "access_level": "view"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["resource_type"] == "entity"
        assert data["resource_id"] == entity.id
        assert data["access_level"] == "view"
        assert data["shared_by_id"] == admin_user.id
        assert data["shared_with_id"] == second_user.id
        assert data["shared_by_name"] == admin_user.name
        assert data["shared_with_name"] == second_user.name
        assert "id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_create_entity_share_edit(
        self, client: AsyncClient, admin_user, admin_token, entity, second_user,
        get_auth_headers, org_owner, org_member
    ):
        """Test creating entity share with edit access."""
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": second_user.id,
                "access_level": "edit"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["access_level"] == "edit"

    @pytest.mark.asyncio
    async def test_create_entity_share_full(
        self, client: AsyncClient, admin_user, admin_token, entity, second_user,
        get_auth_headers, org_owner, org_member
    ):
        """Test creating entity share with full access."""
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": second_user.id,
                "access_level": "full"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["access_level"] == "full"

    @pytest.mark.asyncio
    async def test_create_chat_share_view(
        self, client: AsyncClient, admin_user, admin_token, chat, second_user,
        get_auth_headers, org_owner, org_member
    ):
        """Test creating chat share with view access."""
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "chat",
                "resource_id": chat.id,
                "shared_with_id": second_user.id,
                "access_level": "view"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["resource_type"] == "chat"
        assert data["resource_id"] == chat.id
        assert data["access_level"] == "view"

    @pytest.mark.asyncio
    async def test_create_chat_share_edit(
        self, client: AsyncClient, admin_user, admin_token, chat, second_user,
        get_auth_headers, org_owner, org_member
    ):
        """Test creating chat share with edit access."""
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "chat",
                "resource_id": chat.id,
                "shared_with_id": second_user.id,
                "access_level": "edit"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["access_level"] == "edit"

    @pytest.mark.asyncio
    async def test_create_chat_share_full(
        self, client: AsyncClient, admin_user, admin_token, chat, second_user,
        get_auth_headers, org_owner, org_member
    ):
        """Test creating chat share with full access."""
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "chat",
                "resource_id": chat.id,
                "shared_with_id": second_user.id,
                "access_level": "full"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["access_level"] == "full"

    @pytest.mark.asyncio
    async def test_create_call_share_view(
        self, client: AsyncClient, admin_user, admin_token, call_recording, second_user,
        get_auth_headers, org_owner, org_member
    ):
        """Test creating call share with view access."""
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "call",
                "resource_id": call_recording.id,
                "shared_with_id": second_user.id,
                "access_level": "view"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["resource_type"] == "call"
        assert data["resource_id"] == call_recording.id
        assert data["access_level"] == "view"

    @pytest.mark.asyncio
    async def test_create_call_share_edit(
        self, client: AsyncClient, admin_user, admin_token, call_recording, second_user,
        get_auth_headers, org_owner, org_member
    ):
        """Test creating call share with edit access."""
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "call",
                "resource_id": call_recording.id,
                "shared_with_id": second_user.id,
                "access_level": "edit"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["access_level"] == "edit"

    @pytest.mark.asyncio
    async def test_create_call_share_full(
        self, client: AsyncClient, admin_user, admin_token, call_recording, second_user,
        get_auth_headers, org_owner, org_member
    ):
        """Test creating call share with full access."""
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "call",
                "resource_id": call_recording.id,
                "shared_with_id": second_user.id,
                "access_level": "full"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["access_level"] == "full"

    @pytest.mark.asyncio
    async def test_create_share_with_note(
        self, client: AsyncClient, admin_token, entity, second_user,
        get_auth_headers, org_owner, org_member
    ):
        """Test creating share with a note."""
        note = "Please review this candidate's profile"

        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": second_user.id,
                "access_level": "view",
                "note": note
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["note"] == note

    @pytest.mark.asyncio
    async def test_create_share_with_expiration(
        self, client: AsyncClient, admin_token, entity, second_user,
        get_auth_headers, org_owner, org_member
    ):
        """Test creating share with expiration date."""
        expires_at = datetime.utcnow() + timedelta(days=7)

        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": second_user.id,
                "access_level": "view",
                "expires_at": expires_at.isoformat()
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["expires_at"] is not None

    @pytest.mark.asyncio
    async def test_create_share_with_note_and_expiration(
        self, client: AsyncClient, admin_token, entity, second_user,
        get_auth_headers, org_owner, org_member
    ):
        """Test creating share with both note and expiration."""
        note = "Temporary access for review"
        expires_at = datetime.utcnow() + timedelta(hours=24)

        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": second_user.id,
                "access_level": "edit",
                "note": note,
                "expires_at": expires_at.isoformat()
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["note"] == note
        assert data["expires_at"] is not None
        assert data["access_level"] == "edit"

    @pytest.mark.asyncio
    async def test_update_existing_share(
        self, client: AsyncClient, admin_token, entity, second_user,
        get_auth_headers, org_owner, org_member
    ):
        """Test that creating duplicate share updates the existing one."""
        # Create initial share with view access
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": second_user.id,
                "access_level": "view",
                "note": "Initial share"
            },
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        share_id = response.json()["id"]

        # Create duplicate share with edit access and new note
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": second_user.id,
                "access_level": "edit",
                "note": "Updated share"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == share_id  # Same share ID
        assert data["access_level"] == "edit"  # Updated
        assert data["note"] == "Updated share"  # Updated


class TestCreateShareErrors:
    """Test error cases for share creation."""

    @pytest.mark.asyncio
    async def test_create_share_nonexistent_resource(
        self, client: AsyncClient, admin_token, second_user,
        get_auth_headers, org_owner, org_member
    ):
        """Test creating share for non-existent resource returns 404."""
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": 999999,
                "shared_with_id": second_user.id,
                "access_level": "view"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_share_nonexistent_user(
        self, client: AsyncClient, admin_token, entity,
        get_auth_headers, org_owner
    ):
        """Test creating share for non-existent user returns 404."""
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": 999999,
                "access_level": "view"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404
        assert "пользователь не найден" in response.json()["detail"].lower()  # текст ручки — по-русски

    @pytest.mark.asyncio
    async def test_create_share_not_owner(
        self, client: AsyncClient, second_user_token, entity, regular_user,
        get_auth_headers, org_member, org_admin
    ):
        """Test non-owner cannot create share returns 403."""
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": regular_user.id,
                "access_level": "view"
            },
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403
        assert "permission" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_share_cross_organization(
        self, db_session, client: AsyncClient, admin_token, entity,
        second_organization, get_auth_headers, org_owner
    ):
        """Test cannot share with user from different organization."""
        # Create user in different organization
        other_user = User(
            email="other@other.com",
            password_hash=hash_password("password"),
            name="Other Org User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)

        other_member = OrgMember(
            org_id=second_organization.id,
            user_id=other_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(other_member)
        await db_session.commit()

        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": other_user.id,
                "access_level": "view"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 403
        assert "другой организации" in response.json()["detail"].lower()  # текст ручки — по-русски

    @pytest.mark.asyncio
    async def test_create_share_invalid_access_level(
        self, client: AsyncClient, admin_token, entity, second_user,
        get_auth_headers, org_owner, org_member
    ):
        """Test invalid access level returns 422."""
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": second_user.id,
                "access_level": "invalid"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_share_invalid_resource_type(
        self, client: AsyncClient, admin_token, entity, second_user,
        get_auth_headers, org_owner, org_member
    ):
        """Test invalid resource type returns 422."""
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "invalid",
                "resource_id": entity.id,
                "shared_with_id": second_user.id,
                "access_level": "view"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_share_no_auth(
        self, client: AsyncClient, entity, second_user
    ):
        """Test creating share without authentication returns 401."""
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": second_user.id,
                "access_level": "view"
            }
        )

        assert response.status_code == 401


class TestCreateSharePermissions:
    """Test permission inheritance for share creation."""

    @pytest.mark.asyncio
    async def test_superadmin_can_share_any_resource(
        self, db_session, client: AsyncClient, superadmin_token, entity, second_user,
        organization, get_auth_headers, org_member
    ):
        """Test SUPERADMIN can share any resource."""
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": second_user.id,
                "access_level": "view"
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_user_with_full_access_can_reshare(
        self, db_session, client: AsyncClient, admin_user, admin_token,
        second_user, second_user_token, entity, regular_user,
        get_auth_headers, org_owner, org_member, org_admin
    ):
        """Test user with full access can reshare resource."""
        # Admin shares entity to second_user with full access
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": second_user.id,
                "access_level": "full"
            },
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200

        # second_user reshares to regular_user
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": regular_user.id,
                "access_level": "view"
            },
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["shared_by_id"] == second_user.id
        assert data["shared_with_id"] == regular_user.id

    @pytest.mark.asyncio
    async def test_user_with_edit_access_cannot_reshare(
        self, db_session, client: AsyncClient, admin_user, second_user,
        second_user_token, entity, regular_user,
        get_auth_headers, org_owner, org_member, org_admin
    ):
        """Test user with edit access cannot reshare resource."""
        # Create edit share
        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.edit,
            created_at=datetime.utcnow()
        )
        db_session.add(share)
        await db_session.commit()

        # Try to reshare
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": regular_user.id,
                "access_level": "view"
            },
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_user_with_view_access_cannot_reshare(
        self, client: AsyncClient, second_user_token, entity_share_view,
        regular_user, get_auth_headers, org_member, org_admin
    ):
        """Test user with view access cannot reshare resource."""
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity_share_view.resource_id,
                "shared_with_id": regular_user.id,
                "access_level": "view"
            },
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403


# ============================================================================
# READ TESTS - GET /api/sharing/my-shares
# ============================================================================

class TestGetMyShares:
    """Test retrieving shares created by current user."""

    @pytest.mark.asyncio
    async def test_get_my_shares_empty(
        self, client: AsyncClient, admin_token, get_auth_headers, org_owner
    ):
        """Test getting my shares when none exist."""
        response = await client.get(
            "/api/sharing/my-shares",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_get_my_shares_single(
        self, client: AsyncClient, admin_token, entity_share_view,
        get_auth_headers, org_owner
    ):
        """Test getting my shares with one share."""
        response = await client.get(
            "/api/sharing/my-shares",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == entity_share_view.id
        assert data[0]["resource_type"] == "entity"
        assert data[0]["access_level"] == "view"

    @pytest.mark.asyncio
    async def test_get_my_shares_multiple(
        self, client: AsyncClient, admin_token, entity_share_view,
        chat_share_view, call_share_view, get_auth_headers, org_owner
    ):
        """Test getting my shares with multiple shares."""
        response = await client.get(
            "/api/sharing/my-shares",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 3

        share_ids = [s["id"] for s in data]
        assert entity_share_view.id in share_ids
        assert chat_share_view.id in share_ids
        assert call_share_view.id in share_ids

    @pytest.mark.asyncio
    async def test_get_my_shares_filter_by_entity(
        self, client: AsyncClient, admin_token, entity_share_view,
        chat_share_view, call_share_view, get_auth_headers, org_owner
    ):
        """Test filtering my shares by entity resource type."""
        response = await client.get(
            "/api/sharing/my-shares?resource_type=entity",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert all(s["resource_type"] == "entity" for s in data)
        assert any(s["id"] == entity_share_view.id for s in data)

    @pytest.mark.asyncio
    async def test_get_my_shares_filter_by_chat(
        self, client: AsyncClient, admin_token, entity_share_view,
        chat_share_view, call_share_view, get_auth_headers, org_owner
    ):
        """Test filtering my shares by chat resource type."""
        response = await client.get(
            "/api/sharing/my-shares?resource_type=chat",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert all(s["resource_type"] == "chat" for s in data)
        assert any(s["id"] == chat_share_view.id for s in data)

    @pytest.mark.asyncio
    async def test_get_my_shares_filter_by_call(
        self, client: AsyncClient, admin_token, entity_share_view,
        chat_share_view, call_share_view, get_auth_headers, org_owner
    ):
        """Test filtering my shares by call resource type."""
        response = await client.get(
            "/api/sharing/my-shares?resource_type=call",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert all(s["resource_type"] == "call" for s in data)
        assert any(s["id"] == call_share_view.id for s in data)

    @pytest.mark.asyncio
    async def test_get_my_shares_includes_resource_names(
        self, client: AsyncClient, admin_token, entity_share_view,
        get_auth_headers, org_owner
    ):
        """Test my shares includes resource names."""
        response = await client.get(
            "/api/sharing/my-shares",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert "resource_name" in data[0]

    @pytest.mark.asyncio
    async def test_get_my_shares_sorted_by_created_at(
        self, db_session, client: AsyncClient, admin_user, admin_token,
        second_user, entity, organization, get_auth_headers, org_owner, org_member
    ):
        """Test my shares are sorted by created_at descending."""
        # Create multiple shares with different timestamps
        shares = []
        for i in range(3):
            # Create entities
            new_entity = Entity(
                org_id=organization.id,
                department_id=entity.department_id,
                created_by=admin_user.id,
                name=f"Entity {i}",
                email=f"entity{i}@test.com",
                type=EntityType.candidate,
                status=EntityStatus.active,
                created_at=datetime.utcnow()
            )
            db_session.add(new_entity)
            await db_session.commit()
            await db_session.refresh(new_entity)

            # Create share
            share = SharedAccess(
                resource_type=ResourceType.entity,
                resource_id=new_entity.id,
                entity_id=new_entity.id,
                shared_by_id=admin_user.id,
                shared_with_id=second_user.id,
                access_level=AccessLevel.view,
                created_at=datetime.utcnow() - timedelta(hours=i)
            )
            db_session.add(share)
            shares.append(share)

        await db_session.commit()

        response = await client.get(
            "/api/sharing/my-shares",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 3

        # Verify descending order (most recent first)
        timestamps = [s["created_at"] for s in data]
        assert timestamps == sorted(timestamps, reverse=True)


# ============================================================================
# READ TESTS - GET /api/sharing/shared-with-me
# ============================================================================

class TestGetSharedWithMe:
    """Test retrieving shares received by current user."""

    @pytest.mark.asyncio
    async def test_get_shared_with_me_empty(
        self, client: AsyncClient, admin_token, get_auth_headers, org_owner
    ):
        """Test getting shared-with-me when none exist."""
        response = await client.get(
            "/api/sharing/shared-with-me",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_shared_with_me_single(
        self, client: AsyncClient, second_user_token, entity_share_view,
        get_auth_headers, org_member
    ):
        """Test getting shared-with-me with one share."""
        response = await client.get(
            "/api/sharing/shared-with-me",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(s["id"] == entity_share_view.id for s in data)

    @pytest.mark.asyncio
    async def test_get_shared_with_me_multiple(
        self, client: AsyncClient, second_user_token, entity_share_view,
        chat_share_view, call_share_view, get_auth_headers, org_member
    ):
        """Test getting shared-with-me with multiple shares."""
        response = await client.get(
            "/api/sharing/shared-with-me",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 3

        share_ids = [s["id"] for s in data]
        assert entity_share_view.id in share_ids
        assert chat_share_view.id in share_ids
        assert call_share_view.id in share_ids

    @pytest.mark.asyncio
    async def test_get_shared_with_me_filter_by_entity(
        self, client: AsyncClient, second_user_token, entity_share_view,
        chat_share_view, get_auth_headers, org_member
    ):
        """Test filtering shared-with-me by entity resource type."""
        response = await client.get(
            "/api/sharing/shared-with-me?resource_type=entity",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert all(s["resource_type"] == "entity" for s in data)

    @pytest.mark.asyncio
    async def test_get_shared_with_me_filter_by_chat(
        self, client: AsyncClient, second_user_token, entity_share_view,
        chat_share_view, get_auth_headers, org_member
    ):
        """Test filtering shared-with-me by chat resource type."""
        response = await client.get(
            "/api/sharing/shared-with-me?resource_type=chat",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert all(s["resource_type"] == "chat" for s in data)

    @pytest.mark.asyncio
    async def test_get_shared_with_me_filter_by_call(
        self, client: AsyncClient, second_user_token, call_share_view,
        get_auth_headers, org_member
    ):
        """Test filtering shared-with-me by call resource type."""
        response = await client.get(
            "/api/sharing/shared-with-me?resource_type=call",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert all(s["resource_type"] == "call" for s in data)

    @pytest.mark.asyncio
    async def test_get_shared_with_me_excludes_expired(
        self, client: AsyncClient, second_user_token, expired_share,
        get_auth_headers, org_member
    ):
        """Test shared-with-me excludes expired shares."""
        response = await client.get(
            "/api/sharing/shared-with-me",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Expired share should not appear
        share_ids = [s["id"] for s in data]
        assert expired_share.id not in share_ids

    @pytest.mark.asyncio
    async def test_get_shared_with_me_includes_non_expired(
        self, db_session, client: AsyncClient, admin_user, second_user,
        second_user_token, entity, get_auth_headers, org_member
    ):
        """Test shared-with-me includes non-expired shares."""
        # Create share with future expiration
        future_share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.view,
            expires_at=datetime.utcnow() + timedelta(days=7),
            created_at=datetime.utcnow()
        )
        db_session.add(future_share)
        await db_session.commit()
        await db_session.refresh(future_share)

        response = await client.get(
            "/api/sharing/shared-with-me",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()

        share_ids = [s["id"] for s in data]
        assert future_share.id in share_ids


# ============================================================================
# READ TESTS - GET /api/sharing/resource/{resource_type}/{resource_id}
# ============================================================================

class TestGetResourceShares:
    """Test retrieving all shares for a specific resource."""

    @pytest.mark.asyncio
    async def test_get_resource_shares_as_owner(
        self, client: AsyncClient, admin_token, entity, entity_share_view,
        get_auth_headers, org_owner
    ):
        """Test owner can get all shares for their resource."""
        response = await client.get(
            f"/api/sharing/resource/entity/{entity.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(s["id"] == entity_share_view.id for s in data)

    @pytest.mark.asyncio
    async def test_get_resource_shares_as_shared_user(
        self, client: AsyncClient, second_user_token, entity,
        entity_share_view, get_auth_headers, org_member
    ):
        """Test user with shared access can see resource shares."""
        response = await client.get(
            f"/api/sharing/resource/entity/{entity.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_get_resource_shares_no_access(
        self, db_session, client: AsyncClient, entity, organization,
        get_auth_headers
    ):
        """Test user without access cannot see resource shares."""
        # Create a new user without access
        new_user = User(
            email="noauth@test.com",
            password_hash=hash_password("password"),
            name="No Access User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(new_user)
        await db_session.commit()
        await db_session.refresh(new_user)

        # Add to org
        org_member = OrgMember(
            org_id=organization.id,
            user_id=new_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(org_member)
        await db_session.commit()

        new_user_token = create_access_token(data={"sub": str(new_user.id)})

        response = await client.get(
            f"/api/sharing/resource/entity/{entity.id}",
            headers=get_auth_headers(new_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_resource_shares_multiple(
        self, db_session, client: AsyncClient, admin_user, admin_token,
        entity, organization, get_auth_headers, org_owner
    ):
        """Test getting multiple shares for same resource."""
        # Create multiple users and share with them
        users = []
        for i in range(3):
            user = User(
                email=f"user{i}@test.com",
                password_hash=hash_password("password"),
                name=f"User {i}",
                role=UserRole.admin,
                is_active=True
            )
            db_session.add(user)
            await db_session.commit()
            await db_session.refresh(user)

            # Add to org
            member = OrgMember(
                org_id=organization.id,
                user_id=user.id,
                role=OrgRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(member)
            await db_session.commit()

            # Create share
            share = SharedAccess(
                resource_type=ResourceType.entity,
                resource_id=entity.id,
                entity_id=entity.id,
                shared_by_id=admin_user.id,
                shared_with_id=user.id,
                access_level=AccessLevel.view,
                created_at=datetime.utcnow()
            )
            db_session.add(share)
            users.append(user)

        await db_session.commit()

        response = await client.get(
            f"/api/sharing/resource/entity/{entity.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 3

    @pytest.mark.asyncio
    async def test_get_resource_shares_chat(
        self, client: AsyncClient, admin_token, chat, chat_share_view,
        get_auth_headers, org_owner
    ):
        """Test getting shares for chat resource."""
        response = await client.get(
            f"/api/sharing/resource/chat/{chat.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(s["id"] == chat_share_view.id for s in data)

    @pytest.mark.asyncio
    async def test_get_resource_shares_call(
        self, client: AsyncClient, admin_token, call_recording,
        call_share_view, get_auth_headers, org_owner
    ):
        """Test getting shares for call resource."""
        response = await client.get(
            f"/api/sharing/resource/call/{call_recording.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(s["id"] == call_share_view.id for s in data)


# ============================================================================
# UPDATE TESTS - PATCH /api/sharing/{share_id}
# ============================================================================

class TestUpdateShare:
    """Test updating share properties."""

    @pytest.mark.asyncio
    async def test_update_access_level_view_to_edit(
        self, client: AsyncClient, admin_token, entity_share_view,
        get_auth_headers, org_owner
    ):
        """Test updating access level from view to edit."""
        response = await client.patch(
            f"/api/sharing/{entity_share_view.id}",
            json={"access_level": "edit"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["access_level"] == "edit"
        assert data["id"] == entity_share_view.id

    @pytest.mark.asyncio
    async def test_update_access_level_edit_to_full(
        self, client: AsyncClient, admin_token, entity_share_edit,
        get_auth_headers, org_owner
    ):
        """Test updating access level from edit to full."""
        response = await client.patch(
            f"/api/sharing/{entity_share_edit.id}",
            json={"access_level": "full"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["access_level"] == "full"

    @pytest.mark.asyncio
    async def test_update_access_level_full_to_view(
        self, db_session, client: AsyncClient, admin_user, admin_token,
        second_user, entity, get_auth_headers, org_owner, org_member
    ):
        """Test updating access level from full to view."""
        # Create full access share
        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.full,
            created_at=datetime.utcnow()
        )
        db_session.add(share)
        await db_session.commit()
        await db_session.refresh(share)

        response = await client.patch(
            f"/api/sharing/{share.id}",
            json={"access_level": "view"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["access_level"] == "view"

    @pytest.mark.asyncio
    async def test_update_note(
        self, client: AsyncClient, admin_token, entity_share_view,
        get_auth_headers, org_owner
    ):
        """Test updating share note."""
        new_note = "Updated note for this share"

        response = await client.patch(
            f"/api/sharing/{entity_share_view.id}",
            json={
                "access_level": "view",
                "note": new_note
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["note"] == new_note

    @pytest.mark.asyncio
    async def test_update_expiration(
        self, client: AsyncClient, admin_token, entity_share_view,
        get_auth_headers, org_owner
    ):
        """Test updating share expiration."""
        new_expiration = datetime.utcnow() + timedelta(days=14)

        response = await client.patch(
            f"/api/sharing/{entity_share_view.id}",
            json={
                "access_level": "view",
                "expires_at": new_expiration.isoformat()
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["expires_at"] is not None

    @pytest.mark.asyncio
    async def test_update_multiple_fields(
        self, client: AsyncClient, admin_token, entity_share_view,
        get_auth_headers, org_owner
    ):
        """Test updating multiple share fields at once."""
        new_note = "Comprehensive update"
        new_expiration = datetime.utcnow() + timedelta(days=30)

        response = await client.patch(
            f"/api/sharing/{entity_share_view.id}",
            json={
                "access_level": "edit",
                "note": new_note,
                "expires_at": new_expiration.isoformat()
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["access_level"] == "edit"
        assert data["note"] == new_note
        assert data["expires_at"] is not None

    @pytest.mark.asyncio
    async def test_update_share_nonexistent(
        self, client: AsyncClient, admin_token, get_auth_headers, org_owner
    ):
        """Test updating non-existent share returns 404."""
        response = await client.patch(
            "/api/sharing/999999",
            json={"access_level": "edit"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_share_not_creator(
        self, client: AsyncClient, second_user_token, entity_share_view,
        get_auth_headers, org_member
    ):
        """Test non-creator cannot update share."""
        response = await client.patch(
            f"/api/sharing/{entity_share_view.id}",
            json={"access_level": "edit"},
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_update_share_as_superadmin(
        self, client: AsyncClient, superadmin_token, entity_share_view,
        get_auth_headers
    ):
        """Test SUPERADMIN can update any share."""
        response = await client.patch(
            f"/api/sharing/{entity_share_view.id}",
            json={"access_level": "full"},
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["access_level"] == "full"


# ============================================================================
# DELETE TESTS - DELETE /api/sharing/{share_id}
# ============================================================================

class TestDeleteShare:
    """Test share revocation/deletion."""

    @pytest.mark.asyncio
    async def test_delete_share_as_creator(
        self, db_session, client: AsyncClient, admin_token, entity_share_view,
        get_auth_headers, org_owner
    ):
        """Test creator can delete their share."""
        share_id = entity_share_view.id

        response = await client.delete(
            f"/api/sharing/{share_id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify share is deleted
        from sqlalchemy import select
        result = await db_session.execute(
            select(SharedAccess).where(SharedAccess.id == share_id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_share_as_superadmin(
        self, db_session, client: AsyncClient, superadmin_token,
        entity_share_view, get_auth_headers
    ):
        """Test SUPERADMIN can delete any share."""
        share_id = entity_share_view.id

        response = await client.delete(
            f"/api/sharing/{share_id}",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_delete_share_not_creator(
        self, client: AsyncClient, second_user_token, entity_share_view,
        get_auth_headers, org_member
    ):
        """Test non-creator cannot delete share."""
        response = await client.delete(
            f"/api/sharing/{entity_share_view.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_share_nonexistent(
        self, client: AsyncClient, admin_token, get_auth_headers, org_owner
    ):
        """Test deleting non-existent share returns 404."""
        response = await client.delete(
            "/api/sharing/999999",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_all_shares_for_resource(
        self, db_session, client: AsyncClient, admin_user, admin_token,
        entity, organization, get_auth_headers, org_owner
    ):
        """Test deleting all shares for a resource."""
        # Create multiple shares
        users = []
        share_ids = []

        for i in range(3):
            user = User(
                email=f"deluser{i}@test.com",
                password_hash=hash_password("password"),
                name=f"Delete User {i}",
                role=UserRole.admin,
                is_active=True
            )
            db_session.add(user)
            await db_session.commit()
            await db_session.refresh(user)

            member = OrgMember(
                org_id=organization.id,
                user_id=user.id,
                role=OrgRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(member)
            await db_session.commit()

            share = SharedAccess(
                resource_type=ResourceType.entity,
                resource_id=entity.id,
                entity_id=entity.id,
                shared_by_id=admin_user.id,
                shared_with_id=user.id,
                access_level=AccessLevel.view,
                created_at=datetime.utcnow()
            )
            db_session.add(share)
            await db_session.commit()
            await db_session.refresh(share)

            users.append(user)
            share_ids.append(share.id)

        # Delete all shares
        for share_id in share_ids:
            response = await client.delete(
                f"/api/sharing/{share_id}",
                headers=get_auth_headers(admin_token)
            )
            assert response.status_code == 200

        # Verify all are deleted
        from sqlalchemy import select
        for share_id in share_ids:
            result = await db_session.execute(
                select(SharedAccess).where(SharedAccess.id == share_id)
            )
            assert result.scalar_one_or_none() is None


# ============================================================================
# GET SHARABLE USERS - GET /api/sharing/users
# ============================================================================

class TestGetSharableUsers:
    """Test retrieving users available for sharing."""

    @pytest.mark.asyncio
    async def test_get_sharable_users(
        self, client: AsyncClient, admin_token, second_user,
        get_auth_headers, org_owner, org_member
    ):
        """Test getting list of sharable users."""
        response = await client.get(
            "/api/sharing/users",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

        # Verify second_user is in the list
        user_ids = [u["id"] for u in data]
        assert second_user.id in user_ids

    @pytest.mark.asyncio
    async def test_get_sharable_users_excludes_self(
        self, client: AsyncClient, admin_user, admin_token,
        get_auth_headers, org_owner
    ):
        """Test sharable users excludes current user."""
        response = await client.get(
            "/api/sharing/users",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        user_ids = [u["id"] for u in data]
        assert admin_user.id not in user_ids

    @pytest.mark.asyncio
    async def test_get_sharable_users_same_org_only(
        self, db_session, client: AsyncClient, admin_token,
        second_organization, get_auth_headers, org_owner
    ):
        """Test sharable users only includes same organization."""
        # Create user in different org
        other_user = User(
            email="otherorg@test.com",
            password_hash=hash_password("password"),
            name="Other Org User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)

        other_member = OrgMember(
            org_id=second_organization.id,
            user_id=other_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(other_member)
        await db_session.commit()

        response = await client.get(
            "/api/sharing/users",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        user_ids = [u["id"] for u in data]
        assert other_user.id not in user_ids

    @pytest.mark.asyncio
    async def test_get_sharable_users_excludes_inactive(
        self, db_session, client: AsyncClient, admin_token, organization,
        get_auth_headers, org_owner
    ):
        """Test sharable users excludes inactive users."""
        # Create inactive user
        inactive_user = User(
            email="inactive@test.com",
            password_hash=hash_password("password"),
            name="Inactive User",
            role=UserRole.admin,
            is_active=False
        )
        db_session.add(inactive_user)
        await db_session.commit()
        await db_session.refresh(inactive_user)

        inactive_member = OrgMember(
            org_id=organization.id,
            user_id=inactive_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(inactive_member)
        await db_session.commit()

        response = await client.get(
            "/api/sharing/users",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        user_ids = [u["id"] for u in data]
        assert inactive_user.id not in user_ids

    @pytest.mark.asyncio
    async def test_get_sharable_users_includes_role_info(
        self, client: AsyncClient, admin_token, second_user,
        get_auth_headers, org_owner, org_member
    ):
        """Test sharable users includes role information."""
        response = await client.get(
            "/api/sharing/users",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

        # Verify structure
        user = data[0]
        assert "id" in user
        assert "name" in user
        assert "email" in user
        assert "org_role" in user

    @pytest.mark.asyncio
    async def test_get_sharable_users_includes_department_info(
        self, db_session, client: AsyncClient, admin_token, organization,
        department, second_user, get_auth_headers, org_owner, org_member
    ):
        """Test sharable users includes department information."""
        # Add second_user to department
        dept_member = DepartmentMember(
            department_id=department.id,
            user_id=second_user.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_member)
        await db_session.commit()

        response = await client.get(
            "/api/sharing/users",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Find second_user in response
        user_data = next((u for u in data if u["id"] == second_user.id), None)
        assert user_data is not None
        assert "department_id" in user_data
        assert "department_name" in user_data
        assert "department_role" in user_data

    @pytest.mark.asyncio
    async def test_get_sharable_users_no_org(
        self, db_session, client: AsyncClient, get_auth_headers
    ):
        """Test sharable users returns empty list when user has no org."""
        # Create user without org
        no_org_user = User(
            email="noorg@test.com",
            password_hash=hash_password("password"),
            name="No Org User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(no_org_user)
        await db_session.commit()
        await db_session.refresh(no_org_user)

        no_org_token = create_access_token(data={"sub": str(no_org_user.id)})

        response = await client.get(
            "/api/sharing/users",
            headers=get_auth_headers(no_org_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_get_sharable_users_sorted_by_name(
        self, db_session, client: AsyncClient, admin_token, organization,
        get_auth_headers, org_owner
    ):
        """Test sharable users are sorted by name."""
        # Create multiple users with different names
        names = ["Zoe", "Alice", "Mike", "Bob"]
        for name in names:
            user = User(
                email=f"{name.lower()}@test.com",
                password_hash=hash_password("password"),
                name=name,
                role=UserRole.admin,
                is_active=True
            )
            db_session.add(user)
            await db_session.commit()
            await db_session.refresh(user)

            member = OrgMember(
                org_id=organization.id,
                user_id=user.id,
                role=OrgRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(member)

        await db_session.commit()

        response = await client.get(
            "/api/sharing/users",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Verify sorted by name
        user_names = [u["name"] for u in data]
        assert user_names == sorted(user_names)
