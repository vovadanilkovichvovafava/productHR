"""
Tests for SUPERADMIN data visibility across organizations.

These tests verify that SUPERADMIN users can see ALL data across ALL organizations,
even without being a member of any organization. This is a critical fix that was
implemented to ensure superadmin has "god mode" access to all system data.

Bug fixed: Previously, superadmin couldn't see data because:
1. get_user_org() returned None for users not in any org
2. Route handlers returned empty [] before checking if user was superadmin
3. Now superadmin check happens FIRST, before org membership check
"""
import pytest
from datetime import datetime

from api.models.database import (
    User, UserRole, Organization, OrgMember, OrgRole,
    Chat, Entity, CallRecording, ChatType, EntityType, EntityStatus,
    CallSource, CallStatus
)


class TestSuperadminChatsVisibility:
    """Test that superadmin can see chats across all organizations without org membership."""

    @pytest.mark.asyncio
    async def test_superadmin_sees_all_chats_without_org_membership(
        self, client, db_session, superadmin_user, superadmin_token,
        organization, admin_user, get_auth_headers, org_owner
    ):
        """
        CRITICAL TEST: Superadmin WITHOUT org membership can see chats in that org.

        This verifies the fix where we check UserRole.superadmin BEFORE checking
        org membership in the chats route.
        """
        # Create a chat in the organization (owned by admin_user who IS in the org)
        chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=999888777,
            title="Org Chat For Superadmin Test",
            chat_type=ChatType.hr,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(chat)
        await db_session.commit()

        # Superadmin is NOT a member of the organization - verify this
        from sqlalchemy import select
        stmt = select(OrgMember).where(OrgMember.user_id == superadmin_user.id)
        result = await db_session.execute(stmt)
        org_membership = result.scalar_one_or_none()
        assert org_membership is None, "Superadmin should NOT be in any org for this test"

        # Request chats as superadmin
        response = await client.get(
            "/api/chats",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200, f"Superadmin should be able to list chats, got {response.status_code}"
        data = response.json()

        # Superadmin should see the chat created in the organization
        chat_ids = [c["id"] for c in data]
        assert chat.id in chat_ids, \
            f"CRITICAL BUG: Superadmin cannot see org chats! This means the fix is broken. Chat IDs: {chat_ids}"

    @pytest.mark.asyncio
    async def test_superadmin_sees_chats_from_multiple_orgs(
        self, client, db_session, superadmin_user, superadmin_token,
        organization, second_organization, admin_user, second_user,
        get_auth_headers, org_owner
    ):
        """
        Superadmin should see chats from ALL organizations simultaneously.
        """
        # Create org membership for second user in second org
        second_org_member = OrgMember(
            org_id=second_organization.id,
            user_id=second_user.id,
            role=OrgRole.owner,
            created_at=datetime.utcnow()
        )
        db_session.add(second_org_member)

        # Create chat in first organization
        chat1 = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=111222333,
            title="Chat in Org 1",
            chat_type=ChatType.hr,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(chat1)

        # Create chat in second organization
        chat2 = Chat(
            org_id=second_organization.id,
            owner_id=second_user.id,
            telegram_chat_id=444555666,
            title="Chat in Org 2",
            chat_type=ChatType.sales,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(chat2)
        await db_session.commit()

        # Request chats as superadmin
        response = await client.get(
            "/api/chats",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        chat_ids = [c["id"] for c in data]

        # Should see chats from BOTH organizations
        assert chat1.id in chat_ids, "Superadmin should see chat from org 1"
        assert chat2.id in chat_ids, "Superadmin should see chat from org 2"


class TestSuperadminEntitiesVisibility:
    """Test that superadmin can see entities across all organizations without org membership."""

    @pytest.mark.asyncio
    async def test_superadmin_sees_all_entities_without_org_membership(
        self, client, db_session, superadmin_user, superadmin_token,
        organization, department, admin_user, get_auth_headers, org_owner, dept_lead
    ):
        """
        CRITICAL TEST: Superadmin WITHOUT org membership can see entities in that org.
        """
        # Create an entity in the organization
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Test Contact for Superadmin",
            email="superadmin-test@example.com",
            type=EntityType.candidate,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(entity)
        await db_session.commit()

        # Verify superadmin is NOT in any org
        from sqlalchemy import select
        stmt = select(OrgMember).where(OrgMember.user_id == superadmin_user.id)
        result = await db_session.execute(stmt)
        org_membership = result.scalar_one_or_none()
        assert org_membership is None, "Superadmin should NOT be in any org for this test"

        # Request entities as superadmin
        response = await client.get(
            "/api/entities",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200, f"Superadmin should be able to list entities, got {response.status_code}"
        data = response.json()

        # Superadmin should see the entity
        entity_ids = [e["id"] for e in data]
        assert entity.id in entity_ids, \
            f"CRITICAL BUG: Superadmin cannot see org entities! Entity IDs: {entity_ids}"

    @pytest.mark.asyncio
    async def test_superadmin_sees_entities_from_multiple_orgs(
        self, client, db_session, superadmin_user, superadmin_token,
        organization, second_organization, department, admin_user, second_user,
        get_auth_headers, org_owner, dept_lead
    ):
        """
        Superadmin should see entities from ALL organizations simultaneously.
        """
        # Create department in second org
        from api.models.database import Department
        dept2 = Department(
            name="Second Dept",
            org_id=second_organization.id,
            created_at=datetime.utcnow()
        )
        db_session.add(dept2)

        # Create org membership for second user
        second_org_member = OrgMember(
            org_id=second_organization.id,
            user_id=second_user.id,
            role=OrgRole.owner,
            created_at=datetime.utcnow()
        )
        db_session.add(second_org_member)
        await db_session.flush()

        # Create entity in first org
        entity1 = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Entity in Org 1",
            email="entity1@org1.com",
            type=EntityType.candidate,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(entity1)

        # Create entity in second org
        entity2 = Entity(
            org_id=second_organization.id,
            department_id=dept2.id,
            created_by=second_user.id,
            name="Entity in Org 2",
            email="entity2@org2.com",
            type=EntityType.client,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(entity2)
        await db_session.commit()

        # Request entities as superadmin
        response = await client.get(
            "/api/entities",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        entity_ids = [e["id"] for e in data]

        # Should see entities from BOTH organizations
        assert entity1.id in entity_ids, "Superadmin should see entity from org 1"
        assert entity2.id in entity_ids, "Superadmin should see entity from org 2"


class TestSuperadminCallsVisibility:
    """Test that superadmin can see calls across all organizations without org membership."""

    @pytest.mark.asyncio
    async def test_superadmin_sees_all_calls_without_org_membership(
        self, client, db_session, superadmin_user, superadmin_token,
        organization, admin_user, get_auth_headers, org_owner
    ):
        """
        CRITICAL TEST: Superadmin WITHOUT org membership can see calls in that org.
        """
        # Create a call recording in the organization
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Test Call for Superadmin",
            source_type=CallSource.upload,
            status=CallStatus.done,
            duration_seconds=300,
            created_at=datetime.utcnow()
        )
        db_session.add(call)
        await db_session.commit()

        # Verify superadmin is NOT in any org
        from sqlalchemy import select
        stmt = select(OrgMember).where(OrgMember.user_id == superadmin_user.id)
        result = await db_session.execute(stmt)
        org_membership = result.scalar_one_or_none()
        assert org_membership is None, "Superadmin should NOT be in any org for this test"

        # Request calls as superadmin
        response = await client.get(
            "/api/calls",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200, f"Superadmin should be able to list calls, got {response.status_code}"
        data = response.json()

        # Superadmin should see the call
        call_ids = [c["id"] for c in data]
        assert call.id in call_ids, \
            f"CRITICAL BUG: Superadmin cannot see org calls! Call IDs: {call_ids}"

    @pytest.mark.asyncio
    async def test_superadmin_sees_calls_from_multiple_orgs(
        self, client, db_session, superadmin_user, superadmin_token,
        organization, second_organization, admin_user, second_user,
        get_auth_headers, org_owner
    ):
        """
        Superadmin should see calls from ALL organizations simultaneously.
        """
        # Create org membership for second user
        second_org_member = OrgMember(
            org_id=second_organization.id,
            user_id=second_user.id,
            role=OrgRole.owner,
            created_at=datetime.utcnow()
        )
        db_session.add(second_org_member)

        # Create call in first org
        call1 = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Call in Org 1",
            source_type=CallSource.upload,
            status=CallStatus.done,
            duration_seconds=300,
            created_at=datetime.utcnow()
        )
        db_session.add(call1)

        # Create call in second org
        call2 = CallRecording(
            org_id=second_organization.id,
            owner_id=second_user.id,
            title="Call in Org 2",
            source_type=CallSource.meet,
            status=CallStatus.done,
            duration_seconds=600,
            created_at=datetime.utcnow()
        )
        db_session.add(call2)
        await db_session.commit()

        # Request calls as superadmin
        response = await client.get(
            "/api/calls",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        call_ids = [c["id"] for c in data]

        # Should see calls from BOTH organizations
        assert call1.id in call_ids, "Superadmin should see call from org 1"
        assert call2.id in call_ids, "Superadmin should see call from org 2"


class TestSuperadminStatsVisibility:
    """Test that superadmin can see stats across all organizations."""

    @pytest.mark.asyncio
    async def test_superadmin_stats_include_all_orgs(
        self, client, db_session, superadmin_user, superadmin_token,
        organization, second_organization, admin_user, second_user,
        get_auth_headers, org_owner
    ):
        """
        Superadmin stats should aggregate data from ALL organizations.
        """
        # Create org membership for second user
        second_org_member = OrgMember(
            org_id=second_organization.id,
            user_id=second_user.id,
            role=OrgRole.owner,
            created_at=datetime.utcnow()
        )
        db_session.add(second_org_member)

        # Create chats in both orgs
        chat1 = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=777888999,
            title="Stats Chat Org 1",
            chat_type=ChatType.hr,
            is_active=True,
            created_at=datetime.utcnow()
        )
        chat2 = Chat(
            org_id=second_organization.id,
            owner_id=second_user.id,
            telegram_chat_id=111222333,
            title="Stats Chat Org 2",
            chat_type=ChatType.sales,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add_all([chat1, chat2])
        await db_session.commit()

        # Request stats as superadmin
        response = await client.get(
            "/api/stats",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Stats should include chats from both orgs
        assert data["total_chats"] >= 2, \
            f"Superadmin stats should include chats from all orgs, got {data['total_chats']}"


class TestRegularUserCannotSeeOtherOrgsData:
    """Verify that regular users (non-superadmin) still can't see other org's data."""

    @pytest.mark.asyncio
    async def test_regular_user_cannot_see_other_org_chats(
        self, client, db_session, admin_user, admin_token, second_user, second_user_token,
        organization, second_organization, get_auth_headers, org_owner
    ):
        """
        Regular user should only see chats from their own organization.
        This ensures the superadmin fix doesn't break regular user isolation.
        """
        # Create org membership for second user in SECOND org
        second_org_member = OrgMember(
            org_id=second_organization.id,
            user_id=second_user.id,
            role=OrgRole.owner,
            created_at=datetime.utcnow()
        )
        db_session.add(second_org_member)

        # Create chat in first org (admin_user's org)
        chat1 = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=555666777,
            title="Chat in Admin's Org",
            chat_type=ChatType.hr,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(chat1)
        await db_session.commit()

        # Second user (in different org) should NOT see admin's chat
        response = await client.get(
            "/api/chats",
            headers=get_auth_headers(second_user_token)
        )

        assert response.status_code == 200
        data = response.json()
        chat_ids = [c["id"] for c in data]

        # Second user should NOT see chat1 (from different org)
        assert chat1.id not in chat_ids, \
            "SECURITY BUG: Regular user can see chats from other organization!"

    @pytest.mark.asyncio
    async def test_user_without_org_sees_empty_list(
        self, client, db_session, regular_user, user_token, organization,
        admin_user, get_auth_headers, org_owner
    ):
        """
        User who is not in ANY organization should see empty list (not error).
        This is different from superadmin - regular user just sees nothing.
        """
        # Create a chat in the organization
        chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=888999000,
            title="Chat User Cannot See",
            chat_type=ChatType.hr,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(chat)
        await db_session.commit()

        # regular_user is NOT in any org, should get empty list
        response = await client.get(
            "/api/chats",
            headers=get_auth_headers(user_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Should be empty, not error
        assert len(data) == 0, "User without org should see empty list, not error"
