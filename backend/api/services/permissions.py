"""
Centralized Permission Service for HR-Bot

This service consolidates all access control logic in one place,
replacing scattered permission checks across routes.

Access Hierarchy:
1. SUPERADMIN (non-shadow) - sees EVERYTHING except shadow users' content
2. SHADOW SUPERADMIN - sees all org data except main superadmin's and other shadow users' content
3. OWNER - sees everything in organization, BUT NOT private content created by SUPERADMIN/SHADOW
4. LEAD/SUB_ADMIN - sees all resources in their department + resources created by dept members
5. MEMBER - sees only THEIR OWN resources + explicitly shared resources

Shadow User Content Isolation:
- Main superadmin cannot see content created by shadow users
- Shadow users cannot see content created by main superadmin
- Shadow users cannot see content created by other shadow users
- All superadmins (main + shadow) can see content created by regular users

Resource Types: entity, chat, call, vacancy
Actions: read, write, delete, share
"""

from datetime import datetime
from typing import Optional, List, Set, Tuple, Union, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
import logging

from ..models.database import (
    User, UserRole,
    Organization, OrgMember, OrgRole,
    Department, DepartmentMember, DeptRole,
    Entity, EntityType, Chat, CallRecording, Vacancy,
    SharedAccess, ResourceType, AccessLevel
)

logger = logging.getLogger("hr-analyzer.permissions")


class PermissionService:
    """Centralized permission management service.

    Usage:
        permissions = PermissionService(db)

        # Check if user can access a specific resource
        if await permissions.can_access(user, "chat", chat.id, "read"):
            ...

        # Check if user can access a loaded resource object
        if await permissions.can_access_resource(user, chat, "read"):
            ...

        # Get all accessible resource IDs for list queries
        entity_ids = await permissions.get_accessible_ids(user, "entity", org_id)
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._cache: dict = {}  # Simple per-request cache

    # ==================== MAIN PUBLIC API ====================

    async def can_access(
        self,
        user: User,
        resource_type: str,
        resource_id: int,
        action: str = "read"
    ) -> bool:
        """Check if user can perform action on resource.

        Args:
            user: Current user
            resource_type: "entity" | "chat" | "call"
            resource_id: ID of the resource
            action: "read" | "write" | "delete" | "share"

        Returns:
            True if access is allowed
        """
        # Load the resource
        resource = await self._load_resource(resource_type, resource_id)
        if not resource:
            return False

        return await self.can_access_resource(user, resource, action)

    async def can_access_resource(
        self,
        user: User,
        resource: Union[Entity, Chat, CallRecording],
        action: str = "read"
    ) -> bool:
        """Check if user can perform action on already-loaded resource.

        Args:
            user: Current user
            resource: Entity, Chat, or CallRecording object
            action: "read" | "write" | "delete" | "share"

        Returns:
            True if access is allowed
        """
        resource_type = self._get_resource_type(resource)

        # 1. SUPERADMIN - has access to EVERYTHING except isolated content
        if self._is_superadmin(user):
            # Check content isolation for shadow users
            if await self._is_content_isolated_from_user(user, resource):
                return False
            return True

        # 2. Get user's org context
        user_org = await self._get_user_org(user)
        if not user_org:
            return False

        # Check org boundary
        if not self._check_org_boundary(resource, user_org.id):
            return False

        # 3. OWNER - has access to everything in org (except SUPERADMIN private content)
        if await self._is_org_owner(user, user_org.id):
            if await self._was_created_by_superadmin(resource):
                return False
            return True

        # 4. Resource owner/creator has full access
        if self._is_resource_owner(user, resource):
            return True

        # 5. For write/delete/share actions - check SharedAccess levels
        if action in ("write", "delete", "share"):
            return await self._check_modification_access(user, resource, resource_type, action)

        # 6. Department-based access (LEAD/SUB_ADMIN) for read
        if await self._check_department_access(user, resource):
            return True

        # 6.5. Practice department members can read ALL chats in the org.
        # Mirrors the chat-list rule in routes/chats.py — the whole practice
        # team works on candidate chats together. Without this, practice
        # members could open a chat (it shows up in the list) but got
        # "Access denied" from AI-assistant / report endpoints. Read-only.
        if action == "read" and resource_type == "chat":
            if await self._is_practice_member(user, user_org.id):
                return True

        # 7. SharedAccess for read
        if await self._has_shared_access(user, resource_type, self._get_resource_id(resource)):
            return True

        return False

    async def can_modify(
        self,
        user: User,
        resource: Union[Entity, Chat, CallRecording],
        require_full: bool = False
    ) -> bool:
        """Check if user can modify resource.

        Args:
            user: Current user
            resource: Resource object
            require_full: If True, require 'full' access level. If False, 'edit' or 'full' is enough.
        """
        action = "share" if require_full else "write"
        return await self.can_access_resource(user, resource, action)

    async def can_share_to(
        self,
        from_user: User,
        to_user: User,
        from_user_org_id: int
    ) -> bool:
        """Check if from_user can share resources with to_user.

        Rules:
        - SUPERADMIN → anyone
        - OWNER → anyone in organization
        - OrgRole.ADMIN → their department + other admins + OWNER/SUPERADMIN
        - DeptRole.lead/sub_admin → their department + other leads/sub_admins + OrgRole.admin + OWNER/SUPERADMIN
        - MEMBER → only within their department
        """
        # SUPERADMIN can share with anyone
        if self._is_superadmin(from_user):
            return True

        # Get from_user's org role
        from_user_role = await self._get_org_role(from_user, from_user_org_id)

        # OWNER can share with anyone in their organization
        if from_user_role == OrgRole.owner:
            to_user_org = await self._get_user_org(to_user)
            return to_user_org and to_user_org.id == from_user_org_id

        # Get to_user's org role
        to_user_org_role = await self._get_org_role(to_user, from_user_org_id)

        # If to_user is not in the organization, cannot share
        if to_user_org_role is None:
            return False

        # OrgRole.ADMIN can share with: dept members, other admins, OWNER/SUPERADMIN
        if from_user_role == OrgRole.admin:
            if to_user_org_role == OrgRole.owner or self._is_superadmin(to_user):
                return True
            if to_user_org_role == OrgRole.admin:
                return True
            return await self._are_in_same_department(from_user, to_user)

        # DeptRole.lead/sub_admin sharing rules
        from_dept_admin_ids = await self._get_admin_department_ids(from_user)

        if from_dept_admin_ids:
            if to_user_org_role == OrgRole.owner or self._is_superadmin(to_user):
                return True
            if to_user_org_role == OrgRole.admin:
                return True

            # Can share with other dept leads/sub_admins
            to_dept_admin_ids = await self._get_admin_department_ids(to_user)
            if to_dept_admin_ids:
                return True

            # Can share within their departments
            to_dept_ids = await self._get_user_department_ids(to_user)
            return bool(from_dept_admin_ids & to_dept_ids)

        # MEMBER can share with anyone in the same organization
        # (previously restricted to same department — too strict for HR workflows)
        if from_user_role == OrgRole.member:
            return to_user_org_role is not None  # just needs to be in same org

        return False

    async def get_accessible_ids(
        self,
        user: User,
        resource_type: str,
        org_id: int
    ) -> Set[int]:
        """Get all resource IDs that user can access.

        Optimized for list queries - returns set of IDs.

        Args:
            user: Current user
            resource_type: "entity" | "chat" | "call"
            org_id: Organization ID

        Returns:
            Set of accessible resource IDs
        """
        accessible_ids: Set[int] = set()

        # SUPERADMIN sees everything (with content isolation for shadow users)
        if self._is_superadmin(user):
            return await self._get_all_resource_ids(
                resource_type, org_id,
                exclude_isolated_from_user=user
            )

        # OWNER sees everything in org (except SUPERADMIN/SHADOW private content)
        if await self._is_org_owner(user, org_id):
            return await self._get_all_resource_ids(resource_type, org_id, exclude_superadmin=True)

        # 1. Own resources
        own_ids = await self._get_owned_resource_ids(user, resource_type, org_id)
        accessible_ids.update(own_ids)

        # 1.5 Модель A («общий пул HR»): член орга «видит» ВСЕХ кандидатов своей
        # орг. Добавляем id всех кандидатов орга (только type==candidate; клиенты/
        # партнёры — по строгим правилам ниже). Без этого дедуп/«похожие» искали
        # только среди СВОИХ кандидатов рекрутёра и не находили старых (чужих).
        if resource_type == "entity":
            cand_result = await self.db.execute(
                select(Entity.id).where(
                    Entity.org_id == org_id,
                    Entity.type == EntityType.candidate,
                )
            )
            accessible_ids.update(cand_result.scalars().all())

        # 2. Department resources (if lead/sub_admin)
        dept_ids = await self._get_department_resource_ids(user, resource_type, org_id)
        accessible_ids.update(dept_ids)

        # 3. Shared resources
        shared_ids = await self._get_shared_resource_ids(user, resource_type)
        accessible_ids.update(shared_ids)

        return accessible_ids

    async def get_access_level(
        self,
        user: User,
        resource: Union[Entity, Chat, CallRecording]
    ) -> Optional[str]:
        """Get user's access level for a resource.

        Returns:
            "owner" | "full" | "edit" | "view" | None
        """
        if self._is_superadmin(user):
            return "owner"

        user_org = await self._get_user_org(user)
        if user_org and await self._is_org_owner(user, user_org.id):
            return "owner"

        if self._is_resource_owner(user, resource):
            return "owner"

        # Check SharedAccess
        resource_type = self._get_resource_type(resource)
        resource_id = self._get_resource_id(resource)

        shared = await self._get_shared_access(user.id, resource_type, resource_id)
        if shared:
            return shared.access_level.value

        # Department access = view
        if await self._check_department_access(user, resource):
            return "view"

        return None

    # ==================== PRIVATE HELPERS ====================

    def _is_superadmin(self, user: User) -> bool:
        """Check if user is SUPERADMIN (main or shadow)."""
        return user.role == UserRole.superadmin

    def _is_main_superadmin(self, user: User) -> bool:
        """Check if user is the MAIN superadmin (not a shadow user)."""
        return user.role == UserRole.superadmin and not getattr(user, 'is_shadow', False)

    def _is_shadow_superadmin(self, user: User) -> bool:
        """Check if user is a SHADOW superadmin."""
        return user.role == UserRole.superadmin and getattr(user, 'is_shadow', False)

    async def _is_content_isolated_from_user(self, user: User, resource: Any) -> bool:
        """Check if resource content should be hidden from user due to shadow isolation.

        Content isolation rules:
        - Main superadmin cannot see content created by shadow users
        - Shadow users cannot see content created by main superadmin
        - Shadow users cannot see content created by other shadow users

        Args:
            user: Current user (superadmin)
            resource: Resource to check

        Returns:
            True if content should be hidden (isolated)
        """
        # Get resource creator ID
        creator_id = getattr(resource, 'created_by', None) or getattr(resource, 'owner_id', None)
        if not creator_id:
            return False  # No creator info, allow access

        # Get creator's shadow status
        creator_info = await self._get_user_shadow_info(creator_id)
        if not creator_info:
            return False  # Creator not found, allow access

        creator_is_shadow = creator_info.get('is_shadow', False)
        creator_is_superadmin = creator_info.get('is_superadmin', False)

        # If creator is not a superadmin (main or shadow), content is visible to all superadmins
        if not creator_is_superadmin:
            return False

        # Main superadmin viewing shadow user's content
        if self._is_main_superadmin(user) and creator_is_shadow:
            return True  # Isolated - main cannot see shadow's content

        # Shadow user viewing main superadmin's content
        if self._is_shadow_superadmin(user) and creator_is_superadmin and not creator_is_shadow:
            return True  # Isolated - shadow cannot see main's content

        # Shadow user viewing another shadow user's content
        if self._is_shadow_superadmin(user) and creator_is_shadow and creator_id != user.id:
            return True  # Isolated - shadow cannot see other shadow's content

        return False

    async def _get_user_shadow_info(self, user_id: int) -> Optional[dict]:
        """Get user's shadow status info."""
        cache_key = f"user_shadow_info_{user_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = await self.db.execute(
            select(User.id, User.role, User.is_shadow).where(User.id == user_id)
        )
        row = result.first()
        if not row:
            self._cache[cache_key] = None
            return None

        info = {
            'id': row[0],
            'is_superadmin': row[1] == UserRole.superadmin,
            'is_shadow': row[2] if row[2] is not None else False
        }
        self._cache[cache_key] = info
        return info

    async def _is_org_owner(self, user: User, org_id: int) -> bool:
        """Check if user is OWNER of the organization."""
        if self._is_superadmin(user):
            return False  # Superadmin is higher than owner
        role = await self._get_org_role(user, org_id)
        return role == OrgRole.owner

    async def _get_org_role(self, user: User, org_id: int) -> Optional[OrgRole]:
        """Get user's role in organization."""
        cache_key = f"org_role_{user.id}_{org_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = await self.db.execute(
            select(OrgMember.role).where(
                OrgMember.org_id == org_id,
                OrgMember.user_id == user.id
            )
        )
        role = result.scalar_one_or_none()
        self._cache[cache_key] = role
        return role

    async def _get_user_org(self, user: User) -> Optional[Organization]:
        """Get user's current organization."""
        cache_key = f"user_org_{user.id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = await self.db.execute(
            select(Organization)
            .join(OrgMember, OrgMember.org_id == Organization.id)
            .where(OrgMember.user_id == user.id)
            .limit(1)
        )
        org = result.scalar_one_or_none()
        self._cache[cache_key] = org
        return org

    async def _is_practice_member(self, user: User, org_id: int) -> bool:
        """Check if user is a member of the 'Практика' department in the org.

        Members of the practice department see and work with ALL chats in the
        organization (the whole team works on candidate chats together). This
        mirrors the list query in routes/chats.py so that AI-assistant and
        report endpoints grant the same read access.
        """
        cache_key = f"practice_member_{user.id}_{org_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = await self.db.execute(
            select(DepartmentMember.id)
            .join(Department, Department.id == DepartmentMember.department_id)
            .where(
                DepartmentMember.user_id == user.id,
                Department.org_id == org_id,
                func.lower(func.trim(Department.name)) == 'практика',
            )
            .limit(1)
        )
        is_member = result.scalar_one_or_none() is not None
        self._cache[cache_key] = is_member
        return is_member

    def _check_org_boundary(self, resource: Any, org_id: int) -> bool:
        """Check if resource belongs to organization."""
        resource_org_id = getattr(resource, 'org_id', None)
        return resource_org_id == org_id

    def _is_resource_owner(self, user: User, resource: Any) -> bool:
        """Check if user owns/created the resource."""
        # Entities use created_by
        if hasattr(resource, 'created_by') and resource.created_by == user.id:
            return True
        # Chats and Calls use owner_id
        if hasattr(resource, 'owner_id') and resource.owner_id == user.id:
            return True
        return False

    def _get_resource_type(self, resource: Any) -> str:
        """Get resource type string from object."""
        if isinstance(resource, Entity):
            return "entity"
        elif isinstance(resource, Chat):
            return "chat"
        elif isinstance(resource, CallRecording):
            return "call"
        raise ValueError(f"Unknown resource type: {type(resource)}")

    def _get_resource_id(self, resource: Any) -> int:
        """Get resource ID."""
        return resource.id

    async def _load_resource(self, resource_type: str, resource_id: int) -> Optional[Any]:
        """Load resource by type and ID."""
        model_map = {
            "entity": Entity,
            "chat": Chat,
            "call": CallRecording,
            "vacancy": Vacancy
        }
        model = model_map.get(resource_type)
        if not model:
            return None

        result = await self.db.execute(
            select(model).where(model.id == resource_id)
        )
        return result.scalar_one_or_none()

    async def _was_created_by_superadmin(self, resource: Any) -> bool:
        """Check if resource was created by SUPERADMIN."""
        creator_id = getattr(resource, 'created_by', None) or getattr(resource, 'owner_id', None)
        if not creator_id:
            return False

        result = await self.db.execute(
            select(User.role).where(User.id == creator_id)
        )
        role = result.scalar_one_or_none()
        return role == UserRole.superadmin

    async def _check_department_access(self, user: User, resource: Any) -> bool:
        """Check if user has department-based access.

        For LEAD/SUB_ADMIN: full department access (read/write).
        For MEMBER: read-only department access.

        Access granted if:
        a) Resource is in user's department, OR
        b) Resource owner/entity is a member of user's department
        """
        # First check admin departments (lead/sub_admin)
        admin_dept_ids = await self._get_admin_department_ids(user)
        if admin_dept_ids:
            if self._resource_in_departments(resource, admin_dept_ids):
                return True

            entity_id = getattr(resource, 'entity_id', None)
            if entity_id:
                entity_result = await self.db.execute(
                    select(Entity.department_id).where(Entity.id == entity_id)
                )
                entity_dept_id = entity_result.scalar_one_or_none()
                if entity_dept_id and entity_dept_id in admin_dept_ids:
                    return True

            owner_id = getattr(resource, 'owner_id', None) or getattr(resource, 'created_by', None)
            if owner_id:
                owner_depts = await self._get_user_department_ids_by_user_id(owner_id)
                if owner_depts & admin_dept_ids:
                    return True

        # Then check regular member department access (read-only)
        member_dept_ids = await self._get_user_department_ids(user)
        if member_dept_ids:
            # Check if resource owner is in the same department
            owner_id = getattr(resource, 'owner_id', None) or getattr(resource, 'created_by', None)
            if owner_id:
                owner_depts = await self._get_user_department_ids_by_user_id(owner_id)
                if owner_depts & member_dept_ids:
                    return True

            # Check if resource's entity is in the same department
            entity_id = getattr(resource, 'entity_id', None)
            if entity_id:
                entity_result = await self.db.execute(
                    select(Entity.department_id).where(Entity.id == entity_id)
                )
                entity_dept_id = entity_result.scalar_one_or_none()
                if entity_dept_id and entity_dept_id in member_dept_ids:
                    return True

        return False

    def _resource_in_departments(self, resource: Any, dept_ids: set) -> bool:
        """Check if resource's department_id is in the given set."""
        resource_dept_id = getattr(resource, 'department_id', None)
        return resource_dept_id is not None and resource_dept_id in dept_ids

    async def _get_admin_department_ids(self, user: User) -> Set[int]:
        """Get department IDs where user is lead or sub_admin."""
        cache_key = f"admin_depts_{user.id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = await self.db.execute(
            select(DepartmentMember.department_id).where(
                DepartmentMember.user_id == user.id,
                DepartmentMember.role.in_([DeptRole.lead, DeptRole.sub_admin])
            )
        )
        dept_ids = set(result.scalars().all())
        self._cache[cache_key] = dept_ids
        return dept_ids

    async def _get_user_department_ids(self, user: User) -> Set[int]:
        """Get all department IDs where user is a member."""
        return await self._get_user_department_ids_by_user_id(user.id)

    async def _get_user_department_ids_by_user_id(self, user_id: int) -> Set[int]:
        """Get all department IDs for a user ID."""
        cache_key = f"user_depts_{user_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = await self.db.execute(
            select(DepartmentMember.department_id).where(
                DepartmentMember.user_id == user_id
            )
        )
        dept_ids = set(result.scalars().all())
        self._cache[cache_key] = dept_ids
        return dept_ids

    async def _are_in_same_department(self, user1: User, user2: User) -> bool:
        """Check if two users share at least one department."""
        depts1 = await self._get_user_department_ids(user1)
        depts2 = await self._get_user_department_ids(user2)
        return bool(depts1 & depts2)

    async def _has_shared_access(
        self,
        user: User,
        resource_type: str,
        resource_id: int
    ) -> bool:
        """Check if user has shared access to resource."""
        shared = await self._get_shared_access(user.id, resource_type, resource_id)
        return shared is not None

    async def _get_shared_access(
        self,
        user_id: int,
        resource_type: str,
        resource_id: int
    ) -> Optional[SharedAccess]:
        """Get SharedAccess record for user and resource."""
        rt_enum = self._resource_type_to_enum(resource_type)

        result = await self.db.execute(
            select(SharedAccess).where(
                SharedAccess.resource_type == rt_enum,
                SharedAccess.resource_id == resource_id,
                SharedAccess.shared_with_id == user_id,
                or_(
                    SharedAccess.expires_at.is_(None),
                    SharedAccess.expires_at > datetime.utcnow()
                )
            )
        )
        return result.scalar_one_or_none()

    async def _check_modification_access(
        self,
        user: User,
        resource: Any,
        resource_type: str,
        action: str
    ) -> bool:
        """Check if user can modify/delete/share resource."""
        resource_id = self._get_resource_id(resource)
        shared = await self._get_shared_access(user.id, resource_type, resource_id)

        if not shared:
            return False

        if action == "share":
            return shared.access_level == AccessLevel.full
        else:  # write or delete
            return shared.access_level in (AccessLevel.edit, AccessLevel.full)

    def _resource_type_to_enum(self, resource_type: str) -> ResourceType:
        """Convert string to ResourceType enum."""
        return ResourceType(resource_type)

    # ==================== BATCH OPERATIONS ====================

    async def _get_all_resource_ids(
        self,
        resource_type: str,
        org_id: int,
        exclude_superadmin: bool = False,
        exclude_isolated_from_user: Optional[User] = None
    ) -> Set[int]:
        """Get all resource IDs in organization.

        Args:
            resource_type: Type of resource
            org_id: Organization ID
            exclude_superadmin: If True, exclude resources created by any superadmin
            exclude_isolated_from_user: If provided, apply shadow content isolation rules
        """
        model_map = {
            "entity": Entity,
            "chat": Chat,
            "call": CallRecording,
            "vacancy": Vacancy
        }
        model = model_map.get(resource_type)
        if not model:
            return set()

        query = select(model.id).where(model.org_id == org_id)
        owner_field = 'created_by' if resource_type in ("entity", "vacancy") else 'owner_id'

        if exclude_superadmin:
            # Exclude resources created by any superadmin (main or shadow)
            superadmin_ids = await self._get_superadmin_ids()
            if superadmin_ids:
                query = query.where(~getattr(model, owner_field).in_(superadmin_ids))

        elif exclude_isolated_from_user:
            # Apply shadow content isolation rules
            isolated_ids = await self._get_isolated_user_ids(exclude_isolated_from_user)
            if isolated_ids:
                query = query.where(~getattr(model, owner_field).in_(isolated_ids))

        result = await self.db.execute(query)
        return set(result.scalars().all())

    async def _get_superadmin_ids(self) -> Set[int]:
        """Get all superadmin user IDs (main and shadow)."""
        cache_key = "superadmin_ids"
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = await self.db.execute(
            select(User.id).where(User.role == UserRole.superadmin)
        )
        ids = set(result.scalars().all())
        self._cache[cache_key] = ids
        return ids

    async def _get_isolated_user_ids(self, user: User) -> Set[int]:
        """Get user IDs whose content should be hidden from the given user.

        Shadow content isolation rules:
        - Main superadmin: hide content from all shadow users
        - Shadow user: hide content from main superadmin and other shadow users

        Args:
            user: Current user (superadmin)

        Returns:
            Set of user IDs whose content should be hidden
        """
        cache_key = f"isolated_ids_{user.id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        isolated_ids: Set[int] = set()

        if self._is_main_superadmin(user):
            # Main superadmin: hide all shadow users' content
            result = await self.db.execute(
                select(User.id).where(
                    User.role == UserRole.superadmin,
                    User.is_shadow == True
                )
            )
            isolated_ids = set(result.scalars().all())

        elif self._is_shadow_superadmin(user):
            # Shadow user: hide main superadmin's + other shadows' content
            result = await self.db.execute(
                select(User.id).where(
                    User.role == UserRole.superadmin,
                    User.id != user.id  # Exclude self
                )
            )
            isolated_ids = set(result.scalars().all())

        self._cache[cache_key] = isolated_ids
        return isolated_ids

    async def _get_owned_resource_ids(
        self,
        user: User,
        resource_type: str,
        org_id: int
    ) -> Set[int]:
        """Get resource IDs owned/created by user."""
        model_map = {
            "entity": (Entity, "created_by"),
            "chat": (Chat, "owner_id"),
            "call": (CallRecording, "owner_id"),
            "vacancy": (Vacancy, "created_by")
        }
        model, owner_field = model_map.get(resource_type, (None, None))
        if not model:
            return set()

        result = await self.db.execute(
            select(model.id).where(
                model.org_id == org_id,
                getattr(model, owner_field) == user.id
            )
        )
        return set(result.scalars().all())

    async def _get_department_resource_ids(
        self,
        user: User,
        resource_type: str,
        org_id: int
    ) -> Set[int]:
        """Get resource IDs accessible via department membership (all department members)."""
        # Use admin departments if user is lead/sub_admin, otherwise use all departments
        admin_dept_ids = await self._get_admin_department_ids(user)
        all_dept_ids = await self._get_user_department_ids(user)

        # Combine: admin departments + regular member departments
        effective_dept_ids = admin_dept_ids | all_dept_ids
        if not effective_dept_ids:
            return set()

        accessible_ids: Set[int] = set()

        if resource_type == "entity":
            # Entities directly in department
            result = await self.db.execute(
                select(Entity.id).where(
                    Entity.org_id == org_id,
                    Entity.department_id.in_(effective_dept_ids)
                )
            )
            accessible_ids.update(result.scalars().all())

            # Entities created by department members
            dept_member_ids = await self._get_department_member_ids(effective_dept_ids)
            if dept_member_ids:
                result = await self.db.execute(
                    select(Entity.id).where(
                        Entity.org_id == org_id,
                        Entity.created_by.in_(dept_member_ids)
                    )
                )
                accessible_ids.update(result.scalars().all())

        elif resource_type in ("chat", "call"):
            model = Chat if resource_type == "chat" else CallRecording
            owner_field = "owner_id"

            # Get entity IDs in department
            entity_result = await self.db.execute(
                select(Entity.id).where(
                    Entity.org_id == org_id,
                    Entity.department_id.in_(effective_dept_ids)
                )
            )
            dept_entity_ids = set(entity_result.scalars().all())

            # Also include entities created by department members
            dept_member_ids = await self._get_department_member_ids(effective_dept_ids)
            if dept_member_ids:
                member_entities_result = await self.db.execute(
                    select(Entity.id).where(
                        Entity.org_id == org_id,
                        Entity.created_by.in_(dept_member_ids)
                    )
                )
                dept_entity_ids.update(member_entities_result.scalars().all())

            # Chats/Calls linked to department entities
            if dept_entity_ids:
                result = await self.db.execute(
                    select(model.id).where(
                        model.org_id == org_id,
                        model.entity_id.in_(dept_entity_ids)
                    )
                )
                accessible_ids.update(result.scalars().all())

            # Chats/Calls owned by department members
            if dept_member_ids:
                result = await self.db.execute(
                    select(model.id).where(
                        model.org_id == org_id,
                        getattr(model, owner_field).in_(dept_member_ids)
                    )
                )
                accessible_ids.update(result.scalars().all())

        elif resource_type == "vacancy":
            # Vacancies directly in department
            result = await self.db.execute(
                select(Vacancy.id).where(
                    Vacancy.org_id == org_id,
                    Vacancy.department_id.in_(effective_dept_ids)
                )
            )
            accessible_ids.update(result.scalars().all())

            # Vacancies created by department members
            dept_member_ids = await self._get_department_member_ids(effective_dept_ids)
            if dept_member_ids:
                result = await self.db.execute(
                    select(Vacancy.id).where(
                        Vacancy.org_id == org_id,
                        Vacancy.created_by.in_(dept_member_ids)
                    )
                )
                accessible_ids.update(result.scalars().all())

        return accessible_ids

    async def _get_department_member_ids(self, dept_ids: Set[int]) -> Set[int]:
        """Get all user IDs who are members of given departments."""
        if not dept_ids:
            return set()

        cache_key = f"dept_members_{tuple(sorted(dept_ids))}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = await self.db.execute(
            select(DepartmentMember.user_id).where(
                DepartmentMember.department_id.in_(dept_ids)
            )
        )
        member_ids = set(result.scalars().all())
        self._cache[cache_key] = member_ids
        return member_ids

    async def _get_shared_resource_ids(
        self,
        user: User,
        resource_type: str
    ) -> Set[int]:
        """Get resource IDs shared with user."""
        rt_enum = self._resource_type_to_enum(resource_type)

        result = await self.db.execute(
            select(SharedAccess.resource_id).where(
                SharedAccess.resource_type == rt_enum,
                SharedAccess.shared_with_id == user.id,
                or_(
                    SharedAccess.expires_at.is_(None),
                    SharedAccess.expires_at > datetime.utcnow()
                )
            )
        )
        return set(result.scalars().all())


# ==================== CONVENIENCE FUNCTIONS ====================

async def get_permission_service(db: AsyncSession) -> PermissionService:
    """Factory function for dependency injection."""
    return PermissionService(db)
