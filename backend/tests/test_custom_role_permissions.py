"""
Tests for custom role permission functions.

These tests cover:
- get_user_effective_permissions() - Get effective permissions with custom roles
- get_role_permissions_with_overrides() - Get permissions with optional DB overrides
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import (
    User, UserRole, Organization, CustomRole, UserCustomRole,
    RolePermissionOverride
)
from api.routes.admin import (
    get_user_effective_permissions,
    get_role_permissions_with_overrides,
    get_role_permissions
)


# ============================================================================
# TEST CLASS: get_user_effective_permissions Function
# ============================================================================

@pytest.mark.asyncio
class TestGetUserEffectivePermissions:
    """
    Test get_user_effective_permissions function.

    This function checks if a user has custom roles and applies permission
    overrides, falling back to standard role-based permissions.
    """

    async def test_user_with_no_custom_role_fallback_to_standard(
        self,
        db_session: AsyncSession,
        admin_user: User
    ):
        """Test that users without custom roles get standard permissions."""
        # User has no custom role assigned
        perms = await get_user_effective_permissions(admin_user, db_session)

        # Should get standard admin permissions
        assert isinstance(perms, dict)
        assert "can_view_all_orgs" in perms
        assert "can_delete_users" in perms
        # Admin doesn't have can_view_all_orgs by default
        assert perms["can_view_all_orgs"] == False

    async def test_user_with_custom_role_base_permissions(
        self,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User,
        superadmin_user: User
    ):
        """Test that user with custom role gets base role permissions."""
        # Create a custom role based on "owner"
        custom_role = CustomRole(
            org_id=organization.id,
            name="Custom Manager",
            description="Custom manager role",
            base_role="owner",
            is_active=True,
            created_by=superadmin_user.id
        )
        db_session.add(custom_role)
        await db_session.flush()

        # Assign custom role to user
        user_custom_role = UserCustomRole(
            user_id=admin_user.id,
            role_id=custom_role.id,
            assigned_by=superadmin_user.id
        )
        db_session.add(user_custom_role)
        await db_session.commit()

        # Get permissions
        perms = await get_user_effective_permissions(admin_user, db_session)

        # Should get owner base permissions
        assert isinstance(perms, dict)
        assert perms["can_manage_departments"] == True  # Owner can manage depts
        assert perms["can_delete_users"] == True  # Owner can delete users
        assert perms["can_impersonate_users"] == False  # Owner can't impersonate

    async def test_user_with_custom_role_and_overrides(
        self,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User,
        superadmin_user: User
    ):
        """Test that permission overrides are applied to base permissions."""
        # Create custom role based on "admin"
        custom_role = CustomRole(
            org_id=organization.id,
            name="Limited Admin",
            description="Admin with restricted permissions",
            base_role="admin",
            is_active=True,
            created_by=superadmin_user.id
        )
        db_session.add(custom_role)
        await db_session.flush()

        # Add permission override: disable can_create_users
        override = RolePermissionOverride(
            role_id=custom_role.id,
            permission="can_create_users",
            allowed=False
        )
        db_session.add(override)

        # Assign custom role to user
        user_custom_role = UserCustomRole(
            user_id=admin_user.id,
            role_id=custom_role.id,
            assigned_by=superadmin_user.id
        )
        db_session.add(user_custom_role)
        await db_session.commit()

        # Get permissions with dept admin context
        context = {"is_dept_admin": True, "same_department": True}
        perms = await get_user_effective_permissions(admin_user, db_session, context)

        # Base admin with is_dept_admin would have can_create_users=True
        # But override sets it to False
        assert perms["can_create_users"] == False

    async def test_user_with_custom_role_multiple_overrides(
        self,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User,
        superadmin_user: User
    ):
        """Test multiple permission overrides on a custom role."""
        # Create custom role based on "member"
        custom_role = CustomRole(
            org_id=organization.id,
            name="Enhanced Member",
            description="Member with extra permissions",
            base_role="member",
            is_active=True,
            created_by=superadmin_user.id
        )
        db_session.add(custom_role)
        await db_session.flush()

        # Add multiple overrides to grant extra permissions
        overrides = [
            RolePermissionOverride(
                role_id=custom_role.id,
                permission="can_view_all_dept_data",
                allowed=True
            ),
            RolePermissionOverride(
                role_id=custom_role.id,
                permission="can_share_resources",
                allowed=True
            ),
            RolePermissionOverride(
                role_id=custom_role.id,
                permission="can_access_admin_panel",
                allowed=True
            )
        ]
        for override in overrides:
            db_session.add(override)

        # Assign custom role to user
        user_custom_role = UserCustomRole(
            user_id=admin_user.id,
            role_id=custom_role.id,
            assigned_by=superadmin_user.id
        )
        db_session.add(user_custom_role)
        await db_session.commit()

        # Get permissions
        perms = await get_user_effective_permissions(admin_user, db_session)

        # Member base doesn't have these, but overrides grant them
        assert perms["can_view_all_dept_data"] == True
        assert perms["can_share_resources"] == True
        assert perms["can_access_admin_panel"] == True
        # Other permissions stay as member defaults
        assert perms["can_delete_users"] == False

    async def test_user_with_inactive_custom_role_ignored(
        self,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User,
        superadmin_user: User
    ):
        """Test that inactive custom roles are ignored."""
        # Create inactive custom role
        custom_role = CustomRole(
            org_id=organization.id,
            name="Inactive Role",
            description="This role is inactive",
            base_role="owner",
            is_active=False,  # Inactive!
            created_by=superadmin_user.id
        )
        db_session.add(custom_role)
        await db_session.flush()

        # Assign to user
        user_custom_role = UserCustomRole(
            user_id=admin_user.id,
            role_id=custom_role.id,
            assigned_by=superadmin_user.id
        )
        db_session.add(user_custom_role)
        await db_session.commit()

        # Get permissions
        perms = await get_user_effective_permissions(admin_user, db_session)

        # Should fallback to standard admin permissions (not owner)
        assert perms["can_manage_departments"] == False  # Admin can't manage depts
        assert perms["can_delete_users"] == False  # Admin can't delete users

    async def test_user_with_multiple_custom_roles_uses_latest(
        self,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User,
        superadmin_user: User
    ):
        """Test that when user has multiple roles, the latest is used."""
        from datetime import datetime, timedelta

        # Create two custom roles
        old_role = CustomRole(
            org_id=organization.id,
            name="Old Role",
            base_role="member",
            is_active=True,
            created_by=superadmin_user.id
        )
        new_role = CustomRole(
            org_id=organization.id,
            name="New Role",
            base_role="owner",
            is_active=True,
            created_by=superadmin_user.id
        )
        db_session.add(old_role)
        db_session.add(new_role)
        await db_session.flush()

        # Assign old role first
        old_assignment = UserCustomRole(
            user_id=admin_user.id,
            role_id=old_role.id,
            assigned_by=superadmin_user.id
        )
        db_session.add(old_assignment)
        await db_session.flush()

        # Update assigned_at to be in the past
        old_assignment.assigned_at = datetime.utcnow() - timedelta(days=1)
        db_session.add(old_assignment)

        # Assign new role
        new_assignment = UserCustomRole(
            user_id=admin_user.id,
            role_id=new_role.id,
            assigned_by=superadmin_user.id
        )
        db_session.add(new_assignment)
        await db_session.commit()

        # Get permissions
        perms = await get_user_effective_permissions(admin_user, db_session)

        # Should use new_role (owner) permissions, not old_role (member)
        assert perms["can_manage_departments"] == True  # Owner can
        assert perms["can_delete_users"] == True  # Owner can

    async def test_user_with_custom_role_context_still_applies(
        self,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User,
        superadmin_user: User
    ):
        """Test that context parameters still affect custom role permissions."""
        # Create custom role based on admin
        custom_role = CustomRole(
            org_id=organization.id,
            name="Context Admin",
            base_role="admin",
            is_active=True,
            created_by=superadmin_user.id
        )
        db_session.add(custom_role)
        await db_session.flush()

        # Assign to user
        user_custom_role = UserCustomRole(
            user_id=admin_user.id,
            role_id=custom_role.id,
            assigned_by=superadmin_user.id
        )
        db_session.add(user_custom_role)
        await db_session.commit()

        # Get permissions WITHOUT dept admin context
        perms_no_context = await get_user_effective_permissions(admin_user, db_session)
        assert perms_no_context["can_create_users"] == False

        # Get permissions WITH dept admin context
        context = {"is_dept_admin": True}
        perms_with_context = await get_user_effective_permissions(
            admin_user, db_session, context
        )
        assert perms_with_context["can_create_users"] == True


# ============================================================================
# TEST CLASS: get_role_permissions_with_overrides Function
# ============================================================================

@pytest.mark.asyncio
class TestGetRolePermissionsWithOverrides:
    """
    Test get_role_permissions_with_overrides function.

    This function supports both hardcoded permissions (no db/user_id)
    and database-backed custom roles (with db/user_id).
    """

    async def test_without_db_returns_hardcoded_permissions(self):
        """Test that calling without db returns standard hardcoded permissions."""
        # Call without db or user_id
        perms = await get_role_permissions_with_overrides("admin")

        # Should get hardcoded admin permissions
        assert isinstance(perms, dict)
        assert "can_view_all_orgs" in perms
        assert perms["can_view_all_orgs"] == False  # Admin standard

    async def test_without_user_id_returns_hardcoded_permissions(
        self,
        db_session: AsyncSession
    ):
        """Test that calling without user_id returns standard permissions."""
        # Call with db but no user_id
        perms = await get_role_permissions_with_overrides(
            "owner",
            db=db_session
        )

        # Should get hardcoded owner permissions
        assert perms["can_manage_departments"] == True
        assert perms["can_delete_users"] == True

    async def test_with_db_and_user_id_no_custom_role(
        self,
        db_session: AsyncSession,
        admin_user: User
    ):
        """Test with db/user_id but user has no custom role."""
        # User has no custom role
        perms = await get_role_permissions_with_overrides(
            "admin",
            db=db_session,
            user_id=admin_user.id
        )

        # Should fallback to hardcoded permissions
        assert perms["can_view_all_orgs"] == False

    async def test_with_custom_role_returns_custom_permissions(
        self,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User,
        superadmin_user: User
    ):
        """Test with custom role returns customized permissions."""
        # Create custom role
        custom_role = CustomRole(
            org_id=organization.id,
            name="Custom",
            base_role="owner",
            is_active=True,
            created_by=superadmin_user.id
        )
        db_session.add(custom_role)
        await db_session.flush()

        # Add override
        override = RolePermissionOverride(
            role_id=custom_role.id,
            permission="can_delete_users",
            allowed=False  # Disable this
        )
        db_session.add(override)

        # Assign to user
        user_custom_role = UserCustomRole(
            user_id=admin_user.id,
            role_id=custom_role.id,
            assigned_by=superadmin_user.id
        )
        db_session.add(user_custom_role)
        await db_session.commit()

        # Get permissions
        perms = await get_role_permissions_with_overrides(
            "admin",  # role parameter is ignored when custom role exists
            db=db_session,
            user_id=admin_user.id
        )

        # Should get owner base with override
        assert perms["can_manage_departments"] == True  # From owner base
        assert perms["can_delete_users"] == False  # Overridden

    async def test_with_context_parameter(
        self,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User,
        superadmin_user: User
    ):
        """Test that context parameter is passed through."""
        # Create custom role based on admin
        custom_role = CustomRole(
            org_id=organization.id,
            name="Contextual Admin",
            base_role="admin",
            is_active=True,
            created_by=superadmin_user.id
        )
        db_session.add(custom_role)
        await db_session.flush()

        # Assign to user
        user_custom_role = UserCustomRole(
            user_id=admin_user.id,
            role_id=custom_role.id,
            assigned_by=superadmin_user.id
        )
        db_session.add(user_custom_role)
        await db_session.commit()

        # Get permissions with context
        context = {"is_dept_admin": True, "same_department": True}
        perms = await get_role_permissions_with_overrides(
            "admin",
            context=context,
            db=db_session,
            user_id=admin_user.id
        )

        # Admin with is_dept_admin can create users
        assert perms["can_create_users"] == True

    async def test_backward_compatibility_with_get_role_permissions(self):
        """Test that without db/user_id, behaves like get_role_permissions."""
        # Get permissions both ways
        standard_perms = get_role_permissions("owner")
        override_perms = await get_role_permissions_with_overrides("owner")

        # Should be identical
        assert standard_perms == override_perms

    async def test_handles_inactive_custom_roles(
        self,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User,
        superadmin_user: User
    ):
        """Test that inactive custom roles are ignored."""
        # Create inactive custom role
        custom_role = CustomRole(
            org_id=organization.id,
            name="Inactive",
            base_role="owner",
            is_active=False,
            created_by=superadmin_user.id
        )
        db_session.add(custom_role)
        await db_session.flush()

        # Assign to user
        user_custom_role = UserCustomRole(
            user_id=admin_user.id,
            role_id=custom_role.id,
            assigned_by=superadmin_user.id
        )
        db_session.add(user_custom_role)
        await db_session.commit()

        # Get permissions
        perms = await get_role_permissions_with_overrides(
            "admin",
            db=db_session,
            user_id=admin_user.id
        )

        # Should fallback to hardcoded admin (not owner from inactive role)
        assert perms["can_manage_departments"] == False  # Admin can't


# ============================================================================
# TEST CLASS: Edge Cases and Error Handling
# ============================================================================

@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases and error handling."""

    async def test_user_with_custom_role_no_overrides(
        self,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User,
        superadmin_user: User
    ):
        """Test custom role with no permission overrides."""
        # Create custom role with no overrides
        custom_role = CustomRole(
            org_id=organization.id,
            name="Plain Custom",
            base_role="admin",
            is_active=True,
            created_by=superadmin_user.id
        )
        db_session.add(custom_role)
        await db_session.flush()

        # Assign to user
        user_custom_role = UserCustomRole(
            user_id=admin_user.id,
            role_id=custom_role.id,
            assigned_by=superadmin_user.id
        )
        db_session.add(user_custom_role)
        await db_session.commit()

        # Get permissions
        perms = await get_user_effective_permissions(admin_user, db_session)

        # Should get pure admin permissions
        assert isinstance(perms, dict)
        assert len(perms) > 0

    async def test_override_permission_not_in_base(
        self,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User,
        superadmin_user: User
    ):
        """Test that overrides can add new permissions not in base."""
        # Create custom role
        custom_role = CustomRole(
            org_id=organization.id,
            name="Custom",
            base_role="member",
            is_active=True,
            created_by=superadmin_user.id
        )
        db_session.add(custom_role)
        await db_session.flush()

        # Add override for permission that member doesn't have
        override = RolePermissionOverride(
            role_id=custom_role.id,
            permission="can_manage_departments",
            allowed=True
        )
        db_session.add(override)

        # Assign to user
        user_custom_role = UserCustomRole(
            user_id=admin_user.id,
            role_id=custom_role.id,
            assigned_by=superadmin_user.id
        )
        db_session.add(user_custom_role)
        await db_session.commit()

        # Get permissions
        perms = await get_user_effective_permissions(admin_user, db_session)

        # Should have the new permission
        assert perms["can_manage_departments"] == True

    async def test_none_context_defaults_to_empty_dict(
        self,
        db_session: AsyncSession,
        admin_user: User
    ):
        """Test that None context is handled gracefully."""
        # Should not raise error
        perms = await get_user_effective_permissions(
            admin_user,
            db_session,
            context=None
        )

        assert isinstance(perms, dict)
