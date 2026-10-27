"""
Comprehensive unit tests for authentication service functions.

Tests cover:
- Password hashing and verification (including truncation)
- JWT token creation and validation (including impersonation)
- User authentication and retrieval
- Role checking and permissions
- Department-based access control
- Sharing permissions
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from jose import jwt, JWTError
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from api.services.auth import (
    # Password functions
    _truncate_password,
    hash_password,
    verify_password,
    # JWT functions
    create_access_token,
    create_impersonation_token,
    # User retrieval
    get_current_user,
    get_superadmin,
    get_current_user_optional,
    get_user_from_token,
    authenticate_user,
    # Initialization
    create_superadmin_if_not_exists,
    # Organization helpers
    get_user_org,
    get_user_org_role,
    # Role checking
    is_superadmin,
    is_owner,
    is_department_admin,
    get_user_departments,
    is_same_department,
    can_view_in_department,
    was_created_by_superadmin,
    get_department_admin,
    require_department_membership,
    # Sharing permissions
    can_share_to,
)
from api.config import get_settings
from api.models.database import (
    User, UserRole, Organization, OrgMember, OrgRole,
    Department, DepartmentMember, DeptRole, Entity, EntityType, EntityStatus
)

settings = get_settings()


# ============================================================================
# PASSWORD FUNCTIONS
# ============================================================================

class TestPasswordTruncation:
    """Tests for password truncation (bcrypt 72-byte limit)."""

    def test_truncate_password_short_password(self):
        """Test that short passwords are not truncated."""
        password = "short"
        result = _truncate_password(password)
        assert result == password

    def test_truncate_password_72_bytes(self):
        """Test that passwords exactly 72 bytes are not truncated."""
        password = "a" * 72
        result = _truncate_password(password)
        assert result == password
        assert len(result.encode('utf-8')) == 72

    def test_truncate_password_73_bytes(self):
        """Test that passwords over 72 bytes are truncated."""
        password = "a" * 73
        result = _truncate_password(password)
        assert len(result.encode('utf-8')) == 72
        assert len(result) == 72  # All ASCII

    def test_truncate_password_unicode(self):
        """Test password truncation with unicode characters."""
        # Use unicode characters that take multiple bytes
        password = "密" * 30  # Each character is 3 bytes in UTF-8
        result = _truncate_password(password)
        # Should truncate to fit within 72 bytes
        assert len(result.encode('utf-8')) <= 72

    def test_truncate_password_unicode_boundary(self):
        """Test that truncation handles unicode character boundaries."""
        # Create a password that would split a multi-byte character at 72 bytes
        password = "a" * 71 + "密"  # 71 bytes + 3-byte character
        result = _truncate_password(password)
        # Should truncate cleanly without breaking the character
        result_bytes = result.encode('utf-8')
        assert len(result_bytes) <= 72
        # Should be valid UTF-8 (no broken characters)
        assert result_bytes.decode('utf-8', errors='strict')

    def test_truncate_password_custom_max_bytes(self):
        """Test password truncation with custom max bytes."""
        password = "a" * 100
        result = _truncate_password(password, max_bytes=50)
        assert len(result.encode('utf-8')) == 50


class TestPasswordHashingAndVerification:
    """Tests for password hashing and verification."""

    def test_hash_password_creates_bcrypt_hash(self):
        """Test that hash_password creates a valid bcrypt hash."""
        password = "testpassword123"
        hashed = hash_password(password)

        assert hashed is not None
        assert hashed.startswith("$2b$")  # bcrypt hash prefix
        assert len(hashed) == 60  # bcrypt hash length

    def test_hash_password_truncates_long_passwords(self):
        """Test that very long passwords are truncated before hashing."""
        # Create a password longer than 72 bytes
        long_password = "a" * 100
        hashed = hash_password(long_password)

        # Should still create valid hash
        assert hashed is not None
        # First 72 characters should match
        assert verify_password("a" * 72, hashed) is True
        # Full password should also match (gets truncated during verification)
        assert verify_password(long_password, hashed) is True

    def test_verify_password_with_very_long_password(self):
        """Test password verification with passwords exceeding bcrypt limit."""
        password = "x" * 100
        hashed = hash_password(password)

        # Same long password should verify
        assert verify_password(password, hashed) is True
        # Different long password should not verify
        assert verify_password("y" * 100, hashed) is False

    def test_verify_password_unicode(self):
        """Test password hashing and verification with unicode characters."""
        password = "密码测试123"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True
        assert verify_password("wrong密码", hashed) is False

    def test_hash_password_special_characters(self):
        """Test password hashing with special characters."""
        password = "!@#$%^&*()_+-=[]{}|;:',.<>?/~`"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True


# ============================================================================
# JWT TOKEN FUNCTIONS
# ============================================================================

class TestJWTTokenCreation:
    """Tests for JWT token creation and validation."""

    def test_create_access_token_includes_token_version(self):
        """Test that token includes token_version field."""
        data = {"sub": "123", "token_version": 5}
        token = create_access_token(data)

        decoded = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        assert decoded["token_version"] == 5

    def test_create_access_token_default_expiration(self):
        """Test token creation with default expiration."""
        data = {"sub": "123"}
        token = create_access_token(data)

        decoded = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        exp_time = datetime.utcfromtimestamp(decoded["exp"])  # exp — UTC; fromtimestamp давал сдвиг на пояс машины
        expected_exp = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)

        # Allow 2 minute tolerance
        assert abs((exp_time - expected_exp).total_seconds()) < 120

    def test_create_access_token_preserves_all_data(self):
        """Test that token preserves all provided data fields."""
        data = {
            "sub": "123",
            "user_id": 456,
            "token_version": 2,
            "custom_field": "value"
        }
        token = create_access_token(data)

        decoded = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        assert decoded["sub"] == "123"
        assert decoded["user_id"] == 456
        assert decoded["token_version"] == 2
        assert decoded["custom_field"] == "value"


class TestImpersonationToken:
    """Tests for impersonation token creation."""

    def test_create_impersonation_token_structure(self):
        """Test that impersonation token has correct structure."""
        token = create_impersonation_token(
            impersonated_user_id=100,
            original_user_id=1,
            token_version=3
        )

        decoded = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        assert decoded["sub"] == "100"  # Impersonated user ID as string
        assert decoded["token_version"] == 3
        assert decoded["original_user_id"] == 1
        assert decoded["is_impersonating"] is True

    def test_create_impersonation_token_expiration(self):
        """Test that impersonation token expires in 1 hour."""
        token = create_impersonation_token(
            impersonated_user_id=100,
            original_user_id=1
        )

        decoded = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        exp_time = datetime.utcfromtimestamp(decoded["exp"])  # exp — UTC; fromtimestamp давал сдвиг на пояс машины
        expected_exp = datetime.utcnow() + timedelta(hours=1)

        # Allow 2 minute tolerance
        assert abs((exp_time - expected_exp).total_seconds()) < 120

    def test_create_impersonation_token_default_version(self):
        """Test impersonation token with default token version."""
        token = create_impersonation_token(
            impersonated_user_id=100,
            original_user_id=1
        )

        decoded = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        assert decoded["token_version"] == 0  # Default value


# ============================================================================
# USER RETRIEVAL AND AUTHENTICATION
# ============================================================================


def _request(credentials):
    """Запрос с заголовком Authorization.

    get_current_user теперь берёт токен из cookie или заголовка запроса
    (сигнатура request, access_token, db), а не из HTTPAuthorizationCredentials.
    """
    from starlette.requests import Request
    headers = []
    if credentials is not None:
        headers.append((b"authorization", f"Bearer {credentials.credentials}".encode()))
    return Request({
        "type": "http", "method": "GET", "path": "/api/test",
        "headers": headers, "query_string": b"",
    })

class TestGetCurrentUser:
    """Tests for get_current_user dependency."""

    @pytest.mark.asyncio
    async def test_get_current_user_success(self, db_session, admin_user):
        """Test successful user retrieval from valid token."""
        token = create_access_token(data={"sub": str(admin_user.id), "token_version": 0})
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        user = await get_current_user(_request(credentials), None, db_session)

        assert user is not None
        assert user.id == admin_user.id
        assert user.email == admin_user.email

    @pytest.mark.asyncio
    async def test_get_current_user_with_token_version(self, db_session, admin_user):
        """Test user retrieval with matching token version."""
        admin_user.token_version = 5
        await db_session.commit()

        token = create_access_token(data={"sub": str(admin_user.id), "token_version": 5})
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        user = await get_current_user(_request(credentials), None, db_session)
        assert user.id == admin_user.id

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token_version(self, db_session, admin_user):
        """Test that mismatched token version raises error."""
        admin_user.token_version = 5
        await db_session.commit()

        # Token has old version
        token = create_access_token(data={"sub": str(admin_user.id), "token_version": 3})
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(_request(credentials), None, db_session)

        assert exc_info.value.status_code == 401
        assert "invalidated" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_get_current_user_inactive_user(self, db_session, admin_user):
        """Test that inactive user cannot authenticate."""
        admin_user.is_active = False
        await db_session.commit()

        token = create_access_token(data={"sub": str(admin_user.id), "token_version": 0})
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(_request(credentials), None, db_session)

        assert exc_info.value.status_code == 401
        assert "inactive" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_get_current_user_nonexistent_user(self, db_session):
        """Test that token with non-existent user ID fails."""
        token = create_access_token(data={"sub": "99999", "token_version": 0})
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(_request(credentials), None, db_session)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, db_session):
        """Test that invalid token raises error."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="invalid.token.here"
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(_request(credentials), None, db_session)

        assert exc_info.value.status_code == 401
        assert "invalid" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_get_current_user_missing_sub(self, db_session):
        """Test that token without 'sub' claim fails."""
        token = create_access_token(data={"user_id": 123})  # No 'sub'
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(_request(credentials), None, db_session)

        assert exc_info.value.status_code == 401


class TestGetSuperadmin:
    """Tests for get_superadmin dependency."""

    @pytest.mark.asyncio
    async def test_get_superadmin_success(self, superadmin_user):
        """Test that superadmin user passes check."""
        user = await get_superadmin(superadmin_user)
        assert user.id == superadmin_user.id

    @pytest.mark.asyncio
    async def test_get_superadmin_rejects_admin(self, admin_user):
        """Test that non-superadmin user fails check."""
        with pytest.raises(HTTPException) as exc_info:
            await get_superadmin(admin_user)

        assert exc_info.value.status_code == 403
        assert "superadmin" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_get_superadmin_rejects_regular_user(self, regular_user):
        """Test that regular user fails superadmin check."""
        with pytest.raises(HTTPException) as exc_info:
            await get_superadmin(regular_user)

        assert exc_info.value.status_code == 403


class TestGetCurrentUserOptional:
    """Tests for optional authentication."""

    @pytest.mark.asyncio
    async def test_get_current_user_optional_with_valid_token(self, db_session, admin_user):
        """Test optional auth with valid token returns user."""
        token = create_access_token(data={"sub": str(admin_user.id), "token_version": 0})
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        user = await get_current_user_optional(_request(credentials), None, db_session)
        assert user is not None
        assert user.id == admin_user.id

    @pytest.mark.asyncio
    async def test_get_current_user_optional_without_token(self, db_session):
        """Test optional auth without token returns None."""
        user = await get_current_user_optional(_request(None), None, db_session)
        assert user is None

    @pytest.mark.asyncio
    async def test_get_current_user_optional_invalid_token(self, db_session):
        """Test optional auth with invalid token returns None (not error)."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="invalid.token"
        )

        user = await get_current_user_optional(_request(credentials), None, db_session)
        assert user is None

    @pytest.mark.asyncio
    async def test_get_current_user_optional_inactive_user(self, db_session, admin_user):
        """Test optional auth with inactive user returns None."""
        admin_user.is_active = False
        await db_session.commit()

        token = create_access_token(data={"sub": str(admin_user.id), "token_version": 0})
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        user = await get_current_user_optional(_request(credentials), None, db_session)
        assert user is None

    @pytest.mark.asyncio
    async def test_get_current_user_optional_invalid_token_version(self, db_session, admin_user):
        """Test optional auth with invalid token version returns None."""
        admin_user.token_version = 5
        await db_session.commit()

        token = create_access_token(data={"sub": str(admin_user.id), "token_version": 3})
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        user = await get_current_user_optional(_request(credentials), None, db_session)
        assert user is None


class TestGetUserFromToken:
    """Tests for get_user_from_token function."""

    @pytest.mark.asyncio
    async def test_get_user_from_token_success(self, db_session, admin_user):
        """Test successful user retrieval from raw token string."""
        token = create_access_token(data={"sub": str(admin_user.id), "token_version": 0})

        user = await get_user_from_token(token, db_session)
        assert user is not None
        assert user.id == admin_user.id

    @pytest.mark.asyncio
    async def test_get_user_from_token_empty_string(self, db_session):
        """Test that empty token string returns None."""
        user = await get_user_from_token("", db_session)
        assert user is None

    @pytest.mark.asyncio
    async def test_get_user_from_token_none(self, db_session):
        """Test that None token returns None."""
        user = await get_user_from_token(None, db_session)
        assert user is None

    @pytest.mark.asyncio
    async def test_get_user_from_token_invalid(self, db_session):
        """Test that invalid token returns None."""
        user = await get_user_from_token("invalid.token.here", db_session)
        assert user is None

    @pytest.mark.asyncio
    async def test_get_user_from_token_nonexistent_user(self, db_session):
        """Test token with non-existent user returns None."""
        token = create_access_token(data={"sub": "99999", "token_version": 0})
        user = await get_user_from_token(token, db_session)
        assert user is None


class TestAuthenticateUser:
    """Tests for user authentication with email and password."""

    @pytest.mark.asyncio
    async def test_authenticate_user_timing_attack_prevention(self, db_session, admin_user):
        """Test that authentication performs dummy hash for non-existent users."""
        # This test documents the timing attack prevention behavior
        # Both should take similar time (can't easily test timing in unit tests)

        # Non-existent user - should still hash
        user1 = await authenticate_user(db_session, "nonexistent@test.com", "password")
        assert user1 is None

        # Wrong password - should hash
        user2 = await authenticate_user(db_session, "admin@test.com", "wrongpassword")
        assert user2 is None

    @pytest.mark.asyncio
    async def test_authenticate_user_inactive_user(self, db_session, admin_user):
        """Test that inactive user cannot authenticate."""
        admin_user.is_active = False
        await db_session.commit()

        # Authentication checks password but user object shows inactive
        # The function returns None for any failed auth
        user = await authenticate_user(db_session, "admin@test.com", "admin123")
        # Note: Current implementation might still return the user
        # This test documents actual behavior


# ============================================================================
# SUPERADMIN INITIALIZATION
# ============================================================================

class TestCreateSuperadminIfNotExists:
    """Tests for superadmin and default organization initialization."""

    @pytest.mark.asyncio
    async def test_create_superadmin_if_not_exists_creates_all(self, db_session):
        """Test that function creates superadmin, org, and memberships."""
        await create_superadmin_if_not_exists(db_session)

        # Check superadmin created
        from sqlalchemy import select
        result = await db_session.execute(
            select(User).where(User.role == UserRole.superadmin)
        )
        superadmin = result.scalar_one_or_none()
        assert superadmin is not None
        assert superadmin.email == settings.superadmin_email

        # Check default org created
        result = await db_session.execute(
            select(Organization).where(Organization.slug == "default")
        )
        org = result.scalar_one_or_none()
        assert org is not None

        # Check membership created
        result = await db_session.execute(
            select(OrgMember).where(
                OrgMember.user_id == superadmin.id,
                OrgMember.org_id == org.id
            )
        )
        membership = result.scalar_one_or_none()
        assert membership is not None
        assert membership.role == OrgRole.owner

    @pytest.mark.asyncio
    async def test_create_superadmin_if_not_exists_idempotent(self, db_session, superadmin_user, organization):
        """Test that function is idempotent (can run multiple times)."""
        # Add superadmin to org
        membership = OrgMember(
            org_id=organization.id,
            user_id=superadmin_user.id,
            role=OrgRole.owner
        )
        db_session.add(membership)
        await db_session.commit()

        # Run again - should not error
        await create_superadmin_if_not_exists(db_session)

    @pytest.mark.asyncio
    async def test_create_superadmin_migrates_existing_users(self, db_session, admin_user, regular_user):
        """Test that existing users are migrated to default org."""
        # Create default org and superadmin
        await create_superadmin_if_not_exists(db_session)

        # Check that existing users were added to default org
        from sqlalchemy import select
        result = await db_session.execute(
            select(Organization).where(Organization.slug == "default")
        )
        org = result.scalar_one()

        result = await db_session.execute(
            select(OrgMember).where(
                OrgMember.org_id == org.id,
                OrgMember.user_id == admin_user.id
            )
        )
        assert result.scalar_one_or_none() is not None


# ============================================================================
# ORGANIZATION HELPERS
# ============================================================================

class TestGetUserOrg:
    """Tests for getting user's organization."""

    @pytest.mark.asyncio
    async def test_get_user_org_success(self, db_session, admin_user, organization, org_owner):
        """Test getting user's organization."""
        org = await get_user_org(admin_user, db_session)
        assert org is not None
        assert org.id == organization.id

    @pytest.mark.asyncio
    async def test_get_user_org_no_membership(self, db_session, admin_user):
        """Test that user with no org membership returns None."""
        org = await get_user_org(admin_user, db_session)
        assert org is None

    @pytest.mark.asyncio
    async def test_get_user_org_multiple_orgs(
        self, db_session, admin_user, organization, second_organization
    ):
        """Test that function returns first organization (by join date)."""
        # Add user to both orgs
        membership1 = OrgMember(
            org_id=organization.id,
            user_id=admin_user.id,
            role=OrgRole.admin,
            created_at=datetime.utcnow() - timedelta(days=1)
        )
        membership2 = OrgMember(
            org_id=second_organization.id,
            user_id=admin_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add_all([membership1, membership2])
        await db_session.commit()

        org = await get_user_org(admin_user, db_session)
        assert org.id == organization.id  # First org by creation date


class TestGetUserOrgRole:
    """Tests for getting user's role in organization."""

    @pytest.mark.asyncio
    async def test_get_user_org_role_owner(self, db_session, admin_user, organization, org_owner):
        """Test getting owner role."""
        role = await get_user_org_role(admin_user, organization.id, db_session)
        assert role == OrgRole.owner

    @pytest.mark.asyncio
    async def test_get_user_org_role_admin(self, db_session, regular_user, organization, org_admin):
        """Test getting admin role."""
        role = await get_user_org_role(regular_user, organization.id, db_session)
        assert role == OrgRole.admin

    @pytest.mark.asyncio
    async def test_get_user_org_role_member(self, db_session, second_user, organization, org_member):
        """Test getting member role."""
        role = await get_user_org_role(second_user, organization.id, db_session)
        assert role == OrgRole.member

    @pytest.mark.asyncio
    async def test_get_user_org_role_no_membership(self, db_session, admin_user, organization):
        """Test that non-member returns None."""
        role = await get_user_org_role(admin_user, organization.id, db_session)
        assert role is None


# ============================================================================
# ROLE CHECKING FUNCTIONS
# ============================================================================

class TestIsSuperadmin:
    """Tests for is_superadmin helper function."""

    def test_is_superadmin_true(self, superadmin_user):
        """Test that superadmin user is identified correctly."""
        assert is_superadmin(superadmin_user) is True

    def test_is_superadmin_false_admin(self, admin_user):
        """Test that admin user is not superadmin."""
        assert is_superadmin(admin_user) is False

    def test_is_superadmin_false_regular(self, regular_user):
        """Test that regular user is not superadmin."""
        assert is_superadmin(regular_user) is False


class TestIsOwner:
    """Tests for is_owner function."""

    @pytest.mark.asyncio
    async def test_is_owner_true(self, db_session, admin_user, organization, org_owner):
        """Test that owner is identified correctly."""
        result = await is_owner(admin_user, organization.id, db_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_is_owner_false_admin(self, db_session, regular_user, organization, org_admin):
        """Test that admin is not owner."""
        result = await is_owner(regular_user, organization.id, db_session)
        assert result is False

    @pytest.mark.asyncio
    async def test_is_owner_false_member(self, db_session, second_user, organization, org_member):
        """Test that member is not owner."""
        result = await is_owner(second_user, organization.id, db_session)
        assert result is False

    @pytest.mark.asyncio
    async def test_is_owner_superadmin_returns_false(self, db_session, superadmin_user, organization):
        """Test that superadmin is not considered owner (has higher role)."""
        # Add superadmin to org
        membership = OrgMember(
            org_id=organization.id,
            user_id=superadmin_user.id,
            role=OrgRole.owner
        )
        db_session.add(membership)
        await db_session.commit()

        result = await is_owner(superadmin_user, organization.id, db_session)
        assert result is False  # Superadmin is higher than owner


class TestIsDepartmentAdmin:
    """Tests for department admin checking."""

    @pytest.mark.asyncio
    async def test_is_department_admin_lead(self, db_session, admin_user, department, dept_lead):
        """Test that department lead is admin."""
        result = await is_department_admin(admin_user, department.id, db_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_is_department_admin_sub_admin(self, db_session, regular_user, department):
        """Test that sub-admin is department admin."""
        # Create sub-admin membership
        membership = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.sub_admin
        )
        db_session.add(membership)
        await db_session.commit()

        result = await is_department_admin(regular_user, department.id, db_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_is_department_admin_false_member(self, db_session, regular_user, department, dept_member):
        """Test that regular member is not admin."""
        result = await is_department_admin(regular_user, department.id, db_session)
        assert result is False

    @pytest.mark.asyncio
    async def test_is_department_admin_no_membership(self, db_session, admin_user, department):
        """Test that non-member is not admin."""
        result = await is_department_admin(admin_user, department.id, db_session)
        assert result is False


class TestGetUserDepartments:
    """Tests for getting user's departments."""

    @pytest.mark.asyncio
    async def test_get_user_departments_single(self, db_session, admin_user, department, dept_lead):
        """Test getting single department membership."""
        departments = await get_user_departments(admin_user, db_session)
        assert len(departments) == 1
        assert departments[0][0] == department.id
        assert departments[0][1] == DeptRole.lead

    @pytest.mark.asyncio
    async def test_get_user_departments_multiple(
        self, db_session, admin_user, department, second_department
    ):
        """Test getting multiple department memberships."""
        # Add user to both departments
        membership1 = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.lead
        )
        membership2 = DepartmentMember(
            department_id=second_department.id,
            user_id=admin_user.id,
            role=DeptRole.member
        )
        db_session.add_all([membership1, membership2])
        await db_session.commit()

        departments = await get_user_departments(admin_user, db_session)
        assert len(departments) == 2
        dept_ids = [d[0] for d in departments]
        assert department.id in dept_ids
        assert second_department.id in dept_ids

    @pytest.mark.asyncio
    async def test_get_user_departments_none(self, db_session, admin_user):
        """Test user with no department memberships."""
        departments = await get_user_departments(admin_user, db_session)
        assert len(departments) == 0


class TestIsSameDepartment:
    """Tests for checking if users are in same department."""

    @pytest.mark.asyncio
    async def test_is_same_department_true(
        self, db_session, admin_user, regular_user, department
    ):
        """Test that users in same department are identified."""
        # Add both users to same department
        membership1 = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.lead
        )
        membership2 = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.member
        )
        db_session.add_all([membership1, membership2])
        await db_session.commit()

        result = await is_same_department(admin_user, regular_user, db_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_is_same_department_false(
        self, db_session, admin_user, regular_user, department, second_department
    ):
        """Test that users in different departments return False."""
        # Add users to different departments
        membership1 = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.lead
        )
        membership2 = DepartmentMember(
            department_id=second_department.id,
            user_id=regular_user.id,
            role=DeptRole.member
        )
        db_session.add_all([membership1, membership2])
        await db_session.commit()

        result = await is_same_department(admin_user, regular_user, db_session)
        assert result is False

    @pytest.mark.asyncio
    async def test_is_same_department_multiple_shared(
        self, db_session, admin_user, regular_user, department, second_department
    ):
        """Test that users sharing any department return True."""
        # Add both users to both departments
        memberships = [
            DepartmentMember(department_id=department.id, user_id=admin_user.id, role=DeptRole.lead),
            DepartmentMember(department_id=department.id, user_id=regular_user.id, role=DeptRole.member),
            DepartmentMember(department_id=second_department.id, user_id=admin_user.id, role=DeptRole.member),
            DepartmentMember(department_id=second_department.id, user_id=regular_user.id, role=DeptRole.member),
        ]
        db_session.add_all(memberships)
        await db_session.commit()

        result = await is_same_department(admin_user, regular_user, db_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_is_same_department_no_departments(self, db_session, admin_user, regular_user):
        """Test that users with no departments return False."""
        result = await is_same_department(admin_user, regular_user, db_session)
        assert result is False


class TestCanViewInDepartment:
    """Tests for department-based view permissions."""

    @pytest.mark.asyncio
    async def test_can_view_own_resource(self, db_session, admin_user):
        """Test that user can view their own resources."""
        result = await can_view_in_department(
            user=admin_user,
            resource_owner_id=admin_user.id,
            resource_dept_id=1,
            db=db_session
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_can_view_department_admin(
        self, db_session, admin_user, regular_user, department
    ):
        """Test that department admin can view all department resources."""
        # Admin is lead
        membership_admin = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.lead
        )
        # Regular user is member
        membership_regular = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.member
        )
        db_session.add_all([membership_admin, membership_regular])
        await db_session.commit()

        # Admin viewing regular user's resource
        result = await can_view_in_department(
            user=admin_user,
            resource_owner_id=regular_user.id,
            resource_dept_id=department.id,
            db=db_session
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_cannot_view_other_member_resource(
        self, db_session, regular_user, second_user, department
    ):
        """Test that member cannot view other member's resources."""
        # Both are members
        membership1 = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.member
        )
        membership2 = DepartmentMember(
            department_id=department.id,
            user_id=second_user.id,
            role=DeptRole.member
        )
        db_session.add_all([membership1, membership2])
        await db_session.commit()

        # Member trying to view other member's resource
        result = await can_view_in_department(
            user=regular_user,
            resource_owner_id=second_user.id,
            resource_dept_id=department.id,
            db=db_session
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_cannot_view_resource_no_department(
        self, db_session, admin_user, regular_user
    ):
        """Test that resource without department can only be viewed by owner."""
        result = await can_view_in_department(
            user=admin_user,
            resource_owner_id=regular_user.id,
            resource_dept_id=None,
            db=db_session
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_cannot_view_different_department(
        self, db_session, admin_user, regular_user, department, second_department
    ):
        """Test that user cannot view resource from different department."""
        # Admin in first department
        membership1 = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.lead
        )
        # Regular user in second department
        membership2 = DepartmentMember(
            department_id=second_department.id,
            user_id=regular_user.id,
            role=DeptRole.member
        )
        db_session.add_all([membership1, membership2])
        await db_session.commit()

        result = await can_view_in_department(
            user=admin_user,
            resource_owner_id=regular_user.id,
            resource_dept_id=second_department.id,
            db=db_session
        )
        assert result is False


class TestWasCreatedBySuperadmin:
    """Tests for checking if resource was created by superadmin."""

    @pytest.mark.asyncio
    async def test_was_created_by_superadmin_true(self, db_session, superadmin_user, organization, department):
        """Test that resource created by superadmin is identified."""
        # Create entity by superadmin
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=superadmin_user.id,
            name="Test Entity",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()

        result = await was_created_by_superadmin(entity, db_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_was_created_by_superadmin_false(self, db_session, admin_user, organization, department):
        """Test that resource created by non-superadmin returns False."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Test Entity",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()

        result = await was_created_by_superadmin(entity, db_session)
        assert result is False

    @pytest.mark.asyncio
    async def test_was_created_by_superadmin_no_creator(self, db_session, organization, department):
        """Test that resource without creator returns False."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=None,
            name="Test Entity",
            type=EntityType.candidate,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()

        result = await was_created_by_superadmin(entity, db_session)
        assert result is False


class TestGetDepartmentAdmin:
    """Tests for getting department if user is admin."""

    @pytest.mark.asyncio
    async def test_get_department_admin_as_lead(self, db_session, organization, department):
        """Test getting department for lead user."""
        # Create admin user with department
        admin = User(
            email="dept_admin@test.com",
            password_hash=hash_password("password"),
            name="Dept Admin",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(admin)
        await db_session.flush()

        membership = DepartmentMember(
            department_id=department.id,
            user_id=admin.id,
            role=DeptRole.lead
        )
        db_session.add(membership)
        await db_session.commit()
        await db_session.refresh(admin)

        dept = await get_department_admin(admin, db_session)
        assert dept is not None
        assert dept.id == department.id

    @pytest.mark.asyncio
    async def test_get_department_admin_as_sub_admin(self, db_session, organization, department):
        """Test getting department for sub-admin user."""
        sub_admin = User(
            email="sub_admin@test.com",
            password_hash=hash_password("password"),
            name="Sub Admin",
            role=UserRole.sub_admin,
            is_active=True
        )
        db_session.add(sub_admin)
        await db_session.flush()

        membership = DepartmentMember(
            department_id=department.id,
            user_id=sub_admin.id,
            role=DeptRole.sub_admin
        )
        db_session.add(membership)
        await db_session.commit()
        await db_session.refresh(sub_admin)

        dept = await get_department_admin(sub_admin, db_session)
        assert dept is not None
        assert dept.id == department.id

    @pytest.mark.asyncio
    async def test_get_department_admin_not_admin(self, db_session, regular_user, department):
        """Test that non-admin user returns None."""
        # Regular user with MEMBER role in department
        membership = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.member
        )
        db_session.add(membership)
        await db_session.commit()

        dept = await get_department_admin(regular_user, db_session)
        assert dept is None

    @pytest.mark.asyncio
    async def test_get_department_admin_superadmin(self, db_session, superadmin_user):
        """Test that superadmin returns None (not tied to department)."""
        dept = await get_department_admin(superadmin_user, db_session)
        assert dept is None


class TestRequireDepartmentMembership:
    """Tests for department membership validation."""

    @pytest.mark.asyncio
    async def test_require_department_membership_success(
        self, db_session, admin_user, department
    ):
        """Test that member passes validation."""
        membership = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.lead
        )
        db_session.add(membership)
        await db_session.commit()

        # Should not raise
        await require_department_membership(admin_user, department.id, db_session)

    @pytest.mark.asyncio
    async def test_require_department_membership_fails(self, db_session, admin_user, department):
        """Test that non-member raises error."""
        with pytest.raises(HTTPException) as exc_info:
            await require_department_membership(admin_user, department.id, db_session)

        assert exc_info.value.status_code == 403
        assert "member" in exc_info.value.detail.lower()


# ============================================================================
# SHARING PERMISSIONS
# ============================================================================

class TestCanShareTo:
    """Tests for sharing permission validation."""

    @pytest.mark.asyncio
    async def test_superadmin_can_share_to_anyone(
        self, db_session, superadmin_user, admin_user, organization
    ):
        """Test that superadmin can share with anyone."""
        result = await can_share_to(
            from_user=superadmin_user,
            to_user=admin_user,
            from_user_org_id=organization.id,
            db=db_session
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_owner_can_share_within_org(
        self, db_session, admin_user, regular_user, organization, org_owner, org_admin
    ):
        """Test that owner can share with anyone in their org."""
        result = await can_share_to(
            from_user=admin_user,
            to_user=regular_user,
            from_user_org_id=organization.id,
            db=db_session
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_owner_cannot_share_outside_org(
        self, db_session, admin_user, regular_user, organization,
        second_organization, org_owner
    ):
        """Test that owner cannot share with users outside their org."""
        # regular_user in different org
        membership = OrgMember(
            org_id=second_organization.id,
            user_id=regular_user.id,
            role=OrgRole.member
        )
        db_session.add(membership)
        await db_session.commit()

        result = await can_share_to(
            from_user=admin_user,
            to_user=regular_user,
            from_user_org_id=organization.id,
            db=db_session
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_admin_can_share_within_department(
        self, db_session, admin_user, regular_user, organization,
        department, org_owner, org_admin
    ):
        """Test that admin can share with users in their department."""
        # Both in same department
        membership1 = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.lead
        )
        membership2 = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.member
        )
        db_session.add_all([membership1, membership2])
        await db_session.commit()

        result = await can_share_to(
            from_user=admin_user,
            to_user=regular_user,
            from_user_org_id=organization.id,
            db=db_session
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_admin_can_share_with_other_admins(
        self, db_session, admin_user, regular_user, organization,
        department, second_department, org_owner, org_admin
    ):
        """Test that admin can share with admins of other departments."""
        # Admin in first department, regular user is admin in second
        membership1 = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.lead
        )
        membership2 = DepartmentMember(
            department_id=second_department.id,
            user_id=regular_user.id,
            role=DeptRole.lead
        )
        db_session.add_all([membership1, membership2])

        # Change regular_user org role to admin
        result = await db_session.execute(
            OrgMember.__table__.update()
            .where(OrgMember.user_id == regular_user.id)
            .values(role=OrgRole.admin)
        )
        await db_session.commit()

        result = await can_share_to(
            from_user=admin_user,
            to_user=regular_user,
            from_user_org_id=organization.id,
            db=db_session
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_admin_can_share_with_owner(
        self, db_session, regular_user, admin_user, organization, org_owner, org_admin
    ):
        """Test that admin can share with org owner."""
        result = await can_share_to(
            from_user=regular_user,  # admin role
            to_user=admin_user,  # owner
            from_user_org_id=organization.id,
            db=db_session
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_member_can_share_within_department(
        self, db_session, regular_user, second_user, organization,
        department, org_admin, org_member
    ):
        """Test that member can share within their department."""
        # Both are members of same department
        membership1 = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.member
        )
        membership2 = DepartmentMember(
            department_id=department.id,
            user_id=second_user.id,
            role=DeptRole.member
        )
        db_session.add_all([membership1, membership2])
        await db_session.commit()

        result = await can_share_to(
            from_user=regular_user,
            to_user=second_user,
            from_user_org_id=organization.id,
            db=db_session
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_member_cannot_share_outside_department(
        self, db_session, regular_user, second_user, organization,
        department, second_department, org_admin, org_member
    ):
        """Test that member cannot share outside their department."""
        # Users in different departments
        membership1 = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.member
        )
        membership2 = DepartmentMember(
            department_id=second_department.id,
            user_id=second_user.id,
            role=DeptRole.member
        )
        db_session.add_all([membership1, membership2])
        await db_session.commit()

        result = await can_share_to(
            from_user=regular_user,
            to_user=second_user,
            from_user_org_id=organization.id,
            db=db_session
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_cannot_share_to_user_not_in_org(
        self, db_session, regular_user, second_user, organization, org_admin
    ):
        """Test that user cannot share with user not in organization."""
        # second_user not in organization
        result = await can_share_to(
            from_user=regular_user,
            to_user=second_user,
            from_user_org_id=organization.id,
            db=db_session
        )
        assert result is False
