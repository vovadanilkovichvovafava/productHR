"""
Access matrix and role permissions endpoints.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from .common import (
    get_db,
    get_superadmin,
    User,
    get_role_permissions,
    SimulateAccessRequest,
)


router = APIRouter()


@router.get("/access-matrix")
async def get_access_matrix(
    _: User = Depends(get_superadmin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the complete access control matrix for all roles.

    Returns a comprehensive matrix showing what each role can do.
    This is useful for:
    - Debugging access control issues
    - Understanding the permission model
    - Documenting the system's security model
    - Training new administrators

    **Only SUPERADMIN can access this endpoint.**
    """
    roles = ["SUPERADMIN", "OWNER", "ADMIN", "SUB_ADMIN", "MEMBER"]

    permissions = [
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

    matrix = {}

    for role in roles:
        role_lower = role.lower()
        context = {}
        if role in ["ADMIN", "SUB_ADMIN"]:
            context = {"is_dept_admin": True, "same_department": True}
        elif role == "MEMBER":
            context = {"is_owner": True}

        perms = get_role_permissions(role_lower, context)

        # Build permission matrix for this role
        role_perms = {}

        if role == "SUPERADMIN":
            # SUPERADMIN has everything
            for perm in permissions:
                role_perms[perm] = True
        elif role == "OWNER":
            role_perms["view_all_users"] = True
            role_perms["create_users"] = perms["can_create_users"]
            role_perms["delete_users"] = perms["can_delete_users"]
            role_perms["view_org_entities"] = True
            role_perms["view_dept_entities"] = True
            role_perms["view_own_entities"] = True
            role_perms["edit_org_entities"] = True
            role_perms["edit_dept_entities"] = True
            role_perms["delete_dept_entities"] = True
            role_perms["view_org_chats"] = True
            role_perms["view_dept_chats"] = True
            role_perms["view_org_calls"] = True
            role_perms["manage_departments"] = perms["can_manage_departments"]
            role_perms["manage_org_members"] = perms.get("can_manage_dept_members", True)
            role_perms["impersonate_users"] = perms["can_impersonate_users"]
        elif role == "ADMIN":
            role_perms["view_all_users"] = False
            role_perms["create_users"] = perms["can_create_users"]
            role_perms["delete_users"] = False
            role_perms["view_org_entities"] = False
            role_perms["view_dept_entities"] = perms["can_view_all_dept_data"]
            role_perms["view_own_entities"] = True
            role_perms["edit_org_entities"] = False
            role_perms["edit_dept_entities"] = True
            role_perms["delete_dept_entities"] = True
            role_perms["view_org_chats"] = False
            role_perms["view_dept_chats"] = True
            role_perms["view_org_calls"] = False
            role_perms["manage_departments"] = False
            role_perms["manage_org_members"] = False
            role_perms["impersonate_users"] = False
        elif role == "SUB_ADMIN":
            role_perms["view_all_users"] = False
            role_perms["create_users"] = False
            role_perms["delete_users"] = False
            role_perms["view_org_entities"] = False
            role_perms["view_dept_entities"] = perms["can_view_all_dept_data"]
            role_perms["view_own_entities"] = True
            role_perms["edit_org_entities"] = False
            role_perms["edit_dept_entities"] = True
            role_perms["delete_dept_entities"] = False
            role_perms["view_org_chats"] = False
            role_perms["view_dept_chats"] = True
            role_perms["view_org_calls"] = False
            role_perms["manage_departments"] = False
            role_perms["manage_org_members"] = False
            role_perms["impersonate_users"] = False
        elif role == "MEMBER":
            role_perms["view_all_users"] = False
            role_perms["create_users"] = False
            role_perms["delete_users"] = False
            role_perms["view_org_entities"] = False
            role_perms["view_dept_entities"] = False
            role_perms["view_own_entities"] = True
            role_perms["edit_org_entities"] = False
            role_perms["edit_dept_entities"] = False
            role_perms["delete_dept_entities"] = False
            role_perms["view_org_chats"] = False
            role_perms["view_dept_chats"] = False
            role_perms["view_org_calls"] = False
            role_perms["manage_departments"] = False
            role_perms["manage_org_members"] = False
            role_perms["impersonate_users"] = False

        matrix[role] = role_perms

    return {
        "roles": roles,
        "permissions": permissions,
        "matrix": matrix
    }


@router.post("/simulate-access")
async def simulate_access(
    request_body: SimulateAccessRequest,
    _: User = Depends(get_superadmin),
    db: AsyncSession = Depends(get_db)
):
    """
    Simulate access control for a specific role.

    This endpoint allows you to test what permissions a role has
    in a given organization/department context.

    **Only SUPERADMIN can access this endpoint.**
    """
    role = request_body.role
    org_id = request_body.org_id
    dept_id = request_body.dept_id

    # Build context
    context = {}
    if dept_id:
        context["is_dept_admin"] = True
        context["same_department"] = True
    elif role.upper() == "MEMBER":
        context["is_owner"] = True

    # Get permissions for this role
    perms = get_role_permissions(role.lower(), context)

    # Build response based on role
    response = {}

    if role.upper() == "SUPERADMIN":
        response = {
            "can_view_all_users": True,
            "can_delete_users": True,
            "can_impersonate": True,
            "can_view_all_orgs": True,
            "can_manage_departments": True
        }
    elif role.upper() == "OWNER":
        response = {
            "can_view_org_entities": True,
            "can_edit_org_entities": True,
            "can_delete_org_entities": True,
            "can_manage_org_members": perms.get("can_manage_dept_members", True),
            "can_manage_departments": perms["can_manage_departments"],
            "can_impersonate": perms["can_impersonate_users"],
            "can_view_all_orgs": perms["can_view_all_orgs"]
        }
    elif role.upper() == "ADMIN":
        response = {
            "can_view_dept_entities": perms["can_view_all_dept_data"],
            "can_edit_dept_entities": True,
            "can_delete_dept_entities": True,
            "can_manage_dept_members": perms["can_manage_dept_members"],
            "can_view_all_org_entities": False,
            "can_manage_org_members": False,
            "can_impersonate": perms["can_impersonate_users"]
        }
    elif role.upper() == "SUB_ADMIN":
        response = {
            "can_view_dept_entities": perms["can_view_all_dept_data"],
            "can_view_dept_chats": perms["can_view_all_dept_data"],
            "can_edit_dept_entities": True,
            "can_delete_dept_admins": False,
            "can_manage_dept_members": True,
            "can_delete_dept_members": False
        }
    elif role.upper() == "MEMBER":
        response = {
            "can_view_own_entities": True,
            "can_edit_own_entities": True,
            "can_view_dept_entities": False,
            "can_view_all_dept_chats": False,
            "can_view_shared_entities": True,
            "can_manage_dept_members": False,
            "can_impersonate": perms["can_impersonate_users"]
        }

    return response


@router.get("/role-permissions")
async def get_role_permissions_list(
    role: Optional[str] = Query(None, description="Filter by specific role"),
    _: User = Depends(get_superadmin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed permissions for each role (or a specific role).

    This endpoint provides a detailed breakdown of what each role can do.
    Useful for:
    - Understanding the permission model
    - Generating documentation
    - Building UI permission indicators

    **Query Parameters:**
    - `role` (optional): Filter to show only one role's permissions

    **Only SUPERADMIN can access this endpoint.**
    """
    roles = ["SUPERADMIN", "OWNER", "ADMIN", "SUB_ADMIN", "MEMBER"]

    if role:
        role_upper = role.upper()
        if role_upper not in roles:
            raise HTTPException(status_code=404, detail=f"Role '{role}' not found")
        roles = [role_upper]

    result = {}

    for role_name in roles:
        role_lower = role_name.lower()
        context = {}
        if role_name in ["ADMIN", "SUB_ADMIN"]:
            context = {"is_dept_admin": True, "same_department": True}
        elif role_name == "MEMBER":
            context = {"is_owner": True}

        perms = get_role_permissions(role_lower, context)

        # Group permissions by category
        role_perms = {
            "users": {},
            "organizations": {},
            "departments": {},
            "entities": {},
            "chats": {},
            "calls": {},
            "sharing": {},
            "admin": {}
        }

        if role_name == "SUPERADMIN":
            role_perms["users"] = {
                "view_all_users": True,
                "create_users": True,
                "delete_users": True
            }
            role_perms["organizations"] = {
                "view_all_orgs": True,
                "edit_org_settings": True
            }
            role_perms["departments"] = {
                "manage_departments": True,
                "view_all_dept_data": True
            }
            role_perms["entities"] = {
                "view_org_entities": True,
                "view_dept_entities": True,
                "edit_org_entities": True,
                "edit_dept_entities": True,
                "delete_dept_entities": True
            }
            role_perms["chats"] = {
                "view_org_chats": True,
                "view_dept_chats": True
            }
            role_perms["calls"] = {
                "view_org_calls": True
            }
            role_perms["sharing"] = {
                "share_resources": True,
                "transfer_resources": True
            }
            role_perms["admin"] = {
                "impersonate": True,
                "manage_org": True,
                "access_admin_panel": True
            }
        elif role_name == "OWNER":
            role_perms["users"] = {
                "view_all_users": True,
                "create_users": True,
                "delete_users": True
            }
            role_perms["organizations"] = {
                "view_all_orgs": False,
                "edit_org_settings": True
            }
            role_perms["departments"] = {
                "manage_departments": True,
                "view_all_dept_data": True
            }
            role_perms["entities"] = {
                "view_org_entities": True,
                "view_dept_entities": True,
                "edit_org_entities": True,
                "edit_dept_entities": True,
                "delete_dept_entities": True
            }
            role_perms["chats"] = {
                "view_org_chats": True,
                "view_dept_chats": True
            }
            role_perms["calls"] = {
                "view_org_calls": True
            }
            role_perms["sharing"] = {
                "share_resources": True,
                "transfer_resources": True
            }
            role_perms["admin"] = {
                "impersonate": False,
                "manage_org": True,
                "access_admin_panel": True
            }
        elif role_name == "ADMIN":
            role_perms["users"] = {
                "view_all_users": False,
                "create_users": perms["can_create_users"],
                "delete_users": False
            }
            role_perms["organizations"] = {
                "view_all_orgs": False,
                "edit_org_settings": False
            }
            role_perms["departments"] = {
                "manage_departments": False,
                "view_all_dept_data": perms["can_view_all_dept_data"]
            }
            role_perms["entities"] = {
                "view_org_entities": False,
                "view_dept_entities": True,
                "edit_org_entities": False,
                "edit_dept_entities": True,
                "delete_dept_entities": True
            }
            role_perms["chats"] = {
                "view_org_chats": False,
                "view_dept_chats": True
            }
            role_perms["calls"] = {
                "view_org_calls": False
            }
            role_perms["sharing"] = {
                "share_resources": perms["can_share_resources"],
                "transfer_resources": perms["can_transfer_resources"]
            }
            role_perms["admin"] = {
                "impersonate": False,
                "manage_org": False,
                "access_admin_panel": True
            }
        elif role_name == "SUB_ADMIN":
            role_perms["users"] = {
                "view_all_users": False,
                "create_users": False,
                "delete_users": False
            }
            role_perms["organizations"] = {
                "view_all_orgs": False,
                "edit_org_settings": False
            }
            role_perms["departments"] = {
                "manage_departments": False,
                "view_all_dept_data": perms["can_view_all_dept_data"]
            }
            role_perms["entities"] = {
                "view_org_entities": False,
                "view_dept_entities": True,
                "edit_org_entities": False,
                "edit_dept_entities": True,
                "delete_dept_entities": False
            }
            role_perms["chats"] = {
                "view_org_chats": False,
                "view_dept_chats": True
            }
            role_perms["calls"] = {
                "view_org_calls": False
            }
            role_perms["sharing"] = {
                "share_resources": perms["can_share_resources"],
                "transfer_resources": False
            }
            role_perms["admin"] = {
                "impersonate": False,
                "manage_org": False,
                "access_admin_panel": True
            }
        elif role_name == "MEMBER":
            role_perms["users"] = {
                "view_all_users": False,
                "create_users": False,
                "delete_users": False
            }
            role_perms["organizations"] = {
                "view_all_orgs": False,
                "edit_org_settings": False
            }
            role_perms["departments"] = {
                "manage_departments": False,
                "view_all_dept_data": False
            }
            role_perms["entities"] = {
                "view_org_entities": False,
                "view_dept_entities": False,
                "edit_org_entities": False,
                "edit_dept_entities": False,
                "delete_dept_entities": False
            }
            role_perms["chats"] = {
                "view_org_chats": False,
                "view_dept_chats": False
            }
            role_perms["calls"] = {
                "view_org_calls": False
            }
            role_perms["sharing"] = {
                "share_resources": perms["can_share_resources"],
                "transfer_resources": False
            }
            role_perms["admin"] = {
                "impersonate": False,
                "manage_org": False,
                "access_admin_panel": False
            }

        result[role_name] = role_perms

    return result
