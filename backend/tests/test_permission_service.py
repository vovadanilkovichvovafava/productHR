"""
Tests for PermissionService - centralized access control.

Tests cover:
1. Superadmin access (sees everything)
2. Org owner access (sees org, not superadmin private)
3. Department admin access (lead/sub_admin)
4. Regular member access (own resources only)
5. SharedAccess (view/edit/full levels)
6. Can share to rules
7. Batch operations (get_accessible_ids)
"""
import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import (
    User, UserRole, Organization, OrgMember, OrgRole,
    Department, DepartmentMember, DeptRole,
    Entity, Chat, CallRecording, EntityType, EntityStatus, ChatType, CallStatus, CallSource,
    SharedAccess, ResourceType, AccessLevel
)
from api.services.permissions import PermissionService
from api.services.auth import hash_password


class TestPermissionServiceSuperadmin:
    """Tests for SUPERADMIN access - sees everything."""

    @pytest_asyncio.fixture
    async def setup_superadmin(self, db_session: AsyncSession):
        """Create superadmin and test resources."""
        # Create superadmin
        superadmin = User(
            email="superadmin@test.com",
            password_hash=hash_password("password"),
            name="Super Admin",
            role=UserRole.superadmin
        )
        db_session.add(superadmin)

        # Create org and regular user
        org = Organization(name="Test Org", slug="test-org")
        db_session.add(org)
        await db_session.flush()

        regular_user = User(
            email="regular@test.com",
            password_hash=hash_password("password"),
            name="Regular User",
            role=UserRole.member
        )
        db_session.add(regular_user)
        await db_session.flush()

        # Add regular user to org
        org_member = OrgMember(org_id=org.id, user_id=regular_user.id, role=OrgRole.member)
        db_session.add(org_member)

        # Create entity owned by regular user
        entity = Entity(
            name="Test Entity",
            type=EntityType.candidate,
            status=EntityStatus.active,
            org_id=org.id,
            created_by=regular_user.id
        )
        db_session.add(entity)
        await db_session.flush()

        return {
            "superadmin": superadmin,
            "regular_user": regular_user,
            "org": org,
            "entity": entity
        }

    @pytest.mark.asyncio
    async def test_superadmin_can_access_any_entity(self, db_session: AsyncSession, setup_superadmin):
        """Superadmin can access any entity regardless of owner."""
        data = setup_superadmin
        permissions = PermissionService(db_session)

        can_access = await permissions.can_access_resource(
            data["superadmin"],
            data["entity"],
            "read"
        )
        assert can_access is True

    @pytest.mark.asyncio
    async def test_superadmin_can_modify_any_entity(self, db_session: AsyncSession, setup_superadmin):
        """Superadmin can modify any entity."""
        data = setup_superadmin
        permissions = PermissionService(db_session)

        can_modify = await permissions.can_modify(
            data["superadmin"],
            data["entity"],
            require_full=True
        )
        assert can_modify is True


class TestPermissionServiceOwner:
    """Tests for ORG OWNER access."""

    @pytest_asyncio.fixture
    async def setup_owner(self, db_session: AsyncSession):
        """Create org owner and test resources."""
        org = Organization(name="Test Org", slug="test-org")
        db_session.add(org)
        await db_session.flush()

        # Create owner
        owner = User(
            email="owner@test.com",
            password_hash=hash_password("password"),
            name="Owner",
            role=UserRole.member
        )
        db_session.add(owner)
        await db_session.flush()

        owner_membership = OrgMember(org_id=org.id, user_id=owner.id, role=OrgRole.owner)
        db_session.add(owner_membership)

        # Create superadmin
        superadmin = User(
            email="superadmin@test.com",
            password_hash=hash_password("password"),
            name="Super Admin",
            role=UserRole.superadmin
        )
        db_session.add(superadmin)
        await db_session.flush()

        # Create entity by regular user
        regular_user = User(
            email="regular@test.com",
            password_hash=hash_password("password"),
            name="Regular User",
            role=UserRole.member
        )
        db_session.add(regular_user)
        await db_session.flush()

        regular_membership = OrgMember(org_id=org.id, user_id=regular_user.id, role=OrgRole.member)
        db_session.add(regular_membership)

        regular_entity = Entity(
            name="Regular Entity",
            type=EntityType.candidate,
            status=EntityStatus.active,
            org_id=org.id,
            created_by=regular_user.id
        )
        db_session.add(regular_entity)

        # Create entity by superadmin (should be hidden from owner)
        superadmin_entity = Entity(
            name="Superadmin Entity",
            type=EntityType.candidate,
            status=EntityStatus.active,
            org_id=org.id,
            created_by=superadmin.id
        )
        db_session.add(superadmin_entity)
        await db_session.flush()

        return {
            "owner": owner,
            "superadmin": superadmin,
            "regular_user": regular_user,
            "org": org,
            "regular_entity": regular_entity,
            "superadmin_entity": superadmin_entity
        }

    @pytest.mark.asyncio
    async def test_owner_can_access_regular_entity(self, db_session: AsyncSession, setup_owner):
        """Owner can access entities created by regular users."""
        data = setup_owner
        permissions = PermissionService(db_session)

        can_access = await permissions.can_access_resource(
            data["owner"],
            data["regular_entity"],
            "read"
        )
        assert can_access is True

    @pytest.mark.asyncio
    async def test_owner_cannot_access_superadmin_entity(self, db_session: AsyncSession, setup_owner):
        """Owner CANNOT access entities created by superadmin."""
        data = setup_owner
        permissions = PermissionService(db_session)

        can_access = await permissions.can_access_resource(
            data["owner"],
            data["superadmin_entity"],
            "read"
        )
        assert can_access is False


class TestPermissionServiceDepartmentAdmin:
    """Tests for department lead/sub_admin access."""

    @pytest_asyncio.fixture
    async def setup_department(self, db_session: AsyncSession):
        """Create department with lead and members."""
        org = Organization(name="Test Org", slug="test-org")
        db_session.add(org)
        await db_session.flush()

        # Create department
        dept = Department(name="HR Department", org_id=org.id)
        db_session.add(dept)
        await db_session.flush()

        # Create dept lead
        lead = User(
            email="lead@test.com",
            password_hash=hash_password("password"),
            name="Dept Lead",
            role=UserRole.member
        )
        db_session.add(lead)
        await db_session.flush()

        lead_org = OrgMember(org_id=org.id, user_id=lead.id, role=OrgRole.member)
        lead_dept = DepartmentMember(department_id=dept.id, user_id=lead.id, role=DeptRole.lead)
        db_session.add_all([lead_org, lead_dept])

        # Create dept member
        member = User(
            email="member@test.com",
            password_hash=hash_password("password"),
            name="Dept Member",
            role=UserRole.member
        )
        db_session.add(member)
        await db_session.flush()

        member_org = OrgMember(org_id=org.id, user_id=member.id, role=OrgRole.member)
        member_dept = DepartmentMember(department_id=dept.id, user_id=member.id, role=DeptRole.member)
        db_session.add_all([member_org, member_dept])

        # Create entity by member (in department)
        member_entity = Entity(
            name="Member Entity",
            type=EntityType.candidate,
            status=EntityStatus.active,
            org_id=org.id,
            department_id=dept.id,
            created_by=member.id
        )
        db_session.add(member_entity)

        # Create entity by member (no department)
        member_entity_no_dept = Entity(
            name="Member Entity No Dept",
            type=EntityType.candidate,
            status=EntityStatus.active,
            org_id=org.id,
            department_id=None,
            created_by=member.id
        )
        db_session.add(member_entity_no_dept)

        # Create user outside department
        outsider = User(
            email="outsider@test.com",
            password_hash=hash_password("password"),
            name="Outsider",
            role=UserRole.member
        )
        db_session.add(outsider)
        await db_session.flush()

        outsider_org = OrgMember(org_id=org.id, user_id=outsider.id, role=OrgRole.member)
        db_session.add(outsider_org)

        outsider_entity = Entity(
            name="Outsider Entity",
            type=EntityType.candidate,
            status=EntityStatus.active,
            org_id=org.id,
            created_by=outsider.id
        )
        db_session.add(outsider_entity)
        await db_session.flush()

        return {
            "org": org,
            "dept": dept,
            "lead": lead,
            "member": member,
            "outsider": outsider,
            "member_entity": member_entity,
            "member_entity_no_dept": member_entity_no_dept,
            "outsider_entity": outsider_entity
        }

    @pytest.mark.asyncio
    async def test_lead_can_access_dept_entity(self, db_session: AsyncSession, setup_department):
        """Dept lead can access entities in their department."""
        data = setup_department
        permissions = PermissionService(db_session)

        can_access = await permissions.can_access_resource(
            data["lead"],
            data["member_entity"],
            "read"
        )
        assert can_access is True

    @pytest.mark.asyncio
    async def test_lead_can_access_member_entity_no_dept(self, db_session: AsyncSession, setup_department):
        """Dept lead can access entities created by dept members even without department_id."""
        data = setup_department
        permissions = PermissionService(db_session)

        can_access = await permissions.can_access_resource(
            data["lead"],
            data["member_entity_no_dept"],
            "read"
        )
        assert can_access is True

    @pytest.mark.asyncio
    async def test_lead_cannot_access_outsider_entity(self, db_session: AsyncSession, setup_department):
        """Dept lead CANNOT access entities from users outside their department."""
        data = setup_department
        permissions = PermissionService(db_session)

        can_access = await permissions.can_access_resource(
            data["lead"],
            data["outsider_entity"],
            "read"
        )
        assert can_access is False

    @pytest.mark.asyncio
    async def test_member_cannot_access_other_member_entity(self, db_session: AsyncSession, setup_department):
        """Regular member reads a colleague's entity in the same dept, but can't modify it.

        Раньше рядовой участник отдела не видел чужого вовсе. Теперь у него
        read-only доступ по отделу (_check_department_access: «For MEMBER:
        read-only department access»); править/удалять — нет.
        """
        data = setup_department
        permissions = PermissionService(db_session)

        lead_entity = Entity(
            name="Lead Entity",
            type=EntityType.partner,
            status=EntityStatus.active,
            org_id=data["org"].id,
            department_id=data["dept"].id,
            created_by=data["lead"].id
        )
        db_session.add(lead_entity)
        await db_session.flush()

        assert await permissions.can_access_resource(data["member"], lead_entity, "read") is True
        assert await permissions.can_access_resource(data["member"], lead_entity, "write") is False
        assert await permissions.can_access_resource(data["member"], lead_entity, "delete") is False


class TestPermissionServiceSharedAccess:
    """Tests for SharedAccess permissions."""

    @pytest_asyncio.fixture
    async def setup_shared(self, db_session: AsyncSession):
        """Create users and shared resources."""
        org = Organization(name="Test Org", slug="test-org")
        db_session.add(org)
        await db_session.flush()

        # Create owner of resource
        owner = User(
            email="owner@test.com",
            password_hash=hash_password("password"),
            name="Resource Owner",
            role=UserRole.member
        )
        db_session.add(owner)
        await db_session.flush()

        owner_org = OrgMember(org_id=org.id, user_id=owner.id, role=OrgRole.member)
        db_session.add(owner_org)

        # Create recipient
        recipient = User(
            email="recipient@test.com",
            password_hash=hash_password("password"),
            name="Recipient",
            role=UserRole.member
        )
        db_session.add(recipient)
        await db_session.flush()

        recipient_org = OrgMember(org_id=org.id, user_id=recipient.id, role=OrgRole.member)
        db_session.add(recipient_org)

        # Create entity
        entity = Entity(
            name="Shared Entity",
            type=EntityType.candidate,
            status=EntityStatus.active,
            org_id=org.id,
            created_by=owner.id
        )
        db_session.add(entity)
        await db_session.flush()

        return {
            "org": org,
            "owner": owner,
            "recipient": recipient,
            "entity": entity
        }

    @pytest.mark.asyncio
    async def test_shared_view_allows_read(self, db_session: AsyncSession, setup_shared):
        """User with 'view' shared access can read resource."""
        data = setup_shared
        permissions = PermissionService(db_session)

        # Create shared access with view level
        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=data["entity"].id,
            entity_id=data["entity"].id,
            shared_by_id=data["owner"].id,
            shared_with_id=data["recipient"].id,
            access_level=AccessLevel.view
        )
        db_session.add(share)
        await db_session.flush()

        can_read = await permissions.can_access_resource(
            data["recipient"],
            data["entity"],
            "read"
        )
        assert can_read is True

    @pytest.mark.asyncio
    async def test_shared_view_denies_write(self, db_session: AsyncSession, setup_shared):
        """User with 'view' shared access CANNOT write."""
        data = setup_shared
        permissions = PermissionService(db_session)

        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=data["entity"].id,
            entity_id=data["entity"].id,
            shared_by_id=data["owner"].id,
            shared_with_id=data["recipient"].id,
            access_level=AccessLevel.view
        )
        db_session.add(share)
        await db_session.flush()

        can_write = await permissions.can_access_resource(
            data["recipient"],
            data["entity"],
            "write"
        )
        assert can_write is False

    @pytest.mark.asyncio
    async def test_shared_edit_allows_write(self, db_session: AsyncSession, setup_shared):
        """User with 'edit' shared access can write."""
        data = setup_shared
        permissions = PermissionService(db_session)

        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=data["entity"].id,
            entity_id=data["entity"].id,
            shared_by_id=data["owner"].id,
            shared_with_id=data["recipient"].id,
            access_level=AccessLevel.edit
        )
        db_session.add(share)
        await db_session.flush()

        can_write = await permissions.can_access_resource(
            data["recipient"],
            data["entity"],
            "write"
        )
        assert can_write is True

    @pytest.mark.asyncio
    async def test_shared_edit_denies_share(self, db_session: AsyncSession, setup_shared):
        """User with 'edit' shared access CANNOT share."""
        data = setup_shared
        permissions = PermissionService(db_session)

        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=data["entity"].id,
            entity_id=data["entity"].id,
            shared_by_id=data["owner"].id,
            shared_with_id=data["recipient"].id,
            access_level=AccessLevel.edit
        )
        db_session.add(share)
        await db_session.flush()

        can_share = await permissions.can_access_resource(
            data["recipient"],
            data["entity"],
            "share"
        )
        assert can_share is False

    @pytest.mark.asyncio
    async def test_shared_full_allows_share(self, db_session: AsyncSession, setup_shared):
        """User with 'full' shared access can share."""
        data = setup_shared
        permissions = PermissionService(db_session)

        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=data["entity"].id,
            entity_id=data["entity"].id,
            shared_by_id=data["owner"].id,
            shared_with_id=data["recipient"].id,
            access_level=AccessLevel.full
        )
        db_session.add(share)
        await db_session.flush()

        can_share = await permissions.can_access_resource(
            data["recipient"],
            data["entity"],
            "share"
        )
        assert can_share is True

    @pytest.mark.asyncio
    async def test_expired_share_denies_access(self, db_session: AsyncSession, setup_shared):
        """Expired shared access denies read."""
        data = setup_shared
        permissions = PermissionService(db_session)

        # Create expired share
        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=data["entity"].id,
            entity_id=data["entity"].id,
            shared_by_id=data["owner"].id,
            shared_with_id=data["recipient"].id,
            access_level=AccessLevel.view,
            expires_at=datetime.utcnow() - timedelta(hours=1)  # Expired
        )
        db_session.add(share)
        await db_session.flush()

        can_read = await permissions.can_access_resource(
            data["recipient"],
            data["entity"],
            "read"
        )
        assert can_read is False


class TestPermissionServiceCanShareTo:
    """Tests for can_share_to rules."""

    @pytest_asyncio.fixture
    async def setup_can_share(self, db_session: AsyncSession):
        """Create users with different roles for sharing tests."""
        org = Organization(name="Test Org", slug="test-org")
        db_session.add(org)
        await db_session.flush()

        dept1 = Department(name="Dept 1", org_id=org.id)
        dept2 = Department(name="Dept 2", org_id=org.id)
        db_session.add_all([dept1, dept2])
        await db_session.flush()

        # Superadmin
        superadmin = User(email="super@test.com", password_hash="x", name="Super", role=UserRole.superadmin)
        db_session.add(superadmin)

        # Owner
        owner = User(email="owner@test.com", password_hash="x", name="Owner", role=UserRole.member)
        db_session.add(owner)
        await db_session.flush()
        db_session.add(OrgMember(org_id=org.id, user_id=owner.id, role=OrgRole.owner))

        # Dept lead in dept1
        lead = User(email="lead@test.com", password_hash="x", name="Lead", role=UserRole.member)
        db_session.add(lead)
        await db_session.flush()
        db_session.add(OrgMember(org_id=org.id, user_id=lead.id, role=OrgRole.member))
        db_session.add(DepartmentMember(department_id=dept1.id, user_id=lead.id, role=DeptRole.lead))

        # Member in dept1
        member1 = User(email="member1@test.com", password_hash="x", name="Member1", role=UserRole.member)
        db_session.add(member1)
        await db_session.flush()
        db_session.add(OrgMember(org_id=org.id, user_id=member1.id, role=OrgRole.member))
        db_session.add(DepartmentMember(department_id=dept1.id, user_id=member1.id, role=DeptRole.member))

        # Member in dept2
        member2 = User(email="member2@test.com", password_hash="x", name="Member2", role=UserRole.member)
        db_session.add(member2)
        await db_session.flush()
        db_session.add(OrgMember(org_id=org.id, user_id=member2.id, role=OrgRole.member))
        db_session.add(DepartmentMember(department_id=dept2.id, user_id=member2.id, role=DeptRole.member))

        await db_session.flush()

        return {
            "org": org,
            "dept1": dept1,
            "dept2": dept2,
            "superadmin": superadmin,
            "owner": owner,
            "lead": lead,
            "member1": member1,
            "member2": member2
        }

    @pytest.mark.asyncio
    async def test_superadmin_can_share_to_anyone(self, db_session: AsyncSession, setup_can_share):
        """Superadmin can share to anyone."""
        data = setup_can_share
        permissions = PermissionService(db_session)

        can_share = await permissions.can_share_to(
            data["superadmin"],
            data["member2"],
            data["org"].id
        )
        assert can_share is True

    @pytest.mark.asyncio
    async def test_owner_can_share_to_org_member(self, db_session: AsyncSession, setup_can_share):
        """Owner can share to any org member."""
        data = setup_can_share
        permissions = PermissionService(db_session)

        can_share = await permissions.can_share_to(
            data["owner"],
            data["member2"],
            data["org"].id
        )
        assert can_share is True

    @pytest.mark.asyncio
    async def test_member_can_share_within_dept(self, db_session: AsyncSession, setup_can_share):
        """Member can share within their department."""
        data = setup_can_share
        permissions = PermissionService(db_session)

        can_share = await permissions.can_share_to(
            data["member1"],
            data["lead"],  # Lead is in same dept
            data["org"].id
        )
        assert can_share is True

    @pytest.mark.asyncio
    async def test_member_cannot_share_outside_dept(self, db_session: AsyncSession, setup_can_share):
        """Member shares with anyone in the org, but not outside it.

        Раньше участник делился только внутри своего отдела — для HR это
        оказалось слишком строго (can_share_to: «MEMBER can share with anyone
        in the same organization»). Граница — организация.
        """
        data = setup_can_share
        permissions = PermissionService(db_session)

        # Другой отдел той же организации — можно
        assert await permissions.can_share_to(data["member1"], data["member2"], data["org"].id) is True

        # Человек вне организации — нельзя
        stranger = User(email="stranger@test.com", password_hash="x", name="Stranger", role=UserRole.member)
        db_session.add(stranger)
        await db_session.flush()
        assert await permissions.can_share_to(data["member1"], stranger, data["org"].id) is False


class TestPermissionServiceGetAccessibleIds:
    """Tests for batch accessible IDs retrieval."""

    @pytest_asyncio.fixture
    async def setup_batch(self, db_session: AsyncSession):
        """Create multiple entities for batch tests."""
        org = Organization(name="Test Org", slug="test-org")
        db_session.add(org)
        await db_session.flush()

        dept = Department(name="Dept", org_id=org.id)
        db_session.add(dept)
        await db_session.flush()

        # Lead
        lead = User(email="lead@test.com", password_hash="x", name="Lead", role=UserRole.member)
        db_session.add(lead)
        await db_session.flush()
        db_session.add(OrgMember(org_id=org.id, user_id=lead.id, role=OrgRole.member))
        db_session.add(DepartmentMember(department_id=dept.id, user_id=lead.id, role=DeptRole.lead))

        # Member
        member = User(email="member@test.com", password_hash="x", name="Member", role=UserRole.member)
        db_session.add(member)
        await db_session.flush()
        db_session.add(OrgMember(org_id=org.id, user_id=member.id, role=OrgRole.member))
        db_session.add(DepartmentMember(department_id=dept.id, user_id=member.id, role=DeptRole.member))

        # Create multiple entities
        lead_entity = Entity(name="Lead Entity", type=EntityType.candidate, status=EntityStatus.active, org_id=org.id, department_id=dept.id, created_by=lead.id)
        member_entity = Entity(name="Member Entity", type=EntityType.candidate, status=EntityStatus.active, org_id=org.id, department_id=dept.id, created_by=member.id)
        member_entity_no_dept = Entity(name="Member Entity No Dept", type=EntityType.candidate, status=EntityStatus.active, org_id=org.id, created_by=member.id)

        db_session.add_all([lead_entity, member_entity, member_entity_no_dept])
        await db_session.flush()

        return {
            "org": org,
            "dept": dept,
            "lead": lead,
            "member": member,
            "lead_entity": lead_entity,
            "member_entity": member_entity,
            "member_entity_no_dept": member_entity_no_dept
        }

    @pytest.mark.asyncio
    async def test_lead_gets_all_dept_entities(self, db_session: AsyncSession, setup_batch):
        """Lead gets all department entities including those without dept_id."""
        data = setup_batch
        permissions = PermissionService(db_session)

        accessible_ids = await permissions.get_accessible_ids(
            data["lead"],
            "entity",
            data["org"].id
        )

        # Lead should see: own entity + member's entities (both with and without dept_id)
        assert data["lead_entity"].id in accessible_ids
        assert data["member_entity"].id in accessible_ids
        assert data["member_entity_no_dept"].id in accessible_ids

    @pytest.mark.asyncio
    async def test_member_gets_only_own_entities(self, db_session: AsyncSession, setup_batch):
        """Member gets only their own entities."""
        data = setup_batch
        permissions = PermissionService(db_session)

        accessible_ids = await permissions.get_accessible_ids(
            data["member"],
            "entity",
            data["org"].id
        )

        # Member should see own entities
        assert data["member_entity"].id in accessible_ids
        assert data["member_entity_no_dept"].id in accessible_ids
        # Кандидаты — общий пул организации (get_accessible_ids, модель A):
        # кандидат лида виден и рядовому участнику.
        assert data["lead_entity"].id in accessible_ids

        # А не-кандидат человека вне отдела (партнёр) по-прежнему закрыт.
        outsider = User(email="outsider-batch@test.com", password_hash="x", name="Outsider", role=UserRole.member)
        db_session.add(outsider)
        await db_session.flush()
        db_session.add(OrgMember(org_id=data["org"].id, user_id=outsider.id, role=OrgRole.member))
        partner = Entity(
            name="Outsider Partner", type=EntityType.partner, status=EntityStatus.active,
            org_id=data["org"].id, created_by=outsider.id,
        )
        db_session.add(partner)
        await db_session.flush()
        accessible_ids = await permissions.get_accessible_ids(data["member"], "entity", data["org"].id)
        assert partner.id not in accessible_ids
