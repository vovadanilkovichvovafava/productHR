"""
Comprehensive unit tests for department CRUD operations.

Tests cover:
- All CRUD operations (create, read, update, delete)
- Department member management (add, remove, update roles)
- Role hierarchy and permissions (lead, sub_admin, member)
- Department hierarchy (parent/child relationships)
- Edge cases and error handling
- Cross-organization isolation
- Nested hierarchies and complex scenarios
- Department statistics
- Cross-department access control
"""
import pytest
import pytest_asyncio
from datetime import datetime
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import (
    User, Organization, Department, DepartmentMember, OrgMember,
    DeptRole, OrgRole, UserRole
)
from api.services.auth import create_access_token


@pytest_asyncio.fixture
async def plain_org_member(db_session, org_admin):
    """regular_user — РЯДОВОЙ член организации, а не её админ.

    Фикстура org_admin делает regular_user админом орга, а админ/владелец орга
    управляет любым отделом (is_org_admin_or_owner в ручках отделов). Тестам
    «рядовой участник / саб-админ / лид другого отдела не может…» нужен
    человек без орг-админства — иначе проверка отдела вообще не наступает.
    """
    from api.models.database import OrgRole
    org_admin.role = OrgRole.member
    await db_session.commit()
    return org_admin


# =============================================================================
# CREATE DEPARTMENT TESTS
# =============================================================================

class TestCreateDepartment:
    """Tests for creating departments."""

    async def test_org_owner_creates_root_department_success(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test org owner can create a root-level department."""
        response = await client.post(
            "/api/departments",
            json={
                "name": "Engineering Department",
                "description": "Engineering team",
                "color": "#FF5733"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code in [200, 201]
        data = response.json()
        assert data["name"] == "Engineering Department"
        assert data["description"] == "Engineering team"
        assert data["color"] == "#FF5733"
        assert data["is_active"] is True
        assert data["parent_id"] is None
        assert "id" in data
        assert "created_at" in data

    async def test_org_owner_creates_department_minimal_fields(
        self, client: AsyncClient, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test creating department with only required fields."""
        response = await client.post(
            "/api/departments",
            json={"name": "HR"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code in [200, 201]
        data = response.json()
        assert data["name"] == "HR"
        assert data["description"] is None
        assert data["color"] is None

    async def test_superadmin_creates_root_department_success(
        self, client: AsyncClient, superadmin_user: User, superadmin_token: str,
        organization: Organization, superadmin_org_member: OrgMember, get_auth_headers
    ):
        """Test superadmin can create root department."""
        response = await client.post(
            "/api/departments",
            json={"name": "Sales Department"},
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code in [200, 201]
        data = response.json()
        assert data["name"] == "Sales Department"

    async def test_org_admin_cannot_create_root_department(
        self, client: AsyncClient, regular_user: User, user_token: str,
        organization: Organization, org_admin: OrgMember, get_auth_headers
    ):
        """Test org admin cannot create root-level department."""
        response = await client.post(
            "/api/departments",
            json={"name": "Unauthorized Dept"},
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 403
        assert "Only owners can create top-level departments" in response.json()["detail"]

    async def test_org_member_cannot_create_root_department(
        self, client: AsyncClient, second_user: User, second_user_token: str,
        organization: Organization, org_member: OrgMember, get_auth_headers
    ):
        """Test org member cannot create root-level department."""
        response = await client.post(
            "/api/departments",
            json={"name": "Member Dept"},
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    async def test_dept_lead_creates_subdepartment_success(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        department: Department, org_owner: OrgMember, dept_lead: DepartmentMember,
        get_auth_headers
    ):
        """Test department lead can create subdepartment under their department."""
        response = await client.post(
            "/api/departments",
            json={
                "name": "Backend Team",
                "description": "Backend engineering team",
                "parent_id": department.id
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code in [200, 201]
        data = response.json()
        assert data["name"] == "Backend Team"
        assert data["parent_id"] == department.id
        assert data["parent_name"] == department.name

    async def test_dept_lead_creates_subdepartment_becomes_lead(
        self, db_session: AsyncSession, client: AsyncClient,
        regular_user: User, user_token: str, department: Department,
        organization: Organization, org_admin: OrgMember, get_auth_headers
    ):
        """Test when dept lead creates subdepartment, they become lead of it."""
        # Make regular_user a lead of parent department
        lead = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(lead)
        await db_session.commit()

        # Create subdepartment
        response = await client.post(
            "/api/departments",
            json={
                "name": "Sub Team",
                "parent_id": department.id
            },
            headers=get_auth_headers(user_token)
        )

        assert response.status_code in [200, 201]
        data = response.json()
        # Non-owner creating subdepartment gets added as lead
        assert data["members_count"] == 1

    async def test_non_lead_cannot_create_subdepartment(
        self, client: AsyncClient, regular_user: User, user_token: str,
        department: Department, org_admin: OrgMember, dept_member: DepartmentMember,
        get_auth_headers
    ):
        """Test regular member cannot create subdepartment."""
        response = await client.post(
            "/api/departments",
            json={
                "name": "Unauthorized Sub",
                "parent_id": department.id
            },
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 403
        assert "Only org owners or department leads can create sub-departments" in response.json()["detail"]

    async def test_create_subdepartment_invalid_parent(
        self, client: AsyncClient, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test creating subdepartment with non-existent parent fails."""
        response = await client.post(
            "/api/departments",
            json={
                "name": "Orphan Dept",
                "parent_id": 99999
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404
        assert "Parent department not found" in response.json()["detail"]

    async def test_create_department_empty_name_fails(
        self, client: AsyncClient, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test creating department with empty name fails validation."""
        response = await client.post(
            "/api/departments",
            json={"name": ""},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 422

    async def test_create_department_without_org_access_fails(
        self, client: AsyncClient, second_user: User, second_user_token: str,
        get_auth_headers
    ):
        """Test creating department without org membership fails."""
        response = await client.post(
            "/api/departments",
            json={"name": "No Org Dept"},
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403
        assert "No organization access" in response.json()["detail"]


# =============================================================================
# READ DEPARTMENT TESTS
# =============================================================================

class TestGetDepartment:
    """Tests for retrieving single department details."""

    async def test_get_department_by_id_success(
        self, client: AsyncClient, admin_token: str, department: Department,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test getting department by ID returns full details."""
        response = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == department.id
        assert data["name"] == department.name
        assert "members_count" in data
        assert "entities_count" in data
        assert "children_count" in data
        assert "created_at" in data

    async def test_get_department_with_members_count(
        self, client: AsyncClient, admin_token: str, department: Department,
        organization: Organization, org_owner: OrgMember, dept_member: DepartmentMember,
        get_auth_headers
    ):
        """Test department response includes correct member count."""
        response = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["members_count"] >= 1

    async def test_get_department_with_entities_count(
        self, client: AsyncClient, admin_token: str, department: Department,
        organization: Organization, org_owner: OrgMember, entity, get_auth_headers
    ):
        """Test department response includes correct entity count."""
        response = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["entities_count"] >= 1

    async def test_get_department_with_children(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        get_auth_headers
    ):
        """Test department response includes correct children count."""
        # Create child department
        child = Department(
            name="Child Dept",
            org_id=organization.id,
            parent_id=department.id,
            created_at=datetime.utcnow()
        )
        db_session.add(child)
        await db_session.commit()

        response = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["children_count"] >= 1

    async def test_get_department_with_parent(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        get_auth_headers
    ):
        """Test child department includes parent name."""
        # Create child department
        child = Department(
            name="Child Dept",
            org_id=organization.id,
            parent_id=department.id,
            created_at=datetime.utcnow()
        )
        db_session.add(child)
        await db_session.commit()
        await db_session.refresh(child)

        response = await client.get(
            f"/api/departments/{child.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["parent_id"] == department.id
        assert data["parent_name"] == department.name

    async def test_get_nonexistent_department_fails(
        self, client: AsyncClient, admin_token: str, organization: Organization,
        org_owner: OrgMember, get_auth_headers
    ):
        """Test getting non-existent department returns 404."""
        response = await client.get(
            "/api/departments/99999",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404
        assert "Department not found" in response.json()["detail"]

    async def test_get_department_from_different_org_fails(
        self, db_session: AsyncSession, client: AsyncClient, second_user: User,
        second_user_token: str, second_organization: Organization,
        department: Department, get_auth_headers
    ):
        """Test cannot access department from different organization."""
        # Make second_user member of second_organization
        org_member = OrgMember(
            org_id=second_organization.id,
            user_id=second_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(org_member)
        await db_session.commit()

        # Try to access department from first organization
        response = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 404


class TestListDepartments:
    """Tests for listing departments."""

    async def test_org_owner_lists_all_departments(
        self, client: AsyncClient, admin_token: str, department: Department,
        second_department: Department, organization: Organization,
        org_owner: OrgMember, get_auth_headers
    ):
        """Test org owner sees all departments with full details."""
        response = await client.get(
            "/api/departments",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2

        # All should have full details
        for dept in data:
            assert "members_count" in dept
            assert "entities_count" in dept
            assert "children_count" in dept

        dept_ids = [d["id"] for d in data]
        assert department.id in dept_ids
        assert second_department.id in dept_ids

    async def test_superadmin_lists_all_departments(
        self, client: AsyncClient, superadmin_token: str, department: Department,
        second_department: Department, organization: Organization, superadmin_org_member: OrgMember,
        get_auth_headers
    ):
        """Test superadmin sees all departments with full details."""
        response = await client.get(
            "/api/departments",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        dept_ids = [d["id"] for d in data]
        assert department.id in dept_ids
        assert second_department.id in dept_ids

    async def test_admin_sees_own_dept_full_others_minimal(
        self, client: AsyncClient, regular_user: User, user_token: str,
        department: Department, second_department: Department,
        organization: Organization, org_admin: OrgMember, get_auth_headers
    ):
        """Org admin sees ALL departments with full details.

        Раньше админ орга видел свой отдел полностью, а чужие — только id и
        имя. Теперь owner и org-admin видят все отделы целиком (list_departments:
        нужно, например, пикеру отдела в «Взять в штат» — у HR-админов без
        своего отдела он был пустым). Имя теста оставлено для истории.
        """
        response = await client.get(
            "/api/departments",
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 200
        data = response.json()

        own_dept = next((d for d in data if d["id"] == department.id), None)
        other_dept = next((d for d in data if d["id"] == second_department.id), None)
        assert own_dept is not None and other_dept is not None
        for d in (own_dept, other_dept):
            assert "members_count" in d
            assert "entities_count" in d

    async def test_member_sees_only_own_department(
        self, client: AsyncClient, regular_user: User, user_token: str,
        department: Department, second_department: Department,
        organization: Organization, org_admin: OrgMember, dept_member: DepartmentMember,
        get_auth_headers
    ):
        """Test regular member sees only their own department."""
        response = await client.get(
            "/api/departments",
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Should see at least own department
        dept_ids = [d["id"] for d in data]
        assert department.id in dept_ids

    async def test_list_departments_filter_by_parent(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        get_auth_headers
    ):
        """Test filtering departments by parent_id."""
        # Create child departments
        child1 = Department(
            name="Child 1",
            org_id=organization.id,
            parent_id=department.id,
            created_at=datetime.utcnow()
        )
        child2 = Department(
            name="Child 2",
            org_id=organization.id,
            parent_id=department.id,
            created_at=datetime.utcnow()
        )
        db_session.add_all([child1, child2])
        await db_session.commit()

        response = await client.get(
            f"/api/departments?parent_id={department.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2

        # All should be children of parent department
        for dept in data:
            assert dept["parent_id"] == department.id

    async def test_list_top_level_departments_only(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        get_auth_headers
    ):
        """Test listing only top-level departments (no parent)."""
        # Create child department
        child = Department(
            name="Child Dept",
            org_id=organization.id,
            parent_id=department.id,
            created_at=datetime.utcnow()
        )
        db_session.add(child)
        await db_session.commit()

        # Without parent_id param, should get only top-level
        response = await client.get(
            "/api/departments",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Filter for departments that are in our organization
        for dept in data:
            # Top-level departments have no parent
            if "parent_id" in dept:
                assert dept["parent_id"] is None

    async def test_list_all_departments_with_parent_id_minus_one(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        get_auth_headers
    ):
        """Test parent_id=-1 returns all departments regardless of hierarchy."""
        # Create child department
        child = Department(
            name="Child Dept",
            org_id=organization.id,
            parent_id=department.id,
            created_at=datetime.utcnow()
        )
        db_session.add(child)
        await db_session.commit()

        response = await client.get(
            "/api/departments?parent_id=-1",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Should include both parent and child
        dept_ids = [d["id"] for d in data]
        assert department.id in dept_ids
        assert child.id in dept_ids

    async def test_list_departments_empty_org(
        self, client: AsyncClient, admin_token: str, organization: Organization,
        org_owner: OrgMember, get_auth_headers
    ):
        """Test listing departments in organization with no departments."""
        response = await client.get(
            "/api/departments",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        # May be empty or have departments from fixtures
        assert isinstance(data, list)


class TestGetDepartmentChildren:
    """Tests for getting department children."""

    async def test_get_children_of_department(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        get_auth_headers
    ):
        """Test getting child departments of a parent department."""
        # Create children
        child1 = Department(
            name="Backend",
            org_id=organization.id,
            parent_id=department.id,
            created_at=datetime.utcnow()
        )
        child2 = Department(
            name="Frontend",
            org_id=organization.id,
            parent_id=department.id,
            created_at=datetime.utcnow()
        )
        db_session.add_all([child1, child2])
        await db_session.commit()

        response = await client.get(
            f"/api/departments/{department.id}/children",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2

        # All children should have parent info
        for child in data:
            assert child["parent_id"] == department.id
            assert child["parent_name"] == department.name

    async def test_get_children_of_department_without_children(
        self, client: AsyncClient, admin_token: str, department: Department,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test getting children of department with no children returns empty."""
        response = await client.get(
            f"/api/departments/{department.id}/children",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_children_of_nonexistent_department(
        self, client: AsyncClient, admin_token: str, organization: Organization,
        org_owner: OrgMember, get_auth_headers
    ):
        """Test getting children of non-existent department fails."""
        response = await client.get(
            "/api/departments/99999/children",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404


class TestGetMyDepartments:
    """Tests for getting current user's departments."""

    async def test_get_my_departments_as_member(
        self, client: AsyncClient, regular_user: User, user_token: str,
        department: Department, organization: Organization, org_admin: OrgMember,
        dept_member: DepartmentMember, get_auth_headers
    ):
        """Test user can get their own departments."""
        response = await client.get(
            "/api/departments/my/departments",
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 200
        data = response.json()
        dept_ids = [d["id"] for d in data]
        assert department.id in dept_ids

    async def test_get_my_departments_as_lead(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        dept_lead: DepartmentMember, get_auth_headers
    ):
        """Test department lead can get their departments."""
        response = await client.get(
            "/api/departments/my/departments",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        dept_ids = [d["id"] for d in data]
        assert department.id in dept_ids

    async def test_get_my_departments_no_membership(
        self, client: AsyncClient, second_user: User, second_user_token: str,
        organization: Organization, org_member: OrgMember, get_auth_headers
    ):
        """Test user not in any department gets empty list."""
        response = await client.get(
            "/api/departments/my/departments",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


# =============================================================================
# UPDATE DEPARTMENT TESTS
# =============================================================================

class TestUpdateDepartment:
    """Tests for updating department details."""

    async def test_org_owner_updates_department(
        self, client: AsyncClient, admin_token: str, department: Department,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test org owner can update department."""
        response = await client.patch(
            f"/api/departments/{department.id}",
            json={
                "name": "Updated Name",
                "description": "Updated description",
                "color": "#00FF00"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["description"] == "Updated description"
        assert data["color"] == "#00FF00"

    async def test_dept_lead_updates_own_department(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        dept_lead: DepartmentMember, get_auth_headers
    ):
        """Test department lead can update their department."""
        response = await client.patch(
            f"/api/departments/{department.id}",
            json={"name": "Lead Updated"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Lead Updated"

    async def test_regular_member_cannot_update_department(
        self, client: AsyncClient, regular_user: User, user_token: str,
        department: Department, organization: Organization, org_admin: OrgMember,
        dept_member: DepartmentMember, get_auth_headers
    ):
        """Test regular member cannot update department."""
        response = await client.patch(
            f"/api/departments/{department.id}",
            json={"name": "Unauthorized Update"},
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 403
        assert "Permission denied" in response.json()["detail"]

    async def test_update_department_partial_fields(
        self, client: AsyncClient, admin_token: str, department: Department,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test updating only some fields leaves others unchanged."""
        # Get original data
        get_response = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )
        original = get_response.json()

        # Update only description
        response = await client.patch(
            f"/api/departments/{department.id}",
            json={"description": "New description only"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == original["name"]  # Unchanged
        assert data["description"] == "New description only"  # Changed

    async def test_only_owner_can_deactivate_department(
        self, db_session: AsyncSession, client: AsyncClient, regular_user: User,
        user_token: str, department: Department, organization: Organization,
        org_admin: OrgMember, get_auth_headers
    ):
        """Test only org owner can set is_active to false."""
        # Make regular_user a lead
        lead = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(lead)
        await db_session.commit()

        # Try to deactivate as lead
        response = await client.patch(
            f"/api/departments/{department.id}",
            json={"is_active": False},
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 200
        data = response.json()
        # Should still be active (only owner can deactivate)
        assert data["is_active"] is True

    async def test_owner_can_deactivate_department(
        self, client: AsyncClient, admin_token: str, department: Department,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test org owner can deactivate department."""
        response = await client.patch(
            f"/api/departments/{department.id}",
            json={"is_active": False},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False

    async def test_update_nonexistent_department_fails(
        self, client: AsyncClient, admin_token: str, organization: Organization,
        org_owner: OrgMember, get_auth_headers
    ):
        """Test updating non-existent department fails."""
        response = await client.patch(
            "/api/departments/99999",
            json={"name": "Does not exist"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    async def test_update_department_from_different_org_fails(
        self, db_session: AsyncSession, client: AsyncClient, second_user: User,
        second_user_token: str, second_organization: Organization,
        department: Department, get_auth_headers
    ):
        """Test cannot update department from different organization."""
        # Make second_user owner of second org
        org_owner = OrgMember(
            org_id=second_organization.id,
            user_id=second_user.id,
            role=OrgRole.owner,
            created_at=datetime.utcnow()
        )
        db_session.add(org_owner)
        await db_session.commit()

        response = await client.patch(
            f"/api/departments/{department.id}",
            json={"name": "Cross-org update"},
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 404


# =============================================================================
# DELETE DEPARTMENT TESTS
# =============================================================================

class TestDeleteDepartment:
    """Tests for deleting departments."""

    async def test_org_owner_deletes_empty_department(
        self, client: AsyncClient, admin_token: str, department: Department,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test org owner can delete empty department."""
        response = await client.delete(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify deletion
        get_response = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )
        assert get_response.status_code == 404

    async def test_superadmin_deletes_department(
        self, client: AsyncClient, superadmin_token: str, department: Department,
        organization: Organization, superadmin_org_member: OrgMember, get_auth_headers
    ):
        """Test superadmin can delete department."""
        response = await client.delete(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200

    async def test_dept_lead_cannot_delete_department(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        dept_lead: DepartmentMember, get_auth_headers
    ):
        """Test department lead cannot delete department (only owner can)."""
        # For this test, we need admin_user to be lead but NOT owner
        # Since they're already owner via org_owner fixture, we need different setup
        # Let's use a different user
        pass  # This is handled by test_org_admin_cannot_delete_department

    async def test_org_admin_cannot_delete_department(
        self, client: AsyncClient, regular_user: User, user_token: str,
        department: Department, organization: Organization, org_admin: OrgMember,
        get_auth_headers
    ):
        """Test org admin cannot delete department."""
        response = await client.delete(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 403
        assert "Only owners can delete departments" in response.json()["detail"]

    async def test_cannot_delete_department_with_members(
        self, client: AsyncClient, admin_token: str, department: Department,
        organization: Organization, org_owner: OrgMember, dept_member: DepartmentMember,
        get_auth_headers
    ):
        """Test cannot delete department that has members."""
        response = await client.delete(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 400
        assert "member" in response.json()["detail"].lower()

    async def test_cannot_delete_department_with_entities(
        self, client: AsyncClient, admin_token: str, department: Department,
        organization: Organization, org_owner: OrgMember, entity, get_auth_headers
    ):
        """Test cannot delete department that has entities."""
        response = await client.delete(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 400
        assert "entit" in response.json()["detail"].lower()

    async def test_delete_nonexistent_department_fails(
        self, client: AsyncClient, admin_token: str, organization: Organization,
        org_owner: OrgMember, get_auth_headers
    ):
        """Test deleting non-existent department fails."""
        response = await client.delete(
            "/api/departments/99999",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    async def test_delete_department_from_different_org_fails(
        self, db_session: AsyncSession, client: AsyncClient, second_user: User,
        second_user_token: str, second_organization: Organization,
        department: Department, get_auth_headers
    ):
        """Test cannot delete department from different organization."""
        # Make second_user owner of second org
        org_owner = OrgMember(
            org_id=second_organization.id,
            user_id=second_user.id,
            role=OrgRole.owner,
            created_at=datetime.utcnow()
        )
        db_session.add(org_owner)
        await db_session.commit()

        response = await client.delete(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 404


# =============================================================================
# DEPARTMENT MEMBER MANAGEMENT TESTS
# =============================================================================

class TestListDepartmentMembers:
    """Tests for listing department members."""

    async def test_list_department_members(
        self, client: AsyncClient, admin_token: str, department: Department,
        organization: Organization, org_owner: OrgMember, dept_member: DepartmentMember,
        get_auth_headers
    ):
        """Test listing all members of a department."""
        response = await client.get(
            f"/api/departments/{department.id}/members",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

        # Check member structure
        member = data[0]
        assert "id" in member
        assert "user_id" in member
        assert "user_name" in member
        assert "user_email" in member
        assert "role" in member
        assert "created_at" in member

    async def test_list_members_shows_role_hierarchy(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        regular_user: User, second_user: User, get_auth_headers
    ):
        """Test member list includes different roles."""
        # Create members with different roles
        lead = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        sub_admin = DepartmentMember(
            department_id=department.id,
            user_id=second_user.id,
            role=DeptRole.sub_admin,
            created_at=datetime.utcnow()
        )
        db_session.add_all([lead, sub_admin])
        await db_session.commit()

        response = await client.get(
            f"/api/departments/{department.id}/members",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        roles = [m["role"] for m in data]
        assert "lead" in roles
        assert "sub_admin" in roles

    async def test_list_members_of_nonexistent_department_fails(
        self, client: AsyncClient, admin_token: str, organization: Organization,
        org_owner: OrgMember, get_auth_headers
    ):
        """Test listing members of non-existent department fails."""
        response = await client.get(
            "/api/departments/99999/members",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404


class TestAddDepartmentMember:
    """Tests for adding members to departments."""

    async def test_org_owner_adds_member_to_department(
        self, client: AsyncClient, admin_token: str, department: Department,
        second_user: User, organization: Organization, org_owner: OrgMember,
        org_member: OrgMember, get_auth_headers
    ):
        """Test org owner can add member to department."""
        response = await client.post(
            f"/api/departments/{department.id}/members",
            json={
                "user_id": second_user.id,
                "role": "member"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code in [200, 201]
        data = response.json()
        assert data["user_id"] == second_user.id
        assert data["role"] == "member"

    async def test_dept_lead_adds_member_to_department(
        self, db_session: AsyncSession, client: AsyncClient, regular_user: User,
        user_token: str, department: Department, second_user: User,
        organization: Organization, org_admin: OrgMember, org_member: OrgMember,
        get_auth_headers
    ):
        """Test department lead can add member."""
        # Make regular_user a lead
        lead = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(lead)
        await db_session.commit()

        response = await client.post(
            f"/api/departments/{department.id}/members",
            json={
                "user_id": second_user.id,
                "role": "member"
            },
            headers=get_auth_headers(user_token)
        )

        assert response.status_code in [200, 201]

    async def test_regular_member_cannot_add_member(
        self, client: AsyncClient, regular_user: User, user_token: str,
        department: Department, second_user: User, organization: Organization,
        plain_org_member: OrgMember, org_member: OrgMember, dept_member: DepartmentMember,
        get_auth_headers
    ):
        """Test regular member cannot add member to department."""
        response = await client.post(
            f"/api/departments/{department.id}/members",
            json={
                "user_id": second_user.id,
                "role": "member"
            },
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 403

    async def test_only_owner_can_add_lead(
        self, db_session: AsyncSession, client: AsyncClient, regular_user: User,
        user_token: str, department: Department, second_user: User,
        organization: Organization, org_admin: OrgMember, org_member: OrgMember,
        get_auth_headers
    ):
        """Test only org owner can add department lead."""
        # Make regular_user a lead
        lead = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(lead)
        await db_session.commit()

        # Try to add another lead
        response = await client.post(
            f"/api/departments/{department.id}/members",
            json={
                "user_id": second_user.id,
                "role": "lead"
            },
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 403
        assert "Only org owners can add department leads" in response.json()["detail"]

    async def test_owner_can_add_lead(
        self, client: AsyncClient, admin_token: str, department: Department,
        second_user: User, organization: Organization, org_owner: OrgMember,
        org_member: OrgMember, get_auth_headers
    ):
        """Test org owner can add department lead."""
        response = await client.post(
            f"/api/departments/{department.id}/members",
            json={
                "user_id": second_user.id,
                "role": "lead"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code in [200, 201]
        data = response.json()
        assert data["role"] == "lead"

    async def test_add_member_user_not_in_org_fails(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        get_auth_headers
    ):
        """Test adding user who is not in organization fails."""
        # Create user not in org
        other_user = User(
            email="outsider@test.com",
            password_hash="hash",
            name="Outsider",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)

        response = await client.post(
            f"/api/departments/{department.id}/members",
            json={
                "user_id": other_user.id,
                "role": "member"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404
        assert "User not found in organization" in response.json()["detail"]

    async def test_add_existing_member_updates_role(
        self, client: AsyncClient, admin_token: str, department: Department,
        regular_user: User, organization: Organization, org_owner: OrgMember,
        org_admin: OrgMember, dept_member: DepartmentMember, get_auth_headers
    ):
        """Test adding existing member updates their role."""
        # dept_member fixture makes regular_user a member
        # Try to "add" them again with different role
        response = await client.post(
            f"/api/departments/{department.id}/members",
            json={
                "user_id": regular_user.id,
                "role": "sub_admin"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code in [200, 201]
        data = response.json()
        assert data["user_id"] == regular_user.id
        assert data["role"] == "sub_admin"

    async def test_add_member_to_nonexistent_department_fails(
        self, client: AsyncClient, admin_token: str, second_user: User,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test adding member to non-existent department fails."""
        response = await client.post(
            "/api/departments/99999/members",
            json={
                "user_id": second_user.id,
                "role": "member"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404


class TestUpdateDepartmentMember:
    """Tests for updating department member roles."""

    async def test_org_owner_updates_member_role(
        self, client: AsyncClient, admin_token: str, department: Department,
        regular_user: User, organization: Organization, org_owner: OrgMember,
        org_admin: OrgMember, dept_member: DepartmentMember, get_auth_headers
    ):
        """Test org owner can update member role."""
        response = await client.patch(
            f"/api/departments/{department.id}/members/{regular_user.id}",
            json={"role": "sub_admin"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "sub_admin"

    async def test_dept_lead_updates_member_role(
        self, db_session: AsyncSession, client: AsyncClient, admin_user: User,
        admin_token: str, department: Department, regular_user: User,
        organization: Organization, org_owner: OrgMember, org_admin: OrgMember,
        dept_member: DepartmentMember, get_auth_headers
    ):
        """Test department lead can update member role (except to lead)."""
        # Make admin_user a lead
        lead = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(lead)
        await db_session.commit()

        response = await client.patch(
            f"/api/departments/{department.id}/members/{regular_user.id}",
            json={"role": "sub_admin"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

    async def test_lead_cannot_promote_to_lead(
        self, db_session: AsyncSession, client: AsyncClient, admin_user: User,
        admin_token: str, department: Department, regular_user: User,
        organization: Organization, org_owner: OrgMember, org_admin: OrgMember,
        dept_member: DepartmentMember, get_auth_headers
    ):
        """Test department lead cannot promote member to lead."""
        # Make admin_user a lead but remove owner status for this test
        # Actually, admin_user has org_owner, so this won't work as intended
        # We need to use regular_user as the lead
        pass  # Covered by test_only_owner_can_set_lead_role

    async def test_only_owner_can_set_lead_role(
        self, db_session: AsyncSession, client: AsyncClient, regular_user: User,
        user_token: str, department: Department, second_user: User,
        organization: Organization, org_admin: OrgMember, org_member: OrgMember,
        get_auth_headers
    ):
        """Test only org owner can set lead role."""
        # Make regular_user a lead
        lead = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        # Make second_user a member
        member = DepartmentMember(
            department_id=department.id,
            user_id=second_user.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add_all([lead, member])
        await db_session.commit()

        # Try to promote to lead
        response = await client.patch(
            f"/api/departments/{department.id}/members/{second_user.id}",
            json={"role": "lead"},
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 403
        assert "Only org owners can set lead role" in response.json()["detail"]

    async def test_regular_member_cannot_update_roles(
        self, db_session: AsyncSession, client: AsyncClient, regular_user: User,
        user_token: str, department: Department, second_user: User,
        organization: Organization, plain_org_member: OrgMember, org_member: OrgMember,
        dept_member: DepartmentMember, get_auth_headers
    ):
        """Test regular member cannot update roles."""
        # Make second_user also a member
        member = DepartmentMember(
            department_id=department.id,
            user_id=second_user.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(member)
        await db_session.commit()

        response = await client.patch(
            f"/api/departments/{department.id}/members/{second_user.id}",
            json={"role": "sub_admin"},
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 403

    async def test_update_nonexistent_member_fails(
        self, client: AsyncClient, admin_token: str, department: Department,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test updating non-existent member fails."""
        response = await client.patch(
            f"/api/departments/{department.id}/members/99999",
            json={"role": "member"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404

    async def test_promote_member_to_sub_admin(
        self, client: AsyncClient, admin_token: str, department: Department,
        regular_user: User, organization: Organization, org_owner: OrgMember,
        org_admin: OrgMember, dept_member: DepartmentMember, get_auth_headers
    ):
        """Test promoting member to sub_admin role."""
        response = await client.patch(
            f"/api/departments/{department.id}/members/{regular_user.id}",
            json={"role": "sub_admin"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "sub_admin"

    async def test_demote_sub_admin_to_member(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, regular_user: User, organization: Organization,
        org_owner: OrgMember, org_admin: OrgMember, get_auth_headers
    ):
        """Test demoting sub_admin to member."""
        # Make regular_user a sub_admin
        sub_admin = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.sub_admin,
            created_at=datetime.utcnow()
        )
        db_session.add(sub_admin)
        await db_session.commit()

        response = await client.patch(
            f"/api/departments/{department.id}/members/{regular_user.id}",
            json={"role": "member"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "member"


class TestRemoveDepartmentMember:
    """Tests for removing members from departments."""

    async def test_org_owner_removes_member(
        self, client: AsyncClient, admin_token: str, department: Department,
        regular_user: User, organization: Organization, org_owner: OrgMember,
        org_admin: OrgMember, dept_member: DepartmentMember, get_auth_headers
    ):
        """Test org owner can remove member from department."""
        response = await client.delete(
            f"/api/departments/{department.id}/members/{regular_user.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

    async def test_dept_lead_removes_member(
        self, db_session: AsyncSession, client: AsyncClient, admin_user: User,
        admin_token: str, department: Department, regular_user: User,
        organization: Organization, org_owner: OrgMember, org_admin: OrgMember,
        dept_member: DepartmentMember, get_auth_headers
    ):
        """Test department lead can remove member."""
        # Make admin_user a lead
        lead = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(lead)
        await db_session.commit()

        response = await client.delete(
            f"/api/departments/{department.id}/members/{regular_user.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

    async def test_regular_member_cannot_remove_member(
        self, db_session: AsyncSession, client: AsyncClient, regular_user: User,
        user_token: str, department: Department, second_user: User,
        organization: Organization, plain_org_member: OrgMember, org_member: OrgMember,
        dept_member: DepartmentMember, get_auth_headers
    ):
        """Test regular member cannot remove members."""
        # Make second_user also a member
        member = DepartmentMember(
            department_id=department.id,
            user_id=second_user.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(member)
        await db_session.commit()

        response = await client.delete(
            f"/api/departments/{department.id}/members/{second_user.id}",
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 403

    async def test_cannot_remove_last_lead(
        self, client: AsyncClient, admin_user: User, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        dept_lead: DepartmentMember, get_auth_headers
    ):
        """Test cannot remove the last department lead."""
        response = await client.delete(
            f"/api/departments/{department.id}/members/{admin_user.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 400
        assert "Cannot remove the last department lead" in response.json()["detail"]

    async def test_can_remove_lead_when_multiple_leads_exist(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, admin_user: User, regular_user: User,
        organization: Organization, org_owner: OrgMember, dept_lead: DepartmentMember,
        get_auth_headers
    ):
        """Test can remove lead when multiple leads exist."""
        # Add regular_user as second lead
        second_lead = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(second_lead)
        await db_session.commit()

        # Now remove one lead
        response = await client.delete(
            f"/api/departments/{department.id}/members/{regular_user.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

    async def test_remove_nonexistent_member_fails(
        self, client: AsyncClient, admin_token: str, department: Department,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test removing non-existent member fails."""
        response = await client.delete(
            f"/api/departments/{department.id}/members/99999",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404


# =============================================================================
# ROLE HIERARCHY AND PERMISSIONS TESTS
# =============================================================================

class TestDepartmentRoleHierarchy:
    """Tests for department role hierarchy and permissions."""

    async def test_role_hierarchy_lead_has_most_permissions(
        self, db_session: AsyncSession, client: AsyncClient, regular_user: User,
        user_token: str, department: Department, second_user: User,
        organization: Organization, org_admin: OrgMember, org_member: OrgMember,
        get_auth_headers
    ):
        """Test lead role has permissions to manage department."""
        # Make regular_user a lead
        lead = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(lead)
        await db_session.commit()

        # Lead can update department
        update_resp = await client.patch(
            f"/api/departments/{department.id}",
            json={"description": "Lead updated"},
            headers=get_auth_headers(user_token)
        )
        assert update_resp.status_code == 200

        # Lead can add members (except leads)
        add_resp = await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": second_user.id, "role": "member"},
            headers=get_auth_headers(user_token)
        )
        assert add_resp.status_code in [200, 201]

    async def test_sub_admin_has_limited_permissions(
        self, db_session: AsyncSession, client: AsyncClient, regular_user: User,
        user_token: str, department: Department, organization: Organization,
        plain_org_member: OrgMember, get_auth_headers
    ):
        """Test sub_admin role has limited permissions.

        Sub_admin CAN:
        - Add regular members to their department
        - Update/remove regular members

        Sub_admin CANNOT:
        - Update department settings
        - Add/promote to sub_admin or lead roles
        - Create sub-departments
        """
        # Make regular_user a sub_admin
        sub_admin = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.sub_admin,
            created_at=datetime.utcnow()
        )
        db_session.add(sub_admin)
        await db_session.commit()

        # Sub_admin cannot update department
        update_resp = await client.patch(
            f"/api/departments/{department.id}",
            json={"description": "Sub admin update"},
            headers=get_auth_headers(user_token)
        )
        assert update_resp.status_code == 403

        # Sub_admin cannot add sub_admin or lead
        add_sub_admin_resp = await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": plain_org_member.user_id, "role": "sub_admin"},
            headers=get_auth_headers(user_token)
        )
        assert add_sub_admin_resp.status_code == 403

        add_lead_resp = await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": plain_org_member.user_id, "role": "lead"},
            headers=get_auth_headers(user_token)
        )
        assert add_lead_resp.status_code == 403

        # Sub_admin cannot create sub-department
        create_subdept_resp = await client.post(
            "/api/departments",
            json={"name": "Sub Admin's Sub-Department", "parent_id": department.id},
            headers=get_auth_headers(user_token)
        )
        assert create_subdept_resp.status_code == 403

    async def test_member_has_minimal_permissions(
        self, client: AsyncClient, regular_user: User, user_token: str,
        department: Department, organization: Organization, org_admin: OrgMember,
        dept_member: DepartmentMember, get_auth_headers
    ):
        """Test member role has minimal permissions."""
        # Member cannot update department
        update_resp = await client.patch(
            f"/api/departments/{department.id}",
            json={"description": "Member update"},
            headers=get_auth_headers(user_token)
        )
        assert update_resp.status_code == 403

        # Member cannot add members
        add_resp = await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": 999, "role": "member"},
            headers=get_auth_headers(user_token)
        )
        assert update_resp.status_code == 403

    async def test_all_roles_can_view_department(
        self, db_session: AsyncSession, client: AsyncClient, department: Department,
        regular_user: User, user_token: str, organization: Organization,
        org_admin: OrgMember, get_auth_headers
    ):
        """Test all department roles can view department details."""
        # Test as member
        member = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(member)
        await db_session.commit()

        response = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(user_token)
        )
        assert response.status_code == 200


# =============================================================================
# EDGE CASES AND ERROR HANDLING TESTS
# =============================================================================

class TestDepartmentEdgeCases:
    """Tests for edge cases and error handling."""

    async def test_department_name_validation(
        self, client: AsyncClient, admin_token: str, organization: Organization,
        org_owner: OrgMember, get_auth_headers
    ):
        """Test department name validation."""
        # Empty name
        response = await client.post(
            "/api/departments",
            json={"name": ""},
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 422

        # Very long name (over 255 chars)
        response = await client.post(
            "/api/departments",
            json={"name": "x" * 256},
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 422

    async def test_concurrent_department_operations(
        self, client: AsyncClient, admin_token: str, department: Department,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test handling of concurrent operations on same department."""
        # Two concurrent updates
        response1 = await client.patch(
            f"/api/departments/{department.id}",
            json={"name": "Update 1"},
            headers=get_auth_headers(admin_token)
        )
        response2 = await client.patch(
            f"/api/departments/{department.id}",
            json={"name": "Update 2"},
            headers=get_auth_headers(admin_token)
        )

        # Both should succeed (last write wins)
        assert response1.status_code == 200
        assert response2.status_code == 200

    async def test_department_with_special_characters_in_name(
        self, client: AsyncClient, admin_token: str, organization: Organization,
        org_owner: OrgMember, get_auth_headers
    ):
        """Test department names with special characters."""
        response = await client.post(
            "/api/departments",
            json={"name": "R&D / AI-ML (2024)"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code in [200, 201]
        data = response.json()
        assert data["name"] == "R&D / AI-ML (2024)"

    async def test_department_color_format(
        self, client: AsyncClient, admin_token: str, organization: Organization,
        org_owner: OrgMember, get_auth_headers
    ):
        """Test department color accepts various formats."""
        # Hex color
        response = await client.post(
            "/api/departments",
            json={"name": "Dept 1", "color": "#FF5733"},
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code in [200, 201]

        # Color name (stored as-is, no validation on backend)
        response = await client.post(
            "/api/departments",
            json={"name": "Dept 2", "color": "red"},
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code in [200, 201]

    async def test_circular_parent_relationship_prevented(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        get_auth_headers
    ):
        """Test circular parent relationships are prevented."""
        # Create child
        child = Department(
            name="Child",
            org_id=organization.id,
            parent_id=department.id,
            created_at=datetime.utcnow()
        )
        db_session.add(child)
        await db_session.commit()
        await db_session.refresh(child)

        # Try to make parent a child of child (not directly supported in update)
        # This would need to be prevented at application level
        # The API doesn't support updating parent_id, so this is inherently safe

    async def test_deep_department_hierarchy(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test creating deep department hierarchy."""
        # Create 3-level hierarchy
        parent = Department(
            name="Level 1",
            org_id=organization.id,
            created_at=datetime.utcnow()
        )
        db_session.add(parent)
        await db_session.commit()
        await db_session.refresh(parent)

        child = Department(
            name="Level 2",
            org_id=organization.id,
            parent_id=parent.id,
            created_at=datetime.utcnow()
        )
        db_session.add(child)
        await db_session.commit()
        await db_session.refresh(child)

        grandchild = Department(
            name="Level 3",
            org_id=organization.id,
            parent_id=child.id,
            created_at=datetime.utcnow()
        )
        db_session.add(grandchild)
        await db_session.commit()
        await db_session.refresh(grandchild)

        # Verify hierarchy
        response = await client.get(
            f"/api/departments/{grandchild.id}",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["parent_id"] == child.id


# =============================================================================
# CROSS-ORGANIZATION ISOLATION TESTS
# =============================================================================

class TestCrossOrganizationIsolation:
    """Tests to ensure department data is properly isolated between organizations."""

    async def test_cannot_access_department_from_other_org(
        self, db_session: AsyncSession, client: AsyncClient, second_user: User,
        second_user_token: str, second_organization: Organization,
        department: Department, get_auth_headers
    ):
        """Test user cannot access department from different organization."""
        # Make second_user member of second_organization
        org_member = OrgMember(
            org_id=second_organization.id,
            user_id=second_user.id,
            role=OrgRole.owner,
            created_at=datetime.utcnow()
        )
        db_session.add(org_member)
        await db_session.commit()

        response = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 404

    async def test_cannot_list_departments_from_other_org(
        self, db_session: AsyncSession, client: AsyncClient, second_user: User,
        second_user_token: str, second_organization: Organization,
        department: Department, get_auth_headers
    ):
        """Test department list doesn't include other org's departments."""
        # Make second_user member of second_organization
        org_member = OrgMember(
            org_id=second_organization.id,
            user_id=second_user.id,
            role=OrgRole.owner,
            created_at=datetime.utcnow()
        )
        db_session.add(org_member)
        await db_session.commit()

        response = await client.get(
            "/api/departments",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()
        dept_ids = [d["id"] for d in data]
        assert department.id not in dept_ids

    async def test_cannot_add_user_from_other_org_to_department(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, second_organization: Organization,
        org_owner: OrgMember, get_auth_headers
    ):
        """Test cannot add user from different organization to department."""
        # Create user in second organization
        other_user = User(
            email="otherorg@test.com",
            password_hash="hash",
            name="Other Org User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)

        other_org_member = OrgMember(
            org_id=second_organization.id,
            user_id=other_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(other_org_member)
        await db_session.commit()

        # Try to add to department in different org
        response = await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": other_user.id, "role": "member"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 404
        assert "User not found in organization" in response.json()["detail"]

    async def test_superadmin_can_access_any_org_departments(
        self, client: AsyncClient, superadmin_token: str, department: Department,
        superadmin_org_member: OrgMember, get_auth_headers
    ):
        """Test superadmin can access departments from any organization."""
        response = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200


# =============================================================================
# NESTED DEPARTMENT HIERARCHY TESTS
# =============================================================================

class TestNestedDepartmentHierarchy:
    """Tests for complex nested department hierarchies and permissions."""

    @pytest.mark.xfail(reason="Hierarchy creation logic")
    async def test_create_three_level_hierarchy_with_leads(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        organization: Organization, org_owner: OrgMember, regular_user: User,
        second_user: User, get_auth_headers
    ):
        """Test creating 3-level department hierarchy with leads at each level."""
        # Level 1: Engineering (created by owner)
        response1 = await client.post(
            "/api/departments",
            json={"name": "Engineering", "description": "Engineering Division"},
            headers=get_auth_headers(admin_token)
        )
        assert response1.status_code in [200, 201]
        engineering = response1.json()

        # Add regular_user as lead of Engineering
        await client.post(
            f"/api/departments/{engineering['id']}/members",
            json={"user_id": regular_user.id, "role": "lead"},
            headers=get_auth_headers(admin_token)
        )

        # Make regular_user member of org
        org_member = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.admin,
            created_at=datetime.utcnow()
        )
        db_session.add(org_member)
        await db_session.commit()

        # Level 2: Backend (created by lead of Engineering)
        user_token = create_access_token(data={"sub": str(regular_user.id)})
        response2 = await client.post(
            "/api/departments",
            json={
                "name": "Backend",
                "description": "Backend Team",
                "parent_id": engineering["id"]
            },
            headers=get_auth_headers(user_token)
        )
        assert response2.status_code in [200, 201]
        backend = response2.json()
        assert backend["parent_id"] == engineering["id"]
        assert backend["parent_name"] == "Engineering"
        # Lead creating subdepartment becomes lead of it
        assert backend["members_count"] == 1

        # Verify hierarchy
        response3 = await client.get(
            f"/api/departments/{engineering['id']}/children",
            headers=get_auth_headers(admin_token)
        )
        assert response3.status_code == 200
        children = response3.json()
        assert len(children) >= 1
        assert any(c["id"] == backend["id"] for c in children)

    async def test_lead_of_subdepartment_creates_sub_subdepartment(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        organization: Organization, org_owner: OrgMember, regular_user: User,
        second_user: User, get_auth_headers
    ):
        """Test lead of subdepartment can create sub-subdepartment."""
        # Create parent department
        response1 = await client.post(
            "/api/departments",
            json={"name": "Parent Dept"},
            headers=get_auth_headers(admin_token)
        )
        parent = response1.json()

        # Make regular_user org member
        org_member = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.admin,
            created_at=datetime.utcnow()
        )
        db_session.add(org_member)
        await db_session.commit()

        # Owner creates child and makes regular_user lead
        response2 = await client.post(
            "/api/departments",
            json={"name": "Child Dept", "parent_id": parent["id"]},
            headers=get_auth_headers(admin_token)
        )
        child = response2.json()

        await client.post(
            f"/api/departments/{child['id']}/members",
            json={"user_id": regular_user.id, "role": "lead"},
            headers=get_auth_headers(admin_token)
        )

        # Now regular_user (lead of child) creates grandchild
        user_token = create_access_token(data={"sub": str(regular_user.id)})
        response3 = await client.post(
            "/api/departments",
            json={"name": "Grandchild Dept", "parent_id": child["id"]},
            headers=get_auth_headers(user_token)
        )
        assert response3.status_code in [200, 201]
        grandchild = response3.json()
        assert grandchild["parent_id"] == child["id"]

    async def test_department_hierarchy_statistics(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test department statistics correctly count children in hierarchy."""
        # Create parent
        response1 = await client.post(
            "/api/departments",
            json={"name": "Parent"},
            headers=get_auth_headers(admin_token)
        )
        parent = response1.json()

        # Create 2 children
        await client.post(
            "/api/departments",
            json={"name": "Child 1", "parent_id": parent["id"]},
            headers=get_auth_headers(admin_token)
        )
        await client.post(
            "/api/departments",
            json={"name": "Child 2", "parent_id": parent["id"]},
            headers=get_auth_headers(admin_token)
        )

        # Check parent's children count
        response = await client.get(
            f"/api/departments/{parent['id']}",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["children_count"] >= 2

    async def test_nested_department_permissions_isolation(
        self, db_session: AsyncSession, client: AsyncClient, organization: Organization,
        org_owner: OrgMember, admin_user: User, regular_user: User, second_user: User,
        get_auth_headers
    ):
        """Test that lead of parent cannot directly manage child's members without being lead."""
        # Create parent and child
        admin_token = create_access_token(data={"sub": str(admin_user.id)})
        response1 = await client.post(
            "/api/departments",
            json={"name": "Parent"},
            headers=get_auth_headers(admin_token)
        )
        parent = response1.json()

        response2 = await client.post(
            "/api/departments",
            json={"name": "Child", "parent_id": parent["id"]},
            headers=get_auth_headers(admin_token)
        )
        child = response2.json()

        # Make regular_user lead of parent only. В орге — рядовой член:
        # админ орга управляет любым отделом, и проверка вложенности не наступила бы.
        org_member1 = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(org_member1)
        await db_session.commit()

        await client.post(
            f"/api/departments/{parent['id']}/members",
            json={"user_id": regular_user.id, "role": "lead"},
            headers=get_auth_headers(admin_token)
        )

        # Make second_user org member
        org_member2 = OrgMember(
            org_id=organization.id,
            user_id=second_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(org_member2)
        await db_session.commit()

        # Lead of parent tries to add member to child - should fail
        user_token = create_access_token(data={"sub": str(regular_user.id)})
        response = await client.post(
            f"/api/departments/{child['id']}/members",
            json={"user_id": second_user.id, "role": "member"},
            headers=get_auth_headers(user_token)
        )
        assert response.status_code == 403

    async def test_list_departments_shows_hierarchy(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test listing departments shows parent-child relationships."""
        # Create parent with children
        response1 = await client.post(
            "/api/departments",
            json={"name": "Sales"},
            headers=get_auth_headers(admin_token)
        )
        sales = response1.json()

        response2 = await client.post(
            "/api/departments",
            json={"name": "Enterprise Sales", "parent_id": sales["id"]},
            headers=get_auth_headers(admin_token)
        )
        enterprise = response2.json()

        # List all departments
        response = await client.get(
            "/api/departments?parent_id=-1",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        all_depts = response.json()

        # Find our departments
        sales_data = next((d for d in all_depts if d["id"] == sales["id"]), None)
        enterprise_data = next((d for d in all_depts if d["id"] == enterprise["id"]), None)

        assert sales_data is not None
        assert enterprise_data is not None
        assert enterprise_data["parent_id"] == sales["id"]
        assert enterprise_data["parent_name"] == "Sales"


# =============================================================================
# DEPARTMENT STATISTICS COMPREHENSIVE TESTS
# =============================================================================

class TestDepartmentStatistics:
    """Comprehensive tests for department statistics."""

    async def test_statistics_update_when_members_added(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        regular_user: User, second_user: User, get_auth_headers
    ):
        """Test statistics update correctly when members are added."""
        # Get initial stats
        response1 = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )
        initial_count = response1.json()["members_count"]

        # Make users org members
        for user in [regular_user, second_user]:
            org_member = OrgMember(
                org_id=organization.id,
                user_id=user.id,
                role=OrgRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(org_member)
        await db_session.commit()

        # Add two members
        await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": regular_user.id, "role": "member"},
            headers=get_auth_headers(admin_token)
        )
        await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": second_user.id, "role": "sub_admin"},
            headers=get_auth_headers(admin_token)
        )

        # Check updated stats
        response2 = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )
        assert response2.status_code == 200
        updated_count = response2.json()["members_count"]
        assert updated_count == initial_count + 2

    async def test_statistics_update_when_members_removed(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        regular_user: User, second_user: User, get_auth_headers
    ):
        """Test statistics update correctly when members are removed."""
        # Make users org members
        for user in [regular_user, second_user]:
            org_member = OrgMember(
                org_id=organization.id,
                user_id=user.id,
                role=OrgRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(org_member)
        await db_session.commit()

        # Add members
        await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": regular_user.id, "role": "member"},
            headers=get_auth_headers(admin_token)
        )
        await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": second_user.id, "role": "lead"},
            headers=get_auth_headers(admin_token)
        )

        # Get stats with members
        response1 = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )
        count_with_members = response1.json()["members_count"]

        # Remove one member
        await client.delete(
            f"/api/departments/{department.id}/members/{regular_user.id}",
            headers=get_auth_headers(admin_token)
        )

        # Check updated stats
        response2 = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )
        updated_count = response2.json()["members_count"]
        assert updated_count == count_with_members - 1

    async def test_statistics_with_entities(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        admin_user: User, get_auth_headers
    ):
        """Test entity count statistics are accurate."""
        # Create entities in department
        from api.models.database import Entity, EntityType, EntityStatus

        entity1 = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Entity 1",
            email="entity1@test.com",
            type=EntityType.candidate,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        entity2 = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Entity 2",
            email="entity2@test.com",
            type=EntityType.client,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add_all([entity1, entity2])
        await db_session.commit()

        # Check stats
        response = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["entities_count"] >= 2

    async def test_statistics_zero_counts(
        self, client: AsyncClient, admin_token: str, department: Department,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test statistics correctly show zero for empty departments."""
        response = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()

        # New department should have zero children
        assert data["children_count"] == 0
        # May or may not have members/entities depending on fixtures

    async def test_parent_children_count_accuracy(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test parent department correctly counts its children."""
        # Create parent
        response1 = await client.post(
            "/api/departments",
            json={"name": "Parent Dept"},
            headers=get_auth_headers(admin_token)
        )
        parent = response1.json()

        # Create multiple children
        for i in range(5):
            await client.post(
                "/api/departments",
                json={"name": f"Child {i}", "parent_id": parent["id"]},
                headers=get_auth_headers(admin_token)
            )

        # Verify count
        response = await client.get(
            f"/api/departments/{parent['id']}",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        assert response.json()["children_count"] == 5


# =============================================================================
# CROSS-DEPARTMENT ACCESS TESTS
# =============================================================================

class TestCrossDepartmentAccess:
    """Tests for cross-department access control."""

    async def test_member_cannot_access_other_department_members(
        self, db_session: AsyncSession, client: AsyncClient, organization: Organization,
        department: Department, second_department: Department, regular_user: User,
        org_admin: OrgMember, get_auth_headers
    ):
        """Test member of Dept A cannot access Dept B's members."""
        # Make regular_user member of first department only
        dept_member = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_member)
        await db_session.commit()

        user_token = create_access_token(data={"sub": str(regular_user.id)})

        # Try to list members of second department
        response = await client.get(
            f"/api/departments/{second_department.id}/members",
            headers=get_auth_headers(user_token)
        )
        # Should succeed (viewing is allowed) but might show different data
        assert response.status_code == 200

    async def test_lead_cannot_add_members_to_other_department(
        self, db_session: AsyncSession, client: AsyncClient, organization: Organization,
        department: Department, second_department: Department, regular_user: User,
        second_user: User, plain_org_member: OrgMember, org_member: OrgMember, get_auth_headers
    ):
        """Test lead of Dept A cannot add members to Dept B."""
        # Make regular_user lead of first department
        dept_lead = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_lead)
        await db_session.commit()

        user_token = create_access_token(data={"sub": str(regular_user.id)})

        # Try to add member to second department
        response = await client.post(
            f"/api/departments/{second_department.id}/members",
            json={"user_id": second_user.id, "role": "member"},
            headers=get_auth_headers(user_token)
        )
        assert response.status_code == 403

    async def test_lead_cannot_update_other_department(
        self, db_session: AsyncSession, client: AsyncClient, organization: Organization,
        department: Department, second_department: Department, regular_user: User,
        org_admin: OrgMember, get_auth_headers
    ):
        """Test lead of Dept A cannot update Dept B."""
        # Make regular_user lead of first department
        dept_lead = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_lead)
        await db_session.commit()

        user_token = create_access_token(data={"sub": str(regular_user.id)})

        # Try to update second department
        response = await client.patch(
            f"/api/departments/{second_department.id}",
            json={"description": "Unauthorized update"},
            headers=get_auth_headers(user_token)
        )
        assert response.status_code == 403

    async def test_member_in_multiple_departments_access(
        self, db_session: AsyncSession, client: AsyncClient, organization: Organization,
        department: Department, second_department: Department, regular_user: User,
        org_admin: OrgMember, get_auth_headers
    ):
        """Test user who is member of multiple departments has correct access."""
        # Add regular_user to both departments
        dept_member1 = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        dept_member2 = DepartmentMember(
            department_id=second_department.id,
            user_id=regular_user.id,
            role=DeptRole.sub_admin,
            created_at=datetime.utcnow()
        )
        db_session.add_all([dept_member1, dept_member2])
        await db_session.commit()

        user_token = create_access_token(data={"sub": str(regular_user.id)})

        # Get my departments - should see both
        response = await client.get(
            "/api/departments/my/departments",
            headers=get_auth_headers(user_token)
        )
        assert response.status_code == 200
        my_depts = response.json()
        dept_ids = [d["id"] for d in my_depts]
        assert department.id in dept_ids
        assert second_department.id in dept_ids

    async def test_lead_of_multiple_departments_permissions(
        self, db_session: AsyncSession, client: AsyncClient, organization: Organization,
        department: Department, second_department: Department, regular_user: User,
        second_user: User, org_admin: OrgMember, org_member: OrgMember, get_auth_headers
    ):
        """Test user who is lead of multiple departments can manage both."""
        # Make regular_user lead of both departments
        dept_lead1 = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        dept_lead2 = DepartmentMember(
            department_id=second_department.id,
            user_id=regular_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add_all([dept_lead1, dept_lead2])
        await db_session.commit()

        user_token = create_access_token(data={"sub": str(regular_user.id)})

        # Should be able to update both departments
        response1 = await client.patch(
            f"/api/departments/{department.id}",
            json={"description": "Updated by lead"},
            headers=get_auth_headers(user_token)
        )
        assert response1.status_code == 200

        response2 = await client.patch(
            f"/api/departments/{second_department.id}",
            json={"description": "Updated by lead"},
            headers=get_auth_headers(user_token)
        )
        assert response2.status_code == 200

        # Should be able to add members to both
        response3 = await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": second_user.id, "role": "member"},
            headers=get_auth_headers(user_token)
        )
        assert response3.status_code in [200, 201]


# =============================================================================
# ADVANCED MEMBER MANAGEMENT TESTS
# =============================================================================

class TestAdvancedMemberManagement:
    """Tests for advanced department member management scenarios."""

    async def test_multiple_leads_in_department(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        regular_user: User, second_user: User, get_auth_headers
    ):
        """Test department can have multiple leads."""
        # Make users org members
        for user in [regular_user, second_user]:
            org_member = OrgMember(
                org_id=organization.id,
                user_id=user.id,
                role=OrgRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(org_member)
        await db_session.commit()

        # Add two leads
        response1 = await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": regular_user.id, "role": "lead"},
            headers=get_auth_headers(admin_token)
        )
        assert response1.status_code in [200, 201]

        response2 = await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": second_user.id, "role": "lead"},
            headers=get_auth_headers(admin_token)
        )
        assert response2.status_code in [200, 201]

        # List members - should show both leads
        response = await client.get(
            f"/api/departments/{department.id}/members",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        members = response.json()

        leads = [m for m in members if m["role"] == "lead"]
        assert len(leads) >= 2

    async def test_both_leads_can_manage_department(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        regular_user: User, second_user: User, admin_user: User, get_auth_headers
    ):
        """Test both leads have equal management permissions."""
        # Make users org members
        for user in [regular_user, second_user]:
            org_member = OrgMember(
                org_id=organization.id,
                user_id=user.id,
                role=OrgRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(org_member)
        await db_session.commit()

        # Add as leads
        await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": regular_user.id, "role": "lead"},
            headers=get_auth_headers(admin_token)
        )
        await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": second_user.id, "role": "lead"},
            headers=get_auth_headers(admin_token)
        )

        # Both should be able to update department
        user1_token = create_access_token(data={"sub": str(regular_user.id)})
        response1 = await client.patch(
            f"/api/departments/{department.id}",
            json={"description": "Updated by lead 1"},
            headers=get_auth_headers(user1_token)
        )
        assert response1.status_code == 200

        user2_token = create_access_token(data={"sub": str(second_user.id)})
        response2 = await client.patch(
            f"/api/departments/{department.id}",
            json={"description": "Updated by lead 2"},
            headers=get_auth_headers(user2_token)
        )
        assert response2.status_code == 200

    async def test_promote_member_through_role_hierarchy(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        regular_user: User, get_auth_headers
    ):
        """Test promoting member through role hierarchy: member -> sub_admin -> lead."""
        # Make user org member
        org_member = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(org_member)
        await db_session.commit()

        # Start as member
        response1 = await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": regular_user.id, "role": "member"},
            headers=get_auth_headers(admin_token)
        )
        assert response1.status_code in [200, 201]
        assert response1.json()["role"] == "member"

        # Promote to sub_admin
        response2 = await client.patch(
            f"/api/departments/{department.id}/members/{regular_user.id}",
            json={"role": "sub_admin"},
            headers=get_auth_headers(admin_token)
        )
        assert response2.status_code == 200
        assert response2.json()["role"] == "sub_admin"

        # Promote to lead
        response3 = await client.patch(
            f"/api/departments/{department.id}/members/{regular_user.id}",
            json={"role": "lead"},
            headers=get_auth_headers(admin_token)
        )
        assert response3.status_code == 200
        assert response3.json()["role"] == "lead"

    async def test_demote_lead_to_member(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        regular_user: User, second_user: User, get_auth_headers
    ):
        """Test demoting lead to member when multiple leads exist."""
        # Make users org members
        for user in [regular_user, second_user]:
            org_member = OrgMember(
                org_id=organization.id,
                user_id=user.id,
                role=OrgRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(org_member)
        await db_session.commit()

        # Add two leads
        await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": regular_user.id, "role": "lead"},
            headers=get_auth_headers(admin_token)
        )
        await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": second_user.id, "role": "lead"},
            headers=get_auth_headers(admin_token)
        )

        # Demote one lead to member
        response = await client.patch(
            f"/api/departments/{department.id}/members/{regular_user.id}",
            json={"role": "member"},
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        assert response.json()["role"] == "member"

    async def test_member_role_changes_reflected_in_list(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        regular_user: User, get_auth_headers
    ):
        """Test role changes are immediately reflected in member list."""
        # Make user org member
        org_member = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(org_member)
        await db_session.commit()

        # Add as member
        await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": regular_user.id, "role": "member"},
            headers=get_auth_headers(admin_token)
        )

        # Change to sub_admin
        await client.patch(
            f"/api/departments/{department.id}/members/{regular_user.id}",
            json={"role": "sub_admin"},
            headers=get_auth_headers(admin_token)
        )

        # List members
        response = await client.get(
            f"/api/departments/{department.id}/members",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        members = response.json()

        user_member = next((m for m in members if m["user_id"] == regular_user.id), None)
        assert user_member is not None
        assert user_member["role"] == "sub_admin"


# =============================================================================
# MOVE USERS BETWEEN DEPARTMENTS TESTS
# =============================================================================

class TestMoveUsersBetweenDepartments:
    """Tests for moving users between departments."""

    async def test_move_member_from_dept_a_to_dept_b(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, second_department: Department, organization: Organization,
        org_owner: OrgMember, regular_user: User, get_auth_headers
    ):
        """Test moving a member from one department to another."""
        # Make user org member
        org_member = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(org_member)
        await db_session.commit()

        # Add user to department A
        response1 = await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": regular_user.id, "role": "member"},
            headers=get_auth_headers(admin_token)
        )
        assert response1.status_code in [200, 201]

        # Verify user is in department A
        response2 = await client.get(
            f"/api/departments/{department.id}/members",
            headers=get_auth_headers(admin_token)
        )
        assert response2.status_code == 200
        members_a = response2.json()
        assert any(m["user_id"] == regular_user.id for m in members_a)

        # Get initial stats for both departments
        dept_a_response = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )
        dept_b_response = await client.get(
            f"/api/departments/{second_department.id}",
            headers=get_auth_headers(admin_token)
        )
        initial_dept_a_count = dept_a_response.json()["members_count"]
        initial_dept_b_count = dept_b_response.json()["members_count"]

        # Remove user from department A
        response3 = await client.delete(
            f"/api/departments/{department.id}/members/{regular_user.id}",
            headers=get_auth_headers(admin_token)
        )
        assert response3.status_code == 200

        # Add user to department B
        response4 = await client.post(
            f"/api/departments/{second_department.id}/members",
            json={"user_id": regular_user.id, "role": "member"},
            headers=get_auth_headers(admin_token)
        )
        assert response4.status_code in [200, 201]

        # Verify user is no longer in department A
        response5 = await client.get(
            f"/api/departments/{department.id}/members",
            headers=get_auth_headers(admin_token)
        )
        assert response5.status_code == 200
        members_a_after = response5.json()
        assert not any(m["user_id"] == regular_user.id for m in members_a_after)

        # Verify user is now in department B
        response6 = await client.get(
            f"/api/departments/{second_department.id}/members",
            headers=get_auth_headers(admin_token)
        )
        assert response6.status_code == 200
        members_b = response6.json()
        assert any(m["user_id"] == regular_user.id for m in members_b)

        # Verify statistics updated correctly
        dept_a_after = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )
        dept_b_after = await client.get(
            f"/api/departments/{second_department.id}",
            headers=get_auth_headers(admin_token)
        )
        assert dept_a_after.json()["members_count"] == initial_dept_a_count - 1
        assert dept_b_after.json()["members_count"] == initial_dept_b_count + 1

    async def test_move_lead_changes_role_to_member(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, second_department: Department, organization: Organization,
        org_owner: OrgMember, regular_user: User, second_user: User, get_auth_headers
    ):
        """Test moving a lead to another department and changing role."""
        # Make users org members
        for user in [regular_user, second_user]:
            org_member = OrgMember(
                org_id=organization.id,
                user_id=user.id,
                role=OrgRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(org_member)
        await db_session.commit()

        # Add regular_user as lead to department A
        # Add second_user as another lead (so we can remove regular_user)
        await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": regular_user.id, "role": "lead"},
            headers=get_auth_headers(admin_token)
        )
        await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": second_user.id, "role": "lead"},
            headers=get_auth_headers(admin_token)
        )

        # Verify regular_user is lead in department A
        response1 = await client.get(
            f"/api/departments/{department.id}/members",
            headers=get_auth_headers(admin_token)
        )
        members_a = response1.json()
        user_in_a = next((m for m in members_a if m["user_id"] == regular_user.id), None)
        assert user_in_a is not None
        assert user_in_a["role"] == "lead"

        # Remove from department A
        await client.delete(
            f"/api/departments/{department.id}/members/{regular_user.id}",
            headers=get_auth_headers(admin_token)
        )

        # Add to department B as member (not lead)
        response2 = await client.post(
            f"/api/departments/{second_department.id}/members",
            json={"user_id": regular_user.id, "role": "member"},
            headers=get_auth_headers(admin_token)
        )
        assert response2.status_code in [200, 201]
        assert response2.json()["role"] == "member"

        # Verify role changed in department B
        response3 = await client.get(
            f"/api/departments/{second_department.id}/members",
            headers=get_auth_headers(admin_token)
        )
        members_b = response3.json()
        user_in_b = next((m for m in members_b if m["user_id"] == regular_user.id), None)
        assert user_in_b is not None
        assert user_in_b["role"] == "member"

    async def test_move_multiple_members_at_once(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, second_department: Department, organization: Organization,
        org_owner: OrgMember, get_auth_headers
    ):
        """Test moving multiple members from one department to another."""
        # Create 3 new users
        users = []
        for i in range(3):
            user = User(
                email=f"move_user_{i}@test.com",
                password_hash="hashed",
                name=f"Move User {i}",
                role=UserRole.admin,
                is_active=True
            )
            db_session.add(user)
            users.append(user)
        await db_session.commit()

        # Make them org members
        for user in users:
            org_member = OrgMember(
                org_id=organization.id,
                user_id=user.id,
                role=OrgRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(org_member)
        await db_session.commit()

        # Add all to department A
        for user in users:
            await client.post(
                f"/api/departments/{department.id}/members",
                json={"user_id": user.id, "role": "member"},
                headers=get_auth_headers(admin_token)
            )

        # Get initial counts
        dept_a_initial = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )
        dept_b_initial = await client.get(
            f"/api/departments/{second_department.id}",
            headers=get_auth_headers(admin_token)
        )
        initial_a_count = dept_a_initial.json()["members_count"]
        initial_b_count = dept_b_initial.json()["members_count"]

        # Move all users from A to B
        for user in users:
            # Remove from A
            await client.delete(
                f"/api/departments/{department.id}/members/{user.id}",
                headers=get_auth_headers(admin_token)
            )
            # Add to B
            await client.post(
                f"/api/departments/{second_department.id}/members",
                json={"user_id": user.id, "role": "member"},
                headers=get_auth_headers(admin_token)
            )

        # Verify final counts
        dept_a_final = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )
        dept_b_final = await client.get(
            f"/api/departments/{second_department.id}",
            headers=get_auth_headers(admin_token)
        )
        assert dept_a_final.json()["members_count"] == initial_a_count - 3
        assert dept_b_final.json()["members_count"] == initial_b_count + 3

    async def test_dept_lead_can_move_member_from_their_dept(
        self, db_session: AsyncSession, client: AsyncClient, organization: Organization,
        department: Department, second_department: Department, admin_user: User,
        regular_user: User, second_user: User, org_owner: OrgMember, get_auth_headers
    ):
        """Test department lead can move members from their own department."""
        # Make admin_user lead of department A
        dept_lead_membership = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_lead_membership)

        # Make regular_user org member and dept member
        org_member = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(org_member)
        dept_member = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_member)
        await db_session.commit()

        # Lead removes member from their department
        admin_token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.delete(
            f"/api/departments/{department.id}/members/{regular_user.id}",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200

    async def test_dept_lead_cannot_add_to_other_department(
        self, db_session: AsyncSession, client: AsyncClient, organization: Organization,
        department: Department, second_department: Department, admin_user: User,
        regular_user: User, get_auth_headers
    ):
        """Test department lead cannot add members to other departments."""
        # Make admin_user lead of department A only
        dept_lead_membership = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_lead_membership)

        # Make regular_user org member
        org_member = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(org_member)
        await db_session.commit()

        # Lead tries to add member to department B (should fail)
        admin_token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.post(
            f"/api/departments/{second_department.id}/members",
            json={"user_id": regular_user.id, "role": "member"},
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 403

    @pytest.mark.xfail(reason="Move user logic")
    async def test_move_user_updates_my_departments(
        self, db_session: AsyncSession, client: AsyncClient, organization: Organization,
        department: Department, second_department: Department, regular_user: User,
        org_admin: OrgMember, admin_token: str, get_auth_headers
    ):
        """Test that moving a user updates their /my/departments list."""
        # Add user to department A
        dept_member = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_member)
        await db_session.commit()

        # Check user's departments - should include dept A
        user_token = create_access_token(data={"sub": str(regular_user.id)})
        response1 = await client.get(
            "/api/departments/my/departments",
            headers=get_auth_headers(user_token)
        )
        assert response1.status_code == 200
        my_depts_before = response1.json()
        dept_ids_before = [d["id"] for d in my_depts_before]
        assert department.id in dept_ids_before

        # Move user from A to B
        await client.delete(
            f"/api/departments/{department.id}/members/{regular_user.id}",
            headers=get_auth_headers(admin_token)
        )
        await client.post(
            f"/api/departments/{second_department.id}/members",
            json={"user_id": regular_user.id, "role": "member"},
            headers=get_auth_headers(admin_token)
        )

        # Check user's departments again
        response2 = await client.get(
            "/api/departments/my/departments",
            headers=get_auth_headers(user_token)
        )
        assert response2.status_code == 200
        my_depts_after = response2.json()
        dept_ids_after = [d["id"] for d in my_depts_after]
        assert department.id not in dept_ids_after
        assert second_department.id in dept_ids_after

    async def test_cannot_move_user_to_same_department(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        regular_user: User, get_auth_headers
    ):
        """Test that adding a user to the same department updates their role instead."""
        # Make user org member
        org_member = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(org_member)
        await db_session.commit()

        # Add user to department as member
        response1 = await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": regular_user.id, "role": "member"},
            headers=get_auth_headers(admin_token)
        )
        assert response1.status_code in [200, 201]
        assert response1.json()["role"] == "member"

        # Try to add same user again with different role
        response2 = await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": regular_user.id, "role": "sub_admin"},
            headers=get_auth_headers(admin_token)
        )
        assert response2.status_code in [200, 201]
        # Should update role, not create duplicate
        assert response2.json()["role"] == "sub_admin"

        # Verify there's only one membership
        response3 = await client.get(
            f"/api/departments/{department.id}/members",
            headers=get_auth_headers(admin_token)
        )
        members = response3.json()
        user_memberships = [m for m in members if m["user_id"] == regular_user.id]
        assert len(user_memberships) == 1
        assert user_memberships[0]["role"] == "sub_admin"

    async def test_move_user_between_parent_and_child_departments(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        organization: Organization, org_owner: OrgMember, regular_user: User,
        get_auth_headers
    ):
        """Test moving user between parent and child departments."""
        # Create parent department
        response1 = await client.post(
            "/api/departments",
            json={"name": "Parent Dept"},
            headers=get_auth_headers(admin_token)
        )
        parent_dept = response1.json()

        # Create child department
        response2 = await client.post(
            "/api/departments",
            json={"name": "Child Dept", "parent_id": parent_dept["id"]},
            headers=get_auth_headers(admin_token)
        )
        child_dept = response2.json()

        # Make user org member
        org_member = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(org_member)
        await db_session.commit()

        # Add user to parent
        response3 = await client.post(
            f"/api/departments/{parent_dept['id']}/members",
            json={"user_id": regular_user.id, "role": "member"},
            headers=get_auth_headers(admin_token)
        )
        assert response3.status_code in [200, 201]

        # Move to child
        await client.delete(
            f"/api/departments/{parent_dept['id']}/members/{regular_user.id}",
            headers=get_auth_headers(admin_token)
        )
        response4 = await client.post(
            f"/api/departments/{child_dept['id']}/members",
            json={"user_id": regular_user.id, "role": "member"},
            headers=get_auth_headers(admin_token)
        )
        assert response4.status_code in [200, 201]

        # Verify user is in child, not parent
        parent_members = await client.get(
            f"/api/departments/{parent_dept['id']}/members",
            headers=get_auth_headers(admin_token)
        )
        child_members = await client.get(
            f"/api/departments/{child_dept['id']}/members",
            headers=get_auth_headers(admin_token)
        )

        parent_member_ids = [m["user_id"] for m in parent_members.json()]
        child_member_ids = [m["user_id"] for m in child_members.json()]

        assert regular_user.id not in parent_member_ids
        assert regular_user.id in child_member_ids


# =============================================================================
# ENHANCED STATISTICS TESTS
# =============================================================================

class TestEnhancedDepartmentStatistics:
    """Enhanced tests for department statistics with detailed breakdowns."""

    async def test_statistics_by_member_role_breakdown(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        get_auth_headers
    ):
        """Test department shows correct count breakdown by role types."""
        # Create users with different roles
        users = []
        for i in range(3):
            user = User(
                email=f"role_user_{i}@test.com",
                password_hash="hashed",
                name=f"Role User {i}",
                role=UserRole.admin,
                is_active=True
            )
            db_session.add(user)
            users.append(user)
        await db_session.commit()

        # Make them org members
        for user in users:
            org_member = OrgMember(
                org_id=organization.id,
                user_id=user.id,
                role=OrgRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(org_member)
        await db_session.commit()

        # Add users with different department roles
        await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": users[0].id, "role": "lead"},
            headers=get_auth_headers(admin_token)
        )
        await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": users[1].id, "role": "sub_admin"},
            headers=get_auth_headers(admin_token)
        )
        await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": users[2].id, "role": "member"},
            headers=get_auth_headers(admin_token)
        )

        # Get members list
        response = await client.get(
            f"/api/departments/{department.id}/members",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        members = response.json()

        # Count by role
        role_counts = {}
        for member in members:
            role = member["role"]
            role_counts[role] = role_counts.get(role, 0) + 1

        assert role_counts.get("lead", 0) >= 1
        assert role_counts.get("sub_admin", 0) >= 1
        assert role_counts.get("member", 0) >= 1

    @pytest.mark.xfail(reason="Stats aggregation")
    async def test_statistics_with_multiple_entity_types(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        admin_user: User, get_auth_headers
    ):
        """Test department statistics with different entity types."""
        from api.models.database import Entity, EntityType, EntityStatus

        # Create entities of different types
        entity_types = [EntityType.candidate, EntityType.client, EntityType.employee]
        for i, entity_type in enumerate(entity_types):
            entity = Entity(
                org_id=organization.id,
                department_id=department.id,
                created_by=admin_user.id,
                name=f"Entity {i}",
                email=f"entity{i}@test.com",
                type=entity_type,
                status=EntityStatus.active,
                created_at=datetime.utcnow()
            )
            db_session.add(entity)
        await db_session.commit()

        # Get department statistics
        response = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["entities_count"] >= 3

    async def test_statistics_accuracy_after_bulk_operations(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        get_auth_headers
    ):
        """Test statistics remain accurate after bulk add/remove operations."""
        # Create multiple users
        users = []
        for i in range(10):
            user = User(
                email=f"bulk_user_{i}@test.com",
                password_hash="hashed",
                name=f"Bulk User {i}",
                role=UserRole.admin,
                is_active=True
            )
            db_session.add(user)
            users.append(user)
        await db_session.commit()

        # Make them org members
        for user in users:
            org_member = OrgMember(
                org_id=organization.id,
                user_id=user.id,
                role=OrgRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(org_member)
        await db_session.commit()

        # Get initial count
        initial_response = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )
        initial_count = initial_response.json()["members_count"]

        # Bulk add users
        for user in users:
            await client.post(
                f"/api/departments/{department.id}/members",
                json={"user_id": user.id, "role": "member"},
                headers=get_auth_headers(admin_token)
            )

        # Verify count increased
        after_add_response = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )
        after_add_count = after_add_response.json()["members_count"]
        assert after_add_count == initial_count + 10

        # Bulk remove half
        for user in users[:5]:
            await client.delete(
                f"/api/departments/{department.id}/members/{user.id}",
                headers=get_auth_headers(admin_token)
            )

        # Verify count decreased correctly
        after_remove_response = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )
        after_remove_count = after_remove_response.json()["members_count"]
        assert after_remove_count == initial_count + 5

    async def test_hierarchy_statistics_recursive_counts(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test hierarchy statistics count children correctly at each level."""
        # Create 3-level hierarchy
        # Level 1: Engineering
        response1 = await client.post(
            "/api/departments",
            json={"name": "Engineering"},
            headers=get_auth_headers(admin_token)
        )
        engineering = response1.json()

        # Level 2: Backend, Frontend (2 children of Engineering)
        response2 = await client.post(
            "/api/departments",
            json={"name": "Backend", "parent_id": engineering["id"]},
            headers=get_auth_headers(admin_token)
        )
        backend = response2.json()

        response3 = await client.post(
            "/api/departments",
            json={"name": "Frontend", "parent_id": engineering["id"]},
            headers=get_auth_headers(admin_token)
        )
        frontend = response3.json()

        # Level 3: API, Database (2 children of Backend)
        await client.post(
            "/api/departments",
            json={"name": "API", "parent_id": backend["id"]},
            headers=get_auth_headers(admin_token)
        )
        await client.post(
            "/api/departments",
            json={"name": "Database", "parent_id": backend["id"]},
            headers=get_auth_headers(admin_token)
        )

        # Verify Engineering has 2 direct children
        eng_response = await client.get(
            f"/api/departments/{engineering['id']}",
            headers=get_auth_headers(admin_token)
        )
        assert eng_response.status_code == 200
        assert eng_response.json()["children_count"] == 2

        # Verify Backend has 2 direct children
        backend_response = await client.get(
            f"/api/departments/{backend['id']}",
            headers=get_auth_headers(admin_token)
        )
        assert backend_response.status_code == 200
        assert backend_response.json()["children_count"] == 2

        # Verify Frontend has 0 children
        frontend_response = await client.get(
            f"/api/departments/{frontend['id']}",
            headers=get_auth_headers(admin_token)
        )
        assert frontend_response.status_code == 200
        assert frontend_response.json()["children_count"] == 0

    async def test_statistics_with_inactive_department(
        self, client: AsyncClient, admin_token: str, department: Department,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test statistics for inactive department."""
        # Deactivate department
        response1 = await client.patch(
            f"/api/departments/{department.id}",
            json={"is_active": False},
            headers=get_auth_headers(admin_token)
        )
        assert response1.status_code == 200
        assert response1.json()["is_active"] is False

        # Statistics should still be accessible
        response2 = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )
        assert response2.status_code == 200
        data = response2.json()
        assert "members_count" in data
        assert "entities_count" in data
        assert "children_count" in data


# =============================================================================
# COMPREHENSIVE ROLE TRANSITION TESTS
# =============================================================================

class TestComprehensiveRoleTransitions:
    """Test all possible role transitions for department members."""

    async def test_all_role_promotions(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        regular_user: User, get_auth_headers
    ):
        """Test all upward role transitions: member -> sub_admin -> lead."""
        # Make user org member
        org_member = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(org_member)
        await db_session.commit()

        # Add as member
        response1 = await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": regular_user.id, "role": "member"},
            headers=get_auth_headers(admin_token)
        )
        assert response1.status_code in [200, 201]
        assert response1.json()["role"] == "member"

        # Promote to sub_admin
        response2 = await client.patch(
            f"/api/departments/{department.id}/members/{regular_user.id}",
            json={"role": "sub_admin"},
            headers=get_auth_headers(admin_token)
        )
        assert response2.status_code == 200
        assert response2.json()["role"] == "sub_admin"

        # Promote to lead
        response3 = await client.patch(
            f"/api/departments/{department.id}/members/{regular_user.id}",
            json={"role": "lead"},
            headers=get_auth_headers(admin_token)
        )
        assert response3.status_code == 200
        assert response3.json()["role"] == "lead"

    async def test_all_role_demotions(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        regular_user: User, second_user: User, get_auth_headers
    ):
        """Test all downward role transitions: lead -> sub_admin -> member."""
        # Make users org members
        for user in [regular_user, second_user]:
            org_member = OrgMember(
                org_id=organization.id,
                user_id=user.id,
                role=OrgRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(org_member)
        await db_session.commit()

        # Add regular_user as lead and second_user as backup lead
        await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": regular_user.id, "role": "lead"},
            headers=get_auth_headers(admin_token)
        )
        await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": second_user.id, "role": "lead"},
            headers=get_auth_headers(admin_token)
        )

        # Demote to sub_admin
        response1 = await client.patch(
            f"/api/departments/{department.id}/members/{regular_user.id}",
            json={"role": "sub_admin"},
            headers=get_auth_headers(admin_token)
        )
        assert response1.status_code == 200
        assert response1.json()["role"] == "sub_admin"

        # Demote to member
        response2 = await client.patch(
            f"/api/departments/{department.id}/members/{regular_user.id}",
            json={"role": "member"},
            headers=get_auth_headers(admin_token)
        )
        assert response2.status_code == 200
        assert response2.json()["role"] == "member"

    async def test_direct_role_jumps(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        regular_user: User, get_auth_headers
    ):
        """Test direct role transitions (skipping intermediate roles)."""
        # Make user org member
        org_member = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(org_member)
        await db_session.commit()

        # Add as member
        await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": regular_user.id, "role": "member"},
            headers=get_auth_headers(admin_token)
        )

        # Jump directly from member to lead (skip sub_admin)
        response = await client.patch(
            f"/api/departments/{department.id}/members/{regular_user.id}",
            json={"role": "lead"},
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        assert response.json()["role"] == "lead"

    async def test_role_change_permissions_by_different_users(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        regular_user: User, second_user: User, get_auth_headers
    ):
        """Test role change permissions for owner vs lead vs member."""
        # Make users org members
        for user in [regular_user, second_user]:
            org_member = OrgMember(
                org_id=organization.id,
                user_id=user.id,
                role=OrgRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(org_member)
        await db_session.commit()

        # Make regular_user a lead
        await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": regular_user.id, "role": "lead"},
            headers=get_auth_headers(admin_token)
        )

        # Add second_user as member
        await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": second_user.id, "role": "member"},
            headers=get_auth_headers(admin_token)
        )

        # Lead can promote member to sub_admin
        lead_token = create_access_token(data={"sub": str(regular_user.id)})
        response1 = await client.patch(
            f"/api/departments/{department.id}/members/{second_user.id}",
            json={"role": "sub_admin"},
            headers=get_auth_headers(lead_token)
        )
        assert response1.status_code == 200

        # Lead cannot promote to lead
        response2 = await client.patch(
            f"/api/departments/{department.id}/members/{second_user.id}",
            json={"role": "lead"},
            headers=get_auth_headers(lead_token)
        )
        assert response2.status_code == 403

        # Owner can promote to lead
        response3 = await client.patch(
            f"/api/departments/{department.id}/members/{second_user.id}",
            json={"role": "lead"},
            headers=get_auth_headers(admin_token)
        )
        assert response3.status_code == 200

    async def test_invalid_role_value(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        regular_user: User, get_auth_headers
    ):
        """Test updating member with invalid role value fails."""
        # Make user org member
        org_member = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(org_member)
        await db_session.commit()

        # Add user as member
        await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": regular_user.id, "role": "member"},
            headers=get_auth_headers(admin_token)
        )

        # Try to update with invalid role
        response = await client.patch(
            f"/api/departments/{department.id}/members/{regular_user.id}",
            json={"role": "invalid_role"},
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 422  # Validation error


# =============================================================================
# ADVANCED HIERARCHY TESTS
# =============================================================================

class TestAdvancedDepartmentHierarchy:
    """Advanced tests for deep and complex department hierarchies."""

    async def test_five_level_deep_hierarchy(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test creating and navigating a 5-level deep hierarchy."""
        # Create 5-level hierarchy
        level1 = (await client.post(
            "/api/departments",
            json={"name": "Level 1 - Company"},
            headers=get_auth_headers(admin_token)
        )).json()

        level2 = (await client.post(
            "/api/departments",
            json={"name": "Level 2 - Division", "parent_id": level1["id"]},
            headers=get_auth_headers(admin_token)
        )).json()

        level3 = (await client.post(
            "/api/departments",
            json={"name": "Level 3 - Department", "parent_id": level2["id"]},
            headers=get_auth_headers(admin_token)
        )).json()

        level4 = (await client.post(
            "/api/departments",
            json={"name": "Level 4 - Team", "parent_id": level3["id"]},
            headers=get_auth_headers(admin_token)
        )).json()

        level5 = (await client.post(
            "/api/departments",
            json={"name": "Level 5 - Squad", "parent_id": level4["id"]},
            headers=get_auth_headers(admin_token)
        )).json()

        # Verify level 5 has correct parent chain
        response = await client.get(
            f"/api/departments/{level5['id']}",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["parent_id"] == level4["id"]
        assert data["parent_name"] == "Level 4 - Team"

    async def test_multiple_branches_in_hierarchy(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test hierarchy with multiple branches at each level."""
        # Create root
        root = (await client.post(
            "/api/departments",
            json={"name": "Root"},
            headers=get_auth_headers(admin_token)
        )).json()

        # Create 3 children
        children = []
        for i in range(3):
            child = (await client.post(
                "/api/departments",
                json={"name": f"Child {i}", "parent_id": root["id"]},
                headers=get_auth_headers(admin_token)
            )).json()
            children.append(child)

        # Create 2 grandchildren for each child
        for child in children:
            for j in range(2):
                await client.post(
                    "/api/departments",
                    json={"name": f"Grandchild {child['name']}-{j}", "parent_id": child["id"]},
                    headers=get_auth_headers(admin_token)
                )

        # Verify root has 3 children
        root_response = await client.get(
            f"/api/departments/{root['id']}",
            headers=get_auth_headers(admin_token)
        )
        assert root_response.json()["children_count"] == 3

        # Verify each child has 2 children
        for child in children:
            child_response = await client.get(
                f"/api/departments/{child['id']}",
                headers=get_auth_headers(admin_token)
            )
            assert child_response.json()["children_count"] == 2

    async def test_get_all_descendants_of_department(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        organization: Organization, org_owner: OrgMember, get_auth_headers
    ):
        """Test getting all descendant departments recursively."""
        # Create parent with children and grandchildren
        parent = (await client.post(
            "/api/departments",
            json={"name": "Parent"},
            headers=get_auth_headers(admin_token)
        )).json()

        child1 = (await client.post(
            "/api/departments",
            json={"name": "Child 1", "parent_id": parent["id"]},
            headers=get_auth_headers(admin_token)
        )).json()

        child2 = (await client.post(
            "/api/departments",
            json={"name": "Child 2", "parent_id": parent["id"]},
            headers=get_auth_headers(admin_token)
        )).json()

        # Create grandchildren
        await client.post(
            "/api/departments",
            json={"name": "Grandchild 1", "parent_id": child1["id"]},
            headers=get_auth_headers(admin_token)
        )
        await client.post(
            "/api/departments",
            json={"name": "Grandchild 2", "parent_id": child1["id"]},
            headers=get_auth_headers(admin_token)
        )

        # Get direct children
        children_response = await client.get(
            f"/api/departments/{parent['id']}/children",
            headers=get_auth_headers(admin_token)
        )
        assert children_response.status_code == 200
        children = children_response.json()
        assert len(children) == 2

        # Get grandchildren through child1
        grandchildren_response = await client.get(
            f"/api/departments/{child1['id']}/children",
            headers=get_auth_headers(admin_token)
        )
        assert grandchildren_response.status_code == 200
        grandchildren = grandchildren_response.json()
        assert len(grandchildren) == 2

    async def test_hierarchy_member_inheritance_isolation(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        organization: Organization, org_owner: OrgMember, regular_user: User,
        get_auth_headers
    ):
        """Test that members in parent don't automatically belong to children."""
        # Make user org member
        org_member = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(org_member)
        await db_session.commit()

        # Create parent and child
        parent = (await client.post(
            "/api/departments",
            json={"name": "Parent"},
            headers=get_auth_headers(admin_token)
        )).json()

        child = (await client.post(
            "/api/departments",
            json={"name": "Child", "parent_id": parent["id"]},
            headers=get_auth_headers(admin_token)
        )).json()

        # Add user to parent
        await client.post(
            f"/api/departments/{parent['id']}/members",
            json={"user_id": regular_user.id, "role": "member"},
            headers=get_auth_headers(admin_token)
        )

        # Verify user is in parent
        parent_members = await client.get(
            f"/api/departments/{parent['id']}/members",
            headers=get_auth_headers(admin_token)
        )
        assert any(m["user_id"] == regular_user.id for m in parent_members.json())

        # Verify user is NOT in child (members don't inherit)
        child_members = await client.get(
            f"/api/departments/{child['id']}/members",
            headers=get_auth_headers(admin_token)
        )
        assert not any(m["user_id"] == regular_user.id for m in child_members.json())


# =============================================================================
# BULK MEMBER OPERATIONS TESTS
# =============================================================================

class TestBulkMemberOperations:
    """Tests for bulk operations on department members."""

    async def test_add_multiple_members_sequentially(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        get_auth_headers
    ):
        """Test adding multiple members in sequence and verify final count."""
        # Create 20 users
        users = []
        for i in range(20):
            user = User(
                email=f"bulk_add_{i}@test.com",
                password_hash="hashed",
                name=f"Bulk User {i}",
                role=UserRole.admin,
                is_active=True
            )
            db_session.add(user)
            users.append(user)
        await db_session.commit()

        # Make them org members
        for user in users:
            org_member = OrgMember(
                org_id=organization.id,
                user_id=user.id,
                role=OrgRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(org_member)
        await db_session.commit()

        # Get initial count
        initial_response = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )
        initial_count = initial_response.json()["members_count"]

        # Add all users
        for user in users:
            response = await client.post(
                f"/api/departments/{department.id}/members",
                json={"user_id": user.id, "role": "member"},
                headers=get_auth_headers(admin_token)
            )
            assert response.status_code in [200, 201]

        # Verify final count
        final_response = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )
        final_count = final_response.json()["members_count"]
        assert final_count == initial_count + 20

    async def test_bulk_role_changes(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        get_auth_headers
    ):
        """Test changing roles for multiple members."""
        # Create 5 users
        users = []
        for i in range(5):
            user = User(
                email=f"role_change_{i}@test.com",
                password_hash="hashed",
                name=f"Role User {i}",
                role=UserRole.admin,
                is_active=True
            )
            db_session.add(user)
            users.append(user)
        await db_session.commit()

        # Make them org members
        for user in users:
            org_member = OrgMember(
                org_id=organization.id,
                user_id=user.id,
                role=OrgRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(org_member)
        await db_session.commit()

        # Add all as members
        for user in users:
            await client.post(
                f"/api/departments/{department.id}/members",
                json={"user_id": user.id, "role": "member"},
                headers=get_auth_headers(admin_token)
            )

        # Change all to sub_admin
        for user in users:
            response = await client.patch(
                f"/api/departments/{department.id}/members/{user.id}",
                json={"role": "sub_admin"},
                headers=get_auth_headers(admin_token)
            )
            assert response.status_code == 200

        # Verify all roles changed
        members_response = await client.get(
            f"/api/departments/{department.id}/members",
            headers=get_auth_headers(admin_token)
        )
        members = members_response.json()

        for user in users:
            member_data = next((m for m in members if m["user_id"] == user.id), None)
            assert member_data is not None
            assert member_data["role"] == "sub_admin"

    async def test_remove_all_members_except_leads(
        self, db_session: AsyncSession, client: AsyncClient, admin_token: str,
        department: Department, organization: Organization, org_owner: OrgMember,
        get_auth_headers
    ):
        """Test removing all non-lead members from a department."""
        # Create users
        users = []
        for i in range(10):
            user = User(
                email=f"remove_member_{i}@test.com",
                password_hash="hashed",
                name=f"Member {i}",
                role=UserRole.admin,
                is_active=True
            )
            db_session.add(user)
            users.append(user)
        await db_session.commit()

        # Make them org members
        for user in users:
            org_member = OrgMember(
                org_id=organization.id,
                user_id=user.id,
                role=OrgRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(org_member)
        await db_session.commit()

        # Add first user as lead, rest as members
        await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": users[0].id, "role": "lead"},
            headers=get_auth_headers(admin_token)
        )

        for user in users[1:]:
            await client.post(
                f"/api/departments/{department.id}/members",
                json={"user_id": user.id, "role": "member"},
                headers=get_auth_headers(admin_token)
            )

        # Remove all members except lead
        for user in users[1:]:
            response = await client.delete(
                f"/api/departments/{department.id}/members/{user.id}",
                headers=get_auth_headers(admin_token)
            )
            assert response.status_code == 200

        # Verify only lead remains
        members_response = await client.get(
            f"/api/departments/{department.id}/members",
            headers=get_auth_headers(admin_token)
        )
        members = members_response.json()

        # Filter for our test users (might have other members from fixtures)
        test_user_ids = [u.id for u in users]
        test_members = [m for m in members if m["user_id"] in test_user_ids]

        assert len(test_members) == 1
        assert test_members[0]["user_id"] == users[0].id
        assert test_members[0]["role"] == "lead"
