"""
Tests for Feature Access Control API Routes.

Tests cover:
1. GET /api/admin/features - list all feature settings for organization
2. PUT /api/admin/features/{feature_name} - create/update feature setting
3. DELETE /api/admin/features/{feature_name} - remove feature setting
4. Permission checks (superadmin/owner only)
"""
import pytest
from httpx import AsyncClient
from datetime import datetime

from api.models.database import (
    User, UserRole, Organization, OrgMember, OrgRole,
    Department, DepartmentMember, DeptRole, DepartmentFeature
)
from api.services.auth import create_access_token, hash_password


class TestGetFeatureSettings:
    """Tests for GET /api/admin/features endpoint."""

    @pytest.mark.asyncio
    async def test_superadmin_can_get_features(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        organization: Organization,
        superadmin_org_member: OrgMember
    ):
        """Superadmin can get all feature settings."""
        # Create some feature settings
        feature = DepartmentFeature(
            org_id=organization.id,
            department_id=None,
            feature_name="candidate_database",
            enabled=True
        )
        db_session.add(feature)
        await db_session.commit()

        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.get(
            "/api/admin/features",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert "features" in data
        assert "available_features" in data
        assert "restricted_features" in data

        # Check that vacancies is in the features list
        feature_names = [f["feature_name"] for f in data["features"]]
        assert "candidate_database" in feature_names

    @pytest.mark.asyncio
    async def test_org_owner_can_get_features(
        self,
        client: AsyncClient,
        db_session,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember
    ):
        """Organization owner can get all feature settings."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.get(
            "/api/admin/features",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "features" in data
        assert "restricted_features" in data

    @pytest.mark.asyncio
    async def test_regular_member_cannot_get_features(
        self,
        client: AsyncClient,
        db_session,
        second_user: User,
        organization: Organization,
        org_member: OrgMember
    ):
        """Regular organization member cannot access feature settings."""
        token = create_access_token(data={
            "sub": str(second_user.id),
            "token_version": second_user.token_version
        })

        response = await client.get(
            "/api/admin/features",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_features_include_department_names(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        organization: Organization,
        department: Department,
        superadmin_org_member: OrgMember
    ):
        """Feature settings include department names."""
        # Create department-specific feature
        feature = DepartmentFeature(
            org_id=organization.id,
            department_id=department.id,
            feature_name="candidate_database",
            enabled=True
        )
        db_session.add(feature)
        await db_session.commit()

        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.get(
            "/api/admin/features",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Find the department-specific feature
        dept_features = [f for f in data["features"] if f["department_id"] == department.id]
        assert len(dept_features) == 1
        assert dept_features[0]["department_name"] == department.name


class TestSetFeatureAccess:
    """Tests for PUT /api/admin/features/{feature_name} endpoint."""

    @pytest.mark.asyncio
    async def test_superadmin_can_set_org_wide_feature(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        organization: Organization,
        superadmin_org_member: OrgMember
    ):
        """Superadmin can set org-wide feature access."""
        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.put(
            "/api/admin/features/candidate_database",
            headers={"Authorization": f"Bearer {token}"},
            json={"enabled": True, "department_ids": None}
        )

        assert response.status_code == 200
        data = response.json()
        assert "features" in data

        # Verify the feature was created
        org_wide = [f for f in data["features"] if f["department_id"] is None and f["feature_name"] == "candidate_database"]
        assert len(org_wide) == 1
        assert org_wide[0]["enabled"] is True

    @pytest.mark.asyncio
    async def test_owner_can_set_department_specific_feature(
        self,
        client: AsyncClient,
        db_session,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember,
        department: Department
    ):
        """Organization owner can set department-specific feature access."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.put(
            "/api/admin/features/candidate_database",
            headers={"Authorization": f"Bearer {token}"},
            json={"enabled": True, "department_ids": [department.id]}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify the department-specific feature was created
        dept_features = [f for f in data["features"] if f["department_id"] == department.id]
        assert len(dept_features) == 1
        assert dept_features[0]["enabled"] is True

    @pytest.mark.asyncio
    async def test_set_feature_for_multiple_departments(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        organization: Organization,
        superadmin_org_member: OrgMember,
        department: Department,
        second_department: Department
    ):
        """Can set feature for multiple departments at once."""
        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.put(
            "/api/admin/features/ai_analysis",
            headers={"Authorization": f"Bearer {token}"},
            json={"enabled": True, "department_ids": [department.id, second_department.id]}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify both departments have the feature
        ai_features = [f for f in data["features"] if f["feature_name"] == "ai_analysis"]
        dept_ids = [f["department_id"] for f in ai_features]
        assert department.id in dept_ids
        assert second_department.id in dept_ids

    @pytest.mark.asyncio
    async def test_invalid_feature_name_returns_error(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        organization: Organization,
        superadmin_org_member: OrgMember
    ):
        """Invalid feature name returns 400 error."""
        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.put(
            "/api/admin/features/invalid_feature",
            headers={"Authorization": f"Bearer {token}"},
            json={"enabled": True, "department_ids": None}
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_regular_member_cannot_set_feature(
        self,
        client: AsyncClient,
        db_session,
        second_user: User,
        organization: Organization,
        org_member: OrgMember
    ):
        """Regular member cannot set feature access."""
        token = create_access_token(data={
            "sub": str(second_user.id),
            "token_version": second_user.token_version
        })

        response = await client.put(
            "/api/admin/features/candidate_database",
            headers={"Authorization": f"Bearer {token}"},
            json={"enabled": True, "department_ids": None}
        )

        assert response.status_code == 403


class TestDeleteFeatureSetting:
    """Tests for DELETE /api/admin/features/{feature_name} endpoint."""

    @pytest.mark.asyncio
    async def test_superadmin_can_delete_org_wide_feature(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        organization: Organization,
        superadmin_org_member: OrgMember
    ):
        """Superadmin can delete org-wide feature setting."""
        # Create org-wide feature
        feature = DepartmentFeature(
            org_id=organization.id,
            department_id=None,
            feature_name="candidate_database",
            enabled=True
        )
        db_session.add(feature)
        await db_session.commit()

        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.delete(
            "/api/admin/features/candidate_database",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        # Ответ ручки теперь {"message": "…успешно удалена"}, без "success".
        assert "успешно удалена" in data["message"]

    @pytest.mark.asyncio
    async def test_owner_can_delete_department_feature(
        self,
        client: AsyncClient,
        db_session,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember,
        department: Department
    ):
        """Organization owner can delete department-specific feature."""
        # Create department-specific feature
        feature = DepartmentFeature(
            org_id=organization.id,
            department_id=department.id,
            feature_name="candidate_database",
            enabled=True
        )
        db_session.add(feature)
        await db_session.commit()

        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.delete(
            f"/api/admin/features/candidate_database?department_id={department.id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        # Ответ ручки теперь {"message": "…успешно удалена"}, без "success".
        assert "успешно удалена" in data["message"]

    @pytest.mark.asyncio
    async def test_delete_nonexistent_feature_returns_404(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        organization: Organization,
        superadmin_org_member: OrgMember
    ):
        """Deleting nonexistent feature returns 404."""
        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.delete(
            "/api/admin/features/candidate_database",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_regular_member_cannot_delete_feature(
        self,
        client: AsyncClient,
        db_session,
        second_user: User,
        organization: Organization,
        org_member: OrgMember
    ):
        """Regular member cannot delete feature setting."""
        # Create feature first (as the org)
        feature = DepartmentFeature(
            org_id=organization.id,
            department_id=None,
            feature_name="candidate_database",
            enabled=True
        )
        db_session.add(feature)
        await db_session.commit()

        token = create_access_token(data={
            "sub": str(second_user.id),
            "token_version": second_user.token_version
        })

        response = await client.delete(
            "/api/admin/features/candidate_database",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403


class TestFeatureAccessIntegration:
    """Integration tests for feature access with user permissions."""

    @pytest.mark.asyncio
    async def test_user_feature_access_reflects_settings(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        organization: Organization,
        superadmin_org_member: OrgMember
    ):
        """User's available features reflect the settings."""
        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        # Enable vacancies
        await client.put(
            "/api/admin/features/candidate_database",
            headers={"Authorization": f"Bearer {token}"},
            json={"enabled": True, "department_ids": None}
        )

        # Get feature settings
        response = await client.get(
            "/api/admin/features",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Vacancies should be in the features list
        feature_names = [f["feature_name"] for f in data["features"]]
        assert "candidate_database" in feature_names

    @pytest.mark.asyncio
    async def test_toggle_feature_updates_settings(
        self,
        client: AsyncClient,
        db_session,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember
    ):
        """Toggling a feature updates the settings correctly."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        # Enable vacancies
        response1 = await client.put(
            "/api/admin/features/candidate_database",
            headers={"Authorization": f"Bearer {token}"},
            json={"enabled": True, "department_ids": None}
        )
        assert response1.status_code == 200

        # Verify enabled
        org_wide1 = [f for f in response1.json()["features"] if f["department_id"] is None and f["feature_name"] == "candidate_database"]
        assert org_wide1[0]["enabled"] is True

        # Disable vacancies
        response2 = await client.put(
            "/api/admin/features/candidate_database",
            headers={"Authorization": f"Bearer {token}"},
            json={"enabled": False, "department_ids": None}
        )
        assert response2.status_code == 200

        # Verify disabled
        org_wide2 = [f for f in response2.json()["features"] if f["department_id"] is None and f["feature_name"] == "candidate_database"]
        assert org_wide2[0]["enabled"] is False
