"""
Tests for database constraints, indexes, and cascade deletes.

Verifies:
1. UNIQUE constraints prevent duplicate records
2. CASCADE deletes properly clean up related records
3. Database integrity is maintained
"""
import pytest
from sqlalchemy import exc, inspect
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import (
    Organization, OrgMember, Department, DepartmentMember,
    Entity, Chat, CallRecording, SharedAccess, User, Message,
    OrgRole, DeptRole, EntityType, EntityStatus, ChatType,
    CallStatus, CallSource, ResourceType, AccessLevel
)


class TestUniqueConstraints:
    """Tests for UNIQUE constraints on tables."""

    async def test_org_member_unique_constraint(
        self,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User
    ):
        """Test that duplicate org members are rejected."""
        # Create first membership
        member1 = OrgMember(
            org_id=organization.id,
            user_id=admin_user.id,
            role=OrgRole.member
        )
        db_session.add(member1)
        await db_session.commit()

        # Try to create duplicate membership - should fail
        member2 = OrgMember(
            org_id=organization.id,
            user_id=admin_user.id,
            role=OrgRole.admin  # Different role but same user+org
        )
        db_session.add(member2)

        with pytest.raises(exc.IntegrityError) as excinfo:
            await db_session.commit()

        assert "uq_org_member_user_org" in str(excinfo.value).lower() or "unique" in str(excinfo.value).lower()
        await db_session.rollback()

    async def test_dept_member_unique_constraint(
        self,
        db_session: AsyncSession,
        department: Department,
        admin_user: User
    ):
        """Test that duplicate department members are rejected."""
        # Create first membership
        member1 = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.member
        )
        db_session.add(member1)
        await db_session.commit()

        # Try to create duplicate membership - should fail
        member2 = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.lead  # Different role but same user+dept
        )
        db_session.add(member2)

        with pytest.raises(exc.IntegrityError) as excinfo:
            await db_session.commit()

        assert "uq_dept_member_user_dept" in str(excinfo.value).lower() or "unique" in str(excinfo.value).lower()
        await db_session.rollback()

    async def test_shared_access_unique_constraint_basic(
        self,
        db_session: AsyncSession,
        entity: Entity,
        admin_user: User,
        second_user: User
    ):
        """Test that duplicate share records are rejected (same sharer)."""
        # Create first share
        share1 = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.view
        )
        db_session.add(share1)
        await db_session.commit()

        # Try to create duplicate share - should fail
        share2 = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=admin_user.id,  # Same sharer
            shared_with_id=second_user.id,
            access_level=AccessLevel.edit  # Different access level
        )
        db_session.add(share2)

        with pytest.raises(exc.IntegrityError) as excinfo:
            await db_session.commit()

        assert "uq_shared_access_resource_user" in str(excinfo.value).lower() or "unique" in str(excinfo.value).lower()
        await db_session.rollback()

    async def test_shared_access_allows_different_sharers(
        self,
        db_session: AsyncSession,
        entity: Entity,
        admin_user: User,
        regular_user: User,
        second_user: User
    ):
        """Test that the same resource can be shared with the same person by different users."""
        # Create first share from admin_user
        share1 = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.view
        )
        db_session.add(share1)
        await db_session.commit()

        # Create second share from regular_user to same person - should succeed
        share2 = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=regular_user.id,  # Different sharer!
            shared_with_id=second_user.id,  # Same recipient
            access_level=AccessLevel.edit
        )
        db_session.add(share2)
        await db_session.commit()  # Should not raise

        # Verify both shares exist
        await db_session.refresh(share1)
        await db_session.refresh(share2)
        assert share1.id != share2.id
        assert share1.shared_by_id != share2.shared_by_id


class TestCascadeDeletes:
    """Tests for CASCADE delete behavior."""

    async def test_organization_delete_cascades_to_chats(
        self,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User
    ):
        """Test that deleting an organization cascades to its chats."""
        # Create chat in organization
        chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=123456789,
            title="Test Chat",
            chat_type=ChatType.hr
        )
        db_session.add(chat)
        await db_session.commit()

        chat_id = chat.id

        # Delete organization
        await db_session.delete(organization)
        await db_session.commit()

        # Verify chat was deleted
        from sqlalchemy import select
        result = await db_session.execute(
            select(Chat).where(Chat.id == chat_id)
        )
        deleted_chat = result.scalar_one_or_none()
        assert deleted_chat is None, "Chat should be deleted when organization is deleted"

    async def test_organization_delete_cascades_to_calls(
        self,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User
    ):
        """Test that deleting an organization cascades to its call recordings."""
        # Create call in organization
        call = CallRecording(
            org_id=organization.id,
            owner_id=admin_user.id,
            title="Test Call",
            source_type=CallSource.upload,
            status=CallStatus.done
        )
        db_session.add(call)
        await db_session.commit()

        call_id = call.id

        # Delete organization
        await db_session.delete(organization)
        await db_session.commit()

        # Verify call was deleted
        from sqlalchemy import select
        result = await db_session.execute(
            select(CallRecording).where(CallRecording.id == call_id)
        )
        deleted_call = result.scalar_one_or_none()
        assert deleted_call is None, "Call should be deleted when organization is deleted"

    async def test_organization_delete_cascades_to_entities(
        self,
        db_session: AsyncSession,
        organization: Organization,
        department: Department,
        admin_user: User
    ):
        """Test that deleting an organization cascades to its entities."""
        # Create entity in organization
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Test Entity",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()

        entity_id = entity.id

        # Delete organization
        await db_session.delete(organization)
        await db_session.commit()

        # Verify entity was deleted
        from sqlalchemy import select
        result = await db_session.execute(
            select(Entity).where(Entity.id == entity_id)
        )
        deleted_entity = result.scalar_one_or_none()
        assert deleted_entity is None, "Entity should be deleted when organization is deleted"

    async def test_chat_delete_cascades_to_messages(
        self,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User
    ):
        """Test that deleting a chat cascades to its messages."""
        # Create chat
        chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=123456789,
            title="Test Chat",
            chat_type=ChatType.hr
        )
        db_session.add(chat)
        await db_session.flush()

        # Create message in chat
        message = Message(
            chat_id=chat.id,
            telegram_message_id=111,
            telegram_user_id=222,
            content="Test message",
            content_type="text"
        )
        db_session.add(message)
        await db_session.commit()

        message_id = message.id

        # Delete chat
        await db_session.delete(chat)
        await db_session.commit()

        # Verify message was deleted
        from sqlalchemy import select
        result = await db_session.execute(
            select(Message).where(Message.id == message_id)
        )
        deleted_message = result.scalar_one_or_none()
        assert deleted_message is None, "Message should be deleted when chat is deleted"

    async def test_entity_delete_sets_null_on_calls(
        self,
        db_session: AsyncSession,
        organization: Organization,
        department: Department,
        admin_user: User
    ):
        """Test that deleting an entity sets entity_id to NULL on calls (SET NULL behavior)."""
        # Create entity
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Test Entity",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.flush()

        # Create call linked to entity
        call = CallRecording(
            org_id=organization.id,
            entity_id=entity.id,
            owner_id=admin_user.id,
            title="Test Call",
            source_type=CallSource.upload,
            status=CallStatus.done
        )
        db_session.add(call)
        await db_session.commit()

        call_id = call.id

        # Delete entity
        await db_session.delete(entity)
        await db_session.commit()

        # Verify call still exists but entity_id is NULL
        from sqlalchemy import select
        result = await db_session.execute(
            select(CallRecording).where(CallRecording.id == call_id)
        )
        remaining_call = result.scalar_one_or_none()
        assert remaining_call is not None, "Call should still exist after entity deletion"
        assert remaining_call.entity_id is None, "Call's entity_id should be NULL after entity deletion"

    async def test_department_delete_cascades_to_members(
        self,
        db_session: AsyncSession,
        department: Department,
        admin_user: User
    ):
        """Test that deleting a department cascades to its members."""
        # Create department member
        member = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.member
        )
        db_session.add(member)
        await db_session.commit()

        member_id = member.id

        # Delete department
        await db_session.delete(department)
        await db_session.commit()

        # Verify member was deleted
        from sqlalchemy import select
        result = await db_session.execute(
            select(DepartmentMember).where(DepartmentMember.id == member_id)
        )
        deleted_member = result.scalar_one_or_none()
        assert deleted_member is None, "Department member should be deleted when department is deleted"


class TestIndexes:
    """Tests for database indexes."""

    async def test_indexed_columns_exist(self, db_session: AsyncSession):
        """Verify that frequently searched columns have indexes defined in models."""
        # This is a model-level test - we verify the index=True is set on columns
        # SQLite doesn't provide easy introspection of indexes, so we check the model definitions

        # Organization
        assert Organization.name.index is True, "Organization.name should have index"

        # Department
        assert Department.name.index is True, "Department.name should have index"

        # Entity
        assert Entity.name.index is True, "Entity.name should have index"
        assert Entity.email.index is True, "Entity.email should have index"

        # User
        assert User.name.index is True, "User.name should have index"

        # Message
        assert Message.content_type.index is True, "Message.content_type should have index"


class TestComplexCascadeScenarios:
    """Tests for complex cascade scenarios with multiple levels."""

    async def test_organization_delete_cascades_multiple_levels(
        self,
        db_session: AsyncSession,
        organization: Organization,
        department: Department,
        admin_user: User
    ):
        """Test that deleting an organization cascades through multiple levels."""
        # Create entity in organization
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Test Entity",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.flush()

        # Create chat linked to entity
        chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            entity_id=entity.id,
            telegram_chat_id=123456789,
            title="Test Chat",
            chat_type=ChatType.hr
        )
        db_session.add(chat)
        await db_session.flush()

        # Create message in chat
        message = Message(
            chat_id=chat.id,
            telegram_message_id=111,
            telegram_user_id=222,
            content="Test message",
            content_type="text"
        )
        db_session.add(message)
        await db_session.commit()

        entity_id = entity.id
        chat_id = chat.id
        message_id = message.id

        # Delete organization - should cascade through all levels
        await db_session.delete(organization)
        await db_session.commit()

        # Verify all related records were deleted
        from sqlalchemy import select

        result = await db_session.execute(select(Entity).where(Entity.id == entity_id))
        assert result.scalar_one_or_none() is None, "Entity should be deleted"

        result = await db_session.execute(select(Chat).where(Chat.id == chat_id))
        assert result.scalar_one_or_none() is None, "Chat should be deleted"

        result = await db_session.execute(select(Message).where(Message.id == message_id))
        assert result.scalar_one_or_none() is None, "Message should be deleted"
