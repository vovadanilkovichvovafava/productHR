"""
Comprehensive unit tests for organization CRUD operations.

Tests all endpoints in /api/routes/organizations.py:
- GET /organizations/current - Get current user's organization
- PUT /organizations/current - Update organization settings
- GET /organizations/current/members - List organization members
- POST /organizations/current/members - Invite new member
- PATCH /organizations/current/members/{user_id}/role - Update member role
- DELETE /organizations/current/members/{user_id} - Remove member
- GET /organizations/current/my-role - Get current user's role
"""
import pytest
from datetime import datetime
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from api.models.database import (
    User, Organization, OrgMember, OrgRole, UserRole,
    Entity, EntityType, Chat, CallRecording, CallSource,
    Department, DepartmentMember, DeptRole
)


class TestGetCurrentOrganization:
    """Tests for GET /organizations/current endpoint."""

    @pytest.mark.asyncio
    async def test_owner_can_view_organization(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test that organization owner can view their organization."""
        response = await client.get(
            "/api/organizations/current",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == organization.id
        assert data["name"] == organization.name
        assert data["slug"] == organization.slug
        assert data["subscription_plan"] == organization.subscription_plan.value
        assert "settings" in data
        assert "is_active" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_admin_can_view_organization(
        self, client: AsyncClient, regular_user: User, user_token: str,
        organization: Organization, org_admin: OrgMember, get_auth_headers
    ):
        """Test that organization admin can view their organization."""
        response = await client.get(
            "/api/organizations/current",
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == organization.id
        assert data["name"] == organization.name

    @pytest.mark.asyncio
    async def test_member_can_view_organization(
        self, client: AsyncClient, second_user: User, second_user_token: str,
        organization: Organization, org_member: OrgMember, get_auth_headers
    ):
        """Test that regular member can view their organization."""
        response = await client.get(
            "/api/organizations/current",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == organization.id

    @pytest.mark.asyncio
    async def test_non_member_cannot_view_organization(
        self, client: AsyncClient, regular_user: User, user_token: str,
        organization: Organization, get_auth_headers
    ):
        """Test that non-member cannot view organization."""
        # regular_user exists but has no org membership
        response = await client.get(
            "/api/organizations/current",
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 403
        assert "No organization access" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_superadmin_can_view_organization(
        self, client: AsyncClient, superadmin_user: User, superadmin_token: str,
        organization: Organization, get_auth_headers
    ):
        """Test that superadmin can view any organization."""
        response = await client.get(
            "/api/organizations/current",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        # Superadmin gets first organization
        assert data["id"] == organization.id

    @pytest.mark.asyncio
    async def test_organization_stats_are_returned(
        self, db_session: AsyncSession, client: AsyncClient, admin_user: User,
        admin_token: str, organization: Organization, department: Department,
        org_owner: OrgMember, get_auth_headers
    ):
        """Test that organization stats (counts) are returned correctly."""
        # Create some data (org_owner already exists as a member)
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Test Entity",
            email="test@example.com",
            type=EntityType.candidate,
            created_at=datetime.utcnow()
        )
        db_session.add(entity)

        chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=123456789,
            title="Test Chat",
            created_at=datetime.utcnow()
        )
        db_session.add(chat)

        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Test Call",
            duration_seconds=300,
            source_type=CallSource.upload,
            created_at=datetime.utcnow()
        )
        db_session.add(call)

        await db_session.commit()

        response = await client.get(
            "/api/organizations/current",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        # org_owner already exists, so members_count should be >= 1
        assert data["members_count"] >= 1
        assert data["entities_count"] >= 1
        assert data["chats_count"] >= 1
        assert data["calls_count"] >= 1

    @pytest.mark.asyncio
    async def test_organization_with_no_data_returns_zero_counts(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test that organization with no data returns zero counts (except members)."""
        response = await client.get(
            "/api/organizations/current",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        # At least owner exists
        assert data["members_count"] >= 1
        # These might be 0 if no data exists
        assert "entities_count" in data
        assert "chats_count" in data
        assert "calls_count" in data

    @pytest.mark.asyncio
    async def test_unauthenticated_user_cannot_view_organization(
        self, client: AsyncClient, organization: Organization
    ):
        """Test that unauthenticated user cannot view organization."""
        response = await client.get("/api/organizations/current")

        assert response.status_code == 401


class TestUpdateOrganization:
    """Tests for PUT /organizations/current endpoint."""

    @pytest.mark.asyncio
    async def test_owner_can_update_organization_name(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test that owner can update organization name."""
        response = await client.put(
            "/api/organizations/current",
            json={"name": "Updated Organization Name"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Organization Name"

    @pytest.mark.asyncio
    async def test_owner_can_update_organization_settings(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test that owner can update organization settings."""
        response = await client.put(
            "/api/organizations/current",
            json={"settings": {"theme": "dark", "notifications": True}},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["settings"]["theme"] == "dark"
        assert data["settings"]["notifications"] is True

    @pytest.mark.asyncio
    async def test_owner_can_update_both_name_and_settings(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test that owner can update both name and settings together."""
        response = await client.put(
            "/api/organizations/current",
            json={
                "name": "New Name",
                "settings": {"feature_flags": {"beta": True}}
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name"
        assert "feature_flags" in data["settings"]

    @pytest.mark.asyncio
    async def test_settings_are_merged_not_replaced(
        self, db_session: AsyncSession, client: AsyncClient, admin_user: User,
        admin_token: str, organization: Organization, org_owner: OrgMember,
        get_auth_headers
    ):
        """Test that settings are merged, not completely replaced."""
        # Set initial settings
        organization.settings = {"existing": "value", "keep": "this"}
        await db_session.commit()

        response = await client.put(
            "/api/organizations/current",
            json={"settings": {"new": "setting"}},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["settings"]["existing"] == "value"
        assert data["settings"]["keep"] == "this"
        assert data["settings"]["new"] == "setting"

    @pytest.mark.asyncio
    async def test_admin_cannot_update_organization(
        self, client: AsyncClient, regular_user: User, user_token: str,
        organization: Organization, org_admin: OrgMember, get_auth_headers
    ):
        """Test that organization admin cannot update organization (owner only)."""
        response = await client.put(
            "/api/organizations/current",
            json={"name": "Admin Tried Update"},
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 403
        assert "Owner access required" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_member_cannot_update_organization(
        self, client: AsyncClient, second_user: User, second_user_token: str,
        organization: Organization, org_member: OrgMember, get_auth_headers
    ):
        """Test that regular member cannot update organization."""
        response = await client.put(
            "/api/organizations/current",
            json={"name": "Member Tried Update"},
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_non_member_cannot_update_organization(
        self, client: AsyncClient, regular_user: User, user_token: str,
        organization: Organization, get_auth_headers
    ):
        """Test that non-member cannot update organization."""
        response = await client.put(
            "/api/organizations/current",
            json={"name": "Non-member Update"},
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_empty_name_validation(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test that empty name is rejected."""
        response = await client.put(
            "/api/organizations/current",
            json={"name": ""},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_name_too_long_validation(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test that name exceeding 255 characters is rejected."""
        long_name = "A" * 256
        response = await client.put(
            "/api/organizations/current",
            json={"name": long_name},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_update_with_null_values(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test that null values are ignored (not applied)."""
        original_name = organization.name
        response = await client.put(
            "/api/organizations/current",
            json={"name": None, "settings": {"new": "value"}},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        # Name should remain unchanged when null
        assert data["name"] == original_name
        assert data["settings"]["new"] == "value"


class TestListOrganizationMembers:
    """Tests for GET /organizations/current/members endpoint."""

    @pytest.mark.asyncio
    async def test_owner_can_list_members(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test that owner can list organization members."""
        response = await client.get(
            "/api/organizations/current/members",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        # Check owner is in the list
        owner_found = any(m["user_id"] == admin_user.id for m in data)
        assert owner_found

    @pytest.mark.asyncio
    async def test_admin_can_list_members(
        self, client: AsyncClient, regular_user: User, user_token: str,
        organization: Organization, org_admin: OrgMember, get_auth_headers
    ):
        """Test that admin can list organization members."""
        response = await client.get(
            "/api/organizations/current/members",
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_member_can_list_members(
        self, client: AsyncClient, second_user: User, second_user_token: str,
        organization: Organization, org_member: OrgMember, get_auth_headers
    ):
        """Test that regular member can list organization members."""
        response = await client.get(
            "/api/organizations/current/members",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_non_member_cannot_list_members(
        self, client: AsyncClient, regular_user: User, user_token: str,
        organization: Organization, get_auth_headers
    ):
        """Test that non-member cannot list organization members."""
        response = await client.get(
            "/api/organizations/current/members",
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_member_response_structure(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test that member response has correct structure."""
        response = await client.get(
            "/api/organizations/current/members",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        member = data[0]
        assert "id" in member
        assert "user_id" in member
        assert "user_email" in member
        assert "user_name" in member
        assert "role" in member
        assert "created_at" in member
        # invited_by_name is optional
        assert "invited_by_name" in member

    @pytest.mark.asyncio
    async def test_members_ordered_by_created_at(
        self, db_session: AsyncSession, client: AsyncClient, admin_user: User,
        admin_token: str, organization: Organization, org_owner: OrgMember,
        regular_user: User, second_user: User, get_auth_headers
    ):
        """Test that members are ordered by creation date."""
        # Create members with different timestamps
        member1 = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(member1)
        await db_session.commit()

        response = await client.get(
            "/api/organizations/current/members",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        # Should have at least 2 members (owner + member1)
        assert len(data) >= 2
        # Check they're ordered by created_at
        for i in range(len(data) - 1):
            assert data[i]["created_at"] <= data[i + 1]["created_at"]

    @pytest.mark.asyncio
    async def test_invited_by_name_populated(
        self, db_session: AsyncSession, client: AsyncClient, admin_user: User,
        admin_token: str, organization: Organization, org_owner: OrgMember,
        regular_user: User, get_auth_headers
    ):
        """Test that invited_by_name is populated correctly."""
        # Create member invited by admin_user
        member = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.member,
            invited_by=admin_user.id,
            created_at=datetime.utcnow()
        )
        db_session.add(member)
        await db_session.commit()

        response = await client.get(
            "/api/organizations/current/members",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        # Find the member we just created
        invited_member = next(m for m in data if m["user_id"] == regular_user.id)
        assert invited_member["invited_by_name"] == admin_user.name


class TestInviteMember:
    """Tests for POST /organizations/current/members endpoint."""

    @pytest.mark.asyncio
    async def test_owner_can_invite_member(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test that owner can invite new member."""
        response = await client.post(
            "/api/organizations/current/members",
            json={
                "email": "newmember@test.com",
                "name": "New Member",
                "password": "password123",
                "role": "member"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_email"] == "newmember@test.com"
        assert data["user_name"] == "New Member"
        assert data["role"] == "member"

    @pytest.mark.asyncio
    async def test_owner_can_invite_admin(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test that owner can invite admin."""
        response = await client.post(
            "/api/organizations/current/members",
            json={
                "email": "newadmin@test.com",
                "name": "New Admin",
                "password": "password123",
                "role": "admin"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "admin"

    @pytest.mark.asyncio
    async def test_owner_can_invite_owner(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test that owner can invite another owner."""
        response = await client.post(
            "/api/organizations/current/members",
            json={
                "email": "newowner@test.com",
                "name": "New Owner",
                "password": "password123",
                "role": "owner"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "owner"

    @pytest.mark.asyncio
    async def test_admin_can_invite_member(
        self, client: AsyncClient, regular_user: User, user_token: str,
        organization: Organization, org_admin: OrgMember, get_auth_headers
    ):
        """Test that admin can invite member."""
        response = await client.post(
            "/api/organizations/current/members",
            json={
                "email": "member@test.com",
                "name": "Member",
                "password": "password123",
                "role": "member"
            },
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "member"

    @pytest.mark.asyncio
    async def test_admin_can_invite_admin(
        self, client: AsyncClient, regular_user: User, user_token: str,
        organization: Organization, org_admin: OrgMember, get_auth_headers
    ):
        """Test that admin can invite admin (based on code implementation)."""
        response = await client.post(
            "/api/organizations/current/members",
            json={
                "email": "admin2@test.com",
                "name": "Admin 2",
                "password": "password123",
                "role": "admin"
            },
            headers=get_auth_headers(user_token)
        )

        # Code allows this
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "admin"

    @pytest.mark.asyncio
    async def test_admin_cannot_invite_owner(
        self, client: AsyncClient, regular_user: User, user_token: str,
        organization: Organization, org_admin: OrgMember, get_auth_headers
    ):
        """Test that admin cannot invite owner."""
        response = await client.post(
            "/api/organizations/current/members",
            json={
                "email": "owner2@test.com",
                "name": "Owner 2",
                "password": "password123",
                "role": "owner"
            },
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 403
        assert "Only owner can add owners" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_member_cannot_invite(
        self, client: AsyncClient, second_user: User, second_user_token: str,
        organization: Organization, org_member: OrgMember, get_auth_headers
    ):
        """Test that regular member cannot invite."""
        response = await client.post(
            "/api/organizations/current/members",
            json={
                "email": "someone@test.com",
                "name": "Someone",
                "password": "password123",
                "role": "member"
            },
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_cannot_invite_duplicate_email(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        organization: Organization, org_owner: OrgMember, second_user: User,
        org_member: OrgMember, get_auth_headers
    ):
        """Test that cannot invite user who is already a member."""
        response = await client.post(
            "/api/organizations/current/members",
            json={
                "email": second_user.email,
                "name": "Duplicate",
                "password": "password123",
                "role": "member"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 400
        assert "already a member" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_can_add_existing_user_to_org(
        self, db_session: AsyncSession, client: AsyncClient, admin_user: User,
        admin_token: str, organization: Organization, org_owner: OrgMember,
        get_auth_headers
    ):
        """Test that existing user can be added to organization."""
        # Create a user not in the org
        existing_user = User(
            email="existing@test.com",
            password_hash="hash",
            name="Existing User",
            role=UserRole.admin
        )
        db_session.add(existing_user)
        await db_session.commit()
        await db_session.refresh(existing_user)

        response = await client.post(
            "/api/organizations/current/members",
            json={
                "email": existing_user.email,
                "name": "Any Name",  # Should be ignored
                "password": "password123",  # Should be ignored
                "role": "member"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_email"] == existing_user.email
        assert data["user_name"] == existing_user.name  # Original name kept

    @pytest.mark.asyncio
    async def test_invite_with_department_assignment(
        self, db_session: AsyncSession, client: AsyncClient, admin_user: User,
        admin_token: str, organization: Organization, department: Department,
        org_owner: OrgMember, get_auth_headers
    ):
        """Test inviting member with department assignment."""
        response = await client.post(
            "/api/organizations/current/members",
            json={
                "email": "deptmember@test.com",
                "name": "Dept Member",
                "password": "password123",
                "role": "member",
                "department_ids": [department.id],
                "department_role": "member"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Verify department membership was created
        new_user_id = data["user_id"]
        result = await db_session.execute(
            select(DepartmentMember).where(
                DepartmentMember.user_id == new_user_id,
                DepartmentMember.department_id == department.id
            )
        )
        dept_member = result.scalar_one_or_none()
        assert dept_member is not None
        assert dept_member.role == DeptRole.member

    @pytest.mark.asyncio
    async def test_invite_with_department_lead_role(
        self, db_session: AsyncSession, client: AsyncClient, admin_user: User,
        admin_token: str, organization: Organization, department: Department,
        org_owner: OrgMember, get_auth_headers
    ):
        """Test that owner/admin can assign lead role in department."""
        response = await client.post(
            "/api/organizations/current/members",
            json={
                "email": "deptlead@test.com",
                "name": "Dept Lead",
                "password": "password123",
                "role": "member",
                "department_ids": [department.id],
                "department_role": "lead"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Verify department leadership was created
        new_user_id = data["user_id"]
        result = await db_session.execute(
            select(DepartmentMember).where(
                DepartmentMember.user_id == new_user_id,
                DepartmentMember.department_id == department.id
            )
        )
        dept_member = result.scalar_one_or_none()
        assert dept_member is not None
        assert dept_member.role == DeptRole.lead

    @pytest.mark.asyncio
    async def test_invite_ignores_invalid_department_ids(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test that invalid department IDs are ignored silently."""
        response = await client.post(
            "/api/organizations/current/members",
            json={
                "email": "member@test.com",
                "name": "Member",
                "password": "password123",
                "role": "member",
                "department_ids": [99999],  # Non-existent
                "department_role": "member"
            },
            headers=get_auth_headers(admin_token)
        )

        # Should succeed but ignore invalid department
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_password_too_short_validation(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test that password shorter than 8 characters is rejected."""
        response = await client.post(
            "/api/organizations/current/members",
            json={
                "email": "test@test.com",
                "name": "Test",
                "password": "short",  # Less than 8 chars
                "role": "member"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_invalid_email_validation(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test that invalid email is rejected."""
        response = await client.post(
            "/api/organizations/current/members",
            json={
                "email": "not-an-email",
                "name": "Test",
                "password": "password123",
                "role": "member"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_invalid_role_defaults_to_member(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test that invalid role defaults to member."""
        response = await client.post(
            "/api/organizations/current/members",
            json={
                "email": "test@test.com",
                "name": "Test",
                "password": "password123",
                "role": "invalid_role"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "member"  # Defaults to member


class TestUpdateMemberRole:
    """Tests for PUT /organizations/current/members/{user_id} endpoint."""

    @pytest.mark.asyncio
    async def test_owner_can_promote_member_to_admin(
        self, db_session: AsyncSession, client: AsyncClient, admin_user: User,
        admin_token: str, organization: Organization, org_owner: OrgMember,
        second_user: User, get_auth_headers
    ):
        """Test that owner can promote member to admin."""
        # Create member
        member = OrgMember(
            org_id=organization.id,
            user_id=second_user.id,
            role=OrgRole.member
        )
        db_session.add(member)
        await db_session.commit()

        response = await client.patch(
            f"/api/organizations/current/members/{second_user.id}/role",
            json={"role": "admin"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["role"] == "admin"

    @pytest.mark.asyncio
    async def test_owner_can_demote_admin_to_member(
        self, db_session: AsyncSession, client: AsyncClient, admin_user: User,
        admin_token: str, organization: Organization, org_owner: OrgMember,
        second_user: User, get_auth_headers
    ):
        """Test that owner can demote admin to member."""
        # Create admin
        admin = OrgMember(
            org_id=organization.id,
            user_id=second_user.id,
            role=OrgRole.admin
        )
        db_session.add(admin)
        await db_session.commit()

        response = await client.patch(
            f"/api/organizations/current/members/{second_user.id}/role",
            json={"role": "member"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "member"

    @pytest.mark.asyncio
    async def test_owner_can_promote_member_to_owner(
        self, db_session: AsyncSession, client: AsyncClient, admin_user: User,
        admin_token: str, organization: Organization, org_owner: OrgMember,
        second_user: User, get_auth_headers
    ):
        """Test that owner can promote member to owner."""
        # Create member
        member = OrgMember(
            org_id=organization.id,
            user_id=second_user.id,
            role=OrgRole.member
        )
        db_session.add(member)
        await db_session.commit()

        response = await client.patch(
            f"/api/organizations/current/members/{second_user.id}/role",
            json={"role": "owner"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "owner"

    @pytest.mark.asyncio
    async def test_owner_can_demote_owner_to_admin(
        self, db_session: AsyncSession, client: AsyncClient, admin_user: User,
        admin_token: str, organization: Organization, org_owner: OrgMember,
        second_user: User, get_auth_headers
    ):
        """Test that owner can demote another owner to admin."""
        # Create second owner
        owner2 = OrgMember(
            org_id=organization.id,
            user_id=second_user.id,
            role=OrgRole.owner
        )
        db_session.add(owner2)
        await db_session.commit()

        response = await client.patch(
            f"/api/organizations/current/members/{second_user.id}/role",
            json={"role": "admin"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "admin"

    @pytest.mark.asyncio
    async def test_admin_can_promote_member_to_admin(
        self, db_session: AsyncSession, client: AsyncClient, regular_user: User,
        user_token: str, organization: Organization, org_admin: OrgMember,
        second_user: User, get_auth_headers
    ):
        """Test that admin can promote member to admin."""
        # Create member
        member = OrgMember(
            org_id=organization.id,
            user_id=second_user.id,
            role=OrgRole.member
        )
        db_session.add(member)
        await db_session.commit()

        response = await client.patch(
            f"/api/organizations/current/members/{second_user.id}/role",
            json={"role": "admin"},
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "admin"

    @pytest.mark.asyncio
    async def test_admin_cannot_promote_to_owner(
        self, db_session: AsyncSession, client: AsyncClient, regular_user: User,
        user_token: str, organization: Organization, org_admin: OrgMember,
        second_user: User, get_auth_headers
    ):
        """Test that admin cannot promote member to owner."""
        # Create member
        member = OrgMember(
            org_id=organization.id,
            user_id=second_user.id,
            role=OrgRole.member
        )
        db_session.add(member)
        await db_session.commit()

        response = await client.patch(
            f"/api/organizations/current/members/{second_user.id}/role",
            json={"role": "owner"},
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 403
        assert "Only owner can manage owner roles" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_admin_cannot_demote_owner(
        self, db_session: AsyncSession, client: AsyncClient, regular_user: User,
        user_token: str, organization: Organization, org_admin: OrgMember,
        admin_user: User, org_owner: OrgMember, get_auth_headers
    ):
        """Test that admin cannot demote owner."""
        response = await client.patch(
            f"/api/organizations/current/members/{admin_user.id}/role",
            json={"role": "member"},
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 403
        assert "Only owner can manage owner roles" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_member_cannot_update_roles(
        self, db_session: AsyncSession, client: AsyncClient, second_user: User,
        second_user_token: str, organization: Organization, org_member: OrgMember,
        regular_user: User, get_auth_headers
    ):
        """Test that regular member cannot update roles."""
        # Create another member
        member2 = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.member
        )
        db_session.add(member2)
        await db_session.commit()

        response = await client.patch(
            f"/api/organizations/current/members/{regular_user.id}/role",
            json={"role": "admin"},
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_cannot_change_own_role(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test that user cannot change their own role."""
        response = await client.patch(
            f"/api/organizations/current/members/{admin_user.id}/role",
            json={"role": "member"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 400
        assert "Cannot change own role" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_cannot_update_non_existent_member(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test that updating non-existent member returns 404."""
        response = await client.patch(
            "/api/organizations/current/members/99999/role",
            json={"role": "admin"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404
        assert "Member not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_invalid_role_returns_400(
        self, db_session: AsyncSession, client: AsyncClient, admin_user: User,
        admin_token: str, organization: Organization, org_owner: OrgMember,
        second_user: User, get_auth_headers
    ):
        """Test that invalid role returns 400."""
        # Create member
        member = OrgMember(
            org_id=organization.id,
            user_id=second_user.id,
            role=OrgRole.member
        )
        db_session.add(member)
        await db_session.commit()

        response = await client.patch(
            f"/api/organizations/current/members/{second_user.id}/role",
            json={"role": "invalid_role"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 400
        assert "Invalid role" in response.json()["detail"]


class TestRemoveMember:
    """Tests for DELETE /organizations/current/members/{user_id} endpoint."""

    @pytest.mark.asyncio
    async def test_owner_can_remove_member(
        self, db_session: AsyncSession, client: AsyncClient, admin_user: User,
        admin_token: str, organization: Organization, org_owner: OrgMember,
        second_user: User, get_auth_headers
    ):
        """Test that owner can remove member."""
        # Create member
        member = OrgMember(
            org_id=organization.id,
            user_id=second_user.id,
            role=OrgRole.member
        )
        db_session.add(member)
        await db_session.commit()

        response = await client.delete(
            f"/api/organizations/current/members/{second_user.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_owner_can_remove_admin(
        self, db_session: AsyncSession, client: AsyncClient, admin_user: User,
        admin_token: str, organization: Organization, org_owner: OrgMember,
        second_user: User, get_auth_headers
    ):
        """Test that owner can remove admin."""
        # Create admin
        admin = OrgMember(
            org_id=organization.id,
            user_id=second_user.id,
            role=OrgRole.admin
        )
        db_session.add(admin)
        await db_session.commit()

        response = await client.delete(
            f"/api/organizations/current/members/{second_user.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_owner_cannot_remove_owner(
        self, db_session: AsyncSession, client: AsyncClient, admin_user: User,
        admin_token: str, organization: Organization, org_owner: OrgMember,
        second_user: User, get_auth_headers
    ):
        """Test that owner cannot remove another owner."""
        # Create second owner
        owner2 = OrgMember(
            org_id=organization.id,
            user_id=second_user.id,
            role=OrgRole.owner
        )
        db_session.add(owner2)
        await db_session.commit()

        response = await client.delete(
            f"/api/organizations/current/members/{second_user.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 403
        assert "Cannot remove other owners" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_admin_can_remove_member(
        self, db_session: AsyncSession, client: AsyncClient, regular_user: User,
        user_token: str, organization: Organization, org_admin: OrgMember,
        second_user: User, department: Department, get_auth_headers
    ):
        """Test that admin can remove member of their own department.

        Админ орга удаляет только участников СВОЕГО отдела (remove_member:
        «Admin can only remove members from their own department»), поэтому
        оба стоят в одном отделе.
        """
        # Create member
        member = OrgMember(
            org_id=organization.id,
            user_id=second_user.id,
            role=OrgRole.member
        )
        db_session.add(member)
        db_session.add(DepartmentMember(
            department_id=department.id, user_id=regular_user.id, role=DeptRole.lead,
        ))
        db_session.add(DepartmentMember(
            department_id=department.id, user_id=second_user.id, role=DeptRole.member,
        ))
        await db_session.commit()

        response = await client.delete(
            f"/api/organizations/current/members/{second_user.id}",
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_admin_cannot_remove_admin(
        self, db_session: AsyncSession, client: AsyncClient, regular_user: User,
        user_token: str, organization: Organization, org_admin: OrgMember,
        second_user: User, get_auth_headers
    ):
        """Test that admin cannot remove another admin."""
        # Create second admin
        admin2 = OrgMember(
            org_id=organization.id,
            user_id=second_user.id,
            role=OrgRole.admin
        )
        db_session.add(admin2)
        await db_session.commit()

        response = await client.delete(
            f"/api/organizations/current/members/{second_user.id}",
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 403
        assert "Admins can only remove members" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_admin_cannot_remove_owner(
        self, client: AsyncClient, regular_user: User, user_token: str,
        organization: Organization, org_admin: OrgMember, admin_user: User,
        org_owner: OrgMember, get_auth_headers
    ):
        """Test that admin cannot remove owner."""
        response = await client.delete(
            f"/api/organizations/current/members/{admin_user.id}",
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 403
        assert "Admins can only remove members" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_member_cannot_remove_anyone(
        self, db_session: AsyncSession, client: AsyncClient, second_user: User,
        second_user_token: str, organization: Organization, org_member: OrgMember,
        regular_user: User, get_auth_headers
    ):
        """Test that regular member cannot remove anyone."""
        # Create another member
        member2 = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.member
        )
        db_session.add(member2)
        await db_session.commit()

        response = await client.delete(
            f"/api/organizations/current/members/{regular_user.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_cannot_remove_self(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test that user cannot remove themselves."""
        response = await client.delete(
            f"/api/organizations/current/members/{admin_user.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 400
        assert "Cannot remove yourself" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_superadmin_can_remove_anyone(
        self, db_session: AsyncSession, client: AsyncClient, superadmin_user: User,
        superadmin_token: str, organization: Organization, admin_user: User,
        get_auth_headers
    ):
        """Test that superadmin can remove anyone including owners."""
        # Create owner
        owner = OrgMember(
            org_id=organization.id,
            user_id=admin_user.id,
            role=OrgRole.owner
        )
        db_session.add(owner)
        await db_session.commit()

        response = await client.delete(
            f"/api/organizations/current/members/{admin_user.id}",
            headers=get_auth_headers(superadmin_token)
        )

        # Superadmin can remove anyone
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_removing_last_membership_deletes_user(
        self, db_session: AsyncSession, client: AsyncClient, admin_user: User,
        admin_token: str, organization: Organization, org_owner: OrgMember,
        get_auth_headers
    ):
        """Test that removing user's last membership deletes the user."""
        # Create user with single membership
        new_user = User(
            email="tobedeleted@test.com",
            password_hash="hash",
            name="To Be Deleted",
            role=UserRole.admin
        )
        db_session.add(new_user)
        await db_session.flush()

        member = OrgMember(
            org_id=organization.id,
            user_id=new_user.id,
            role=OrgRole.member
        )
        db_session.add(member)
        await db_session.commit()

        user_id = new_user.id

        response = await client.delete(
            f"/api/organizations/current/members/{user_id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_deleted"] is True

        # Verify user was deleted
        result = await db_session.execute(select(User).where(User.id == user_id))
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_removing_membership_keeps_user_if_has_other_orgs(
        self, db_session: AsyncSession, client: AsyncClient, admin_user: User,
        admin_token: str, organization: Organization, org_owner: OrgMember,
        get_auth_headers
    ):
        """Test that user is kept if they have memberships in other orgs."""
        # Create user
        new_user = User(
            email="multiorg@test.com",
            password_hash="hash",
            name="Multi Org User",
            role=UserRole.admin
        )
        db_session.add(new_user)
        await db_session.flush()

        # Create second org
        org2 = Organization(
            name="Second Org",
            slug="second-org"
        )
        db_session.add(org2)
        await db_session.flush()

        # Add user to both orgs
        member1 = OrgMember(
            org_id=organization.id,
            user_id=new_user.id,
            role=OrgRole.member
        )
        member2 = OrgMember(
            org_id=org2.id,
            user_id=new_user.id,
            role=OrgRole.member
        )
        db_session.add_all([member1, member2])
        await db_session.commit()

        user_id = new_user.id

        # Remove from first org
        response = await client.delete(
            f"/api/organizations/current/members/{user_id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_deleted"] is False

        # Verify user still exists
        result = await db_session.execute(select(User).where(User.id == user_id))
        assert result.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_superadmin_user_never_deleted(
        self, db_session: AsyncSession, client: AsyncClient, admin_user: User,
        admin_token: str, organization: Organization, org_owner: OrgMember,
        superadmin_user: User, get_auth_headers
    ):
        """Test that superadmin user is never deleted even if last membership."""
        # Add superadmin to org
        member = OrgMember(
            org_id=organization.id,
            user_id=superadmin_user.id,
            role=OrgRole.member
        )
        db_session.add(member)
        await db_session.commit()

        superadmin_id = superadmin_user.id

        response = await client.delete(
            f"/api/organizations/current/members/{superadmin_id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

        # Verify superadmin still exists
        result = await db_session.execute(
            select(User).where(User.id == superadmin_id)
        )
        assert result.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_remove_non_existent_member(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test that removing non-existent member returns 404."""
        response = await client.delete(
            "/api/organizations/current/members/99999",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404
        assert "Member not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_user_deletion_cleans_up_foreign_keys(
        self, db_session: AsyncSession, client: AsyncClient, admin_user: User,
        admin_token: str, organization: Organization, department: Department,
        org_owner: OrgMember, get_auth_headers
    ):
        """Test that user deletion properly cleans up all foreign key references."""
        # Create user with various associated data
        new_user = User(
            email="cleanup@test.com",
            password_hash="hash",
            name="Cleanup User",
            role=UserRole.admin
        )
        db_session.add(new_user)
        await db_session.flush()

        # Add to org
        member = OrgMember(
            org_id=organization.id,
            user_id=new_user.id,
            role=OrgRole.member
        )
        db_session.add(member)
        await db_session.flush()

        # Add to department
        dept_member = DepartmentMember(
            department_id=department.id,
            user_id=new_user.id,
            role=DeptRole.member
        )
        db_session.add(dept_member)

        # Create entity
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=new_user.id,
            name="User Entity",
            email="entity@test.com",
            type=EntityType.candidate
        )
        db_session.add(entity)

        await db_session.commit()

        user_id = new_user.id
        entity_id = entity.id

        # Remove user
        response = await client.delete(
            f"/api/organizations/current/members/{user_id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

        # Verify department membership deleted
        result = await db_session.execute(
            select(DepartmentMember).where(DepartmentMember.user_id == user_id)
        )
        assert result.scalar_one_or_none() is None

        # Verify entity still exists but created_by nullified
        result = await db_session.execute(
            select(Entity).where(Entity.id == entity_id)
        )
        entity = result.scalar_one_or_none()
        assert entity is not None
        assert entity.created_by is None


class TestGetMyRole:
    """Tests for GET /organizations/current/my-role endpoint."""

    @pytest.mark.asyncio
    async def test_owner_gets_owner_role(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test that owner gets their role correctly."""
        response = await client.get(
            "/api/organizations/current/my-role",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "owner"
        assert data["org_id"] == organization.id
        assert data["org_name"] == organization.name

    @pytest.mark.asyncio
    async def test_admin_gets_admin_role(
        self, client: AsyncClient, regular_user: User, user_token: str,
        organization: Organization, org_admin: OrgMember, get_auth_headers
    ):
        """Test that admin gets their role correctly."""
        response = await client.get(
            "/api/organizations/current/my-role",
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "admin"
        assert data["org_id"] == organization.id
        assert data["org_name"] == organization.name

    @pytest.mark.asyncio
    async def test_member_gets_member_role(
        self, client: AsyncClient, second_user: User, second_user_token: str,
        organization: Organization, org_member: OrgMember, get_auth_headers
    ):
        """Test that member gets their role correctly."""
        response = await client.get(
            "/api/organizations/current/my-role",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "member"
        assert data["org_id"] == organization.id

    @pytest.mark.asyncio
    async def test_non_member_gets_403(
        self, client: AsyncClient, regular_user: User, user_token: str,
        organization: Organization, get_auth_headers
    ):
        """Test that non-member cannot get role."""
        response = await client.get(
            "/api/organizations/current/my-role",
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_unauthenticated_gets_401(
        self, client: AsyncClient, organization: Organization
    ):
        """Test that unauthenticated user gets 401."""
        response = await client.get("/api/organizations/current/my-role")

        assert response.status_code == 401


class TestOrganizationPermissions:
    """Integration tests for organization permissions across roles."""

    @pytest.mark.asyncio
    async def test_complete_owner_workflow(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test complete workflow for owner: create, update, view, remove member."""
        # View org
        response = await client.get(
            "/api/organizations/current",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200

        # Update org
        response = await client.put(
            "/api/organizations/current",
            json={"name": "Updated Name"},
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200

        # Invite member
        response = await client.post(
            "/api/organizations/current/members",
            json={
                "email": "workflow@test.com",
                "name": "Workflow User",
                "password": "password123",
                "role": "member"
            },
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        new_user_id = response.json()["user_id"]

        # Update role
        response = await client.patch(
            f"/api/organizations/current/members/{new_user_id}/role",
            json={"role": "admin"},
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200

        # Remove member
        response = await client.delete(
            f"/api/organizations/current/members/{new_user_id}",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_limited_workflow(
        self, client: AsyncClient, regular_user: User, user_token: str,
        organization: Organization, org_admin: OrgMember, get_auth_headers
    ):
        """Test admin can view, invite, and manage members but not update org."""
        # Can view org
        response = await client.get(
            "/api/organizations/current",
            headers=get_auth_headers(user_token)
        )
        assert response.status_code == 200

        # Cannot update org
        response = await client.put(
            "/api/organizations/current",
            json={"name": "Admin Update"},
            headers=get_auth_headers(user_token)
        )
        assert response.status_code == 403

        # Can invite member
        response = await client.post(
            "/api/organizations/current/members",
            json={
                "email": "adminworkflow@test.com",
                "name": "Admin Workflow",
                "password": "password123",
                "role": "member"
            },
            headers=get_auth_headers(user_token)
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_member_read_only_workflow(
        self, client: AsyncClient, second_user: User, second_user_token: str,
        organization: Organization, org_member: OrgMember, get_auth_headers
    ):
        """Test member can only view org and members."""
        # Can view org
        response = await client.get(
            "/api/organizations/current",
            headers=get_auth_headers(second_user_token)
        )
        assert response.status_code == 200

        # Can view members
        response = await client.get(
            "/api/organizations/current/members",
            headers=get_auth_headers(second_user_token)
        )
        assert response.status_code == 200

        # Cannot update org
        response = await client.put(
            "/api/organizations/current",
            json={"name": "Member Update"},
            headers=get_auth_headers(second_user_token)
        )
        assert response.status_code == 403

        # Cannot invite
        response = await client.post(
            "/api/organizations/current/members",
            json={
                "email": "test@test.com",
                "name": "Test",
                "password": "password123",
                "role": "member"
            },
            headers=get_auth_headers(second_user_token)
        )
        assert response.status_code == 403
