"""
Comprehensive unit tests for user CRUD operations.
Tests for /home/user/HR-bot-/backend/api/routes/users.py

This test suite covers:
- GET /me endpoint (current user info)
- GET /users (list users with role-based filtering)
- POST /users (create user)
- PATCH /users/{id} (update user)
- DELETE /users/{id} (delete user with FK cleanup)
- Role-based access control
- Edge cases and error handling

Target: 80%+ coverage
"""
import pytest
from datetime import datetime
from sqlalchemy import select

from api.models.database import (
    User, UserRole, DepartmentMember, DeptRole, Chat,
    SharedAccess, AnalysisHistory, AIConversation, EntityAIConversation,
    EntityAnalysis, CallRecording, Entity, EntityType, EntityStatus,
    OrgMember, OrgRole, Invitation, CriteriaPreset, ReportSubscription,
    ResourceType, AccessLevel
)
from api.services.auth import create_access_token


class TestGetCurrentUserMe:
    """Tests for GET /api/users/me endpoint - get current user information."""

    @pytest.mark.asyncio
    async def test_get_current_user_info_success(
        self, client, admin_user, admin_token, get_auth_headers
    ):
        """Test getting current user info returns correct data."""
        response = await client.get(
            "/api/users/me",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == admin_user.id
        assert data["email"] == admin_user.email
        assert data["name"] == admin_user.name
        assert data["role"] == admin_user.role.value
        assert data["is_active"] == admin_user.is_active
        assert "created_at" in data
        assert "chats_count" in data

    @pytest.mark.asyncio
    async def test_get_me_includes_chat_count(
        self, client, admin_user, admin_token, organization, get_auth_headers, db_session
    ):
        """Test that /me endpoint includes accurate chat count."""
        # Create 3 chats for the user
        for i in range(3):
            chat = Chat(
                org_id=organization.id,
                owner_id=admin_user.id,
                telegram_chat_id=1000000 + i,
                title=f"Test Chat {i}",
                is_active=True,
                created_at=datetime.utcnow()
            )
            db_session.add(chat)
        await db_session.commit()

        response = await client.get(
            "/api/users/me",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["chats_count"] == 3

    @pytest.mark.asyncio
    async def test_get_me_with_zero_chats(
        self, client, admin_user, admin_token, get_auth_headers
    ):
        """Test /me endpoint when user has no chats."""
        response = await client.get(
            "/api/users/me",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["chats_count"] == 0

    @pytest.mark.asyncio
    async def test_get_me_with_telegram_info(
        self, client, get_auth_headers, db_session
    ):
        """Test /me endpoint returns Telegram information."""
        user = User(
            email="telegram@test.com",
            password_hash="hashed",
            name="Telegram User",
            role=UserRole.admin,
            telegram_id=123456789,
            telegram_username="testuser",
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        token = create_access_token(data={"sub": str(user.id)})

        response = await client.get(
            "/api/users/me",
            headers=get_auth_headers(token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["telegram_id"] == 123456789
        assert data["telegram_username"] == "testuser"

    @pytest.mark.asyncio
    async def test_get_me_without_telegram_info(
        self, client, admin_user, admin_token, get_auth_headers
    ):
        """Test /me endpoint when user has no Telegram info."""
        response = await client.get(
            "/api/users/me",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["telegram_id"] is None
        assert data["telegram_username"] is None

    @pytest.mark.asyncio
    async def test_get_me_requires_authentication(self, client):
        """Test that /me endpoint requires authentication."""
        response = await client.get("/api/users/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_me_with_invalid_token(self, client, get_auth_headers):
        """Test /me endpoint with invalid token."""
        response = await client.get(
            "/api/users/me",
            headers=get_auth_headers("invalid_token_here")
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_me_for_superadmin(
        self, client, superadmin_user, superadmin_token, get_auth_headers
    ):
        """Test /me endpoint for SUPERADMIN role."""
        response = await client.get(
            "/api/users/me",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "superadmin"

    @pytest.mark.asyncio
    async def test_get_me_for_sub_admin(
        self, client, get_auth_headers, db_session
    ):
        """Test /me endpoint for SUB_ADMIN role."""
        user = User(
            email="subadmin@test.com",
            password_hash="hashed",
            name="Sub Admin",
            role=UserRole.sub_admin,
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        token = create_access_token(data={"sub": str(user.id)})

        response = await client.get(
            "/api/users/me",
            headers=get_auth_headers(token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "sub_admin"

    @pytest.mark.asyncio
    async def test_get_me_for_inactive_user(
        self, client, get_auth_headers, db_session
    ):
        """Test /me endpoint for inactive user."""
        user = User(
            email="inactive@test.com",
            password_hash="hashed",
            name="Inactive User",
            role=UserRole.admin,
            is_active=False
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        token = create_access_token(data={"sub": str(user.id)})

        response = await client.get(
            "/api/users/me",
            headers=get_auth_headers(token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False


class TestListUsers:
    """Tests for GET /api/users endpoint - list users with role-based filtering."""

    @pytest.mark.asyncio
    async def test_superadmin_sees_all_users(
        self, client, superadmin_user, superadmin_token, admin_user,
        regular_user, get_auth_headers
    ):
        """Test SUPERADMIN can see all users in the system."""
        response = await client.get(
            "/api/users",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 3  # At least superadmin, admin, regular

        emails = [u["email"] for u in data]
        assert superadmin_user.email in emails
        assert admin_user.email in emails
        assert regular_user.email in emails

    @pytest.mark.asyncio
    async def test_admin_sees_same_department_users(
        self, client, admin_user, admin_token, regular_user, department,
        get_auth_headers, db_session
    ):
        """Test ADMIN sees all users in their department."""
        # Add both users to same department
        for user in [admin_user, regular_user]:
            dept_member = DepartmentMember(
                department_id=department.id,
                user_id=user.id,
                role=DeptRole.lead if user == admin_user else DeptRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(dept_member)
        await db_session.commit()

        response = await client.get(
            "/api/users",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        emails = [u["email"] for u in data]
        assert admin_user.email in emails
        assert regular_user.email in emails

    @pytest.mark.asyncio
    async def test_admin_sees_admins_from_other_departments(
        self, client, admin_user, admin_token, department, second_department,
        get_auth_headers, db_session
    ):
        """Test ADMIN sees ADMIN/SUB_ADMIN from other departments."""
        # Add admin_user to department 1
        dept_member1 = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_member1)

        # Create another admin in department 2
        other_admin = User(
            email="otheradmin@test.com",
            password_hash="hashed",
            name="Other Admin",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(other_admin)
        await db_session.commit()
        await db_session.refresh(other_admin)

        dept_member2 = DepartmentMember(
            department_id=second_department.id,
            user_id=other_admin.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_member2)
        await db_session.commit()

        response = await client.get(
            "/api/users",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        emails = [u["email"] for u in data]
        assert "otheradmin@test.com" in emails

    @pytest.mark.asyncio
    async def test_admin_does_not_see_members_from_other_departments(
        self, client, admin_user, admin_token, department, second_department,
        get_auth_headers, db_session
    ):
        """Test ADMIN does not see regular members from other departments."""
        # Add admin_user to department 1
        dept_member1 = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_member1)

        # Create regular member in department 2
        other_member = User(
            email="othermember@test.com",
            password_hash="hashed",
            name="Other Member",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(other_member)
        await db_session.commit()
        await db_session.refresh(other_member)

        dept_member2 = DepartmentMember(
            department_id=second_department.id,
            user_id=other_member.id,
            role=DeptRole.member,  # Regular member, not admin
            created_at=datetime.utcnow()
        )
        db_session.add(dept_member2)
        await db_session.commit()

        response = await client.get(
            "/api/users",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        emails = [u["email"] for u in data]
        # Should NOT see the regular member from other department
        assert "othermember@test.com" not in emails

    @pytest.mark.asyncio
    async def test_admin_without_department_returns_empty_list(
        self, client, admin_user, admin_token, get_auth_headers
    ):
        """Test ADMIN without department membership returns empty list."""
        response = await client.get(
            "/api/users",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data == []

    @pytest.mark.asyncio
    async def test_sub_admin_has_same_visibility_as_admin(
        self, client, department, get_auth_headers, db_session
    ):
        """Test SUB_ADMIN has same user visibility as ADMIN."""
        sub_admin = User(
            email="subadmin@test.com",
            password_hash="hashed",
            name="Sub Admin",
            role=UserRole.sub_admin,
            is_active=True
        )
        db_session.add(sub_admin)
        await db_session.commit()
        await db_session.refresh(sub_admin)

        dept_member = DepartmentMember(
            department_id=department.id,
            user_id=sub_admin.id,
            role=DeptRole.sub_admin,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_member)
        await db_session.commit()

        token = create_access_token(data={"sub": str(sub_admin.id)})

        response = await client.get(
            "/api/users",
            headers=get_auth_headers(token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        emails = [u["email"] for u in data]
        assert "subadmin@test.com" in emails

    @pytest.mark.asyncio
    async def test_list_users_includes_chat_counts(
        self, client, superadmin_user, superadmin_token, admin_user,
        organization, get_auth_headers, db_session
    ):
        """Test user list includes accurate chat counts for each user."""
        # Create 2 chats for admin_user
        for i in range(2):
            chat = Chat(
                org_id=organization.id,
                owner_id=admin_user.id,
                telegram_chat_id=2000000 + i,
                title=f"Admin Chat {i}",
                is_active=True,
                created_at=datetime.utcnow()
            )
            db_session.add(chat)
        await db_session.commit()

        response = await client.get(
            "/api/users",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Find admin_user in response
        admin_data = next((u for u in data if u["email"] == admin_user.email), None)
        assert admin_data is not None
        assert admin_data["chats_count"] == 2

    @pytest.mark.asyncio
    async def test_list_users_response_structure(
        self, client, superadmin_token, get_auth_headers
    ):
        """Test that user list response has correct structure."""
        response = await client.get(
            "/api/users",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        if len(data) > 0:
            user = data[0]
            assert "id" in user
            assert "email" in user
            assert "name" in user
            assert "role" in user
            assert "is_active" in user
            assert "created_at" in user
            assert "chats_count" in user
            assert isinstance(user["chats_count"], int)

    @pytest.mark.asyncio
    async def test_list_users_requires_authentication(self, client):
        """Test listing users requires authentication."""
        response = await client.get("/api/users")
        assert response.status_code == 401


class TestCreateUser:
    """Tests for POST /api/users endpoint - create new user."""

    @pytest.mark.asyncio
    async def test_create_admin_user_success(
        self, client, superadmin_token, department, get_auth_headers
    ):
        """Test SUPERADMIN can create ADMIN user with department."""
        response = await client.post(
            "/api/users",
            json={
                "email": "newadmin@test.com",
                "password": "ValidPass123!",
                "name": "New Admin",
                "role": "admin",
                "department_id": department.id
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newadmin@test.com"
        assert data["name"] == "New Admin"
        assert data["role"] == "admin"
        assert data["is_active"] is True
        assert data["chats_count"] == 0

    @pytest.mark.asyncio
    async def test_create_superadmin_user(
        self, client, superadmin_token, get_auth_headers
    ):
        """Test creating SUPERADMIN user (no department required)."""
        response = await client.post(
            "/api/users",
            json={
                "email": "newsuperadmin@test.com",
                "password": "SuperSecure123!",
                "name": "New Superadmin",
                "role": "superadmin"
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["role"] == "superadmin"

    @pytest.mark.asyncio
    async def test_create_sub_admin_user(
        self, client, superadmin_token, department, get_auth_headers
    ):
        """Test creating SUB_ADMIN user with department."""
        response = await client.post(
            "/api/users",
            json={
                "email": "newsubadmin@test.com",
                "password": "SubAdminPass123!",
                "name": "New Sub Admin",
                "role": "sub_admin",
                "department_id": department.id
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["role"] == "sub_admin"

    @pytest.mark.asyncio
    async def test_create_user_with_telegram_credentials(
        self, client, superadmin_token, department, get_auth_headers
    ):
        """Test creating user with Telegram ID and username."""
        response = await client.post(
            "/api/users",
            json={
                "email": "telegramuser@test.com",
                "password": "TelegramPass123!",
                "name": "Telegram User",
                "role": "admin",
                "department_id": department.id,
                "telegram_id": 987654321,
                "telegram_username": "telegramuser"
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["telegram_id"] == 987654321
        assert data["telegram_username"] == "telegramuser"

    @pytest.mark.asyncio
    async def test_create_user_duplicate_email_fails(
        self, client, superadmin_token, admin_user, department, get_auth_headers
    ):
        """Test creating user with duplicate email fails."""
        response = await client.post(
            "/api/users",
            json={
                "email": admin_user.email,
                "password": "Password123!",
                "name": "Duplicate",
                "role": "admin",
                "department_id": department.id
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 400
        assert "Email exists" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_user_duplicate_telegram_id_fails(
        self, client, superadmin_token, department, get_auth_headers, db_session
    ):
        """Test creating user with duplicate Telegram ID fails."""
        # Create user with telegram_id
        existing = User(
            email="existing@test.com",
            password_hash="hashed",
            name="Existing",
            role=UserRole.admin,
            telegram_id=111111,
            is_active=True
        )
        db_session.add(existing)
        await db_session.commit()

        response = await client.post(
            "/api/users",
            json={
                "email": "new@test.com",
                "password": "Password123!",
                "name": "New User",
                "role": "admin",
                "department_id": department.id,
                "telegram_id": 111111
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 400
        assert "Telegram ID exists" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_user_weak_password_fails(
        self, client, superadmin_token, department, get_auth_headers
    ):
        """Test creating user with weak password fails validation."""
        response = await client.post(
            "/api/users",
            json={
                "email": "weakpass@test.com",
                "password": "weak",
                "name": "Weak Password",
                "role": "admin",
                "department_id": department.id
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code in [400, 422]  # 422 for Pydantic validation

    @pytest.mark.asyncio
    async def test_create_admin_without_department_fails(
        self, client, superadmin_token, get_auth_headers
    ):
        """Test creating ADMIN without department fails."""
        response = await client.post(
            "/api/users",
            json={
                "email": "nodept@test.com",
                "password": "Password123!",
                "name": "No Department",
                "role": "admin"
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 400
        assert "must be assigned to a department" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_sub_admin_without_department_fails(
        self, client, superadmin_token, get_auth_headers
    ):
        """Test creating SUB_ADMIN without department fails."""
        response = await client.post(
            "/api/users",
            json={
                "email": "nodept_sub@test.com",
                "password": "Password123!",
                "name": "No Department Sub",
                "role": "sub_admin"
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 400
        assert "must be assigned to a department" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_user_nonexistent_department_fails(
        self, client, superadmin_token, get_auth_headers
    ):
        """Test creating user with non-existent department fails."""
        response = await client.post(
            "/api/users",
            json={
                "email": "baddept@test.com",
                "password": "Password123!",
                "name": "Bad Department",
                "role": "admin",
                "department_id": 99999
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 404
        assert "Department not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_user_creates_department_membership(
        self, client, superadmin_token, department, get_auth_headers, db_session
    ):
        """Test creating user also creates department membership."""
        response = await client.post(
            "/api/users",
            json={
                "email": "depttest@test.com",
                "password": "Password123!",
                "name": "Dept Test",
                "role": "admin",
                "department_id": department.id
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 201
        user_id = response.json()["id"]

        # Verify department membership
        result = await db_session.execute(
            select(DepartmentMember).where(DepartmentMember.user_id == user_id)
        )
        dept_member = result.scalar_one_or_none()
        assert dept_member is not None
        assert dept_member.department_id == department.id
        assert dept_member.role == DeptRole.lead

    @pytest.mark.asyncio
    async def test_create_user_admin_gets_lead_dept_role(
        self, client, superadmin_token, department, get_auth_headers, db_session
    ):
        """Test ADMIN user gets 'lead' department role."""
        response = await client.post(
            "/api/users",
            json={
                "email": "adminlead@test.com",
                "password": "Password123!",
                "name": "Admin Lead",
                "role": "admin",
                "department_id": department.id
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 201
        user_id = response.json()["id"]

        result = await db_session.execute(
            select(DepartmentMember).where(DepartmentMember.user_id == user_id)
        )
        dept_member = result.scalar_one_or_none()
        assert dept_member.role == DeptRole.lead

    @pytest.mark.asyncio
    async def test_create_user_sub_admin_gets_sub_admin_dept_role(
        self, client, superadmin_token, department, get_auth_headers, db_session
    ):
        """Test SUB_ADMIN user gets 'sub_admin' department role."""
        response = await client.post(
            "/api/users",
            json={
                "email": "subadminrole@test.com",
                "password": "Password123!",
                "name": "Sub Admin Role",
                "role": "sub_admin",
                "department_id": department.id
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 201
        user_id = response.json()["id"]

        result = await db_session.execute(
            select(DepartmentMember).where(DepartmentMember.user_id == user_id)
        )
        dept_member = result.scalar_one_or_none()
        assert dept_member.role == DeptRole.sub_admin

    @pytest.mark.asyncio
    async def test_create_user_requires_superadmin(
        self, client, admin_token, department, get_auth_headers
    ):
        """Test only SUPERADMIN can create users."""
        response = await client.post(
            "/api/users",
            json={
                "email": "unauthorized@test.com",
                "password": "Password123!",
                "name": "Unauthorized",
                "role": "admin",
                "department_id": department.id
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_user_requires_authentication(
        self, client, department
    ):
        """Test creating user requires authentication."""
        response = await client.post(
            "/api/users",
            json={
                "email": "noauth@test.com",
                "password": "Password123!",
                "name": "No Auth",
                "role": "admin",
                "department_id": department.id
            }
        )

        assert response.status_code == 401


class TestUpdateUser:
    """Tests for PATCH /api/users/{id} endpoint - update user."""

    @pytest.mark.asyncio
    async def test_update_user_name_and_email(
        self, client, superadmin_token, admin_user, get_auth_headers
    ):
        """Test updating user name and email."""
        response = await client.patch(
            f"/api/users/{admin_user.id}",
            json={
                "name": "Updated Name",
                "email": "updated@test.com"
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["email"] == "updated@test.com"

    @pytest.mark.asyncio
    async def test_update_user_role_to_sub_admin(
        self, client, superadmin_token, admin_user, department,
        get_auth_headers, db_session
    ):
        """Test updating user role from ADMIN to SUB_ADMIN."""
        # Give admin_user a department
        dept_member = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_member)
        await db_session.commit()

        response = await client.patch(
            f"/api/users/{admin_user.id}",
            json={"role": "sub_admin"},
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "sub_admin"

    @pytest.mark.asyncio
    async def test_update_user_role_to_superadmin(
        self, client, superadmin_token, admin_user, get_auth_headers
    ):
        """Test updating user role to SUPERADMIN."""
        response = await client.patch(
            f"/api/users/{admin_user.id}",
            json={"role": "superadmin"},
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "superadmin"

    @pytest.mark.asyncio
    async def test_update_user_telegram_info(
        self, client, superadmin_token, admin_user, get_auth_headers
    ):
        """Test updating user Telegram information."""
        response = await client.patch(
            f"/api/users/{admin_user.id}",
            json={
                "telegram_id": 555555,
                "telegram_username": "newtelegramuser"
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["telegram_id"] == 555555
        assert data["telegram_username"] == "newtelegramuser"

    @pytest.mark.asyncio
    async def test_update_user_active_status(
        self, client, superadmin_token, admin_user, get_auth_headers
    ):
        """Test deactivating a user."""
        response = await client.patch(
            f"/api/users/{admin_user.id}",
            json={"is_active": False},
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False

    @pytest.mark.asyncio
    async def test_reactivate_inactive_user(
        self, client, superadmin_token, get_auth_headers, db_session
    ):
        """Test reactivating an inactive user."""
        # Create inactive user
        user = User(
            email="inactive@test.com",
            password_hash="hashed",
            name="Inactive User",
            role=UserRole.admin,
            is_active=False
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # Reactivate the user
        response = await client.patch(
            f"/api/users/{user.id}",
            json={"is_active": True},
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_deactivate_then_reactivate_user(
        self, client, superadmin_token, admin_user, get_auth_headers, db_session
    ):
        """Test deactivating and then reactivating the same user."""
        # Deactivate
        response = await client.patch(
            f"/api/users/{admin_user.id}",
            json={"is_active": False},
            headers=get_auth_headers(superadmin_token)
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is False

        # Reactivate
        response = await client.patch(
            f"/api/users/{admin_user.id}",
            json={"is_active": True},
            headers=get_auth_headers(superadmin_token)
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is True

        # Verify in database
        await db_session.refresh(admin_user)
        assert admin_user.is_active is True

    @pytest.mark.asyncio
    async def test_update_user_department(
        self, client, superadmin_token, admin_user, department,
        second_department, get_auth_headers, db_session
    ):
        """Test updating user's department."""
        # Give admin_user initial department
        dept_member = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_member)
        await db_session.commit()

        response = await client.patch(
            f"/api/users/{admin_user.id}",
            json={"department_id": second_department.id},
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200

        # Verify department was updated
        result = await db_session.execute(
            select(DepartmentMember).where(DepartmentMember.user_id == admin_user.id)
        )
        dept_member = result.scalar_one_or_none()
        assert dept_member.department_id == second_department.id

    @pytest.mark.asyncio
    async def test_update_creates_department_membership_if_missing(
        self, client, superadmin_token, department, get_auth_headers, db_session
    ):
        """Test updating user with department creates membership if it doesn't exist."""
        # Create user without department
        user = User(
            email="nodept@test.com",
            password_hash="hashed",
            name="No Dept",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        response = await client.patch(
            f"/api/users/{user.id}",
            json={"department_id": department.id},
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200

        # Verify department membership was created
        result = await db_session.execute(
            select(DepartmentMember).where(DepartmentMember.user_id == user.id)
        )
        dept_member = result.scalar_one_or_none()
        assert dept_member is not None
        assert dept_member.department_id == department.id

    @pytest.mark.asyncio
    async def test_update_department_updates_dept_role_based_on_user_role(
        self, client, superadmin_token, department, get_auth_headers, db_session
    ):
        """Test updating department also updates department role."""
        # Create SUB_ADMIN user
        user = User(
            email="subadmin@test.com",
            password_hash="hashed",
            name="Sub Admin",
            role=UserRole.sub_admin,
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        response = await client.patch(
            f"/api/users/{user.id}",
            json={"department_id": department.id},
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200

        result = await db_session.execute(
            select(DepartmentMember).where(DepartmentMember.user_id == user.id)
        )
        dept_member = result.scalar_one_or_none()
        assert dept_member.role == DeptRole.sub_admin

    @pytest.mark.asyncio
    async def test_update_to_admin_role_without_department_fails(
        self, client, superadmin_token, get_auth_headers, db_session
    ):
        """Test updating to ADMIN role without department fails."""
        # Create SUPERADMIN user (no department required)
        user = User(
            email="super@test.com",
            password_hash="hashed",
            name="Super",
            role=UserRole.superadmin,
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        response = await client.patch(
            f"/api/users/{user.id}",
            json={"role": "admin"},
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 400
        assert "must be assigned to a department" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_nonexistent_user_fails(
        self, client, superadmin_token, get_auth_headers
    ):
        """Test updating non-existent user returns 404."""
        response = await client.patch(
            "/api/users/99999",
            json={"name": "Does Not Exist"},
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 404
        assert "User not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_with_nonexistent_department_fails(
        self, client, superadmin_token, admin_user, get_auth_headers
    ):
        """Test updating user with non-existent department fails."""
        response = await client.patch(
            f"/api/users/{admin_user.id}",
            json={"department_id": 99999},
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 404
        assert "Department not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_user_partial_update(
        self, client, superadmin_token, admin_user, get_auth_headers
    ):
        """Test partial update only changes specified fields."""
        original_email = admin_user.email

        response = await client.patch(
            f"/api/users/{admin_user.id}",
            json={"name": "Only Name Changed"},
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Only Name Changed"
        assert data["email"] == original_email

    @pytest.mark.asyncio
    async def test_update_user_requires_superadmin(
        self, client, admin_token, regular_user, get_auth_headers
    ):
        """Test only SUPERADMIN can update users."""
        response = await client.patch(
            f"/api/users/{regular_user.id}",
            json={"name": "Unauthorized"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_update_user_requires_authentication(
        self, client, admin_user
    ):
        """Test updating user requires authentication."""
        response = await client.patch(
            f"/api/users/{admin_user.id}",
            json={"name": "No Auth"}
        )

        assert response.status_code == 401


class TestDeleteUser:
    """Tests for DELETE /api/users/{id} endpoint - delete user with FK cleanup."""

    @pytest.mark.asyncio
    async def test_delete_user_success(
        self, client, superadmin_token, admin_user, get_auth_headers, db_session
    ):
        """Test SUPERADMIN can delete user."""
        user_id = admin_user.id

        response = await client.delete(
            f"/api/users/{user_id}",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 204

        # Verify user was deleted
        result = await db_session.execute(
            select(User).where(User.id == user_id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_user_cannot_delete_self(
        self, client, superadmin_user, superadmin_token, get_auth_headers
    ):
        """Test user cannot delete themselves."""
        response = await client.delete(
            f"/api/users/{superadmin_user.id}",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 400
        assert "Cannot delete yourself" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_nonexistent_user_fails(
        self, client, superadmin_token, get_auth_headers
    ):
        """Test deleting non-existent user returns 404."""
        response = await client.delete(
            "/api/users/99999",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 404
        assert "User not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_user_removes_department_membership(
        self, client, superadmin_token, department, get_auth_headers, db_session
    ):
        """Test deleting user removes their department memberships."""
        user = User(
            email="deptuser@test.com",
            password_hash="hashed",
            name="Dept User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        dept_member = DepartmentMember(
            department_id=department.id,
            user_id=user.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_member)
        await db_session.commit()

        response = await client.delete(
            f"/api/users/{user.id}",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 204

        # Verify department membership was deleted
        result = await db_session.execute(
            select(DepartmentMember).where(DepartmentMember.user_id == user.id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_user_nullifies_chat_ownership(
        self, client, superadmin_token, organization, get_auth_headers, db_session
    ):
        """Test deleting user nullifies chat owner_id."""
        user = User(
            email="chatowner@test.com",
            password_hash="hashed",
            name="Chat Owner",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        chat = Chat(
            org_id=organization.id,
            owner_id=user.id,
            telegram_chat_id=9999999,
            title="User Chat",
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(chat)
        await db_session.commit()
        chat_id = chat.id

        response = await client.delete(
            f"/api/users/{user.id}",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 204

        # Verify chat exists but owner_id is null
        db_session.expire_all()
        result = await db_session.execute(
            select(Chat).where(Chat.id == chat_id)
        )
        chat = result.scalar_one_or_none()
        assert chat is not None
        assert chat.owner_id is None

    @pytest.mark.asyncio
    async def test_delete_user_removes_shared_access_records(
        self, client, superadmin_token, organization, department,
        get_auth_headers, db_session
    ):
        """Test deleting user removes SharedAccess records."""
        user = User(
            email="shareuser@test.com",
            password_hash="hashed",
            name="Share User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # Create entity to share
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=user.id,
            name="Test Entity",
            type=EntityType.candidate,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(entity)
        await db_session.commit()

        # Create another user to share with
        other_user = User(
            email="other@test.com",
            password_hash="hashed",
            name="Other",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)

        # Create share
        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=user.id,
            shared_with_id=other_user.id,
            access_level=AccessLevel.view,
            created_at=datetime.utcnow()
        )
        db_session.add(share)
        await db_session.commit()

        response = await client.delete(
            f"/api/users/{user.id}",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 204

        # Verify SharedAccess was deleted
        result = await db_session.execute(
            select(SharedAccess).where(SharedAccess.shared_by_id == user.id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_user_nullifies_call_recording_ownership(
        self, client, superadmin_token, organization, get_auth_headers, db_session
    ):
        """Test deleting user nullifies CallRecording owner_id."""
        user = User(
            email="callowner@test.com",
            password_hash="hashed",
            name="Call Owner",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        from api.models.database import CallStatus, CallSource
        call = CallRecording(
            org_id=organization.id,
            owner_id=user.id,
            title="Test Call",
            source_type=CallSource.upload,
            status=CallStatus.done,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()
        call_id = call.id

        response = await client.delete(
            f"/api/users/{user.id}",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 204

        # Verify call exists but owner_id is null
        db_session.expire_all()
        result = await db_session.execute(
            select(CallRecording).where(CallRecording.id == call_id)
        )
        call = result.scalar_one_or_none()
        assert call is not None
        assert call.owner_id is None

    @pytest.mark.asyncio
    async def test_delete_user_nullifies_entity_created_by(
        self, client, superadmin_token, organization, department,
        get_auth_headers, db_session
    ):
        """Test deleting user nullifies Entity created_by."""
        user = User(
            email="entitycreator@test.com",
            password_hash="hashed",
            name="Entity Creator",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=user.id,
            name="Test Entity",
            type=EntityType.candidate,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(entity)
        await db_session.commit()
        entity_id = entity.id

        response = await client.delete(
            f"/api/users/{user.id}",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 204

        # Verify entity exists but created_by is null
        db_session.expire_all()
        result = await db_session.execute(
            select(Entity).where(Entity.id == entity_id)
        )
        entity = result.scalar_one_or_none()
        assert entity is not None
        assert entity.created_by is None

    @pytest.mark.asyncio
    async def test_delete_user_removes_org_membership(
        self, client, superadmin_token, organization, get_auth_headers, db_session
    ):
        """Test deleting user removes organization memberships."""
        user = User(
            email="orgmember@test.com",
            password_hash="hashed",
            name="Org Member",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        org_member = OrgMember(
            org_id=organization.id,
            user_id=user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(org_member)
        await db_session.commit()

        response = await client.delete(
            f"/api/users/{user.id}",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 204

        # Verify org membership was deleted
        result = await db_session.execute(
            select(OrgMember).where(OrgMember.user_id == user.id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_user_with_multiple_relationships(
        self, client, superadmin_token, organization, department,
        get_auth_headers, db_session
    ):
        """Test deleting user with multiple relationships cleans up properly."""
        user = User(
            email="complex@test.com",
            password_hash="hashed",
            name="Complex User",
            role=UserRole.admin,
            telegram_id=777777,
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # Add department membership
        dept_member = DepartmentMember(
            department_id=department.id,
            user_id=user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_member)

        # Add org membership
        org_member = OrgMember(
            org_id=organization.id,
            user_id=user.id,
            role=OrgRole.admin,
            created_at=datetime.utcnow()
        )
        db_session.add(org_member)

        # Add chat
        chat = Chat(
            org_id=organization.id,
            owner_id=user.id,
            telegram_chat_id=8888888,
            title="Complex Chat",
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(chat)

        # Add entity
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=user.id,
            name="Complex Entity",
            type=EntityType.candidate,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(entity)

        await db_session.commit()
        chat_id = chat.id
        entity_id = entity.id

        response = await client.delete(
            f"/api/users/{user.id}",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 204

        # Verify user deleted
        result = await db_session.execute(
            select(User).where(User.id == user.id)
        )
        assert result.scalar_one_or_none() is None

        # Verify memberships deleted
        result = await db_session.execute(
            select(DepartmentMember).where(DepartmentMember.user_id == user.id)
        )
        assert result.scalar_one_or_none() is None

        result = await db_session.execute(
            select(OrgMember).where(OrgMember.user_id == user.id)
        )
        assert result.scalar_one_or_none() is None

        # Verify chat and entity still exist with nullified FKs
        db_session.expire_all()
        result = await db_session.execute(
            select(Chat).where(Chat.id == chat_id)
        )
        chat = result.scalar_one_or_none()
        assert chat is not None
        assert chat.owner_id is None

        result = await db_session.execute(
            select(Entity).where(Entity.id == entity_id)
        )
        entity = result.scalar_one_or_none()
        assert entity is not None
        assert entity.created_by is None

    @pytest.mark.asyncio
    async def test_delete_user_requires_superadmin(
        self, client, admin_token, regular_user, get_auth_headers
    ):
        """Test only SUPERADMIN can delete users."""
        response = await client.delete(
            f"/api/users/{regular_user.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_user_requires_authentication(
        self, client, admin_user
    ):
        """Test deleting user requires authentication."""
        response = await client.delete(f"/api/users/{admin_user.id}")
        assert response.status_code == 401


class TestUserRoleChanges:
    """Tests for user role changes and transitions."""

    @pytest.mark.asyncio
    async def test_change_admin_to_sub_admin(
        self, client, superadmin_token, department, get_auth_headers, db_session
    ):
        """Test changing user role from ADMIN to SUB_ADMIN."""
        user = User(
            email="rolechange@test.com",
            password_hash="hashed",
            name="Role Change",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # Give user department with lead role
        dept_member = DepartmentMember(
            department_id=department.id,
            user_id=user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_member)
        await db_session.commit()

        response = await client.patch(
            f"/api/users/{user.id}",
            json={"role": "sub_admin"},
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        assert response.json()["role"] == "sub_admin"

    @pytest.mark.asyncio
    async def test_change_sub_admin_to_admin(
        self, client, superadmin_token, department, get_auth_headers, db_session
    ):
        """Test changing user role from SUB_ADMIN to ADMIN."""
        user = User(
            email="subtoaadmin@test.com",
            password_hash="hashed",
            name="Sub to Admin",
            role=UserRole.sub_admin,
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        dept_member = DepartmentMember(
            department_id=department.id,
            user_id=user.id,
            role=DeptRole.sub_admin,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_member)
        await db_session.commit()

        response = await client.patch(
            f"/api/users/{user.id}",
            json={"role": "admin"},
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        assert response.json()["role"] == "admin"

    @pytest.mark.asyncio
    async def test_change_admin_to_superadmin(
        self, client, superadmin_token, get_auth_headers, db_session
    ):
        """Test promoting ADMIN to SUPERADMIN."""
        user = User(
            email="promote@test.com",
            password_hash="hashed",
            name="Promote",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        response = await client.patch(
            f"/api/users/{user.id}",
            json={"role": "superadmin"},
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        assert response.json()["role"] == "superadmin"

    @pytest.mark.asyncio
    async def test_change_superadmin_to_admin_requires_department(
        self, client, superadmin_token, department, get_auth_headers, db_session
    ):
        """Test demoting SUPERADMIN to ADMIN requires department."""
        user = User(
            email="demote@test.com",
            password_hash="hashed",
            name="Demote",
            role=UserRole.superadmin,
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # Try to demote without department - should fail
        response = await client.patch(
            f"/api/users/{user.id}",
            json={"role": "admin"},
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 400
        assert "must be assigned to a department" in response.json()["detail"]

        # Now with department - should succeed
        response = await client.patch(
            f"/api/users/{user.id}",
            json={"role": "admin", "department_id": department.id},
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        assert response.json()["role"] == "admin"


class TestUserPermissionChecks:
    """Tests for permission checks across different user roles."""

    @pytest.mark.asyncio
    async def test_superadmin_can_list_users(
        self, client, superadmin_token, get_auth_headers
    ):
        """Test SUPERADMIN has permission to list users."""
        response = await client.get(
            "/api/users",
            headers=get_auth_headers(superadmin_token)
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_can_list_users(
        self, client, admin_token, get_auth_headers
    ):
        """Test ADMIN has permission to list users."""
        response = await client.get(
            "/api/users",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_sub_admin_can_list_users(
        self, client, get_auth_headers, db_session
    ):
        """Test SUB_ADMIN has permission to list users."""
        user = User(
            email="subadmin@test.com",
            password_hash="hashed",
            name="Sub Admin",
            role=UserRole.sub_admin,
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        token = create_access_token(data={"sub": str(user.id)})

        response = await client.get(
            "/api/users",
            headers=get_auth_headers(token)
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_only_superadmin_can_create_users(
        self, client, admin_token, department, get_auth_headers
    ):
        """Test only SUPERADMIN can create users."""
        response = await client.post(
            "/api/users",
            json={
                "email": "test@test.com",
                "password": "Password123!",
                "name": "Test",
                "role": "admin",
                "department_id": department.id
            },
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_only_superadmin_can_update_users(
        self, client, admin_token, regular_user, get_auth_headers
    ):
        """Test only SUPERADMIN can update users."""
        response = await client.patch(
            f"/api/users/{regular_user.id}",
            json={"name": "Updated"},
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_only_superadmin_can_delete_users(
        self, client, admin_token, regular_user, get_auth_headers
    ):
        """Test only SUPERADMIN can delete users."""
        response = await client.delete(
            f"/api/users/{regular_user.id}",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_all_authenticated_users_can_access_me_endpoint(
        self, client, admin_token, get_auth_headers
    ):
        """Test all authenticated users can access /me endpoint."""
        response = await client.get(
            "/api/users/me",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200


class TestChangePassword:
    """Tests for POST /api/auth/change-password endpoint - change user password."""

    @pytest.mark.asyncio
    async def test_change_password_success(
        self, client, admin_user, get_auth_headers, db_session
    ):
        """Test successfully changing password."""
        from api.services.auth import hash_password, verify_password, create_access_token

        # Set a known password for the user
        admin_user.password_hash = hash_password("OldPassword123!")
        await db_session.commit()

        token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.post(
            "/api/auth/change-password",
            json={
                "current_password": "OldPassword123!",
                "new_password": "NewPassword123!"
            },
            headers=get_auth_headers(token)
        )

        assert response.status_code == 200
        assert response.json()["message"] == "Password changed"

        # Verify password was actually changed in database
        await db_session.refresh(admin_user)
        assert verify_password("NewPassword123!", admin_user.password_hash)
        assert not verify_password("OldPassword123!", admin_user.password_hash)

    @pytest.mark.asyncio
    async def test_change_password_wrong_current_password(
        self, client, admin_user, get_auth_headers, db_session
    ):
        """Test changing password with wrong current password fails."""
        from api.services.auth import hash_password, create_access_token

        admin_user.password_hash = hash_password("CorrectPassword123!")
        await db_session.commit()

        token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.post(
            "/api/auth/change-password",
            json={
                "current_password": "WrongPassword123!",
                "new_password": "NewPassword123!"
            },
            headers=get_auth_headers(token)
        )

        assert response.status_code == 400
        assert "Wrong current password" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_change_password_weak_new_password(
        self, client, admin_user, get_auth_headers, db_session
    ):
        """Test changing password with weak new password fails validation."""
        from api.services.auth import hash_password, create_access_token

        admin_user.password_hash = hash_password("OldPassword123!")
        await db_session.commit()

        token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.post(
            "/api/auth/change-password",
            json={
                "current_password": "OldPassword123!",
                "new_password": "weak"
            },
            headers=get_auth_headers(token)
        )

        assert response.status_code in [400, 422]  # 422 for Pydantic validation
        # Password policy validation should fail
        assert "detail" in response.json()

    @pytest.mark.asyncio
    async def test_change_password_invalidates_tokens(
        self, client, admin_user, get_auth_headers, db_session
    ):
        """Test changing password increments token_version to invalidate existing tokens."""
        from api.services.auth import hash_password, create_access_token

        admin_user.password_hash = hash_password("OldPassword123!")
        admin_user.token_version = 0
        await db_session.commit()

        token = create_access_token(data={"sub": str(admin_user.id), "token_version": 0})

        response = await client.post(
            "/api/auth/change-password",
            json={
                "current_password": "OldPassword123!",
                "new_password": "NewPassword123!"
            },
            headers=get_auth_headers(token)
        )

        assert response.status_code == 200

        # Verify token_version was incremented
        await db_session.refresh(admin_user)
        assert admin_user.token_version == 1

    @pytest.mark.asyncio
    async def test_change_password_requires_authentication(self, client):
        """Test changing password requires authentication."""
        response = await client.post(
            "/api/auth/change-password",
            json={
                "current_password": "OldPassword123!",
                "new_password": "NewPassword123!"
            }
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_change_password_with_invalid_token(self, client, get_auth_headers):
        """Test changing password with invalid token fails."""
        response = await client.post(
            "/api/auth/change-password",
            json={
                "current_password": "OldPassword123!",
                "new_password": "NewPassword123!"
            },
            headers=get_auth_headers("invalid_token")
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_change_password_same_as_current(
        self, client, admin_user, get_auth_headers, db_session
    ):
        """Test changing password to the same password (should work)."""
        from api.services.auth import hash_password, create_access_token

        admin_user.password_hash = hash_password("SamePassword123!")
        await db_session.commit()

        token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.post(
            "/api/auth/change-password",
            json={
                "current_password": "SamePassword123!",
                "new_password": "SamePassword123!"
            },
            headers=get_auth_headers(token)
        )

        # Should succeed - no restriction on reusing same password
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_change_password_for_superadmin(
        self, client, superadmin_user, get_auth_headers, db_session
    ):
        """Test SUPERADMIN can change their password."""
        from api.services.auth import hash_password, create_access_token

        superadmin_user.password_hash = hash_password("SuperOld123!")
        await db_session.commit()

        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.post(
            "/api/auth/change-password",
            json={
                "current_password": "SuperOld123!",
                "new_password": "SuperNew123!"
            },
            headers=get_auth_headers(token)
        )

        assert response.status_code == 200
        assert response.json()["message"] == "Password changed"

    @pytest.mark.asyncio
    async def test_change_password_for_inactive_user(
        self, client, get_auth_headers, db_session
    ):
        """Test inactive user cannot change password."""
        from api.services.auth import hash_password, create_access_token

        # Create inactive user
        user = User(
            email="inactive@test.com",
            password_hash=hash_password("InactivePass123!"),
            name="Inactive User",
            role=UserRole.admin,
            is_active=False
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        token = create_access_token(data={"sub": str(user.id)})

        response = await client.post(
            "/api/auth/change-password",
            json={
                "current_password": "InactivePass123!",
                "new_password": "NewInactivePass123!"
            },
            headers=get_auth_headers(token)
        )

        # Should fail because get_current_user checks is_active (returns 401 for invalid auth)
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_change_password_missing_fields(
        self, client, admin_token, get_auth_headers
    ):
        """Test changing password with missing fields fails."""
        # Missing new_password
        response = await client.post(
            "/api/auth/change-password",
            json={"current_password": "OldPassword123!"},
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 422

        # Missing current_password
        response = await client.post(
            "/api/auth/change-password",
            json={"new_password": "NewPassword123!"},
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_change_password_empty_passwords(
        self, client, admin_token, get_auth_headers
    ):
        """Test changing password with empty strings fails."""
        response = await client.post(
            "/api/auth/change-password",
            json={
                "current_password": "",
                "new_password": ""
            },
            headers=get_auth_headers(admin_token)
        )

        # Should fail validation
        assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_change_password_with_special_characters(
        self, client, admin_user, get_auth_headers, db_session
    ):
        """Test changing password with special characters."""
        from api.services.auth import hash_password, create_access_token, verify_password

        admin_user.password_hash = hash_password("OldPass123!")
        await db_session.commit()

        token = create_access_token(data={"sub": str(admin_user.id)})

        # Password with various special characters
        new_password = "N3wP@ss#$%^&*()!"

        response = await client.post(
            "/api/auth/change-password",
            json={
                "current_password": "OldPass123!",
                "new_password": new_password
            },
            headers=get_auth_headers(token)
        )

        assert response.status_code == 200

        # Verify the special character password works
        await db_session.refresh(admin_user)
        assert verify_password(new_password, admin_user.password_hash)
