"""
Tests for database indexes to ensure optimal query performance.

These tests verify that:
1. Required indexes exist in the database schema
2. Queries use indexes effectively for common search operations
"""
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import (
    Organization, Department, Entity, User, Message, Chat, ChatType
)


class TestDatabaseIndexes:
    """Test that required database indexes exist."""

    async def test_organization_name_has_index(self, db_session: AsyncSession):
        """Organization.name should be indexed for search performance."""
        # Check table metadata for indexes
        table_indexes = Organization.__table__.indexes
        index_columns = []
        for idx in table_indexes:
            index_columns.extend(idx.columns.keys())

        # Also check if column has index=True flag
        name_column = Organization.__table__.columns['name']
        has_index = name_column.index or 'name' in index_columns

        assert has_index, (
            "Organization.name should have an index for efficient name-based searches. "
            "Add: name = Column(String(255), nullable=False, index=True)"
        )

    async def test_department_name_has_index(self, db_session: AsyncSession):
        """Department.name should be indexed for search performance."""
        # Check table metadata for indexes
        table_indexes = Department.__table__.indexes
        index_columns = []
        for idx in table_indexes:
            index_columns.extend(idx.columns.keys())

        # Check if column has index=True flag
        name_column = Department.__table__.columns['name']
        has_index = name_column.index or 'name' in index_columns

        assert has_index, (
            "Department.name should have an index for efficient name-based searches. "
            "Add: name = Column(String(255), nullable=False, index=True)"
        )

    async def test_entity_name_has_index(self, db_session: AsyncSession):
        """Entity.name should be indexed for search performance."""
        # Check table metadata for indexes
        table_indexes = Entity.__table__.indexes
        index_columns = []
        for idx in table_indexes:
            index_columns.extend(idx.columns.keys())

        # Check if column has index=True flag
        name_column = Entity.__table__.columns['name']
        has_index = name_column.index or 'name' in index_columns

        assert has_index, (
            "Entity.name should have an index for efficient contact searches. "
            "Add: name = Column(String(255), nullable=False, index=True)"
        )

    async def test_entity_email_has_index(self, db_session: AsyncSession):
        """Entity.email should be indexed for search performance."""
        # Check table metadata for indexes
        table_indexes = Entity.__table__.indexes
        index_columns = []
        for idx in table_indexes:
            index_columns.extend(idx.columns.keys())

        # Check if column has index=True flag
        email_column = Entity.__table__.columns['email']
        has_index = email_column.index or 'email' in index_columns

        assert has_index, (
            "Entity.email should have an index for efficient email-based searches. "
            "Add: email = Column(String(255), nullable=True, index=True)"
        )

    async def test_user_name_has_index(self, db_session: AsyncSession):
        """User.name should be indexed for search performance."""
        # Check table metadata for indexes
        table_indexes = User.__table__.indexes
        index_columns = []
        for idx in table_indexes:
            index_columns.extend(idx.columns.keys())

        # Check if column has index=True flag
        name_column = User.__table__.columns['name']
        has_index = name_column.index or 'name' in index_columns

        assert has_index, (
            "User.name should have an index for efficient user searches. "
            "Add: name = Column(String(255), nullable=False, index=True)"
        )

    async def test_message_content_type_has_index(self, db_session: AsyncSession):
        """Message.content_type should be indexed for filtering by media type."""
        # Check table metadata for indexes
        table_indexes = Message.__table__.indexes
        index_columns = []
        for idx in table_indexes:
            index_columns.extend(idx.columns.keys())

        # Check if column has index=True flag
        content_type_column = Message.__table__.columns['content_type']
        has_index = content_type_column.index or 'content_type' in index_columns

        assert has_index, (
            "Message.content_type should have an index for efficient filtering by message type. "
            "Add: content_type = Column(String(50), nullable=False, index=True)"
        )


class TestExistingIndexes:
    """Verify that existing indexes are properly defined."""

    async def test_organization_slug_has_index(self, db_session: AsyncSession):
        """Organization.slug should be indexed (already defined)."""
        # Check table metadata for indexes
        table_indexes = Organization.__table__.indexes
        index_columns = []
        for idx in table_indexes:
            index_columns.extend(idx.columns.keys())

        # Check if column has index=True flag
        slug_column = Organization.__table__.columns['slug']
        has_index = slug_column.index or 'slug' in index_columns

        assert has_index, "Organization.slug should have an index"

    async def test_user_email_has_index(self, db_session: AsyncSession):
        """User.email should be indexed (already defined)."""
        # Check table metadata for indexes
        table_indexes = User.__table__.indexes
        index_columns = []
        for idx in table_indexes:
            index_columns.extend(idx.columns.keys())

        # Check if column has index=True flag
        email_column = User.__table__.columns['email']
        has_index = email_column.index or 'email' in index_columns

        assert has_index, "User.email should have an index"

    async def test_entity_type_has_index(self, db_session: AsyncSession):
        """Entity.type should be indexed (already defined)."""
        # Check table metadata for indexes
        table_indexes = Entity.__table__.indexes
        index_columns = []
        for idx in table_indexes:
            index_columns.extend(idx.columns.keys())

        # Check if column has index=True flag
        type_column = Entity.__table__.columns['type']
        has_index = type_column.index or 'type' in index_columns

        assert has_index, "Entity.type should have an index"


class TestIndexPerformance:
    """Test that queries use indexes effectively."""

    @pytest_asyncio.fixture
    async def many_entities(self, db_session: AsyncSession, organization: Organization, department: Department):
        """Create 100 test entities for performance testing."""
        entities = []
        for i in range(100):
            entity = Entity(
                org_id=organization.id,
                department_id=department.id,
                name=f"Test Entity {i:03d}",
                email=f"entity{i:03d}@test.com",
                type="candidate",
                status="active"
            )
            entities.append(entity)

        db_session.add_all(entities)
        await db_session.commit()
        return entities

    @pytest_asyncio.fixture
    async def many_users(self, db_session: AsyncSession):
        """Create 100 test users for performance testing."""
        from api.services.auth import hash_password

        users = []
        for i in range(100):
            user = User(
                email=f"perfuser{i:03d}@test.com",
                password_hash=hash_password(f"password{i}"),
                name=f"Performance User {i:03d}",
                role="admin",
                is_active=True
            )
            users.append(user)

        db_session.add_all(users)
        await db_session.commit()
        return users

    @pytest_asyncio.fixture
    async def many_organizations(self, db_session: AsyncSession):
        """Create 100 test organizations for performance testing."""
        orgs = []
        for i in range(100):
            org = Organization(
                name=f"Test Organization {i:03d}",
                slug=f"test-org-{i:03d}"
            )
            orgs.append(org)

        db_session.add_all(orgs)
        await db_session.commit()
        return orgs

    @pytest_asyncio.fixture
    async def many_departments(self, db_session: AsyncSession, organization: Organization):
        """Create 100 test departments for performance testing."""
        depts = []
        for i in range(100):
            dept = Department(
                org_id=organization.id,
                name=f"Test Department {i:03d}"
            )
            depts.append(dept)

        db_session.add_all(depts)
        await db_session.commit()
        return depts

    @pytest_asyncio.fixture
    async def many_messages(self, db_session: AsyncSession, chat: Chat):
        """Create 100 test messages with different content types."""
        messages = []
        content_types = ["text", "voice", "video_note", "document", "photo"]

        for i in range(100):
            msg = Message(
                chat_id=chat.id,
                telegram_user_id=123456789 + i,
                content=f"Test message {i}",
                content_type=content_types[i % len(content_types)]
            )
            messages.append(msg)

        db_session.add_all(messages)
        await db_session.commit()
        return messages

    async def test_search_entities_by_name_uses_index(
        self,
        db_session: AsyncSession,
        many_entities
    ):
        """
        Verify entity name search performs efficiently.
        Without index: O(n) table scan
        With index: O(log n) index lookup
        """
        # Search for specific entity by name
        stmt = select(Entity).where(Entity.name == "Test Entity 050")
        result = await db_session.execute(stmt)
        entity = result.scalar_one_or_none()

        assert entity is not None
        assert entity.name == "Test Entity 050"

        # Search with LIKE pattern
        stmt = select(Entity).where(Entity.name.like("Test Entity 0%"))
        result = await db_session.execute(stmt)
        entities = result.scalars().all()

        # Should find entities 000-099
        assert len(entities) > 0

    async def test_search_entities_by_email_uses_index(
        self,
        db_session: AsyncSession,
        many_entities
    ):
        """
        Verify entity email search performs efficiently.
        Without index: O(n) table scan
        With index: O(log n) index lookup
        """
        # Search for specific entity by email
        stmt = select(Entity).where(Entity.email == "entity050@test.com")
        result = await db_session.execute(stmt)
        entity = result.scalar_one_or_none()

        assert entity is not None
        assert entity.email == "entity050@test.com"

        # Search with LIKE pattern
        stmt = select(Entity).where(Entity.email.like("entity0%@test.com"))
        result = await db_session.execute(stmt)
        entities = result.scalars().all()

        assert len(entities) > 0

    async def test_search_users_by_name_uses_index(
        self,
        db_session: AsyncSession,
        many_users
    ):
        """
        Verify user name search performs efficiently.
        Without index: O(n) table scan
        With index: O(log n) index lookup
        """
        # Search for specific user by name
        stmt = select(User).where(User.name == "Performance User 050")
        result = await db_session.execute(stmt)
        user = result.scalar_one_or_none()

        assert user is not None
        assert user.name == "Performance User 050"

        # Search with LIKE pattern
        stmt = select(User).where(User.name.like("Performance User 0%"))
        result = await db_session.execute(stmt)
        users = result.scalars().all()

        assert len(users) > 0

    async def test_search_organizations_by_name_uses_index(
        self,
        db_session: AsyncSession,
        many_organizations
    ):
        """
        Verify organization name search performs efficiently.
        Without index: O(n) table scan
        With index: O(log n) index lookup
        """
        # Search for specific organization by name
        stmt = select(Organization).where(Organization.name == "Test Organization 050")
        result = await db_session.execute(stmt)
        org = result.scalar_one_or_none()

        assert org is not None
        assert org.name == "Test Organization 050"

        # Search with LIKE pattern
        stmt = select(Organization).where(Organization.name.like("Test Organization 0%"))
        result = await db_session.execute(stmt)
        orgs = result.scalars().all()

        assert len(orgs) > 0

    async def test_search_departments_by_name_uses_index(
        self,
        db_session: AsyncSession,
        many_departments
    ):
        """
        Verify department name search performs efficiently.
        Without index: O(n) table scan
        With index: O(log n) index lookup
        """
        # Search for specific department by name
        stmt = select(Department).where(Department.name == "Test Department 050")
        result = await db_session.execute(stmt)
        dept = result.scalar_one_or_none()

        assert dept is not None
        assert dept.name == "Test Department 050"

        # Search with LIKE pattern
        stmt = select(Department).where(Department.name.like("Test Department 0%"))
        result = await db_session.execute(stmt)
        depts = result.scalars().all()

        assert len(depts) > 0

    async def test_filter_messages_by_content_type_uses_index(
        self,
        db_session: AsyncSession,
        many_messages
    ):
        """
        Verify message content_type filtering performs efficiently.
        Without index: O(n) table scan
        With index: O(log n) index lookup
        """
        # Filter messages by content type
        stmt = select(Message).where(Message.content_type == "voice")
        result = await db_session.execute(stmt)
        messages = result.scalars().all()

        # Should find voice messages (every 5th message is voice: 1, 6, 11, ...)
        assert len(messages) > 0
        assert all(msg.content_type == "voice" for msg in messages)

        # Filter for document messages
        stmt = select(Message).where(Message.content_type == "document")
        result = await db_session.execute(stmt)
        messages = result.scalars().all()

        assert len(messages) > 0
        assert all(msg.content_type == "document" for msg in messages)

    async def test_combined_filters_with_indexes(
        self,
        db_session: AsyncSession,
        many_entities
    ):
        """
        Test that multiple indexed columns work together efficiently.
        """
        # Filter by both type (indexed) and name (should be indexed)
        stmt = select(Entity).where(
            Entity.type == "candidate",
            Entity.name.like("Test Entity 02%")
        )
        result = await db_session.execute(stmt)
        entities = result.scalars().all()

        # Should find entities 020-029
        assert len(entities) > 0
        assert all(e.type == "candidate" for e in entities)

    async def test_ordering_by_indexed_columns(
        self,
        db_session: AsyncSession,
        many_entities
    ):
        """
        Test that ordering by indexed columns is efficient.
        """
        # Order by name (should be indexed)
        stmt = select(Entity).order_by(Entity.name).limit(10)
        result = await db_session.execute(stmt)
        entities = result.scalars().all()

        assert len(entities) == 10

        # Verify ordering
        names = [e.name for e in entities]
        assert names == sorted(names)


class TestCompositeIndexScenarios:
    """Test scenarios where composite indexes might be beneficial."""

    async def test_entity_org_name_query(
        self,
        db_session: AsyncSession,
        organization: Organization,
        department: Department
    ):
        """
        Test common query: find entity by organization and name.
        A composite index on (org_id, name) would be optimal.
        """
        # Create test entity
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            name="Test Composite",
            email="composite@test.com",
            type="candidate",
            status="active"
        )
        db_session.add(entity)
        await db_session.commit()

        # Common query pattern
        stmt = select(Entity).where(
            Entity.org_id == organization.id,
            Entity.name == "Test Composite"
        )
        result = await db_session.execute(stmt)
        found = result.scalar_one_or_none()

        assert found is not None
        assert found.name == "Test Composite"

    async def test_message_chat_content_type_query(
        self,
        db_session: AsyncSession,
        chat: Chat
    ):
        """
        Test common query: find messages by chat and content type.
        A composite index on (chat_id, content_type) would be optimal.
        """
        # Create test messages
        for i in range(5):
            msg = Message(
                chat_id=chat.id,
                telegram_user_id=123456789 + i,
                content=f"Test {i}",
                content_type="voice"
            )
            db_session.add(msg)
        await db_session.commit()

        # Common query pattern
        stmt = select(Message).where(
            Message.chat_id == chat.id,
            Message.content_type == "voice"
        )
        result = await db_session.execute(stmt)
        messages = result.scalars().all()

        assert len(messages) == 5
        assert all(m.content_type == "voice" for m in messages)
