"""
Tests for Entity (contact) access control.
These tests verify that access_level (view/edit/full) is properly enforced.
"""
import pytest
from datetime import datetime

from api.models.database import (
    Entity, SharedAccess, AccessLevel, ResourceType,
    DepartmentMember, DeptRole, OrgMember, OrgRole, EntityType, EntityStatus
)


class TestEntityOwnerAccess:
    """Test entity access for owner."""

    @pytest.mark.asyncio
    async def test_owner_can_view_entity(self, client, admin_user, admin_token, entity, get_auth_headers, org_owner):
        """Test that entity owner can view their entity."""
        response = await client.get(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Contact"

    @pytest.mark.asyncio
    async def test_owner_can_update_entity(self, client, admin_user, admin_token, entity, get_auth_headers, org_owner):
        """Test that entity owner can update their entity."""
        response = await client.put(
            f"/api/entities/{entity.id}",
            json={"name": "Updated Contact", "type": "candidate"},
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Contact"

    @pytest.mark.asyncio
    async def test_owner_can_delete_entity(self, client, admin_user, admin_token, entity, get_auth_headers, org_owner):
        """Test that entity owner can delete their entity."""
        response = await client.delete(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200


class TestEntityViewAccess:
    """Test entity access with view permission - CRITICAL SECURITY TESTS."""

    @pytest.mark.asyncio
    async def test_view_user_can_see_entity(
        self, client, second_user, second_user_token, entity, entity_share_view, get_auth_headers, org_member
    ):
        """Test that user with view access can see entity."""
        response = await client.get(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_view_user_cannot_update_entity(
        self, client, second_user, second_user_token, entity, entity_share_view, get_auth_headers, org_member
    ):
        """
        CRITICAL TEST: User with view-only access should NOT be able to update entity.
        This test should PASS after security fix.
        """
        response = await client.put(
            f"/api/entities/{entity.id}",
            json={"name": "Hacked Name", "type": "candidate"},
            headers=get_auth_headers(second_user_token)
        )

        # Expected: 403 Forbidden
        # Current bug: might return 200
        assert response.status_code == 403, \
            f"SECURITY BUG: View-only user was able to update entity! Got {response.status_code}"

    @pytest.mark.asyncio
    async def test_view_user_cannot_delete_entity(
        self, client, second_user, second_user_token, entity, entity_share_view, get_auth_headers, org_member
    ):
        """
        CRITICAL TEST: User with view-only access should NOT be able to delete entity.
        This test documents the current bug - should FAIL until fixed.
        """
        response = await client.delete(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(second_user_token)
        )

        # Expected: 403 Forbidden
        # Current bug: returns 200 (deletes entity!)
        assert response.status_code == 403, \
            f"SECURITY BUG: View-only user was able to delete entity! Got {response.status_code}"

    @pytest.mark.asyncio
    async def test_view_user_cannot_link_chat(
        self, client, second_user, second_user_token, entity, entity_share_view,
        get_auth_headers, org_member, chat
    ):
        """
        CRITICAL TEST: User with view-only access should NOT be able to link chat to entity.
        """
        response = await client.post(
            f"/api/entities/{entity.id}/link-chat/{chat.id}",
            headers=get_auth_headers(second_user_token)
        )

        # Expected: 403 Forbidden
        assert response.status_code == 403, \
            f"SECURITY BUG: View-only user was able to link chat! Got {response.status_code}"


class TestEntityEditAccess:
    """Test entity access with edit permission."""

    @pytest.mark.asyncio
    async def test_edit_user_can_view_entity(
        self, client, second_user, second_user_token, entity, entity_share_edit, get_auth_headers, org_member
    ):
        """Test that user with edit access can view entity."""
        response = await client.get(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_edit_user_can_update_entity(
        self, client, second_user, second_user_token, entity, entity_share_edit, get_auth_headers, org_member
    ):
        """Test that user with edit access can update entity."""
        response = await client.put(
            f"/api/entities/{entity.id}",
            json={"name": "Legitimately Updated", "type": "candidate"},
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_edit_user_cannot_delete_entity(
        self, client, second_user, second_user_token, entity, entity_share_edit, get_auth_headers, org_member
    ):
        """
        Test that user with edit access should NOT be able to delete entity.
        Only owner or full access should allow deletion.
        """
        response = await client.delete(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(second_user_token)
        )

        # Edit permission should NOT allow delete - only owner or full access
        assert response.status_code == 403, \
            f"Edit user should not be able to delete. Got {response.status_code}"


class TestEntityNoAccess:
    """Test entity access for users without any share."""

    @pytest.mark.asyncio
    async def test_no_access_user_cannot_view_entity(
        self, db_session, client, second_user, second_user_token, entity, get_auth_headers, org_member
    ):
        """Test that user without share cannot view a non-candidate entity (not in their dept).

        Кандидат (фикстура entity) — общий для организации: его читает любой
        член орга (модель «общий пул HR»). Закрытым без шаринга остаётся
        контакт другого типа.
        """
        response = await client.get(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(second_user_token)
        )
        assert response.status_code == 200

        entity.type = EntityType.partner
        await db_session.commit()

        response = await client.get(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(second_user_token)
        )

        # Expected: 403 or 404
        assert response.status_code in [403, 404], \
            f"User without access should not see entity. Got {response.status_code}"

    @pytest.mark.asyncio
    async def test_no_access_user_cannot_update_entity(
        self, client, second_user, second_user_token, entity, get_auth_headers, org_member
    ):
        """Test that user without share cannot update entity."""
        response = await client.put(
            f"/api/entities/{entity.id}",
            json={"name": "Hacked", "type": "candidate"},
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_no_access_user_cannot_delete_entity(
        self, client, second_user, second_user_token, entity, get_auth_headers, org_member
    ):
        """Test that user without share cannot delete entity."""
        response = await client.delete(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(second_user_token)
        )

        # Current bug: might return 200 because only org_id is checked
        assert response.status_code in [403, 404], \
            f"User without access should not delete entity. Got {response.status_code}"


class TestEntityExpiredShare:
    """Test that expired shares don't grant access."""

    @pytest.mark.asyncio
    async def test_expired_share_no_edit_access(
        self, client, second_user, second_user_token, entity, expired_share, get_auth_headers, org_member
    ):
        """Test that expired share does not grant edit access."""
        response = await client.put(
            f"/api/entities/{entity.id}",
            json={"name": "Using expired share", "type": "candidate"},
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 403, \
            f"Expired share should not grant access. Got {response.status_code}"


class TestEntityCrossOrganization:
    """Test that users cannot access entities from other organizations."""

    @pytest.mark.asyncio
    async def test_cannot_access_entity_from_other_org(
        self, db_session, client, second_user, second_user_token, second_organization, get_auth_headers
    ):
        """Test that user cannot access entity from different organization."""
        # Create entity in second organization
        other_entity = Entity(
            org_id=second_organization.id,
            name="Other Org Contact",
            type="candidate",
            status="active",
            created_by=1,  # Some user
            created_at=datetime.utcnow()
        )
        db_session.add(other_entity)
        await db_session.commit()
        await db_session.refresh(other_entity)

        response = await client.get(
            f"/api/entities/{other_entity.id}",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code in [403, 404], \
            f"User should not access entity from other org. Got {response.status_code}"


class TestEntityListFiltering:
    """Test that entity list properly filters by access."""

    @pytest.mark.asyncio
    async def test_list_shows_only_accessible_entities(
        self, client, second_user, second_user_token, entity, second_entity,
        get_auth_headers, org_member, dept_member
    ):
        """Test that entity list only shows entities user has access to."""
        response = await client.get(
            "/api/entities",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Should only see entities they own or have share/dept access to
        entity_ids = [e["id"] for e in data]

        # second_entity is owned by second_user, so should be visible
        assert second_entity.id in entity_ids, "User should see their own entity"

    @pytest.mark.asyncio
    async def test_list_shows_shared_entities(
        self, client, second_user, second_user_token, entity, entity_share_view,
        get_auth_headers, org_member
    ):
        """Test that shared entities appear in list."""
        response = await client.get(
            "/api/entities",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()

        entity_ids = [e["id"] for e in data]
        assert entity.id in entity_ids, "User should see shared entity"


class TestEntityOrgRoleAccess:
    """Test entity access based on organization role."""

    @pytest.mark.asyncio
    async def test_org_owner_can_access_all_entities(
        self, client, admin_user, admin_token, entity, second_entity, get_auth_headers, org_owner
    ):
        """Test that org owner can access all entities in org."""
        response = await client.get(
            f"/api/entities/{second_entity.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_org_owner_can_delete_any_entity(
        self, client, admin_user, admin_token, second_entity, get_auth_headers, org_owner
    ):
        """Test that org owner can delete any entity in org."""
        response = await client.delete(
            f"/api/entities/{second_entity.id}",
            headers=get_auth_headers(admin_token)
        )

        # Org owner should be able to delete
        assert response.status_code == 200


class TestEntityDepartmentAccess:
    """Test entity access based on department membership."""

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Requires entity-specific department viewing logic - members can view dept entities but not other resources")
    async def test_dept_member_can_view_dept_entities(
        self, client, regular_user, user_token, entity, get_auth_headers, org_admin, dept_member
    ):
        """Test that department member can view entities in their department."""
        response = await client.get(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(user_token)
        )

        # If user is in same department as entity, should be able to view
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dept_member_cannot_view_other_dept_entities(
        self, db_session, client, regular_user, user_token, second_department,
        organization, admin_user, get_auth_headers, org_admin
    ):
        """Test that department member cannot view entities from other department."""
        # Create entity in second department
        other_entity = Entity(
            org_id=organization.id,
            department_id=second_department.id,
            name="Other Dept Contact",
            # Не кандидат: кандидаты общие для орга и видны из любого отдела.
            type="partner",
            status="active",
            created_by=admin_user.id,
            created_at=datetime.utcnow()
        )
        db_session.add(other_entity)
        await db_session.commit()
        await db_session.refresh(other_entity)

        response = await client.get(
            f"/api/entities/{other_entity.id}",
            headers=get_auth_headers(user_token)
        )

        # User is not in second_department, should not see
        # Current bug: might return 200 because only org_id is checked
        assert response.status_code in [403, 404], \
            f"User should not see entity from other dept. Got {response.status_code}"


class TestDepartmentAdminContactVisibility:
    """Test that department admin/lead can see contacts created by department members.

    This is a critical test for the fix of dept_user_ids undefined variable bug.
    """

    @pytest.mark.asyncio
    async def test_dept_lead_sees_contacts_created_by_dept_members(
        self, db_session, client, organization, department, admin_user, admin_token,
        regular_user, user_token, get_auth_headers
    ):
        """
        Test that department lead can see contacts created by department members in list.

        Scenario:
        1. admin_user is lead of department
        2. regular_user is member of same department
        3. regular_user creates a contact (without department_id)
        4. admin_user (lead) should see this contact in their list
        """
        # Setup: make admin_user lead of department
        dept_lead = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_lead)

        # Setup: make regular_user member of same department
        dept_member = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_member)

        # Setup: add admin_user to organization as admin (not owner to test dept access)
        org_admin = OrgMember(
            org_id=organization.id,
            user_id=admin_user.id,
            role=OrgRole.admin,
            created_at=datetime.utcnow()
        )
        db_session.add(org_admin)

        # Setup: add regular_user to organization as member
        org_member = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(org_member)

        await db_session.commit()

        # Create entity by regular_user (department member) - without department_id!
        member_entity = Entity(
            org_id=organization.id,
            department_id=None,  # No department_id - should still be visible to lead
            created_by=regular_user.id,
            name="Contact By Member",
            email="member-contact@test.com",
            type=EntityType.candidate,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(member_entity)
        await db_session.commit()
        await db_session.refresh(member_entity)

        # Test: admin_user (lead) should see this contact
        response = await client.get(
            "/api/entities",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        entity_ids = [e["id"] for e in data]
        assert member_entity.id in entity_ids, \
            f"Dept lead should see contact created by dept member. Got entities: {entity_ids}"

    @pytest.mark.asyncio
    async def test_dept_sub_admin_sees_contacts_created_by_dept_members(
        self, db_session, client, organization, department, admin_user, admin_token,
        regular_user, get_auth_headers
    ):
        """
        Test that department sub_admin can see contacts created by department members.
        """
        # Setup: make admin_user sub_admin of department
        dept_sub_admin = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.sub_admin,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_sub_admin)

        # Setup: make regular_user member of same department
        dept_member = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_member)

        # Setup: add admin_user to organization as admin
        org_admin = OrgMember(
            org_id=organization.id,
            user_id=admin_user.id,
            role=OrgRole.admin,
            created_at=datetime.utcnow()
        )
        db_session.add(org_admin)

        # Setup: add regular_user to organization as member
        org_member = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(org_member)

        await db_session.commit()

        # Create entity by regular_user (department member) - without department_id!
        member_entity = Entity(
            org_id=organization.id,
            department_id=None,
            created_by=regular_user.id,
            name="Contact By Member 2",
            email="member-contact2@test.com",
            type=EntityType.client,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(member_entity)
        await db_session.commit()
        await db_session.refresh(member_entity)

        # Test: admin_user (sub_admin) should see this contact
        response = await client.get(
            "/api/entities",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        entity_ids = [e["id"] for e in data]
        assert member_entity.id in entity_ids, \
            f"Dept sub_admin should see contact created by dept member. Got entities: {entity_ids}"

    @pytest.mark.asyncio
    async def test_dept_lead_sees_contacts_with_department_id(
        self, db_session, client, organization, department, admin_user, admin_token,
        get_auth_headers, second_user
    ):
        """
        Test that department lead can see contacts explicitly assigned to their department.
        """
        # Setup: make admin_user lead of department
        dept_lead = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_lead)

        # Setup: add admin_user to organization as admin
        org_admin = OrgMember(
            org_id=organization.id,
            user_id=admin_user.id,
            role=OrgRole.admin,
            created_at=datetime.utcnow()
        )
        db_session.add(org_admin)

        await db_session.commit()

        # Create entity with department_id set (created by someone else)
        dept_entity = Entity(
            org_id=organization.id,
            department_id=department.id,  # Explicitly in the department
            # Другой, но СУЩЕСТВУЮЩИЙ пользователь: в тестовой SQLite включены
            # внешние ключи, и несуществующий id 999 ронял вставку.
            created_by=second_user.id,
            name="Dept Contact",
            email="dept-contact@test.com",
            type=EntityType.partner,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_entity)
        await db_session.commit()
        await db_session.refresh(dept_entity)

        # Test: admin_user (lead) should see this contact
        response = await client.get(
            "/api/entities",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        entity_ids = [e["id"] for e in data]
        assert dept_entity.id in entity_ids, \
            f"Dept lead should see contact in their department. Got entities: {entity_ids}"
