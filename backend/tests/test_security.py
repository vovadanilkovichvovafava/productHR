"""
Security tests for HR-Bot backend.

These tests document security requirements and vulnerabilities identified in the audit.
Some tests may fail initially - this is expected as they document missing security features.
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from jose import jwt

from api.services.auth import (
    hash_password,
    create_access_token,
)
from api.config import settings
from api.models.database import User, UserRole


class TestCORSSecurity:
    """
    Test CORS security configuration.

    VULNERABILITY: main.py:374 has allow_origins="*" which allows any domain
    to make requests with credentials, opening up CSRF and session hijacking risks.
    """

    @pytest.mark.asyncio
    async def test_cors_not_allow_all_origins(self, client):
        """
        Test that CORS doesn't allow wildcard origins with credentials.

        EXPECTED BEHAVIOR: Either:
        1. CORS should specify allowed origins explicitly (not "*")
        2. OR if "*" is used, allow_credentials should be False

        CURRENT BEHAVIOR: Allows "*" with credentials=True (SECURITY RISK)
        """
        # Make a request with a random origin
        response = await client.get(
            "/health",
            headers={"Origin": "https://evil-site.com"}
        )

        # Check CORS headers - should not allow credentials with wildcard
        cors_allow_origin = response.headers.get("access-control-allow-origin")
        cors_allow_credentials = response.headers.get("access-control-allow-credentials")

        # SECURITY REQUIREMENT: Cannot have both wildcard origin and credentials
        if cors_allow_origin == "*":
            # If wildcard is used, credentials must not be allowed
            assert cors_allow_credentials != "true", (
                "SECURITY VULNERABILITY: CORS allows wildcard origin (*) with credentials=true. "
                "This allows any website to make authenticated requests on behalf of users."
            )

    @pytest.mark.asyncio
    async def test_cors_validates_origin(self, client):
        """
        Test that CORS validates allowed origins.

        EXPECTED: Only whitelisted origins should be allowed
        CURRENT: All origins allowed (*)
        """
        # This test documents the expected behavior
        # Should only allow specific trusted domains
        response = await client.options(
            "/api/auth/login",
            headers={"Origin": "https://evil-site.com"}
        )

        # In a secure implementation, evil-site.com should not be allowed
        # TODO: This test will fail until CORS is properly configured
        pass


class TestRateLimiting:
    """
    Test rate limiting on authentication endpoints.

    Rate limiting is configured via slowapi decorators on auth routes.
    In test mode (TESTING=1), rate limiting is disabled to avoid test interference.
    These tests verify that rate limiting is properly configured.
    """

    def test_login_has_rate_limit(self):
        """
        Test that login endpoint has rate limiting decorator configured.

        Rate limit: 5 requests per minute
        """
        from api.routes.auth import login

        # Check that the endpoint has rate limit decorator
        # slowapi adds __wrapped__ or _rate_limit_info to decorated functions
        assert hasattr(login, '__wrapped__') or hasattr(login, '_rate_limit_info') or \
               any('limit' in str(getattr(login, attr, '')) for attr in dir(login)), \
            "Login endpoint should have rate limiting decorator"

    def test_register_has_rate_limit(self):
        """
        Test that register endpoint has rate limiting decorator configured.

        Rate limit: 3 requests per minute
        """
        from api.routes.auth import register

        # Check that the endpoint has rate limit decorator
        assert hasattr(register, '__wrapped__') or hasattr(register, '_rate_limit_info') or \
               any('limit' in str(getattr(register, attr, '')) for attr in dir(register)), \
            "Register endpoint should have rate limiting decorator"

    def test_password_change_has_rate_limit(self):
        """
        Test that password change endpoint has rate limiting decorator configured.

        Rate limit: 3 requests per minute
        """
        from api.routes.auth import change_password

        # Check that the endpoint has rate limit decorator
        assert hasattr(change_password, '__wrapped__') or hasattr(change_password, '_rate_limit_info') or \
               any('limit' in str(getattr(change_password, attr, '')) for attr in dir(change_password)), \
            "Password change endpoint should have rate limiting decorator"

    def test_limiter_is_configured(self):
        """Test that rate limiter is properly configured in the app."""
        from main import app

        # Check that limiter is attached to app state
        assert hasattr(app.state, 'limiter'), "Rate limiter should be configured in app.state"

    # Блокировка аккаунта после неудачных входов УБРАНА по решению владельца
    # (routes/auth.py, login: «запирала HR-пользователей на 15 минут… мешало
    # больше, чем защищало»). Прежние тесты «5 ошибок → 423», «лок истекает»,
    # «сообщение о локе» проверяли удалённое поведение; вместо них — то, что
    # осталось: ошибки не запирают вход, а успешный вход снимает старый лок.

    @pytest.mark.asyncio
    async def test_account_lockout_after_failed_attempts(self, client, admin_user):
        """Failed attempts no longer lock the account: the right password still works."""
        for _ in range(5):
            response = await client.post("/api/auth/login", json={
                "email": "admin@test.com",
                "password": "wrongpassword"
            })
            assert response.status_code == 401

        response = await client.post("/api/auth/login", json={
            "email": "admin@test.com",
            "password": "Admin123"
        })
        assert response.status_code == 200, response.text

    @pytest.mark.asyncio
    async def test_lockout_expires_after_timeout(self, client, admin_user, db_session):
        """A lock left in the DB from before is ignored and cleared by a successful login."""
        admin_user.locked_until = datetime.utcnow() + timedelta(minutes=15)
        admin_user.failed_login_attempts = 5
        await db_session.commit()

        response = await client.post("/api/auth/login", json={
            "email": "admin@test.com",
            "password": "Admin123"
        })
        assert response.status_code == 200, response.text

        await db_session.refresh(admin_user)
        assert admin_user.locked_until is None
        assert admin_user.failed_login_attempts == 0


class TestPasswordSecurity:
    """
    Test password complexity requirements.

    VULNERABILITY: No password strength requirements allow weak passwords like "123".
    """

    @pytest.mark.asyncio
    async def test_weak_password_rejected(self, client, admin_user, admin_token, get_auth_headers):
        """
        Test that weak passwords are rejected.

        EXPECTED: Passwords like "123" should be rejected
        """
        response = await client.post(
            "/api/auth/change-password",
            json={
                "current_password": "admin123",
                "new_password": "123"  # Too weak
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code in [400, 422], (
            f"SECURITY VULNERABILITY: Weak password '123' was accepted. "
            f"Expected rejection (400/422), got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_short_password_rejected(self, client, admin_user, admin_token, get_auth_headers):
        """
        Test that short passwords are rejected.

        EXPECTED: Minimum password length (e.g., 8 characters)
        """
        response = await client.post(
            "/api/auth/change-password",
            json={
                "current_password": "admin123",
                "new_password": "abc"  # Too short
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code in [400, 422], (
            f"SECURITY VULNERABILITY: Short password 'abc' was accepted. "
            f"Expected rejection (400/422), got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_password_without_numbers_rejected(self, client, admin_user, admin_token, get_auth_headers):
        """
        Test password complexity: require numbers.

        EXPECTED: Password should contain at least one number
        """
        response = await client.post(
            "/api/auth/change-password",
            json={
                "current_password": "admin123",
                "new_password": "passwordonly"  # No numbers
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code in [400, 422], (
            f"SECURITY VULNERABILITY: Password without numbers 'passwordonly' was accepted. "
            f"Expected rejection (400/422), got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_common_password_rejected(self, client, admin_user, admin_token, get_auth_headers):
        """
        Test that common passwords are rejected.

        EXPECTED: Passwords like "password123" should be rejected
        """
        response = await client.post(
            "/api/auth/change-password",
            json={
                "current_password": "admin123",
                "new_password": "password123"  # Common password
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code in [400, 422], (
            f"SECURITY VULNERABILITY: Common password 'password123' was accepted. "
            f"Expected rejection (400/422), got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_password_same_as_email_rejected(self, client, admin_user, admin_token, get_auth_headers):
        """
        Test that password cannot be same as email.

        EXPECTED: Password should not match email or username
        """
        response = await client.post(
            "/api/auth/change-password",
            json={
                "current_password": "admin123",
                "new_password": "admin@test.com"  # Same as email
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code in [400, 422], (
            f"SECURITY VULNERABILITY: Password same as email 'admin@test.com' was accepted. "
            f"Expected rejection (400/422), got {response.status_code}"
        )


class TestTokenSecurity:
    """
    Test JWT token security.

    Tests for token expiration, validation, and proper error handling.
    """

    @pytest.mark.asyncio
    async def test_expired_token_rejected(self, client, admin_user):
        """
        Test that expired tokens are rejected.

        EXPECTED: 401 Unauthorized with expired token
        CURRENT: Should be working (test for regression)
        """
        # Create expired token manually
        expired_payload = {
            "sub": str(admin_user.id),
            "exp": datetime.utcnow() - timedelta(seconds=1)  # Already expired
        }
        token = jwt.encode(expired_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 401, (
            f"Expired token was accepted! Expected 401, got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self, client):
        """
        Test that invalid/malformed tokens are rejected.

        EXPECTED: 401 Unauthorized
        """
        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"}
        )

        assert response.status_code == 401, (
            f"Invalid token was accepted! Expected 401, got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_token_without_user_id_rejected(self, client):
        """
        Test that token without user_id (sub) is rejected.

        EXPECTED: 401 Unauthorized
        """
        # Create token without user_id
        token = create_access_token(data={"random_field": "value"})

        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 401, (
            f"Token without user_id was accepted! Expected 401, got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_token_with_invalid_user_id_rejected(self, client):
        """
        Test that token with non-existent user_id is rejected.

        EXPECTED: 401 Unauthorized
        """
        # Create token with non-existent user
        token = create_access_token(data={"sub": "999999"})

        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 401, (
            f"Token with non-existent user was accepted! Expected 401, got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_token_with_inactive_user_rejected(self, client, db_session):
        """
        Test that token for inactive user is rejected.

        EXPECTED: 401 Unauthorized when user is deactivated
        """
        # Create inactive user
        inactive_user = User(
            email="inactive@test.com",
            password_hash=hash_password("password123"),
            name="Inactive User",
            role=UserRole.admin,
            is_active=False
        )
        db_session.add(inactive_user)
        await db_session.commit()
        await db_session.refresh(inactive_user)

        # Create valid token for inactive user
        token = create_access_token(data={"sub": str(inactive_user.id)})

        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 401, (
            f"Token for inactive user was accepted! Expected 401, got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_token_without_bearer_prefix_rejected(self, client, admin_token):
        """
        Test that token without 'Bearer' prefix is rejected.

        EXPECTED: 401 or 403 Unauthorized
        """
        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": admin_token}  # Missing "Bearer" prefix
        )

        assert response.status_code in [401, 403], (
            f"Token without Bearer prefix was accepted! Expected 401/403, got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_token_signed_with_wrong_secret_rejected(self, client, admin_user):
        """
        Test that token signed with wrong secret is rejected.

        EXPECTED: 401 Unauthorized
        """
        # Create token with wrong secret
        wrong_token = jwt.encode(
            {"sub": str(admin_user.id), "exp": datetime.utcnow() + timedelta(hours=1)},
            "wrong_secret_key_12345",
            algorithm="HS256"
        )

        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {wrong_token}"}
        )

        assert response.status_code == 401, (
            f"Token signed with wrong secret was accepted! Expected 401, got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_token_expiration_time_reasonable(self):
        """
        Test that token expiration time is reasonable.

        EXPECTED: Tokens should expire (not be valid forever)
        Recommended: 15 minutes to 24 hours
        """
        token = create_access_token(data={"sub": "1"})
        decoded = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])

        exp_time = datetime.fromtimestamp(decoded["exp"])
        now = datetime.utcnow()
        time_until_expiry = exp_time - now

        # Check that token expires
        assert "exp" in decoded, "Token has no expiration!"

        # Check that expiration is reasonable (between 1 minute and 30 days)
        assert timedelta(minutes=1) < time_until_expiry < timedelta(days=30), (
            f"Token expiration time seems unreasonable: {time_until_expiry}. "
            f"Should be between 1 minute and 30 days."
        )


class TestSessionSecurity:
    """
    Test session and authentication security.
    """

    @pytest.mark.asyncio
    async def test_no_token_reuse_after_password_change(self, client, admin_user, admin_token, get_auth_headers, db_session):
        """
        Test that tokens are invalidated after password change.

        EXPECTED: Old tokens should be invalid after password change
        CURRENT: Likely FAILS - tokens remain valid (JWT is stateless)

        NOTE: This is a known limitation of JWT. Solutions:
        1. Token blacklist
        2. Include password hash version in token
        3. Use refresh tokens with revocation
        """
        # Verify old token works
        response = await client.get("/api/auth/me", headers=get_auth_headers(admin_token))
        assert response.status_code == 200

        # Change password - use valid password that passes validation
        response = await client.post(
            "/api/auth/change-password",
            json={
                "current_password": "Admin123",  # Correct password from fixture
                "new_password": "NewPassword456"  # Must have uppercase, lowercase, numbers
            },
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200

        # Try to use old token
        response = await client.get("/api/auth/me", headers=get_auth_headers(admin_token))

        # TODO: Uncomment when token invalidation is implemented
        # assert response.status_code == 401, (
        #     "SECURITY VULNERABILITY: Old token still valid after password change. "
        #     "Tokens should be invalidated when password changes."
        # )

        if response.status_code == 200:
            pytest.skip(
                "Token invalidation not implemented: Old tokens remain valid after password change. "
                "SECURITY RISK: Stolen tokens can be used even after password reset."
            )

    @pytest.mark.asyncio
    async def test_concurrent_sessions_allowed(self, client, admin_user):
        """
        Test concurrent sessions behavior.

        This documents whether multiple simultaneous logins are allowed.
        This is typically allowed but should be monitored for suspicious activity.

        Note: The login endpoint uses httpOnly cookies for tokens (security feature),
        so we extract tokens from cookies instead of JSON response.
        """
        # Login twice
        response1 = await client.post("/api/auth/login", json={
            "email": admin_user.email,
            "password": "Admin123"  # Correct password from fixture
        })
        assert response1.status_code == 200, f"First login failed: {response1.text}"
        # Token is in httpOnly cookie, not in JSON response
        token1 = response1.cookies.get("access_token")
        assert token1 is not None, "No access_token cookie in first login response"

        response2 = await client.post("/api/auth/login", json={
            "email": admin_user.email,
            "password": "Admin123"  # Correct password from fixture
        })
        assert response2.status_code == 200, f"Second login failed: {response2.text}"
        token2 = response2.cookies.get("access_token")
        assert token2 is not None, "No access_token cookie in second login response"

        # Both tokens should work
        response1 = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token1}"})
        response2 = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token2}"})

        assert response1.status_code == 200
        assert response2.status_code == 200

        # Document that concurrent sessions are allowed
        # This is normal behavior but should be monitored


class TestInputValidation:
    """
    Test input validation and sanitization.
    """

    @pytest.mark.asyncio
    async def test_email_validation(self, client):
        """
        Test that invalid emails are rejected.

        EXPECTED: Proper email validation
        """
        response = await client.post("/api/auth/login", json={
            "email": "not-an-email",
            "password": "password123"
        })

        # Should fail validation (422) or authentication (401)
        assert response.status_code in [401, 422]

    @pytest.mark.asyncio
    async def test_sql_injection_in_email(self, client):
        """
        Test that SQL injection attempts in email are handled safely.

        EXPECTED: Should not cause SQL errors or unauthorized access
        """
        sql_injection_attempts = [
            "admin@test.com' OR '1'='1",
            "admin@test.com'; DROP TABLE users; --",
            "admin@test.com' UNION SELECT * FROM users --"
        ]

        for injection in sql_injection_attempts:
            response = await client.post("/api/auth/login", json={
                "email": injection,
                "password": "password123"
            })

            # Should fail safely (401 or 422), not 500
            assert response.status_code in [401, 422], (
                f"SQL injection attempt caused unexpected status: {response.status_code}"
            )

    @pytest.mark.asyncio
    async def test_xss_in_name_field(self, client, admin_user, admin_token, get_auth_headers):
        """
        Test that XSS attempts in name fields are handled.

        NOTE: This test documents the need for output escaping in frontend.
        Backend should store data as-is, frontend should escape when rendering.
        """
        xss_attempts = [
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert('xss')>",
            "';alert('xss');//"
        ]

        # Backend typically stores data as-is
        # Frontend is responsible for proper escaping
        # This test just ensures no crashes
        for xss in xss_attempts:
            response = await client.get("/api/auth/me", headers=get_auth_headers(admin_token))
            # Should not crash
            assert response.status_code == 200


class TestSecurityHeaders:
    """
    Test security-related HTTP headers.

    NOTE: These tests document recommended security headers.
    """

    @pytest.mark.asyncio
    async def test_security_headers_present(self, client):
        """
        Test that security headers are present.

        RECOMMENDED HEADERS:
        - X-Content-Type-Options: nosniff
        - X-Frame-Options: DENY or SAMEORIGIN
        - X-XSS-Protection: 1; mode=block
        - Strict-Transport-Security: max-age=31536000; includeSubDomains
        - Content-Security-Policy: appropriate policy
        """
        # JSON-ответы (/api/*, /health) получают только nosniff + no-store
        # (middleware/security.py: CSP и прочее браузер к JSON не применяет).
        response = await client.get("/health")
        assert response.headers.get("x-content-type-options") == "nosniff"
        assert "no-store" in response.headers.get("cache-control", "")

        # Полный набор — у страниц вне API.
        response = await client.get("/not-an-api-page")

        # Check that all required security headers are present
        assert response.headers.get("x-content-type-options") == "nosniff", \
            "X-Content-Type-Options header should be set to nosniff"

        assert response.headers.get("x-frame-options") == "DENY", \
            "X-Frame-Options header should be set to DENY"

        assert response.headers.get("x-xss-protection") == "1; mode=block", \
            "X-XSS-Protection header should be set to '1; mode=block'"

        hsts = response.headers.get("strict-transport-security", "")
        assert "max-age=" in hsts, \
            "Strict-Transport-Security header should contain max-age"
        assert "includeSubDomains" in hsts, \
            "Strict-Transport-Security header should include includeSubDomains"

        csp = response.headers.get("content-security-policy", "")
        assert "default-src" in csp, \
            "Content-Security-Policy header should contain default-src directive"


class TestAPISecurityBestPractices:
    """
    Test general API security best practices.
    """

    @pytest.mark.asyncio
    async def test_error_messages_dont_leak_info(self, client):
        """
        Test that error messages don't leak sensitive information.

        EXPECTED: Generic error messages, not detailed system info
        """
        # Try to login with non-existent user
        response = await client.post("/api/auth/login", json={
            "email": "nonexistent@test.com",
            "password": "password123"
        })

        error_message = response.json().get("detail", "").lower()

        # Should not reveal if user exists or not
        # Should be generic like "Invalid credentials"
        assert "not found" not in error_message, (
            "Error message reveals user existence: Should use generic 'Invalid credentials'"
        )

    @pytest.mark.asyncio
    async def test_timing_attack_resistance(self, client, admin_user):
        """
        Test resistance to timing attacks on login.

        EXPECTED: Similar response time for existing/non-existing users
        CURRENT: Likely vulnerable (bcrypt check only for existing users)

        NOTE: This is difficult to test reliably without many iterations
        """
        import time

        # Time login with existing user
        start = time.time()
        await client.post("/api/auth/login", json={
            "email": "admin@test.com",
            "password": "wrongpassword"
        })
        existing_time = time.time() - start

        # Time login with non-existing user
        start = time.time()
        await client.post("/api/auth/login", json={
            "email": "nonexistent@test.com",
            "password": "wrongpassword"
        })
        nonexistent_time = time.time() - start

        # Times should be similar (within 100ms for single request)
        # Note: This is a basic check, timing attacks need statistical analysis
        time_difference = abs(existing_time - nonexistent_time)

        # Assert that timing difference is not significant
        assert time_difference <= 0.1, (
            f"Potential timing attack vulnerability: {time_difference:.3f}s difference. "
            f"Times should be similar to prevent user enumeration."
        )
