"""
Tests for admin sandbox test environment endpoints.

These tests verify that the sandbox creation, deletion, status check, and quick switch
endpoints work correctly for creating isolated test environments.
"""
import pytest
from httpx import AsyncClient

from api.models.database import (
    User, UserRole, Organization, OrgMember, OrgRole,
    Department, DepartmentMember, DeptRole,
    Entity, Chat, CallRecording, SharedAccess
)
from api.services.auth import create_access_token


# ============================================================================
# TEST CLASS: Sandbox Creation
# ============================================================================

@pytest.mark.asyncio
class TestSandboxCreate:
    """
    Test POST /api/admin/sandbox/create endpoint.

    Creates a complete test environment with users, entities, chats, calls, and shared access.
    """

    async def test_create_sandbox_success(self, client: AsyncClient, superadmin_user: User, organization: Organization, db_session):
        """Test successful sandbox creation."""
        # Add superadmin to organization
        org_member = OrgMember(
            org_id=organization.id,
            user_id=superadmin_user.id,
            role=OrgRole.owner
        )
        db_session.add(org_member)
        await db_session.commit()

        token = create_access_token(data={"sub": str(superadmin_user.id), "token_version": superadmin_user.token_version})

        response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "department_id" in data
        assert "users" in data
        assert "entities" in data
        assert "chats" in data
        assert "calls" in data

        # Verify users created
        assert len(data["users"]) == 4
        user_emails = [u["email"] for u in data["users"]]
        assert "sandbox_owner@test.local" in user_emails
        assert "sandbox_admin@test.local" in user_emails
        assert "sandbox_subadmin@test.local" in user_emails
        assert "sandbox_member@test.local" in user_emails

        # Verify password is "sandbox123" for all users
        for user in data["users"]:
            assert user["password"] == "sandbox123"

        # Verify entities created
        assert len(data["entities"]) == 5

        # Verify chats created (expanded sandbox has 7 chats)
        assert len(data["chats"]) == 7

        # Verify calls created (expanded sandbox has 6 calls)
        assert len(data["calls"]) == 6

    async def test_create_sandbox_creates_department(self, client: AsyncClient, superadmin_user: User, organization: Organization, db_session):
        """Test that sandbox creates QA Sandbox department."""
        # Add superadmin to organization
        org_member = OrgMember(
            org_id=organization.id,
            user_id=superadmin_user.id,
            role=OrgRole.owner
        )
        db_session.add(org_member)
        await db_session.commit()

        token = create_access_token(data={"sub": str(superadmin_user.id), "token_version": superadmin_user.token_version})

        response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify department exists in database
        from sqlalchemy import select
        result = await db_session.execute(
            select(Department).where(Department.id == data["department_id"])
        )
        dept = result.scalar_one_or_none()

        assert dept is not None
        assert dept.name == "Sandbox Test Department"
        assert dept.description == "Automated test environment for QA and development"
        assert dept.color == "#FF6B35"
        assert dept.is_active is True

    async def test_create_sandbox_creates_users_with_roles(self, client: AsyncClient, superadmin_user: User, organization: Organization, db_session):
        """Test that sandbox creates users with correct roles."""
        # Add superadmin to organization
        org_member = OrgMember(
            org_id=organization.id,
            user_id=superadmin_user.id,
            role=OrgRole.owner
        )
        db_session.add(org_member)
        await db_session.commit()

        token = create_access_token(data={"sub": str(superadmin_user.id), "token_version": superadmin_user.token_version})

        response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify role assignments
        users = data["users"]

        # Find each user and verify roles
        owner_user = next(u for u in users if u["email"] == "sandbox_owner@test.local")
        assert owner_user["org_role"] == "owner"
        assert owner_user["dept_role"] == "lead"

        admin_user = next(u for u in users if u["email"] == "sandbox_admin@test.local")
        assert admin_user["org_role"] == "admin"
        assert admin_user["dept_role"] == "lead"

        subadmin_user = next(u for u in users if u["email"] == "sandbox_subadmin@test.local")
        assert subadmin_user["org_role"] == "member"
        assert subadmin_user["dept_role"] == "sub_admin"

        member_user = next(u for u in users if u["email"] == "sandbox_member@test.local")
        assert member_user["org_role"] == "member"
        assert member_user["dept_role"] == "member"

    async def test_create_sandbox_entities_tagged(self, client: AsyncClient, superadmin_user: User, organization: Organization, db_session):
        """Test that all sandbox entities are tagged with 'sandbox'."""
        # Add superadmin to organization
        org_member = OrgMember(
            org_id=organization.id,
            user_id=superadmin_user.id,
            role=OrgRole.owner
        )
        db_session.add(org_member)
        await db_session.commit()

        token = create_access_token(data={"sub": str(superadmin_user.id), "token_version": superadmin_user.token_version})

        response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify entities have sandbox tag
        from sqlalchemy import select
        for entity_data in data["entities"]:
            result = await db_session.execute(
                select(Entity).where(Entity.id == entity_data["id"])
            )
            entity = result.scalar_one_or_none()
            assert entity is not None
            assert "sandbox" in entity.tags

    async def test_create_sandbox_creates_shared_access(self, client: AsyncClient, superadmin_user: User, organization: Organization, db_session):
        """Test that sandbox creates sharing relationships."""
        # Add superadmin to organization
        org_member = OrgMember(
            org_id=organization.id,
            user_id=superadmin_user.id,
            role=OrgRole.owner
        )
        db_session.add(org_member)
        await db_session.commit()

        token = create_access_token(data={"sub": str(superadmin_user.id), "token_version": superadmin_user.token_version})

        response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200

        # Verify shared access records exist
        from sqlalchemy import select
        result = await db_session.execute(select(SharedAccess))
        shared_access = result.scalars().all()

        assert len(shared_access) >= 3  # At least 3 sharing relationships created

    async def test_create_sandbox_already_exists(self, client: AsyncClient, superadmin_user: User, organization: Organization, db_session):
        """Test that creating sandbox twice fails."""
        # Add superadmin to organization
        org_member = OrgMember(
            org_id=organization.id,
            user_id=superadmin_user.id,
            role=OrgRole.owner
        )
        db_session.add(org_member)
        await db_session.commit()

        token = create_access_token(data={"sub": str(superadmin_user.id), "token_version": superadmin_user.token_version})

        # Create sandbox first time
        response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

        # Try to create again
        response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"].lower()

    async def test_create_sandbox_non_superadmin_denied(self, client: AsyncClient, admin_user: User):
        """Test that non-SUPERADMIN cannot create sandbox."""
        token = create_access_token(data={"sub": str(admin_user.id), "token_version": admin_user.token_version})

        response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403

    async def test_create_sandbox_unauthenticated(self, client: AsyncClient):
        """Test that unauthenticated requests are rejected."""
        response = await client.post("/api/admin/sandbox/create")
        assert response.status_code in [401, 403]


# ============================================================================
# TEST CLASS: Sandbox Deletion
# ============================================================================

@pytest.mark.asyncio
class TestSandboxDelete:
    """
    Test DELETE /api/admin/sandbox endpoint.

    Removes all sandbox test data including users, entities, chats, calls.
    """

    async def test_delete_sandbox_success(self, client: AsyncClient, superadmin_user: User, organization: Organization, db_session):
        """Test successful sandbox deletion."""
        # Add superadmin to organization
        org_member = OrgMember(
            org_id=organization.id,
            user_id=superadmin_user.id,
            role=OrgRole.owner
        )
        db_session.add(org_member)
        await db_session.commit()

        token = create_access_token(data={"sub": str(superadmin_user.id), "token_version": superadmin_user.token_version})

        # Create sandbox first
        create_response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert create_response.status_code == 200

        # Delete sandbox
        delete_response = await client.delete(
            "/api/admin/sandbox",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert delete_response.status_code == 200
        data = delete_response.json()

        assert "message" in data
        assert "deleted" in data
        assert data["deleted"]["users"] == 4
        assert data["deleted"]["entities"] == 5
        assert data["deleted"]["chats"] == 7  # expanded sandbox
        assert data["deleted"]["calls"] == 6  # expanded sandbox

    async def test_delete_sandbox_removes_users(self, client: AsyncClient, superadmin_user: User, organization: Organization, db_session):
        """Test that sandbox deletion removes all sandbox users."""
        # Add superadmin to organization
        org_member = OrgMember(
            org_id=organization.id,
            user_id=superadmin_user.id,
            role=OrgRole.owner
        )
        db_session.add(org_member)
        await db_session.commit()

        token = create_access_token(data={"sub": str(superadmin_user.id), "token_version": superadmin_user.token_version})

        # Create sandbox
        await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"}
        )

        # Delete sandbox
        await client.delete(
            "/api/admin/sandbox",
            headers={"Authorization": f"Bearer {token}"}
        )

        # Verify users are deleted
        from sqlalchemy import select
        sandbox_emails = [
            "sandbox_owner@test.local",
            "sandbox_admin@test.local",
            "sandbox_subadmin@test.local",
            "sandbox_member@test.local"
        ]

        result = await db_session.execute(
            select(User).where(User.email.in_(sandbox_emails))
        )
        users = result.scalars().all()

        assert len(users) == 0

    async def test_delete_sandbox_removes_department(self, client: AsyncClient, superadmin_user: User, organization: Organization, db_session):
        """Test that sandbox deletion removes QA Sandbox department."""
        # Add superadmin to organization
        org_member = OrgMember(
            org_id=organization.id,
            user_id=superadmin_user.id,
            role=OrgRole.owner
        )
        db_session.add(org_member)
        await db_session.commit()

        token = create_access_token(data={"sub": str(superadmin_user.id), "token_version": superadmin_user.token_version})

        # Create sandbox
        create_response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"}
        )
        dept_id = create_response.json()["department_id"]

        # Delete sandbox
        await client.delete(
            "/api/admin/sandbox",
            headers={"Authorization": f"Bearer {token}"}
        )

        # Verify department is deleted
        from sqlalchemy import select
        result = await db_session.execute(
            select(Department).where(Department.id == dept_id)
        )
        dept = result.scalar_one_or_none()

        assert dept is None

    async def test_delete_sandbox_not_exists(self, client: AsyncClient, superadmin_user: User, organization: Organization, db_session):
        """Test deleting non-existent sandbox returns error."""
        # Add superadmin to organization
        org_member = OrgMember(
            org_id=organization.id,
            user_id=superadmin_user.id,
            role=OrgRole.owner
        )
        db_session.add(org_member)
        await db_session.commit()

        token = create_access_token(data={"sub": str(superadmin_user.id), "token_version": superadmin_user.token_version})

        # Try to delete without creating
        response = await client.delete(
            "/api/admin/sandbox",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 404
        detail = response.json()["detail"].lower()
        assert "sandbox" in detail or "not found" in detail or "does not exist" in detail

    async def test_delete_sandbox_non_superadmin_denied(self, client: AsyncClient, admin_user: User):
        """Test that non-SUPERADMIN cannot delete sandbox."""
        token = create_access_token(data={"sub": str(admin_user.id), "token_version": admin_user.token_version})

        response = await client.delete(
            "/api/admin/sandbox",
            headers={"Authorization": f"Bearer {token}"}
        )

        # Non-superadmin should be denied (403) or get not found (404) if no sandbox
        assert response.status_code in [403, 404]


# ============================================================================
# TEST CLASS: Sandbox Status
# ============================================================================

@pytest.mark.asyncio
class TestSandboxStatus:
    """
    Test GET /api/admin/sandbox/status endpoint.

    Checks if sandbox exists and returns information about it.
    """

    async def test_sandbox_status_exists(self, client: AsyncClient, superadmin_user: User, organization: Organization, db_session):
        """Test sandbox status when sandbox exists."""
        # Add superadmin to organization
        org_member = OrgMember(
            org_id=organization.id,
            user_id=superadmin_user.id,
            role=OrgRole.owner
        )
        db_session.add(org_member)
        await db_session.commit()

        token = create_access_token(data={"sub": str(superadmin_user.id), "token_version": superadmin_user.token_version})

        # Create sandbox
        await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"}
        )

        # Check status
        response = await client.get(
            "/api/admin/sandbox/status",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["exists"] is True
        assert data["department_id"] is not None
        assert len(data["users"]) == 4
        assert data["stats"]["contacts"] == 5
        assert data["stats"]["chats"] == 7  # expanded sandbox
        assert data["stats"]["calls"] == 6  # expanded sandbox

    async def test_sandbox_status_not_exists(self, client: AsyncClient, superadmin_user: User, organization: Organization, db_session):
        """Test sandbox status when sandbox doesn't exist."""
        # Add superadmin to organization
        org_member = OrgMember(
            org_id=organization.id,
            user_id=superadmin_user.id,
            role=OrgRole.owner
        )
        db_session.add(org_member)
        await db_session.commit()

        token = create_access_token(data={"sub": str(superadmin_user.id), "token_version": superadmin_user.token_version})

        # Check status without creating
        response = await client.get(
            "/api/admin/sandbox/status",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["exists"] is False
        assert data["department_id"] is None
        assert len(data["users"]) == 0
        assert data["stats"]["contacts"] == 0
        assert data["stats"]["chats"] == 0
        assert data["stats"]["calls"] == 0

    async def test_sandbox_status_includes_user_info(self, client: AsyncClient, superadmin_user: User, organization: Organization, db_session):
        """Test sandbox status includes detailed user information."""
        # Add superadmin to organization
        org_member = OrgMember(
            org_id=organization.id,
            user_id=superadmin_user.id,
            role=OrgRole.owner
        )
        db_session.add(org_member)
        await db_session.commit()

        token = create_access_token(data={"sub": str(superadmin_user.id), "token_version": superadmin_user.token_version})

        # Create sandbox
        await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"}
        )

        # Check status
        response = await client.get(
            "/api/admin/sandbox/status",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify user info structure
        users = data["users"]
        assert len(users) == 4

        for user in users:
            assert "id" in user
            assert "email" in user
            assert "name" in user
            assert "role" in user
            assert "is_active" in user
            # role_label is optional
            assert "role_label" in user or "role" in user

    async def test_sandbox_status_non_superadmin_denied(self, client: AsyncClient, admin_user: User):
        """Test that non-SUPERADMIN cannot check sandbox status."""
        token = create_access_token(data={"sub": str(admin_user.id), "token_version": admin_user.token_version})

        response = await client.get(
            "/api/admin/sandbox/status",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403


# ============================================================================
# TEST CLASS: Sandbox Switch User
# ============================================================================

@pytest.mark.asyncio
class TestSandboxSwitch:
    """
    Test POST /api/admin/sandbox/switch/{user_email} endpoint.

    Quick switch to sandbox user for testing different roles.
    """

    async def test_switch_to_sandbox_user_success(self, client: AsyncClient, superadmin_user: User, organization: Organization, db_session):
        """Test successfully switching to a sandbox user."""
        # Add superadmin to organization
        org_member = OrgMember(
            org_id=organization.id,
            user_id=superadmin_user.id,
            role=OrgRole.owner
        )
        db_session.add(org_member)
        await db_session.commit()

        token = create_access_token(data={"sub": str(superadmin_user.id), "token_version": superadmin_user.token_version})

        # Create sandbox
        await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"}
        )

        # Switch to sandbox owner
        response = await client.post(
            "/api/admin/sandbox/switch/sandbox_owner@test.local",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Token is now set via cookie, response contains user info
        assert "user" in data
        assert "message" in data
        assert data["user"]["email"] == "sandbox_owner@test.local"

    async def test_switch_to_each_sandbox_user(self, client: AsyncClient, superadmin_user: User, organization: Organization, db_session):
        """Test switching to each sandbox user."""
        # Add superadmin to organization
        org_member = OrgMember(
            org_id=organization.id,
            user_id=superadmin_user.id,
            role=OrgRole.owner
        )
        db_session.add(org_member)
        await db_session.commit()

        token = create_access_token(data={"sub": str(superadmin_user.id), "token_version": superadmin_user.token_version})

        # Create sandbox
        await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"}
        )

        # Test switching to each user
        sandbox_users = [
            "sandbox_owner@test.local",
            "sandbox_admin@test.local",
            "sandbox_subadmin@test.local",
            "sandbox_member@test.local"
        ]

        for user_email in sandbox_users:
            response = await client.post(
                f"/api/admin/sandbox/switch/{user_email}",
                headers={"Authorization": f"Bearer {token}"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["user"]["email"] == user_email

    async def test_switch_to_non_sandbox_user_denied(self, client: AsyncClient, superadmin_user: User, organization: Organization, db_session):
        """Test that switching to non-sandbox user is denied."""
        # Add superadmin to organization
        org_member = OrgMember(
            org_id=organization.id,
            user_id=superadmin_user.id,
            role=OrgRole.owner
        )
        db_session.add(org_member)
        await db_session.commit()

        token = create_access_token(data={"sub": str(superadmin_user.id), "token_version": superadmin_user.token_version})

        # Try to switch to non-sandbox user (non-existent email)
        response = await client.post(
            "/api/admin/sandbox/switch/regular@example.com",
            headers={"Authorization": f"Bearer {token}"}
        )

        # Should return 404 (user not found) or 400 (not sandbox user)
        assert response.status_code in [400, 404]
        detail = response.json()["detail"].lower()
        assert "sandbox" in detail or "not found" in detail

    async def test_switch_to_nonexistent_sandbox_user(self, client: AsyncClient, superadmin_user: User, organization: Organization, db_session):
        """Test switching to non-existent sandbox user."""
        # Add superadmin to organization
        org_member = OrgMember(
            org_id=organization.id,
            user_id=superadmin_user.id,
            role=OrgRole.owner
        )
        db_session.add(org_member)
        await db_session.commit()

        token = create_access_token(data={"sub": str(superadmin_user.id), "token_version": superadmin_user.token_version})

        # Try to switch to non-existent sandbox user
        response = await client.post(
            "/api/admin/sandbox/switch/sandbox_nonexistent@test.local",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    async def test_switch_creates_impersonation_log(self, client: AsyncClient, superadmin_user: User, organization: Organization, db_session):
        """Test that switching creates an impersonation log entry."""
        # Add superadmin to organization
        org_member = OrgMember(
            org_id=organization.id,
            user_id=superadmin_user.id,
            role=OrgRole.owner
        )
        db_session.add(org_member)
        await db_session.commit()

        token = create_access_token(data={"sub": str(superadmin_user.id), "token_version": superadmin_user.token_version})

        # Create sandbox
        await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"}
        )

        # Switch to sandbox user
        await client.post(
            "/api/admin/sandbox/switch/sandbox_owner@test.local",
            headers={"Authorization": f"Bearer {token}"}
        )

        # Verify impersonation log exists
        from sqlalchemy import select
        from api.models.database import ImpersonationLog

        result = await db_session.execute(
            select(ImpersonationLog).where(ImpersonationLog.superadmin_id == superadmin_user.id)
        )
        logs = result.scalars().all()

        assert len(logs) >= 1

    async def test_switch_non_superadmin_denied(self, client: AsyncClient, admin_user: User):
        """Test that non-SUPERADMIN cannot switch to sandbox user."""
        token = create_access_token(data={"sub": str(admin_user.id), "token_version": admin_user.token_version})

        response = await client.post(
            "/api/admin/sandbox/switch/sandbox_owner@test.local",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403


# ============================================================================
# TEST CLASS: Integration Tests
# ============================================================================

@pytest.mark.asyncio
class TestSandboxIntegration:
    """
    Integration tests for the complete sandbox lifecycle.
    """

    async def test_full_sandbox_lifecycle(self, client: AsyncClient, superadmin_user: User, organization: Organization, db_session):
        """Test complete sandbox lifecycle: create, check status, switch users, delete."""
        # Add superadmin to organization
        org_member = OrgMember(
            org_id=organization.id,
            user_id=superadmin_user.id,
            role=OrgRole.owner
        )
        db_session.add(org_member)
        await db_session.commit()

        token = create_access_token(data={"sub": str(superadmin_user.id), "token_version": superadmin_user.token_version})

        # 1. Check status (should not exist)
        status_response = await client.get(
            "/api/admin/sandbox/status",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert status_response.json()["exists"] is False

        # 2. Create sandbox
        create_response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert create_response.status_code == 200

        # 3. Check status (should exist)
        status_response = await client.get(
            "/api/admin/sandbox/status",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert status_response.json()["exists"] is True

        # 4. Switch to sandbox user
        switch_response = await client.post(
            "/api/admin/sandbox/switch/sandbox_admin@test.local",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert switch_response.status_code == 200

        # 5. Delete sandbox
        delete_response = await client.delete(
            "/api/admin/sandbox",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert delete_response.status_code == 200

        # 6. Check status (should not exist)
        status_response = await client.get(
            "/api/admin/sandbox/status",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert status_response.json()["exists"] is False

    async def test_sandbox_data_isolation(self, client: AsyncClient, superadmin_user: User, organization: Organization, department: Department, db_session):
        """Test that sandbox data doesn't interfere with existing data."""
        # Add superadmin to organization
        org_member = OrgMember(
            org_id=organization.id,
            user_id=superadmin_user.id,
            role=OrgRole.owner
        )
        db_session.add(org_member)
        await db_session.commit()

        # Create some existing data
        from sqlalchemy import select
        existing_dept_count = len((await db_session.execute(select(Department))).scalars().all())
        existing_user_count = len((await db_session.execute(select(User))).scalars().all())

        token = create_access_token(data={"sub": str(superadmin_user.id), "token_version": superadmin_user.token_version})

        # Create sandbox
        await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"}
        )

        # Verify sandbox data exists
        new_dept_count = len((await db_session.execute(select(Department))).scalars().all())
        new_user_count = len((await db_session.execute(select(User))).scalars().all())

        assert new_dept_count == existing_dept_count + 1  # QA Sandbox dept
        assert new_user_count == existing_user_count + 4  # 4 sandbox users

        # Delete sandbox
        await client.delete(
            "/api/admin/sandbox",
            headers={"Authorization": f"Bearer {token}"}
        )

        # Verify original data still exists
        final_dept_count = len((await db_session.execute(select(Department))).scalars().all())
        final_user_count = len((await db_session.execute(select(User))).scalars().all())

        assert final_dept_count == existing_dept_count
        assert final_user_count == existing_user_count
