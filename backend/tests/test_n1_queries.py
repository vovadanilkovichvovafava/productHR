"""
Tests for N+1 query fixes in chats, departments, and sharing endpoints.

These tests verify that the specific N+1 query issues identified in the audit
have been fixed using batch queries and eager loading.

Fixed endpoints:
1. GET /api/chats/deleted/list - batch load message counts
2. GET /api/departments/{id}/children - batch load member/entity/children counts
3. GET /api/departments/my/departments - batch load counts
4. GET /api/sharing/resource/{type}/{id} - eager load users
5. GET /api/sharing/users - batch load departments
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy import event

from api.models.database import (
    User, Organization, OrgMember, Department, DepartmentMember,
    Chat, Message, SharedAccess, Entity,
    UserRole, OrgRole, DeptRole, ChatType, ResourceType, AccessLevel,
    EntityType, EntityStatus
)


# ============================================================================
# QUERY COUNTING UTILITIES
# ============================================================================

class QueryCounter:
    """Context manager to count SQL queries using SQLAlchemy event listeners."""

    def __init__(self, engine):
        self.engine = engine
        self.count = 0
        self.queries = []

    def _before_cursor_execute(self, conn, cursor, statement, parameters, context, executemany):
        """Event handler to count queries."""
        self.count += 1
        # Store query for debugging
        self.queries.append({
            'statement': statement,
            'parameters': parameters
        })

    def __enter__(self):
        """Start counting queries."""
        self.count = 0
        self.queries = []
        # Listen on the sync engine (AsyncEngine.sync_engine)
        event.listen(
            self.engine.sync_engine,
            "before_cursor_execute",
            self._before_cursor_execute
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop counting queries."""
        event.remove(
            self.engine.sync_engine,
            "before_cursor_execute",
            self._before_cursor_execute
        )
        return False

    def print_queries(self):
        """Print all queries for debugging."""
        for i, query in enumerate(self.queries, 1):
            print(f"\nQuery {i}:")
            print(query['statement'])
            if query['parameters']:
                print(f"Parameters: {query['parameters']}")


# ============================================================================
# TEST: DELETED CHATS LIST N+1 FIX
# ============================================================================

class TestDeletedChatsNoNPlusOne:
    """Test that GET /api/chats/deleted/list has fixed N+1 queries."""

    @pytest.mark.asyncio
    async def test_deleted_chats_no_n_plus_one(
        self,
        client,
        db_session,
        async_engine,
        admin_user,
        admin_token,
        organization,
        org_owner,  # Required to give admin_user access to the organization
        get_auth_headers
    ):
        """
        Test that listing deleted chats does not execute O(n) queries.

        Fixed: For each deleted chat, was making 1 query to count messages.
        Now uses batch query to load all message counts at once.
        """
        # Create 10 deleted chats with messages
        num_chats = 10
        for i in range(num_chats):
            chat = Chat(
                org_id=organization.id,
                owner_id=admin_user.id,
                telegram_chat_id=5000000 + i,
                title=f"Deleted Chat {i}",
                chat_type=ChatType.hr,
                is_active=False,
                deleted_at=datetime.utcnow() - timedelta(days=i),
                created_at=datetime.utcnow()
            )
            db_session.add(chat)
            await db_session.flush()

            # Add messages to each chat
            for j in range(5):
                message = Message(
                    chat_id=chat.id,
                    telegram_message_id=i * 1000 + j,
                    telegram_user_id=100 + j,
                    content=f"Message {j} in deleted chat {i}",
                    content_type="text",
                    timestamp=datetime.utcnow()
                )
                db_session.add(message)

        await db_session.commit()

        # Count queries when fetching deleted chats
        counter = QueryCounter(async_engine)
        with counter:
            response = await client.get(
                "/api/chats/deleted/list",
                headers=get_auth_headers(admin_token)
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == num_chats, f"Expected {num_chats} deleted chats"

        query_count = counter.count

        print(f"\n{'='*70}")
        print(f"DELETED CHATS LIST PERFORMANCE TEST")
        print(f"{'='*70}")
        print(f"Number of deleted chats: {num_chats}")
        print(f"Total queries executed: {query_count}")
        print(f"Queries per chat: {query_count / num_chats:.2f}")
        print(f"{'='*70}")

        # Expected queries:
        # 1. SELECT user (auth)
        # 2. SELECT org membership
        # 3. SELECT deleted chats with owner eager loaded
        # 4. Batch SELECT message counts with GROUP BY
        #
        # With N+1: would be ~12 queries (2 base + 10*1)
        # Fixed: should be ~4-6 queries
        assert query_count <= 10, (
            f"N+1 query problem detected! "
            f"Expected ~6 queries, but got {query_count}. "
            f"Should use batch query for message counts."
        )

        # Verify response data
        for chat_data in data:
            assert 'id' in chat_data
            assert 'messages_count' in chat_data
            assert 'deleted_at' in chat_data


# ============================================================================
# TEST: DEPARTMENT CHILDREN LIST N+1 FIX
# ============================================================================

class TestDepartmentChildrenNoNPlusOne:
    """Test that GET /api/departments/{id}/children has fixed N+1 queries."""

    @pytest.mark.asyncio
    async def test_department_children_no_n_plus_one(
        self,
        client,
        db_session,
        async_engine,
        admin_user,
        admin_token,
        organization,
        org_owner,  # Required to give admin_user access to the organization
        get_auth_headers
    ):
        """
        Test that listing department children does not execute O(n) queries.

        Fixed: For each child department, was making 3 queries:
        - Count members
        - Count entities
        - Count children
        Now uses batch queries with GROUP BY.
        """
        # Create parent department
        parent_dept = Department(
            name="Parent Department",
            org_id=organization.id,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(parent_dept)
        await db_session.flush()

        # Create 8 child departments
        num_children = 8
        for i in range(num_children):
            child = Department(
                name=f"Child Department {i}",
                org_id=organization.id,
                parent_id=parent_dept.id,
                is_active=True,
                created_at=datetime.utcnow()
            )
            db_session.add(child)
            await db_session.flush()

            # Add members to each child
            member = DepartmentMember(
                department_id=child.id,
                user_id=admin_user.id,
                role=DeptRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(member)

            # Add entities to each child
            for j in range(2):
                entity = Entity(
                    org_id=organization.id,
                    department_id=child.id,
                    created_by=admin_user.id,
                    name=f"Entity {i}-{j}",
                    email=f"entity{i}{j}@test.com",
                    type=EntityType.candidate,
                    status=EntityStatus.active,
                    created_at=datetime.utcnow()
                )
                db_session.add(entity)

        await db_session.commit()

        # Count queries when fetching children
        counter = QueryCounter(async_engine)
        with counter:
            response = await client.get(
                f"/api/departments/{parent_dept.id}/children",
                headers=get_auth_headers(admin_token)
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == num_children, f"Expected {num_children} child departments"

        query_count = counter.count

        print(f"\n{'='*70}")
        print(f"DEPARTMENT CHILDREN PERFORMANCE TEST")
        print(f"{'='*70}")
        print(f"Number of children: {num_children}")
        print(f"Total queries executed: {query_count}")
        print(f"Queries per child: {query_count / num_children:.2f}")
        print(f"{'='*70}")

        # Expected queries:
        # 1. SELECT user (auth)
        # 2. SELECT org membership
        # 3. SELECT parent department
        # 4. SELECT child departments
        # 5. Batch SELECT member counts with GROUP BY
        # 6. Batch SELECT entity counts with GROUP BY
        # 7. Batch SELECT children counts with GROUP BY
        #
        # With N+1: would be ~26 queries (2 base + 8*3)
        # Fixed: should be ~7-9 queries
        assert query_count <= 12, (
            f"N+1 query problem detected! "
            f"Expected ~9 queries, but got {query_count}. "
            f"Should use batch queries with GROUP BY for counts."
        )

        # Verify response data
        for dept_data in data:
            assert 'id' in dept_data
            assert 'members_count' in dept_data
            assert 'entities_count' in dept_data
            assert 'children_count' in dept_data


# ============================================================================
# TEST: MY DEPARTMENTS LIST N+1 FIX
# ============================================================================

class TestMyDepartmentsNoNPlusOne:
    """Test that GET /api/departments/my/departments has fixed N+1 queries."""

    @pytest.mark.asyncio
    async def test_my_departments_no_n_plus_one(
        self,
        client,
        db_session,
        async_engine,
        admin_user,
        admin_token,
        organization,
        org_owner,  # Required to give admin_user access to the organization
        get_auth_headers
    ):
        """
        Test that listing user's departments does not execute O(n) queries.

        Fixed: For each department, was making 3 queries for counts.
        Now uses batch queries with GROUP BY.
        """
        # Create 6 departments and make admin_user a member
        num_depts = 6
        for i in range(num_depts):
            dept = Department(
                name=f"My Department {i}",
                org_id=organization.id,
                is_active=True,
                created_at=datetime.utcnow()
            )
            db_session.add(dept)
            await db_session.flush()

            # Add admin_user as member
            member = DepartmentMember(
                department_id=dept.id,
                user_id=admin_user.id,
                role=DeptRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(member)

            # Add entities
            entity = Entity(
                org_id=organization.id,
                department_id=dept.id,
                created_by=admin_user.id,
                name=f"Entity {i}",
                email=f"entity{i}@test.com",
                type=EntityType.candidate,
                status=EntityStatus.active,
                created_at=datetime.utcnow()
            )
            db_session.add(entity)

        await db_session.commit()

        # Count queries when fetching my departments
        counter = QueryCounter(async_engine)
        with counter:
            response = await client.get(
                "/api/departments/my/departments",
                headers=get_auth_headers(admin_token)
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == num_depts, f"Expected {num_depts} departments"

        query_count = counter.count

        print(f"\n{'='*70}")
        print(f"MY DEPARTMENTS PERFORMANCE TEST")
        print(f"{'='*70}")
        print(f"Number of departments: {num_depts}")
        print(f"Total queries executed: {query_count}")
        print(f"Queries per department: {query_count / num_depts:.2f}")
        print(f"{'='*70}")

        # Expected queries:
        # 1. SELECT user (auth)
        # 2. SELECT org membership
        # 3. SELECT user's departments
        # 4. SELECT parent departments (for names)
        # 5. Batch SELECT member counts
        # 6. Batch SELECT entity counts
        # 7. Batch SELECT children counts
        #
        # With N+1: would be ~20 queries (2 base + 6*3)
        # Fixed: should be ~7-9 queries
        assert query_count <= 12, (
            f"N+1 query problem detected! "
            f"Expected ~9 queries, but got {query_count}. "
            f"Should use batch queries with GROUP BY for counts."
        )


# ============================================================================
# TEST: RESOURCE SHARES LIST N+1 FIX
# ============================================================================

class TestResourceSharesNoNPlusOne:
    """Test that GET /api/sharing/resource/{type}/{id} has fixed N+1 queries."""

    @pytest.mark.asyncio
    async def test_resource_shares_no_n_plus_one(
        self,
        client,
        db_session,
        async_engine,
        admin_user,
        admin_token,
        organization,
        org_owner,  # без членства в орге доступ к чату — 403
        get_auth_headers
    ):
        """
        Test that listing shares for a resource does not execute O(n) queries.

        Fixed: For each share, was making 2 queries to get users.
        Now uses selectinload to eager load relationships.
        """
        # Create a chat
        chat = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=6000000,
            title="Shared Resource Chat",
            chat_type=ChatType.hr,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(chat)
        await db_session.flush()

        # Create 10 users and share the chat with them
        num_shares = 10
        for i in range(num_shares):
            user = User(
                email=f"sharetest{i}@test.com",
                password_hash="hashed",
                name=f"Share Test User {i}",
                role=UserRole.admin,
                is_active=True
            )
            db_session.add(user)
            await db_session.flush()

            # Add to organization
            member = OrgMember(
                org_id=organization.id,
                user_id=user.id,
                role=OrgRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(member)

            # Share chat with user
            share = SharedAccess(
                resource_type=ResourceType.chat,
                resource_id=chat.id,
                chat_id=chat.id,
                shared_by_id=admin_user.id,
                shared_with_id=user.id,
                access_level=AccessLevel.view,
                created_at=datetime.utcnow()
            )
            db_session.add(share)

        await db_session.commit()

        # Count queries when fetching resource shares
        counter = QueryCounter(async_engine)
        with counter:
            response = await client.get(
                f"/api/sharing/resource/chat/{chat.id}",
                headers=get_auth_headers(admin_token)
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == num_shares, f"Expected {num_shares} shares"

        query_count = counter.count

        print(f"\n{'='*70}")
        print(f"RESOURCE SHARES PERFORMANCE TEST")
        print(f"{'='*70}")
        print(f"Number of shares: {num_shares}")
        print(f"Total queries executed: {query_count}")
        print(f"Queries per share: {query_count / num_shares:.2f}")
        print(f"{'='*70}")

        # Expected queries:
        # 1. SELECT user (auth)
        # 2. SELECT chat (to verify access)
        # 3. SELECT shares with selectinload(shared_by, shared_with)
        # 4. Batch SELECT resource names
        #
        # With N+1: would be ~22 queries (2 base + 10*2)
        # Fixed: should be ~5-7 queries
        assert query_count <= 10, (
            f"N+1 query problem detected! "
            f"Expected ~7 queries, but got {query_count}. "
            f"Should use selectinload for user relationships."
        )

        # Verify response data
        for share_data in data:
            assert 'shared_by_name' in share_data
            assert 'shared_with_name' in share_data


# ============================================================================
# TEST: SHARABLE USERS LIST N+1 FIX
# ============================================================================

class TestSharableUsersNoNPlusOne:
    """Test that GET /api/sharing/users has fixed N+1 queries."""

    @pytest.mark.asyncio
    async def test_sharable_users_no_n_plus_one(
        self,
        client,
        db_session,
        async_engine,
        admin_user,
        admin_token,
        organization,
        org_owner,  # Required to give admin_user access to the organization
        get_auth_headers
    ):
        """
        Test that listing sharable users does not execute O(n) queries.

        Fixed: For each user, was making 1 query to get department.
        Now uses batch query to load all departments at once.
        """
        # Create departments
        dept1 = Department(
            name="Sales Department",
            org_id=organization.id,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(dept1)
        await db_session.flush()

        dept2 = Department(
            name="Marketing Department",
            org_id=organization.id,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db_session.add(dept2)
        await db_session.flush()

        # Create 12 users in different departments
        num_users = 12
        for i in range(num_users):
            user = User(
                email=f"sharableuser{i}@test.com",
                password_hash="hashed",
                name=f"Sharable User {i}",
                role=UserRole.admin,
                is_active=True
            )
            db_session.add(user)
            await db_session.flush()

            # Add to organization
            member = OrgMember(
                org_id=organization.id,
                user_id=user.id,
                role=OrgRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(member)

            # Add to department
            dept_member = DepartmentMember(
                department_id=dept1.id if i % 2 == 0 else dept2.id,
                user_id=user.id,
                role=DeptRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(dept_member)

        await db_session.commit()

        # Count queries when fetching sharable users
        counter = QueryCounter(async_engine)
        with counter:
            response = await client.get(
                "/api/sharing/users",
                headers=get_auth_headers(admin_token)
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == num_users, f"Expected {num_users} users"

        query_count = counter.count

        print(f"\n{'='*70}")
        print(f"SHARABLE USERS PERFORMANCE TEST")
        print(f"{'='*70}")
        print(f"Number of users: {num_users}")
        print(f"Total queries executed: {query_count}")
        print(f"Queries per user: {query_count / num_users:.2f}")
        print(f"{'='*70}")

        # Expected queries:
        # 1. SELECT user (auth)
        # 2. SELECT org membership
        # 3. SELECT users with org memberships
        # 4. Batch SELECT department memberships with departments
        #
        # With N+1: would be ~14 queries (2 base + 12*1)
        # Fixed: should be ~4-5 queries
        assert query_count <= 8, (
            f"N+1 query problem detected! "
            f"Expected ~5 queries, but got {query_count}. "
            f"Should use batch query for department memberships."
        )

        # Verify response data
        for user_data in data:
            assert 'id' in user_data
            assert 'name' in user_data
            # Most users should have department info
