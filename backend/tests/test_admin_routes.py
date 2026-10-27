"""
Tests for additional admin routes endpoints.

These tests cover:
- GET /api/admin/impersonation-logs - Get audit log of impersonation sessions
- GET /api/admin/users/{user_id}/details - Get detailed user information
"""
import pytest
from httpx import AsyncClient
from datetime import datetime

from api.models.database import (
    User, UserRole, Organization, OrgMember, OrgRole,
    Department, DepartmentMember, DeptRole, ImpersonationLog
)
from api.services.auth import create_access_token


# ============================================================================
# TEST CLASS: Impersonation Logs Endpoint
# ============================================================================

@pytest.mark.asyncio
class TestImpersonationLogs:
    """
    Test GET /api/admin/impersonation-logs endpoint.

    Returns audit log of all impersonation sessions for security monitoring.
    """

    async def test_get_impersonation_logs_success(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        admin_user: User
    ):
        """Test successfully retrieving impersonation logs."""
        # Create impersonation log
        log = ImpersonationLog(
            superadmin_id=superadmin_user.id,
            impersonated_user_id=admin_user.id,
            ip_address="127.0.0.1",
            user_agent="Test Browser",
            started_at=datetime.utcnow()
        )
        db_session.add(log)
        await db_session.commit()

        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.get(
            "/api/admin/impersonation-logs",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert isinstance(data, list)
        assert len(data) >= 1

        # Verify log entry structure
        log_entry = data[0]
        assert "id" in log_entry
        assert "superadmin_id" in log_entry
        assert "superadmin_name" in log_entry
        assert "superadmin_email" in log_entry
        assert "impersonated_user_id" in log_entry
        assert "impersonated_user_name" in log_entry
        assert "impersonated_user_email" in log_entry
        assert "started_at" in log_entry
        assert "ip_address" in log_entry
        assert "user_agent" in log_entry

    async def test_get_impersonation_logs_multiple_entries(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        admin_user: User,
        regular_user: User
    ):
        """Test retrieving multiple impersonation log entries."""
        # Create multiple logs
        logs = [
            ImpersonationLog(
                superadmin_id=superadmin_user.id,
                impersonated_user_id=admin_user.id,
                ip_address="127.0.0.1",
                user_agent="Browser 1",
                started_at=datetime.utcnow()
            ),
            ImpersonationLog(
                superadmin_id=superadmin_user.id,
                impersonated_user_id=regular_user.id,
                ip_address="192.168.1.1",
                user_agent="Browser 2",
                started_at=datetime.utcnow()
            )
        ]
        for log in logs:
            db_session.add(log)
        await db_session.commit()

        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.get(
            "/api/admin/impersonation-logs",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data) >= 2

    async def test_get_impersonation_logs_with_limit(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        admin_user: User
    ):
        """Test retrieving impersonation logs with limit parameter."""
        # Create 5 logs
        for i in range(5):
            log = ImpersonationLog(
                superadmin_id=superadmin_user.id,
                impersonated_user_id=admin_user.id,
                ip_address=f"127.0.0.{i}",
                started_at=datetime.utcnow()
            )
            db_session.add(log)
        await db_session.commit()

        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        # Request with limit=3
        response = await client.get(
            "/api/admin/impersonation-logs?limit=3",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Should return at most 3 logs
        assert len(data) <= 3

    async def test_get_impersonation_logs_ordered_by_date(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        admin_user: User
    ):
        """Test that impersonation logs are ordered by date (newest first)."""
        from datetime import timedelta

        # Create logs with different timestamps
        old_log = ImpersonationLog(
            superadmin_id=superadmin_user.id,
            impersonated_user_id=admin_user.id,
            started_at=datetime.utcnow() - timedelta(days=2)
        )
        new_log = ImpersonationLog(
            superadmin_id=superadmin_user.id,
            impersonated_user_id=admin_user.id,
            started_at=datetime.utcnow()
        )
        db_session.add(old_log)
        db_session.add(new_log)
        await db_session.commit()

        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.get(
            "/api/admin/impersonation-logs",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # First log should be the newest
        if len(data) >= 2:
            first_timestamp = datetime.fromisoformat(data[0]["started_at"])
            second_timestamp = datetime.fromisoformat(data[1]["started_at"])
            assert first_timestamp >= second_timestamp

    async def test_get_impersonation_logs_includes_user_info(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        admin_user: User
    ):
        """Test that logs include user information."""
        log = ImpersonationLog(
            superadmin_id=superadmin_user.id,
            impersonated_user_id=admin_user.id,
            started_at=datetime.utcnow()
        )
        db_session.add(log)
        await db_session.commit()

        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.get(
            "/api/admin/impersonation-logs",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        log_entry = data[0]
        assert log_entry["superadmin_email"] == superadmin_user.email
        assert log_entry["superadmin_name"] == superadmin_user.name
        assert log_entry["impersonated_user_email"] == admin_user.email
        assert log_entry["impersonated_user_name"] == admin_user.name

    async def test_get_impersonation_logs_non_superadmin_denied(
        self,
        client: AsyncClient,
        admin_user: User
    ):
        """Test that non-SUPERADMIN cannot access impersonation logs."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.get(
            "/api/admin/impersonation-logs",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403

    async def test_get_impersonation_logs_unauthenticated(
        self,
        client: AsyncClient
    ):
        """Test that unauthenticated requests are rejected."""
        response = await client.get("/api/admin/impersonation-logs")
        assert response.status_code in [401, 403]

    async def test_get_impersonation_logs_empty(
        self,
        client: AsyncClient,
        superadmin_user: User
    ):
        """Test retrieving logs when no impersonation has occurred."""
        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.get(
            "/api/admin/impersonation-logs",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


# ============================================================================
# TEST CLASS: User Details Endpoint
# ============================================================================

@pytest.mark.asyncio
class TestUserDetails:
    """
    Test GET /api/admin/users/{user_id}/details endpoint.

    Returns comprehensive user information including memberships and security data.
    """

    async def test_get_user_details_success(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        admin_user: User,
        organization: Organization,
        department: Department
    ):
        """Test successfully retrieving user details."""
        # Add user to organization and department
        org_member = OrgMember(
            org_id=organization.id,
            user_id=admin_user.id,
            role=OrgRole.admin
        )
        dept_member = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.lead
        )
        db_session.add(org_member)
        db_session.add(dept_member)
        await db_session.commit()

        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.get(
            f"/api/admin/users/{admin_user.id}/details",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify basic user info
        assert data["id"] == admin_user.id
        assert data["email"] == admin_user.email
        assert data["name"] == admin_user.name
        assert data["role"] == admin_user.role.value
        assert data["is_active"] == admin_user.is_active

        # Verify organizations array
        assert "organizations" in data
        assert isinstance(data["organizations"], list)
        assert len(data["organizations"]) >= 1

        # Verify departments array
        assert "departments" in data
        assert isinstance(data["departments"], list)
        assert len(data["departments"]) >= 1

        # Verify security info
        assert "token_version" in data
        assert "failed_login_attempts" in data
        assert "locked_until" in data

    async def test_get_user_details_includes_org_memberships(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        admin_user: User,
        organization: Organization,
        second_organization: Organization
    ):
        """Test that user details include all organization memberships."""
        # Add user to multiple organizations
        org1_member = OrgMember(
            org_id=organization.id,
            user_id=admin_user.id,
            role=OrgRole.owner
        )
        org2_member = OrgMember(
            org_id=second_organization.id,
            user_id=admin_user.id,
            role=OrgRole.member
        )
        db_session.add(org1_member)
        db_session.add(org2_member)
        await db_session.commit()

        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.get(
            f"/api/admin/users/{admin_user.id}/details",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Should have 2 organizations
        assert len(data["organizations"]) == 2

        # Verify organization info structure
        org_info = data["organizations"][0]
        assert "org_id" in org_info
        assert "org_name" in org_info
        assert "org_slug" in org_info
        assert "role" in org_info
        assert "joined_at" in org_info

    async def test_get_user_details_includes_dept_memberships(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        admin_user: User,
        organization: Organization,
        department: Department,
        second_department: Department
    ):
        """Test that user details include all department memberships."""
        # Add user to organization first
        org_member = OrgMember(
            org_id=organization.id,
            user_id=admin_user.id,
            role=OrgRole.admin
        )
        db_session.add(org_member)

        # Add user to multiple departments
        dept1_member = DepartmentMember(
            department_id=department.id,
            user_id=admin_user.id,
            role=DeptRole.lead
        )
        dept2_member = DepartmentMember(
            department_id=second_department.id,
            user_id=admin_user.id,
            role=DeptRole.member
        )
        db_session.add(dept1_member)
        db_session.add(dept2_member)
        await db_session.commit()

        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.get(
            f"/api/admin/users/{admin_user.id}/details",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Should have 2 departments
        assert len(data["departments"]) == 2

        # Verify department info structure
        dept_info = data["departments"][0]
        assert "dept_id" in dept_info
        assert "dept_name" in dept_info
        assert "dept_color" in dept_info
        assert "role" in dept_info
        assert "joined_at" in dept_info

    async def test_get_user_details_includes_security_info(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        admin_user: User
    ):
        """Test that user details include security information."""
        # Set some security fields
        admin_user.token_version = 5
        admin_user.failed_login_attempts = 2
        db_session.add(admin_user)
        await db_session.commit()

        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.get(
            f"/api/admin/users/{admin_user.id}/details",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["token_version"] == 5
        assert data["failed_login_attempts"] == 2

    async def test_get_user_details_includes_telegram_info(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        user_with_telegram: User
    ):
        """Test that user details include telegram information if available."""
        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.get(
            f"/api/admin/users/{user_with_telegram.id}/details",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["telegram_id"] == user_with_telegram.telegram_id
        assert data["telegram_username"] == user_with_telegram.telegram_username

    async def test_get_user_details_user_not_found(
        self,
        client: AsyncClient,
        superadmin_user: User
    ):
        """Test retrieving details for non-existent user."""
        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.get(
            "/api/admin/users/99999/details",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 404

    async def test_get_user_details_non_superadmin_denied(
        self,
        client: AsyncClient,
        admin_user: User,
        regular_user: User
    ):
        """Test that non-SUPERADMIN cannot access user details."""
        token = create_access_token(data={
            "sub": str(admin_user.id),
            "token_version": admin_user.token_version
        })

        response = await client.get(
            f"/api/admin/users/{regular_user.id}/details",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403

    async def test_get_user_details_unauthenticated(
        self,
        client: AsyncClient,
        admin_user: User
    ):
        """Test that unauthenticated requests are rejected."""
        response = await client.get(f"/api/admin/users/{admin_user.id}/details")
        assert response.status_code in [401, 403]

    async def test_get_user_details_no_memberships(
        self,
        client: AsyncClient,
        db_session,
        superadmin_user: User,
        regular_user: User
    ):
        """Test user details for user with no org/dept memberships."""
        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.get(
            f"/api/admin/users/{regular_user.id}/details",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Should have empty arrays
        assert data["organizations"] == []
        assert data["departments"] == []

    async def test_get_user_details_includes_created_at(
        self,
        client: AsyncClient,
        superadmin_user: User,
        admin_user: User
    ):
        """Test that user details include created_at timestamp."""
        token = create_access_token(data={
            "sub": str(superadmin_user.id),
            "token_version": superadmin_user.token_version
        })

        response = await client.get(
            f"/api/admin/users/{admin_user.id}/details",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert "created_at" in data
        # Should be parseable as datetime
        datetime.fromisoformat(data["created_at"])
