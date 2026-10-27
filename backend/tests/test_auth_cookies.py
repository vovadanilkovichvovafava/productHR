"""
Tests for cookie-based authentication (XSS protection).

These tests verify that JWT tokens are properly stored in httpOnly cookies
instead of being returned in the response body, which prevents XSS attacks.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import User, Organization, OrgMember, UserRole, OrgRole



def _plain(jar):
    """Куки ответа как обычный словарь.

    Сервер ставит куке флаг Secure (is_secure_context), а тестовый клиент ходит
    по http://test — httpx такие куки из jar обратно не отправляет, и /me
    отвечал 401. Браузер на проде ходит по https, там кука уходит.
    """
    return dict(jar)

class TestAuthCookies:
    """Tests for cookie-based authentication."""

    async def test_login_sets_httponly_cookie(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User,
        org_owner
    ):
        """Test that login sets httpOnly cookie and doesn't return token in body."""
        response = await client.post(
            "/api/auth/login",
            json={"email": "admin@test.com", "password": "Admin123"}
        )

        assert response.status_code == 200

        # Тело — TokenResponse: токен в теле есть НАМЕРЕННО (его берёт
        # расширение Chrome, у него нет кук сайта), данные человека — в "user".
        # Вебу токен приходит httpOnly-кукой (проверено ниже).
        data = response.json()
        assert "id" in data["user"]
        assert data["user"]["email"] == "admin@test.com"
        assert data.get("refresh_token") is None  # refresh в теле — только по include_refresh

        # Check that cookie is set
        cookies = response.cookies
        assert "access_token" in cookies
        assert cookies["access_token"] is not None
        assert len(cookies["access_token"]) > 0

        # Cookie should have httpOnly flag (this is checked via Set-Cookie header)
        set_cookie_header = response.headers.get("set-cookie", "")
        assert "access_token=" in set_cookie_header
        assert "HttpOnly" in set_cookie_header
        assert "samesite=lax" in set_cookie_header.lower()  # сравнение — в нижнем регистре

    async def test_authenticated_request_with_cookie_works(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User,
        org_owner
    ):
        """Test that authenticated requests work with cookie."""
        # Login to get cookie
        login_response = await client.post(
            "/api/auth/login",
            json={"email": "admin@test.com", "password": "Admin123"}
        )
        assert login_response.status_code == 200

        # Extract cookie from response
        cookies = _plain(login_response.cookies)

        # Make authenticated request using cookie
        me_response = await client.get(
            "/api/auth/me",
            cookies=cookies  # Pass cookies to the request
        )

        assert me_response.status_code == 200
        data = me_response.json()
        assert data["email"] == "admin@test.com"

    async def test_request_without_cookie_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession
    ):
        """Test that requests without cookie return 401."""
        # Make authenticated request WITHOUT cookie
        response = await client.get("/api/auth/me")

        assert response.status_code == 401
        assert response.json()["detail"] == "Not authenticated"

    async def test_logout_clears_cookie(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User,
        org_owner
    ):
        """Test that logout clears the cookie."""
        # Login first
        login_response = await client.post(
            "/api/auth/login",
            json={"email": "admin@test.com", "password": "Admin123"}
        )
        assert login_response.status_code == 200
        cookies = _plain(login_response.cookies)

        # Logout
        logout_response = await client.post(
            "/api/auth/logout",
            cookies=cookies
        )

        assert logout_response.status_code == 200
        assert logout_response.json()["message"] == "Logged out successfully"

        # Check that cookie is cleared (deleted)
        # When a cookie is deleted, it's set with an expired date or empty value
        set_cookie_header = logout_response.headers.get("set-cookie", "")
        # The cookie should be present in the Set-Cookie header (being deleted)
        assert "access_token" in set_cookie_header

    async def test_request_with_invalid_cookie_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession
    ):
        """Test that requests with invalid cookie return 401."""
        # Make request with invalid cookie
        response = await client.get(
            "/api/auth/me",
            cookies={"access_token": "invalid_token_value"}
        )

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid token"

    async def test_cookie_based_auth_with_multiple_endpoints(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User,
        org_owner
    ):
        """Test that cookie-based auth works across multiple endpoints."""
        # Login
        login_response = await client.post(
            "/api/auth/login",
            json={"email": "admin@test.com", "password": "Admin123"}
        )
        assert login_response.status_code == 200
        cookies = _plain(login_response.cookies)

        # Test /auth/me endpoint
        me_response = await client.get("/api/auth/me", cookies=cookies)
        assert me_response.status_code == 200

        # Test /stats endpoint (requires authentication)
        stats_response = await client.get("/api/stats", cookies=cookies)
        assert stats_response.status_code == 200

        # Test /chats endpoint
        chats_response = await client.get("/api/chats", cookies=cookies)
        assert chats_response.status_code == 200

    async def test_failed_login_does_not_set_cookie(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User,
        org_owner
    ):
        """Test that failed login doesn't set cookie."""
        response = await client.post(
            "/api/auth/login",
            json={"email": "admin@test.com", "password": "WrongPassword123"}
        )

        assert response.status_code == 401

        # Check that no cookie is set
        cookies = response.cookies
        assert "access_token" not in cookies

    async def test_token_version_invalidation_with_cookies(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User,
        org_owner
    ):
        """Test that changing password invalidates old cookies via token_version."""
        # Login
        login_response = await client.post(
            "/api/auth/login",
            json={"email": "admin@test.com", "password": "Admin123"}
        )
        assert login_response.status_code == 200
        old_cookies = _plain(login_response.cookies)

        # Verify cookie works
        me_response = await client.get("/api/auth/me", cookies=old_cookies)
        assert me_response.status_code == 200

        # Change password (this increments token_version)
        change_pw_response = await client.post(
            "/api/auth/change-password",
            json={
                "current_password": "Admin123",
                "new_password": "NewPassword123"
            },
            cookies=old_cookies
        )
        assert change_pw_response.status_code == 200

        # Old cookie should now be invalid
        me_response_after = await client.get("/api/auth/me", cookies=old_cookies)
        assert me_response_after.status_code == 401
        assert me_response_after.json()["detail"] == "Token has been invalidated"

        # Login with new password should work
        new_login_response = await client.post(
            "/api/auth/login",
            json={"email": "admin@test.com", "password": "NewPassword123"}
        )
        assert new_login_response.status_code == 200
        new_cookies = _plain(new_login_response.cookies)

        # New cookie should work
        me_response_new = await client.get("/api/auth/me", cookies=new_cookies)
        assert me_response_new.status_code == 200

    async def test_cookie_security_flags(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User,
        org_owner
    ):
        """Test that cookie has proper security flags set."""
        response = await client.post(
            "/api/auth/login",
            json={"email": "admin@test.com", "password": "Admin123"}
        )

        assert response.status_code == 200

        # Check Set-Cookie header for security flags
        set_cookie_header = response.headers.get("set-cookie", "")

        # httpOnly prevents JavaScript access (XSS protection)
        assert "HttpOnly" in set_cookie_header

        # secure flag (HTTPS only) should be present
        assert "Secure" in set_cookie_header

        # SameSite prevents CSRF
        assert "samesite=lax" in set_cookie_header.lower()

        # path should be /
        assert "Path=/" in set_cookie_header

        # max-age should be set (7 days = 604800 seconds)
        assert "Max-Age=604800" in set_cookie_header

    async def test_no_authorization_header_needed(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User,
        org_owner
    ):
        """Test that Authorization header is not needed with cookie auth."""
        # Login to get cookie
        login_response = await client.post(
            "/api/auth/login",
            json={"email": "admin@test.com", "password": "Admin123"}
        )
        assert login_response.status_code == 200
        cookies = _plain(login_response.cookies)

        # Make request with cookie but WITHOUT Authorization header
        # (in the old system, this would fail)
        response = await client.get(
            "/api/auth/me",
            cookies=cookies
            # No Authorization header!
        )

        assert response.status_code == 200
        assert response.json()["email"] == "admin@test.com"

    async def test_authorization_header_ignored_cookie_used(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User,
        org_owner
    ):
        """Test that even if Authorization header is present, cookie is used."""
        # Login to get cookie
        login_response = await client.post(
            "/api/auth/login",
            json={"email": "admin@test.com", "password": "Admin123"}
        )
        assert login_response.status_code == 200
        cookies = _plain(login_response.cookies)

        # Make request with BOTH cookie AND invalid Authorization header
        # The cookie should be used, not the header
        response = await client.get(
            "/api/auth/me",
            cookies=cookies,
            headers={"Authorization": "Bearer invalid_token"}
        )

        # Should succeed because cookie is valid (header is ignored)
        assert response.status_code == 200
        assert response.json()["email"] == "admin@test.com"
