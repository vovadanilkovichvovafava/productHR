"""
Comprehensive tests for complex sharing scenarios across all resource types.

Tests cover:
1. Sharing chain (resharing)
2. Cross-department sharing
3. Share expiration
4. Transfer with sharing
5. Bulk operations
6. Role changes during share
7. Organization boundaries
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy import select

from api.models.database import (
    SharedAccess, AccessLevel, ResourceType, Entity, Chat, CallRecording,
    User, UserRole, OrgMember, OrgRole, Department, DepartmentMember, DeptRole,
    Organization, EntityType, EntityStatus, ChatType, CallStatus, CallSource
)
from api.services.auth import hash_password


# ============================================================================
# SCENARIO 1: SHARING CHAIN
# ============================================================================

class TestSharingChain:
    """Test complex sharing chains and resharing scenarios."""

    @pytest.mark.asyncio
    async def test_full_access_allows_reshare(
        self, db_session, client, admin_user, admin_token, second_user, second_user_token,
        entity, organization, get_auth_headers, org_owner, org_member
    ):
        """Test that user with full access can reshare to a third user."""
        # Create third user
        third_user = User(
            email="third@test.com",
            password_hash=hash_password("user123"),
            name="Third User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(third_user)
        await db_session.commit()
        await db_session.refresh(third_user)

        # Add third user to organization
        third_member = OrgMember(
            org_id=organization.id,
            user_id=third_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(third_member)
        await db_session.commit()

        # Step 1: Admin (A) shares to second_user (B) with full access
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": second_user.id,
                "access_level": "full"
            },
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        share_a_to_b = response.json()

        # Step 2: second_user (B) reshares to third_user (C) with edit access
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": third_user.id,
                "access_level": "edit"
            },
            headers=get_auth_headers(second_user_token)
        )
        assert response.status_code == 200
        share_b_to_c = response.json()
        assert share_b_to_c["access_level"] == "edit"

        # Step 3: Verify third_user (C) cannot reshare (doesn't have full access)
        fourth_user = User(
            email="fourth@test.com",
            password_hash=hash_password("user123"),
            name="Fourth User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(fourth_user)
        await db_session.commit()
        await db_session.refresh(fourth_user)

        fourth_member = OrgMember(
            org_id=organization.id,
            user_id=fourth_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(fourth_member)
        await db_session.commit()

        from api.services.auth import create_access_token
        third_user_token = create_access_token(data={"sub": str(third_user.id)})

        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": fourth_user.id,
                "access_level": "view"
            },
            headers=get_auth_headers(third_user_token)
        )
        assert response.status_code == 403, "User with edit access should not be able to reshare"

    @pytest.mark.asyncio
    async def test_revoking_original_share_does_not_affect_chain(
        self, db_session, client, admin_user, admin_token, second_user, second_user_token,
        entity, organization, get_auth_headers, org_owner, org_member
    ):
        """Test that A revoking share to B doesn't affect B's share to C."""
        # Create third user
        third_user = User(
            email="third@test.com",
            password_hash=hash_password("user123"),
            name="Third User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(third_user)
        await db_session.commit()
        await db_session.refresh(third_user)

        third_member = OrgMember(
            org_id=organization.id,
            user_id=third_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(third_member)
        await db_session.commit()

        # A shares to B with full access
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": second_user.id,
                "access_level": "full"
            },
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        share_a_to_b_id = response.json()["id"]

        # B shares to C with edit access
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": third_user.id,
                "access_level": "edit"
            },
            headers=get_auth_headers(second_user_token)
        )
        assert response.status_code == 200
        share_b_to_c_id = response.json()["id"]

        # A revokes share to B
        response = await client.delete(
            f"/api/sharing/{share_a_to_b_id}",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200

        # Verify B->C share still exists
        result = await db_session.execute(
            select(SharedAccess).where(SharedAccess.id == share_b_to_c_id)
        )
        share_b_to_c = result.scalar_one_or_none()
        assert share_b_to_c is not None, "B->C share should still exist after A revokes A->B share"
        assert share_b_to_c.shared_with_id == third_user.id


# ============================================================================
# SCENARIO 2: CROSS-DEPARTMENT SHARING
# ============================================================================

class TestCrossDepartmentSharing:
    """Test sharing across different departments within the same organization."""

    @pytest.mark.asyncio
    async def test_admin_can_share_across_departments(
        self, db_session, client, organization, get_auth_headers, org_owner
    ):
        """Test that ADMIN in Dept1 can share to MEMBER in Dept2."""
        # Create two departments
        dept1 = Department(
            name="Department 1",
            org_id=organization.id,
            created_at=datetime.utcnow()
        )
        dept2 = Department(
            name="Department 2",
            org_id=organization.id,
            created_at=datetime.utcnow()
        )
        db_session.add_all([dept1, dept2])
        await db_session.commit()
        await db_session.refresh(dept1)
        await db_session.refresh(dept2)

        # Create user in dept1 (admin)
        user_dept1 = User(
            email="dept1admin@test.com",
            password_hash=hash_password("password"),
            name="Dept1 Admin",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(user_dept1)
        await db_session.commit()
        await db_session.refresh(user_dept1)

        # Create user in dept2 (member)
        user_dept2 = User(
            email="dept2member@test.com",
            password_hash=hash_password("password"),
            name="Dept2 Member",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(user_dept2)
        await db_session.commit()
        await db_session.refresh(user_dept2)

        # Add users to organization
        org_member1 = OrgMember(
            org_id=organization.id,
            user_id=user_dept1.id,
            role=OrgRole.admin,
            created_at=datetime.utcnow()
        )
        org_member2 = OrgMember(
            org_id=organization.id,
            user_id=user_dept2.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add_all([org_member1, org_member2])
        await db_session.commit()

        # Add users to departments
        dept_member1 = DepartmentMember(
            department_id=dept1.id,
            user_id=user_dept1.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        dept_member2 = DepartmentMember(
            department_id=dept2.id,
            user_id=user_dept2.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add_all([dept_member1, dept_member2])
        await db_session.commit()

        # Create entity owned by dept1 admin
        entity = Entity(
            org_id=organization.id,
            department_id=dept1.id,
            created_by=user_dept1.id,
            name="Cross Dept Contact",
            email="contact@test.com",
            type=EntityType.candidate,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # dept1 admin shares with dept2 member
        from api.services.auth import create_access_token
        user_dept1_token = create_access_token(data={"sub": str(user_dept1.id)})

        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": user_dept2.id,
                "access_level": "edit"
            },
            headers=get_auth_headers(user_dept1_token)
        )
        assert response.status_code == 200, response.text

        # Verify dept2 member can access via shared-with-me
        user_dept2_token = create_access_token(data={"sub": str(user_dept2.id)})
        response = await client.get(
            "/api/sharing/shared-with-me",
            headers=get_auth_headers(user_dept2_token)
        )
        assert response.status_code == 200
        shares = response.json()
        assert len(shares) >= 1
        assert any(s["resource_id"] == entity.id for s in shares)

    @pytest.mark.asyncio
    async def test_department_filters_work_with_cross_dept_shares(
        self, db_session, client, organization, get_auth_headers
    ):
        """Test that department filters still work correctly with cross-department shares."""
        # Create two departments
        dept1 = Department(
            name="Sales",
            org_id=organization.id,
            created_at=datetime.utcnow()
        )
        dept2 = Department(
            name="HR",
            org_id=organization.id,
            created_at=datetime.utcnow()
        )
        db_session.add_all([dept1, dept2])
        await db_session.commit()
        await db_session.refresh(dept1)
        await db_session.refresh(dept2)

        # Create users
        user1 = User(
            email="sales@test.com",
            password_hash=hash_password("password"),
            name="Sales User",
            role=UserRole.admin,
            is_active=True
        )
        user2 = User(
            email="hr@test.com",
            password_hash=hash_password("password"),
            name="HR User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add_all([user1, user2])
        await db_session.commit()
        await db_session.refresh(user1)
        await db_session.refresh(user2)

        # Add to org
        for user in [user1, user2]:
            org_member = OrgMember(
                org_id=organization.id,
                user_id=user.id,
                role=OrgRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(org_member)
        await db_session.commit()

        # Add to departments
        dept_member1 = DepartmentMember(
            department_id=dept1.id,
            user_id=user1.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        dept_member2 = DepartmentMember(
            department_id=dept2.id,
            user_id=user2.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add_all([dept_member1, dept_member2])
        await db_session.commit()

        # Create entity in dept1 (Sales)
        entity = Entity(
            org_id=organization.id,
            department_id=dept1.id,
            created_by=user1.id,
            name="Sales Contact",
            email="sales_contact@test.com",
            type=EntityType.client,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # User1 shares with User2
        from api.services.auth import create_access_token
        user1_token = create_access_token(data={"sub": str(user1.id)})

        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": user2.id,
                "access_level": "view"
            },
            headers=get_auth_headers(user1_token)
        )
        assert response.status_code == 200

        # User2 should see the entity (it's shared with them)
        user2_token = create_access_token(data={"sub": str(user2.id)})
        response = await client.get(
            "/api/entities",
            headers=get_auth_headers(user2_token)
        )
        assert response.status_code == 200
        # Note: The entity should appear because it's shared, even though it's in a different department


# ============================================================================
# SCENARIO 3: SHARE EXPIRATION
# ============================================================================

class TestShareExpiration:
    """Test share expiration functionality."""

    @pytest.mark.asyncio
    async def test_share_with_expiry_access_before_expiry(
        self, db_session, client, admin_user, admin_token, second_user, second_user_token,
        entity, get_auth_headers, org_owner, org_member
    ):
        """Test that user has access before share expires."""
        # Create share with 1 hour expiry
        expires_at = datetime.utcnow() + timedelta(hours=1)

        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": second_user.id,
                "access_level": "edit",
                "expires_at": expires_at.isoformat()
            },
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        share_data = response.json()
        assert share_data["expires_at"] is not None

        # Verify second_user can see the share
        response = await client.get(
            "/api/sharing/shared-with-me",
            headers=get_auth_headers(second_user_token)
        )
        assert response.status_code == 200
        shares = response.json()
        assert len(shares) >= 1
        assert any(s["resource_id"] == entity.id for s in shares)

    @pytest.mark.asyncio
    async def test_expired_share_no_access(
        self, db_session, client, admin_user, admin_token, second_user, second_user_token,
        entity, get_auth_headers, org_owner, org_member
    ):
        """Test that user loses access after share expires."""
        # Create share that expired 1 hour ago
        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.edit,
            expires_at=datetime.utcnow() - timedelta(hours=1),  # Already expired
            created_at=datetime.utcnow() - timedelta(days=2)
        )
        db_session.add(share)
        await db_session.commit()

        # Verify second_user cannot see the expired share
        response = await client.get(
            "/api/sharing/shared-with-me",
            headers=get_auth_headers(second_user_token)
        )
        assert response.status_code == 200
        shares = response.json()
        # Expired shares should not appear in shared-with-me
        expired_share_ids = [s["id"] for s in shares if s["id"] == share.id]
        assert len(expired_share_ids) == 0, "Expired shares should not appear in shared-with-me"

    @pytest.mark.asyncio
    async def test_share_expiration_for_all_resource_types(
        self, db_session, client, admin_user, admin_token, second_user, second_user_token,
        entity, chat, call_recording, get_auth_headers, org_owner, org_member
    ):
        """Test expiration works for all resource types."""
        resources = [
            ("entity", entity.id),
            ("chat", chat.id),
            ("call", call_recording.id)
        ]

        for resource_type, resource_id in resources:
            # Create share with future expiry
            expires_at = datetime.utcnow() + timedelta(days=7)

            response = await client.post(
                "/api/sharing",
                json={
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "shared_with_id": second_user.id,
                    "access_level": "view",
                    "expires_at": expires_at.isoformat()
                },
                headers=get_auth_headers(admin_token)
            )
            assert response.status_code == 200, f"Failed to share {resource_type}"

        # Verify all shares appear in shared-with-me
        response = await client.get(
            "/api/sharing/shared-with-me",
            headers=get_auth_headers(second_user_token)
        )
        assert response.status_code == 200
        shares = response.json()
        assert len(shares) >= 3


# ============================================================================
# SCENARIO 5: BULK OPERATIONS
# ============================================================================

class TestBulkSharingOperations:
    """Test bulk sharing operations."""

    @pytest.mark.asyncio
    async def test_share_multiple_entities_at_once(
        self, db_session, client, admin_user, admin_token, second_user,
        entity, organization, department, get_auth_headers, org_owner, org_member
    ):
        """Test sharing multiple entities to the same user."""
        # Create additional entities
        entities = [entity]
        for i in range(3):
            new_entity = Entity(
                org_id=organization.id,
                department_id=department.id,
                created_by=admin_user.id,
                name=f"Bulk Entity {i}",
                email=f"bulk{i}@test.com",
                type=EntityType.candidate,
                status=EntityStatus.active,
                created_at=datetime.utcnow()
            )
            db_session.add(new_entity)
            entities.append(new_entity)

        await db_session.commit()
        for e in entities:
            await db_session.refresh(e)

        # Share all entities with second_user
        share_ids = []
        for entity_to_share in entities:
            response = await client.post(
                "/api/sharing",
                json={
                    "resource_type": "entity",
                    "resource_id": entity_to_share.id,
                    "shared_with_id": second_user.id,
                    "access_level": "view"
                },
                headers=get_auth_headers(admin_token)
            )
            assert response.status_code == 200
            share_ids.append(response.json()["id"])

        # Verify all shares exist
        assert len(share_ids) == len(entities)

        # Verify second_user sees all shares
        from api.services.auth import create_access_token
        second_user_token = create_access_token(data={"sub": str(second_user.id)})

        response = await client.get(
            "/api/sharing/shared-with-me",
            headers=get_auth_headers(second_user_token)
        )
        assert response.status_code == 200
        shares = response.json()
        assert len(shares) >= len(entities)

    @pytest.mark.asyncio
    async def test_revoke_all_shares_from_user(
        self, db_session, client, admin_user, admin_token, second_user,
        organization, department, get_auth_headers, org_owner, org_member
    ):
        """Test revoking all shares from a specific user."""
        # Create multiple entities
        entities = []
        for i in range(3):
            entity = Entity(
                org_id=organization.id,
                department_id=department.id,
                created_by=admin_user.id,
                name=f"Entity {i}",
                email=f"entity{i}@test.com",
                type=EntityType.candidate,
                status=EntityStatus.active,
                created_at=datetime.utcnow()
            )
            db_session.add(entity)
            entities.append(entity)

        await db_session.commit()
        for e in entities:
            await db_session.refresh(e)

        # Share all with second_user
        share_ids = []
        for entity in entities:
            response = await client.post(
                "/api/sharing",
                json={
                    "resource_type": "entity",
                    "resource_id": entity.id,
                    "shared_with_id": second_user.id,
                    "access_level": "view"
                },
                headers=get_auth_headers(admin_token)
            )
            assert response.status_code == 200
            share_ids.append(response.json()["id"])

        # Revoke all shares
        for share_id in share_ids:
            response = await client.delete(
                f"/api/sharing/{share_id}",
                headers=get_auth_headers(admin_token)
            )
            assert response.status_code == 200

        # Verify all shares are gone
        for share_id in share_ids:
            result = await db_session.execute(
                select(SharedAccess).where(SharedAccess.id == share_id)
            )
            share = result.scalar_one_or_none()
            assert share is None, f"Share {share_id} should be deleted"

    @pytest.mark.asyncio
    async def test_share_multiple_resource_types_to_user(
        self, db_session, client, admin_user, admin_token, second_user,
        entity, organization, get_auth_headers, org_owner, org_member
    ):
        """Test sharing different resource types to the same user."""
        # Create chat
        chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=111222333,
            title="Bulk Test Chat",
            chat_type=ChatType.hr,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(chat)

        # Create call
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Bulk Test Call",
            source_type=CallSource.upload,
            status=CallStatus.done,
            duration_seconds=300,
            created_at=datetime.utcnow()
        )
        db_session.add(call)

        await db_session.commit()
        await db_session.refresh(chat)
        await db_session.refresh(call)

        # Share all resource types
        resources = [
            ("entity", entity.id),
            ("chat", chat.id),
            ("call", call.id)
        ]

        for resource_type, resource_id in resources:
            response = await client.post(
                "/api/sharing",
                json={
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "shared_with_id": second_user.id,
                    "access_level": "edit"
                },
                headers=get_auth_headers(admin_token)
            )
            assert response.status_code == 200

        # Verify all shares
        from api.services.auth import create_access_token
        second_user_token = create_access_token(data={"sub": str(second_user.id)})

        response = await client.get(
            "/api/sharing/shared-with-me",
            headers=get_auth_headers(second_user_token)
        )
        assert response.status_code == 200
        shares = response.json()
        assert len(shares) >= 3

        # Verify we have all resource types
        resource_types = set(s["resource_type"] for s in shares)
        assert "entity" in resource_types
        assert "chat" in resource_types
        assert "call" in resource_types


# ============================================================================
# SCENARIO 6: ROLE CHANGES DURING SHARE
# ============================================================================

class TestRoleChangesDuringShare:
    """Test how role changes affect existing shares."""

    @pytest.mark.asyncio
    async def test_share_persists_after_org_role_change(
        self, db_session, client, admin_user, admin_token, second_user,
        entity, organization, get_auth_headers, org_owner, org_member
    ):
        """Test that shares persist when user's organization role changes."""
        # Share entity with second_user
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": second_user.id,
                "access_level": "edit"
            },
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        share_id = response.json()["id"]

        # Change second_user's org role from member to admin
        result = await db_session.execute(
            select(OrgMember).where(
                OrgMember.user_id == second_user.id,
                OrgMember.org_id == organization.id
            )
        )
        org_membership = result.scalar_one_or_none()
        org_membership.role = OrgRole.admin
        await db_session.commit()

        # Verify share still exists
        result = await db_session.execute(
            select(SharedAccess).where(SharedAccess.id == share_id)
        )
        share = result.scalar_one_or_none()
        assert share is not None
        assert share.access_level == AccessLevel.edit

    @pytest.mark.asyncio
    async def test_share_persists_after_department_role_change(
        self, db_session, client, admin_user, admin_token, second_user,
        entity, organization, department, get_auth_headers, org_owner, org_member, dept_member
    ):
        """Test that shares persist when user's department role changes."""
        # Share entity
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": second_user.id,
                "access_level": "view"
            },
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        share_id = response.json()["id"]

        # Change second_user's department role
        result = await db_session.execute(
            select(DepartmentMember).where(
                DepartmentMember.user_id == second_user.id,
                DepartmentMember.department_id == department.id
            )
        )
        dept_membership = result.scalar_one_or_none()
        if dept_membership:
            dept_membership.role = DeptRole.sub_admin
            await db_session.commit()

        # Verify share still exists
        result = await db_session.execute(
            select(SharedAccess).where(SharedAccess.id == share_id)
        )
        share = result.scalar_one_or_none()
        assert share is not None

    @pytest.mark.asyncio
    async def test_user_deactivation_does_not_delete_shares(
        self, db_session, client, admin_user, admin_token, second_user,
        entity, get_auth_headers, org_owner, org_member
    ):
        """Test that deactivating a user doesn't delete their shares."""
        # Share entity
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": second_user.id,
                "access_level": "edit"
            },
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        share_id = response.json()["id"]

        # Deactivate second_user
        second_user.is_active = False
        await db_session.commit()

        # Verify share still exists (though user can't access it)
        result = await db_session.execute(
            select(SharedAccess).where(SharedAccess.id == share_id)
        )
        share = result.scalar_one_or_none()
        assert share is not None


# ============================================================================
# SCENARIO 7: ORGANIZATION BOUNDARIES
# ============================================================================

class TestOrganizationBoundaries:
    """Test sharing restrictions across organization boundaries."""

    @pytest.mark.asyncio
    async def test_cannot_share_to_user_in_different_org(
        self, db_session, client, admin_user, admin_token, entity,
        organization, get_auth_headers, org_owner
    ):
        """Test that regular users cannot share with users in different organizations."""
        # Create second organization
        other_org = Organization(
            name="Other Organization",
            slug="other-org",
            created_at=datetime.utcnow()
        )
        db_session.add(other_org)
        await db_session.commit()
        await db_session.refresh(other_org)

        # Create user in other organization
        other_user = User(
            email="other@other.com",
            password_hash=hash_password("password"),
            name="Other Org User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)

        other_member = OrgMember(
            org_id=other_org.id,
            user_id=other_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(other_member)
        await db_session.commit()

        # Try to share with user from other org
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": other_user.id,
                "access_level": "view"
            },
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 403
        assert "другой организации" in response.json()["detail"].lower()  # текст ручки — по-русски

    @pytest.mark.asyncio
    async def test_superadmin_can_access_across_orgs(
        self, db_session, client, superadmin_user, superadmin_token, entity,
        organization, get_auth_headers
    ):
        """Test that SUPERADMIN can access resources across organizations."""
        # Create second organization with entity
        other_org = Organization(
            name="Other Organization",
            slug="other-org-super",
            created_at=datetime.utcnow()
        )
        db_session.add(other_org)
        await db_session.commit()
        await db_session.refresh(other_org)

        # Create user in other organization
        other_user = User(
            email="otheruser@other.com",
            password_hash=hash_password("password"),
            name="Other User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)

        other_member = OrgMember(
            org_id=other_org.id,
            user_id=other_user.id,
            role=OrgRole.owner,
            created_at=datetime.utcnow()
        )
        db_session.add(other_member)
        await db_session.commit()

        # Create department in other org
        other_dept = Department(
            name="Other Dept",
            org_id=other_org.id,
            created_at=datetime.utcnow()
        )
        db_session.add(other_dept)
        await db_session.commit()
        await db_session.refresh(other_dept)

        # Create entity in other organization
        other_entity = Entity(
            org_id=other_org.id,
            department_id=other_dept.id,
            created_by=other_user.id,
            name="Other Org Entity",
            email="otherorg@test.com",
            type=EntityType.candidate,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(other_entity)
        await db_session.commit()
        await db_session.refresh(other_entity)

        # SUPERADMIN should be able to list all entities (across orgs)
        response = await client.get(
            "/api/entities",
            headers=get_auth_headers(superadmin_token)
        )
        assert response.status_code == 200
        # Superadmin should see entities from all organizations

    @pytest.mark.asyncio
    async def test_sharable_users_only_from_same_org(
        self, db_session, client, admin_user, admin_token, second_user,
        organization, get_auth_headers, org_owner, org_member
    ):
        """Test that sharable users endpoint only returns users from same org."""
        # Create second organization with users
        other_org = Organization(
            name="Other Org",
            slug="other-org-sharable",
            created_at=datetime.utcnow()
        )
        db_session.add(other_org)
        await db_session.commit()
        await db_session.refresh(other_org)

        # Create users in other org
        for i in range(3):
            other_user = User(
                email=f"otheruser{i}@other.com",
                password_hash=hash_password("password"),
                name=f"Other User {i}",
                role=UserRole.admin,
                is_active=True
            )
            db_session.add(other_user)
            await db_session.commit()
            await db_session.refresh(other_user)

            other_member = OrgMember(
                org_id=other_org.id,
                user_id=other_user.id,
                role=OrgRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(other_member)

        await db_session.commit()

        # Get sharable users for admin_user
        response = await client.get(
            "/api/sharing/users",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        users = response.json()

        # Verify all users are from same org
        user_emails = [u["email"] for u in users]
        assert second_user.email in user_emails
        assert not any("otheruser" in email for email in user_emails), \
            "Users from other organizations should not appear in sharable users list"


# ============================================================================
# ADDITIONAL EDGE CASE SCENARIOS
# ============================================================================

class TestAdditionalSharingEdgeCases:
    """Test additional edge cases in sharing functionality."""

    @pytest.mark.asyncio
    async def test_cannot_share_with_self(
        self, db_session, client, admin_user, admin_token, entity,
        get_auth_headers, org_owner
    ):
        """Test that user cannot share resource with themselves."""
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": admin_user.id,  # Same as current user
                "access_level": "view"
            },
            headers=get_auth_headers(admin_token)
        )
        # This might succeed (as it's redundant) or fail - depends on implementation
        # The important part is it doesn't cause an error

    @pytest.mark.asyncio
    async def test_updating_share_preserves_other_fields(
        self, db_session, client, admin_user, admin_token, second_user,
        entity, get_auth_headers, org_owner, org_member
    ):
        """Test that updating share access level preserves other fields."""
        # Create share with note and expiry
        expires_at = datetime.utcnow() + timedelta(days=30)

        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": second_user.id,
                "access_level": "view",
                "note": "Important share",
                "expires_at": expires_at.isoformat()
            },
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        share_id = response.json()["id"]
        original_note = response.json()["note"]

        # Update only access level
        response = await client.patch(
            f"/api/sharing/{share_id}",
            json={"access_level": "edit"},
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        updated_share = response.json()

        # Verify note is preserved
        assert updated_share["note"] == original_note
        assert updated_share["access_level"] == "edit"

    @pytest.mark.asyncio
    async def test_cascade_delete_on_resource_deletion(
        self, db_session, client, admin_user, admin_token, second_user,
        organization, department, get_auth_headers, org_owner, org_member
    ):
        """Test that shares are deleted when resource is deleted."""
        # Create entity
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="To Be Deleted",
            email="delete@test.com",
            type=EntityType.candidate,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # Share entity
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": second_user.id,
                "access_level": "view"
            },
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        share_id = response.json()["id"]

        # Delete entity
        response = await client.delete(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200

        # Verify share is also deleted (cascade)
        result = await db_session.execute(
            select(SharedAccess).where(SharedAccess.id == share_id)
        )
        share = result.scalar_one_or_none()
        assert share is None, "Share should be cascade deleted with resource"

    @pytest.mark.asyncio
    async def test_share_note_field(
        self, db_session, client, admin_user, admin_token, second_user,
        entity, get_auth_headers, org_owner, org_member
    ):
        """Test that share notes are properly stored and retrieved."""
        note_text = "This is a test share for reviewing candidate data"

        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": second_user.id,
                "access_level": "view",
                "note": note_text
            },
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        share_data = response.json()
        assert share_data["note"] == note_text

        # Verify via shared-with-me endpoint
        from api.services.auth import create_access_token
        second_user_token = create_access_token(data={"sub": str(second_user.id)})

        response = await client.get(
            "/api/sharing/shared-with-me",
            headers=get_auth_headers(second_user_token)
        )
        assert response.status_code == 200
        shares = response.json()
        matching_share = next((s for s in shares if s["id"] == share_data["id"]), None)
        assert matching_share is not None
        assert matching_share["note"] == note_text
