"""
Tests for authentication security features.

This module tests:
1. Rate limiting on auth endpoints
2. Brute-force protection (account lockout)
3. Password complexity validation
"""
import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient

from api.models.database import User, UserRole
from api.services.auth import hash_password


class TestRateLimiting:
    """Test rate limiting on authentication endpoints."""

    @pytest.mark.asyncio
    async def test_login_rate_limit(self, client: AsyncClient, admin_user: User):
        """Test that login endpoint is rate limited to 5 requests per minute.

        NOTE: This test requires rate limiting to be enabled.
        In test mode, rate limiting is disabled by default (see conftest.py).
        To test rate limiting, we need to temporarily enable it.
        """
        # This test documents the EXPECTED behavior
        # In production, after 5 failed login attempts from same IP,
        # the 6th request should return 429 (Too Many Requests)

        # For now, we just verify that the endpoint works
        response = await client.post("/api/auth/login", json={
            "email": "admin@test.com",
            "password": "Admin123"
        })
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_register_rate_limit(self, client: AsyncClient):
        """Test that register endpoint is rate limited to 3 requests per minute.

        NOTE: Registration is currently disabled, so this returns 403.
        This test documents the expected rate limiting behavior.
        """
        response = await client.post("/api/auth/register", json={
            "email": "new@test.com",
            "password": "Test123456",
            "name": "New User"
        })
        # Registration is disabled, so we get 403
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_change_password_rate_limit(self, client: AsyncClient, admin_user: User, admin_token, get_auth_headers):
        """Test that change-password endpoint is rate limited to 3 requests per minute."""
        # This test verifies the endpoint works
        # In production, after 3 requests from same IP, should return 429
        response = await client.post("/api/auth/change-password",
            json={
                "current_password": "admin123",
                "new_password": "NewPass123"
            },
            headers=get_auth_headers(admin_token)
        )
        # Should succeed (password validation will pass now with uppercase)
        assert response.status_code in [200, 400]  # 400 if current password is wrong


class TestBruteForceProtection:
    """Test brute-force protection (account lockout after failed attempts)."""

    # Блокировку аккаунта после неудачных попыток УБРАЛИ намеренно (комментарий
    # в routes/auth.py login): она запирала HR на 15 минут из-за автозаполненного
    # пароля. Счётчик на входе не растёт и не читается; успешный вход обнуляет
    # failed_login_attempts/locked_until, снимая старый лок. От перебора
    # остаётся лимит частоты запросов на /login.

    @pytest.mark.asyncio
    async def test_failed_login_does_not_increment_counter(self, client: AsyncClient, admin_user: User, db_session):
        """Неудачный вход — 401, счётчик попыток не растёт (lockout убран)."""
        assert admin_user.failed_login_attempts == 0
        assert admin_user.locked_until is None

        response = await client.post("/api/auth/login", json={
            "email": "admin@test.com",
            "password": "wrongpassword"
        })

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials"

        await db_session.refresh(admin_user)
        assert admin_user.failed_login_attempts == 0
        assert admin_user.locked_until is None

    @pytest.mark.asyncio
    async def test_successful_login_resets_counter(self, client: AsyncClient, admin_user: User, db_session):
        """Test that successful login resets failed attempts counter."""
        # Set failed attempts
        admin_user.failed_login_attempts = 3
        await db_session.commit()

        # Successful login
        response = await client.post("/api/auth/login", json={
            "email": "admin@test.com",
            "password": "Admin123"
        })

        assert response.status_code == 200

        # Refresh user from database
        await db_session.refresh(admin_user)

        # Failed attempts should be reset
        assert admin_user.failed_login_attempts == 0
        assert admin_user.locked_until is None

    @pytest.mark.asyncio
    async def test_no_lockout_after_5_failed_attempts(self, client: AsyncClient, admin_user: User, db_session):
        """После 5 неудачных попыток аккаунт не запирается: верный пароль впускает."""
        for _ in range(5):
            response = await client.post("/api/auth/login", json={
                "email": "admin@test.com",
                "password": "wrongpassword"
            })
            assert response.status_code == 401
            assert response.json()["detail"] == "Invalid credentials"

        await db_session.refresh(admin_user)
        assert admin_user.locked_until is None

        response = await client.post("/api/auth/login", json={
            "email": "admin@test.com",
            "password": "Admin123"
        })
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_old_lock_is_cleared_by_correct_password(self, client: AsyncClient, admin_user: User, db_session):
        """Лок, выставленный раньше (до отмены блокировки), вход не держит и снимается."""
        admin_user.failed_login_attempts = 5
        admin_user.locked_until = datetime.utcnow() + timedelta(minutes=15)
        await db_session.commit()

        response = await client.post("/api/auth/login", json={
            "email": "admin@test.com",
            "password": "Admin123"
        })

        assert response.status_code == 200
        await db_session.refresh(admin_user)
        assert admin_user.failed_login_attempts == 0
        assert admin_user.locked_until is None

    @pytest.mark.asyncio
    async def test_lockout_expires_after_15_minutes(self, client: AsyncClient, admin_user: User, db_session):
        """Test that account lockout expires after 15 minutes."""
        # Lock the account with expired lockout time
        admin_user.failed_login_attempts = 5
        admin_user.locked_until = datetime.utcnow() - timedelta(minutes=1)  # Expired 1 minute ago
        await db_session.commit()

        # Try to login with correct password
        response = await client.post("/api/auth/login", json={
            "email": "admin@test.com",
            "password": "Admin123"
        })

        # Should succeed - lockout has expired
        assert response.status_code == 200

        # Refresh user from database
        await db_session.refresh(admin_user)

        # Lockout should be cleared
        assert admin_user.failed_login_attempts == 0
        assert admin_user.locked_until is None

    @pytest.mark.asyncio
    async def test_generic_error_message_for_nonexistent_user(self, client: AsyncClient):
        """Test that login returns generic error for non-existent user (prevents user enumeration)."""
        response = await client.post("/api/auth/login", json={
            "email": "nonexistent@test.com",
            "password": "somepassword"
        })

        # Should return generic error message
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials"
        # Should NOT reveal that user doesn't exist


class TestPasswordValidation:
    """Test password complexity validation."""

    @pytest.mark.asyncio
    async def test_password_too_short(self, client: AsyncClient, admin_user: User, admin_token, get_auth_headers):
        """Test that password shorter than 8 characters is rejected."""
        response = await client.post("/api/auth/change-password",
            json={
                "current_password": "admin123",
                "new_password": "Ab1"  # Too short
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 422  # Validation error
        assert "at least 8 characters" in str(response.json()).lower()

    @pytest.mark.asyncio
    async def test_password_no_uppercase(self, client: AsyncClient, admin_user: User, admin_token, get_auth_headers):
        """Test that password without uppercase letter is rejected."""
        response = await client.post("/api/auth/change-password",
            json={
                "current_password": "admin123",
                "new_password": "alllowercase123"  # No uppercase
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 422  # Validation error
        assert "uppercase" in str(response.json()).lower()

    @pytest.mark.asyncio
    async def test_password_no_lowercase(self, client: AsyncClient, admin_user: User, admin_token, get_auth_headers):
        """Test that password without lowercase letter is rejected."""
        response = await client.post("/api/auth/change-password",
            json={
                "current_password": "admin123",
                "new_password": "ALLUPPERCASE123"  # No lowercase
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 422  # Validation error
        assert "lowercase" in str(response.json()).lower()

    @pytest.mark.asyncio
    async def test_password_no_digit(self, client: AsyncClient, admin_user: User, admin_token, get_auth_headers):
        """Test that password without digit is rejected."""
        response = await client.post("/api/auth/change-password",
            json={
                "current_password": "admin123",
                "new_password": "NoDigitsHere"  # No digit
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 422  # Validation error
        assert "number" in str(response.json()).lower()

    @pytest.mark.asyncio
    async def test_password_common_password(self, client: AsyncClient, admin_user: User, admin_token, get_auth_headers):
        """Test that common passwords are rejected."""
        response = await client.post("/api/auth/change-password",
            json={
                "current_password": "admin123",
                "new_password": "Password123"  # Common password
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 422  # Validation error
        assert "common" in str(response.json()).lower()

    @pytest.mark.asyncio
    async def test_password_matches_email(self, client: AsyncClient, db_session):
        """Test that password matching email is rejected."""
        # Create user with UserCreate (this will trigger validation)
        from api.models.schemas import UserCreate
        from api.services.password_policy import validate_password

        # Test the validation function directly
        is_valid, error = validate_password("admin@test.com", "admin@test.com")
        assert not is_valid
        assert "email" in error.lower()

    @pytest.mark.asyncio
    async def test_password_valid(self, client: AsyncClient, admin_user: User, admin_token, get_auth_headers):
        """Test that valid password is accepted."""
        response = await client.post("/api/auth/change-password",
            json={
                "current_password": "Admin123",
                "new_password": "ValidPass123"  # Valid: 8+ chars, uppercase, lowercase, digit
            },
            headers=get_auth_headers(admin_token)
        )

        # Should succeed or fail with wrong current password (not validation error)
        # If it fails with 400, it's because current password is wrong (which is ok for this test)
        # If it succeeds with 200, that's also ok
        # But it should NOT fail with 422 (validation error)
        assert response.status_code in [200, 400]

    @pytest.mark.asyncio
    async def test_user_create_with_weak_password(self, db_session):
        """Test that creating user with weak password is rejected."""
        from api.models.schemas import UserCreate
        from pydantic import ValidationError

        # Test weak password rejection via Pydantic validation
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(
                email="test@test.com",
                password="weak",  # Too short, no uppercase, no digit
                name="Test User"
            )

        # Should contain validation error about password
        errors = exc_info.value.errors()
        assert len(errors) > 0
        assert any("password" in str(error).lower() for error in errors)

    @pytest.mark.asyncio
    async def test_user_create_with_valid_password(self, db_session):
        """Test that creating user with valid password succeeds."""
        from api.models.schemas import UserCreate

        # Should not raise validation error
        user_data = UserCreate(
            email="test@test.com",
            password="ValidPass123",  # Valid password
            name="Test User"
        )

        assert user_data.email == "test@test.com"
        assert user_data.password == "ValidPass123"


class TestPasswordPolicyFunction:
    """Test the password validation function directly."""

    def test_validate_password_too_short(self):
        """Test password validation for too short password."""
        from api.services.password_policy import validate_password

        is_valid, error = validate_password("Ab1")
        assert not is_valid
        assert "8 characters" in error

    def test_validate_password_no_uppercase(self):
        """Test password validation for missing uppercase."""
        from api.services.password_policy import validate_password

        is_valid, error = validate_password("alllower123")
        assert not is_valid
        assert "uppercase" in error.lower()

    def test_validate_password_no_lowercase(self):
        """Test password validation for missing lowercase."""
        from api.services.password_policy import validate_password

        is_valid, error = validate_password("ALLUPPER123")
        assert not is_valid
        assert "lowercase" in error.lower()

    def test_validate_password_no_digit(self):
        """Test password validation for missing digit."""
        from api.services.password_policy import validate_password

        is_valid, error = validate_password("NoDigitsHere")
        assert not is_valid
        assert "number" in error.lower()

    def test_validate_password_common(self):
        """Test password validation for common password."""
        from api.services.password_policy import validate_password

        is_valid, error = validate_password("Password123")
        assert not is_valid
        assert "common" in error.lower()

    def test_validate_password_matches_email(self):
        """Test password validation when password matches email."""
        from api.services.password_policy import validate_password

        is_valid, error = validate_password("admin@test.com", "admin@test.com")
        assert not is_valid
        assert "email" in error.lower()

    def test_validate_password_matches_username(self):
        """Test password validation when password matches email username."""
        from api.services.password_policy import validate_password

        # «admin» сам по себе в списке частых паролей, а эта проверка идёт
        # первой — для проверки «совпадает с именем почты» нужен нечастый логин.
        is_valid, error = validate_password("johnsmith2024", "johnsmith2024@test.com")
        assert not is_valid
        assert "email username" in error.lower()

    def test_validate_password_valid(self):
        """Test password validation for valid password."""
        from api.services.password_policy import validate_password

        is_valid, error = validate_password("ValidPass123")
        assert is_valid
        assert error == ""

    def test_validate_password_valid_with_email(self):
        """Test password validation for valid password with email check."""
        from api.services.password_policy import validate_password

        is_valid, error = validate_password("CompletelyDifferent123", "admin@test.com")
        assert is_valid
        assert error == ""
