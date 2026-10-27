"""
Performance tests to detect N+1 query problems in HR-Bot backend.

These tests verify that list endpoints use proper eager loading (selectinload/joinedload)
instead of executing O(n) queries for related data.

N+1 issues found in audit:
- GET /api/chats: 3 additional queries per chat (messages count, participants count, criteria check)
- GET /api/departments: 3 additional queries per dept (members count, entities count, children count)
- GET /api/sharing/my-shares: 2 additional queries per share (shared_by user, shared_with user)
"""
import pytest
from datetime import datetime
from sqlalchemy import event
from typing import List

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
# TEST: CHATS LIST N+1 PROBLEM
# ============================================================================

class TestChatsListNoNPlusOne:
    """Test that GET /api/chats does not have N+1 query problems."""

    @pytest.mark.asyncio
    async def test_chats_list_no_n_plus_one(
        self,
        client,
        db_session,
        async_engine,
        admin_user,
        admin_token,
        organization,
        org_owner,
        get_auth_headers
    ):
        """
        Test that listing chats does not execute O(n) queries.

        Current issue: For each chat, makes 3 additional queries:
        1. Count messages
        2. Count distinct participants
        3. Check for criteria

        This test creates 15 chats and verifies query count is reasonable.
        """
        # Create 15 chats with messages
        num_chats = 15
        for i in range(num_chats):
            chat = Chat(
                org_id=organization.id,
                owner_id=admin_user.id,
                telegram_chat_id=1000000 + i,
                title=f"Test Chat {i}",
                chat_type=ChatType.hr if i % 2 == 0 else ChatType.sales,
                is_active=True,
                created_at=datetime.utcnow()
            )
            db_session.add(chat)
            await db_session.flush()

            # Add some messages to each chat
            for j in range(3):
                message = Message(
                    chat_id=chat.id,
                    telegram_message_id=i * 1000 + j,
                    telegram_user_id=100 + j,
                    username=f"user{j}",
                    content=f"Message {j} in chat {i}",
                    content_type="text",
                    timestamp=datetime.utcnow()
                )
                db_session.add(message)

        await db_session.commit()

        # Count queries when fetching chats
        counter = QueryCounter(async_engine)
        with counter:
            response = await client.get(
                "/api/chats",
                headers=get_auth_headers(admin_token)
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == num_chats, f"Expected {num_chats} chats, got {len(data)}"

        # Analyze query count
        query_count = counter.count

        # Expected queries (with proper optimization):
        # 1. SELECT user (auth)
        # 2. SELECT org membership
        # 3. SELECT shared chat IDs
        # 4. SELECT department leads
        # 5. SELECT department members (if user is lead)
        # 6. SELECT chats with eager loading (owner, entity)
        # 7-9. Aggregated counts (messages, participants, criteria) - ideally in 3 queries with subqueries
        #
        # With N+1 problem: 1-6 base queries + (num_chats * 3) = ~50 queries for 15 chats
        # Properly optimized: ~9-12 queries total regardless of chat count

        print(f"\n{'='*70}")
        print(f"CHATS LIST PERFORMANCE TEST")
        print(f"{'='*70}")
        print(f"Number of chats: {num_chats}")
        print(f"Total queries executed: {query_count}")
        print(f"Queries per chat: {query_count / num_chats:.2f}")
        print(f"{'='*70}")

        # If you want to debug, uncomment:
        # counter.print_queries()

        # Assert reasonable query count
        # With N+1: would be ~50 queries (5 base + 15*3)
        # Properly optimized: should be ~12 queries
        # We'll allow up to 20 queries to account for variations
        assert query_count <= 20, (
            f"N+1 query problem detected! "
            f"Expected ~12 queries, but got {query_count}. "
            f"This indicates the endpoint is executing {query_count / num_chats:.1f} queries per chat. "
            f"Should use aggregated queries or subqueries instead of per-chat queries."
        )

        # Verify response contains expected data
        for chat_data in data:
            assert 'id' in chat_data
            assert 'title' in chat_data
            assert 'messages_count' in chat_data or 'message_count' in chat_data
            assert 'owner_name' in chat_data or 'owner' in chat_data


# ============================================================================
# TEST: DEPARTMENTS LIST N+1 PROBLEM
# ============================================================================

class TestDepartmentsListNoNPlusOne:
    """Test that GET /api/departments does not have N+1 query problems."""

    @pytest.mark.asyncio
    async def test_departments_list_no_n_plus_one(
        self,
        client,
        db_session,
        async_engine,
        admin_user,
        regular_user,
        admin_token,
        organization,
        org_owner,
        get_auth_headers
    ):
        """
        Test that listing departments does not execute O(n) queries.

        Current issue: For each department, makes 3 additional queries:
        1. Count members
        2. Count entities
        3. Count children

        This test creates 12 departments and verifies query count is reasonable.
        """
        # Create 12 departments
        num_depts = 12
        departments = []
        for i in range(num_depts):
            dept = Department(
                name=f"Department {i}",
                description=f"Test department {i}",
                org_id=organization.id,
                is_active=True,
                created_at=datetime.utcnow()
            )
            db_session.add(dept)
            await db_session.flush()
            departments.append(dept)

            # Add some members to each department
            for user in [admin_user, regular_user]:
                member = DepartmentMember(
                    department_id=dept.id,
                    user_id=user.id,
                    role=DeptRole.lead if user == admin_user else DeptRole.member,
                    created_at=datetime.utcnow()
                )
                db_session.add(member)

            # Add some entities to each department
            for j in range(2):
                entity = Entity(
                    org_id=organization.id,
                    department_id=dept.id,
                    created_by=admin_user.id,
                    name=f"Contact {i}-{j}",
                    email=f"contact{i}{j}@test.com",
                    type=EntityType.candidate,
                    status=EntityStatus.active,
                    created_at=datetime.utcnow()
                )
                db_session.add(entity)

        # Add some child departments
        for i in range(3):
            child = Department(
                name=f"Sub-Department {i}",
                org_id=organization.id,
                parent_id=departments[0].id,  # Make them children of first dept
                is_active=True,
                created_at=datetime.utcnow()
            )
            db_session.add(child)

        await db_session.commit()

        # Count queries when fetching departments
        counter = QueryCounter(async_engine)
        with counter:
            response = await client.get(
                "/api/departments?parent_id=-1",  # Get all departments
                headers=get_auth_headers(admin_token)
            )

        assert response.status_code == 200
        data = response.json()
        # Should return 12 top-level depts + 3 sub-depts = 15 total
        assert len(data) >= num_depts, f"Expected at least {num_depts} departments"

        # Analyze query count
        query_count = counter.count

        # Expected queries (with proper optimization):
        # 1. SELECT user (auth)
        # 2. SELECT org membership
        # 3. SELECT departments
        # 4. SELECT parent departments (for parent names)
        # 5-7. Aggregated counts (members, entities, children) - ideally 3 queries with GROUP BY
        #
        # With N+1 problem: 1-4 base queries + (num_depts * 3) = ~40 queries for 12 depts
        # Properly optimized: ~7-10 queries total regardless of dept count

        print(f"\n{'='*70}")
        print(f"DEPARTMENTS LIST PERFORMANCE TEST")
        print(f"{'='*70}")
        print(f"Number of departments: {len(data)}")
        print(f"Total queries executed: {query_count}")
        print(f"Queries per department: {query_count / len(data):.2f}")
        print(f"{'='*70}")

        # If you want to debug, uncomment:
        # counter.print_queries()

        # Assert reasonable query count
        # With N+1: would be ~40 queries (4 base + 12*3)
        # Properly optimized: should be ~10 queries
        # We'll allow up to 18 queries to account for variations
        assert query_count <= 18, (
            f"N+1 query problem detected! "
            f"Expected ~10 queries, but got {query_count}. "
            f"This indicates the endpoint is executing {query_count / len(data):.1f} queries per department. "
            f"Should use aggregated queries with GROUP BY instead of per-department queries."
        )

        # Verify response contains expected data
        for dept_data in data:
            assert 'id' in dept_data
            assert 'name' in dept_data
            assert 'members_count' in dept_data
            assert 'entities_count' in dept_data
            assert 'children_count' in dept_data


# ============================================================================
# TEST: SHARING LIST N+1 PROBLEM
# ============================================================================

class TestSharesListNoNPlusOne:
    """Test that GET /api/sharing/my-shares does not have N+1 query problems."""

    @pytest.mark.asyncio
    async def test_shares_list_no_n_plus_one(
        self,
        client,
        db_session,
        async_engine,
        admin_user,
        admin_token,
        organization,
        org_owner,
        get_auth_headers
    ):
        """
        Test that listing shares does not execute O(n) queries.

        Current issue: For each share, makes 2 additional queries:
        1. Get shared_by user
        2. Get shared_with user

        This test creates 10 users, 10 chats, and 10 shares.
        """
        # Create 10 additional users
        users = [admin_user]
        for i in range(10):
            user = User(
                email=f"shareuser{i}@test.com",
                password_hash="hashed",
                name=f"Share User {i}",
                role=UserRole.admin,
                is_active=True
            )
            db_session.add(user)
            await db_session.flush()
            users.append(user)

            # Add to organization
            member = OrgMember(
                org_id=organization.id,
                user_id=user.id,
                role=OrgRole.member,
                created_at=datetime.utcnow()
            )
            db_session.add(member)

        # Create 10 chats
        chats = []
        for i in range(10):
            chat = Chat(
                org_id=organization.id,
                owner_id=admin_user.id,
                telegram_chat_id=2000000 + i,
                title=f"Shared Chat {i}",
                chat_type=ChatType.hr,
                is_active=True,
                created_at=datetime.utcnow()
            )
            db_session.add(chat)
            await db_session.flush()
            chats.append(chat)

        # Create 10 shares from admin_user to other users
        num_shares = 10
        for i in range(num_shares):
            share = SharedAccess(
                resource_type=ResourceType.chat,
                resource_id=chats[i].id,
                shared_by_id=admin_user.id,
                shared_with_id=users[i + 1].id,  # Share with different users
                access_level=AccessLevel.view if i % 2 == 0 else AccessLevel.edit,
                note=f"Share note {i}",
                created_at=datetime.utcnow()
            )
            db_session.add(share)

        await db_session.commit()

        # Count queries when fetching shares
        counter = QueryCounter(async_engine)
        with counter:
            response = await client.get(
                "/api/sharing/my-shares",
                headers=get_auth_headers(admin_token)
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == num_shares, f"Expected {num_shares} shares, got {len(data)}"

        # Analyze query count
        query_count = counter.count

        # Expected queries (with proper optimization):
        # 1. SELECT user (auth)
        # 2. SELECT shares
        # 3. SELECT all shared_by users (with IN clause or joinedload)
        # 4. SELECT all shared_with users (with IN clause or joinedload)
        # 5. SELECT resource names for chats (with IN clause)
        #
        # With N+1 problem: 1-2 base queries + (num_shares * 2) = ~22 queries for 10 shares
        # Properly optimized: ~5 queries total regardless of share count

        print(f"\n{'='*70}")
        print(f"SHARES LIST PERFORMANCE TEST")
        print(f"{'='*70}")
        print(f"Number of shares: {num_shares}")
        print(f"Total queries executed: {query_count}")
        print(f"Queries per share: {query_count / num_shares:.2f}")
        print(f"{'='*70}")

        # If you want to debug, uncomment:
        # counter.print_queries()

        # Assert reasonable query count
        # With N+1: would be ~22 queries (2 base + 10*2)
        # Properly optimized: should be ~5 queries
        # We'll allow up to 12 queries to account for variations
        assert query_count <= 12, (
            f"N+1 query problem detected! "
            f"Expected ~5 queries, but got {query_count}. "
            f"This indicates the endpoint is executing {query_count / num_shares:.1f} queries per share. "
            f"Should use eager loading (selectinload/joinedload) or IN clauses instead of per-share queries."
        )

        # Verify response contains expected data
        for share_data in data:
            assert 'id' in share_data
            assert 'resource_type' in share_data
            assert 'shared_by_name' in share_data
            assert 'shared_with_name' in share_data
            assert 'access_level' in share_data


# ============================================================================
# ADDITIONAL TESTS FOR SHARED-WITH-ME ENDPOINT
# ============================================================================

class TestSharedWithMeNoNPlusOne:
    """Test that GET /api/sharing/shared-with-me does not have N+1 query problems."""

    @pytest.mark.asyncio
    async def test_shared_with_me_no_n_plus_one(
        self,
        client,
        db_session,
        async_engine,
        admin_user,
        regular_user,
        user_token,
        organization,
        org_owner,
        org_admin,
        get_auth_headers
    ):
        """
        Test that the shared-with-me endpoint also avoids N+1 queries.
        Similar to my-shares, this endpoint has the same N+1 issues.
        """
        # Create 10 chats owned by admin
        chats = []
        for i in range(10):
            chat = Chat(
                org_id=organization.id,
                owner_id=admin_user.id,
                telegram_chat_id=3000000 + i,
                title=f"Admin Chat {i}",
                chat_type=ChatType.sales,
                is_active=True,
                created_at=datetime.utcnow()
            )
            db_session.add(chat)
            await db_session.flush()
            chats.append(chat)

        # Share all chats with regular_user
        num_shares = 10
        for i in range(num_shares):
            share = SharedAccess(
                resource_type=ResourceType.chat,
                resource_id=chats[i].id,
                shared_by_id=admin_user.id,
                shared_with_id=regular_user.id,
                access_level=AccessLevel.view,
                created_at=datetime.utcnow()
            )
            db_session.add(share)

        await db_session.commit()

        # Count queries when fetching shared-with-me
        counter = QueryCounter(async_engine)
        with counter:
            response = await client.get(
                "/api/sharing/shared-with-me",
                headers=get_auth_headers(user_token)
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == num_shares, f"Expected {num_shares} shares, got {len(data)}"

        query_count = counter.count

        print(f"\n{'='*70}")
        print(f"SHARED-WITH-ME PERFORMANCE TEST")
        print(f"{'='*70}")
        print(f"Number of shares: {num_shares}")
        print(f"Total queries executed: {query_count}")
        print(f"Queries per share: {query_count / num_shares:.2f}")
        print(f"{'='*70}")

        # Same expectations as my-shares endpoint
        assert query_count <= 12, (
            f"N+1 query problem detected in shared-with-me endpoint! "
            f"Expected ~5 queries, but got {query_count}. "
            f"Should use eager loading or IN clauses instead of per-share queries."
        )
