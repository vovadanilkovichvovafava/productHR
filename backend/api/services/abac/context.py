"""Access context builder for ABAC"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.database import (
    User, UserRole, OrgRole, DeptRole,
    OrgMember, DepartmentMember, Department,
    Entity, Chat, CallRecording,
    SharedAccess, ResourceType, AccessLevel
)


@dataclass
class AccessContext:
    """Context for ABAC policy evaluation"""

    # Subject (user) attributes
    subject: Dict[str, Any] = field(default_factory=dict)

    # Resource attributes
    resource: Dict[str, Any] = field(default_factory=dict)

    # Action being performed
    action: Dict[str, Any] = field(default_factory=dict)

    # Environment attributes (time, IP, etc.)
    environment: Dict[str, Any] = field(default_factory=dict)

    def get(self, attr_type: str, attr_name: str, default: Any = None) -> Any:
        """Get attribute value by type and name"""
        type_map = {
            "subject": self.subject,
            "resource": self.resource,
            "action": self.action,
            "environment": self.environment
        }
        return type_map.get(attr_type, {}).get(attr_name, default)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization"""
        return {
            "subject": self.subject,
            "resource": self.resource,
            "action": self.action,
            "environment": self.environment
        }


class AccessContextBuilder:
    """Builds AccessContext from request data"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._dept_cache: Dict[int, Dict[str, Any]] = {}
        self._org_role_cache: Dict[tuple, OrgRole] = {}
        self._shared_access_cache: Dict[tuple, Optional[AccessLevel]] = {}

    async def build(
        self,
        user: User,
        resource_type: str,
        resource_id: Optional[int] = None,
        resource: Optional[Any] = None,
        action: str = "read",
        org_id: Optional[int] = None,
        extra_context: Optional[Dict[str, Any]] = None
    ) -> AccessContext:
        """Build complete access context"""
        context = AccessContext()

        # Build subject attributes
        context.subject = await self._build_subject_attrs(user, org_id)

        # Build resource attributes
        if resource or resource_id:
            context.resource = await self._build_resource_attrs(
                resource_type, resource_id, resource, user
            )
        else:
            context.resource = {"type": resource_type}

        # Build action attributes
        context.action = {"type": action}

        # Build environment attributes
        context.environment = self._build_environment_attrs(extra_context)

        # Add computed attributes
        await self._add_computed_attrs(context, user, resource_type, resource_id, resource)

        return context

    async def _build_subject_attrs(
        self, user: User, org_id: Optional[int]
    ) -> Dict[str, Any]:
        """Build subject (user) attributes"""
        attrs = {
            "id": user.id,
            "role": user.role.value if user.role else "member",
            "is_superadmin": user.role == UserRole.superadmin,
        }

        # Get org memberships and roles
        memberships_result = await self.db.execute(
            select(OrgMember).where(OrgMember.user_id == user.id)
        )
        memberships = list(memberships_result.scalars().all())

        attrs["org_ids"] = [m.org_id for m in memberships]
        attrs["org_roles"] = {m.org_id: m.role.value for m in memberships}

        # Get specific org role if org_id provided
        if org_id:
            for m in memberships:
                if m.org_id == org_id:
                    attrs["org_id"] = org_id
                    attrs["org_role"] = m.role.value
                    attrs["is_org_owner"] = m.role == OrgRole.owner
                    attrs["is_org_admin"] = m.role in (OrgRole.owner, OrgRole.admin)
                    break

        # Get department memberships
        dept_result = await self.db.execute(
            select(DepartmentMember, Department)
            .join(Department, DepartmentMember.department_id == Department.id)
            .where(DepartmentMember.user_id == user.id)
        )
        dept_memberships = list(dept_result.all())

        attrs["departments"] = []
        attrs["dept_roles"] = {}
        attrs["admin_dept_ids"] = []
        attrs["dept_member_ids"] = set()  # All user IDs in user's admin departments

        for dept_member, dept in dept_memberships:
            attrs["departments"].append(dept.id)
            attrs["dept_roles"][dept.id] = dept_member.role.value

            if dept_member.role in (DeptRole.lead, DeptRole.sub_admin):
                attrs["admin_dept_ids"].append(dept.id)
                attrs["is_dept_admin"] = True

                # Get all members of this department
                members_result = await self.db.execute(
                    select(DepartmentMember.user_id)
                    .where(DepartmentMember.department_id == dept.id)
                )
                for member_id in members_result.scalars().all():
                    attrs["dept_member_ids"].add(member_id)

        # Check if user has any admin dept role
        attrs["dept_role"] = None
        for dept_id, role in attrs["dept_roles"].items():
            if role in ("lead", "sub_admin"):
                attrs["dept_role"] = role
                break

        # Convert set to list for JSON serialization
        attrs["dept_member_ids"] = list(attrs["dept_member_ids"])

        return attrs

    async def _build_resource_attrs(
        self,
        resource_type: str,
        resource_id: Optional[int],
        resource: Optional[Any],
        user: User
    ) -> Dict[str, Any]:
        """Build resource attributes"""
        attrs = {
            "type": resource_type,
            "id": resource_id
        }

        # Load resource if not provided
        if not resource and resource_id:
            resource = await self._load_resource(resource_type, resource_id)

        if not resource:
            return attrs

        # Common attributes
        if hasattr(resource, "org_id"):
            attrs["org_id"] = resource.org_id
        if hasattr(resource, "department_id"):
            attrs["department_id"] = resource.department_id
        if hasattr(resource, "created_by"):
            attrs["created_by"] = resource.created_by
        if hasattr(resource, "owner_id"):
            attrs["owner_id"] = resource.owner_id

        # Get creator role for superadmin private check
        creator_id = attrs.get("created_by") or attrs.get("owner_id")
        if creator_id:
            creator_result = await self.db.execute(
                select(User.role).where(User.id == creator_id)
            )
            creator_role = creator_result.scalar_one_or_none()
            if creator_role:
                attrs["created_by_role"] = creator_role.value
                attrs["is_private"] = creator_role == UserRole.superadmin

        # Entity-specific
        if resource_type == "entity" and hasattr(resource, "type"):
            attrs["entity_type"] = resource.type.value if resource.type else None
            attrs["status"] = resource.status.value if resource.status else None

        # Chat-specific
        if resource_type == "chat":
            attrs["entity_id"] = resource.entity_id if hasattr(resource, "entity_id") else None
            if attrs["entity_id"]:
                # Get entity's department
                entity_result = await self.db.execute(
                    select(Entity.department_id).where(Entity.id == attrs["entity_id"])
                )
                entity_dept = entity_result.scalar_one_or_none()
                if entity_dept:
                    attrs["linked_entity_department_id"] = entity_dept

        # Call-specific
        if resource_type == "call":
            attrs["entity_id"] = resource.entity_id if hasattr(resource, "entity_id") else None
            if attrs["entity_id"]:
                # Get entity's department
                entity_result = await self.db.execute(
                    select(Entity.department_id).where(Entity.id == attrs["entity_id"])
                )
                entity_dept = entity_result.scalar_one_or_none()
                if entity_dept:
                    attrs["linked_entity_department_id"] = entity_dept

        return attrs

    async def _load_resource(self, resource_type: str, resource_id: int) -> Optional[Any]:
        """Load resource from database"""
        model_map = {
            "entity": Entity,
            "chat": Chat,
            "call": CallRecording,
            "department": Department,
        }
        model = model_map.get(resource_type)
        if not model:
            return None

        result = await self.db.execute(
            select(model).where(model.id == resource_id)
        )
        return result.scalar_one_or_none()

    def _build_environment_attrs(self, extra_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Build environment attributes"""
        now = datetime.utcnow()
        attrs = {
            "timestamp": now.isoformat(),
            "hour": now.hour,
            "day_of_week": now.weekday(),
            "is_business_hours": 9 <= now.hour <= 18,
        }

        if extra_context:
            attrs.update(extra_context)

        return attrs

    async def _add_computed_attrs(
        self,
        context: AccessContext,
        user: User,
        resource_type: str,
        resource_id: Optional[int],
        resource: Optional[Any]
    ) -> None:
        """Add computed attributes for policy evaluation"""
        subject = context.subject
        res = context.resource

        # is_resource_owner: subject.id = resource.created_by OR resource.owner_id
        owner_id = res.get("created_by") or res.get("owner_id")
        subject["is_resource_owner"] = owner_id == user.id if owner_id else False

        # org_id_matches_resource: subject is in same org as resource
        subject["org_id_matches_resource"] = (
            res.get("org_id") in subject.get("org_ids", [])
            if res.get("org_id") else False
        )

        # resource_in_admin_dept: resource.department_id in subject.admin_dept_ids
        resource_dept = res.get("department_id") or res.get("linked_entity_department_id")
        subject["resource_in_admin_dept"] = (
            resource_dept in subject.get("admin_dept_ids", [])
            if resource_dept else False
        )

        # resource_created_by_dept_member: resource.created_by in dept_member_ids
        creator_id = res.get("created_by") or res.get("owner_id")
        subject["resource_created_by_dept_member"] = (
            creator_id in subject.get("dept_member_ids", [])
            if creator_id else False
        )

        # has_shared_access / shared_access_level
        if resource_id and resource_type:
            shared = await self._get_shared_access(user.id, resource_type, resource_id)
            subject["has_shared_access"] = shared is not None
            subject["shared_access_level"] = shared.value if shared else None
        else:
            subject["has_shared_access"] = False
            subject["shared_access_level"] = None

    async def _get_shared_access(
        self, user_id: int, resource_type: str, resource_id: int
    ) -> Optional[AccessLevel]:
        """Get user's shared access level for resource"""
        cache_key = (user_id, resource_type, resource_id)
        if cache_key in self._shared_access_cache:
            return self._shared_access_cache[cache_key]

        # Map string to ResourceType enum
        type_map = {
            "entity": ResourceType.entity,
            "chat": ResourceType.chat,
            "call": ResourceType.call,
        }
        rt = type_map.get(resource_type)
        if not rt:
            return None

        result = await self.db.execute(
            select(SharedAccess.access_level)
            .where(
                SharedAccess.resource_type == rt,
                SharedAccess.resource_id == resource_id,
                SharedAccess.shared_with_id == user_id
            )
        )
        access_level = result.scalar_one_or_none()
        self._shared_access_cache[cache_key] = access_level
        return access_level
