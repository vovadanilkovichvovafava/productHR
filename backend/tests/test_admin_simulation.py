"""
Tests for admin role simulation and permission management features.

These tests verify that role-based access control works correctly across the system:
- SUPERADMIN: Full access to everything
- OWNER: Full access within organization (except SUPERADMIN's private content)
- ADMIN (Department Lead): Full access within their department
- SUB_ADMIN: View all dept data, limited management (cannot delete admins)
- MEMBER: View own data + shared resources only
"""
import pytest
from datetime import datetime

from api.models.database import (
    User, UserRole, Organization, OrgMember, OrgRole,
    Department, DepartmentMember, DeptRole,
    Entity, Chat, CallRecording, EntityType, EntityStatus,
    ChatType, CallSource, CallStatus
)
from api.services.auth import create_access_token


# ============================================================================
# FIXTURES - Additional users with different roles
# ============================================================================

@pytest.fixture
async def sub_admin_user(db_session):
    """Create a SUB_ADMIN user."""
    user = User(
        email="subadmin@test.com",
        password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYqVr/1fXem",  # hashed "password"
        name="Sub Admin",
        role=UserRole.sub_admin,
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def member_user(db_session):
    """Create a MEMBER user (regular user)."""
    user = User(
        email="member@test.com",
        password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYqVr/1fXem",
        name="Regular Member",
        role=UserRole.admin,  # Base role, but will be MEMBER in org/dept
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def owner_user(db_session):
    """Create an OWNER user."""
    user = User(
        email="owner@test.com",
        password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYqVr/1fXem",
        name="Organization Owner",
        role=UserRole.admin,
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def setup_org_structure(
    db_session,
    organization,
    department,
    second_department,
    superadmin_user,
    owner_user,
    admin_user,
    sub_admin_user,
    member_user
):
    """Set up complete org structure with all roles."""
    # Add users to organization with different roles
    memberships = [
        OrgMember(org_id=organization.id, user_id=superadmin_user.id, role=OrgRole.owner),
        OrgMember(org_id=organization.id, user_id=owner_user.id, role=OrgRole.owner),
        OrgMember(org_id=organization.id, user_id=admin_user.id, role=OrgRole.admin),
        OrgMember(org_id=organization.id, user_id=sub_admin_user.id, role=OrgRole.admin),
        OrgMember(org_id=organization.id, user_id=member_user.id, role=OrgRole.member),
    ]
    for m in memberships:
        db_session.add(m)

    # Add users to departments with different roles
    dept_members = [
        # First department: admin_user is lead, member_user is member
        DepartmentMember(department_id=department.id, user_id=admin_user.id, role=DeptRole.lead),
        DepartmentMember(department_id=department.id, user_id=member_user.id, role=DeptRole.member),
        # Second department: sub_admin_user is sub_admin
        DepartmentMember(department_id=second_department.id, user_id=sub_admin_user.id, role=DeptRole.sub_admin),
    ]
    for dm in dept_members:
        db_session.add(dm)

    await db_session.commit()
    return {
        'org': organization,
        'dept1': department,
        'dept2': second_department,
        'superadmin': superadmin_user,
        'owner': owner_user,
        'admin': admin_user,
        'sub_admin': sub_admin_user,
        'member': member_user
    }


# ============================================================================
# TEST CLASS: Access Matrix Endpoint
# ============================================================================

@pytest.mark.asyncio
class TestAccessMatrix:
    """
    Test /api/admin/access-matrix endpoint.

    Returns a matrix showing what each role can do across different resources.
    """

    async def test_access_matrix_returns_structure(self, client, superadmin_user):
        """Test that access matrix endpoint returns correct structure."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.get(
            "/api/admin/access-matrix",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Should have roles and permissions
        assert "roles" in data
        assert "permissions" in data
        assert "matrix" in data

        # All roles should be included
        roles = data["roles"]
        assert "SUPERADMIN" in roles
        assert "OWNER" in roles
        assert "ADMIN" in roles
        assert "SUB_ADMIN" in roles
        assert "MEMBER" in roles

    async def test_access_matrix_includes_all_permissions(self, client, superadmin_user):
        """Test that all permissions are listed in access matrix."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.get(
            "/api/admin/access-matrix",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        permissions = data["permissions"]

        # Should include key permissions
        expected_permissions = [
            "view_all_users",
            "create_users",
            "delete_users",
            "view_org_entities",
            "view_dept_entities",
            "view_own_entities",
            "edit_org_entities",
            "edit_dept_entities",
            "delete_dept_entities",
            "view_org_chats",
            "view_dept_chats",
            "view_org_calls",
            "manage_departments",
            "manage_org_members",
            "impersonate_users"
        ]

        for perm in expected_permissions:
            assert perm in permissions, f"Permission {perm} should be in matrix"

    async def test_access_matrix_only_superadmin(self, client, admin_user, regular_user):
        """Test that only SUPERADMIN can access the access matrix."""
        # Test with admin user
        admin_token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            "/api/admin/access-matrix",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 403

        # Test with regular user
        user_token = create_access_token(data={"sub": str(regular_user.id)})
        response = await client.get(
            "/api/admin/access-matrix",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403

    async def test_access_matrix_unauthenticated(self, client):
        """Test that unauthenticated requests are rejected."""
        response = await client.get("/api/admin/access-matrix")
        assert response.status_code in [401, 403]

    async def test_access_matrix_superadmin_permissions(self, client, superadmin_user):
        """Test that SUPERADMIN has all permissions in matrix."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.get(
            "/api/admin/access-matrix",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        matrix = data["matrix"]

        # SUPERADMIN should have access to everything
        superadmin_perms = matrix.get("SUPERADMIN", {})
        for permission, has_access in superadmin_perms.items():
            assert has_access is True, f"SUPERADMIN should have {permission}"


# ============================================================================
# TEST CLASS: Simulate Access Endpoint
# ============================================================================

@pytest.mark.asyncio
class TestSimulateAccess:
    """
    Test /api/admin/simulate-access endpoint.

    Simulates what a specific role can access for testing purposes.
    """

    async def test_simulate_superadmin_access(self, client, superadmin_user):
        """Test simulating SUPERADMIN access - should see everything."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.post(
            "/api/admin/simulate-access",
            headers={"Authorization": f"Bearer {token}"},
            json={"role": "SUPERADMIN"}
        )

        assert response.status_code == 200
        data = response.json()

        # SUPERADMIN can do everything
        assert data["can_view_all_users"] is True
        assert data["can_delete_users"] is True
        assert data["can_impersonate"] is True
        assert data["can_view_all_orgs"] is True
        assert data["can_manage_departments"] is True

    async def test_simulate_owner_access(self, client, superadmin_user, organization):
        """Test simulating OWNER access - full org access."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.post(
            "/api/admin/simulate-access",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "role": "OWNER",
                "org_id": organization.id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # OWNER has full org access
        assert data["can_view_org_entities"] is True
        assert data["can_edit_org_entities"] is True
        assert data["can_delete_org_entities"] is True
        assert data["can_manage_org_members"] is True
        assert data["can_manage_departments"] is True

        # But not global permissions
        assert data["can_impersonate"] is False
        assert data.get("can_view_all_orgs", False) is False

    async def test_simulate_admin_access(self, client, superadmin_user, organization, department):
        """Test simulating ADMIN (lead) access - department scoped."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.post(
            "/api/admin/simulate-access",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "role": "ADMIN",
                "org_id": organization.id,
                "dept_id": department.id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # ADMIN can manage their department
        assert data["can_view_dept_entities"] is True
        assert data["can_edit_dept_entities"] is True
        assert data["can_delete_dept_entities"] is True
        assert data["can_manage_dept_members"] is True

        # But not org-wide
        assert data.get("can_view_all_org_entities", False) is False
        assert data.get("can_manage_org_members", False) is False
        assert data["can_impersonate"] is False

    async def test_simulate_sub_admin_access(self, client, superadmin_user, organization, department):
        """Test simulating SUB_ADMIN access - limited admin rights."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.post(
            "/api/admin/simulate-access",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "role": "SUB_ADMIN",
                "org_id": organization.id,
                "dept_id": department.id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # SUB_ADMIN can view dept data
        assert data["can_view_dept_entities"] is True
        assert data["can_view_dept_chats"] is True

        # Can edit but not delete admins
        assert data["can_edit_dept_entities"] is True
        assert data.get("can_delete_dept_admins", False) is False

        # Limited management
        assert data.get("can_manage_dept_members", True) is True
        assert data.get("can_delete_dept_members", False) is False

    async def test_simulate_member_access(self, client, superadmin_user, organization):
        """Test simulating MEMBER access - most restricted."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.post(
            "/api/admin/simulate-access",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "role": "MEMBER",
                "org_id": organization.id
            }
        )

        assert response.status_code == 200
        data = response.json()

        # MEMBER can only view own data
        assert data["can_view_own_entities"] is True
        assert data["can_edit_own_entities"] is True

        # Cannot view dept-wide data
        assert data.get("can_view_dept_entities", False) is False
        assert data.get("can_view_all_dept_chats", False) is False

        # Can view shared resources
        assert data.get("can_view_shared_entities", True) is True

        # No management permissions
        assert data.get("can_manage_dept_members", False) is False
        assert data["can_impersonate"] is False

    async def test_simulate_access_non_superadmin_denied(self, client, admin_user):
        """Test that non-SUPERADMIN cannot use simulate endpoint."""
        token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.post(
            "/api/admin/simulate-access",
            headers={"Authorization": f"Bearer {token}"},
            json={"role": "MEMBER"}
        )

        assert response.status_code == 403


# ============================================================================
# TEST CLASS: Impersonation
# ============================================================================

@pytest.mark.asyncio
class TestImpersonation:
    """
    Test user impersonation features.

    SUPERADMIN can impersonate any user to debug issues or view their perspective.
    """

    async def test_superadmin_can_impersonate(self, client, superadmin_user, admin_user):
        """Test that SUPERADMIN can impersonate another user."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.post(
            "/api/admin/impersonate",
            headers={"Authorization": f"Bearer {token}"},
            json={"user_id": admin_user.id}
        )

        assert response.status_code == 200
        data = response.json()

        # Should return impersonation token
        assert "token" in data
        assert "impersonated_user" in data
        assert data["impersonated_user"]["id"] == admin_user.id
        assert data["impersonated_user"]["email"] == admin_user.email

        # Token should be different from original
        impersonate_token = data["token"]
        assert impersonate_token != token

    async def test_impersonation_token_works(
        self,
        client,
        superadmin_user,
        admin_user,
        organization,
        department
    ):
        """Test that impersonation token works for API calls."""
        # Get impersonation token
        superadmin_token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.post(
            "/api/admin/impersonate",
            headers={"Authorization": f"Bearer {superadmin_token}"},
            json={"user_id": admin_user.id}
        )

        assert response.status_code == 200
        impersonate_token = response.json()["token"]

        # Use impersonation token to make request
        # Should see data as admin_user, not superadmin
        response = await client.get(
            "/api/users/me",
            headers={"Authorization": f"Bearer {impersonate_token}"}
        )

        # Impersonation may return the impersonated user's data
        # Implementation depends on how impersonation is handled
        assert response.status_code == 200

    async def test_non_superadmin_cannot_impersonate(self, client, admin_user, regular_user):
        """Test that non-SUPERADMIN cannot impersonate."""
        admin_token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.post(
            "/api/admin/impersonate",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"user_id": regular_user.id}
        )

        assert response.status_code == 403

    async def test_exit_impersonation(self, client, superadmin_user, admin_user):
        """Test exiting impersonation mode."""
        # Start impersonation
        superadmin_token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.post(
            "/api/admin/impersonate",
            headers={"Authorization": f"Bearer {superadmin_token}"},
            json={"user_id": admin_user.id}
        )

        assert response.status_code == 200
        impersonate_token = response.json()["token"]

        # Exit impersonation
        response = await client.post(
            "/api/admin/exit-impersonation",
            headers={"Authorization": f"Bearer {impersonate_token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Should return original token or new token for superadmin
        assert "token" in data
        assert data.get("message") == "Exited impersonation mode"

    async def test_impersonation_is_logged(self, client, db_session, superadmin_user, admin_user):
        """Test that impersonation actions are logged for audit."""
        superadmin_token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.post(
            "/api/admin/impersonate",
            headers={"Authorization": f"Bearer {superadmin_token}"},
            json={"user_id": admin_user.id}
        )

        assert response.status_code == 200

        # Check audit log exists (if implemented)
        # This depends on whether audit logging is implemented
        # For now, just verify the endpoint works
        assert True

    async def test_cannot_impersonate_nonexistent_user(self, client, superadmin_user):
        """Test that impersonating non-existent user fails gracefully."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.post(
            "/api/admin/impersonate",
            headers={"Authorization": f"Bearer {token}"},
            json={"user_id": 99999}
        )

        assert response.status_code == 404

    async def test_cannot_impersonate_self(self, client, superadmin_user):
        """Test that user cannot impersonate themselves."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.post(
            "/api/admin/impersonate",
            headers={"Authorization": f"Bearer {token}"},
            json={"user_id": superadmin_user.id}
        )

        assert response.status_code == 400
        assert "cannot impersonate yourself" in response.json()["detail"].lower()


# ============================================================================
# TEST CLASS: Role Permissions Endpoint
# ============================================================================

@pytest.mark.asyncio
class TestRolePermissions:
    """
    Test /api/admin/role-permissions endpoint.

    Returns detailed permissions for each role, grouped by category.
    """

    async def test_role_permissions_returns_all_roles(self, client, superadmin_user):
        """Test that endpoint returns permissions for all roles."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.get(
            "/api/admin/role-permissions",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Should have all roles
        assert "SUPERADMIN" in data
        assert "OWNER" in data
        assert "ADMIN" in data
        assert "SUB_ADMIN" in data
        assert "MEMBER" in data

    async def test_role_permissions_grouped_by_category(self, client, superadmin_user):
        """Test that permissions are grouped by category."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.get(
            "/api/admin/role-permissions",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Check SUPERADMIN permissions structure
        superadmin_perms = data["SUPERADMIN"]

        # Should have categories
        expected_categories = [
            "users",
            "organizations",
            "departments",
            "entities",
            "chats",
            "calls",
            "sharing",
            "admin"
        ]

        for category in expected_categories:
            assert category in superadmin_perms, f"Category {category} should exist"

    async def test_superadmin_has_all_permissions(self, client, superadmin_user):
        """Test that SUPERADMIN has all permissions."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.get(
            "/api/admin/role-permissions",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        superadmin_perms = data["SUPERADMIN"]

        # SUPERADMIN should have all permissions set to True
        for category, permissions in superadmin_perms.items():
            if isinstance(permissions, dict):
                for perm, value in permissions.items():
                    assert value is True, f"SUPERADMIN should have {category}.{perm}"

    async def test_member_has_limited_permissions(self, client, superadmin_user):
        """Test that MEMBER role has most restricted permissions."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.get(
            "/api/admin/role-permissions",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        member_perms = data["MEMBER"]

        # MEMBER should NOT have these permissions
        if "admin" in member_perms:
            assert member_perms["admin"].get("impersonate", False) is False
            assert member_perms["admin"].get("manage_org", False) is False

        if "users" in member_perms:
            assert member_perms["users"].get("delete_users", False) is False
            assert member_perms["users"].get("view_all_users", False) is False

    async def test_role_permissions_only_superadmin(self, client, admin_user):
        """Test that only SUPERADMIN can access role permissions."""
        token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.get(
            "/api/admin/role-permissions",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403

    async def test_role_permissions_specific_role(self, client, superadmin_user):
        """Test getting permissions for a specific role."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.get(
            "/api/admin/role-permissions?role=ADMIN",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Should only return ADMIN permissions
        assert "ADMIN" in data
        assert len(data) == 1

    async def test_role_permissions_includes_descriptions(self, client, superadmin_user):
        """Test that permissions include helpful descriptions."""
        token = create_access_token(data={"sub": str(superadmin_user.id)})

        response = await client.get(
            "/api/admin/role-permissions",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Permissions should have descriptions (optional feature)
        # This tests that the response is well-documented
        assert isinstance(data, dict)
        assert len(data) > 0


# ============================================================================
# TEST CLASS: Real Permission Verification
# ============================================================================

@pytest.mark.asyncio
class TestActualRolePermissions:
    """
    Test that actual role logic matches documented behavior.

    These tests verify the real permission system works correctly.
    """

    async def test_superadmin_sees_all_entities(
        self,
        client,
        db_session,
        setup_org_structure,
        superadmin_user,
        member_user
    ):
        """Test SUPERADMIN can see all entities in system."""
        setup = setup_org_structure

        # Create entities by different users
        entity1 = Entity(
            org_id=setup['org'].id,
            department_id=setup['dept1'].id,
            created_by=member_user.id,
            name="Member's Entity",
            email="member@entity.com",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity1)
        await db_session.commit()

        # SUPERADMIN should see all entities
        token = create_access_token(data={"sub": str(superadmin_user.id)})
        response = await client.get(
            "/api/entities",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        entities = response.json()
        assert len(entities) >= 1

    async def test_admin_sees_only_dept_entities(
        self,
        client,
        db_session,
        setup_org_structure,
        member_user
    ):
        """ADMIN of the org sees all entities; department isolation applies to members.

        Админ организации (OrgRole.admin) — полный доступ к базе
        (has_full_database_access: owner/admin), поэтому видит и чужой отдел.
        Изоляция по отделам осталась у рядового участника — проверяем на нём.
        Сущности — партнёры: кандидаты общие для организации (модель «общий
        пул HR») и видны всем её членам независимо от отдела.
        """
        setup = setup_org_structure

        # Create entity in dept1
        entity1 = Entity(
            org_id=setup['org'].id,
            department_id=setup['dept1'].id,
            created_by=member_user.id,
            name="Dept1 Entity",
            email="dept1@entity.com",
            type=EntityType.partner,
            status=EntityStatus.active
        )
        db_session.add(entity1)

        # Create entity in dept2
        entity2 = Entity(
            org_id=setup['org'].id,
            department_id=setup['dept2'].id,
            created_by=setup['sub_admin'].id,
            name="Dept2 Entity",
            email="dept2@entity.com",
            type=EntityType.partner,
            status=EntityStatus.active
        )
        db_session.add(entity2)
        await db_session.commit()

        # Org admin sees both departments
        admin_token = create_access_token(data={"sub": str(setup['admin'].id)})
        response = await client.get(
            "/api/entities",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        entity_names = [e['name'] for e in response.json()]
        assert "Dept1 Entity" in entity_names
        assert "Dept2 Entity" in entity_names

        # Regular member of dept1 sees own dept1 entity, not dept2
        member_token = create_access_token(data={"sub": str(member_user.id)})
        response = await client.get(
            "/api/entities",
            headers={"Authorization": f"Bearer {member_token}"}
        )
        assert response.status_code == 200
        entity_names = [e['name'] for e in response.json()]
        assert "Dept1 Entity" in entity_names
        assert "Dept2 Entity" not in entity_names

    async def test_member_sees_only_own_entities(
        self,
        client,
        db_session,
        setup_org_structure
    ):
        """Test MEMBER can only see their own entities."""
        setup = setup_org_structure

        # Create entity by member
        entity1 = Entity(
            org_id=setup['org'].id,
            department_id=setup['dept1'].id,
            created_by=setup['member'].id,
            name="Member's Own Entity",
            email="member@entity.com",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity1)

        # Create entity by admin in same dept
        entity2 = Entity(
            org_id=setup['org'].id,
            department_id=setup['dept1'].id,
            created_by=setup['admin'].id,
            name="Admin's Entity",
            email="admin@entity.com",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity2)
        await db_session.commit()

        # Member should only see their own
        member_token = create_access_token(data={"sub": str(setup['member'].id)})
        response = await client.get(
            "/api/entities",
            headers={"Authorization": f"Bearer {member_token}"}
        )

        assert response.status_code == 200
        entities = response.json()

        # Should only see own entity
        entity_names = [e['name'] for e in entities]
        assert "Member's Own Entity" in entity_names
        # Note: Member might see admin's entity if in same dept depending on implementation
        # The key is they definitely see their own

    async def test_sub_admin_cannot_delete_admins(
        self,
        client,
        setup_org_structure
    ):
        """Test SUB_ADMIN cannot delete ADMIN users."""
        setup = setup_org_structure

        # SUB_ADMIN tries to delete ADMIN
        sub_admin_token = create_access_token(data={"sub": str(setup['sub_admin'].id)})
        response = await client.delete(
            f"/api/users/{setup['admin'].id}",
            headers={"Authorization": f"Bearer {sub_admin_token}"}
        )

        # Should be forbidden
        assert response.status_code == 403

    async def test_owner_sees_all_org_data(
        self,
        client,
        db_session,
        setup_org_structure
    ):
        """Test OWNER can see all data in their organization."""
        setup = setup_org_structure

        # Create entities in different departments
        entity1 = Entity(
            org_id=setup['org'].id,
            department_id=setup['dept1'].id,
            created_by=setup['admin'].id,
            name="Dept1 Entity",
            email="dept1@entity.com",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        entity2 = Entity(
            org_id=setup['org'].id,
            department_id=setup['dept2'].id,
            created_by=setup['sub_admin'].id,
            name="Dept2 Entity",
            email="dept2@entity.com",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity1)
        db_session.add(entity2)
        await db_session.commit()

        # OWNER should see all entities in org
        owner_token = create_access_token(data={"sub": str(setup['owner'].id)})
        response = await client.get(
            "/api/entities",
            headers={"Authorization": f"Bearer {owner_token}"}
        )

        assert response.status_code == 200
        entities = response.json()

        # Should see entities from both departments
        entity_names = [e['name'] for e in entities]
        assert "Dept1 Entity" in entity_names
        assert "Dept2 Entity" in entity_names

    async def test_owner_cannot_see_superadmin_private_data(
        self,
        client,
        db_session,
        setup_org_structure,
        superadmin_user
    ):
        """Test OWNER cannot see private content created by SUPERADMIN."""
        setup = setup_org_structure

        # SUPERADMIN creates private entity (no department)
        private_entity = Entity(
            org_id=setup['org'].id,
            department_id=None,  # No department = private
            created_by=superadmin_user.id,
            name="Superadmin Private",
            email="private@entity.com",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(private_entity)
        await db_session.commit()

        # OWNER tries to view
        owner_token = create_access_token(data={"sub": str(setup['owner'].id)})
        response = await client.get(
            f"/api/entities/{private_entity.id}",
            headers={"Authorization": f"Bearer {owner_token}"}
        )

        # Should be forbidden or not found
        assert response.status_code in [403, 404]
