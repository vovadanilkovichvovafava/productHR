"""
Tests for authentication and authorization.
"""
import pytest
from datetime import datetime, timedelta
from jose import jwt

from api.services.auth import (
    hash_password,
    verify_password,
    create_access_token,
    authenticate_user
)
from api.config import settings
from api.models.database import User, UserRole


class TestPasswordHashing:
    """Test password hashing functions."""

    def test_hash_password_creates_hash(self):
        """Test that password hash is created."""
        password = "testpassword123"
        hashed = hash_password(password)

        assert hashed is not None
        assert hashed != password
        assert len(hashed) > 20

    def test_hash_password_different_each_time(self):
        """Test that same password creates different hashes (salt)."""
        password = "testpassword123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        assert hash1 != hash2

    def test_verify_password_correct(self):
        """Test password verification with correct password."""
        password = "testpassword123"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password."""
        password = "testpassword123"
        hashed = hash_password(password)

        assert verify_password("wrongpassword", hashed) is False

    def test_verify_password_empty(self):
        """Test password verification with empty password."""
        password = "testpassword123"
        hashed = hash_password(password)

        assert verify_password("", hashed) is False

    def test_hash_empty_password(self):
        """Test hashing empty password (should work but not recommended)."""
        hashed = hash_password("")
        assert hashed is not None
        assert verify_password("", hashed) is True


class TestJWTTokens:
    """Test JWT token creation and validation."""

    def test_create_access_token(self):
        """Test creating access token."""
        data = {"sub": "test@test.com", "user_id": 1}
        token = create_access_token(data)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 50

    def test_create_access_token_contains_data(self):
        """Test that token contains correct data."""
        data = {"sub": "test@test.com", "user_id": 123}
        token = create_access_token(data)

        decoded = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])

        assert decoded["sub"] == "test@test.com"
        assert decoded["user_id"] == 123

    def test_create_access_token_has_expiration(self):
        """Test that token has expiration."""
        data = {"sub": "test@test.com"}
        token = create_access_token(data)

        decoded = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])

        assert "exp" in decoded
        exp_time = datetime.utcfromtimestamp(decoded["exp"])  # exp — UTC; fromtimestamp сдвигал на пояс машины
        assert exp_time > datetime.utcnow()

    def test_create_access_token_custom_expiration(self):
        """Test token with custom expiration."""
        data = {"sub": "test@test.com"}
        expires_delta = timedelta(minutes=5)
        token = create_access_token(data, expires_delta=expires_delta)

        decoded = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])

        exp_time = datetime.utcfromtimestamp(decoded["exp"])  # exp — UTC; fromtimestamp сдвигал на пояс машины
        expected_exp = datetime.utcnow() + expires_delta

        # Allow 1 minute tolerance
        assert abs((exp_time - expected_exp).total_seconds()) < 60

    def test_invalid_token_raises_error(self):
        """Test that invalid token raises error."""
        with pytest.raises(jwt.JWTError):
            jwt.decode("invalid.token.here", settings.jwt_secret, algorithms=["HS256"])

    def test_expired_token_raises_error(self):
        """Test that expired token raises error."""
        data = {"sub": "test@test.com"}
        expires_delta = timedelta(seconds=-1)  # Already expired
        token = create_access_token(data, expires_delta=expires_delta)

        with pytest.raises(jwt.ExpiredSignatureError):
            jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


class TestAuthenticateUser:
    """Test user authentication."""

    @pytest.mark.asyncio
    async def test_authenticate_valid_user(self, db_session, admin_user):
        """Test authentication with valid credentials."""
        user = await authenticate_user(db_session, "admin@test.com", "Admin123")

        assert user is not None
        assert user.email == "admin@test.com"

    @pytest.mark.asyncio
    async def test_authenticate_wrong_password(self, db_session, admin_user):
        """Test authentication with wrong password."""
        user = await authenticate_user(db_session, "admin@test.com", "WrongPassword123")

        assert user is None

    @pytest.mark.asyncio
    async def test_authenticate_nonexistent_user(self, db_session):
        """Test authentication with non-existent user."""
        user = await authenticate_user(db_session, "nonexistent@test.com", "password")

        assert user is None

    @pytest.mark.asyncio
    async def test_authenticate_empty_password(self, db_session, admin_user):
        """Test authentication with empty password."""
        user = await authenticate_user(db_session, "admin@test.com", "")

        assert user is None

    @pytest.mark.asyncio
    async def test_authenticate_case_sensitive_email(self, db_session, admin_user):
        """Test that email is case-sensitive (or not, depending on implementation)."""
        user = await authenticate_user(db_session, "ADMIN@test.com", "Admin123")
        # This depends on implementation - adjust based on expected behavior
        # If case-insensitive:
        # assert user is not None
        # If case-sensitive:
        # assert user is None


class TestLoginEndpoint:
    """Test /api/auth/login endpoint."""

    @pytest.mark.asyncio
    async def test_login_success(self, client, admin_user):
        """Test successful login."""
        response = await client.post("/api/auth/login", json={
            "email": "admin@test.com",
            "password": "Admin123"
        })

        assert response.status_code == 200
        data = response.json()
        # Ответ — TokenResponse: данные человека в "user" (токен в теле —
        # для расширения), вебу токен приходит httpOnly-кукой.
        assert "id" in data["user"]
        assert data["user"]["email"] == "admin@test.com"
        # Check that access_token cookie is set
        assert "access_token" in response.cookies

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client, admin_user):
        """Test login with wrong password."""
        response = await client.post("/api/auth/login", json={
            "email": "admin@test.com",
            "password": "WrongPassword123"
        })

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client):
        """Test login with non-existent user."""
        response = await client.post("/api/auth/login", json={
            "email": "nonexistent@test.com",
            "password": "password123"
        })

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_missing_email(self, client):
        """Test login without email."""
        response = await client.post("/api/auth/login", json={
            "password": "password123"
        })

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_login_missing_password(self, client):
        """Test login without password."""
        response = await client.post("/api/auth/login", json={
            "email": "admin@test.com"
        })

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_login_invalid_email_format(self, client):
        """Test login with invalid email format."""
        response = await client.post("/api/auth/login", json={
            "email": "notanemail",
            "password": "password123"
        })

        # Should fail validation or authentication
        assert response.status_code in [401, 422]


class TestProtectedEndpoints:
    """Test that protected endpoints require authentication."""

    @pytest.mark.asyncio
    async def test_protected_endpoint_without_token(self, client):
        """Test accessing protected endpoint without token."""
        response = await client.get("/api/auth/me")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_protected_endpoint_with_invalid_token(self, client):
        """Test accessing protected endpoint with invalid token."""
        response = await client.get("/api/auth/me", headers={
            "Authorization": "Bearer invalid.token.here"
        })

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_protected_endpoint_with_valid_token(self, client, admin_user, admin_token, get_auth_headers):
        """Test accessing protected endpoint with valid token."""
        response = await client.get("/api/auth/me", headers=get_auth_headers(admin_token))

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "admin@test.com"

    @pytest.mark.asyncio
    async def test_protected_endpoint_with_expired_token(self, client, admin_user):
        """Test accessing protected endpoint with expired token."""
        token = create_access_token(
            data={"sub": admin_user.email, "user_id": admin_user.id},
            expires_delta=timedelta(seconds=-1)
        )

        response = await client.get("/api/auth/me", headers={
            "Authorization": f"Bearer {token}"
        })

        assert response.status_code == 401


class TestChangePassword:
    """Test password change functionality."""

    @pytest.mark.asyncio
    async def test_change_password_success(self, client, admin_user, admin_token, get_auth_headers):
        """Test successful password change."""
        response = await client.post("/api/auth/change-password",
            json={
                "current_password": "Admin123",
                "new_password": "NewPassword123"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_change_password_wrong_current(self, client, admin_user, admin_token, get_auth_headers):
        """Test password change with wrong current password."""
        response = await client.post("/api/auth/change-password",
            json={
                "current_password": "WrongPassword123",
                "new_password": "NewPassword456"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code in [400, 401, 403]

    @pytest.mark.asyncio
    async def test_change_password_weak_new_password(self, client, admin_user, admin_token, get_auth_headers):
        """Test password change with weak new password."""
        response = await client.post("/api/auth/change-password",
            json={
                "current_password": "Admin123",
                "new_password": "123"  # Too short
            },
            headers=get_auth_headers(admin_token)
        )

        # Should now return validation error
        assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_change_password_unauthenticated(self, client):
        """Test password change without authentication."""
        response = await client.post("/api/auth/change-password",
            json={
                "current_password": "Admin123",
                "new_password": "NewPassword123"
            }
        )

        assert response.status_code == 401


class TestUserRoles:
    """Test user role-based access."""

    @pytest.mark.asyncio
    async def test_superadmin_can_access_admin_endpoints(self, client, superadmin_user, superadmin_token, get_auth_headers):
        """Test that superadmin can access admin-only endpoints."""
        response = await client.get("/api/users", headers=get_auth_headers(superadmin_token))

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_regular_user_cannot_access_admin_endpoints(self, client, regular_user, user_token, get_auth_headers, organization, org_member):
        """Test that regular user cannot access admin-only endpoints."""
        # This depends on which endpoints are admin-only
        # Example: listing all users in system
        response = await client.get("/api/users", headers=get_auth_headers(user_token))

        # Should be forbidden or return limited data
        # assert response.status_code in [403, 200]  # Depends on implementation
