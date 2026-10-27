# Performance Tests - N+1 Query Detection

This document describes the performance tests created to detect N+1 query problems in the HR-Bot backend.

## Overview

N+1 query problems occur when an endpoint executes O(n) database queries instead of a constant number of queries. These tests use SQLAlchemy event listeners to count SQL queries and verify that list endpoints use proper eager loading.

## Test File

**Location:** `/home/user/HR-bot-/backend/tests/test_performance.py`

## Tests Implemented

### 1. `TestChatsListNoNPlusOne::test_chats_list_no_n_plus_one`

**Endpoint:** `GET /api/chats`

**N+1 Issue Detected:**
- Creates 15 chats with messages
- Executes **50 queries** (3.33 queries per chat)
- Expected: ~12 queries with proper optimization
- **Root Cause:** For each chat, makes 3 separate queries:
  1. Count messages: `SELECT COUNT(messages.id) WHERE chat_id = ?`
  2. Count participants: `SELECT COUNT(DISTINCT telegram_user_id) WHERE chat_id = ?`
  3. Check criteria: `SELECT criteria.id WHERE chat_id = ?`

**Recommendation:** Use subqueries or aggregated queries with GROUP BY to fetch all counts in O(1) queries.

### 2. `TestDepartmentsListNoNPlusOne::test_departments_list_no_n_plus_one`

**Endpoint:** `GET /api/departments`

**N+1 Issue Detected:**
- Creates 15 departments with members, entities, and children
- Executes **49 queries** (3.27 queries per department)
- Expected: ~10 queries with proper optimization
- **Root Cause:** For each department, makes 3 separate queries:
  1. Count members: `SELECT department_members WHERE department_id = ?`
  2. Count entities: `SELECT entities WHERE department_id = ?`
  3. Count children: `SELECT departments WHERE parent_id = ?`

**Recommendation:** Use aggregated queries with GROUP BY to fetch all counts in 3 total queries instead of 3*n queries.

### 3. `TestSharesListNoNPlusOne::test_shares_list_no_n_plus_one`

**Endpoint:** `GET /api/sharing/my-shares`

**N+1 Issue Detected:**
- Creates 10 shares
- Executes **32 queries** (3.2 queries per share)
- Expected: ~5 queries with proper optimization
- **Root Cause:** For each share, makes 2+ separate queries:
  1. Get shared_by user: `SELECT users WHERE id = ?`
  2. Get shared_with user: `SELECT users WHERE id = ?`
  3. Get resource name (via `get_resource_name` function)

**Recommendation:** Use eager loading with `selectinload(SharedAccess.shared_by).selectinload(SharedAccess.shared_with)` or fetch all users with a single IN clause.

### 4. `TestSharedWithMeNoNPlusOne::test_shared_with_me_no_n_plus_one`

**Endpoint:** `GET /api/sharing/shared-with-me`

**N+1 Issue Detected:**
- Creates 10 shares
- Executes **32 queries** (3.2 queries per share)
- Expected: ~5 queries with proper optimization
- **Root Cause:** Same as `my-shares` endpoint

**Recommendation:** Same as `my-shares` - use eager loading or IN clauses.

## How to Run Tests

```bash
cd /home/user/HR-bot-/backend

# Run all performance tests
SECRET_KEY=test_secret SUPERADMIN_PASSWORD=test_pass DATABASE_URL=sqlite+aiosqlite:///test.db \
python -m pytest tests/test_performance.py -v -s

# Run specific test
SECRET_KEY=test_secret SUPERADMIN_PASSWORD=test_pass DATABASE_URL=sqlite+aiosqlite:///test.db \
python -m pytest tests/test_performance.py::TestChatsListNoNPlusOne -v -s
```

## Test Results

All 4 tests currently **FAIL** (as expected) because the N+1 problems exist:

```
FAILED tests/test_performance.py::TestChatsListNoNPlusOne::test_chats_list_no_n_plus_one
  AssertionError: N+1 query problem detected! Expected ~12 queries, but got 50.

FAILED tests/test_performance.py::TestDepartmentsListNoNPlusOne::test_departments_list_no_n_plus_one
  AssertionError: N+1 query problem detected! Expected ~10 queries, but got 49.

FAILED tests/test_performance.py::TestSharesListNoNPlusOne::test_shares_list_no_n_plus_one
  AssertionError: N+1 query problem detected! Expected ~5 queries, but got 32.

FAILED tests/test_performance.py::TestSharedWithMeNoNPlusOne::test_shared_with_me_no_n_plus_one
  AssertionError: N+1 query problem detected! Expected ~5 queries, but got 32.
```

## How the Tests Work

### Query Counter Implementation

The tests use a custom `QueryCounter` class that leverages SQLAlchemy's event system:

```python
class QueryCounter:
    def __init__(self, engine):
        self.engine = engine
        self.count = 0
        self.queries = []

    def _before_cursor_execute(self, conn, cursor, statement, parameters, context, executemany):
        self.count += 1
        self.queries.append({'statement': statement, 'parameters': parameters})

    def __enter__(self):
        event.listen(self.engine.sync_engine, "before_cursor_execute", self._before_cursor_execute)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        event.remove(self.engine.sync_engine, "before_cursor_execute", self._before_cursor_execute)
```

### Test Pattern

Each test follows this pattern:

1. **Setup:** Create multiple records (10-15+) to make N+1 problems obvious
2. **Execute:** Wrap the API call in a `QueryCounter` context manager
3. **Assert:** Verify query count is reasonable (not O(n))
4. **Report:** Print performance metrics for debugging

## Expected Behavior After Fixes

Once the endpoints are optimized:

- **Chats endpoint:** Should execute ~12 queries regardless of chat count
- **Departments endpoint:** Should execute ~10 queries regardless of department count
- **Sharing endpoints:** Should execute ~5 queries regardless of share count

## Performance Impact

Current performance with N+1 problems:
- 100 chats = ~305 queries (3.05 * 100 + 5 base queries)
- 100 departments = ~310 queries
- 100 shares = ~320 queries

After optimization:
- 100 chats = ~12 queries (constant)
- 100 departments = ~10 queries (constant)
- 100 shares = ~5 queries (constant)

This represents a **25-30x performance improvement** for large result sets.

## Debugging

To see all executed queries, uncomment the `counter.print_queries()` line in any test. This will print all SQL statements and their parameters.

## Next Steps

1. Fix the N+1 problems in the endpoints (see recommendations above)
2. Run tests again to verify fixes
3. Monitor production query performance
4. Consider adding similar tests for other list endpoints
