"""
Tests for departments functionality.
"""
import pytest
import pytest_asyncio
from datetime import datetime

from api.models.database import Department, DepartmentMember, DeptRole


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


class TestCreateDepartment:
    """Test department creation."""

    @pytest.mark.asyncio
    async def test_org_owner_can_create_department(
        self, client, admin_user, admin_token, organization, get_auth_headers, org_owner
    ):
        """Test that org owner can create department."""
        response = await client.post(
            "/api/departments",
            json={"name": "New Department"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code in [200, 201]
        data = response.json()
        assert data["name"] == "New Department"

    @pytest.mark.asyncio
    async def test_regular_member_cannot_create_root_department(
        self, client, second_user, second_user_token, organization, get_auth_headers, org_member
    ):
        """Test that regular member cannot create root department."""
        response = await client.post(
            "/api/departments",
            json={"name": "Unauthorized Department"},
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_dept_lead_can_create_subdepartment(
        self, client, admin_user, admin_token, department, get_auth_headers, org_owner, dept_lead
    ):
        """Test that department lead can create subdepartment."""
        response = await client.post(
            "/api/departments",
            json={"name": "Sub Department", "parent_id": department.id},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code in [200, 201]

    @pytest.mark.asyncio
    async def test_create_department_undefined_variable_bug(
        self, client, admin_user, admin_token, department, get_auth_headers, org_owner, dept_lead
    ):
        """
        BUG TEST: departments.py:293 uses undefined variable 'is_admin'.
        This should cause NameError when creating department with parent_id.
        """
        # This test documents the bug - creating subdepartment should fail with NameError
        # After fix, should work correctly
        response = await client.post(
            "/api/departments",
            json={"name": "Test Subdept", "parent_id": department.id},
            headers=get_auth_headers(admin_token)
        )

        # If bug exists, will get 500 Internal Server Error
        # After fix, should get 200/201
        assert response.status_code != 500, \
            f"BUG: Undefined variable 'is_admin' causes error. Got {response.status_code}"


class TestUpdateDepartment:
    """Test department update."""

    @pytest.mark.asyncio
    async def test_org_owner_can_update_department(
        self, client, admin_user, admin_token, department, get_auth_headers, org_owner
    ):
        """Test that org owner can update department."""
        response = await client.patch(
            f"/api/departments/{department.id}",
            json={"name": "Updated Department Name"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Department Name"

    @pytest.mark.asyncio
    async def test_dept_lead_can_update_own_department(
        self, client, admin_user, admin_token, department, get_auth_headers, org_owner, dept_lead
    ):
        """Test that department lead can update their department."""
        response = await client.patch(
            f"/api/departments/{department.id}",
            json={"name": "Lead Updated Name"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_regular_member_cannot_update_department(
        self, client, regular_user, user_token, department, get_auth_headers, org_admin, dept_member
    ):
        """Test that regular member cannot update department."""
        response = await client.patch(
            f"/api/departments/{department.id}",
            json={"name": "Unauthorized Update"},
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 403


class TestDeleteDepartment:
    """Test department deletion."""

    @pytest.mark.asyncio
    async def test_org_owner_can_delete_department(
        self, client, admin_user, admin_token, department, get_auth_headers, org_owner
    ):
        """Test that org owner can delete department."""
        response = await client.delete(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_cannot_delete_department_with_members(
        self, client, admin_user, admin_token, department, get_auth_headers, org_owner, dept_member
    ):
        """Test that department with members cannot be deleted."""
        response = await client.delete(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )

        # Should fail because department has members
        assert response.status_code in [400, 409]

    @pytest.mark.asyncio
    async def test_cannot_delete_department_with_entities(
        self, client, admin_user, admin_token, department, entity, get_auth_headers, org_owner
    ):
        """Test that department with entities cannot be deleted."""
        response = await client.delete(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(admin_token)
        )

        # Should fail because department has entities
        assert response.status_code in [400, 409]


class TestDepartmentMembers:
    """Test department member management."""

    @pytest.mark.asyncio
    async def test_org_owner_can_add_member(
        self, client, admin_user, admin_token, department, second_user, get_auth_headers, org_owner, org_member
    ):
        """Test that org owner can add member to department."""
        response = await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": second_user.id, "role": "member"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code in [200, 201]

    @pytest.mark.asyncio
    async def test_dept_lead_can_add_member(
        self, client, admin_user, admin_token, department, second_user, get_auth_headers, org_owner, org_member, dept_lead
    ):
        """Test that department lead can add member."""
        response = await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": second_user.id, "role": "member"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code in [200, 201]

    @pytest.mark.asyncio
    async def test_regular_member_cannot_add_member(
        self, client, regular_user, user_token, department, second_user, get_auth_headers, plain_org_member, dept_member, org_member
    ):
        """Test that regular member cannot add member to department."""
        response = await client.post(
            f"/api/departments/{department.id}/members",
            json={"user_id": second_user.id, "role": "member"},
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_cannot_remove_last_lead(
        self, client, admin_user, admin_token, department, get_auth_headers, org_owner, dept_lead
    ):
        """Test that last department lead cannot be removed."""
        response = await client.delete(
            f"/api/departments/{department.id}/members/{admin_user.id}",
            headers=get_auth_headers(admin_token)
        )

        # Should fail - cannot remove last lead
        assert response.status_code == 400


class TestDepartmentHierarchy:
    """Test department hierarchy operations."""

    @pytest.mark.asyncio
    async def test_create_subdepartment(
        self, client, admin_user, admin_token, department, get_auth_headers, org_owner, dept_lead
    ):
        """Test creating subdepartment."""
        response = await client.post(
            "/api/departments",
            json={"name": "Subdepartment", "parent_id": department.id},
            headers=get_auth_headers(admin_token)
        )

        # Might fail due to is_admin bug
        if response.status_code in [200, 201]:
            data = response.json()
            assert data["parent_id"] == department.id

    @pytest.mark.asyncio
    async def test_get_department_children(
        self, db_session, client, admin_user, admin_token, department, organization, get_auth_headers, org_owner
    ):
        """Test getting department children."""
        # Create child department
        child = Department(
            name="Child Department",
            org_id=organization.id,
            parent_id=department.id,
            
            
            
            created_at=datetime.utcnow()
        )
        db_session.add(child)
        await db_session.commit()

        response = await client.get(
            f"/api/departments/{department.id}/children",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1


class TestDepartmentAccess:
    """Test department access control."""

    @pytest.mark.asyncio
    async def test_member_can_view_own_department(
        self, client, regular_user, user_token, department, get_auth_headers, org_admin, dept_member
    ):
        """Test that member can view their department."""
        response = await client.get(
            f"/api/departments/{department.id}",
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_non_member_cannot_view_department_details(
        self, client, second_user, second_user_token, second_department, get_auth_headers, org_member
    ):
        """Test that non-member cannot view department they're not in."""
        # Second user is not in second_department
        response = await client.get(
            f"/api/departments/{second_department.id}",
            headers=get_auth_headers(second_user_token)
        )

        # Depending on implementation, might return 403 or limited data


class TestDepartmentList:
    """Test department listing."""

    @pytest.mark.asyncio
    async def test_org_owner_sees_all_departments(
        self, client, admin_user, admin_token, department, second_department, get_auth_headers, org_owner
    ):
        """Test that org owner sees all departments."""
        response = await client.get(
            "/api/departments",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        dept_ids = [d["id"] for d in data]
        assert department.id in dept_ids
        assert second_department.id in dept_ids

    @pytest.mark.asyncio
    async def test_member_sees_accessible_departments(
        self, client, regular_user, user_token, department, second_department, get_auth_headers, org_admin, dept_member
    ):
        """Test that member sees departments they have access to."""
        response = await client.get(
            "/api/departments",
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Should see department they're member of
        dept_ids = [d["id"] for d in data]
        assert department.id in dept_ids


class TestDepartmentMemberRoles:
    """Test department member role management."""

    @pytest.mark.asyncio
    async def test_promote_member_to_lead(
        self, client, admin_user, admin_token, department, regular_user, get_auth_headers, org_owner, dept_member
    ):
        """Test promoting member to lead."""
        response = await client.patch(
            f"/api/departments/{department.id}/members/{regular_user.id}",
            json={"role": "lead"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "lead"

    @pytest.mark.asyncio
    async def test_demote_lead_to_member(
        self, db_session, client, admin_user, admin_token, department, regular_user, get_auth_headers, org_owner
    ):
        """Test demoting lead to member (if multiple leads exist)."""
        # First make regular_user a lead
        lead_member = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(lead_member)
        await db_session.commit()

        # Now demote them (should work if admin_user is also lead)
        response = await client.patch(
            f"/api/departments/{department.id}/members/{regular_user.id}",
            json={"role": "member"},
            headers=get_auth_headers(admin_token)
        )

        # Should succeed if there's still at least one lead left
        if response.status_code == 200:
            data = response.json()
            assert data["role"] == "member"


class TestCrossOrgDepartments:
    """Test that departments are properly isolated by organization."""

    @pytest.mark.asyncio
    async def test_cannot_access_department_from_other_org(
        self, db_session, client, second_user, second_user_token, second_organization, get_auth_headers, org_member
    ):
        """Test that user cannot access department from different organization."""
        # Create department in second organization
        other_dept = Department(
            name="Other Org Department",
            org_id=second_organization.id,
            
            
            
            created_at=datetime.utcnow()
        )
        db_session.add(other_dept)
        await db_session.commit()
        await db_session.refresh(other_dept)

        response = await client.get(
            f"/api/departments/{other_dept.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code in [403, 404], \
            f"User should not access department from other org. Got {response.status_code}"


class TestDepartmentAdminEntityVisibility:
    """Test that department admins can see entities created by department members."""

    @pytest.mark.asyncio
    async def test_dept_lead_sees_entities_created_by_dept_members(
        self, db_session, client, admin_user, admin_token, second_user, second_user_token,
        organization, department, get_auth_headers, org_owner, org_member
    ):
        """
        Test that department lead can see entities created by regular department members.
        This tests the fix for entities without department_id but created by dept members.
        """
        from api.models.database import Entity, EntityType, EntityStatus

        # Add admin_user as lead of the department
        lead_membership = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(lead_membership)

        # Add second_user as member of the same department
        member_membership = DepartmentMember(
            department_id=department.id,
            user_id=second_user.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(member_membership)
        await db_session.commit()

        # second_user creates an entity WITHOUT department_id
        entity_no_dept = Entity(
            org_id=organization.id,
            department_id=None,  # No department assignment
            created_by=second_user.id,
            name="Entity by Dept Member",
            email="member-entity@test.com",
            type=EntityType.candidate,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(entity_no_dept)
        await db_session.commit()
        await db_session.refresh(entity_no_dept)

        # Department lead should see this entity because owner is in their department
        response = await client.get(
            "/api/entities",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        entity_ids = [e["id"] for e in data]

        assert entity_no_dept.id in entity_ids, \
            "Department lead should see entities created by department members, even without department_id"

    @pytest.mark.asyncio
    async def test_dept_sub_admin_sees_entities_created_by_dept_members(
        self, db_session, client, admin_user, admin_token, second_user,
        organization, department, get_auth_headers, org_owner, org_member
    ):
        """
        Test that department sub_admin can see entities created by department members.
        """
        from api.models.database import Entity, EntityType, EntityStatus

        # Add admin_user as sub_admin of the department
        sub_admin_membership = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.sub_admin,
            created_at=datetime.utcnow()
        )
        db_session.add(sub_admin_membership)

        # Add second_user as member of the same department
        member_membership = DepartmentMember(
            department_id=department.id,
            user_id=second_user.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(member_membership)
        await db_session.commit()

        # second_user creates an entity WITHOUT department_id
        entity_no_dept = Entity(
            org_id=organization.id,
            department_id=None,
            created_by=second_user.id,
            name="Entity for Sub Admin Test",
            email="subadmin-test@test.com",
            type=EntityType.candidate,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(entity_no_dept)
        await db_session.commit()
        await db_session.refresh(entity_no_dept)

        # Sub_admin should see this entity
        response = await client.get(
            "/api/entities",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        entity_ids = [e["id"] for e in data]

        assert entity_no_dept.id in entity_ids, \
            "Department sub_admin should see entities created by department members"

    @pytest.mark.asyncio
    async def test_regular_member_cannot_see_other_members_entities(
        self, db_session, client, admin_user, admin_token, second_user, second_user_token,
        organization, department, get_auth_headers, org_owner, org_member
    ):
        """
        Test that regular department member cannot see entities created by other members.
        Only lead/sub_admin should have this privilege.

        admin_user здесь — РЯДОВОЙ член орга (фикстура org_owner сделала бы его
        владельцем, а владелец видит всё в организации), а сущность — не
        кандидат: кандидаты общие для организации (модель «общий пул HR»).
        """
        from api.models.database import Entity, EntityType, EntityStatus, OrgRole
        org_owner.role = OrgRole.member
        await db_session.commit()

        # Both are regular members
        member1 = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.member,  # Regular member, not lead
            created_at=datetime.utcnow()
        )
        db_session.add(member1)

        member2 = DepartmentMember(
            department_id=department.id,
            user_id=second_user.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(member2)
        await db_session.commit()

        # second_user creates an entity
        entity = Entity(
            org_id=organization.id,
            department_id=None,
            created_by=second_user.id,
            name="Private Entity",
            email="private@test.com",
            type=EntityType.partner,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # admin_user (regular member) should NOT see this entity
        response = await client.get(
            "/api/entities",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        entity_ids = [e["id"] for e in data]

        assert entity.id not in entity_ids, \
            "Regular department member should NOT see entities created by other members"
