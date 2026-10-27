"""
Tests for custom roles and permissions system (/api/admin/custom-roles…).

Переписано 24.10.2026 под НАСТОЯЩИЙ контракт ручек (api/routes/admin/custom_roles.py).
Прежний файл был спецификацией другого дизайна, который так и не сделали:
вложенные права «ресурс → действие» (`{"entities": {"read": true}}`), 201 на
создание и привязку, 204 на удаление. Реализация устроена иначе:
- роль наследует права БАЗОВОЙ роли (`base_role`: owner/admin/sub_admin/member,
  поле обязательное), права — плоские ключи вида `can_share_resources`;
- переопределение — `POST …/permissions {"permission": key, "allowed": bool}`,
  снятие — `DELETE …/permissions/{key}` (возврат к значению базовой роли);
- удаление роли мягкое: `is_active=False`, ответ 200 с телом;
- создание/привязка отвечают 200.
Имена тестов и их смысл (CRUD только суперадмину, переопределения, привязка к
людям, слияние с правами по умолчанию, журнал, граничные случаи) сохранены.

Endpoints:
- POST /api/admin/custom-roles
- GET /api/admin/custom-roles
- GET /api/admin/custom-roles/{id}
- PATCH /api/admin/custom-roles/{id}
- DELETE /api/admin/custom-roles/{id}
- POST /api/admin/custom-roles/{id}/permissions
- DELETE /api/admin/custom-roles/{id}/permissions/{permission}
- POST /api/admin/custom-roles/{id}/assign/{user_id}
- DELETE /api/admin/custom-roles/{id}/assign/{user_id}
- GET /api/admin/permission-audit-logs
- GET /api/admin/me/permissions
"""
import pytest
from datetime import datetime
from httpx import AsyncClient

from api.models.database import User, Organization, OrgMember, OrgRole
from api.services.auth import create_access_token


BASE = "/api/admin/custom-roles"


def _token(user: User) -> str:
    return create_access_token(data={"sub": str(user.id)})


async def _create_role(client, headers, org_id, name="Custom Manager", base_role="member", **extra):
    payload = {"name": name, "description": f"{name} description", "base_role": base_role, "org_id": org_id}
    payload.update(extra)
    response = await client.post(BASE, json=payload, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# ============================================================================
# TEST CLASS: CustomRole CRUD Operations
# ============================================================================

@pytest.mark.asyncio
class TestCustomRoleCRUD:
    """Tests for CustomRole CRUD operations - superadmin only."""

    async def test_create_custom_role_as_superadmin(
        self, client: AsyncClient, superadmin_user: User, organization: Organization,
        superadmin_org_member: OrgMember, get_auth_headers
    ):
        """Test creating a custom role as superadmin - should succeed."""
        headers = get_auth_headers(_token(superadmin_user))
        response = await client.post(BASE, json={
            "name": "Custom Manager",
            "description": "Custom role for managers with specific permissions",
            "base_role": "admin",
            "org_id": organization.id,
        }, headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] > 0
        assert data["name"] == "Custom Manager"
        assert data["base_role"] == "admin"
        assert data["org_id"] == organization.id
        assert data["is_active"] is True
        # Права базовой роли приходят сразу
        assert data["permissions"]["can_access_admin_panel"] is True
        assert data["permissions"]["can_view_all_orgs"] is False

    async def test_create_custom_role_as_non_superadmin(
        self, client: AsyncClient, admin_user: User, organization: Organization,
        org_owner: OrgMember, get_auth_headers
    ):
        """Test creating a custom role as non-superadmin - should fail with 403."""
        response = await client.post(BASE, json={
            "name": "Custom Manager", "description": "Test role",
            "base_role": "member", "org_id": organization.id,
        }, headers=get_auth_headers(_token(admin_user)))

        assert response.status_code == 403
        assert "superadmin" in response.json()["detail"].lower()

    async def test_create_custom_role_without_authentication(
        self, client: AsyncClient, organization: Organization
    ):
        """Test creating custom role without authentication - should fail with 401."""
        response = await client.post(BASE, json={
            "name": "Custom Manager", "description": "Test role",
            "base_role": "member", "org_id": organization.id,
        })
        assert response.status_code == 401

    async def test_create_duplicate_role_name(
        self, client: AsyncClient, superadmin_user: User, organization: Organization,
        superadmin_org_member: OrgMember, get_auth_headers
    ):
        """Test creating duplicate role name in same org - should fail with 409."""
        headers = get_auth_headers(_token(superadmin_user))
        await _create_role(client, headers, organization.id, name="Duplicate Role")

        response = await client.post(BASE, json={
            "name": "Duplicate Role", "description": "Second",
            "base_role": "member", "org_id": organization.id,
        }, headers=headers)
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    async def test_create_custom_role_with_invalid_permissions(
        self, client: AsyncClient, superadmin_user: User, organization: Organization,
        superadmin_org_member: OrgMember, get_auth_headers
    ):
        """Test creating custom role with invalid base role - should fail validation."""
        response = await client.post(BASE, json={
            "name": "Invalid Role", "description": "Role with invalid base role",
            "base_role": "god_mode", "org_id": organization.id,
        }, headers=get_auth_headers(_token(superadmin_user)))
        assert response.status_code == 422

    async def test_get_custom_roles_list(
        self, client: AsyncClient, superadmin_user: User, organization: Organization,
        superadmin_org_member: OrgMember, get_auth_headers
    ):
        """Test retrieving list of custom roles."""
        headers = get_auth_headers(_token(superadmin_user))
        for i in range(2):
            await _create_role(client, headers, organization.id, name=f"Role {i}")

        response = await client.get(BASE, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2
        assert {"Role 0", "Role 1"} <= {r["name"] for r in data}
        assert all("permissions" in r for r in data)

    async def test_get_custom_roles_list_filter_by_org(
        self, client: AsyncClient, superadmin_user: User, organization: Organization,
        second_organization: Organization, superadmin_org_member: OrgMember, get_auth_headers
    ):
        """Test that custom roles list is filtered by organization."""
        headers = get_auth_headers(_token(superadmin_user))
        await _create_role(client, headers, organization.id, name="Org1 Role")
        await _create_role(client, headers, second_organization.id, name="Org2 Role")

        response = await client.get(f"{BASE}?org_id={organization.id}", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Org1 Role"
        assert data[0]["org_id"] == organization.id

    async def test_get_custom_role_by_id(
        self, client: AsyncClient, superadmin_user: User, organization: Organization,
        superadmin_org_member: OrgMember, get_auth_headers
    ):
        """Test retrieving a specific custom role by ID."""
        headers = get_auth_headers(_token(superadmin_user))
        role = await _create_role(client, headers, organization.id, name="Specific Role")

        response = await client.get(f"{BASE}/{role['id']}", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == role["id"]
        assert data["name"] == "Specific Role"
        assert data["permissions"] == role["permissions"]

    async def test_get_custom_role_not_found(
        self, client: AsyncClient, superadmin_user: User,
        superadmin_org_member: OrgMember, get_auth_headers
    ):
        """Test retrieving non-existent role - should return 404."""
        response = await client.get(f"{BASE}/99999", headers=get_auth_headers(_token(superadmin_user)))
        assert response.status_code == 404

    async def test_update_custom_role(
        self, client: AsyncClient, superadmin_user: User, organization: Organization,
        superadmin_org_member: OrgMember, get_auth_headers
    ):
        """Test updating a custom role."""
        headers = get_auth_headers(_token(superadmin_user))
        role = await _create_role(client, headers, organization.id, name="Original Name")

        response = await client.patch(f"{BASE}/{role['id']}", json={
            "name": "Updated Name", "description": "Updated description", "is_active": False,
        }, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["description"] == "Updated description"
        assert data["is_active"] is False

    async def test_update_custom_role_as_non_superadmin(
        self, client: AsyncClient, superadmin_user: User, admin_user: User,
        organization: Organization, superadmin_org_member: OrgMember, org_owner: OrgMember,
        get_auth_headers
    ):
        """Test updating custom role as non-superadmin - should fail with 403."""
        role = await _create_role(client, get_auth_headers(_token(superadmin_user)), organization.id)

        response = await client.patch(f"{BASE}/{role['id']}", json={"name": "Hacked"},
                                      headers=get_auth_headers(_token(admin_user)))
        assert response.status_code == 403

    async def test_delete_custom_role(
        self, client: AsyncClient, superadmin_user: User, organization: Organization,
        superadmin_org_member: OrgMember, get_auth_headers
    ):
        """Test deleting a custom role (soft delete: is_active=False)."""
        headers = get_auth_headers(_token(superadmin_user))
        role = await _create_role(client, headers, organization.id, name="To Delete")

        response = await client.delete(f"{BASE}/{role['id']}", headers=headers)
        assert response.status_code == 200
        assert response.json()["is_active"] is False

        # Роль осталась, но выключена; в списке активных её нет
        get_response = await client.get(f"{BASE}/{role['id']}", headers=headers)
        assert get_response.status_code == 200
        assert get_response.json()["is_active"] is False
        active = await client.get(f"{BASE}?is_active=true", headers=headers)
        assert role["id"] not in [r["id"] for r in active.json()]

    async def test_delete_custom_role_as_non_superadmin(
        self, client: AsyncClient, superadmin_user: User, admin_user: User,
        organization: Organization, superadmin_org_member: OrgMember, org_owner: OrgMember,
        get_auth_headers
    ):
        """Test deleting custom role as non-superadmin - should fail with 403."""
        role = await _create_role(client, get_auth_headers(_token(superadmin_user)), organization.id)

        response = await client.delete(f"{BASE}/{role['id']}", headers=get_auth_headers(_token(admin_user)))
        assert response.status_code == 403


# ============================================================================
# TEST CLASS: Permission Overrides
# ============================================================================

@pytest.mark.asyncio
class TestPermissionOverrides:
    """Tests for managing permission overrides on custom roles."""

    async def test_add_permission_override(
        self, client: AsyncClient, superadmin_user: User, organization: Organization,
        superadmin_org_member: OrgMember, get_auth_headers
    ):
        """Test adding a permission override to a custom role."""
        headers = get_auth_headers(_token(superadmin_user))
        role = await _create_role(client, headers, organization.id, base_role="member")
        assert role["permissions"]["can_share_resources"] is False

        response = await client.post(f"{BASE}/{role['id']}/permissions",
                                     json={"permission": "can_share_resources", "allowed": True},
                                     headers=headers)
        assert response.status_code == 200
        assert response.json()["allowed"] is True

        data = (await client.get(f"{BASE}/{role['id']}", headers=headers)).json()
        assert data["permissions"]["can_share_resources"] is True

    async def test_update_permission_override(
        self, client: AsyncClient, superadmin_user: User, organization: Organization,
        superadmin_org_member: OrgMember, get_auth_headers
    ):
        """Test updating an existing permission override."""
        headers = get_auth_headers(_token(superadmin_user))
        role = await _create_role(client, headers, organization.id, base_role="member")
        url = f"{BASE}/{role['id']}/permissions"
        await client.post(url, json={"permission": "can_view_chats", "allowed": False}, headers=headers)

        response = await client.post(url, json={"permission": "can_view_chats", "allowed": True}, headers=headers)
        assert response.status_code == 200
        assert "updated" in response.json()["message"]

        data = (await client.get(f"{BASE}/{role['id']}", headers=headers)).json()
        assert data["permissions"]["can_view_chats"] is True
        # Остальное — как у базовой роли
        assert data["permissions"]["can_view_contacts"] is True

    async def test_remove_permission_override(
        self, client: AsyncClient, superadmin_user: User, organization: Organization,
        superadmin_org_member: OrgMember, get_auth_headers
    ):
        """Test removing a permission override from a custom role."""
        headers = get_auth_headers(_token(superadmin_user))
        role = await _create_role(client, headers, organization.id, base_role="member")
        await client.post(f"{BASE}/{role['id']}/permissions",
                          json={"permission": "can_view_calls", "allowed": False}, headers=headers)

        response = await client.delete(f"{BASE}/{role['id']}/permissions/can_view_calls", headers=headers)
        assert response.status_code == 200
        assert response.json()["reverted_to"] is True

        data = (await client.get(f"{BASE}/{role['id']}", headers=headers)).json()
        assert data["permissions"]["can_view_calls"] is True

        # Снять несуществующее переопределение — 404
        again = await client.delete(f"{BASE}/{role['id']}/permissions/can_view_calls", headers=headers)
        assert again.status_code == 404

    async def test_get_role_with_permissions(
        self, client: AsyncClient, superadmin_user: User, organization: Organization,
        superadmin_org_member: OrgMember, get_auth_headers
    ):
        """Test retrieving a role returns complete permission structure."""
        headers = get_auth_headers(_token(superadmin_user))
        role = await _create_role(client, headers, organization.id, name="Complex Role", base_role="member")
        url = f"{BASE}/{role['id']}/permissions"
        await client.post(url, json={"permission": "can_share_resources", "allowed": True}, headers=headers)
        await client.post(url, json={"permission": "can_view_calls", "allowed": False}, headers=headers)

        response = await client.get(f"{BASE}/{role['id']}", headers=headers)
        assert response.status_code == 200
        perms = response.json()["permissions"]
        # Полный набор ключей базовой роли — на месте
        assert set(perms) == set(role["permissions"])
        assert perms["can_share_resources"] is True
        assert perms["can_view_calls"] is False
        assert perms["can_view_chats"] is True

    async def test_invalid_permission_key_rejected(
        self, client: AsyncClient, superadmin_user: User, organization: Organization,
        superadmin_org_member: OrgMember, get_auth_headers
    ):
        """Unknown permission key - 400."""
        headers = get_auth_headers(_token(superadmin_user))
        role = await _create_role(client, headers, organization.id)
        response = await client.post(f"{BASE}/{role['id']}/permissions",
                                     json={"permission": "entities.create", "allowed": True}, headers=headers)
        assert response.status_code == 400


# ============================================================================
# TEST CLASS: User Role Assignment
# ============================================================================

@pytest.mark.asyncio
class TestUserRoleAssignment:
    """Tests for assigning custom roles to users."""

    async def test_assign_custom_role_to_user(
        self, client: AsyncClient, superadmin_user: User, regular_user: User,
        organization: Organization, superadmin_org_member: OrgMember, org_admin: OrgMember,
        get_auth_headers
    ):
        """Test assigning a custom role to a user."""
        headers = get_auth_headers(_token(superadmin_user))
        role = await _create_role(client, headers, organization.id)

        response = await client.post(f"{BASE}/{role['id']}/assign/{regular_user.id}", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["role_id"] == role["id"]
        assert data["user_id"] == regular_user.id

    async def test_assign_custom_role_as_non_superadmin(
        self, client: AsyncClient, superadmin_user: User, admin_user: User, regular_user: User,
        organization: Organization, superadmin_org_member: OrgMember, org_owner: OrgMember,
        get_auth_headers
    ):
        """Test assigning custom role as non-superadmin - should fail with 403."""
        role = await _create_role(client, get_auth_headers(_token(superadmin_user)), organization.id)

        response = await client.post(f"{BASE}/{role['id']}/assign/{regular_user.id}",
                                     headers=get_auth_headers(_token(admin_user)))
        assert response.status_code == 403

    async def test_assign_duplicate_role_to_user(
        self, client: AsyncClient, superadmin_user: User, regular_user: User,
        organization: Organization, superadmin_org_member: OrgMember, org_admin: OrgMember,
        get_auth_headers
    ):
        """Test assigning same role twice to same user - should handle gracefully (409)."""
        headers = get_auth_headers(_token(superadmin_user))
        role = await _create_role(client, headers, organization.id)
        url = f"{BASE}/{role['id']}/assign/{regular_user.id}"

        assert (await client.post(url, headers=headers)).status_code == 200
        response = await client.post(url, headers=headers)
        assert response.status_code == 409

    async def test_remove_custom_role_from_user(
        self, client: AsyncClient, superadmin_user: User, regular_user: User,
        organization: Organization, superadmin_org_member: OrgMember, org_admin: OrgMember,
        get_auth_headers
    ):
        """Test removing a custom role from a user."""
        headers = get_auth_headers(_token(superadmin_user))
        role = await _create_role(client, headers, organization.id)
        url = f"{BASE}/{role['id']}/assign/{regular_user.id}"
        await client.post(url, headers=headers)

        response = await client.delete(url, headers=headers)
        assert response.status_code == 200
        assert response.json()["user_id"] == regular_user.id

    async def test_remove_non_existent_role_assignment(
        self, client: AsyncClient, superadmin_user: User, regular_user: User,
        organization: Organization, superadmin_org_member: OrgMember, org_admin: OrgMember,
        get_auth_headers
    ):
        """Test removing role assignment that doesn't exist - should return 404."""
        headers = get_auth_headers(_token(superadmin_user))
        role = await _create_role(client, headers, organization.id)

        response = await client.delete(f"{BASE}/{role['id']}/assign/{regular_user.id}", headers=headers)
        assert response.status_code == 404

    async def test_user_with_custom_role_gets_permissions(
        self, client: AsyncClient, superadmin_user: User, regular_user: User,
        organization: Organization, superadmin_org_member: OrgMember, org_admin: OrgMember,
        get_auth_headers
    ):
        """Test that user with custom role receives correct permissions."""
        headers = get_auth_headers(_token(superadmin_user))
        role = await _create_role(client, headers, organization.id, name="Sharer", base_role="member")
        await client.post(f"{BASE}/{role['id']}/permissions",
                          json={"permission": "can_share_resources", "allowed": True}, headers=headers)
        await client.post(f"{BASE}/{role['id']}/assign/{regular_user.id}", headers=headers)

        response = await client.get("/api/admin/me/permissions",
                                    headers=get_auth_headers(_token(regular_user)))
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "custom_role"
        assert data["custom_role_id"] == role["id"]
        assert data["custom_role_name"] == "Sharer"
        assert data["permissions"]["can_share_resources"] is True


# ============================================================================
# TEST CLASS: Fallback Behavior
# ============================================================================

@pytest.mark.asyncio
class TestFallbackBehavior:
    """Tests for permission fallback and merging with default permissions."""

    async def test_user_without_custom_role_uses_default_permissions(
        self, client: AsyncClient, regular_user: User, organization: Organization,
        org_admin: OrgMember, get_auth_headers
    ):
        """Test that user without custom role uses default role permissions."""
        response = await client.get("/api/admin/me/permissions",
                                    headers=get_auth_headers(_token(regular_user)))
        assert response.status_code == 200
        data = response.json()
        assert data["source"] in ("user_role", "dept_role")
        assert data["custom_role_id"] is None
        assert isinstance(data["permissions"], dict) and data["permissions"]

    async def test_custom_role_overrides_default_permission(
        self, client: AsyncClient, superadmin_user: User, regular_user: User,
        organization: Organization, superadmin_org_member: OrgMember, org_admin: OrgMember,
        get_auth_headers
    ):
        """Test that custom role permissions override default role permissions."""
        user_headers = get_auth_headers(_token(regular_user))
        default = (await client.get("/api/admin/me/permissions", headers=user_headers)).json()
        assert default["permissions"]["can_view_chats"] is True

        headers = get_auth_headers(_token(superadmin_user))
        role = await _create_role(client, headers, organization.id, base_role="member")
        await client.post(f"{BASE}/{role['id']}/permissions",
                          json={"permission": "can_view_chats", "allowed": False}, headers=headers)
        await client.post(f"{BASE}/{role['id']}/assign/{regular_user.id}", headers=headers)

        data = (await client.get("/api/admin/me/permissions", headers=user_headers)).json()
        assert data["permissions"]["can_view_chats"] is False

    async def test_partial_override_merges_with_defaults(
        self, client: AsyncClient, superadmin_user: User, regular_user: User,
        organization: Organization, superadmin_org_member: OrgMember, org_admin: OrgMember,
        get_auth_headers
    ):
        """Test that partial permission overrides merge with default permissions."""
        headers = get_auth_headers(_token(superadmin_user))
        role = await _create_role(client, headers, organization.id, base_role="member")
        await client.post(f"{BASE}/{role['id']}/permissions",
                          json={"permission": "can_share_resources", "allowed": True}, headers=headers)
        await client.post(f"{BASE}/{role['id']}/assign/{regular_user.id}", headers=headers)

        data = (await client.get("/api/admin/me/permissions",
                                 headers=get_auth_headers(_token(regular_user)))).json()
        perms = data["permissions"]
        assert perms["can_share_resources"] is True      # переопределено
        assert perms["can_view_contacts"] is True        # от базовой роли
        assert perms["can_delete_users"] is False        # от базовой роли
        assert set(perms) == set(role["permissions"])


# ============================================================================
# TEST CLASS: Audit Logging
# ============================================================================

@pytest.mark.asyncio
class TestAuditLogging:
    """Tests for audit logging of role and permission changes."""

    async def _logs(self, client, headers, **params):
        query = "&".join(f"{k}={v}" for k, v in params.items())
        response = await client.get(f"/api/admin/permission-audit-logs?{query}", headers=headers)
        assert response.status_code == 200
        return response.json()

    async def test_role_creation_logged(
        self, client: AsyncClient, superadmin_user: User, organization: Organization,
        superadmin_org_member: OrgMember, get_auth_headers
    ):
        """Test that role creation is logged in audit trail."""
        headers = get_auth_headers(_token(superadmin_user))
        role = await _create_role(client, headers, organization.id, name="Logged Role")

        logs = await self._logs(client, headers, role_id=role["id"])
        creation = [l for l in logs if l["action"] == "create_custom_role"]
        assert len(creation) == 1
        assert creation[0]["changed_by_id"] == superadmin_user.id
        assert creation[0]["details"]["name"] == "Logged Role"

    async def test_permission_change_logged(
        self, client: AsyncClient, superadmin_user: User, organization: Organization,
        superadmin_org_member: OrgMember, get_auth_headers
    ):
        """Test that permission changes are logged in audit trail."""
        headers = get_auth_headers(_token(superadmin_user))
        role = await _create_role(client, headers, organization.id)
        await client.post(f"{BASE}/{role['id']}/permissions",
                          json={"permission": "can_share_resources", "allowed": True}, headers=headers)

        logs = await self._logs(client, headers, role_id=role["id"])
        change = [l for l in logs if l["action"] == "add_permission_override"]
        assert len(change) == 1
        assert change[0]["details"] == {
            "permission": "can_share_resources", "old_value": False, "new_value": True,
        }

    async def test_role_assignment_logged(
        self, client: AsyncClient, superadmin_user: User, regular_user: User,
        organization: Organization, superadmin_org_member: OrgMember, org_admin: OrgMember,
        get_auth_headers
    ):
        """Test that role assignments are logged in audit trail."""
        headers = get_auth_headers(_token(superadmin_user))
        role = await _create_role(client, headers, organization.id)
        await client.post(f"{BASE}/{role['id']}/assign/{regular_user.id}", headers=headers)

        logs = await self._logs(client, headers, role_id=role["id"])
        assignment = [l for l in logs if l["action"] == "assign_custom_role"]
        assert len(assignment) == 1
        assert assignment[0]["user_id"] == regular_user.id

    async def test_get_audit_logs_as_superadmin(
        self, client: AsyncClient, superadmin_user: User,
        superadmin_org_member: OrgMember, get_auth_headers
    ):
        """Test that superadmin can access audit logs."""
        response = await client.get("/api/admin/permission-audit-logs",
                                    headers=get_auth_headers(_token(superadmin_user)))
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_get_audit_logs_as_non_superadmin(
        self, client: AsyncClient, admin_user: User, org_owner: OrgMember, get_auth_headers
    ):
        """Test that non-superadmin cannot access audit logs."""
        response = await client.get("/api/admin/permission-audit-logs",
                                    headers=get_auth_headers(_token(admin_user)))
        assert response.status_code == 403

    async def test_audit_logs_filter_by_role(
        self, client: AsyncClient, superadmin_user: User, organization: Organization,
        superadmin_org_member: OrgMember, get_auth_headers
    ):
        """Test filtering audit logs by role ID."""
        headers = get_auth_headers(_token(superadmin_user))
        role1 = await _create_role(client, headers, organization.id, name="Role One")
        await _create_role(client, headers, organization.id, name="Role Two")

        logs = await self._logs(client, headers, role_id=role1["id"])
        assert logs
        assert all(l["custom_role_id"] == role1["id"] for l in logs)

    async def test_audit_logs_pagination(
        self, client: AsyncClient, superadmin_user: User, organization: Organization,
        superadmin_org_member: OrgMember, get_auth_headers
    ):
        """Test pagination of audit logs."""
        headers = get_auth_headers(_token(superadmin_user))
        for i in range(5):
            await _create_role(client, headers, organization.id, name=f"Role {i}")

        page1 = await self._logs(client, headers, limit=3, offset=0)
        page2 = await self._logs(client, headers, limit=3, offset=3)
        assert len(page1) == 3
        assert len(page2) == 2
        assert not {l["id"] for l in page1} & {l["id"] for l in page2}


# ============================================================================
# TEST CLASS: Edge Cases and Validation
# ============================================================================

@pytest.mark.asyncio
class TestEdgeCasesAndValidation:
    """Tests for edge cases and input validation."""

    async def test_create_role_with_empty_name(
        self, client: AsyncClient, superadmin_user: User, organization: Organization,
        superadmin_org_member: OrgMember, get_auth_headers
    ):
        """Test creating role with empty name - should fail validation."""
        response = await client.post(BASE, json={
            "name": "", "description": "Test", "base_role": "member", "org_id": organization.id,
        }, headers=get_auth_headers(_token(superadmin_user)))
        assert response.status_code == 422

    async def test_create_role_with_invalid_org_id(
        self, client: AsyncClient, superadmin_user: User,
        superadmin_org_member: OrgMember, get_auth_headers
    ):
        """Test creating role with non-existent org ID - should fail."""
        response = await client.post(BASE, json={
            "name": "Test Role", "description": "Test", "base_role": "member", "org_id": 99999,
        }, headers=get_auth_headers(_token(superadmin_user)))
        assert response.status_code == 404

    async def test_assign_role_to_non_existent_user(
        self, client: AsyncClient, superadmin_user: User, organization: Organization,
        superadmin_org_member: OrgMember, get_auth_headers
    ):
        """Test assigning role to non-existent user - should fail."""
        headers = get_auth_headers(_token(superadmin_user))
        role = await _create_role(client, headers, organization.id)

        response = await client.post(f"{BASE}/{role['id']}/assign/99999", headers=headers)
        assert response.status_code == 404

    async def test_delete_role_with_assigned_users(
        self, client: AsyncClient, superadmin_user: User, regular_user: User,
        organization: Organization, superadmin_org_member: OrgMember, org_admin: OrgMember,
        get_auth_headers
    ):
        """Test deleting role that is assigned to users - should handle gracefully.

        Удаление мягкое: роль выключается, и человек с ней возвращается к правам
        по умолчанию (me/permissions учитывает только активные роли). Новую
        привязку выключенной роли сервер не даёт.
        """
        headers = get_auth_headers(_token(superadmin_user))
        role = await _create_role(client, headers, organization.id)
        await client.post(f"{BASE}/{role['id']}/assign/{regular_user.id}", headers=headers)

        response = await client.delete(f"{BASE}/{role['id']}", headers=headers)
        assert response.status_code == 200

        perms = (await client.get("/api/admin/me/permissions",
                                  headers=get_auth_headers(_token(regular_user)))).json()
        assert perms["custom_role_id"] is None

        again = await client.post(f"{BASE}/{role['id']}/assign/{superadmin_user.id}", headers=headers)
        assert again.status_code == 400

    async def test_role_name_uniqueness_per_organization(
        self, client: AsyncClient, superadmin_user: User, organization: Organization,
        second_organization: Organization, superadmin_org_member: OrgMember,
        get_auth_headers, db_session
    ):
        """Test that role names must be unique per organization (not globally)."""
        db_session.add(OrgMember(
            org_id=second_organization.id, user_id=superadmin_user.id,
            role=OrgRole.owner, created_at=datetime.utcnow(),
        ))
        await db_session.commit()
        headers = get_auth_headers(_token(superadmin_user))

        await _create_role(client, headers, organization.id, name="Manager")
        # То же имя в другой организации — можно
        await _create_role(client, headers, second_organization.id, name="Manager")
        # То же имя в той же — нельзя
        response = await client.post(BASE, json={
            "name": "Manager", "description": "dup", "base_role": "member", "org_id": organization.id,
        }, headers=headers)
        assert response.status_code == 409
