"""
Tests for Feature Access Control Service

Tests cover:
1. can_access_feature for superadmin (always true)
2. can_access_feature for owner (always true)
3. can_access_feature for regular user (checks db)
4. Default features (chats, contacts) always accessible
5. Restricted features (candidate_database) require enablement
6. Department-specific settings override org-wide
7. set_department_feature
8. get_org_features
9. bulk_set_department_features
"""
import pytest
import pytest_asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import (
    User, UserRole, Organization, OrgMember, OrgRole,
    Department, DepartmentMember, DeptRole, DepartmentFeature
)
from api.services.features import (
    can_access_feature, get_user_features, set_department_feature,
    get_org_features, delete_department_feature, bulk_set_department_features,
    DEFAULT_FEATURES, RESTRICTED_FEATURES, ALL_FEATURES
)
from api.services.auth import hash_password


class TestFeatureConstants:
    """Tests for feature constants."""

    def test_default_features_include_expected(self):
        """Default features should include chats, contacts, calls, dashboard."""
        assert "chats" in DEFAULT_FEATURES
        assert "contacts" in DEFAULT_FEATURES
        assert "calls" in DEFAULT_FEATURES
        assert "dashboard" in DEFAULT_FEATURES

    def test_restricted_features_include_expected(self):
        """Restricted features should include candidate_database, ai_analysis."""
        assert "candidate_database" in RESTRICTED_FEATURES
        assert "ai_analysis" in RESTRICTED_FEATURES

    def test_all_features_is_union(self):
        """ALL_FEATURES should be union of default and restricted."""
        for feature in DEFAULT_FEATURES:
            assert feature in ALL_FEATURES
        for feature in RESTRICTED_FEATURES:
            assert feature in ALL_FEATURES


class TestCanAccessFeatureSuperadmin:
    """Tests for superadmin access - always has access."""

    @pytest_asyncio.fixture
    async def setup_superadmin(self, db_session: AsyncSession):
        """Create superadmin and test organization."""
        superadmin = User(
            email="superadmin@test.com",
            password_hash=hash_password("password"),
            name="Super Admin",
            role=UserRole.superadmin,
            is_active=True
        )
        db_session.add(superadmin)

        org = Organization(name="Test Org", slug="test-org")
        db_session.add(org)
        await db_session.flush()

        return {"superadmin": superadmin, "org": org}

    @pytest.mark.asyncio
    async def test_superadmin_can_access_default_feature(
        self, db_session: AsyncSession, setup_superadmin
    ):
        """Superadmin can access default features."""
        data = setup_superadmin

        can_access = await can_access_feature(
            db_session,
            data["superadmin"].id,
            data["org"].id,
            "chats"
        )
        assert can_access is True

    @pytest.mark.asyncio
    async def test_superadmin_can_access_restricted_feature(
        self, db_session: AsyncSession, setup_superadmin
    ):
        """Superadmin can access restricted features without enablement."""
        data = setup_superadmin

        can_access = await can_access_feature(
            db_session,
            data["superadmin"].id,
            data["org"].id,
            "candidate_database"
        )
        assert can_access is True

    @pytest.mark.asyncio
    async def test_superadmin_can_access_any_feature(
        self, db_session: AsyncSession, setup_superadmin
    ):
        """Superadmin can access any feature."""
        data = setup_superadmin

        for feature in ALL_FEATURES:
            can_access = await can_access_feature(
                db_session,
                data["superadmin"].id,
                data["org"].id,
                feature
            )
            assert can_access is True, f"Superadmin should access {feature}"


class TestCanAccessFeatureOwner:
    """Tests for owner access - always has access."""

    @pytest_asyncio.fixture
    async def setup_owner(self, db_session: AsyncSession):
        """Create org owner."""
        org = Organization(name="Test Org", slug="test-org")
        db_session.add(org)
        await db_session.flush()

        owner = User(
            email="owner@test.com",
            password_hash=hash_password("password"),
            name="Owner",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(owner)
        await db_session.flush()

        owner_membership = OrgMember(
            org_id=org.id,
            user_id=owner.id,
            role=OrgRole.owner
        )
        db_session.add(owner_membership)
        await db_session.flush()

        return {"owner": owner, "org": org}

    @pytest.mark.asyncio
    async def test_owner_can_access_default_feature(
        self, db_session: AsyncSession, setup_owner
    ):
        """Owner can access default features."""
        data = setup_owner

        can_access = await can_access_feature(
            db_session,
            data["owner"].id,
            data["org"].id,
            "contacts"
        )
        assert can_access is True

    @pytest.mark.asyncio
    async def test_owner_can_access_restricted_feature(
        self, db_session: AsyncSession, setup_owner
    ):
        """Owner can access restricted features without enablement."""
        data = setup_owner

        can_access = await can_access_feature(
            db_session,
            data["owner"].id,
            data["org"].id,
            "candidate_database"
        )
        assert can_access is True

    @pytest.mark.asyncio
    async def test_owner_can_access_any_feature(
        self, db_session: AsyncSession, setup_owner
    ):
        """Owner can access any feature."""
        data = setup_owner

        for feature in ALL_FEATURES:
            can_access = await can_access_feature(
                db_session,
                data["owner"].id,
                data["org"].id,
                feature
            )
            assert can_access is True, f"Owner should access {feature}"


class TestCanAccessFeatureRegularUser:
    """Tests for regular user access - checks database settings."""

    @pytest_asyncio.fixture
    async def setup_regular_user(self, db_session: AsyncSession):
        """Create regular user with org membership."""
        org = Organization(name="Test Org", slug="test-org")
        db_session.add(org)
        await db_session.flush()

        dept = Department(name="HR Department", org_id=org.id)
        db_session.add(dept)
        await db_session.flush()

        user = User(
            email="user@test.com",
            password_hash=hash_password("password"),
            name="Regular User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(user)
        await db_session.flush()

        org_member = OrgMember(
            org_id=org.id,
            user_id=user.id,
            role=OrgRole.member
        )
        db_session.add(org_member)

        dept_member = DepartmentMember(
            department_id=dept.id,
            user_id=user.id,
            role=DeptRole.member
        )
        db_session.add(dept_member)
        await db_session.flush()

        return {"user": user, "org": org, "dept": dept}

    @pytest.mark.asyncio
    async def test_regular_user_can_access_default_features(
        self, db_session: AsyncSession, setup_regular_user
    ):
        """Regular user can always access default features."""
        data = setup_regular_user

        for feature in DEFAULT_FEATURES:
            can_access = await can_access_feature(
                db_session,
                data["user"].id,
                data["org"].id,
                feature
            )
            assert can_access is True, f"User should access default feature {feature}"

    @pytest.mark.asyncio
    async def test_regular_user_cannot_access_restricted_by_default(
        self, db_session: AsyncSession, setup_regular_user
    ):
        """Regular user cannot access restricted features by default."""
        data = setup_regular_user

        can_access = await can_access_feature(
            db_session,
            data["user"].id,
            data["org"].id,
            "candidate_database"
        )
        assert can_access is False

    @pytest.mark.asyncio
    async def test_regular_user_can_access_enabled_restricted_feature(
        self, db_session: AsyncSession, setup_regular_user
    ):
        """Regular user can access restricted feature when enabled org-wide."""
        data = setup_regular_user

        # Enable vacancies org-wide
        feature_setting = DepartmentFeature(
            org_id=data["org"].id,
            department_id=None,  # org-wide
            feature_name="candidate_database",
            enabled=True
        )
        db_session.add(feature_setting)
        await db_session.flush()

        can_access = await can_access_feature(
            db_session,
            data["user"].id,
            data["org"].id,
            "candidate_database"
        )
        assert can_access is True

    @pytest.mark.asyncio
    async def test_nonexistent_user_cannot_access(
        self, db_session: AsyncSession, setup_regular_user
    ):
        """Nonexistent user cannot access any feature."""
        data = setup_regular_user

        can_access = await can_access_feature(
            db_session,
            99999,  # Nonexistent user ID
            data["org"].id,
            "chats"
        )
        assert can_access is False


class TestDefaultFeaturesAccess:
    """Tests for default features - always accessible."""

    @pytest_asyncio.fixture
    async def setup_member(self, db_session: AsyncSession):
        """Create org member."""
        org = Organization(name="Test Org", slug="test-org")
        db_session.add(org)
        await db_session.flush()

        user = User(
            email="member@test.com",
            password_hash=hash_password("password"),
            name="Member",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(user)
        await db_session.flush()

        org_member = OrgMember(
            org_id=org.id,
            user_id=user.id,
            role=OrgRole.member
        )
        db_session.add(org_member)
        await db_session.flush()

        return {"user": user, "org": org}

    @pytest.mark.asyncio
    async def test_chats_always_accessible(
        self, db_session: AsyncSession, setup_member
    ):
        """Chats feature is always accessible."""
        data = setup_member

        can_access = await can_access_feature(
            db_session,
            data["user"].id,
            data["org"].id,
            "chats"
        )
        assert can_access is True

    @pytest.mark.asyncio
    async def test_contacts_always_accessible(
        self, db_session: AsyncSession, setup_member
    ):
        """Contacts feature is always accessible."""
        data = setup_member

        can_access = await can_access_feature(
            db_session,
            data["user"].id,
            data["org"].id,
            "contacts"
        )
        assert can_access is True

    @pytest.mark.asyncio
    async def test_calls_always_accessible(
        self, db_session: AsyncSession, setup_member
    ):
        """Calls feature is always accessible."""
        data = setup_member

        can_access = await can_access_feature(
            db_session,
            data["user"].id,
            data["org"].id,
            "calls"
        )
        assert can_access is True

    @pytest.mark.asyncio
    async def test_dashboard_always_accessible(
        self, db_session: AsyncSession, setup_member
    ):
        """Dashboard feature is always accessible."""
        data = setup_member

        can_access = await can_access_feature(
            db_session,
            data["user"].id,
            data["org"].id,
            "dashboard"
        )
        assert can_access is True


class TestRestrictedFeaturesAccess:
    """Tests for restricted features - require enablement."""

    @pytest_asyncio.fixture
    async def setup_user_with_dept(self, db_session: AsyncSession):
        """Create user with department membership."""
        org = Organization(name="Test Org", slug="test-org")
        db_session.add(org)
        await db_session.flush()

        dept = Department(name="HR Department", org_id=org.id)
        db_session.add(dept)
        await db_session.flush()

        user = User(
            email="user@test.com",
            password_hash=hash_password("password"),
            name="User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(user)
        await db_session.flush()

        org_member = OrgMember(
            org_id=org.id,
            user_id=user.id,
            role=OrgRole.member
        )
        db_session.add(org_member)

        dept_member = DepartmentMember(
            department_id=dept.id,
            user_id=user.id,
            role=DeptRole.member
        )
        db_session.add(dept_member)
        await db_session.flush()

        return {"user": user, "org": org, "dept": dept}

    @pytest.mark.asyncio
    async def test_vacancies_disabled_by_default(
        self, db_session: AsyncSession, setup_user_with_dept
    ):
        """Vacancies feature is disabled by default."""
        data = setup_user_with_dept

        can_access = await can_access_feature(
            db_session,
            data["user"].id,
            data["org"].id,
            "candidate_database"
        )
        assert can_access is False

    @pytest.mark.asyncio
    async def test_ai_analysis_disabled_by_default(
        self, db_session: AsyncSession, setup_user_with_dept
    ):
        """AI analysis feature is disabled by default."""
        data = setup_user_with_dept

        can_access = await can_access_feature(
            db_session,
            data["user"].id,
            data["org"].id,
            "ai_analysis"
        )
        assert can_access is False

    @pytest.mark.asyncio
    async def test_vacancies_enabled_org_wide(
        self, db_session: AsyncSession, setup_user_with_dept
    ):
        """Vacancies accessible when enabled org-wide."""
        data = setup_user_with_dept

        # Enable org-wide
        feature = DepartmentFeature(
            org_id=data["org"].id,
            department_id=None,
            feature_name="candidate_database",
            enabled=True
        )
        db_session.add(feature)
        await db_session.flush()

        can_access = await can_access_feature(
            db_session,
            data["user"].id,
            data["org"].id,
            "candidate_database"
        )
        assert can_access is True

    @pytest.mark.asyncio
    async def test_vacancies_disabled_org_wide(
        self, db_session: AsyncSession, setup_user_with_dept
    ):
        """Vacancies not accessible when disabled org-wide."""
        data = setup_user_with_dept

        # Disable org-wide
        feature = DepartmentFeature(
            org_id=data["org"].id,
            department_id=None,
            feature_name="candidate_database",
            enabled=False
        )
        db_session.add(feature)
        await db_session.flush()

        can_access = await can_access_feature(
            db_session,
            data["user"].id,
            data["org"].id,
            "candidate_database"
        )
        assert can_access is False


class TestDepartmentSpecificSettings:
    """Tests for department-specific settings overriding org-wide."""

    @pytest_asyncio.fixture
    async def setup_multi_dept(self, db_session: AsyncSession):
        """Create user in multiple departments."""
        org = Organization(name="Test Org", slug="test-org")
        db_session.add(org)
        await db_session.flush()

        dept1 = Department(name="Department 1", org_id=org.id)
        dept2 = Department(name="Department 2", org_id=org.id)
        db_session.add_all([dept1, dept2])
        await db_session.flush()

        user = User(
            email="user@test.com",
            password_hash=hash_password("password"),
            name="User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(user)
        await db_session.flush()

        org_member = OrgMember(
            org_id=org.id,
            user_id=user.id,
            role=OrgRole.member
        )
        db_session.add(org_member)

        # User is member of dept1 only
        dept_member = DepartmentMember(
            department_id=dept1.id,
            user_id=user.id,
            role=DeptRole.member
        )
        db_session.add(dept_member)
        await db_session.flush()

        return {"user": user, "org": org, "dept1": dept1, "dept2": dept2}

    @pytest.mark.asyncio
    async def test_dept_enabled_overrides_org_disabled(
        self, db_session: AsyncSession, setup_multi_dept
    ):
        """Department enabled setting overrides org-wide disabled."""
        data = setup_multi_dept

        # Disable org-wide
        org_feature = DepartmentFeature(
            org_id=data["org"].id,
            department_id=None,
            feature_name="candidate_database",
            enabled=False
        )
        db_session.add(org_feature)

        # Enable for dept1
        dept_feature = DepartmentFeature(
            org_id=data["org"].id,
            department_id=data["dept1"].id,
            feature_name="candidate_database",
            enabled=True
        )
        db_session.add(dept_feature)
        await db_session.flush()

        can_access = await can_access_feature(
            db_session,
            data["user"].id,
            data["org"].id,
            "candidate_database"
        )
        assert can_access is True

    @pytest.mark.asyncio
    async def test_dept_disabled_overrides_org_enabled(
        self, db_session: AsyncSession, setup_multi_dept
    ):
        """Department disabled setting overrides org-wide enabled."""
        data = setup_multi_dept

        # Enable org-wide
        org_feature = DepartmentFeature(
            org_id=data["org"].id,
            department_id=None,
            feature_name="candidate_database",
            enabled=True
        )
        db_session.add(org_feature)

        # Disable for dept1
        dept_feature = DepartmentFeature(
            org_id=data["org"].id,
            department_id=data["dept1"].id,
            feature_name="candidate_database",
            enabled=False
        )
        db_session.add(dept_feature)
        await db_session.flush()

        can_access = await can_access_feature(
            db_session,
            data["user"].id,
            data["org"].id,
            "candidate_database"
        )
        assert can_access is False

    @pytest.mark.asyncio
    async def test_specific_dept_id_check(
        self, db_session: AsyncSession, setup_multi_dept
    ):
        """Check access for specific department ID."""
        data = setup_multi_dept

        # Enable for dept1 only
        dept1_feature = DepartmentFeature(
            org_id=data["org"].id,
            department_id=data["dept1"].id,
            feature_name="candidate_database",
            enabled=True
        )
        db_session.add(dept1_feature)

        # Disable for dept2
        dept2_feature = DepartmentFeature(
            org_id=data["org"].id,
            department_id=data["dept2"].id,
            feature_name="candidate_database",
            enabled=False
        )
        db_session.add(dept2_feature)
        await db_session.flush()

        # Check with specific dept1 - should be enabled
        can_access_dept1 = await can_access_feature(
            db_session,
            data["user"].id,
            data["org"].id,
            "candidate_database",
            department_id=data["dept1"].id
        )
        assert can_access_dept1 is True

        # Check with specific dept2 - should be disabled
        can_access_dept2 = await can_access_feature(
            db_session,
            data["user"].id,
            data["org"].id,
            "candidate_database",
            department_id=data["dept2"].id
        )
        assert can_access_dept2 is False

    @pytest.mark.asyncio
    async def test_fallback_to_org_wide_when_no_dept_setting(
        self, db_session: AsyncSession, setup_multi_dept
    ):
        """Falls back to org-wide when no department-specific setting."""
        data = setup_multi_dept

        # Only set org-wide, no department setting
        org_feature = DepartmentFeature(
            org_id=data["org"].id,
            department_id=None,
            feature_name="candidate_database",
            enabled=True
        )
        db_session.add(org_feature)
        await db_session.flush()

        can_access = await can_access_feature(
            db_session,
            data["user"].id,
            data["org"].id,
            "candidate_database"
        )
        assert can_access is True


class TestSetDepartmentFeature:
    """Tests for set_department_feature function."""

    @pytest_asyncio.fixture
    async def setup_org_dept(self, db_session: AsyncSession):
        """Create org and department."""
        org = Organization(name="Test Org", slug="test-org")
        db_session.add(org)
        await db_session.flush()

        dept = Department(name="Test Dept", org_id=org.id)
        db_session.add(dept)
        await db_session.flush()

        return {"org": org, "dept": dept}

    @pytest.mark.asyncio
    async def test_set_org_wide_feature(
        self, db_session: AsyncSession, setup_org_dept
    ):
        """Set org-wide feature setting."""
        data = setup_org_dept

        result = await set_department_feature(
            db_session,
            data["org"].id,
            "candidate_database",
            True,
            department_id=None
        )

        assert result.org_id == data["org"].id
        assert result.department_id is None
        assert result.feature_name == "candidate_database"
        assert result.enabled is True

    @pytest.mark.asyncio
    async def test_set_department_specific_feature(
        self, db_session: AsyncSession, setup_org_dept
    ):
        """Set department-specific feature setting."""
        data = setup_org_dept

        result = await set_department_feature(
            db_session,
            data["org"].id,
            "candidate_database",
            True,
            department_id=data["dept"].id
        )

        assert result.org_id == data["org"].id
        assert result.department_id == data["dept"].id
        assert result.feature_name == "candidate_database"
        assert result.enabled is True

    @pytest.mark.asyncio
    async def test_update_existing_feature_setting(
        self, db_session: AsyncSession, setup_org_dept
    ):
        """Update existing feature setting."""
        data = setup_org_dept

        # Create initial setting
        await set_department_feature(
            db_session,
            data["org"].id,
            "candidate_database",
            True,
            department_id=None
        )

        # Update to disabled
        result = await set_department_feature(
            db_session,
            data["org"].id,
            "candidate_database",
            False,
            department_id=None
        )

        assert result.enabled is False

    @pytest.mark.asyncio
    async def test_invalid_feature_name_raises_error(
        self, db_session: AsyncSession, setup_org_dept
    ):
        """Invalid feature name raises ValueError."""
        data = setup_org_dept

        with pytest.raises(ValueError, match="Invalid feature name"):
            await set_department_feature(
                db_session,
                data["org"].id,
                "invalid_feature",
                True
            )

    @pytest.mark.asyncio
    async def test_set_default_feature(
        self, db_session: AsyncSession, setup_org_dept
    ):
        """Can set default features (even though always accessible)."""
        data = setup_org_dept

        result = await set_department_feature(
            db_session,
            data["org"].id,
            "chats",
            True,
            department_id=None
        )

        assert result.feature_name == "chats"
        assert result.enabled is True


class TestGetOrgFeatures:
    """Tests for get_org_features function."""

    @pytest_asyncio.fixture
    async def setup_org_with_features(self, db_session: AsyncSession):
        """Create org with multiple feature settings."""
        org = Organization(name="Test Org", slug="test-org")
        db_session.add(org)
        await db_session.flush()

        dept1 = Department(name="Dept 1", org_id=org.id)
        dept2 = Department(name="Dept 2", org_id=org.id)
        db_session.add_all([dept1, dept2])
        await db_session.flush()

        # Add feature settings
        features = [
            DepartmentFeature(
                org_id=org.id,
                department_id=None,
                feature_name="candidate_database",
                enabled=True
            ),
            DepartmentFeature(
                org_id=org.id,
                department_id=dept1.id,
                feature_name="candidate_database",
                enabled=False
            ),
            DepartmentFeature(
                org_id=org.id,
                department_id=dept2.id,
                feature_name="ai_analysis",
                enabled=True
            ),
        ]
        db_session.add_all(features)
        await db_session.flush()

        return {"org": org, "dept1": dept1, "dept2": dept2}

    @pytest.mark.asyncio
    async def test_get_all_org_features(
        self, db_session: AsyncSession, setup_org_with_features
    ):
        """Get all feature settings for organization."""
        data = setup_org_with_features

        features = await get_org_features(db_session, data["org"].id)

        assert len(features) == 3
        feature_names = [f["feature_name"] for f in features]
        assert "candidate_database" in feature_names
        assert "ai_analysis" in feature_names

    @pytest.mark.asyncio
    async def test_features_include_department_name(
        self, db_session: AsyncSession, setup_org_with_features
    ):
        """Features include department name when applicable."""
        data = setup_org_with_features

        features = await get_org_features(db_session, data["org"].id)

        dept_features = [f for f in features if f["department_id"] is not None]
        for f in dept_features:
            assert f["department_name"] is not None

    @pytest.mark.asyncio
    async def test_org_wide_features_have_null_dept(
        self, db_session: AsyncSession, setup_org_with_features
    ):
        """Org-wide features have null department_id and name."""
        data = setup_org_with_features

        features = await get_org_features(db_session, data["org"].id)

        org_wide = [f for f in features if f["department_id"] is None]
        assert len(org_wide) >= 1
        for f in org_wide:
            assert f["department_name"] is None

    @pytest.mark.asyncio
    async def test_empty_org_returns_empty_list(
        self, db_session: AsyncSession
    ):
        """Org with no features returns empty list."""
        org = Organization(name="Empty Org", slug="empty-org")
        db_session.add(org)
        await db_session.flush()

        features = await get_org_features(db_session, org.id)

        assert features == []


class TestDeleteDepartmentFeature:
    """Tests for delete_department_feature function."""

    @pytest_asyncio.fixture
    async def setup_feature_to_delete(self, db_session: AsyncSession):
        """Create feature setting to delete."""
        org = Organization(name="Test Org", slug="test-org")
        db_session.add(org)
        await db_session.flush()

        feature = DepartmentFeature(
            org_id=org.id,
            department_id=None,
            feature_name="candidate_database",
            enabled=True
        )
        db_session.add(feature)
        await db_session.flush()

        return {"org": org, "feature": feature}

    @pytest.mark.asyncio
    async def test_delete_existing_feature(
        self, db_session: AsyncSession, setup_feature_to_delete
    ):
        """Delete existing feature setting."""
        data = setup_feature_to_delete

        result = await delete_department_feature(
            db_session,
            data["feature"].id,
            data["org"].id
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_delete_nonexistent_feature_returns_false(
        self, db_session: AsyncSession, setup_feature_to_delete
    ):
        """Deleting nonexistent feature returns False."""
        data = setup_feature_to_delete

        result = await delete_department_feature(
            db_session,
            99999,
            data["org"].id
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_wrong_org_returns_false(
        self, db_session: AsyncSession, setup_feature_to_delete
    ):
        """Deleting feature from wrong org returns False."""
        data = setup_feature_to_delete

        # Create another org
        other_org = Organization(name="Other Org", slug="other-org")
        db_session.add(other_org)
        await db_session.flush()

        result = await delete_department_feature(
            db_session,
            data["feature"].id,
            other_org.id
        )

        assert result is False


class TestBulkSetDepartmentFeatures:
    """Tests for bulk_set_department_features function."""

    @pytest_asyncio.fixture
    async def setup_bulk_depts(self, db_session: AsyncSession):
        """Create org with multiple departments."""
        org = Organization(name="Test Org", slug="test-org")
        db_session.add(org)
        await db_session.flush()

        depts = []
        for i in range(3):
            dept = Department(name=f"Dept {i+1}", org_id=org.id)
            db_session.add(dept)
            depts.append(dept)
        await db_session.flush()

        return {"org": org, "depts": depts}

    @pytest.mark.asyncio
    async def test_bulk_set_for_multiple_departments(
        self, db_session: AsyncSession, setup_bulk_depts
    ):
        """Set feature for multiple departments at once."""
        data = setup_bulk_depts
        dept_ids = [d.id for d in data["depts"]]

        results = await bulk_set_department_features(
            db_session,
            data["org"].id,
            "candidate_database",
            True,
            department_ids=dept_ids
        )

        assert len(results) == 3
        for r in results:
            assert r.feature_name == "candidate_database"
            assert r.enabled is True
            assert r.department_id in dept_ids

    @pytest.mark.asyncio
    async def test_bulk_set_org_wide_only(
        self, db_session: AsyncSession, setup_bulk_depts
    ):
        """Set org-wide feature when no department_ids provided."""
        data = setup_bulk_depts

        results = await bulk_set_department_features(
            db_session,
            data["org"].id,
            "candidate_database",
            True,
            department_ids=None
        )

        assert len(results) == 1
        assert results[0].department_id is None
        assert results[0].enabled is True

    @pytest.mark.asyncio
    async def test_bulk_disable_feature(
        self, db_session: AsyncSession, setup_bulk_depts
    ):
        """Bulk disable feature for departments."""
        data = setup_bulk_depts
        dept_ids = [data["depts"][0].id, data["depts"][1].id]

        results = await bulk_set_department_features(
            db_session,
            data["org"].id,
            "candidate_database",
            False,
            department_ids=dept_ids
        )

        assert len(results) == 2
        for r in results:
            assert r.enabled is False


class TestGetUserFeatures:
    """Tests for get_user_features function."""

    @pytest_asyncio.fixture
    async def setup_user_features(self, db_session: AsyncSession):
        """Create user with feature settings."""
        org = Organization(name="Test Org", slug="test-org")
        db_session.add(org)
        await db_session.flush()

        user = User(
            email="user@test.com",
            password_hash=hash_password("password"),
            name="User",
            role=UserRole.admin,
            is_active=True
        )
        db_session.add(user)
        await db_session.flush()

        org_member = OrgMember(
            org_id=org.id,
            user_id=user.id,
            role=OrgRole.member
        )
        db_session.add(org_member)
        await db_session.flush()

        return {"user": user, "org": org}

    @pytest.mark.asyncio
    async def test_get_default_features_only(
        self, db_session: AsyncSession, setup_user_features
    ):
        """Get only default features when no restricted enabled."""
        data = setup_user_features

        features = await get_user_features(
            db_session,
            data["user"].id,
            data["org"].id
        )

        assert "chats" in features
        assert "contacts" in features
        assert "calls" in features
        assert "dashboard" in features
        assert "candidate_database" not in features

    @pytest.mark.asyncio
    async def test_get_features_includes_enabled_restricted(
        self, db_session: AsyncSession, setup_user_features
    ):
        """Get features includes enabled restricted features."""
        data = setup_user_features

        # Enable vacancies
        feature = DepartmentFeature(
            org_id=data["org"].id,
            department_id=None,
            feature_name="candidate_database",
            enabled=True
        )
        db_session.add(feature)
        await db_session.flush()

        features = await get_user_features(
            db_session,
            data["user"].id,
            data["org"].id
        )

        assert "candidate_database" in features

    @pytest.mark.asyncio
    async def test_superadmin_gets_all_features(
        self, db_session: AsyncSession, setup_user_features
    ):
        """Superadmin gets all features."""
        data = setup_user_features

        # Create superadmin
        superadmin = User(
            email="super@test.com",
            password_hash=hash_password("password"),
            name="Super",
            role=UserRole.superadmin,
            is_active=True
        )
        db_session.add(superadmin)
        await db_session.flush()

        features = await get_user_features(
            db_session,
            superadmin.id,
            data["org"].id
        )

        for f in ALL_FEATURES:
            assert f in features
