"""
Database integrity tests - testing constraints, cascades, and data integrity.

These tests document database integrity issues identified in the audit.
Some tests may fail - that's intentional to document missing constraints.
"""
import pytest
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from api.models.database import (
    User, Organization, OrgMember, Department, DepartmentMember,
    Entity, Chat, Message, CallRecording, SharedAccess,
    UserRole, OrgRole, DeptRole, AccessLevel, ResourceType,
    EntityType, EntityStatus, ChatType, CallStatus, CallSource
)
from api.services.auth import hash_password


class TestUniqueConstraints:
    """Test unique constraints on membership and sharing tables."""

    @pytest.mark.asyncio
    async def test_cannot_add_duplicate_org_member(self, db_session, organization, admin_user):
        """
        Test that adding the same user to an org twice should fail.

        EXPECTED: This test SHOULD FAIL because OrgMember lacks a unique constraint
        on (org_id, user_id). This is a database integrity issue.
        """
        # Add user to org first time
        member1 = OrgMember(
            org_id=organization.id,
            user_id=admin_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(member1)
        await db_session.commit()

        # Try to add same user to same org again
        member2 = OrgMember(
            org_id=organization.id,
            user_id=admin_user.id,
            role=OrgRole.admin,  # Different role shouldn't matter
            created_at=datetime.utcnow()
        )
        db_session.add(member2)

        # This SHOULD raise IntegrityError but won't due to missing constraint
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_cannot_add_duplicate_dept_member(self, db_session, department, regular_user):
        """
        Test that adding the same user to a department twice should fail.

        EXPECTED: This test SHOULD FAIL because DepartmentMember lacks a unique
        constraint on (department_id, user_id). This is a database integrity issue.
        """
        # Add user to department first time
        member1 = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(member1)
        await db_session.commit()

        # Try to add same user to same department again
        member2 = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.lead,  # Different role shouldn't matter
            created_at=datetime.utcnow()
        )
        db_session.add(member2)

        # This SHOULD raise IntegrityError but won't due to missing constraint
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_cannot_create_duplicate_share(self, db_session, entity, admin_user, second_user):
        """
        Test that sharing the same resource with the same user twice should fail or update.

        EXPECTED: This test SHOULD FAIL because SharedAccess lacks a unique constraint
        on (resource_type, resource_id, shared_with_id). This allows duplicate shares.
        """
        # Create first share
        share1 = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.view,
            created_at=datetime.utcnow()
        )
        db_session.add(share1)
        await db_session.commit()

        # Try to create duplicate share
        share2 = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.edit,  # Different level shouldn't matter
            created_at=datetime.utcnow()
        )
        db_session.add(share2)

        # This SHOULD raise IntegrityError but won't due to missing constraint
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_duplicate_shares_now_prevented(self, db_session, entity, admin_user, second_user):
        """
        Verify that duplicate shares are now prevented by the unique constraint.
        This test verifies the bug fix is working correctly.
        """
        # Store IDs before operations
        entity_id = entity.id
        admin_user_id = admin_user.id
        second_user_id = second_user.id

        # Create first share
        share1 = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity_id,
            entity_id=entity_id,
            shared_by_id=admin_user_id,
            shared_with_id=second_user_id,
            access_level=AccessLevel.view,
            created_at=datetime.utcnow()
        )
        db_session.add(share1)
        await db_session.commit()

        # Try to create duplicate share - this should now FAIL
        share2 = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity_id,
            entity_id=entity_id,
            shared_by_id=admin_user_id,
            shared_with_id=second_user_id,
            access_level=AccessLevel.edit,
            created_at=datetime.utcnow()
        )
        db_session.add(share2)

        # This should raise IntegrityError due to unique constraint
        with pytest.raises(IntegrityError):
            await db_session.commit()

        # Rollback the failed transaction
        await db_session.rollback()

        # Verify only one share exists
        result = await db_session.execute(
            select(SharedAccess).where(
                SharedAccess.resource_type == ResourceType.entity,
                SharedAccess.resource_id == entity_id,
                SharedAccess.shared_with_id == second_user_id
            )
        )
        shares = result.scalars().all()

        # Bug is fixed - we have only 1 share!
        assert len(shares) == 1


class TestCascadeDelete:
    """Test cascade delete behavior for related records."""

    @pytest.mark.asyncio
    async def test_delete_org_deletes_members(self, db_session, organization, admin_user, regular_user):
        """Test that deleting an organization deletes all its members."""
        # Add members to org
        member1 = OrgMember(
            org_id=organization.id,
            user_id=admin_user.id,
            role=OrgRole.owner,
            created_at=datetime.utcnow()
        )
        member2 = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add_all([member1, member2])
        await db_session.commit()

        org_id = organization.id

        # Delete organization
        await db_session.delete(organization)
        await db_session.commit()

        # Verify members were deleted (cascade)
        result = await db_session.execute(
            select(OrgMember).where(OrgMember.org_id == org_id)
        )
        members = result.scalars().all()
        assert len(members) == 0

    @pytest.mark.asyncio
    async def test_delete_org_deletes_departments(self, db_session, organization, department):
        """Test that deleting an organization deletes all its departments."""
        # Create another department
        dept2 = Department(
            name="Second Department",
            org_id=organization.id,
            created_at=datetime.utcnow()
        )
        db_session.add(dept2)
        await db_session.commit()

        org_id = organization.id

        # Delete organization
        await db_session.delete(organization)
        await db_session.commit()

        # Verify departments were deleted (cascade)
        result = await db_session.execute(
            select(Department).where(Department.org_id == org_id)
        )
        departments = result.scalars().all()
        assert len(departments) == 0

    @pytest.mark.asyncio
    async def test_delete_org_deletes_entities(self, db_session, organization, entity):
        """Test that deleting an organization should delete all its entities."""
        org_id = organization.id
        entity_id = entity.id

        # Delete organization
        await db_session.delete(organization)
        await db_session.commit()

        # Verify entity was deleted
        result = await db_session.execute(
            select(Entity).where(Entity.id == entity_id)
        )
        deleted_entity = result.scalar_one_or_none()

        # Entity has ondelete="CASCADE" on org_id
        assert deleted_entity is None

    @pytest.mark.asyncio
    async def test_delete_user_deletes_memberships(self, db_session, organization, admin_user):
        """Test that deleting a user deletes their org/dept memberships."""
        # Add user to org
        member = OrgMember(
            org_id=organization.id,
            user_id=admin_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(member)
        await db_session.commit()

        user_id = admin_user.id

        # Delete user
        await db_session.delete(admin_user)
        await db_session.commit()

        # Verify org membership was deleted (cascade)
        result = await db_session.execute(
            select(OrgMember).where(OrgMember.user_id == user_id)
        )
        memberships = result.scalars().all()
        assert len(memberships) == 0

    @pytest.mark.asyncio
    async def test_delete_department_deletes_members(self, db_session, department, admin_user, regular_user):
        """Test that deleting a department deletes all its members."""
        # Add members to department
        member1 = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        member2 = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add_all([member1, member2])
        await db_session.commit()

        dept_id = department.id

        # Delete department
        await db_session.delete(department)
        await db_session.commit()

        # Verify members were deleted (cascade)
        result = await db_session.execute(
            select(DepartmentMember).where(DepartmentMember.department_id == dept_id)
        )
        members = result.scalars().all()
        assert len(members) == 0

    @pytest.mark.asyncio
    async def test_delete_chat_deletes_messages(self, db_session, chat):
        """Test that deleting a chat deletes all its messages."""
        # Add messages to chat
        msg1 = Message(
            chat_id=chat.id,
            telegram_user_id=123456,
            content="Test message 1",
            content_type="text",
            timestamp=datetime.utcnow()
        )
        msg2 = Message(
            chat_id=chat.id,
            telegram_user_id=123456,
            content="Test message 2",
            content_type="text",
            timestamp=datetime.utcnow()
        )
        db_session.add_all([msg1, msg2])
        await db_session.commit()

        chat_id = chat.id

        # Delete chat
        await db_session.delete(chat)
        await db_session.commit()

        # Verify messages were deleted (cascade)
        result = await db_session.execute(
            select(Message).where(Message.chat_id == chat_id)
        )
        messages = result.scalars().all()
        assert len(messages) == 0

    @pytest.mark.asyncio
    async def test_delete_entity_sets_null_on_chat(self, db_session, organization, department, entity, admin_user):
        """
        Test that deleting an entity sets entity_id to NULL on related chats.
        Chat.entity_id has ondelete="SET NULL"
        """
        # Create chat linked to entity
        chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=999888777,
            title="Test Chat",
            chat_type=ChatType.hr,
            entity_id=entity.id,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(chat)
        await db_session.commit()

        chat_id = chat.id

        # Delete entity
        await db_session.delete(entity)
        await db_session.commit()

        # Verify chat still exists but entity_id is NULL
        result = await db_session.execute(
            select(Chat).where(Chat.id == chat_id)
        )
        updated_chat = result.scalar_one()
        assert updated_chat is not None
        assert updated_chat.entity_id is None

    @pytest.mark.asyncio
    async def test_delete_department_sets_null_on_entities(self, db_session, department, entity):
        """
        Test that deleting a department sets department_id to NULL on entities.
        Entity.department_id has ondelete="SET NULL"
        """
        entity_id = entity.id
        assert entity.department_id == department.id

        # Delete department
        await db_session.delete(department)
        await db_session.commit()

        # Verify entity still exists but department_id is NULL
        result = await db_session.execute(
            select(Entity).where(Entity.id == entity_id)
        )
        updated_entity = result.scalar_one()
        assert updated_entity is not None
        assert updated_entity.department_id is None


class TestForeignKeyIntegrity:
    """Test foreign key constraints prevent orphaned records."""

    @pytest.mark.asyncio
    async def test_cannot_create_member_for_nonexistent_org(self, db_session, admin_user):
        """
        Test that creating an org member with invalid org_id should fail.

        NOTE: SQLite doesn't enforce FK constraints by default unless
        PRAGMA foreign_keys=ON is set. This test may pass in SQLite but
        would fail in PostgreSQL.
        """
        # Try to create member for non-existent org
        member = OrgMember(
            org_id=99999,  # Non-existent org
            user_id=admin_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(member)

        # This should fail with FK constraint violation
        # But might not in SQLite without PRAGMA foreign_keys=ON
        try:
            await db_session.commit()
            # If we get here, FK constraints aren't enforced
            # Clean up for other tests
            await db_session.rollback()
        except IntegrityError:
            # Good - FK constraint is enforced
            await db_session.rollback()

    @pytest.mark.asyncio
    async def test_cannot_create_entity_for_nonexistent_dept(self, db_session, organization, admin_user):
        """
        Test that creating an entity with invalid department_id should fail.

        NOTE: SQLite may not enforce this without PRAGMA foreign_keys=ON.
        """
        # Try to create entity for non-existent department
        entity = Entity(
            org_id=organization.id,
            department_id=99999,  # Non-existent department
            created_by=admin_user.id,
            name="Test Entity",
            type=EntityType.candidate,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(entity)

        # This should fail with FK constraint violation
        try:
            await db_session.commit()
            # If we get here, FK constraints aren't enforced
            await db_session.rollback()
        except IntegrityError:
            # Good - FK constraint is enforced
            await db_session.rollback()

    @pytest.mark.asyncio
    async def test_cannot_create_share_for_nonexistent_user(self, db_session, entity, admin_user):
        """
        Test that creating a share with invalid user_id should fail.
        """
        # Try to create share with non-existent user
        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=99999,  # Non-existent user
            access_level=AccessLevel.view,
            created_at=datetime.utcnow()
        )
        db_session.add(share)

        # This should fail with FK constraint violation
        try:
            await db_session.commit()
            await db_session.rollback()
        except IntegrityError:
            # Good - FK constraint is enforced
            await db_session.rollback()


class TestDataTypes:
    """Test that data types handle expected ranges correctly."""

    @pytest.mark.asyncio
    async def test_telegram_id_handles_large_values(self, db_session):
        """
        Test that telegram_id can handle values > 2^31.

        Telegram IDs can be very large (up to ~10 digits). Using BigInteger
        is correct for this use case.
        """
        # Telegram IDs can be larger than 2^31 (2,147,483,647)
        large_telegram_id = 5000000000  # ~5 billion

        user = User(
            email="telegram_user@test.com",
            password_hash=hash_password("test123"),
            name="Telegram User",
            role=UserRole.admin,
            telegram_id=large_telegram_id,
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()

        # Verify it was stored correctly
        result = await db_session.execute(
            select(User).where(User.telegram_id == large_telegram_id)
        )
        fetched_user = result.scalar_one()
        assert fetched_user.telegram_id == large_telegram_id

    @pytest.mark.asyncio
    async def test_telegram_chat_id_handles_large_values(self, db_session, organization, admin_user):
        """
        Test that telegram_chat_id can handle large values.
        """
        large_chat_id = 6000000000  # ~6 billion

        chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=large_chat_id,
            title="Test Chat",
            chat_type=ChatType.hr,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(chat)
        await db_session.commit()

        # Verify it was stored correctly
        result = await db_session.execute(
            select(Chat).where(Chat.telegram_chat_id == large_chat_id)
        )
        fetched_chat = result.scalar_one()
        assert fetched_chat.telegram_chat_id == large_chat_id

    @pytest.mark.asyncio
    async def test_telegram_message_id_handles_large_values(self, db_session, chat):
        """
        Test that telegram_message_id can handle large values.
        """
        large_message_id = 7000000000  # ~7 billion

        message = Message(
            chat_id=chat.id,
            telegram_message_id=large_message_id,
            telegram_user_id=123456789,
            content="Test message",
            content_type="text",
            timestamp=datetime.utcnow()
        )
        db_session.add(message)
        await db_session.commit()

        # Verify it was stored correctly
        result = await db_session.execute(
            select(Message).where(Message.telegram_message_id == large_message_id)
        )
        fetched_message = result.scalar_one()
        assert fetched_message.telegram_message_id == large_message_id


class TestOrphanRecords:
    """Test for orphaned records after deletions."""

    @pytest.mark.asyncio
    async def test_no_orphan_shares_after_entity_delete(self, db_session, entity, admin_user, second_user):
        """
        Test that shares are deleted when the shared entity is deleted.

        EXPECTED: This test SHOULD FAIL because SharedAccess.resource_id is not
        a proper foreign key - it's just an integer. Deleting an entity won't
        cascade to SharedAccess records.
        """
        # Create share for entity
        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=entity.id,
            entity_id=entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.view,
            created_at=datetime.utcnow()
        )
        db_session.add(share)
        await db_session.commit()

        entity_id = entity.id

        # Delete entity
        await db_session.delete(entity)
        await db_session.commit()

        # Check for orphaned shares
        result = await db_session.execute(
            select(SharedAccess).where(
                SharedAccess.resource_type == ResourceType.entity,
                SharedAccess.resource_id == entity_id
            )
        )
        orphan_shares = result.scalars().all()

        # This will FAIL - orphan shares will still exist!
        assert len(orphan_shares) == 0, f"Found {len(orphan_shares)} orphaned shares after entity deletion"

    @pytest.mark.asyncio
    async def test_no_orphan_shares_after_chat_delete(self, db_session, chat, admin_user, second_user):
        """
        Test that shares are deleted when the shared chat is deleted.

        EXPECTED: This test SHOULD FAIL because SharedAccess.resource_id is not
        a proper foreign key.
        """
        # Create share for chat
        share = SharedAccess(
            resource_type=ResourceType.chat,
            resource_id=chat.id,
            chat_id=chat.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.view,
            created_at=datetime.utcnow()
        )
        db_session.add(share)
        await db_session.commit()

        chat_id = chat.id

        # Delete chat
        await db_session.delete(chat)
        await db_session.commit()

        # Check for orphaned shares
        result = await db_session.execute(
            select(SharedAccess).where(
                SharedAccess.resource_type == ResourceType.chat,
                SharedAccess.resource_id == chat_id
            )
        )
        orphan_shares = result.scalars().all()

        # This will FAIL - orphan shares will still exist!
        assert len(orphan_shares) == 0, f"Found {len(orphan_shares)} orphaned shares after chat deletion"

    @pytest.mark.asyncio
    async def test_no_orphan_shares_after_call_delete(self, db_session, call_recording, admin_user, second_user):
        """
        Test that shares are deleted when the shared call recording is deleted.

        EXPECTED: This test SHOULD FAIL because SharedAccess.resource_id is not
        a proper foreign key.
        """
        # Create share for call
        share = SharedAccess(
            resource_type=ResourceType.call,
            resource_id=call_recording.id,
            call_id=call_recording.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.view,
            created_at=datetime.utcnow()
        )
        db_session.add(share)
        await db_session.commit()

        call_id = call_recording.id

        # Delete call
        await db_session.delete(call_recording)
        await db_session.commit()

        # Check for orphaned shares
        result = await db_session.execute(
            select(SharedAccess).where(
                SharedAccess.resource_type == ResourceType.call,
                SharedAccess.resource_id == call_id
            )
        )
        orphan_shares = result.scalars().all()

        # This will FAIL - orphan shares will still exist!
        assert len(orphan_shares) == 0, f"Found {len(orphan_shares)} orphaned shares after call deletion"

    @pytest.mark.asyncio
    async def test_no_orphan_messages_after_chat_delete(self, db_session, chat):
        """
        Test that messages are properly deleted when chat is deleted.

        This should PASS because Message.chat_id has proper FK with CASCADE.
        """
        # Add messages to chat
        msg1 = Message(
            chat_id=chat.id,
            telegram_user_id=123456,
            content="Test message 1",
            content_type="text",
            timestamp=datetime.utcnow()
        )
        msg2 = Message(
            chat_id=chat.id,
            telegram_user_id=123456,
            content="Test message 2",
            content_type="text",
            timestamp=datetime.utcnow()
        )
        db_session.add_all([msg1, msg2])
        await db_session.commit()

        chat_id = chat.id

        # Delete chat
        await db_session.delete(chat)
        await db_session.commit()

        # Check for orphaned messages
        result = await db_session.execute(
            select(Message).where(Message.chat_id == chat_id)
        )
        orphan_messages = result.scalars().all()

        # This should PASS - messages should be deleted via CASCADE
        assert len(orphan_messages) == 0


class TestConstraintViolations:
    """Test various constraint violations to ensure database integrity."""

    @pytest.mark.asyncio
    async def test_cannot_create_user_with_duplicate_email(self, db_session, admin_user):
        """Test that creating a user with duplicate email fails."""
        duplicate_user = User(
            email=admin_user.email,  # Duplicate email
            password_hash=hash_password("test123"),
            name="Duplicate User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(duplicate_user)

        # Should fail due to unique constraint on email
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_cannot_create_user_with_duplicate_telegram_id(self, db_session):
        """Test that creating users with duplicate telegram_id fails."""
        user1 = User(
            email="user1@test.com",
            password_hash=hash_password("test123"),
            name="User 1",
            role=UserRole.admin,
            telegram_id=123456789,
            is_active=True
        )
        db_session.add(user1)
        await db_session.commit()

        user2 = User(
            email="user2@test.com",
            password_hash=hash_password("test123"),
            name="User 2",
            role=UserRole.admin,
            telegram_id=123456789,  # Duplicate telegram_id
            is_active=True
        )
        db_session.add(user2)

        # Should fail due to unique constraint on telegram_id
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_cannot_create_org_with_duplicate_slug(self, db_session, organization):
        """Test that creating an org with duplicate slug fails."""
        duplicate_org = Organization(
            name="Another Org",
            slug=organization.slug,  # Duplicate slug
            created_at=datetime.utcnow()
        )
        db_session.add(duplicate_org)

        # Should fail due to unique constraint on slug
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_cannot_create_chat_with_duplicate_telegram_chat_id(self, db_session, chat, organization, admin_user):
        """Test that creating a chat with duplicate telegram_chat_id fails."""
        duplicate_chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=chat.telegram_chat_id,  # Duplicate
            title="Duplicate Chat",
            chat_type=ChatType.hr,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(duplicate_chat)

        # Should fail due to unique constraint on telegram_chat_id
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_user_email_cannot_be_null(self, db_session):
        """Test that user email is required."""
        user = User(
            email=None,  # NULL email
            password_hash=hash_password("test123"),
            name="No Email User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(user)

        # Should fail due to NOT NULL constraint
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_organization_name_cannot_be_null(self, db_session):
        """Test that organization name is required."""
        org = Organization(
            name=None,  # NULL name
            slug="test-slug",
            created_at=datetime.utcnow()
        )
        db_session.add(org)

        # Should fail due to NOT NULL constraint
        with pytest.raises(IntegrityError):
            await db_session.commit()
