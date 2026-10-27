"""
Tests for GET /api/admin/me/features endpoint.

This endpoint returns the list of features available to the current user
based on their organization and department settings.
"""
import pytest
from httpx import AsyncClient

from api.models.database import (
    User, UserRole, Organization, OrgMember, OrgRole,
    Department, DepartmentMember, DeptRole, DepartmentFeature
)
from api.services.auth import create_access_token
from api.services.features import DEFAULT_FEATURES, RESTRICTED_FEATURES


# ============================================================================
# TEST CLASS: My Features Endpoint
# ============================================================================

@pytest.mark.asyncio
class TestMyFeatures:
    """
    Test GET /api/admin/me/features endpoint.

    Returns the list of features available to the current user.
    """

    async def test_superadmin_gets_all_features(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        organization: Organization,
        superadmin_org_member: OrgMember
    ):
        """Superadmin should have access to all features including restricted ones."""
        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.get(
            "/api/admin/me/features",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "features" in data
        assert isinstance(data["features"], list)

        # Superadmin should have all features
        for feature in DEFAULT_FEATURES:
            assert feature in data["features"]
        for feature in RESTRICTED_FEATURES:
            assert feature in data["features"]

    async def test_owner_gets_all_features(
        self,
        client: AsyncClient,
        db_session,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember
    ):
        """Organization owner should have access to all features."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.get(
            "/api/admin/me/features",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Owner should have all features
        for feature in DEFAULT_FEATURES:
            assert feature in data["features"]
        for feature in RESTRICTED_FEATURES:
            assert feature in data["features"]

    async def test_member_gets_default_features_only(
        self,
        client: AsyncClient,
        db_session,
        second_user: User,
        organization: Organization,
        department: Department,
        org_member: OrgMember
    ):
        """Regular member should only get default features when no restricted features are enabled."""
        # Add user to department
        dept_member = DepartmentMember(
            department_id=department.id,
            user_id=second_user.id,
            role=DeptRole.member
        )
        db_session.add(dept_member)
        await db_session.commit()

        token = create_access_token(data={
            "sub": str(second_user.id),
            "token_version": second_user.token_version
        })

        response = await client.get(
            "/api/admin/me/features",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Member should have default features
        for feature in DEFAULT_FEATURES:
            assert feature in data["features"]

        # Member should NOT have restricted features (unless enabled)
        for feature in RESTRICTED_FEATURES:
            assert feature not in data["features"]

    async def test_member_gets_enabled_restricted_feature(
        self,
        client: AsyncClient,
        db_session,
        second_user: User,
        organization: Organization,
        department: Department,
        org_member: OrgMember
    ):
        """Member should get restricted features that are enabled for their org/department."""
        # Add user to department
        dept_member = DepartmentMember(
            department_id=department.id,
            user_id=second_user.id,
            role=DeptRole.member
        )
        db_session.add(dept_member)

        # Enable vacancies feature for the organization
        org_feature = DepartmentFeature(
            org_id=organization.id,
            department_id=None,  # Org-wide
            feature_name="candidate_database",
            enabled=True
        )
        db_session.add(org_feature)
        await db_session.commit()

        token = create_access_token(data={
            "sub": str(second_user.id),
            "token_version": second_user.token_version
        })

        response = await client.get(
            "/api/admin/me/features",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Member should have vacancies feature now
        assert "candidate_database" in data["features"]

    async def test_member_dept_feature_override(
        self,
        client: AsyncClient,
        db_session,
        second_user: User,
        organization: Organization,
        department: Department,
        org_member: OrgMember
    ):
        """Department-level feature setting should override org-wide setting."""
        # Add user to department
        dept_member = DepartmentMember(
            department_id=department.id,
            user_id=second_user.id,
            role=DeptRole.member
        )
        db_session.add(dept_member)

        # Enable vacancies feature org-wide
        org_feature = DepartmentFeature(
            org_id=organization.id,
            department_id=None,
            feature_name="candidate_database",
            enabled=True
        )
        db_session.add(org_feature)

        # But disable it for this specific department
        dept_feature = DepartmentFeature(
            org_id=organization.id,
            department_id=department.id,
            feature_name="candidate_database",
            enabled=False
        )
        db_session.add(dept_feature)
        await db_session.commit()

        token = create_access_token(data={
            "sub": str(second_user.id),
            "token_version": second_user.token_version
        })

        response = await client.get(
            "/api/admin/me/features",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Member should NOT have vacancies feature (dept override disabled it)
        assert "candidate_database" not in data["features"]

    async def test_user_not_in_org_gets_default_features(
        self,
        client: AsyncClient,
        db_session,
        admin_user: User
    ):
        """User not in any organization should only get default features."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.get(
            "/api/admin/me/features",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # User should have default features
        for feature in DEFAULT_FEATURES:
            assert feature in data["features"]

        # Should NOT have restricted features
        for feature in RESTRICTED_FEATURES:
            assert feature not in data["features"]

    async def test_unauthenticated_request_fails(
        self,
        client: AsyncClient
    ):
        """Unauthenticated request should return 401."""
        response = await client.get("/api/admin/me/features")

        assert response.status_code == 401

    async def test_features_from_multiple_departments(
        self,
        client: AsyncClient,
        db_session,
        second_user: User,
        organization: Organization,
        department: Department,
        second_department: Department,
        org_member: OrgMember
    ):
        """User in multiple departments should have access to features enabled in any of them."""
        # Add user to both departments
        dept_member1 = DepartmentMember(
            department_id=department.id,
            user_id=second_user.id,
            role=DeptRole.member
        )
        dept_member2 = DepartmentMember(
            department_id=second_department.id,
            user_id=second_user.id,
            role=DeptRole.member
        )
        db_session.add(dept_member1)
        db_session.add(dept_member2)

        # Enable vacancies for first department only
        dept_feature = DepartmentFeature(
            org_id=organization.id,
            department_id=department.id,
            feature_name="candidate_database",
            enabled=True
        )
        db_session.add(dept_feature)
        await db_session.commit()

        token = create_access_token(data={
            "sub": str(second_user.id),
            "token_version": second_user.token_version
        })

        response = await client.get(
            "/api/admin/me/features",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # User should have vacancies (enabled in one of their departments)
        assert "candidate_database" in data["features"]
