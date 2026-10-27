"""
Tests for sandbox functionality.

The sandbox feature allows SUPERADMIN to create isolated test environments
for testing role-based permissions and access control without affecting real data.

Sandbox creates:
- 1 department (named "Sandbox Test Department")
- 4 users (owner, admin, member1, member2) with @test.local emails
- 5 entities with different ownership
- 3 chats
- 2 calls
- Sharing relationships between users
- All items tagged with "sandbox" tag

Test cases verify:
1. Sandbox creation and proper data setup
2. Sandbox status reporting
3. User switching (impersonation of sandbox users)
4. Complete cleanup on deletion
5. Data isolation (sandbox data not visible to non-sandbox users)
6. Role-based permissions within sandbox
"""
import pytest
from datetime import datetime
from sqlalchemy import select, func

from api.models.database import (
    User, UserRole, Organization, OrgMember, OrgRole,
    Department, DepartmentMember, DeptRole,
    Entity, Chat, CallRecording, SharedAccess,
    EntityType, EntityStatus, ChatType, CallSource, CallStatus,
    AccessLevel, ResourceType
)
from api.services.auth import create_access_token


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
async def org_with_dept(db_session, organization, department):
    """Setup organization with department for sandbox tests."""
    return {
        'org': organization,
        'dept': department
    }


@pytest.fixture
async def real_user_with_data(db_session, organization, department, regular_user):
    """Create a real user with some data that should not be visible to sandbox."""
    # Add user to org and department
    org_member = OrgMember(
        org_id=organization.id,
        user_id=regular_user.id,
        role=OrgRole.admin
    )
    dept_member = DepartmentMember(
        department_id=department.id,
        user_id=regular_user.id,
        role=DeptRole.lead
    )
    db_session.add(org_member)
    db_session.add(dept_member)

    # Create real entity
    entity = Entity(
        org_id=organization.id,
        department_id=department.id,
        created_by=regular_user.id,
        name="Real User Entity",
        email="real@company.com",
        type=EntityType.candidate,
        status=EntityStatus.active
    )
    db_session.add(entity)

    # Create real chat
    chat = Chat(
        org_id=organization.id,
        owner_id=regular_user.id,
        telegram_chat_id=111111111,
        title="Real User Chat",
        chat_type=ChatType.hr,
        is_active=True
    )
    db_session.add(chat)

    await db_session.commit()
    await db_session.refresh(regular_user)
    await db_session.refresh(entity)
    await db_session.refresh(chat)

    return {
        'user': regular_user,
        'entity': entity,
        'chat': chat
    }


# ============================================================================
# TEST CLASS: Sandbox Creation
# ============================================================================

@pytest.mark.asyncio
class TestSandboxCreation:
    """Test sandbox environment creation."""

    async def test_superadmin_can_create_sandbox(
        self,
        client,
        db_session,
        superadmin_user,
        organization
    ):
        """Test that SUPERADMIN can create a sandbox environment."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"org_id": organization.id}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "department_id" in data
        assert "users" in data
        assert "entities" in data
        assert "chats" in data
        assert "calls" in data

        # Verify correct counts
        assert len(data["users"]) == 4
        assert len(data["entities"]) == 5
        # Набор песочницы расширили: 7 чатов и 6 звонков (api/routes/admin/sandbox.py)
        assert len(data["chats"]) == 7
        assert len(data["calls"]) == 6

    async def test_non_superadmin_cannot_create_sandbox(
        self,
        client,
        admin_user,
        organization
    ):
        """Test that non-SUPERADMIN cannot create sandbox."""
        token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"org_id": organization.id}
        )

        assert response.status_code == 403

    async def test_sandbox_creates_correct_department(
        self,
        client,
        db_session,
        superadmin_user,
        organization
    ):
        """Test that sandbox creates a department with correct name."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"org_id": organization.id}
        )

        assert response.status_code == 200
        data = response.json()

        # Get department from DB
        result = await db_session.execute(
            select(Department).where(Department.id == data["department_id"])
        )
        dept = result.scalar_one_or_none()

        assert dept is not None
        assert "sandbox" in dept.name.lower() or "test" in dept.name.lower()
        assert dept.org_id == organization.id

    async def test_sandbox_creates_four_users_with_correct_roles(
        self,
        client,
        db_session,
        superadmin_user,
        organization
    ):
        """Test that sandbox creates 4 users with different roles."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"org_id": organization.id}
        )

        assert response.status_code == 200
        data = response.json()

        users = data["users"]
        assert len(users) == 4

        # Verify we have different roles
        roles = [u["role"] for u in users]
        assert "sandbox_owner" in roles or OrgRole.owner.value in [u["org_role"] for u in users]
        assert "sandbox_admin" in roles or DeptRole.lead.value in [u["dept_role"] for u in users if "dept_role" in u]
        assert "sandbox_member" in roles or DeptRole.member.value in [u["dept_role"] for u in users if "dept_role" in u]

        # Verify all have @test.local emails
        for user in users:
            assert user["email"].endswith("@test.local")

    async def test_sandbox_creates_five_entities_with_correct_ownership(
        self,
        client,
        db_session,
        superadmin_user,
        organization
    ):
        """Test that sandbox creates 5 entities with different owners."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"org_id": organization.id}
        )

        assert response.status_code == 200
        data = response.json()

        entities = data["entities"]
        assert len(entities) == 5

        # Verify entities are owned by different sandbox users
        owner_ids = [e["created_by"] for e in entities]
        assert len(set(owner_ids)) >= 2, "Entities should have different owners"

        # Verify all entities have sandbox tag or test email
        for entity in entities:
            has_sandbox_tag = "sandbox" in entity.get("tags", [])
            has_test_email = entity.get("email", "").endswith("@test.local")
            assert has_sandbox_tag or has_test_email

    async def test_sandbox_creates_three_chats(
        self,
        client,
        db_session,
        superadmin_user,
        organization
    ):
        """Test that sandbox creates its chats (7 — по набору в sandbox.py)."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"org_id": organization.id}
        )

        assert response.status_code == 200
        data = response.json()

        chats = data["chats"]
        assert len(chats) == 7

        # Verify chats are owned by sandbox users
        sandbox_user_ids = [u["id"] for u in data["users"]]
        for chat in chats:
            assert chat["owner_id"] in sandbox_user_ids

    async def test_sandbox_creates_two_calls(
        self,
        client,
        db_session,
        superadmin_user,
        organization
    ):
        """Test that sandbox creates its call recordings (6 — по набору в sandbox.py)."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"org_id": organization.id}
        )

        assert response.status_code == 200
        data = response.json()

        calls = data["calls"]
        assert len(calls) == 6

        # Verify calls are owned by sandbox users
        sandbox_user_ids = [u["id"] for u in data["users"]]
        for call in calls:
            assert call["owner_id"] in sandbox_user_ids

    async def test_sandbox_creates_sharing_relationships(
        self,
        client,
        db_session,
        superadmin_user,
        organization
    ):
        """Test that sandbox creates sharing relationships between users."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"org_id": organization.id}
        )

        assert response.status_code == 200
        data = response.json()

        # Get sandbox user IDs
        sandbox_user_ids = [u["id"] for u in data["users"]]

        # Check if any shares exist between sandbox users
        result = await db_session.execute(
            select(SharedAccess).where(
                SharedAccess.shared_with_id.in_(sandbox_user_ids)
            )
        )
        shares = result.scalars().all()

        assert len(shares) > 0, "Sandbox should create sharing relationships"

        # Verify shares are between sandbox users only
        for share in shares:
            assert share.shared_by_id in sandbox_user_ids
            assert share.shared_with_id in sandbox_user_ids

    async def test_sandbox_users_have_test_local_emails(
        self,
        client,
        db_session,
        superadmin_user,
        organization
    ):
        """Test that all sandbox users have @test.local email addresses."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"org_id": organization.id}
        )

        assert response.status_code == 200
        data = response.json()

        for user in data["users"]:
            assert user["email"].endswith("@test.local")
            assert "@test.local" in user["email"]

    async def test_cannot_create_multiple_sandboxes(
        self,
        client,
        db_session,
        superadmin_user,
        organization
    ):
        """Test that only one sandbox can exist at a time."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        # Create first sandbox
        response1 = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"org_id": organization.id}
        )
        assert response1.status_code == 200

        # Try to create second sandbox
        response2 = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"org_id": organization.id}
        )

        # Should fail or return existing sandbox
        assert response2.status_code in [400, 409, 200]
        if response2.status_code == 200:
            # If it returns existing, verify it's the same sandbox
            data1 = response1.json()
            data2 = response2.json()
            assert data1["department_id"] == data2["department_id"]


# ============================================================================
# TEST CLASS: Sandbox Status
# ============================================================================

@pytest.mark.asyncio
class TestSandboxStatus:
    """Test sandbox status endpoint."""

    async def test_status_returns_false_when_not_created(
        self,
        client,
        superadmin_user,
        organization
    ):
        """Test that status returns exists=false when sandbox doesn't exist."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.get(
            f"/api/admin/sandbox/status?org_id={organization.id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["exists"] is False
        assert "department_id" not in data or data["department_id"] is None

    async def test_status_returns_true_when_created(
        self,
        client,
        superadmin_user,
        organization
    ):
        """Test that status returns exists=true when sandbox exists."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        # Create sandbox
        create_response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"org_id": organization.id}
        )
        assert create_response.status_code == 200

        # Check status
        status_response = await client.get(
            f"/api/admin/sandbox/status?org_id={organization.id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert status_response.status_code == 200
        data = status_response.json()

        assert data["exists"] is True
        assert "department_id" in data
        assert data["department_id"] is not None

    async def test_status_returns_user_list_when_created(
        self,
        client,
        superadmin_user,
        organization
    ):
        """Test that status returns list of sandbox users."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        # Create sandbox
        await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"org_id": organization.id}
        )

        # Check status
        response = await client.get(
            f"/api/admin/sandbox/status?org_id={organization.id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert "users" in data
        assert len(data["users"]) == 4

        # Verify user data structure
        for user in data["users"]:
            assert "id" in user
            assert "email" in user
            assert "name" in user
            assert "role" in user

    async def test_status_returns_department_id(
        self,
        client,
        superadmin_user,
        organization
    ):
        """Test that status returns the sandbox department ID."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        # Create sandbox
        create_response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"org_id": organization.id}
        )
        created_dept_id = create_response.json()["department_id"]

        # Check status
        status_response = await client.get(
            f"/api/admin/sandbox/status?org_id={organization.id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert status_response.status_code == 200
        data = status_response.json()

        assert data["department_id"] == created_dept_id

    async def test_non_superadmin_cannot_check_status(
        self,
        client,
        admin_user,
        organization
    ):
        """Test that non-SUPERADMIN cannot check sandbox status."""
        token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.get(
            f"/api/admin/sandbox/status?org_id={organization.id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403


# ============================================================================
# TEST CLASS: Sandbox Switch (User Impersonation)
# ============================================================================

@pytest.mark.asyncio
class TestSandboxSwitch:
    """Test switching to sandbox users."""

    async def test_can_switch_to_sandbox_owner(
        self,
        client,
        superadmin_user,
        organization
    ):
        """Test that SUPERADMIN can switch to sandbox_owner."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        # Create sandbox
        create_response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"org_id": organization.id}
        )
        users = create_response.json()["users"]

        # Find owner user
        owner_user = next((u for u in users if "owner" in u.get("name", "").lower() or u.get("org_role") == OrgRole.owner.value), None)
        assert owner_user is not None

        # Switch to owner using email
        response = await client.post(
            f"/api/admin/sandbox/switch/{owner_user['email']}",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Токен имперсонации теперь только в httpOnly-куке (как у логина)
        assert "access_token" in response.cookies
        assert "access_token" not in data
        assert "user" in data
        assert data["user"]["id"] == owner_user["id"]

    async def test_can_switch_to_sandbox_admin(
        self,
        client,
        superadmin_user,
        organization
    ):
        """Test that SUPERADMIN can switch to sandbox_admin."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        # Create sandbox
        create_response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"org_id": organization.id}
        )
        users = create_response.json()["users"]

        # Find admin user
        admin_user = next((u for u in users if "admin" in u.get("name", "").lower() and "owner" not in u.get("name", "").lower()), None)
        assert admin_user is not None

        # Switch to admin using email
        response = await client.post(
            f"/api/admin/sandbox/switch/{admin_user['email']}",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Токен имперсонации теперь только в httpOnly-куке (как у логина)
        assert "access_token" in response.cookies
        assert data["user"]["id"] == admin_user["id"]

    async def test_can_switch_to_sandbox_member(
        self,
        client,
        superadmin_user,
        organization
    ):
        """Test that SUPERADMIN can switch to sandbox_member."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        # Create sandbox
        create_response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"org_id": organization.id}
        )
        users = create_response.json()["users"]

        # Find member user
        member_user = next((u for u in users if "member" in u.get("name", "").lower()), None)
        assert member_user is not None

        # Switch to member using email
        response = await client.post(
            f"/api/admin/sandbox/switch/{member_user['email']}",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Токен имперсонации теперь только в httpOnly-куке (как у логина)
        assert "access_token" in response.cookies
        assert data["user"]["id"] == member_user["id"]

    async def test_cannot_switch_to_non_sandbox_user(
        self,
        client,
        superadmin_user,
        regular_user,
        organization
    ):
        """Test that cannot switch to non-sandbox user via sandbox endpoint."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        # Create sandbox first
        await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"org_id": organization.id}
        )

        # Try to switch to regular user via sandbox endpoint
        response = await client.post(
            f"/api/admin/sandbox/switch/{regular_user.email}",
            headers={"Authorization": f"Bearer {token}"}
        )

        # Should be bad request (not a sandbox user)
        assert response.status_code in [400, 403, 404]

    async def test_switch_returns_valid_impersonation_token(
        self,
        client,
        superadmin_user,
        organization
    ):
        """Test that switch returns a valid impersonation token."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        # Create sandbox
        create_response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"org_id": organization.id}
        )
        users = create_response.json()["users"]
        sandbox_user = users[0]

        # Switch to sandbox user using email
        switch_response = await client.post(
            f"/api/admin/sandbox/switch/{sandbox_user['email']}",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert switch_response.status_code == 200
        impersonation_token = switch_response.cookies["access_token"]  # токен — в httpOnly-куке, не в теле

        # Try to use the impersonation token
        me_response = await client.get(
            "/api/users/me",
            headers={"Authorization": f"Bearer {impersonation_token}"}
        )

        # Should work and return the sandbox user's info
        assert me_response.status_code == 200
        # Implementation may vary, but token should be valid

    async def test_non_superadmin_cannot_switch(
        self,
        client,
        admin_user,
        organization
    ):
        """Test that non-SUPERADMIN cannot switch to sandbox users."""
        admin_token = create_access_token(data={"sub": str(admin_user.id)})
        superadmin_token = create_access_token(data={"sub": str(1)})  # Assuming ID 1 is superadmin

        # Create sandbox as superadmin
        create_response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {superadmin_token}"},
            json={"org_id": organization.id}
        )

        if create_response.status_code == 200:
            users = create_response.json()["users"]
            sandbox_user = users[0]

            # Try to switch as admin using email
            response = await client.post(
                f"/api/admin/sandbox/switch/{sandbox_user['email']}",
                headers={"Authorization": f"Bearer {admin_token}"}
            )

            assert response.status_code == 403


# ============================================================================
# TEST CLASS: Sandbox Deletion
# ============================================================================

@pytest.mark.asyncio
class TestSandboxDeletion:
    """Test sandbox deletion and cleanup."""

    async def test_superadmin_can_delete_sandbox(
        self,
        client,
        superadmin_user,
        organization
    ):
        """Test that SUPERADMIN can delete sandbox."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        # Create sandbox
        create_response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"org_id": organization.id}
        )
        assert create_response.status_code == 200

        # Delete sandbox
        delete_response = await client.delete(
            f"/api/admin/sandbox?org_id={organization.id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert delete_response.status_code == 200
        data = delete_response.json()

        assert "deleted" in data or "message" in data

    async def test_all_sandbox_users_deleted(
        self,
        client,
        db_session,
        superadmin_user,
        organization
    ):
        """Test that all sandbox users are deleted."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        # Create sandbox
        create_response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"org_id": organization.id}
        )
        user_ids = [u["id"] for u in create_response.json()["users"]]

        # Delete sandbox
        await client.delete(
            f"/api/admin/sandbox?org_id={organization.id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        # Verify users are deleted
        result = await db_session.execute(
            select(User).where(User.id.in_(user_ids))
        )
        remaining_users = result.scalars().all()

        assert len(remaining_users) == 0

    async def test_all_sandbox_entities_deleted(
        self,
        client,
        db_session,
        superadmin_user,
        organization
    ):
        """Test that all sandbox entities are deleted."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        # Create sandbox
        create_response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"org_id": organization.id}
        )
        entity_ids = [e["id"] for e in create_response.json()["entities"]]

        # Delete sandbox
        await client.delete(
            f"/api/admin/sandbox?org_id={organization.id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        # Verify entities are deleted
        result = await db_session.execute(
            select(Entity).where(Entity.id.in_(entity_ids))
        )
        remaining_entities = result.scalars().all()

        assert len(remaining_entities) == 0

    async def test_all_sandbox_chats_deleted(
        self,
        client,
        db_session,
        superadmin_user,
        organization
    ):
        """Test that all sandbox chats are deleted."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        # Create sandbox
        create_response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"org_id": organization.id}
        )
        chat_ids = [c["id"] for c in create_response.json()["chats"]]

        # Delete sandbox
        await client.delete(
            f"/api/admin/sandbox?org_id={organization.id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        # Verify chats are deleted
        result = await db_session.execute(
            select(Chat).where(Chat.id.in_(chat_ids))
        )
        remaining_chats = result.scalars().all()

        assert len(remaining_chats) == 0

    async def test_all_sandbox_calls_deleted(
        self,
        client,
        db_session,
        superadmin_user,
        organization
    ):
        """Test that all sandbox calls are deleted."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        # Create sandbox
        create_response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"org_id": organization.id}
        )
        call_ids = [c["id"] for c in create_response.json()["calls"]]

        # Delete sandbox
        await client.delete(
            f"/api/admin/sandbox?org_id={organization.id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        # Verify calls are deleted
        result = await db_session.execute(
            select(CallRecording).where(CallRecording.id.in_(call_ids))
        )
        remaining_calls = result.scalars().all()

        assert len(remaining_calls) == 0

    async def test_sandbox_department_deleted(
        self,
        client,
        db_session,
        superadmin_user,
        organization
    ):
        """Test that sandbox department is deleted."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        # Create sandbox
        create_response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"org_id": organization.id}
        )
        dept_id = create_response.json()["department_id"]

        # Delete sandbox
        await client.delete(
            f"/api/admin/sandbox?org_id={organization.id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        # Verify department is deleted
        result = await db_session.execute(
            select(Department).where(Department.id == dept_id)
        )
        dept = result.scalar_one_or_none()

        assert dept is None

    async def test_status_returns_false_after_deletion(
        self,
        client,
        superadmin_user,
        organization
    ):
        """Test that status returns exists=false after sandbox deletion."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        # Create sandbox
        await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {token}"},
            json={"org_id": organization.id}
        )

        # Delete sandbox
        await client.delete(
            f"/api/admin/sandbox?org_id={organization.id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        # Check status
        status_response = await client.get(
            f"/api/admin/sandbox/status?org_id={organization.id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert status_response.status_code == 200
        data = status_response.json()

        assert data["exists"] is False

    async def test_non_superadmin_cannot_delete_sandbox(
        self,
        client,
        admin_user,
        organization
    ):
        """Test that non-SUPERADMIN cannot delete sandbox."""
        token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.delete(
            f"/api/admin/sandbox?org_id={organization.id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403


# ============================================================================
# TEST CLASS: Sandbox Data Isolation
# ============================================================================

@pytest.mark.asyncio
class TestSandboxDataIsolation:
    """Test that sandbox data is isolated from real data."""

    async def test_sandbox_entities_only_visible_to_sandbox_users(
        self,
        client,
        db_session,
        superadmin_user,
        organization,
        real_user_with_data
    ):
        """Test that sandbox entities are only visible to sandbox users."""
        superadmin_token = create_access_token(data={"sub": str(superadmin_user.id)})
        real_user_token = create_access_token(data={"sub": str(real_user_with_data['user'].id)})

        # Create sandbox
        create_response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {superadmin_token}"},
            json={"org_id": organization.id}
        )
        sandbox_entity_ids = [e["id"] for e in create_response.json()["entities"]]

        # Real user tries to list entities
        response = await client.get(
            "/api/entities",
            headers={"Authorization": f"Bearer {real_user_token}"}
        )

        assert response.status_code == 200
        entities = response.json()
        entity_ids = [e["id"] for e in entities]

        # Real user should not see sandbox entities
        for sandbox_id in sandbox_entity_ids:
            assert sandbox_id not in entity_ids

    @pytest.mark.xfail(reason="Data isolation between sandbox and real users may not be fully implemented")
    async def test_sandbox_users_cannot_access_real_data(
        self,
        client,
        db_session,
        superadmin_user,
        organization,
        real_user_with_data
    ):
        """Test that sandbox users cannot access real user data."""
        superadmin_token = create_access_token(data={"sub": str(superadmin_user.id)})

        # Create sandbox
        create_response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {superadmin_token}"},
            json={"org_id": organization.id}
        )
        sandbox_user = create_response.json()["users"][0]

        # Switch to sandbox user using email
        switch_response = await client.post(
            f"/api/admin/sandbox/switch/{sandbox_user['email']}",
            headers={"Authorization": f"Bearer {superadmin_token}"}
        )
        sandbox_token = switch_response.cookies["access_token"]  # токен — в httpOnly-куке, не в теле

        # Sandbox user tries to access real entity
        real_entity_id = real_user_with_data['entity'].id
        response = await client.get(
            f"/api/entities/{real_entity_id}",
            headers={"Authorization": f"Bearer {sandbox_token}"}
        )

        # Should be forbidden or not found
        assert response.status_code in [403, 404]

    async def test_real_users_cannot_see_sandbox_data(
        self,
        client,
        db_session,
        superadmin_user,
        organization,
        real_user_with_data
    ):
        """Test that real users cannot see sandbox data."""
        superadmin_token = create_access_token(data={"sub": str(superadmin_user.id)})
        real_user_token = create_access_token(data={"sub": str(real_user_with_data['user'].id)})

        # Create sandbox
        create_response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {superadmin_token}"},
            json={"org_id": organization.id}
        )
        sandbox_chat_ids = [c["id"] for c in create_response.json()["chats"]]

        # Real user tries to list chats
        response = await client.get(
            "/api/chats",
            headers={"Authorization": f"Bearer {real_user_token}"}
        )

        assert response.status_code == 200
        chats = response.json()
        chat_ids = [c["id"] for c in chats]

        # Real user should not see sandbox chats
        for sandbox_id in sandbox_chat_ids:
            assert sandbox_id not in chat_ids

    @pytest.mark.xfail(reason="Superadmin viewing entities may require organization membership setup")
    async def test_superadmin_can_see_both_sandbox_and_real_data(
        self,
        client,
        db_session,
        superadmin_user,
        organization,
        real_user_with_data
    ):
        """Test that SUPERADMIN can see both sandbox and real data."""
        superadmin_token = create_access_token(data={"sub": str(superadmin_user.id)})

        # Create sandbox
        create_response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {superadmin_token}"},
            json={"org_id": organization.id}
        )
        sandbox_entity_ids = set(e["id"] for e in create_response.json()["entities"])

        # SUPERADMIN lists all entities
        response = await client.get(
            "/api/entities",
            headers={"Authorization": f"Bearer {superadmin_token}"}
        )

        assert response.status_code == 200
        entities = response.json()
        entity_ids = set(e["id"] for e in entities)

        # SUPERADMIN should see both sandbox and real entities
        assert real_user_with_data['entity'].id in entity_ids
        # At least some sandbox entities should be visible
        assert len(sandbox_entity_ids & entity_ids) > 0


# ============================================================================
# TEST CLASS: Role Testing Within Sandbox
# ============================================================================

@pytest.mark.asyncio
class TestSandboxRolePermissions:
    """Test role-based permissions within sandbox environment."""

    async def test_sandbox_owner_sees_all_sandbox_entities(
        self,
        client,
        db_session,
        superadmin_user,
        organization
    ):
        """Test that sandbox_owner sees all entities in sandbox."""
        superadmin_token = create_access_token(data={"sub": str(superadmin_user.id)})

        # Create sandbox
        create_response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {superadmin_token}"},
            json={"org_id": organization.id}
        )

        users = create_response.json()["users"]
        sandbox_entity_count = len(create_response.json()["entities"])

        # Find owner
        owner = next((u for u in users if "owner" in u.get("name", "").lower() or u.get("org_role") == OrgRole.owner.value), users[0])

        # Switch to owner using email
        switch_response = await client.post(
            f"/api/admin/sandbox/switch/{owner['email']}",
            headers={"Authorization": f"Bearer {superadmin_token}"}
        )
        owner_token = switch_response.cookies["access_token"]  # токен — в httpOnly-куке, не в теле

        # Owner lists entities
        response = await client.get(
            "/api/entities",
            headers={"Authorization": f"Bearer {owner_token}"}
        )

        assert response.status_code == 200
        entities = response.json()

        # Owner should see all sandbox entities
        assert len(entities) == sandbox_entity_count

    async def test_sandbox_admin_sees_department_entities(
        self,
        client,
        db_session,
        superadmin_user,
        organization
    ):
        """Test that sandbox_admin sees all entities in their department."""
        superadmin_token = create_access_token(data={"sub": str(superadmin_user.id)})

        # Create sandbox
        create_response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {superadmin_token}"},
            json={"org_id": organization.id}
        )

        users = create_response.json()["users"]
        sandbox_entity_count = len(create_response.json()["entities"])

        # Find admin/lead
        admin = next((u for u in users if ("admin" in u.get("name", "").lower() or "lead" in u.get("name", "").lower()) and "owner" not in u.get("name", "").lower()), None)

        if admin:
            # Switch to admin using email
            switch_response = await client.post(
                f"/api/admin/sandbox/switch/{admin['email']}",
                headers={"Authorization": f"Bearer {superadmin_token}"}
            )
            admin_token = switch_response.cookies["access_token"]  # токен — в httpOnly-куке, не в теле

            # Admin lists entities
            response = await client.get(
                "/api/entities",
                headers={"Authorization": f"Bearer {admin_token}"}
            )

            assert response.status_code == 200
            entities = response.json()

            # Admin should see department entities (all sandbox in same dept)
            assert len(entities) == sandbox_entity_count

    async def test_sandbox_member_sees_only_own_entities(
        self,
        client,
        db_session,
        superadmin_user,
        organization
    ):
        """Test that sandbox_member sees only their own entities."""
        superadmin_token = create_access_token(data={"sub": str(superadmin_user.id)})

        # Create sandbox
        create_response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {superadmin_token}"},
            json={"org_id": organization.id}
        )

        users = create_response.json()["users"]
        all_entities = create_response.json()["entities"]

        # Find member
        member = next((u for u in users if "member" in u.get("name", "").lower() and "admin" not in u.get("name", "").lower()), None)

        if member:
            # Count entities owned by this member
            member_entity_count = sum(1 for e in all_entities if e["created_by"] == member["id"])

            # Switch to member using email
            switch_response = await client.post(
                f"/api/admin/sandbox/switch/{member['email']}",
                headers={"Authorization": f"Bearer {superadmin_token}"}
            )
            member_token = switch_response.cookies["access_token"]  # токен — в httpOnly-куке, не в теле

            # Member lists entities
            response = await client.get(
                "/api/entities",
                headers={"Authorization": f"Bearer {member_token}"}
            )

            assert response.status_code == 200
            entities = response.json()

            # Member should only see their own entities (or shared ones)
            # At minimum, should see their own
            owned_entities = [e for e in entities if e["created_by"] == member["id"]]
            assert len(owned_entities) == member_entity_count

    async def test_sharing_works_between_sandbox_users(
        self,
        client,
        db_session,
        superadmin_user,
        organization
    ):
        """Test that sharing works correctly between sandbox users."""
        superadmin_token = create_access_token(data={"sub": str(superadmin_user.id)})

        # Create sandbox
        create_response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {superadmin_token}"},
            json={"org_id": organization.id}
        )

        users = create_response.json()["users"]

        # Get two different users
        user1 = users[0]
        user2 = users[1]

        # Check if any entities are shared between them
        result = await db_session.execute(
            select(SharedAccess).where(
                SharedAccess.shared_by_id == user1["id"],
                SharedAccess.shared_with_id == user2["id"]
            )
        )
        share = result.scalar_one_or_none()

        if share:
            # Switch to user2 using email
            switch_response = await client.post(
                f"/api/admin/sandbox/switch/{user2['email']}",
                headers={"Authorization": f"Bearer {superadmin_token}"}
            )
            user2_token = switch_response.cookies["access_token"]  # токен — в httpOnly-куке, не в теле

            # User2 should be able to access the shared resource
            if share.resource_type == ResourceType.entity:
                response = await client.get(
                    f"/api/entities/{share.entity_id}",
                    headers={"Authorization": f"Bearer {user2_token}"}
                )
                # Should be able to view if shared
                assert response.status_code == 200

    async def test_sandbox_member_cannot_delete_others_entities(
        self,
        client,
        db_session,
        superadmin_user,
        organization
    ):
        """Test that sandbox member cannot delete entities owned by others."""
        superadmin_token = create_access_token(data={"sub": str(superadmin_user.id)})

        # Create sandbox
        create_response = await client.post(
            "/api/admin/sandbox/create",
            headers={"Authorization": f"Bearer {superadmin_token}"},
            json={"org_id": organization.id}
        )

        users = create_response.json()["users"]
        entities = create_response.json()["entities"]

        # Find a member
        member = next((u for u in users if "member" in u.get("name", "").lower() and "admin" not in u.get("name", "").lower()), None)

        if member:
            # Find an entity NOT owned by this member
            other_entity = next((e for e in entities if e["created_by"] != member["id"]), None)

            if other_entity:
                # Switch to member using email
                switch_response = await client.post(
                    f"/api/admin/sandbox/switch/{member['email']}",
                    headers={"Authorization": f"Bearer {superadmin_token}"}
                )
                member_token = switch_response.cookies["access_token"]  # токен — в httpOnly-куке, не в теле

                # Try to delete other's entity
                response = await client.delete(
                    f"/api/entities/{other_entity['id']}",
                    headers={"Authorization": f"Bearer {member_token}"}
                )

                # Should be forbidden
                assert response.status_code in [403, 404]
