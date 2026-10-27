"""
Tests for Feature Audit Logging.

Tests cover:
1. Audit logs are created when features are enabled/disabled
2. Audit logs are created when features are deleted
3. GET /api/admin/features/audit-logs returns correct data
4. Audit logs contain correct user and department information
5. Permission checks for viewing audit logs
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from api.models.database import (
    User, UserRole, Organization, OrgMember, OrgRole,
    Department, DepartmentMember, DeptRole, DepartmentFeature, FeatureAuditLog
)
from api.services.auth import create_access_token


class TestFeatureAuditLogCreation:
    """Tests for audit log creation when modifying features."""

    @pytest.mark.asyncio
    async def test_enabling_feature_creates_audit_log(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        organization: Organization,
        superadmin_org_member: OrgMember
    ):
        """Enabling a feature creates an audit log entry."""
        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        # Enable vacancies feature
        response = await client.put(
            "/api/admin/features/candidate_database",
            headers={"Authorization": f"Bearer {token}"},
            json={"enabled": True, "department_ids": None}
        )

        assert response.status_code == 200

        # Check audit log was created
        result = await db_session.execute(
            select(FeatureAuditLog).where(
                FeatureAuditLog.org_id == organization.id,
                FeatureAuditLog.feature_name == "candidate_database"
            )
        )
        audit_log = result.scalar()

        assert audit_log is not None
        assert audit_log.action == "enable"
        assert audit_log.new_value is True
        assert audit_log.changed_by == superadmin_user.id
        assert audit_log.department_id is None
        assert audit_log.details is not None
        assert audit_log.details.get("scope") == "organization-wide"
        assert audit_log.details.get("changed_by_name") == superadmin_user.name
        assert audit_log.details.get("changed_by_email") == superadmin_user.email

    @pytest.mark.asyncio
    async def test_disabling_feature_creates_audit_log(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        organization: Organization,
        superadmin_org_member: OrgMember
    ):
        """Disabling a feature creates an audit log entry."""
        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        # First enable the feature
        await client.put(
            "/api/admin/features/candidate_database",
            headers={"Authorization": f"Bearer {token}"},
            json={"enabled": True, "department_ids": None}
        )

        # Clear session cache to get fresh data
        await db_session.commit()

        # Now disable it
        response = await client.put(
            "/api/admin/features/candidate_database",
            headers={"Authorization": f"Bearer {token}"},
            json={"enabled": False, "department_ids": None}
        )

        assert response.status_code == 200

        # Check audit logs
        result = await db_session.execute(
            select(FeatureAuditLog).where(
                FeatureAuditLog.org_id == organization.id,
                FeatureAuditLog.feature_name == "candidate_database"
            ).order_by(FeatureAuditLog.created_at.desc())
        )
        audit_logs = result.scalars().all()

        # Should have two logs: enable and disable
        assert len(audit_logs) >= 2

        # Latest should be disable
        disable_log = audit_logs[0]
        assert disable_log.action == "disable"
        assert disable_log.new_value is False
        assert disable_log.old_value is True

    @pytest.mark.asyncio
    async def test_department_specific_feature_creates_audit_log_with_department_info(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        organization: Organization,
        superadmin_org_member: OrgMember,
        department: Department
    ):
        """Department-specific feature change creates audit log with department info."""
        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.put(
            "/api/admin/features/candidate_database",
            headers={"Authorization": f"Bearer {token}"},
            json={"enabled": True, "department_ids": [department.id]}
        )

        assert response.status_code == 200

        # Check audit log
        result = await db_session.execute(
            select(FeatureAuditLog).where(
                FeatureAuditLog.org_id == organization.id,
                FeatureAuditLog.feature_name == "candidate_database",
                FeatureAuditLog.department_id == department.id
            )
        )
        audit_log = result.scalar()

        assert audit_log is not None
        assert audit_log.department_id == department.id
        assert audit_log.details.get("department_name") == department.name

    @pytest.mark.asyncio
    async def test_deleting_feature_creates_audit_log(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        organization: Organization,
        superadmin_org_member: OrgMember
    ):
        """Deleting a feature setting creates an audit log entry."""
        # First create a feature setting
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

        # Check audit log
        result = await db_session.execute(
            select(FeatureAuditLog).where(
                FeatureAuditLog.org_id == organization.id,
                FeatureAuditLog.feature_name == "candidate_database",
                FeatureAuditLog.action == "delete"
            )
        )
        audit_log = result.scalar()

        assert audit_log is not None
        assert audit_log.action == "delete"
        assert audit_log.old_value is True
        assert audit_log.new_value is None


class TestGetFeatureAuditLogs:
    """Tests for GET /api/admin/features/audit-logs endpoint."""

    @pytest.mark.asyncio
    async def test_superadmin_can_get_audit_logs(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        organization: Organization,
        superadmin_org_member: OrgMember
    ):
        """Superadmin can get feature audit logs."""
        # Create some audit logs
        audit_log = FeatureAuditLog(
            org_id=organization.id,
            changed_by=superadmin_user.id,
            feature_name="candidate_database",
            action="enable",
            department_id=None,
            old_value=None,
            new_value=True,
            details={"scope": "organization-wide"}
        )
        db_session.add(audit_log)
        await db_session.commit()

        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.get(
            "/api/admin/features/audit-logs",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data) >= 1
        log_entry = data[0]

        assert log_entry["feature_name"] == "candidate_database"
        assert log_entry["action"] == "enable"
        assert log_entry["changed_by"] == superadmin_user.id
        assert log_entry["changed_by_name"] == superadmin_user.name
        assert log_entry["changed_by_email"] == superadmin_user.email

    @pytest.mark.asyncio
    async def test_org_owner_can_get_audit_logs(
        self,
        client: AsyncClient,
        db_session,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember
    ):
        """Organization owner can get feature audit logs."""
        # Create audit log
        audit_log = FeatureAuditLog(
            org_id=organization.id,
            changed_by=admin_user.id,
            feature_name="ai_analysis",
            action="disable",
            department_id=None,
            old_value=True,
            new_value=False,
            details={}
        )
        db_session.add(audit_log)
        await db_session.commit()

        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.get(
            "/api/admin/features/audit-logs",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_regular_member_cannot_get_audit_logs(
        self,
        client: AsyncClient,
        db_session,
        second_user: User,
        organization: Organization,
        org_member: OrgMember
    ):
        """Regular member cannot access feature audit logs."""
        token = create_access_token(data={
            "sub": str(second_user.id),
            "token_version": second_user.token_version
        })

        response = await client.get(
            "/api/admin/features/audit-logs",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_filter_audit_logs_by_feature_name(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        organization: Organization,
        superadmin_org_member: OrgMember
    ):
        """Can filter audit logs by feature name."""
        # Create logs for different features
        log1 = FeatureAuditLog(
            org_id=organization.id,
            changed_by=superadmin_user.id,
            feature_name="candidate_database",
            action="enable",
            new_value=True
        )
        log2 = FeatureAuditLog(
            org_id=organization.id,
            changed_by=superadmin_user.id,
            feature_name="ai_analysis",
            action="enable",
            new_value=True
        )
        db_session.add_all([log1, log2])
        await db_session.commit()

        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.get(
            "/api/admin/features/audit-logs?feature_name=candidate_database",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Should only have vacancies logs
        for log in data:
            assert log["feature_name"] == "candidate_database"

    @pytest.mark.asyncio
    async def test_audit_logs_pagination(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        organization: Organization,
        superadmin_org_member: OrgMember
    ):
        """Audit logs support pagination."""
        # Create multiple logs
        for i in range(10):
            log = FeatureAuditLog(
                org_id=organization.id,
                changed_by=superadmin_user.id,
                feature_name="candidate_database",
                action="enable" if i % 2 == 0 else "disable",
                new_value=i % 2 == 0
            )
            db_session.add(log)
        await db_session.commit()

        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        # Get first page
        response1 = await client.get(
            "/api/admin/features/audit-logs?limit=3&offset=0",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response1.status_code == 200
        data1 = response1.json()
        assert len(data1) == 3

        # Get second page
        response2 = await client.get(
            "/api/admin/features/audit-logs?limit=3&offset=3",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2) == 3

        # Pages should have different logs
        ids1 = {log["id"] for log in data1}
        ids2 = {log["id"] for log in data2}
        assert ids1.isdisjoint(ids2)

    @pytest.mark.asyncio
    async def test_audit_logs_include_department_name(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        organization: Organization,
        superadmin_org_member: OrgMember,
        department: Department
    ):
        """Audit logs include department name for department-specific changes."""
        audit_log = FeatureAuditLog(
            org_id=organization.id,
            changed_by=superadmin_user.id,
            feature_name="candidate_database",
            action="enable",
            department_id=department.id,
            new_value=True,
            details={"department_name": department.name}
        )
        db_session.add(audit_log)
        await db_session.commit()

        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.get(
            "/api/admin/features/audit-logs",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        dept_log = next((log for log in data if log["department_id"] == department.id), None)
        assert dept_log is not None
        assert dept_log["department_name"] == department.name


class TestAuditLogIntegration:
    """Integration tests for audit logging with feature operations."""

    @pytest.mark.asyncio
    async def test_full_feature_lifecycle_audit_trail(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        organization: Organization,
        superadmin_org_member: OrgMember
    ):
        """Full feature lifecycle creates complete audit trail."""
        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        # Enable feature
        await client.put(
            "/api/admin/features/candidate_database",
            headers={"Authorization": f"Bearer {token}"},
            json={"enabled": True, "department_ids": None}
        )

        # Disable feature
        await client.put(
            "/api/admin/features/candidate_database",
            headers={"Authorization": f"Bearer {token}"},
            json={"enabled": False, "department_ids": None}
        )

        # Delete feature
        await client.delete(
            "/api/admin/features/candidate_database",
            headers={"Authorization": f"Bearer {token}"}
        )

        # Get audit logs
        response = await client.get(
            "/api/admin/features/audit-logs?feature_name=candidate_database",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Should have 3 logs: enable, disable, delete
        assert len(data) >= 3

        actions = [log["action"] for log in data]
        assert "enable" in actions
        assert "disable" in actions
        assert "delete" in actions

    @pytest.mark.asyncio
    async def test_multiple_department_changes_create_multiple_logs(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        organization: Organization,
        superadmin_org_member: OrgMember,
        department: Department,
        second_department: Department
    ):
        """Setting feature for multiple departments creates log for each."""
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

        # Check audit logs
        result = await db_session.execute(
            select(FeatureAuditLog).where(
                FeatureAuditLog.org_id == organization.id,
                FeatureAuditLog.feature_name == "ai_analysis"
            )
        )
        audit_logs = result.scalars().all()

        # Should have logs for both departments
        dept_ids = [log.department_id for log in audit_logs]
        assert department.id in dept_ids
        assert second_department.id in dept_ids
