"""
Comprehensive unit tests for invitation management endpoints.

Tests cover:
- Invitation creation with various roles and permissions
- Listing invitations with filtering
- Invitation validation (expiry, usage checks)
- Accepting invitations (new and existing users)
- Revoking invitations
- Permission checks for all operations
"""
import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.models.database import (
    User, Organization, OrgMember, OrgRole, Department,
    DepartmentMember, DeptRole, Invitation
)
from api.services.auth import create_access_token


def auth_headers(token: str) -> dict:
    """Create authorization headers with token."""
    return {"Authorization": f"Bearer {token}"}


class TestCreateInvitation:
    """Tests for POST /api/invitations endpoint."""

    async def test_owner_creates_member_invitation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember
    ):
        """Test owner successfully creates member invitation."""
        token = create_access_token({"sub": str(admin_user.id)})

        response = await client.post(
            "/api/invitations",
            json={
                "email": "newmember@test.com",
                "name": "New Member",
                "org_role": "member",
                "expires_in_days": 7
            },
            headers=auth_headers(token),
            params={"org_id": organization.id}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "newmember@test.com"
        assert data["name"] == "New Member"
        assert data["org_role"] == "member"
        assert data["invited_by_name"] == admin_user.name
        assert data["token"] is not None
        assert data["invitation_url"].startswith("/invite/")
        assert data["expires_at"] is not None
        assert data["used_at"] is None

        # Verify invitation in database
        result = await db_session.execute(
            select(Invitation).where(Invitation.token == data["token"])
        )
        invitation = result.scalar_one()
        assert invitation.org_id == organization.id
        assert invitation.org_role == OrgRole.member

    async def test_owner_creates_admin_invitation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember
    ):
        """Test owner can create admin invitation."""
        token = create_access_token({"sub": str(admin_user.id)})

        response = await client.post(
            "/api/invitations",
            json={
                "email": "newadmin@test.com",
                "name": "New Admin",
                "org_role": "admin",
                "expires_in_days": 7
            },
            headers=auth_headers(token),
            params={"org_id": organization.id}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["org_role"] == "admin"

    async def test_owner_creates_owner_invitation(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember
    ):
        """Test owner can create owner invitation."""
        token = create_access_token({"sub": str(admin_user.id)})

        response = await client.post(
            "/api/invitations",
            json={
                "email": "newowner@test.com",
                "org_role": "owner",
                "expires_in_days": 7
            },
            headers=auth_headers(token),
            params={"org_id": organization.id}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["org_role"] == "owner"

    async def test_admin_creates_member_invitation(
        self,
        client: AsyncClient,
        regular_user: User,
        organization: Organization,
        org_admin: OrgMember
    ):
        """Test admin can create member invitation."""
        token = create_access_token({"sub": str(regular_user.id)})

        response = await client.post(
            "/api/invitations",
            json={
                "email": "newmember@test.com",
                "org_role": "member",
                "expires_in_days": 5
            },
            headers=auth_headers(token),
            params={"org_id": organization.id}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["org_role"] == "member"

    async def test_admin_cannot_create_admin_invitation(
        self,
        client: AsyncClient,
        regular_user: User,
        organization: Organization,
        org_admin: OrgMember
    ):
        """Test admin cannot create admin/owner invitations."""
        token = create_access_token({"sub": str(regular_user.id)})

        response = await client.post(
            "/api/invitations",
            json={
                "email": "newadmin@test.com",
                "org_role": "admin",
                "expires_in_days": 7
            },
            headers=auth_headers(token),
            params={"org_id": organization.id}
        )

        assert response.status_code == 403
        assert "Only owner can create owner/admin invitations" in response.json()["detail"]

    async def test_admin_cannot_create_owner_invitation(
        self,
        client: AsyncClient,
        regular_user: User,
        organization: Organization,
        org_admin: OrgMember
    ):
        """Test admin cannot create owner invitations."""
        token = create_access_token({"sub": str(regular_user.id)})

        response = await client.post(
            "/api/invitations",
            json={
                "email": "newowner@test.com",
                "org_role": "owner",
                "expires_in_days": 7
            },
            headers=auth_headers(token),
            params={"org_id": organization.id}
        )

        assert response.status_code == 403

    async def test_create_invitation_with_departments(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember,
        department: Department,
        second_department: Department
    ):
        """Test creating invitation with department assignments."""
        token = create_access_token({"sub": str(admin_user.id)})

        response = await client.post(
            "/api/invitations",
            json={
                "email": "newmember@test.com",
                "org_role": "member",
                "department_ids": [
                    {"id": department.id, "role": "member"},
                    {"id": second_department.id, "role": "lead"}
                ],
                "expires_in_days": 7
            },
            headers=auth_headers(token),
            params={"org_id": organization.id}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["department_ids"]) == 2
        assert {"id": department.id, "role": "member"} in data["department_ids"]
        assert {"id": second_department.id, "role": "lead"} in data["department_ids"]

    async def test_admin_can_only_invite_to_own_departments(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        regular_user: User,
        organization: Organization,
        org_admin: OrgMember,
        department: Department,
        second_department: Department
    ):
        """Test admin can only invite to departments they belong to."""
        # Add admin to first department only
        dept_member = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.member
        )
        db_session.add(dept_member)
        await db_session.commit()

        token = create_access_token({"sub": str(regular_user.id)})

        # Try to invite to second department (admin is not a member)
        response = await client.post(
            "/api/invitations",
            json={
                "email": "newmember@test.com",
                "org_role": "member",
                "department_ids": [
                    {"id": second_department.id, "role": "member"}
                ],
                "expires_in_days": 7
            },
            headers=auth_headers(token),
            params={"org_id": organization.id}
        )

        assert response.status_code == 403
        assert "You can only invite to departments you belong to" in response.json()["detail"]

    async def test_create_invitation_for_existing_member_fails(
        self,
        client: AsyncClient,
        admin_user: User,
        second_user: User,
        organization: Organization,
        org_owner: OrgMember,
        org_member: OrgMember
    ):
        """Test cannot create invitation for user already in organization."""
        token = create_access_token({"sub": str(admin_user.id)})

        response = await client.post(
            "/api/invitations",
            json={
                "email": second_user.email,  # Already a member
                "org_role": "member",
                "expires_in_days": 7
            },
            headers=auth_headers(token),
            params={"org_id": organization.id}
        )

        assert response.status_code == 400
        assert "already a member" in response.json()["detail"]

    async def test_create_invitation_no_expiration(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember
    ):
        """Test creating invitation with no expiration."""
        token = create_access_token({"sub": str(admin_user.id)})

        response = await client.post(
            "/api/invitations",
            json={
                "email": "newmember@test.com",
                "org_role": "member",
                "expires_in_days": 0  # Never expires
            },
            headers=auth_headers(token),
            params={"org_id": organization.id}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["expires_at"] is None

    async def test_create_invitation_without_email(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember
    ):
        """Test creating generic invitation without specific email."""
        token = create_access_token({"sub": str(admin_user.id)})

        response = await client.post(
            "/api/invitations",
            json={
                "org_role": "member",
                "expires_in_days": 7
            },
            headers=auth_headers(token),
            params={"org_id": organization.id}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] is None
        assert data["token"] is not None

    async def test_regular_member_cannot_create_invitation(
        self,
        client: AsyncClient,
        second_user: User,
        organization: Organization,
        org_member: OrgMember
    ):
        """Test regular member cannot create invitations."""
        token = create_access_token({"sub": str(second_user.id)})

        response = await client.post(
            "/api/invitations",
            json={
                "email": "newmember@test.com",
                "org_role": "member",
                "expires_in_days": 7
            },
            headers=auth_headers(token),
            params={"org_id": organization.id}
        )

        assert response.status_code == 403

    async def test_create_invitation_invalid_role_defaults_to_member(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember
    ):
        """Test invalid role defaults to member."""
        token = create_access_token({"sub": str(admin_user.id)})

        response = await client.post(
            "/api/invitations",
            json={
                "email": "newmember@test.com",
                "org_role": "invalid_role",
                "expires_in_days": 7
            },
            headers=auth_headers(token),
            params={"org_id": organization.id}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["org_role"] == "member"

    async def test_department_lead_creates_invitation_for_own_department(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        regular_user: User,
        organization: Organization,
        department: Department
    ):
        """Test department lead can create invitation for their department."""
        # Give regular_user org member role (not admin/owner) and dept lead role
        org_member = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(org_member)

        dept_lead = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_lead)
        await db_session.commit()

        token = create_access_token({"sub": str(regular_user.id)})

        # Department lead can create invitation for their department
        response = await client.post(
            "/api/invitations",
            json={
                "email": "newmember@test.com",
                "name": "New Department Member",
                "org_role": "member",
                "department_ids": [{"id": department.id, "role": "member"}],
                "expires_in_days": 7
            },
            headers=auth_headers(token),
            params={"org_id": organization.id}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "newmember@test.com"
        assert data["org_role"] == "member"
        assert len(data["department_ids"]) == 1
        assert data["department_ids"][0]["id"] == department.id

    async def test_department_lead_must_specify_department(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        regular_user: User,
        organization: Organization,
        department: Department
    ):
        """Test department lead must specify at least one department."""
        # Give regular_user org member role (not admin/owner) and dept lead role
        org_member = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.member,
            created_at=datetime.utcnow()
        )
        db_session.add(org_member)

        dept_lead = DepartmentMember(
            department_id=department.id,
            user_id=regular_user.id,
            role=DeptRole.lead,
            created_at=datetime.utcnow()
        )
        db_session.add(dept_lead)
        await db_session.commit()

        token = create_access_token({"sub": str(regular_user.id)})

        # Department lead must specify department (without being org admin)
        response = await client.post(
            "/api/invitations",
            json={
                "email": "newmember@test.com",
                "name": "New Department Member",
                "org_role": "member",
                "expires_in_days": 7
            },
            headers=auth_headers(token),
            params={"org_id": organization.id}
        )

        assert response.status_code == 400
        assert "department" in response.json()["detail"].lower()


class TestListInvitations:
    """Tests for GET /api/invitations endpoint."""

    async def test_owner_sees_all_invitations(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        regular_user: User,
        organization: Organization,
        org_owner: OrgMember,
        org_admin: OrgMember
    ):
        """Test owner can see all organization invitations."""
        # Create invitations by different users
        inv1 = Invitation(
            token="token1",
            org_id=organization.id,
            email="user1@test.com",
            org_role=OrgRole.member,
            invited_by_id=admin_user.id
        )
        inv2 = Invitation(
            token="token2",
            org_id=organization.id,
            email="user2@test.com",
            org_role=OrgRole.member,
            invited_by_id=regular_user.id
        )
        db_session.add_all([inv1, inv2])
        await db_session.commit()

        token = create_access_token({"sub": str(admin_user.id)})

        response = await client.get(
            "/api/invitations",
            headers=auth_headers(token),
            params={"org_id": organization.id}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        emails = [inv["email"] for inv in data]
        assert "user1@test.com" in emails
        assert "user2@test.com" in emails

    async def test_admin_sees_only_own_invitations(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        regular_user: User,
        organization: Organization,
        org_admin: OrgMember
    ):
        """Test admin sees only invitations they created."""
        # Create invitations by different users
        inv1 = Invitation(
            token="token1",
            org_id=organization.id,
            email="user1@test.com",
            org_role=OrgRole.member,
            invited_by_id=regular_user.id  # Created by admin
        )
        inv2 = Invitation(
            token="token2",
            org_id=organization.id,
            email="user2@test.com",
            org_role=OrgRole.member,
            invited_by_id=admin_user.id  # Created by owner
        )
        db_session.add_all([inv1, inv2])
        await db_session.commit()

        token = create_access_token({"sub": str(regular_user.id)})

        response = await client.get(
            "/api/invitations",
            headers=auth_headers(token),
            params={"org_id": organization.id}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["email"] == "user1@test.com"
        assert data[0]["invited_by_name"] == regular_user.name

    async def test_list_invitations_exclude_used_by_default(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember
    ):
        """Test used invitations are excluded by default."""
        inv1 = Invitation(
            token="token1",
            org_id=organization.id,
            email="user1@test.com",
            org_role=OrgRole.member,
            invited_by_id=admin_user.id
        )
        inv2 = Invitation(
            token="token2",
            org_id=organization.id,
            email="user2@test.com",
            org_role=OrgRole.member,
            invited_by_id=admin_user.id,
            used_at=datetime.utcnow(),
            used_by_id=admin_user.id
        )
        db_session.add_all([inv1, inv2])
        await db_session.commit()

        token = create_access_token({"sub": str(admin_user.id)})

        response = await client.get(
            "/api/invitations",
            headers=auth_headers(token),
            params={"org_id": organization.id}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["email"] == "user1@test.com"
        assert data[0]["used_at"] is None

    async def test_list_invitations_include_used(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember
    ):
        """Test can include used invitations."""
        inv1 = Invitation(
            token="token1",
            org_id=organization.id,
            email="user1@test.com",
            org_role=OrgRole.member,
            invited_by_id=admin_user.id
        )
        inv2 = Invitation(
            token="token2",
            org_id=organization.id,
            email="user2@test.com",
            org_role=OrgRole.member,
            invited_by_id=admin_user.id,
            used_at=datetime.utcnow(),
            used_by_id=admin_user.id
        )
        db_session.add_all([inv1, inv2])
        await db_session.commit()

        token = create_access_token({"sub": str(admin_user.id)})

        response = await client.get(
            "/api/invitations",
            headers=auth_headers(token),
            params={"org_id": organization.id, "include_used": True}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    async def test_list_invitations_response_format(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember,
        department: Department
    ):
        """Test invitation response includes all required fields."""
        inv = Invitation(
            token="test_token",
            org_id=organization.id,
            email="test@test.com",
            name="Test User",
            org_role=OrgRole.member,
            department_ids=[{"id": department.id, "role": "member"}],
            invited_by_id=admin_user.id,
            expires_at=datetime.utcnow() + timedelta(days=7)
        )
        db_session.add(inv)
        await db_session.commit()

        token = create_access_token({"sub": str(admin_user.id)})

        response = await client.get(
            "/api/invitations",
            headers=auth_headers(token),
            params={"org_id": organization.id}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

        invitation = data[0]
        assert invitation["id"] is not None
        assert invitation["token"] == "test_token"
        assert invitation["email"] == "test@test.com"
        assert invitation["name"] == "Test User"
        assert invitation["org_role"] == "member"
        assert len(invitation["department_ids"]) == 1
        assert invitation["invited_by_name"] == admin_user.name
        assert invitation["expires_at"] is not None
        assert invitation["used_at"] is None
        assert invitation["used_by_name"] is None
        assert invitation["created_at"] is not None
        assert invitation["invitation_url"] == f"/invite/{inv.token}"

    async def test_regular_member_cannot_list_invitations(
        self,
        client: AsyncClient,
        second_user: User,
        organization: Organization,
        org_member: OrgMember
    ):
        """Test regular member cannot list invitations."""
        token = create_access_token({"sub": str(second_user.id)})

        response = await client.get(
            "/api/invitations",
            headers=auth_headers(token),
            params={"org_id": organization.id}
        )

        assert response.status_code == 403


class TestValidateInvitation:
    """Tests for GET /api/invitations/validate/{token} endpoint."""

    async def test_validate_valid_invitation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization
    ):
        """Test validating a valid invitation."""
        inv = Invitation(
            token="valid_token",
            org_id=organization.id,
            email="test@test.com",
            name="Test User",
            org_role=OrgRole.member,
            expires_at=datetime.utcnow() + timedelta(days=7)
        )
        db_session.add(inv)
        await db_session.commit()

        response = await client.get("/api/invitations/validate/valid_token")

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["expired"] is False
        assert data["used"] is False
        assert data["email"] == "test@test.com"
        assert data["name"] == "Test User"
        assert data["org_name"] == organization.name
        assert data["org_role"] == "member"

    async def test_validate_invalid_token(self, client: AsyncClient):
        """Test validating non-existent token."""
        response = await client.get("/api/invitations/validate/invalid_token")

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["expired"] is False
        assert data["used"] is False

    async def test_validate_used_invitation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization
    ):
        """Test validating already used invitation."""
        inv = Invitation(
            token="used_token",
            org_id=organization.id,
            email="test@test.com",
            org_role=OrgRole.member,
            used_at=datetime.utcnow(),
            used_by_id=admin_user.id
        )
        db_session.add(inv)
        await db_session.commit()

        response = await client.get("/api/invitations/validate/used_token")

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["used"] is True
        assert data["expired"] is False
        assert data["org_name"] == organization.name

    async def test_validate_expired_invitation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization
    ):
        """Test validating expired invitation."""
        inv = Invitation(
            token="expired_token",
            org_id=organization.id,
            email="test@test.com",
            org_role=OrgRole.member,
            expires_at=datetime.utcnow() - timedelta(days=1)
        )
        db_session.add(inv)
        await db_session.commit()

        response = await client.get("/api/invitations/validate/expired_token")

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["expired"] is True
        assert data["used"] is False
        assert data["org_name"] == organization.name

    async def test_validate_invitation_no_expiration(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization
    ):
        """Test validating invitation with no expiration."""
        inv = Invitation(
            token="no_expiry_token",
            org_id=organization.id,
            email="test@test.com",
            org_role=OrgRole.member,
            expires_at=None
        )
        db_session.add(inv)
        await db_session.commit()

        response = await client.get("/api/invitations/validate/no_expiry_token")

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["expired"] is False


class TestAcceptInvitation:
    """Tests for POST /api/invitations/accept/{token} endpoint."""

    async def test_new_user_accepts_invitation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization
    ):
        """Test new user accepts invitation and creates account."""
        inv = Invitation(
            token="new_user_token",
            org_id=organization.id,
            email="newuser@test.com",
            name="New User",
            org_role=OrgRole.member,
            invited_by_id=admin_user.id
        )
        db_session.add(inv)
        await db_session.commit()

        response = await client.post(
            "/api/invitations/accept/new_user_token",
            json={
                "email": "newuser@test.com",
                "name": "New User",
                "password": "securepassword123"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["access_token"] is not None
        assert data["user_id"] is not None
        assert "t.me" in data["telegram_bind_url"]

        # Verify user was created
        result = await db_session.execute(
            select(User).where(User.email == "newuser@test.com")
        )
        user = result.scalar_one()
        assert user.name == "New User"

        # Verify org membership was created
        result = await db_session.execute(
            select(OrgMember).where(
                OrgMember.user_id == user.id,
                OrgMember.org_id == organization.id
            )
        )
        membership = result.scalar_one()
        assert membership.role == OrgRole.member

        # Verify invitation was marked as used
        await db_session.refresh(inv)
        assert inv.used_at is not None
        assert inv.used_by_id == user.id

    async def test_existing_user_accepts_invitation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization,
        second_organization: Organization,
        regular_user: User
    ):
        """Test existing user accepts invitation to join new organization."""
        inv = Invitation(
            token="existing_user_token",
            org_id=second_organization.id,
            email=regular_user.email,
            org_role=OrgRole.member,
            invited_by_id=admin_user.id
        )
        db_session.add(inv)
        await db_session.commit()

        response = await client.post(
            "/api/invitations/accept/existing_user_token",
            json={
                "email": regular_user.email,
                "name": regular_user.name,
                "password": "anypassword"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["user_id"] == regular_user.id

        # Verify org membership was created for second org
        result = await db_session.execute(
            select(OrgMember).where(
                OrgMember.user_id == regular_user.id,
                OrgMember.org_id == second_organization.id
            )
        )
        membership = result.scalar_one()
        assert membership.role == OrgRole.member

    async def test_accept_invitation_with_departments(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization,
        department: Department,
        second_department: Department
    ):
        """Test accepting invitation creates department memberships."""
        inv = Invitation(
            token="dept_token",
            org_id=organization.id,
            email="deptuser@test.com",
            org_role=OrgRole.member,
            department_ids=[
                {"id": department.id, "role": "member"},
                {"id": second_department.id, "role": "lead"}
            ],
            invited_by_id=admin_user.id
        )
        db_session.add(inv)
        await db_session.commit()

        response = await client.post(
            "/api/invitations/accept/dept_token",
            json={
                "email": "deptuser@test.com",
                "name": "Department User",
                "password": "password123"
            }
        )

        assert response.status_code == 200

        # Verify user was created
        result = await db_session.execute(
            select(User).where(User.email == "deptuser@test.com")
        )
        user = result.scalar_one()

        # Verify department memberships
        result = await db_session.execute(
            select(DepartmentMember).where(DepartmentMember.user_id == user.id)
        )
        dept_memberships = result.scalars().all()
        assert len(dept_memberships) == 2

        dept_roles = {dm.department_id: dm.role for dm in dept_memberships}
        assert dept_roles[department.id] == DeptRole.member
        assert dept_roles[second_department.id] == DeptRole.lead

    async def test_accept_invitation_invalid_department_ignored(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization,
        second_organization: Organization,
        department: Department
    ):
        """Test accepting invitation ignores departments from wrong org."""
        # Create department in different org
        other_dept = Department(
            name="Other Dept",
            org_id=second_organization.id
        )
        db_session.add(other_dept)
        await db_session.commit()

        inv = Invitation(
            token="cross_org_dept_token",
            org_id=organization.id,
            email="test@test.com",
            org_role=OrgRole.member,
            department_ids=[
                {"id": department.id, "role": "member"},
                {"id": other_dept.id, "role": "member"}  # Wrong org
            ],
            invited_by_id=admin_user.id
        )
        db_session.add(inv)
        await db_session.commit()

        response = await client.post(
            "/api/invitations/accept/cross_org_dept_token",
            json={
                "email": "test@test.com",
                "name": "Test User",
                "password": "password123"
            }
        )

        assert response.status_code == 200

        result = await db_session.execute(
            select(User).where(User.email == "test@test.com")
        )
        user = result.scalar_one()

        # Verify only department from correct org was added
        result = await db_session.execute(
            select(DepartmentMember).where(DepartmentMember.user_id == user.id)
        )
        dept_memberships = result.scalars().all()
        assert len(dept_memberships) == 1
        assert dept_memberships[0].department_id == department.id

    async def test_accept_invitation_token_not_found(self, client: AsyncClient):
        """Test accepting invitation with invalid token."""
        response = await client.post(
            "/api/invitations/accept/invalid_token",
            json={
                "email": "test@test.com",
                "name": "Test",
                "password": "password"
            }
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    async def test_accept_already_used_invitation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization
    ):
        """Test cannot accept already used invitation."""
        inv = Invitation(
            token="used_token",
            org_id=organization.id,
            email="test@test.com",
            org_role=OrgRole.member,
            used_at=datetime.utcnow(),
            used_by_id=admin_user.id
        )
        db_session.add(inv)
        await db_session.commit()

        response = await client.post(
            "/api/invitations/accept/used_token",
            json={
                "email": "test@test.com",
                "name": "Test",
                "password": "password"
            }
        )

        assert response.status_code == 400
        assert "already used" in response.json()["detail"]

    async def test_accept_expired_invitation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization
    ):
        """Test cannot accept expired invitation."""
        inv = Invitation(
            token="expired_token",
            org_id=organization.id,
            email="test@test.com",
            org_role=OrgRole.member,
            expires_at=datetime.utcnow() - timedelta(days=1)
        )
        db_session.add(inv)
        await db_session.commit()

        response = await client.post(
            "/api/invitations/accept/expired_token",
            json={
                "email": "test@test.com",
                "name": "Test",
                "password": "password"
            }
        )

        assert response.status_code == 400
        assert "expired" in response.json()["detail"]

    async def test_accept_invitation_user_already_member(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember
    ):
        """Test cannot accept invitation if already member of org."""
        inv = Invitation(
            token="duplicate_token",
            org_id=organization.id,
            email=admin_user.email,
            org_role=OrgRole.member
        )
        db_session.add(inv)
        await db_session.commit()

        response = await client.post(
            "/api/invitations/accept/duplicate_token",
            json={
                "email": admin_user.email,
                "name": "Test",
                "password": "password"
            }
        )

        assert response.status_code == 400
        assert "already a member" in response.json()["detail"]

    async def test_accept_invitation_creates_telegram_url(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization
    ):
        """Test telegram bind URL is generated on acceptance."""
        inv = Invitation(
            token="telegram_token",
            org_id=organization.id,
            email="telegram@test.com",
            org_role=OrgRole.member
        )
        db_session.add(inv)
        await db_session.commit()

        response = await client.post(
            "/api/invitations/accept/telegram_token",
            json={
                "email": "telegram@test.com",
                "name": "Telegram User",
                "password": "password123"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["telegram_bind_url"] is not None
        assert "enceladus_mst_bot" in data["telegram_bind_url"]
        # Ссылка несёт ОДНОРАЗОВЫЙ токен пользователя, а не «bind_<id>»: id
        # перебирается, и чужой мог привязать свой Telegram к новому аккаунту.
        user = await db_session.get(User, data["user_id"])
        await db_session.refresh(user)
        assert user.telegram_bind_token
        assert data["telegram_bind_url"].endswith(f"?start={user.telegram_bind_token}")
        assert f"bind_{data['user_id']}" not in data["telegram_bind_url"]

    async def test_accept_invitation_admin_role(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization,
        admin_user: User
    ):
        """Test accepting invitation with admin role."""
        inv = Invitation(
            token="admin_token",
            org_id=organization.id,
            email="newadmin@test.com",
            org_role=OrgRole.admin,
            invited_by_id=admin_user.id
        )
        db_session.add(inv)
        await db_session.commit()

        response = await client.post(
            "/api/invitations/accept/admin_token",
            json={
                "email": "newadmin@test.com",
                "name": "New Admin",
                "password": "password123"
            }
        )

        assert response.status_code == 200

        # Verify user has admin role in org
        result = await db_session.execute(
            select(User).where(User.email == "newadmin@test.com")
        )
        user = result.scalar_one()

        result = await db_session.execute(
            select(OrgMember).where(
                OrgMember.user_id == user.id,
                OrgMember.org_id == organization.id
            )
        )
        membership = result.scalar_one()
        assert membership.role == OrgRole.admin


class TestRevokeInvitation:
    """Tests for DELETE /api/invitations/{invitation_id} endpoint."""

    async def test_owner_revokes_any_invitation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        regular_user: User,
        organization: Organization,
        org_owner: OrgMember
    ):
        """Test owner can revoke any invitation."""
        inv = Invitation(
            token="revoke_token",
            org_id=organization.id,
            email="test@test.com",
            org_role=OrgRole.member,
            invited_by_id=regular_user.id  # Created by someone else
        )
        db_session.add(inv)
        await db_session.commit()
        inv_id = inv.id

        token = create_access_token({"sub": str(admin_user.id)})

        response = await client.delete(
            f"/api/invitations/{inv_id}",
            headers=auth_headers(token),
            params={"org_id": organization.id}
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify invitation was deleted
        result = await db_session.execute(
            select(Invitation).where(Invitation.id == inv_id)
        )
        assert result.scalar_one_or_none() is None

    async def test_admin_revokes_own_invitation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        regular_user: User,
        organization: Organization,
        org_admin: OrgMember
    ):
        """Test admin can revoke their own invitation."""
        inv = Invitation(
            token="admin_revoke_token",
            org_id=organization.id,
            email="test@test.com",
            org_role=OrgRole.member,
            invited_by_id=regular_user.id
        )
        db_session.add(inv)
        await db_session.commit()
        inv_id = inv.id

        token = create_access_token({"sub": str(regular_user.id)})

        response = await client.delete(
            f"/api/invitations/{inv_id}",
            headers=auth_headers(token),
            params={"org_id": organization.id}
        )

        assert response.status_code == 200

        # Verify deletion
        result = await db_session.execute(
            select(Invitation).where(Invitation.id == inv_id)
        )
        assert result.scalar_one_or_none() is None

    async def test_admin_cannot_revoke_others_invitation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        regular_user: User,
        organization: Organization,
        org_admin: OrgMember
    ):
        """Test admin cannot revoke invitations created by others."""
        inv = Invitation(
            token="other_admin_token",
            org_id=organization.id,
            email="test@test.com",
            org_role=OrgRole.member,
            invited_by_id=admin_user.id  # Created by owner
        )
        db_session.add(inv)
        await db_session.commit()

        token = create_access_token({"sub": str(regular_user.id)})

        response = await client.delete(
            f"/api/invitations/{inv.id}",
            headers=auth_headers(token),
            params={"org_id": organization.id}
        )

        assert response.status_code == 403
        assert "You can only revoke your own invitations" in response.json()["detail"]

    async def test_revoke_nonexistent_invitation(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember
    ):
        """Test revoking non-existent invitation returns 404."""
        token = create_access_token({"sub": str(admin_user.id)})

        response = await client.delete(
            "/api/invitations/99999",
            headers=auth_headers(token),
            params={"org_id": organization.id}
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    async def test_revoke_invitation_from_different_org(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization,
        second_organization: Organization,
        org_owner: OrgMember
    ):
        """Test cannot revoke invitation from different organization."""
        inv = Invitation(
            token="other_org_token",
            org_id=second_organization.id,
            email="test@test.com",
            org_role=OrgRole.member
        )
        db_session.add(inv)
        await db_session.commit()

        token = create_access_token({"sub": str(admin_user.id)})

        response = await client.delete(
            f"/api/invitations/{inv.id}",
            headers=auth_headers(token),
            params={"org_id": organization.id}
        )

        assert response.status_code == 404

    async def test_regular_member_cannot_revoke_invitation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        second_user: User,
        organization: Organization,
        org_member: OrgMember
    ):
        """Test regular member cannot revoke invitations."""
        inv = Invitation(
            token="member_revoke_token",
            org_id=organization.id,
            email="test@test.com",
            org_role=OrgRole.member,
            invited_by_id=second_user.id
        )
        db_session.add(inv)
        await db_session.commit()

        token = create_access_token({"sub": str(second_user.id)})

        response = await client.delete(
            f"/api/invitations/{inv.id}",
            headers=auth_headers(token),
            params={"org_id": organization.id}
        )

        assert response.status_code == 403


class TestInvitationExpiryLogic:
    """Tests specifically for invitation expiry edge cases."""

    async def test_invitation_expiring_in_future_is_valid(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization
    ):
        """Test invitation expiring in future is still valid."""
        inv = Invitation(
            token="future_expiry",
            org_id=organization.id,
            email="test@test.com",
            org_role=OrgRole.member,
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        db_session.add(inv)
        await db_session.commit()

        response = await client.get("/api/invitations/validate/future_expiry")

        assert response.status_code == 200
        assert response.json()["valid"] is True
        assert response.json()["expired"] is False

    async def test_invitation_just_expired_is_invalid(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization
    ):
        """Test invitation that just expired is invalid."""
        inv = Invitation(
            token="just_expired",
            org_id=organization.id,
            email="test@test.com",
            org_role=OrgRole.member,
            expires_at=datetime.utcnow() - timedelta(seconds=1)
        )
        db_session.add(inv)
        await db_session.commit()

        response = await client.get("/api/invitations/validate/just_expired")

        assert response.status_code == 200
        assert response.json()["valid"] is False
        assert response.json()["expired"] is True

    async def test_accept_invitation_expiring_soon_succeeds(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization
    ):
        """Test can accept invitation that's about to expire."""
        inv = Invitation(
            token="expiring_soon",
            org_id=organization.id,
            email="test@test.com",
            org_role=OrgRole.member,
            expires_at=datetime.utcnow() + timedelta(minutes=5)
        )
        db_session.add(inv)
        await db_session.commit()

        response = await client.post(
            "/api/invitations/accept/expiring_soon",
            json={
                "email": "test@test.com",
                "name": "Test User",
                "password": "password123"
            }
        )

        assert response.status_code == 200
        assert response.json()["success"] is True


class TestInvitationRoleAssignment:
    """Tests for role assignment through invitations."""

    async def test_member_invitation_assigns_member_role(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization
    ):
        """Test member invitation assigns member role."""
        inv = Invitation(
            token="member_role",
            org_id=organization.id,
            email="member@test.com",
            org_role=OrgRole.member
        )
        db_session.add(inv)
        await db_session.commit()

        await client.post(
            "/api/invitations/accept/member_role",
            json={
                "email": "member@test.com",
                "name": "Member",
                "password": "password"
            }
        )

        result = await db_session.execute(
            select(User).where(User.email == "member@test.com")
        )
        user = result.scalar_one()

        result = await db_session.execute(
            select(OrgMember).where(OrgMember.user_id == user.id)
        )
        membership = result.scalar_one()
        assert membership.role == OrgRole.member

    async def test_owner_invitation_assigns_owner_role(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization
    ):
        """Test owner invitation assigns owner role."""
        inv = Invitation(
            token="owner_role",
            org_id=organization.id,
            email="owner@test.com",
            org_role=OrgRole.owner
        )
        db_session.add(inv)
        await db_session.commit()

        await client.post(
            "/api/invitations/accept/owner_role",
            json={
                "email": "owner@test.com",
                "name": "Owner",
                "password": "password"
            }
        )

        result = await db_session.execute(
            select(User).where(User.email == "owner@test.com")
        )
        user = result.scalar_one()

        result = await db_session.execute(
            select(OrgMember).where(OrgMember.user_id == user.id)
        )
        membership = result.scalar_one()
        assert membership.role == OrgRole.owner

    async def test_department_role_assignment(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization,
        department: Department
    ):
        """Test department role is correctly assigned."""
        inv = Invitation(
            token="dept_role",
            org_id=organization.id,
            email="dept@test.com",
            org_role=OrgRole.member,
            department_ids=[{"id": department.id, "role": "lead"}]
        )
        db_session.add(inv)
        await db_session.commit()

        await client.post(
            "/api/invitations/accept/dept_role",
            json={
                "email": "dept@test.com",
                "name": "Dept Lead",
                "password": "password"
            }
        )

        result = await db_session.execute(
            select(User).where(User.email == "dept@test.com")
        )
        user = result.scalar_one()

        result = await db_session.execute(
            select(DepartmentMember).where(DepartmentMember.user_id == user.id)
        )
        dept_membership = result.scalar_one()
        assert dept_membership.role == DeptRole.lead

    async def test_invalid_department_role_defaults_to_member(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization,
        department: Department
    ):
        """Test invalid department role defaults to member."""
        inv = Invitation(
            token="invalid_dept_role",
            org_id=organization.id,
            email="invalid@test.com",
            org_role=OrgRole.member,
            department_ids=[{"id": department.id, "role": "invalid_role"}]
        )
        db_session.add(inv)
        await db_session.commit()

        await client.post(
            "/api/invitations/accept/invalid_dept_role",
            json={
                "email": "invalid@test.com",
                "name": "Test",
                "password": "password"
            }
        )

        result = await db_session.execute(
            select(User).where(User.email == "invalid@test.com")
        )
        user = result.scalar_one()

        result = await db_session.execute(
            select(DepartmentMember).where(DepartmentMember.user_id == user.id)
        )
        dept_membership = result.scalar_one()
        assert dept_membership.role == DeptRole.member
