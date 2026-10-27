"""
Tests for refresh token management.

This module tests:
1. Token creation and storage
2. Token validation (hash verification)
3. Token revocation
4. Token rotation (issuing new tokens)
5. Token expiration handling
"""
import pytest
import pytest_asyncio
from datetime import datetime, timedelta
import hashlib
import secrets
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import User, RefreshToken, UserRole
from api.services.auth import hash_password


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def generate_token() -> str:
    """Generate a secure random refresh token."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Hash a refresh token using SHA-256."""
    return hashlib.sha256(token.encode()).hexdigest()


# ============================================================================
# FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def refresh_user(db_session: AsyncSession) -> User:
    """Create a user for refresh token tests."""
    user = User(
        email="refresh_test@test.com",
        password_hash=hash_password("TestPass123"),
        name="Refresh Test User",
        role=UserRole.admin,
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def valid_refresh_token(db_session: AsyncSession, refresh_user: User) -> tuple[RefreshToken, str]:
    """Create a valid refresh token and return (token_record, raw_token)."""
    raw_token = generate_token()
    token_hash = hash_token(raw_token)

    refresh_token = RefreshToken(
        token_hash=token_hash,
        user_id=refresh_user.id,
        device_name="Test Browser",
        ip_address="127.0.0.1",
        expires_at=datetime.utcnow() + timedelta(days=7),
        created_at=datetime.utcnow()
    )
    db_session.add(refresh_token)
    await db_session.commit()
    await db_session.refresh(refresh_token)
    return refresh_token, raw_token


@pytest_asyncio.fixture
async def expired_refresh_token(db_session: AsyncSession, refresh_user: User) -> tuple[RefreshToken, str]:
    """Create an expired refresh token."""
    raw_token = generate_token()
    token_hash = hash_token(raw_token)

    refresh_token = RefreshToken(
        token_hash=token_hash,
        user_id=refresh_user.id,
        device_name="Expired Browser",
        ip_address="127.0.0.1",
        expires_at=datetime.utcnow() - timedelta(days=1),  # Expired
        created_at=datetime.utcnow() - timedelta(days=8)
    )
    db_session.add(refresh_token)
    await db_session.commit()
    await db_session.refresh(refresh_token)
    return refresh_token, raw_token


@pytest_asyncio.fixture
async def revoked_refresh_token(db_session: AsyncSession, refresh_user: User) -> tuple[RefreshToken, str]:
    """Create a revoked refresh token."""
    raw_token = generate_token()
    token_hash = hash_token(raw_token)

    refresh_token = RefreshToken(
        token_hash=token_hash,
        user_id=refresh_user.id,
        device_name="Revoked Browser",
        ip_address="127.0.0.1",
        expires_at=datetime.utcnow() + timedelta(days=7),
        created_at=datetime.utcnow(),
        revoked_at=datetime.utcnow()  # Revoked
    )
    db_session.add(refresh_token)
    await db_session.commit()
    await db_session.refresh(refresh_token)
    return refresh_token, raw_token


@pytest_asyncio.fixture
async def multiple_refresh_tokens(db_session: AsyncSession, refresh_user: User) -> list[tuple[RefreshToken, str]]:
    """Create multiple refresh tokens for the same user."""
    tokens = []
    devices = ["Chrome on Windows", "Firefox on Linux", "Safari on Mac", "Mobile App"]

    for device in devices:
        raw_token = generate_token()
        token_hash = hash_token(raw_token)

        refresh_token = RefreshToken(
            token_hash=token_hash,
            user_id=refresh_user.id,
            device_name=device,
            ip_address="127.0.0.1",
            expires_at=datetime.utcnow() + timedelta(days=7),
            created_at=datetime.utcnow()
        )
        db_session.add(refresh_token)
        tokens.append((refresh_token, raw_token))

    await db_session.commit()
    for token, _ in tokens:
        await db_session.refresh(token)

    return tokens


# ============================================================================
# TOKEN CREATION TESTS
# ============================================================================

class TestRefreshTokenCreation:
    """Tests for refresh token creation."""

    @pytest.mark.asyncio
    async def test_create_refresh_token(self, db_session: AsyncSession, refresh_user: User):
        """Test creating a new refresh token."""
        raw_token = generate_token()
        token_hash = hash_token(raw_token)

        refresh_token = RefreshToken(
            token_hash=token_hash,
            user_id=refresh_user.id,
            device_name="Test Device",
            ip_address="192.168.1.1",
            expires_at=datetime.utcnow() + timedelta(days=7)
        )

        db_session.add(refresh_token)
        await db_session.commit()
        await db_session.refresh(refresh_token)

        assert refresh_token.id is not None
        assert refresh_token.token_hash == token_hash
        assert refresh_token.user_id == refresh_user.id
        assert refresh_token.device_name == "Test Device"
        assert refresh_token.ip_address == "192.168.1.1"
        assert refresh_token.revoked_at is None

    @pytest.mark.asyncio
    async def test_create_token_without_device_name(self, db_session: AsyncSession, refresh_user: User):
        """Test creating refresh token without optional device name."""
        raw_token = generate_token()
        token_hash = hash_token(raw_token)

        refresh_token = RefreshToken(
            token_hash=token_hash,
            user_id=refresh_user.id,
            expires_at=datetime.utcnow() + timedelta(days=7)
        )

        db_session.add(refresh_token)
        await db_session.commit()
        await db_session.refresh(refresh_token)

        assert refresh_token.id is not None
        assert refresh_token.device_name is None
        assert refresh_token.ip_address is None

    @pytest.mark.asyncio
    async def test_token_hash_is_unique(self, db_session: AsyncSession, refresh_user: User):
        """Test that token hash must be unique."""
        raw_token = generate_token()
        token_hash = hash_token(raw_token)

        # Create first token
        token1 = RefreshToken(
            token_hash=token_hash,
            user_id=refresh_user.id,
            expires_at=datetime.utcnow() + timedelta(days=7)
        )
        db_session.add(token1)
        await db_session.commit()

        # Try to create second token with same hash
        token2 = RefreshToken(
            token_hash=token_hash,  # Same hash
            user_id=refresh_user.id,
            expires_at=datetime.utcnow() + timedelta(days=7)
        )
        db_session.add(token2)

        # Should raise integrity error
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_token_linked_to_user(self, db_session: AsyncSession, refresh_user: User):
        """Test that refresh token is properly linked to user."""
        raw_token = generate_token()
        token_hash = hash_token(raw_token)

        refresh_token = RefreshToken(
            token_hash=token_hash,
            user_id=refresh_user.id,
            expires_at=datetime.utcnow() + timedelta(days=7)
        )
        db_session.add(refresh_token)
        await db_session.commit()

        # Reload user with refresh_tokens relationship
        result = await db_session.execute(
            select(User).where(User.id == refresh_user.id)
        )
        user = result.scalar_one()

        # Check relationship
        result = await db_session.execute(
            select(RefreshToken).where(RefreshToken.user_id == user.id)
        )
        user_tokens = result.scalars().all()
        assert len(user_tokens) == 1
        assert user_tokens[0].token_hash == token_hash


# ============================================================================
# TOKEN VALIDATION TESTS
# ============================================================================

class TestRefreshTokenValidation:
    """Tests for refresh token validation."""

    @pytest.mark.asyncio
    async def test_validate_valid_token(
        self,
        db_session: AsyncSession,
        valid_refresh_token: tuple[RefreshToken, str]
    ):
        """Test validating a valid refresh token."""
        token_record, raw_token = valid_refresh_token

        # Hash the raw token
        token_hash = hash_token(raw_token)

        # Find token by hash
        result = await db_session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        found_token = result.scalar_one_or_none()

        assert found_token is not None
        assert found_token.id == token_record.id
        assert found_token.revoked_at is None
        assert found_token.expires_at > datetime.utcnow()

    @pytest.mark.asyncio
    async def test_validate_invalid_token(self, db_session: AsyncSession):
        """Test that invalid token hash returns no result."""
        fake_token = "this-is-not-a-valid-token"
        fake_hash = hash_token(fake_token)

        result = await db_session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == fake_hash)
        )
        found_token = result.scalar_one_or_none()

        assert found_token is None

    @pytest.mark.asyncio
    async def test_validate_expired_token(
        self,
        db_session: AsyncSession,
        expired_refresh_token: tuple[RefreshToken, str]
    ):
        """Test that expired token is detected."""
        token_record, raw_token = expired_refresh_token
        token_hash = hash_token(raw_token)

        # Find token
        result = await db_session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        found_token = result.scalar_one_or_none()

        assert found_token is not None
        # Token exists but is expired
        assert found_token.expires_at < datetime.utcnow()

    @pytest.mark.asyncio
    async def test_validate_revoked_token(
        self,
        db_session: AsyncSession,
        revoked_refresh_token: tuple[RefreshToken, str]
    ):
        """Test that revoked token is detected."""
        token_record, raw_token = revoked_refresh_token
        token_hash = hash_token(raw_token)

        # Find token
        result = await db_session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        found_token = result.scalar_one_or_none()

        assert found_token is not None
        # Token exists but is revoked
        assert found_token.revoked_at is not None


# ============================================================================
# TOKEN REVOCATION TESTS
# ============================================================================

class TestRefreshTokenRevocation:
    """Tests for refresh token revocation."""

    @pytest.mark.asyncio
    async def test_revoke_single_token(
        self,
        db_session: AsyncSession,
        valid_refresh_token: tuple[RefreshToken, str]
    ):
        """Test revoking a single refresh token."""
        token_record, _ = valid_refresh_token

        # Token should not be revoked initially
        assert token_record.revoked_at is None

        # Revoke the token
        token_record.revoked_at = datetime.utcnow()
        await db_session.commit()
        await db_session.refresh(token_record)

        # Token should now be revoked
        assert token_record.revoked_at is not None

    @pytest.mark.asyncio
    async def test_revoke_all_user_tokens(
        self,
        db_session: AsyncSession,
        refresh_user: User,
        multiple_refresh_tokens: list[tuple[RefreshToken, str]]
    ):
        """Test revoking all tokens for a user (logout everywhere)."""
        # All tokens should be valid initially
        for token, _ in multiple_refresh_tokens:
            assert token.revoked_at is None

        # Revoke all tokens for user
        now = datetime.utcnow()
        result = await db_session.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == refresh_user.id,
                RefreshToken.revoked_at.is_(None)
            )
        )
        user_tokens = result.scalars().all()

        for token in user_tokens:
            token.revoked_at = now

        await db_session.commit()

        # Verify all tokens are revoked
        result = await db_session.execute(
            select(RefreshToken).where(RefreshToken.user_id == refresh_user.id)
        )
        all_tokens = result.scalars().all()

        for token in all_tokens:
            assert token.revoked_at is not None

    @pytest.mark.asyncio
    async def test_revoked_token_cannot_be_used(
        self,
        db_session: AsyncSession,
        valid_refresh_token: tuple[RefreshToken, str]
    ):
        """Test that a revoked token cannot be used for validation."""
        token_record, raw_token = valid_refresh_token
        token_hash = hash_token(raw_token)

        # Revoke the token
        token_record.revoked_at = datetime.utcnow()
        await db_session.commit()

        # Try to validate the token
        result = await db_session.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None)  # Only non-revoked tokens
            )
        )
        valid_token = result.scalar_one_or_none()

        # Should not find any valid token
        assert valid_token is None

    @pytest.mark.asyncio
    async def test_cascade_delete_on_user_deletion(
        self,
        db_session: AsyncSession,
        refresh_user: User,
        valid_refresh_token: tuple[RefreshToken, str]
    ):
        """Test that refresh tokens are deleted when user is deleted."""
        token_record, _ = valid_refresh_token
        token_id = token_record.id
        user_id = refresh_user.id

        # Delete the user
        await db_session.delete(refresh_user)
        await db_session.commit()

        # Token should be deleted due to cascade
        result = await db_session.execute(
            select(RefreshToken).where(RefreshToken.id == token_id)
        )
        token = result.scalar_one_or_none()

        assert token is None


# ============================================================================
# TOKEN ROTATION TESTS
# ============================================================================

class TestRefreshTokenRotation:
    """Tests for refresh token rotation (issuing new tokens)."""

    @pytest.mark.asyncio
    async def test_rotate_token(
        self,
        db_session: AsyncSession,
        refresh_user: User,
        valid_refresh_token: tuple[RefreshToken, str]
    ):
        """Test rotating a refresh token (revoke old, create new)."""
        old_token, old_raw = valid_refresh_token

        # Simulate token rotation
        # 1. Revoke old token
        old_token.revoked_at = datetime.utcnow()

        # 2. Create new token
        new_raw = generate_token()
        new_hash = hash_token(new_raw)

        new_token = RefreshToken(
            token_hash=new_hash,
            user_id=refresh_user.id,
            device_name=old_token.device_name,
            ip_address=old_token.ip_address,
            expires_at=datetime.utcnow() + timedelta(days=7)
        )
        db_session.add(new_token)
        await db_session.commit()
        await db_session.refresh(new_token)

        # Old token should be revoked
        await db_session.refresh(old_token)
        assert old_token.revoked_at is not None

        # New token should be valid
        assert new_token.revoked_at is None
        assert new_token.expires_at > datetime.utcnow()

    @pytest.mark.asyncio
    async def test_rotation_creates_different_hash(
        self,
        db_session: AsyncSession,
        refresh_user: User,
        valid_refresh_token: tuple[RefreshToken, str]
    ):
        """Test that rotation creates a different token hash."""
        old_token, old_raw = valid_refresh_token
        old_hash = old_token.token_hash

        # Create new token
        new_raw = generate_token()
        new_hash = hash_token(new_raw)

        # Hashes should be different
        assert old_hash != new_hash

        # Raw tokens should be different
        assert old_raw != new_raw

    @pytest.mark.asyncio
    async def test_rotation_preserves_device_info(
        self,
        db_session: AsyncSession,
        refresh_user: User,
        valid_refresh_token: tuple[RefreshToken, str]
    ):
        """Test that rotation preserves device information."""
        old_token, _ = valid_refresh_token
        original_device = old_token.device_name
        original_ip = old_token.ip_address

        # Create rotated token with same device info
        new_raw = generate_token()
        new_hash = hash_token(new_raw)

        new_token = RefreshToken(
            token_hash=new_hash,
            user_id=refresh_user.id,
            device_name=original_device,
            ip_address=original_ip,
            expires_at=datetime.utcnow() + timedelta(days=7)
        )
        db_session.add(new_token)
        await db_session.commit()
        await db_session.refresh(new_token)

        assert new_token.device_name == original_device
        assert new_token.ip_address == original_ip


# ============================================================================
# TOKEN EXPIRATION TESTS
# ============================================================================

class TestRefreshTokenExpiration:
    """Tests for refresh token expiration."""

    @pytest.mark.asyncio
    async def test_token_expires_after_duration(
        self,
        db_session: AsyncSession,
        refresh_user: User
    ):
        """Test that token expires after specified duration."""
        raw_token = generate_token()
        token_hash = hash_token(raw_token)

        # Create token that expires in 1 second
        expires_at = datetime.utcnow() + timedelta(seconds=1)

        refresh_token = RefreshToken(
            token_hash=token_hash,
            user_id=refresh_user.id,
            expires_at=expires_at
        )
        db_session.add(refresh_token)
        await db_session.commit()

        # Token should be valid initially
        assert refresh_token.expires_at > datetime.utcnow()

        # Wait for expiration
        import asyncio
        await asyncio.sleep(1.5)

        # Token should now be expired
        assert refresh_token.expires_at < datetime.utcnow()

    @pytest.mark.asyncio
    async def test_cleanup_expired_tokens(
        self,
        db_session: AsyncSession,
        refresh_user: User,
        expired_refresh_token: tuple[RefreshToken, str],
        valid_refresh_token: tuple[RefreshToken, str]
    ):
        """Test cleaning up expired tokens."""
        expired_token, _ = expired_refresh_token
        valid_token, _ = valid_refresh_token

        # Find and delete expired tokens
        result = await db_session.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == refresh_user.id,
                RefreshToken.expires_at < datetime.utcnow()
            )
        )
        expired_tokens = result.scalars().all()

        for token in expired_tokens:
            await db_session.delete(token)

        await db_session.commit()

        # Only valid token should remain
        result = await db_session.execute(
            select(RefreshToken).where(RefreshToken.user_id == refresh_user.id)
        )
        remaining_tokens = result.scalars().all()

        assert len(remaining_tokens) == 1
        assert remaining_tokens[0].id == valid_token.id

    @pytest.mark.asyncio
    async def test_expired_token_query_filter(
        self,
        db_session: AsyncSession,
        refresh_user: User,
        expired_refresh_token: tuple[RefreshToken, str],
        valid_refresh_token: tuple[RefreshToken, str]
    ):
        """Test filtering out expired tokens in queries."""
        # Query for valid (non-expired, non-revoked) tokens
        result = await db_session.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == refresh_user.id,
                RefreshToken.expires_at > datetime.utcnow(),
                RefreshToken.revoked_at.is_(None)
            )
        )
        valid_tokens = result.scalars().all()

        # Should only find the valid token
        assert len(valid_tokens) == 1

    @pytest.mark.asyncio
    async def test_token_expiration_boundary(
        self,
        db_session: AsyncSession,
        refresh_user: User
    ):
        """Test token at exact expiration boundary."""
        raw_token = generate_token()
        token_hash = hash_token(raw_token)

        # Create token that expires exactly now
        now = datetime.utcnow()

        refresh_token = RefreshToken(
            token_hash=token_hash,
            user_id=refresh_user.id,
            expires_at=now
        )
        db_session.add(refresh_token)
        await db_session.commit()

        # Query with > comparison should not find it
        result = await db_session.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.expires_at > now
            )
        )
        token = result.scalar_one_or_none()

        assert token is None


# ============================================================================
# TOKEN SECURITY TESTS
# ============================================================================

class TestRefreshTokenSecurity:
    """Tests for refresh token security properties."""

    def test_token_is_random(self):
        """Test that generated tokens are random."""
        tokens = [generate_token() for _ in range(100)]

        # All tokens should be unique
        assert len(tokens) == len(set(tokens))

    def test_token_has_sufficient_entropy(self):
        """Test that tokens have sufficient length/entropy."""
        token = generate_token()

        # Token should be at least 32 characters
        assert len(token) >= 32

    def test_hash_is_one_way(self):
        """Test that token hash cannot be reversed to original token."""
        raw_token = generate_token()
        token_hash = hash_token(raw_token)

        # Hash should be different from original
        assert token_hash != raw_token

        # Hash should be consistent
        assert hash_token(raw_token) == token_hash

    def test_different_tokens_produce_different_hashes(self):
        """Test that different tokens produce different hashes."""
        token1 = generate_token()
        token2 = generate_token()

        hash1 = hash_token(token1)
        hash2 = hash_token(token2)

        assert hash1 != hash2

    @pytest.mark.asyncio
    async def test_raw_token_not_stored(
        self,
        db_session: AsyncSession,
        valid_refresh_token: tuple[RefreshToken, str]
    ):
        """Test that raw token is not stored in database."""
        token_record, raw_token = valid_refresh_token

        # The stored hash should not equal the raw token
        assert token_record.token_hash != raw_token

        # But hash of raw token should match stored hash
        assert hash_token(raw_token) == token_record.token_hash


# ============================================================================
# SERVICE FUNCTION TESTS
# ============================================================================

class TestRefreshTokenServiceFunctions:
    """Tests for the auth service refresh token functions."""

    @pytest.mark.asyncio
    async def test_create_refresh_token_service(self, db_session: AsyncSession, admin_user: User):
        """Test creating refresh token via service function."""
        from api.services.auth import create_refresh_token as create_token_service
        from api.services.auth import _hash_token as service_hash

        raw_token = await create_token_service(
            db_session,
            user_id=admin_user.id,
            device_name="Test Browser",
            ip_address="10.0.0.1"
        )

        # Token should be returned
        assert raw_token is not None
        assert len(raw_token) >= 64  # URL-safe base64 encoded

        # Token should exist in database
        result = await db_session.execute(
            select(RefreshToken).where(RefreshToken.user_id == admin_user.id)
        )
        tokens = result.scalars().all()
        assert len(tokens) >= 1

        # Find the token we just created
        found = False
        for token in tokens:
            if token.token_hash == service_hash(raw_token):
                found = True
                assert token.device_name == "Test Browser"
                assert token.ip_address == "10.0.0.1"
                assert token.revoked_at is None
        assert found

    @pytest.mark.asyncio
    async def test_validate_refresh_token_service(self, db_session: AsyncSession, admin_user: User):
        """Test validating refresh token via service function."""
        from api.services.auth import create_refresh_token as create_token_service
        from api.services.auth import validate_refresh_token as validate_token_service

        raw_token = await create_token_service(db_session, user_id=admin_user.id)

        user_id = await validate_token_service(db_session, raw_token)
        assert user_id == admin_user.id

    @pytest.mark.asyncio
    async def test_validate_invalid_token_service(self, db_session: AsyncSession):
        """Test validating invalid token returns None."""
        from api.services.auth import validate_refresh_token as validate_token_service

        user_id = await validate_token_service(db_session, "invalid_token_12345")
        assert user_id is None

    @pytest.mark.asyncio
    async def test_revoke_refresh_token_service(self, db_session: AsyncSession, admin_user: User):
        """Test revoking refresh token via service function."""
        from api.services.auth import create_refresh_token as create_token_service
        from api.services.auth import revoke_refresh_token as revoke_token_service
        from api.services.auth import validate_refresh_token as validate_token_service

        raw_token = await create_token_service(db_session, user_id=admin_user.id)

        # Token should be valid
        assert await validate_token_service(db_session, raw_token) == admin_user.id

        # Revoke token
        result = await revoke_token_service(db_session, raw_token)
        assert result is True

        # Token should no longer be valid
        assert await validate_token_service(db_session, raw_token) is None

    @pytest.mark.asyncio
    async def test_revoke_all_user_tokens_service(self, db_session: AsyncSession, admin_user: User):
        """Test revoking all user tokens via service function."""
        from api.services.auth import create_refresh_token as create_token_service
        from api.services.auth import revoke_all_user_tokens as revoke_all_service
        from api.services.auth import validate_refresh_token as validate_token_service

        # Create multiple tokens
        tokens = []
        for _ in range(3):
            token = await create_token_service(db_session, user_id=admin_user.id)
            tokens.append(token)

        # All should be valid
        for token in tokens:
            assert await validate_token_service(db_session, token) == admin_user.id

        # Revoke all
        count = await revoke_all_service(db_session, admin_user.id)
        assert count == 3

        # All should be invalid
        for token in tokens:
            assert await validate_token_service(db_session, token) is None

    @pytest.mark.asyncio
    async def test_rotate_refresh_token_service(self, db_session: AsyncSession, admin_user: User):
        """Test rotating refresh token via service function."""
        from api.services.auth import create_refresh_token as create_token_service
        from api.services.auth import rotate_refresh_token as rotate_token_service
        from api.services.auth import validate_refresh_token as validate_token_service

        old_token = await create_token_service(db_session, user_id=admin_user.id)

        result = await rotate_token_service(
            db_session,
            old_token=old_token,
            device_name="New Device",
            ip_address="192.168.1.100"
        )

        assert result is not None
        new_token, user_id = result
        assert user_id == admin_user.id
        assert new_token != old_token

        # Old token should be revoked
        assert await validate_token_service(db_session, old_token) is None

        # New token should be valid
        assert await validate_token_service(db_session, new_token) == admin_user.id

    @pytest.mark.asyncio
    async def test_rotate_revoked_token_triggers_security(self, db_session: AsyncSession, admin_user: User):
        """Test that rotating a revoked token revokes ALL user tokens (security)."""
        from api.services.auth import create_refresh_token as create_token_service
        from api.services.auth import rotate_refresh_token as rotate_token_service
        from api.services.auth import revoke_refresh_token as revoke_token_service
        from api.services.auth import validate_refresh_token as validate_token_service

        token1 = await create_token_service(db_session, user_id=admin_user.id)
        token2 = await create_token_service(db_session, user_id=admin_user.id)

        # Revoke token1
        await revoke_token_service(db_session, token1)

        # Try to rotate the already-revoked token1 (simulating attacker)
        result = await rotate_token_service(db_session, token1)
        assert result is None

        # Security: ALL user tokens should be revoked
        assert await validate_token_service(db_session, token2) is None

    @pytest.mark.asyncio
    async def test_rotate_recently_rotated_token_grace_reissues(
        self, db_session: AsyncSession, admin_user: User
    ):
        """Гонка мультивкладок: тот же токен ротируют дважды подряд (в пределах
        grace). Второй раз НЕ считаем кражей — выдаём новый токен и НЕ убиваем
        остальные сессии. Иначе юзера выкидывало из системы каждые ~15 мин."""
        from api.services.auth import create_refresh_token as create_token_service
        from api.services.auth import rotate_refresh_token as rotate_token_service
        from api.services.auth import validate_refresh_token as validate_token_service

        other = await create_token_service(db_session, user_id=admin_user.id)  # вторая сессия
        token1 = await create_token_service(db_session, user_id=admin_user.id)

        # Первая вкладка ротировала token1
        first = await rotate_token_service(db_session, token1)
        assert first is not None

        # Вторая вкладка предъявляет ТОТ ЖЕ token1 (уже ротирован секунду назад)
        second = await rotate_token_service(db_session, token1)
        assert second is not None, "в пределах grace-окна должен выдаться новый токен, а не None"
        new_token2, uid = second
        assert uid == admin_user.id
        assert await validate_token_service(db_session, new_token2) == admin_user.id

        # ГЛАВНОЕ: остальные сессии НЕ убиты (нет revoke_all)
        assert await validate_token_service(db_session, other) == admin_user.id

    @pytest.mark.asyncio
    async def test_rotate_stale_rotated_token_denied_without_nuke(
        self, db_session: AsyncSession, admin_user: User
    ):
        """Ротированный токен предъявлен СИЛЬНО позже grace (отставший клиент):
        отказываем именно ему (None), но остальные сессии живы (без revoke_all)."""
        from sqlalchemy import select
        from api.models.database import RefreshToken
        from api.services.auth import create_refresh_token as create_token_service
        from api.services.auth import rotate_refresh_token as rotate_token_service
        from api.services.auth import validate_refresh_token as validate_token_service
        from api.services.auth import _hash_token

        other = await create_token_service(db_session, user_id=admin_user.id)
        token1 = await create_token_service(db_session, user_id=admin_user.id)
        assert await rotate_token_service(db_session, token1) is not None

        # Отматываем rotated_at далеко назад (за пределы grace)
        rec = (await db_session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == _hash_token(token1))
        )).scalar_one()
        rec.rotated_at = datetime.utcnow() - timedelta(hours=2)
        await db_session.commit()

        result = await rotate_token_service(db_session, token1)
        assert result is None  # отставшему отказали
        # но остальные сессии не тронуты
        assert await validate_token_service(db_session, other) == admin_user.id

    @pytest.mark.asyncio
    async def test_get_user_sessions_service(self, db_session: AsyncSession, admin_user: User):
        """Test getting user sessions via service function."""
        from api.services.auth import create_refresh_token as create_token_service
        from api.services.auth import get_user_sessions as get_sessions_service

        # Create sessions with different devices
        await create_token_service(db_session, user_id=admin_user.id, device_name="Chrome")
        await create_token_service(db_session, user_id=admin_user.id, device_name="Firefox")

        sessions = await get_sessions_service(db_session, admin_user.id)
        assert len(sessions) == 2

        devices = {s.device_name for s in sessions}
        assert "Chrome" in devices
        assert "Firefox" in devices

    @pytest.mark.asyncio
    async def test_short_lived_access_token_creation(self, admin_user: User):
        """Test creating short-lived access token."""
        from api.services.auth import create_short_lived_access_token
        from jose import jwt
        from api.config import get_settings

        settings = get_settings()
        token = create_short_lived_access_token(
            user_id=admin_user.id,
            token_version=admin_user.token_version
        )

        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        assert payload["sub"] == str(admin_user.id)

        # Should expire in approximately 15 minutes
        exp = datetime.utcfromtimestamp(payload["exp"])
        diff = (exp - datetime.utcnow()).total_seconds()
        assert 800 < diff < 1000  # 13-17 minutes


# ============================================================================
# ENDPOINT TESTS
# ============================================================================

class TestRefreshTokenEndpoints:
    """Tests for refresh token HTTP endpoints."""

    @pytest.mark.asyncio
    async def test_login_returns_refresh_token_cookie(self, client, admin_user: User):
        """Test that login endpoint sets refresh token cookie."""
        response = await client.post("/api/auth/login", json={
            "email": "admin@test.com",
            "password": "Admin123"
        })

        assert response.status_code == 200
        assert "refresh_token" in response.cookies

    @pytest.mark.asyncio
    async def test_login_returns_access_token_cookie(self, client, admin_user: User):
        """Test that login endpoint sets access token cookie."""
        response = await client.post("/api/auth/login", json={
            "email": "admin@test.com",
            "password": "Admin123"
        })

        assert response.status_code == 200
        assert "access_token" in response.cookies

    @pytest.mark.asyncio
    async def test_refresh_endpoint_success(self, client, admin_user: User, db_session: AsyncSession):
        """Test successful token refresh."""
        # Login to get tokens
        login_response = await client.post("/api/auth/login", json={
            "email": "admin@test.com",
            "password": "Admin123"
        })
        refresh_token = login_response.cookies.get("refresh_token")

        # Refresh
        response = await client.post(
            "/api/auth/refresh",
            cookies={"refresh_token": refresh_token}
        )

        assert response.status_code == 200
        assert response.json()["message"] == "Token refreshed successfully"
        assert "access_token" in response.cookies
        assert "refresh_token" in response.cookies

    @pytest.mark.asyncio
    async def test_refresh_rotates_token(self, client, admin_user: User, db_session: AsyncSession):
        """Test that refresh endpoint rotates the refresh token."""
        # Login
        login_response = await client.post("/api/auth/login", json={
            "email": "admin@test.com",
            "password": "Admin123"
        })
        old_refresh = login_response.cookies.get("refresh_token")

        # Refresh
        refresh_response = await client.post(
            "/api/auth/refresh",
            cookies={"refresh_token": old_refresh}
        )
        new_refresh = refresh_response.cookies.get("refresh_token")

        # Tokens should be different
        assert old_refresh != new_refresh

        # Повторный refresh тем же (только что ротированным) токеном в пределах
        # grace-окна — доброкачественная гонка мультивкладок: НЕ 401 и НЕ нук всех
        # сессий, а выдача нового токена. Раньше здесь был 401 + revoke_all, из-за
        # чего юзера постоянно выкидывало из системы (обратная связь 2026-08-05).
        second_refresh = await client.post(
            "/api/auth/refresh",
            cookies={"refresh_token": old_refresh}
        )
        assert second_refresh.status_code == 200
        reissued = second_refresh.cookies.get("refresh_token")
        assert reissued and reissued != old_refresh

    @pytest.mark.asyncio
    async def test_refresh_without_token_fails(self, client):
        """Test that refresh without token returns 401."""
        response = await client.post("/api/auth/refresh")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_with_invalid_token_fails(self, client):
        """Test that refresh with invalid token returns 401."""
        response = await client.post(
            "/api/auth/refresh",
            cookies={"refresh_token": "invalid_token"}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_logout_revokes_token(self, client, admin_user: User, db_session: AsyncSession):
        """Test that logout revokes the refresh token."""
        from api.services.auth import validate_refresh_token as validate_token_service

        # Login
        login_response = await client.post("/api/auth/login", json={
            "email": "admin@test.com",
            "password": "Admin123"
        })
        refresh_token = login_response.cookies.get("refresh_token")

        # Logout
        await client.post(
            "/api/auth/logout",
            cookies={"refresh_token": refresh_token}
        )

        # Token should be revoked
        assert await validate_token_service(db_session, refresh_token) is None

    @pytest.mark.asyncio
    async def test_logout_all_revokes_all_tokens(
        self, client, admin_user: User, admin_token, get_auth_headers, db_session: AsyncSession
    ):
        """Test that logout-all revokes all refresh tokens."""
        from api.services.auth import validate_refresh_token as validate_token_service

        # Create multiple sessions
        tokens = []
        for _ in range(3):
            response = await client.post("/api/auth/login", json={
                "email": "admin@test.com",
                "password": "Admin123"
            })
            tokens.append(response.cookies.get("refresh_token"))

        # Logout all
        response = await client.post(
            "/api/auth/logout-all",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        assert response.json()["revoked_count"] == 3

        # All tokens should be revoked
        for token in tokens:
            assert await validate_token_service(db_session, token) is None

    @pytest.mark.asyncio
    async def test_sessions_endpoint_returns_sessions(
        self, client, admin_user: User, admin_token, get_auth_headers, db_session: AsyncSession
    ):
        """Test that sessions endpoint returns active sessions."""
        from api.services.auth import create_refresh_token as create_token_service

        # Create sessions
        await create_token_service(db_session, user_id=admin_user.id, device_name="Chrome")
        await create_token_service(db_session, user_id=admin_user.id, device_name="Firefox")

        # Get sessions
        response = await client.get(
            "/api/auth/sessions",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["sessions"]) == 2

    @pytest.mark.asyncio
    async def test_sessions_requires_auth(self, client):
        """Test that sessions endpoint requires authentication."""
        response = await client.get("/api/auth/sessions")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_inactive_user_cannot_refresh(self, client, admin_user: User, db_session: AsyncSession):
        """Test that inactive user cannot use refresh token."""
        # Login
        login_response = await client.post("/api/auth/login", json={
            "email": "admin@test.com",
            "password": "Admin123"
        })
        refresh_token = login_response.cookies.get("refresh_token")

        # Deactivate user
        admin_user.is_active = False
        await db_session.commit()

        # Try to refresh
        response = await client.post(
            "/api/auth/refresh",
            cookies={"refresh_token": refresh_token}
        )

        assert response.status_code == 401
        assert "inactive" in response.json()["detail"].lower()
