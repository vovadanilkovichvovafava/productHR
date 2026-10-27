"""
Tests for cross-organization sharing security validation.

This test suite ensures that:
1. Users can only share resources within their organization
2. Cross-organization sharing is blocked with 403 Forbidden
3. Department-level rules are enforced
4. SUPERADMIN can share across organizations
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import (
    User, Organization, OrgMember, Department, DepartmentMember,
    Entity, Chat, CallRecording, SharedAccess,
    UserRole, OrgRole, DeptRole, EntityType, EntityStatus,
    ChatType, CallStatus, CallSource, ResourceType, AccessLevel
)
from datetime import datetime


class TestCrossOrgSharing:
    """Tests for cross-organization sharing validation."""

    @pytest.mark.asyncio
    async def test_share_entity_within_same_org_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User,
        regular_user: User,
        org_owner: OrgMember,
        org_admin: OrgMember,
        department: Department,
        entity: Entity,
        get_auth_headers
    ):
        """Test that sharing within the same organization works."""
        # Create auth token for admin_user who owns the entity
        from api.services.auth import create_access_token
        token = create_access_token(data={"sub": str(admin_user.id)})
        headers = get_auth_headers(token)

        # Share entity with regular_user in the same org
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": regular_user.id,
                "access_level": "view"
            },
            headers=headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["resource_type"] == "entity"
        assert data["shared_with_id"] == regular_user.id
        assert data["access_level"] == "view"

    @pytest.mark.asyncio
    async def test_share_entity_to_different_org_blocked(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization,
        second_organization: Organization,
        admin_user: User,
        department: Department,
        entity: Entity,
        org_owner: OrgMember,  # admin_user — владелец своей орги, иначе 403 ещё на праве шаринга
        get_auth_headers
    ):
        """Test that sharing to a user in a different organization is blocked with 403."""
        # Create a user in the second organization
        other_org_user = User(
            email="otherorg@test.com",
            password_hash="hash",
            name="Other Org User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(other_org_user)
        await db_session.flush()

        # Add user to second organization
        other_org_member = OrgMember(
            org_id=second_organization.id,
            user_id=other_org_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(other_org_member)
        await db_session.commit()

        # Try to share entity with user from different org
        from api.services.auth import create_access_token
        token = create_access_token(data={"sub": str(admin_user.id)})
        headers = get_auth_headers(token)

        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": other_org_user.id,
                "access_level": "view"
            },
            headers=headers
        )

        # Should be blocked with 403
        assert response.status_code == 403
        assert "организации" in response.json()["detail"] or "отделе" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_share_chat_to_different_org_blocked(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization,
        second_organization: Organization,
        admin_user: User,
        chat: Chat,
        org_owner: OrgMember,  # admin_user — владелец своей орги, иначе 403 ещё на праве шаринга
        get_auth_headers
    ):
        """Test that sharing chats to users in different organizations is blocked."""
        # Create a user in the second organization
        other_org_user = User(
            email="otherorg2@test.com",
            password_hash="hash",
            name="Other Org User 2",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(other_org_user)
        await db_session.flush()

        other_org_member = OrgMember(
            org_id=second_organization.id,
            user_id=other_org_user.id,
            role=OrgRole.admin,
            created_at=datetime.utcnow()
        )
        db_session.add(other_org_member)
        await db_session.commit()

        # Try to share chat
        from api.services.auth import create_access_token
        token = create_access_token(data={"sub": str(admin_user.id)})
        headers = get_auth_headers(token)

        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "chat",
                "resource_id": chat.id,
                "shared_with_id": other_org_user.id,
                "access_level": "edit"
            },
            headers=headers
        )

        assert response.status_code == 403
        assert "организации" in response.json()["detail"] or "отделе" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_share_call_to_different_org_blocked(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization,
        second_organization: Organization,
        admin_user: User,
        call_recording: CallRecording,
        org_owner: OrgMember,  # admin_user — владелец своей орги, иначе 403 ещё на праве шаринга
        get_auth_headers
    ):
        """Test that sharing calls to users in different organizations is blocked."""
        # Create a user in the second organization
        other_org_user = User(
            email="otherorg3@test.com",
            password_hash="hash",
            name="Other Org User 3",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(other_org_user)
        await db_session.flush()

        other_org_member = OrgMember(
            org_id=second_organization.id,
            user_id=other_org_user.id,
            role=OrgRole.owner,
            created_at=datetime.utcnow()
        )
        db_session.add(other_org_member)
        await db_session.commit()

        # Try to share call
        from api.services.auth import create_access_token
        token = create_access_token(data={"sub": str(admin_user.id)})
        headers = get_auth_headers(token)

        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "call",
                "resource_id": call_recording.id,
                "shared_with_id": other_org_user.id,
                "access_level": "full"
            },
            headers=headers
        )

        assert response.status_code == 403
        assert "организации" in response.json()["detail"] or "отделе" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_superadmin_can_share_across_orgs(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization,
        second_organization: Organization,
        superadmin_user: User,
        department: Department,
        get_auth_headers
    ):
        """Test that SUPERADMIN can share resources across organizations."""
        # Create entity owned by superadmin in first org
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=superadmin_user.id,
            name="Superadmin Entity",
            email="super@test.com",
            type=EntityType.candidate,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(entity)
        await db_session.flush()

        # Create user in second org
        other_org_user = User(
            email="secondorg@test.com",
            password_hash="hash",
            name="Second Org User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(other_org_user)
        await db_session.flush()

        other_org_member = OrgMember(
            org_id=second_organization.id,
            user_id=other_org_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(other_org_member)
        await db_session.commit()

        # SUPERADMIN shares with user from different org - should work
        from api.services.auth import create_access_token
        token = create_access_token(data={"sub": str(superadmin_user.id)})
        headers = get_auth_headers(token)

        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": other_org_user.id,
                "access_level": "view"
            },
            headers=headers
        )

        # SUPERADMIN should be able to share across orgs
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_member_can_share_outside_department(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization,
        department: Department,
        second_department: Department,
        get_auth_headers
    ):
        """Test that organization members can only share within their department."""
        # Create two users in the same org but different departments
        member1 = User(
            email="member1@test.com",
            password_hash="hash",
            name="Member 1",
            role=UserRole.admin,
            is_active=True
        )
        member2 = User(
            email="member2@test.com",
            password_hash="hash",
            name="Member 2",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add_all([member1, member2])
        await db_session.flush()

        # Add both to same org
        org_member1 = OrgMember(
            org_id=organization.id,
            user_id=member1.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        org_member2 = OrgMember(
            org_id=organization.id,
            user_id=member2.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add_all([org_member1, org_member2])
        await db_session.flush()

        # Put them in different departments
        dept_member1 = DepartmentMember(
            department_id=department.id,
            user_id=member1.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        dept_member2 = DepartmentMember(
            department_id=second_department.id,
            user_id=member2.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add_all([dept_member1, dept_member2])

        # Create entity owned by member1
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=member1.id,
            name="Member1 Entity",
            email="m1@test.com",
            type=EntityType.client,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(entity)
        await db_session.commit()

        # Member1 tries to share with Member2 (different department)
        from api.services.auth import create_access_token
        token = create_access_token(data={"sub": str(member1.id)})
        headers = get_auth_headers(token)

        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": member2.id,
                "access_level": "view"
            },
            headers=headers
        )

        # Рядовой участник шарит любому в СВОЕЙ организации, отдел не важен
        # (permissions.can_share_to, e9ee64f5: «только свой отдел» оказалось
        # слишком строго для HR). Граница — организация, её проверяют тесты выше.
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_member_can_share_within_department(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization,
        department: Department,
        get_auth_headers
    ):
        """Test that organization members CAN share within their department."""
        # Create two users in the same department
        member1 = User(
            email="deptmember1@test.com",
            password_hash="hash",
            name="Dept Member 1",
            role=UserRole.admin,
            is_active=True
        )
        member2 = User(
            email="deptmember2@test.com",
            password_hash="hash",
            name="Dept Member 2",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add_all([member1, member2])
        await db_session.flush()

        # Add both to same org
        org_member1 = OrgMember(
            org_id=organization.id,
            user_id=member1.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        org_member2 = OrgMember(
            org_id=organization.id,
            user_id=member2.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add_all([org_member1, org_member2])
        await db_session.flush()

        # Put them in SAME department
        dept_member1 = DepartmentMember(
            department_id=department.id,
            user_id=member1.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        dept_member2 = DepartmentMember(
            department_id=department.id,
            user_id=member2.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add_all([dept_member1, dept_member2])

        # Create entity owned by member1
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=member1.id,
            name="Member1 Entity",
            email="dm1@test.com",
            type=EntityType.lead,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(entity)
        await db_session.commit()

        # Member1 shares with Member2 (same department) - should work
        from api.services.auth import create_access_token
        token = create_access_token(data={"sub": str(member1.id)})
        headers = get_auth_headers(token)

        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": member2.id,
                "access_level": "edit"
            },
            headers=headers
        )

        # Should succeed
        assert response.status_code == 200
        data = response.json()
        assert data["shared_with_id"] == member2.id
        assert data["access_level"] == "edit"

    @pytest.mark.asyncio
    async def test_org_owner_can_share_with_anyone_in_org(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User,
        department: Department,
        second_department: Department,
        org_owner: OrgMember,
        get_auth_headers
    ):
        """Test that organization owners can share with anyone in the organization."""
        # admin_user — владелец через фикстуру org_owner. Раньше тут были сырые
        # строки SQL без text() (SQLAlchemy 2.0 их не принимает) и UPDATE строки
        # org_members, которой не существовало.

        # Create user in different department
        other_dept_user = User(
            email="otherdept@test.com",
            password_hash="hash",
            name="Other Dept User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(other_dept_user)
        await db_session.flush()

        org_member = OrgMember(
            org_id=organization.id,
            user_id=other_dept_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(org_member)
        await db_session.flush()

        dept_member = DepartmentMember(
            department_id=second_department.id,
            user_id=other_dept_user.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_member)

        # Create entity
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Owner Entity",
            email="owner@test.com",
            type=EntityType.partner,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(entity)
        await db_session.commit()

        # Owner shares with user in different department - should work
        from api.services.auth import create_access_token
        token = create_access_token(data={"sub": str(admin_user.id)})
        headers = get_auth_headers(token)

        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": other_dept_user.id,
                "access_level": "view"
            },
            headers=headers
        )

        # Should succeed - owners can share with anyone in org
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_user_not_in_org_cannot_share(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization,
        department: Department,
        regular_user: User,
        get_auth_headers
    ):
        """Test that users not in any organization cannot share."""
        # Create a user not in any organization
        orphan_user = User(
            email="orphan@test.com",
            password_hash="hash",
            name="Orphan User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(orphan_user)
        await db_session.flush()

        # Create an entity (somehow) for this user
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=orphan_user.id,
            name="Orphan Entity",
            email="orphan_entity@test.com",
            type=EntityType.candidate,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(entity)
        await db_session.commit()

        # Try to share
        from api.services.auth import create_access_token
        token = create_access_token(data={"sub": str(orphan_user.id)})
        headers = get_auth_headers(token)

        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": regular_user.id,
                "access_level": "view"
            },
            headers=headers
        )

        # Should fail - user not in org. Отказ приходит раньше — на праве
        # шаринга ресурса («You don't have permission…»): без организации у
        # человека нет доступа к карточке вовсе.
        assert response.status_code == 403
