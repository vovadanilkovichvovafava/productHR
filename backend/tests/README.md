# HR-Bot Backend Tests

## Quick Start

```bash
# 1. Create virtual environment
cd backend
python -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt
pip install pytest pytest-asyncio aiosqlite httpx

# 3. Set required environment variables
export SECRET_KEY="your-test-secret-key"
export SUPERADMIN_PASSWORD="your-test-password"

# 4. Run tests
python -m pytest tests/ -v
```

## Running Specific Tests

```bash
# Run only schema validation tests (fast, no DB needed)
python -m pytest tests/test_schemas.py -v

# Run specific test file
python -m pytest tests/test_sharing.py -v

# Run specific test class
python -m pytest tests/test_sharing.py::TestCreateShare -v

# Run single test
python -m pytest tests/test_sharing.py::TestCreateShare::test_owner_can_share_entity -v
```

## Test Structure

| File | Description | Count |
|------|-------------|-------|
| `test_schemas.py` | Pydantic schema validation | 42 |
| `test_auth.py` | Authentication & JWT | 25 |
| `test_sharing.py` | Resource sharing | 25 |
| `test_entities_access.py` | Entity access control | 22 |
| `test_chats_access.py` | Chat access control | 25 |
| `test_calls_access.py` | Call recording access | 20 |
| `test_departments.py` | Department management | 20 |
| `test_organizations.py` | Organization management | 18 |

## Environment Variables

Required for tests:
- `SECRET_KEY` - JWT signing key
- `SUPERADMIN_PASSWORD` - Superadmin password

## Test Database

Tests use SQLite in-memory database (`:memory:`) for isolation.
Each test function gets a fresh database.

## Fixtures (conftest.py)

### Users
- `superadmin_user` - User with SUPERADMIN role
- `admin_user` - User with ADMIN role
- `regular_user` - Regular user
- `second_user` - Another user for permission tests

### Tokens
- `superadmin_token`, `admin_token`, `user_token`, `second_user_token`

### Organizations
- `organization` - Test organization
- `second_organization` - For cross-org tests

### Resources
- `entity`, `chat`, `call_recording` - Test resources
- `entity_view_share`, `entity_edit_share` - Share objects

## Common Issues

### 1. Missing SECRET_KEY
```
pydantic_core._pydantic_core.ValidationError: SECRET_KEY Field required
```
Fix: Set `export SECRET_KEY="test-key"`

### 2. Import errors
```
ImportError: cannot import name 'hash_password'
```
Fix: The function is `hash_password`, not `get_password_hash`

### 3. Fixture field errors
```
TypeError: 'members_count' is an invalid keyword argument
```
Fix: Remove computed fields from fixtures. Department doesn't have `members_count` column.

## Writing New Tests

1. Use `@pytest.mark.asyncio` for async tests
2. Use fixtures from `conftest.py` for users/tokens/resources
3. Use `get_auth_headers(token)` for authenticated requests
4. Create JWT with `{"sub": str(user.id)}` format

Example:
```python
@pytest.mark.asyncio
async def test_example(self, client, admin_user, admin_token, get_auth_headers):
    response = await client.get(
        "/api/some-endpoint",
        headers=get_auth_headers(admin_token)
    )
    assert response.status_code == 200
```
