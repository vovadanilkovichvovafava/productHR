"""
Comprehensive tests for user management API endpoints.
Tests for backend/api/routes/users.py covering all CRUD operations and role-based access control.
"""
import pytest
from datetime import datetime

from api.models.database import User, UserRole, DepartmentMember, DeptRole, Chat
from api.services.auth import create_access_token


class TestGetUsers:
    """Test GET /api/users endpoint - list users with role-based filtering."""

    @pytest.mark.asyncio
    async def test_superadmin_sees_all_users(
        self, client, superadmin_user, superadmin_token, admin_user, regular_user,
        second_user, get_auth_headers, db_session
    ):
        """Test that SUPERADMIN sees all users in the system."""
        response = await client.get(
            "/api/users",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should see all 4 users: superadmin, admin, regular, second
        assert len(data) >= 4

        # Verify response structure
        for user in data:
            assert "id" in user
            assert "email" in user
            assert "name" in user
            assert "role" in user
            assert "is_active" in user
            assert "created_at" in user
            assert "chats_count" in user

    @pytest.mark.asyncio
    async def test_admin_sees_department_users_and_other_admins(
        self, client, admin_user, admin_token, regular_user, second_user,
        department, second_department, get_auth_headers, db_session, organization
    ):
        """Test that ADMIN sees users in their department + other admins."""
        # Create admin user in department 1
        dept_member1 = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_member1)

        # Create regular user in same department
        dept_member2 = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_member2)

        # Create another admin in different department
        other_admin = User(
            email="other_admin@test.com",
            password_hash="hashed",
            name="Other Admin",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(other_admin)
        await db_session.commit()
        await db_session.refresh(other_admin)

        dept_member3 = DepartmentMember(
            department_id=second_department.id,
            user_id=other_admin.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_member3)

        # Create regular user in different department (should NOT be visible)
        member_other_dept = User(
            email="member_other@test.com",
            password_hash="hashed",
            name="Member Other Dept",
            role=UserRole.admin,  # Even as ADMIN role
            is_active=True
        )
        db_session.add(member_other_dept)
        await db_session.commit()
        await db_session.refresh(member_other_dept)

        # Put them as member (not admin) in other department
        dept_member4 = DepartmentMember(
            department_id=second_department.id,
            user_id=member_other_dept.id,
            role=DeptRole.member,  # Not lead or sub_admin
            created_at=datetime.utcnow()
        )
        db_session.add(dept_member4)
        await db_session.commit()

        response = await client.get(
            "/api/users",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        user_emails = [u["email"] for u in data]

        # Should see users from own department
        assert admin_user.email in user_emails
        assert regular_user.email in user_emails

        # Should see admin from other department
        assert "other_admin@test.com" in user_emails

    @pytest.mark.asyncio
    async def test_admin_without_department_returns_empty_list(
        self, client, admin_user, admin_token, get_auth_headers
    ):
        """Test that ADMIN without department membership returns empty list."""
        # Admin user has no department membership in this scenario
        response = await client.get(
            "/api/users",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_sub_admin_sees_department_users_and_other_admins(
        self, client, department, second_department, get_auth_headers, db_session
    ):
        """Test that SUB_ADMIN has same visibility as ADMIN."""
        # Create SUB_ADMIN user
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

        # Create member in same department
        member = User(
            email="member@test.com",
            password_hash="hashed",
            name="Member",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(member)
        await db_session.commit()
        await db_session.refresh(member)

        dept_member2 = DepartmentMember(
            department_id=department.id,
            user_id=member.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_member2)
        await db_session.commit()

        from api.services.auth import create_access_token
        sub_admin_token = create_access_token(data={"sub": str(sub_admin.id)})

        response = await client.get(
            "/api/users",
            headers=get_auth_headers(sub_admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        user_emails = [u["email"] for u in data]

        # Should see users from own department
        assert "subadmin@test.com" in user_emails
        assert "member@test.com" in user_emails

    @pytest.mark.asyncio
    async def test_get_users_includes_chat_counts(
        self, client, superadmin_user, superadmin_token, admin_user,
        organization, chat, get_auth_headers, db_session
    ):
        """Test that user list includes accurate chat counts."""
        # chat fixture creates one chat for admin_user
        # Create another chat for admin_user
        chat2 = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=999999,
            title="Second Chat",
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(chat2)
        await db_session.commit()

        response = await client.get(
            "/api/users",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Find admin user in response
        admin_data = next((u for u in data if u["email"] == admin_user.email), None)
        assert admin_data is not None
        assert admin_data["chats_count"] == 2

    @pytest.mark.asyncio
    async def test_get_users_requires_authentication(self, client):
        """Test that listing users requires authentication."""
        response = await client.get("/api/users")
        assert response.status_code == 401


class TestCreateUser:
    """Test POST /api/users endpoint - create new user."""

    @pytest.mark.asyncio
    async def test_superadmin_can_create_user(
        self, client, superadmin_token, department, get_auth_headers
    ):
        """Test that SUPERADMIN can create a new user."""
        response = await client.post(
            "/api/users",
            json={
                "email": "newuser@test.com",
                "password": "NewUser123!",
                "name": "New User",
                "role": "admin",
                "department_id": department.id
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newuser@test.com"
        assert data["name"] == "New User"
        assert data["role"] == "admin"
        assert data["is_active"] is True
        assert data["chats_count"] == 0
        assert "id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_create_superadmin_user(
        self, client, superadmin_token, get_auth_headers
    ):
        """Test creating a SUPERADMIN user (no department required)."""
        response = await client.post(
            "/api/users",
            json={
                "email": "newsuperadmin@test.com",
                "password": "SuperAdmin123!",
                "name": "New Super Admin",
                "role": "superadmin"
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newsuperadmin@test.com"
        assert data["role"] == "superadmin"

    @pytest.mark.asyncio
    async def test_create_sub_admin_user(
        self, client, superadmin_token, department, get_auth_headers
    ):
        """Test creating a SUB_ADMIN user."""
        response = await client.post(
            "/api/users",
            json={
                "email": "newsubadmin@test.com",
                "password": "SubAdmin123!",
                "name": "New Sub Admin",
                "role": "sub_admin",
                "department_id": department.id
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newsubadmin@test.com"
        assert data["role"] == "sub_admin"

    @pytest.mark.asyncio
    async def test_create_user_with_telegram_info(
        self, client, superadmin_token, department, get_auth_headers
    ):
        """Test creating user with Telegram ID and username."""
        response = await client.post(
            "/api/users",
            json={
                "email": "telegram_user@test.com",
                "password": "TelegramUser123!",
                "name": "Telegram User",
                "role": "admin",
                "department_id": department.id,
                "telegram_id": 123456789,
                "telegram_username": "testuser"
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["telegram_id"] == 123456789
        assert data["telegram_username"] == "testuser"

    @pytest.mark.asyncio
    async def test_create_user_duplicate_email_rejected(
        self, client, superadmin_token, admin_user, department, get_auth_headers
    ):
        """Test that duplicate email is rejected."""
        response = await client.post(
            "/api/users",
            json={
                "email": admin_user.email,  # Duplicate
                "password": "Password123!",
                "name": "Duplicate User",
                "role": "admin",
                "department_id": department.id
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 400
        assert "Email exists" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_user_duplicate_telegram_id_rejected(
        self, client, superadmin_token, department, get_auth_headers, db_session
    ):
        """Test that duplicate Telegram ID is rejected."""
        # Create user with telegram_id
        existing_user = User(
            email="existing@test.com",
            password_hash="hashed",
            name="Existing User",
            role=UserRole.admin,
            telegram_id=555555,
            is_active=True
        )
        db_session.add(existing_user)
        await db_session.commit()

        response = await client.post(
            "/api/users",
            json={
                "email": "new@test.com",
                "password": "Password123!",
                "name": "New User",
                "role": "admin",
                "department_id": department.id,
                "telegram_id": 555555  # Duplicate
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 400
        assert "Telegram ID exists" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_user_invalid_password_rejected(
        self, client, superadmin_token, department, get_auth_headers
    ):
        """Test that weak password is rejected."""
        response = await client.post(
            "/api/users",
            json={
                "email": "weakpass@test.com",
                "password": "123",  # Too short, no uppercase, no special chars
                "name": "Weak Password User",
                "role": "admin",
                "department_id": department.id
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code in [400, 422]  # 422 for Pydantic validation
        # Should get password policy error
        assert "detail" in response.json()

    @pytest.mark.asyncio
    async def test_create_admin_without_department_rejected(
        self, client, superadmin_token, get_auth_headers
    ):
        """Test that creating ADMIN without department is rejected."""
        response = await client.post(
            "/api/users",
            json={
                "email": "nodept@test.com",
                "password": "Password123!",
                "name": "No Department Admin",
                "role": "admin"
                # No department_id
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 400
        assert "must be assigned to a department" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_sub_admin_without_department_rejected(
        self, client, superadmin_token, get_auth_headers
    ):
        """Test that creating SUB_ADMIN without department is rejected."""
        response = await client.post(
            "/api/users",
            json={
                "email": "nodept_subadmin@test.com",
                "password": "Password123!",
                "name": "No Department Sub Admin",
                "role": "sub_admin"
                # No department_id
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 400
        assert "must be assigned to a department" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_user_with_nonexistent_department_rejected(
        self, client, superadmin_token, get_auth_headers
    ):
        """Test that creating user with non-existent department is rejected."""
        response = await client.post(
            "/api/users",
            json={
                "email": "baddept@test.com",
                "password": "Password123!",
                "name": "Bad Department User",
                "role": "admin",
                "department_id": 99999  # Non-existent
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 404
        assert "Department not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_non_superadmin_cannot_create_user(
        self, client, admin_token, department, get_auth_headers
    ):
        """Test that non-SUPERADMIN cannot create users."""
        response = await client.post(
            "/api/users",
            json={
                "email": "unauthorized@test.com",
                "password": "Password123!",
                "name": "Unauthorized User",
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
        """Test that creating user requires authentication."""
        response = await client.post(
            "/api/users",
            json={
                "email": "noauth@test.com",
                "password": "Password123!",
                "name": "No Auth User",
                "role": "admin",
                "department_id": department.id
            }
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_user_creates_department_membership(
        self, client, superadmin_token, department, get_auth_headers, db_session
    ):
        """Test that creating user with department creates proper membership."""
        response = await client.post(
            "/api/users",
            json={
                "email": "deptmember@test.com",
                "password": "Password123!",
                "name": "Dept Member",
                "role": "admin",
                "department_id": department.id
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 201
        user_id = response.json()["id"]

        # Verify department membership was created
        from sqlalchemy import select
        result = await db_session.execute(
            select(DepartmentMember).where(DepartmentMember.user_id == user_id)
        )
        dept_member = result.scalar_one_or_none()

        assert dept_member is not None
        assert dept_member.department_id == department.id
        assert dept_member.role == DeptRole.lead  # ADMIN gets lead role


class TestUpdateUser:
    """Test PATCH /api/users/{id} endpoint - update user."""

    @pytest.mark.asyncio
    async def test_superadmin_can_update_user(
        self, client, superadmin_token, admin_user, get_auth_headers
    ):
        """Test that SUPERADMIN can update any user."""
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
    async def test_update_user_role(
        self, client, superadmin_token, admin_user, department, get_auth_headers, db_session
    ):
        """Test updating user role."""
        # Give admin_user a department first
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
            json={
                "role": "sub_admin"
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "sub_admin"

    @pytest.mark.asyncio
    async def test_update_user_telegram_info(
        self, client, superadmin_token, admin_user, get_auth_headers
    ):
        """Test updating user Telegram information."""
        response = await client.patch(
            f"/api/users/{admin_user.id}",
            json={
                "telegram_id": 777777,
                "telegram_username": "newusername"
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["telegram_id"] == 777777
        assert data["telegram_username"] == "newusername"

    @pytest.mark.asyncio
    async def test_update_user_active_status(
        self, client, superadmin_token, admin_user, get_auth_headers
    ):
        """Test updating user active status."""
        response = await client.patch(
            f"/api/users/{admin_user.id}",
            json={
                "is_active": False
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False

    @pytest.mark.asyncio
    async def test_update_user_department(
        self, client, superadmin_token, admin_user, department, second_department,
        get_auth_headers, db_session
    ):
        """Test updating user department membership."""
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
            json={
                "department_id": second_department.id
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200

        # Verify department was updated
        from sqlalchemy import select
        result = await db_session.execute(
            select(DepartmentMember).where(DepartmentMember.user_id == admin_user.id)
        )
        dept_member = result.scalar_one_or_none()
        assert dept_member.department_id == second_department.id

    @pytest.mark.asyncio
    async def test_update_user_to_admin_role_without_department_rejected(
        self, client, superadmin_token, get_auth_headers, db_session
    ):
        """Test that updating to ADMIN role without department is rejected."""
        # Create user without department
        user = User(
            email="nodept@test.com",
            password_hash="hashed",
            name="No Dept User",
            role=UserRole.superadmin,  # Start as superadmin (no dept required)
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        response = await client.patch(
            f"/api/users/{user.id}",
            json={
                "role": "admin"  # Change to admin without providing department
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 400
        assert "must be assigned to a department" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_nonexistent_user_returns_404(
        self, client, superadmin_token, get_auth_headers
    ):
        """Test that updating non-existent user returns 404."""
        response = await client.patch(
            "/api/users/99999",
            json={
                "name": "Does Not Exist"
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 404
        assert "User not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_user_with_nonexistent_department_rejected(
        self, client, superadmin_token, admin_user, get_auth_headers
    ):
        """Test that updating user with non-existent department is rejected."""
        response = await client.patch(
            f"/api/users/{admin_user.id}",
            json={
                "department_id": 99999
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 404
        assert "Department not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_non_superadmin_cannot_update_user(
        self, client, admin_token, regular_user, get_auth_headers
    ):
        """Test that non-SUPERADMIN cannot update users."""
        response = await client.patch(
            f"/api/users/{regular_user.id}",
            json={
                "name": "Unauthorized Update"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_update_user_requires_authentication(
        self, client, admin_user
    ):
        """Test that updating user requires authentication."""
        response = await client.patch(
            f"/api/users/{admin_user.id}",
            json={
                "name": "No Auth Update"
            }
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_update_user_department_updates_dept_role(
        self, client, superadmin_token, admin_user, department, get_auth_headers, db_session
    ):
        """Test that updating department also updates department role based on user role."""
        # Create user without department initially
        user = User(
            email="newrole@test.com",
            password_hash="hashed",
            name="New Role User",
            role=UserRole.sub_admin,
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        response = await client.patch(
            f"/api/users/{user.id}",
            json={
                "department_id": department.id
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200

        # Verify department role matches user role
        from sqlalchemy import select
        result = await db_session.execute(
            select(DepartmentMember).where(DepartmentMember.user_id == user.id)
        )
        dept_member = result.scalar_one_or_none()
        assert dept_member.role == DeptRole.sub_admin  # SUB_ADMIN gets sub_admin dept role


class TestDeleteUser:
    """Test DELETE /api/users/{id} endpoint - delete user."""

    @pytest.mark.asyncio
    async def test_superadmin_can_delete_user(
        self, client, superadmin_token, admin_user, get_auth_headers, db_session
    ):
        """Test that SUPERADMIN can delete users."""
        user_id = admin_user.id

        response = await client.delete(
            f"/api/users/{user_id}",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 204

        # Verify user was deleted
        from sqlalchemy import select
        result = await db_session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        assert user is None

    @pytest.mark.asyncio
    async def test_cannot_delete_self(
        self, client, superadmin_user, superadmin_token, get_auth_headers
    ):
        """Test that user cannot delete themselves."""
        response = await client.delete(
            f"/api/users/{superadmin_user.id}",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 400
        assert "Cannot delete yourself" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_nonexistent_user_returns_404(
        self, client, superadmin_token, get_auth_headers
    ):
        """Test that deleting non-existent user returns 404."""
        response = await client.delete(
            "/api/users/99999",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 404
        assert "User not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_user_cascades_department_membership(
        self, client, superadmin_token, department, get_auth_headers, db_session
    ):
        """Test that deleting user also deletes department memberships."""
        # Create user with department
        user = User(
            email="cascade@test.com",
            password_hash="hashed",
            name="Cascade User",
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
        from sqlalchemy import select
        result = await db_session.execute(
            select(DepartmentMember).where(DepartmentMember.user_id == user.id)
        )
        dept_member = result.scalar_one_or_none()
        assert dept_member is None

    @pytest.mark.asyncio
    async def test_delete_user_nullifies_chat_ownership(
        self, client, superadmin_token, organization, get_auth_headers, db_session
    ):
        """Test that deleting user nullifies their chat ownership."""
        # Create user with chat
        user = User(
            email="chats@test.com",
            password_hash="hashed",
            name="Chats User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        chat = Chat(
            org_id=organization.id,
            owner_id=user.id,
            telegram_chat_id=123123123,
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

        # Verify chat still exists but owner_id is null
        from sqlalchemy import select
        db_session.expire_all()  # Clear session cache (not async)
        result = await db_session.execute(
            select(Chat).where(Chat.id == chat_id)
        )
        chat = result.scalar_one_or_none()
        assert chat is not None
        assert chat.owner_id is None

    @pytest.mark.asyncio
    async def test_non_superadmin_cannot_delete_user(
        self, client, admin_token, regular_user, get_auth_headers
    ):
        """Test that non-SUPERADMIN cannot delete users."""
        response = await client.delete(
            f"/api/users/{regular_user.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_user_requires_authentication(
        self, client, admin_user
    ):
        """Test that deleting user requires authentication."""
        response = await client.delete(
            f"/api/users/{admin_user.id}"
        )

        assert response.status_code == 401


class TestUserRoleBasedAccess:
    """Test role-based access control for user operations."""

    @pytest.mark.asyncio
    async def test_admin_cannot_create_users(
        self, client, admin_token, department, get_auth_headers
    ):
        """Test that ADMIN role cannot create users."""
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
    async def test_sub_admin_cannot_create_users(
        self, client, department, get_auth_headers, db_session
    ):
        """Test that SUB_ADMIN role cannot create users."""
        # Create SUB_ADMIN
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

        from api.services.auth import create_access_token
        sub_admin_token = create_access_token(data={"sub": str(sub_admin.id)})

        response = await client.post(
            "/api/users",
            json={
                "email": "unauthorized@test.com",
                "password": "Password123!",
                "name": "Unauthorized",
                "role": "admin",
                "department_id": department.id
            },
            headers=get_auth_headers(sub_admin_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_cannot_update_users(
        self, client, admin_token, regular_user, get_auth_headers
    ):
        """Test that ADMIN role cannot update users."""
        response = await client.patch(
            f"/api/users/{regular_user.id}",
            json={"name": "Updated"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_cannot_delete_users(
        self, client, admin_token, regular_user, get_auth_headers
    ):
        """Test that ADMIN role cannot delete users."""
        response = await client.delete(
            f"/api/users/{regular_user.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 403


class TestUserEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_create_user_with_empty_name(
        self, client, superadmin_token, department, get_auth_headers
    ):
        """Test that empty name is handled appropriately."""
        response = await client.post(
            "/api/users",
            json={
                "email": "emptyname@test.com",
                "password": "Password123!",
                "name": "",
                "role": "admin",
                "department_id": department.id
            },
            headers=get_auth_headers(superadmin_token)
        )

        # Should either reject or accept empty name
        # This tests current behavior
        assert response.status_code in [201, 400, 422]

    @pytest.mark.asyncio
    async def test_update_user_partial_fields(
        self, client, superadmin_token, admin_user, get_auth_headers
    ):
        """Test that partial updates work correctly."""
        original_email = admin_user.email

        response = await client.patch(
            f"/api/users/{admin_user.id}",
            json={
                "name": "Only Name Updated"
            },
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Only Name Updated"
        assert data["email"] == original_email  # Email should remain unchanged

    @pytest.mark.asyncio
    async def test_get_users_empty_database(
        self, client, get_auth_headers, db_session
    ):
        """Test listing users when only the requesting superadmin exists."""
        # Create fresh superadmin
        superadmin = User(
            email="lonely@test.com",
            password_hash="hashed",
            name="Lonely Admin",
            role=UserRole.superadmin,
            is_active=True
        )
        db_session.add(superadmin)
        await db_session.commit()
        await db_session.refresh(superadmin)

        from api.services.auth import create_access_token
        token = create_access_token(data={"sub": str(superadmin.id)})

        response = await client.get(
            "/api/users",
            headers=get_auth_headers(token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1  # At least the superadmin
        assert any(u["email"] == "lonely@test.com" for u in data)

    @pytest.mark.asyncio
    async def test_delete_user_with_multiple_relationships(
        self, client, superadmin_token, organization, department,
        get_auth_headers, db_session
    ):
        """Test that deleting user with multiple relationships works correctly."""
        # Create user with multiple relationships
        user = User(
            email="complex@test.com",
            password_hash="hashed",
            name="Complex User",
            role=UserRole.admin,
            telegram_id=888888,
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

        # Add chat
        chat = Chat(
            org_id=organization.id,
            owner_id=user.id,
            telegram_chat_id=321321321,
            title="Complex User Chat",
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(chat)
        await db_session.commit()

        # Delete user
        response = await client.delete(
            f"/api/users/{user.id}",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 204

        # Verify all cleanup happened
        from sqlalchemy import select
        user_result = await db_session.execute(
            select(User).where(User.id == user.id)
        )
        assert user_result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_create_user_sets_correct_department_role_for_admin(
        self, client, superadmin_token, department, get_auth_headers, db_session
    ):
        """Test that ADMIN users get 'lead' department role."""
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

        from sqlalchemy import select
        result = await db_session.execute(
            select(DepartmentMember).where(DepartmentMember.user_id == user_id)
        )
        dept_member = result.scalar_one_or_none()
        assert dept_member.role == DeptRole.lead

    @pytest.mark.asyncio
    async def test_create_user_sets_correct_department_role_for_sub_admin(
        self, client, superadmin_token, department, get_auth_headers, db_session
    ):
        """Test that SUB_ADMIN users get 'sub_admin' department role."""
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

        from sqlalchemy import select
        result = await db_session.execute(
            select(DepartmentMember).where(DepartmentMember.user_id == user_id)
        )
        dept_member = result.scalar_one_or_none()
        assert dept_member.role == DeptRole.sub_admin


class TestUserProfileUpdate:
    """Test PATCH /api/users/me/profile endpoint - self profile update."""

    @pytest.mark.asyncio
    async def test_user_can_update_own_profile_name(
        self, client, admin_user, admin_token, get_auth_headers
    ):
        """Test that user can update their own name."""
        response = await client.patch(
            "/api/users/me/profile",
            json={"name": "Updated Name"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["id"] == admin_user.id

    @pytest.mark.asyncio
    async def test_user_can_update_telegram_username(
        self, client, admin_user, admin_token, get_auth_headers
    ):
        """Test that user can update their telegram username."""
        response = await client.patch(
            "/api/users/me/profile",
            json={"telegram_username": "@NewUsername"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        # Should normalize: remove @ prefix, lowercase
        assert data["telegram_username"] == "newusername"

    @pytest.mark.asyncio
    async def test_user_can_add_additional_emails(
        self, client, admin_user, admin_token, get_auth_headers
    ):
        """Test that user can add additional emails."""
        response = await client.patch(
            "/api/users/me/profile",
            json={"additional_emails": ["work@example.com", "Personal@Example.org"]},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        # Should normalize: lowercase, stripped
        assert "work@example.com" in data["additional_emails"]
        assert "personal@example.org" in data["additional_emails"]

    @pytest.mark.asyncio
    async def test_user_can_add_additional_telegram_usernames(
        self, client, admin_user, admin_token, get_auth_headers
    ):
        """Test that user can add additional telegram usernames."""
        response = await client.patch(
            "/api/users/me/profile",
            json={"additional_telegram_usernames": ["@WorkAccount", "PersonalTG"]},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        # Should normalize: remove @ prefix, lowercase
        assert "workaccount" in data["additional_telegram_usernames"]
        assert "personaltg" in data["additional_telegram_usernames"]

    @pytest.mark.asyncio
    async def test_user_can_update_all_profile_fields(
        self, client, admin_user, admin_token, get_auth_headers
    ):
        """Test that user can update all profile fields at once."""
        response = await client.patch(
            "/api/users/me/profile",
            json={
                "name": "Full Update Name",
                "telegram_username": "fullupdate",
                "additional_emails": ["email1@test.com", "email2@test.com"],
                "additional_telegram_usernames": ["tg1", "tg2", "tg3"]
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Full Update Name"
        assert data["telegram_username"] == "fullupdate"
        assert len(data["additional_emails"]) == 2
        assert len(data["additional_telegram_usernames"]) == 3

    @pytest.mark.asyncio
    async def test_profile_update_filters_empty_values(
        self, client, admin_user, admin_token, get_auth_headers
    ):
        """Test that empty strings are filtered from arrays."""
        response = await client.patch(
            "/api/users/me/profile",
            json={
                "additional_emails": ["valid@test.com", "", "  ", "another@test.com"],
                "additional_telegram_usernames": ["valid", "", "  "]
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["additional_emails"] == ["valid@test.com", "another@test.com"]
        assert data["additional_telegram_usernames"] == ["valid"]

    @pytest.mark.asyncio
    async def test_profile_update_clears_telegram_username_with_empty_string(
        self, client, db_session, get_auth_headers
    ):
        """Test that empty string clears telegram username."""
        # Create user with telegram username
        user = User(
            email="hastg@test.com",
            password_hash="hashed",
            name="Has TG",
            role=UserRole.admin,
            telegram_username="oldusername",
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        token = create_access_token(data={"sub": str(user.id)})

        response = await client.patch(
            "/api/users/me/profile",
            json={"telegram_username": ""},
            headers=get_auth_headers(token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["telegram_username"] is None

    @pytest.mark.asyncio
    async def test_profile_update_requires_authentication(self, client):
        """Test that profile update requires authentication."""
        response = await client.patch(
            "/api/users/me/profile",
            json={"name": "Unauthenticated"}
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_profile_update_partial_fields_preserve_others(
        self, client, db_session, get_auth_headers
    ):
        """Test that updating some fields doesn't affect others."""
        # Create user with all fields set
        user = User(
            email="fulluser@test.com",
            password_hash="hashed",
            name="Original Name",
            role=UserRole.admin,
            telegram_username="originaltg",
            additional_emails=["original@test.com"],
            additional_telegram_usernames=["originaltguser"],
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        token = create_access_token(data={"sub": str(user.id)})

        # Only update name
        response = await client.patch(
            "/api/users/me/profile",
            json={"name": "New Name Only"},
            headers=get_auth_headers(token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name Only"
        # Other fields should be unchanged
        assert data["telegram_username"] == "originaltg"
        assert data["additional_emails"] == ["original@test.com"]
        assert data["additional_telegram_usernames"] == ["originaltguser"]

    @pytest.mark.asyncio
    async def test_profile_response_includes_new_fields(
        self, client, admin_token, get_auth_headers
    ):
        """Test that profile response includes additional_emails and additional_telegram_usernames."""
        response = await client.patch(
            "/api/users/me/profile",
            json={"name": "Test Fields"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        # Response should include these fields even if empty
        assert "additional_emails" in data
        assert "additional_telegram_usernames" in data
        assert isinstance(data["additional_emails"], list)
        assert isinstance(data["additional_telegram_usernames"], list)

    @pytest.mark.asyncio
    async def test_get_current_user_includes_additional_fields(
        self, client, db_session, get_auth_headers
    ):
        """Test that GET /api/users/me includes additional profile fields."""
        # Create user with additional fields
        user = User(
            email="withfields@test.com",
            password_hash="hashed",
            name="With Fields",
            role=UserRole.admin,
            additional_emails=["extra@test.com"],
            additional_telegram_usernames=["extratg"],
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
        assert data["additional_emails"] == ["extra@test.com"]
        assert data["additional_telegram_usernames"] == ["extratg"]
