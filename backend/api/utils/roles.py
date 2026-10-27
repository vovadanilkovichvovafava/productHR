"""
Role mapping utilities for consistent role string → enum conversion.

This module centralizes role mapping logic to avoid duplication across the codebase.
"""
from typing import Optional

from ..models.database import UserRole, DeptRole, OrgRole


def map_role_string_to_user_role(role_string: Optional[str]) -> UserRole:
    """Map a role string to UserRole enum.

    Args:
        role_string: Role as string (superadmin, admin, sub_admin, member)

    Returns:
        UserRole enum value, defaults to member for unknown roles
    """
    if not role_string:
        return UserRole.member

    role_map = {
        "superadmin": UserRole.superadmin,
        "admin": UserRole.admin,
        "sub_admin": UserRole.sub_admin,
        "member": UserRole.member,
    }
    return role_map.get(role_string.lower(), UserRole.member)


def map_user_role_to_dept_role(user_role: UserRole) -> DeptRole:
    """Map UserRole to corresponding DeptRole.

    Args:
        user_role: UserRole enum value

    Returns:
        DeptRole enum value
    """
    role_map = {
        UserRole.superadmin: DeptRole.lead,  # Superadmin gets lead role in departments
        UserRole.admin: DeptRole.lead,
        UserRole.sub_admin: DeptRole.sub_admin,
        UserRole.member: DeptRole.member,
    }
    return role_map.get(user_role, DeptRole.member)


def map_user_role_to_org_role(user_role: UserRole) -> OrgRole:
    """Map UserRole to corresponding OrgRole.

    Args:
        user_role: UserRole enum value

    Returns:
        OrgRole enum value
    """
    role_map = {
        UserRole.superadmin: OrgRole.owner,  # Superadmin gets owner role in orgs
        UserRole.admin: OrgRole.admin,
        UserRole.sub_admin: OrgRole.admin,  # sub_admin is still org admin level
        UserRole.member: OrgRole.member,
    }
    return role_map.get(user_role, OrgRole.member)
