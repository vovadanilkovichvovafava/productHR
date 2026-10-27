"""
Tests for password reset flow.

This module tests the complete flow:
1. Admin resets user password
2. User logs in with temporary password
3. User changes password (must_change_password flow)
4. User can continue using the application without re-login
"""
import pytest
from api.services.auth import create_access_token, hash_password
from api.models.database import User, UserRole


class TestPasswordResetFlow:
    """Tests for admin password reset and forced password change."""

    @pytest.mark.asyncio
    async def test_admin_reset_password_sets_must_change_flag(
        self, client, db_session, superadmin_user, admin_user, get_auth_headers
    ):
        """Test that admin password reset sets must_change_password flag."""
        # Create token for superadmin
        superadmin_token = create_access_token({
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        # Reset admin user's password
        response = await client.post(
            f"/api/admin/users/{admin_user.id}/reset-password",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert "temporary_password" in data
        assert data["user_email"] == admin_user.email

        # Verify flag is set in database
        await db_session.refresh(admin_user)
        assert admin_user.must_change_password is True

    @pytest.mark.asyncio
    async def test_login_returns_must_change_password_flag(
        self, client, db_session, superadmin_user, admin_user, get_auth_headers
    ):
        """Test that login returns must_change_password flag when set."""
        # Create token for superadmin and reset password
        superadmin_token = create_access_token({
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        reset_response = await client.post(
            f"/api/admin/users/{admin_user.id}/reset-password",
            headers=get_auth_headers(superadmin_token)
        )
        temp_password = reset_response.json()["temporary_password"]

        # Login with temporary password
        login_response = await client.post("/api/auth/login", json={
            "email": admin_user.email,
            "password": temp_password
        })

        assert login_response.status_code == 200
        data = login_response.json()
        # Флаг — в данных человека (TokenResponse.user)
        assert data["user"]["must_change_password"] is True

    @pytest.mark.asyncio
    async def test_password_change_after_reset_keeps_token_valid(
        self, client, db_session, superadmin_user, admin_user, get_auth_headers
    ):
        """
        Test that changing password after admin reset does NOT invalidate token.

        This is the main bug fix test:
        - Admin resets password -> token_version increments
        - User logs in -> gets new token with new token_version
        - User changes password (must_change_password=True) -> token should stay valid
        """
        # Create token for superadmin and reset password
        superadmin_token = create_access_token({
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        reset_response = await client.post(
            f"/api/admin/users/{admin_user.id}/reset-password",
            headers=get_auth_headers(superadmin_token)
        )
        temp_password = reset_response.json()["temporary_password"]

        # Login with temporary password
        login_response = await client.post("/api/auth/login", json={
            "email": admin_user.email,
            "password": temp_password
        })
        assert login_response.status_code == 200

        # Get token from cookies
        user_token = login_response.cookies.get("access_token")
        assert user_token is not None

        # Verify user can access API
        me_response = await client.get(
            "/api/auth/me",
            headers=get_auth_headers(user_token)
        )
        assert me_response.status_code == 200
        assert me_response.json()["must_change_password"] is True

        # Change password
        change_response = await client.post(
            "/api/auth/change-password",
            json={
                "current_password": temp_password,
                "new_password": "NewSecurePass123"
            },
            headers=get_auth_headers(user_token)
        )
        assert change_response.status_code == 200

        # KEY TEST: Token should STILL be valid after password change
        me_response_after = await client.get(
            "/api/auth/me",
            headers=get_auth_headers(user_token)
        )
        assert me_response_after.status_code == 200, (
            "Token was invalidated after forced password change! "
            "This breaks the UX - user gets logged out immediately after changing password."
        )
        assert me_response_after.json()["must_change_password"] is False

    @pytest.mark.asyncio
    async def test_voluntary_password_change_invalidates_token(
        self, client, db_session, admin_user, get_auth_headers
    ):
        """
        Test that voluntary password change (must_change_password=False) DOES invalidate token.

        This ensures security: when user voluntarily changes password,
        all other sessions should be logged out.
        """
        # Create initial token
        initial_token = create_access_token({
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        # Verify user can access API
        me_response = await client.get(
            "/api/auth/me",
            headers=get_auth_headers(initial_token)
        )
        assert me_response.status_code == 200
        assert me_response.json()["must_change_password"] is False

        # Voluntarily change password
        change_response = await client.post(
            "/api/auth/change-password",
            json={
                "current_password": "Admin123",  # Original password from fixture
                "new_password": "NewSecurePass123"
            },
            headers=get_auth_headers(initial_token)
        )
        assert change_response.status_code == 200

        # Token should be INVALID after voluntary password change
        me_response_after = await client.get(
            "/api/auth/me",
            headers=get_auth_headers(initial_token)
        )
        assert me_response_after.status_code == 401, (
            "Token was NOT invalidated after voluntary password change! "
            "This is a security issue - other sessions should be logged out."
        )

    @pytest.mark.asyncio
    async def test_full_password_reset_flow(
        self, client, db_session, superadmin_user, get_auth_headers
    ):
        """
        Test the complete password reset flow end-to-end.

        1. Superadmin creates a user
        2. Superadmin resets user's password
        3. User logs in with temp password
        4. User is prompted to change password
        5. User changes password
        6. User continues using the app without interruption
        """
        # Step 1: Create a new user (directly in DB for simplicity)
        new_user = User(
            email="newuser@test.com",
            password_hash=hash_password("InitialPass123"),
            name="New User",
            role=UserRole.member,
            is_active=True
        )
        db_session.add(new_user)
        await db_session.commit()
        await db_session.refresh(new_user)

        # Step 2: Superadmin resets password
        superadmin_token = create_access_token({
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        reset_response = await client.post(
            f"/api/admin/users/{new_user.id}/reset-password",
            headers=get_auth_headers(superadmin_token)
        )
        assert reset_response.status_code == 200
        temp_password = reset_response.json()["temporary_password"]

        # Step 3: User logs in
        login_response = await client.post("/api/auth/login", json={
            "email": "newuser@test.com",
            "password": temp_password
        })
        assert login_response.status_code == 200
        user_token = login_response.cookies.get("access_token")

        # Step 4: Verify must_change_password is True
        me_response = await client.get(
            "/api/auth/me",
            headers=get_auth_headers(user_token)
        )
        assert me_response.status_code == 200
        assert me_response.json()["must_change_password"] is True

        # Step 5: User changes password
        change_response = await client.post(
            "/api/auth/change-password",
            json={
                "current_password": temp_password,
                "new_password": "MyNewSecurePass456"
            },
            headers=get_auth_headers(user_token)
        )
        assert change_response.status_code == 200

        # Step 6: User can continue using the app
        me_response_final = await client.get(
            "/api/auth/me",
            headers=get_auth_headers(user_token)
        )
        assert me_response_final.status_code == 200
        assert me_response_final.json()["must_change_password"] is False
        assert me_response_final.json()["email"] == "newuser@test.com"


class TestPasswordResetEdgeCases:
    """Edge cases for password reset flow."""

    @pytest.mark.asyncio
    async def test_cannot_reset_other_superadmin_password(
        self, client, db_session, superadmin_user, get_auth_headers
    ):
        """Test that superadmin cannot reset another superadmin's password."""
        # Create another superadmin
        other_superadmin = User(
            email="other_superadmin@test.com",
            password_hash=hash_password("OtherAdmin123"),
            name="Other Superadmin",
            role=UserRole.superadmin,
            is_active=True
        )
        db_session.add(other_superadmin)
        await db_session.commit()
        await db_session.refresh(other_superadmin)

        # Try to reset other superadmin's password
        superadmin_token = create_access_token({
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.post(
            f"/api/admin/users/{other_superadmin.id}/reset-password",
            headers=get_auth_headers(superadmin_token)
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_password_reset_unlocks_account(
        self, client, db_session, superadmin_user, admin_user, get_auth_headers
    ):
        """Test that password reset unlocks a locked account."""
        from datetime import datetime, timedelta

        # Lock the admin user's account
        admin_user.failed_login_attempts = 5
        admin_user.locked_until = datetime.utcnow() + timedelta(minutes=15)
        await db_session.commit()

        # Reset password
        superadmin_token = create_access_token({
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.post(
            f"/api/admin/users/{admin_user.id}/reset-password",
            headers=get_auth_headers(superadmin_token)
        )
        assert response.status_code == 200

        # Verify account is unlocked
        await db_session.refresh(admin_user)
        assert admin_user.failed_login_attempts == 0
        assert admin_user.locked_until is None

    @pytest.mark.asyncio
    async def test_weak_password_rejected_during_change(
        self, client, db_session, superadmin_user, admin_user, get_auth_headers
    ):
        """Test that weak passwords are rejected when changing after reset."""
        # Reset password
        superadmin_token = create_access_token({
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        reset_response = await client.post(
            f"/api/admin/users/{admin_user.id}/reset-password",
            headers=get_auth_headers(superadmin_token)
        )
        temp_password = reset_response.json()["temporary_password"]

        # Login
        login_response = await client.post("/api/auth/login", json={
            "email": admin_user.email,
            "password": temp_password
        })
        user_token = login_response.cookies.get("access_token")

        # Try to set weak password
        change_response = await client.post(
            "/api/auth/change-password",
            json={
                "current_password": temp_password,
                "new_password": "123"  # Too weak
            },
            headers=get_auth_headers(user_token)
        )

        # Should be rejected (400 from backend or 422 from validation)
        assert change_response.status_code in [400, 422]
