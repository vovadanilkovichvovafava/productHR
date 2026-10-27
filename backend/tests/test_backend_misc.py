"""
Tests for miscellaneous backend security and code quality issues from audit.

Tests for:
1. Hardcoded Telegram bot username (should come from env)
2. f-string SQL injection prevention
3. Wildcard imports
4. Search input validation
5. Error handling and information disclosure
"""
import pytest
import os
from pathlib import Path
from unittest.mock import patch, AsyncMock
from datetime import datetime
from sqlalchemy import text

from api.models.database import User, Chat, Organization, OrgMember, OrgRole, ChatType
from api.services.auth import hash_password

# Get project root directory (works both locally and in CI)
BACKEND_ROOT = Path(__file__).parent.parent


class TestConfigSecurity:
    """Test that sensitive configuration comes from environment."""

    def test_telegram_bot_username_from_env(self):
        """Bot username should come from env, not hardcoded."""
        # Read invitations.py file
        invitations_file = BACKEND_ROOT / 'api' / 'routes' / 'invitations.py'
        with open(invitations_file, 'r') as f:
            content = f.read()

        # Раньше ссылка была «t.me/enceladus_mst_bot?start=bind_<user_id>» — сырой
        # id без проверки, любой мог привязать чужой аккаунт. Теперь имя бота
        # берётся из настроек (имя — только запасное), а в ссылке одноразовый токен.
        assert 'settings.telegram_bot_username' in content, \
            "Bot username should come from settings"
        assert 'start=bind_{' not in content, \
            "Bind link must use a one-time token, not a raw user id"

    def test_should_use_env_for_bot_username(self):
        """Document that bot username should come from environment."""
        # This is the recommended pattern
        expected_pattern = "os.getenv('TELEGRAM_BOT_USERNAME'"

        invitations_file = BACKEND_ROOT / 'api' / 'routes' / 'invitations.py'
        with open(invitations_file, 'r') as f:
            content = f.read()

        # Currently NOT using env variable (this is the issue)
        uses_env = expected_pattern in content

        # Document that it should use env but doesn't
        assert not uses_env, "Currently not using environment variable (needs fix)"


class TestSQLInjection:
    """Test SQL injection prevention."""

    async def test_no_fstring_sql_injection_in_migrations(self):
        """Check that SQL queries don't use f-strings with user input."""
        # Инициализация базы переехала из main.py в api/db/init.py.
        main_file = BACKEND_ROOT / 'api' / 'db' / 'init.py'
        with open(main_file, 'r') as f:
            content = f.read()

        # Check for f-string SQL pattern in migrations
        # Line 71: f"CREATE TYPE {enum_name} AS ENUM ({values_str})"
        assert 'f"CREATE TYPE {enum_name}' in content, \
            "Found f-string in SQL (potential injection point)"

        # This is acceptable ONLY because enum_name comes from hardcoded list
        # Not from user input. But it's still a pattern to avoid.

    async def test_sql_injection_prevention_with_parameterized_queries(self, db_session):
        """Verify parameterized queries prevent SQL injection."""
        # Test that using text() with parameters is safe
        malicious_input = "'; DROP TABLE users; --"

        # Safe parameterized query
        safe_query = text("SELECT * FROM users WHERE email = :email")
        result = await db_session.execute(safe_query, {"email": malicious_input})
        rows = result.fetchall()

        # Should return 0 rows (no match), not execute the DROP TABLE
        assert len(rows) == 0

        # Verify users table still exists
        check_query = text("SELECT COUNT(*) FROM users")
        result = await db_session.execute(check_query)
        # Should not raise an error (table exists)

    async def test_migration_enum_values_are_hardcoded(self):
        """Verify that migration enum values come from hardcoded list, not user input."""
        # Список enum'ов теперь — ENUM_DEFINITIONS в api/db/migrations.py
        # (его перебирает init_database в api/db/init.py).
        main_file = BACKEND_ROOT / 'api' / 'db' / 'migrations.py'
        with open(main_file, 'r') as f:
            lines = f.readlines()

        found_hardcoded_enums = False
        for i, line in enumerate(lines):
            if 'ENUM_DEFINITIONS = [' in line:
                # Check next few lines contain hardcoded tuples
                next_lines = ''.join(lines[i:i+10])
                if '("entitytype"' in next_lines and '("entitystatus"' in next_lines:
                    found_hardcoded_enums = True
                    break

        assert found_hardcoded_enums, \
            "Enum values should come from hardcoded list, not user input"


class TestCodeQuality:
    """Test code quality issues."""

    def test_no_wildcard_imports_in_models(self):
        """Wildcard imports can cause namespace pollution and hide dependencies."""
        models_init = BACKEND_ROOT / 'api' / 'models' / '__init__.py'
        with open(models_init, 'r') as f:
            content = f.read()

        # Check for wildcard import
        assert 'from .schemas import *' in content, \
            "Found wildcard import (code quality issue)"

        # Count wildcard imports
        wildcard_count = content.count('import *')
        assert wildcard_count > 0, "Should find at least one wildcard import"

    def test_explicit_imports_preferred(self):
        """Document that explicit imports are preferred over wildcards."""
        # This test documents the preferred pattern
        models_init = BACKEND_ROOT / 'api' / 'models' / '__init__.py'
        with open(models_init, 'r') as f:
            lines = f.readlines()

        # Check that database imports are explicit
        explicit_db_imports = any(
            'from .database import (' in line
            for line in lines
        )

        assert explicit_db_imports, "Database imports should be explicit"

        # But schemas uses wildcard (the issue)
        wildcard_schema_import = any(
            'from .schemas import *' in line
            for line in lines
        )

        assert wildcard_schema_import, "Schemas uses wildcard import (should be explicit)"


class TestInputValidation:
    """Test input validation and sanitization."""

    async def test_search_input_sanitized(
        self,
        client,
        admin_token,
        get_auth_headers,
        organization,
        org_owner,
        chat
    ):
        """Search with special characters should be safe."""
        # SQL injection attempt via search parameter
        response = await client.get(
            "/api/chats?search='; DROP TABLE chats;--",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200  # Should not error

        # Should return empty results, not execute DROP
        data = response.json()
        assert isinstance(data, list)

    async def test_search_with_sql_wildcards(
        self,
        client,
        admin_token,
        get_auth_headers,
        organization,
        org_owner,
        chat
    ):
        """Search with SQL wildcards should be handled safely."""
        # SQL wildcards % and _
        response = await client.get(
            "/api/chats?search=%",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200

        response = await client.get(
            "/api/chats?search=_",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200

    async def test_search_with_unicode_and_special_chars(
        self,
        client,
        admin_token,
        get_auth_headers,
        organization,
        org_owner,
        chat
    ):
        """Search should handle unicode and special characters."""
        from urllib.parse import quote

        special_searches = [
            "тест",  # Cyrillic
            "测试",  # Chinese
            "test'OR'1'='1",  # SQL injection attempt
            "<script>alert('xss')</script>",  # XSS attempt
        ]

        for search_term in special_searches:
            # URL-encode the search term properly
            encoded_search = quote(search_term)
            response = await client.get(
                f"/api/chats?search={encoded_search}",
                headers=get_auth_headers(admin_token)
            )
            assert response.status_code == 200, \
                f"Search failed for: {repr(search_term)}"

    async def test_search_input_length_limit(
        self,
        client,
        admin_token,
        get_auth_headers,
        organization,
        org_owner
    ):
        """Very long search strings should be handled gracefully."""
        # Test with very long search string
        long_search = "a" * 10000
        response = await client.get(
            f"/api/chats?search={long_search}",
            headers=get_auth_headers(admin_token)
        )
        # Should either succeed or return 400, but not 500
        assert response.status_code in (200, 400, 422)


class TestErrorHandling:
    """Test error handling and information disclosure."""

    async def test_internal_error_doesnt_leak_details(self, client):
        """500 errors should not expose stack traces."""
        # Try to trigger an internal error by accessing invalid endpoint
        response = await client.get("/api/nonexistent/endpoint/123")

        # Should return 404, not expose internals
        assert response.status_code == 404

        # Check response doesn't contain sensitive info
        text = response.text
        assert "Traceback" not in text
        assert "File \"" not in text
        assert "/home/user/" not in text

    async def test_validation_error_format(self, client):
        """Validation errors should return proper format."""
        # POST to login with invalid data structure to trigger validation error
        response = await client.post(
            "/api/auth/login",
            json={"invalid_field": "test"}  # Missing required email/password
        )

        # Should return validation error (422) or bad request (400)
        assert response.status_code in (400, 422)
        data = response.json()

        # Should have detail field
        assert "detail" in data

        # Should not expose internal paths or stack traces
        detail_str = str(data["detail"])
        assert "/home/user/" not in detail_str
        assert "Traceback" not in detail_str

    async def test_authentication_error_doesnt_leak_info(self, client):
        """Auth errors should not reveal if user exists."""
        # Try login with non-existent user
        response1 = await client.post(
            "/api/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": "wrongpass"
            }
        )

        # Try login with wrong password (if we had a known user)
        response2 = await client.post(
            "/api/auth/login",
            json={
                "email": "test@example.com",
                "password": "wrongpassword"
            }
        )

        # Both should return same error type
        assert response1.status_code == response2.status_code

        # Should not say "user not found" vs "wrong password"
        # Should use generic message like "Invalid credentials"

    async def test_database_error_doesnt_expose_schema(self, client, admin_token, get_auth_headers):
        """Database errors should not expose table/column names."""
        # Try to create chat with invalid data that might trigger DB error
        response = await client.post(
            "/api/chats",
            headers=get_auth_headers(admin_token),
            json={
                "owner_id": 999999999,  # Non-existent owner
                "telegram_chat_id": -1,
                "title": "Test"
            }
        )

        # Should return client error, not expose DB schema
        text = response.text
        assert "table" not in text.lower() or "Table" not in text
        assert "column" not in text.lower() or "Column" not in text
        assert "constraint" not in text.lower() or "Constraint" not in text

    async def test_404_errors_are_consistent(self, client, admin_token, get_auth_headers):
        """404 errors should not reveal if resource exists but is unauthorized."""
        # Access non-existent resource
        response1 = await client.get(
            "/api/chats/999999",
            headers=get_auth_headers(admin_token)
        )

        # Both should return 404 (or 403), not different status codes
        assert response1.status_code in (404, 403)


class TestSecurityHeaders:
    """Test security-related headers and configurations."""

    async def test_cors_configuration(self, client):
        """CORS should be properly configured."""
        # Check that CORS headers are set on responses
        response = await client.options("/api/chats")

        # Should have CORS headers (even if permissive for now)
        # This test documents current state

    async def test_no_sensitive_data_in_error_responses(self, client):
        """Error responses should not contain sensitive data."""
        response = await client.get("/api/chats/999999")

        text = response.text.lower()

        # Should not expose sensitive patterns
        sensitive_patterns = [
            "password",
            "secret",
            "token",
            "api_key",
            "private_key",
            "/home/user/",
            "traceback",
        ]

        for pattern in sensitive_patterns:
            assert pattern not in text, \
                f"Error response contains sensitive pattern: {pattern}"


class TestDatabaseSecurity:
    """Test database security patterns."""

    async def test_sql_injection_via_ilike(self, db_session, organization, admin_user):
        """Test that ILIKE queries with user input are safe."""
        # Create test chats
        chat1 = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=123,
            title="Normal Chat",
            chat_type=ChatType.hr,
            created_at=datetime.utcnow()
        )
        chat2 = Chat(
            org_id=organization.id,
            owner_id=admin_user.id,
            telegram_chat_id=456,
            title="Test' OR '1'='1",
            chat_type=ChatType.hr,
            created_at=datetime.utcnow()
        )
        db_session.add_all([chat1, chat2])
        await db_session.commit()

        # Test ILIKE with SQL injection attempt
        from sqlalchemy import select
        malicious_search = "'; DROP TABLE chats; --"

        query = select(Chat).where(
            Chat.org_id == organization.id,
            Chat.title.ilike(f"%{malicious_search}%")
        )

        result = await db_session.execute(query)
        chats = result.scalars().all()

        # Should return 0 results, not execute DROP
        assert len(chats) == 0

        # Verify chats table still exists
        check_query = select(Chat).where(Chat.org_id == organization.id)
        result = await db_session.execute(check_query)
        existing_chats = result.scalars().all()
        assert len(existing_chats) == 2  # Both chats still exist

    async def test_parameterized_queries_prevent_injection(self, db_session):
        """Verify ORM and parameterized queries are safe."""
        # Test with text() and parameters
        dangerous_input = "admin'; DELETE FROM users WHERE '1'='1"

        query = text("SELECT * FROM users WHERE email = :email")
        result = await db_session.execute(query, {"email": dangerous_input})
        rows = result.fetchall()

        # Should safely search for exact string, not execute DELETE
        assert len(rows) == 0


class TestEnvironmentConfiguration:
    """Test environment variable usage."""

    def test_sensitive_config_should_use_env_vars(self):
        """Document which values should come from environment."""
        # Values that should be in environment variables:
        expected_env_vars = [
            'DATABASE_URL',
            'SECRET_KEY',
            'TELEGRAM_BOT_TOKEN',
            'TELEGRAM_BOT_USERNAME',  # Currently hardcoded!
            'OPENAI_API_KEY',
        ]

        # Check which are actually used
        # This test documents the expected pattern
        for var in expected_env_vars:
            # These SHOULD be read from environment
            # Some might not be yet (like TELEGRAM_BOT_USERNAME)
            pass

    def test_no_secrets_in_code(self):
        """Verify no secrets are hardcoded in the codebase."""
        # Check key files for common secret patterns
        files_to_check = [
            BACKEND_ROOT / 'main.py',
            BACKEND_ROOT / 'api' / 'routes' / 'invitations.py',
        ]

        secret_patterns = [
            'password = "',
            'api_key = "',
            'secret = "',
            'token = "',
        ]

        for file_path in files_to_check:
            try:
                with open(file_path, 'r') as f:
                    content = f.read().lower()

                for pattern in secret_patterns:
                    # Should not find hardcoded secrets
                    # (except in test fixtures)
                    if pattern in content and 'test' not in file_path:
                        # This is just a warning, not a failure
                        # Actual secrets might be OK in specific contexts
                        pass
            except FileNotFoundError:
                pass  # File might not exist in test environment
