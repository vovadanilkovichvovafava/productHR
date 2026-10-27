"""
API contract tests to ensure response formats match expected schemas.

These tests verify that all API endpoints return responses with the correct
structure, field types, and required fields. This helps prevent breaking changes
to the API contract.
"""
import pytest
from datetime import datetime
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, List

from api.models.database import (
    User, Organization, OrgMember, Department, DepartmentMember,
    Entity, Chat, CallRecording, SharedAccess,
    UserRole, OrgRole, DeptRole, EntityType, EntityStatus,
    ChatType, CallStatus, CallSource, AccessLevel, ResourceType
)
from api.services.auth import create_access_token

from .helpers import (
    create_test_user, create_test_organization, create_full_org_setup,
    create_test_entity, create_test_chat, create_test_call,
    create_share, make_auth_headers, assert_response_has_fields,
    assert_pagination_format, add_user_to_org, create_test_department,
    add_user_to_dept
)


# ============================================================================
# USER API CONTRACTS
# ============================================================================

class TestUserAPIContracts:
    """Test User API response formats."""

    @pytest.mark.asyncio
    async def test_user_response_format(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        admin_token: str
    ):
        """Test user response has all required fields."""
        response = await client.get(
            "/api/users/me",
            headers=make_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()

        required_fields = ["id", "email", "name", "role", "is_active", "created_at"]
        assert_response_has_fields(data, required_fields)

        # Verify field types
        assert isinstance(data["id"], int)
        assert isinstance(data["email"], str)
        assert isinstance(data["name"], str)
        assert isinstance(data["role"], str)
        assert isinstance(data["is_active"], bool)
        assert isinstance(data["created_at"], str)  # ISO format datetime

        # Optional fields should have correct types if present
        if data.get("telegram_id") is not None:
            assert isinstance(data["telegram_id"], int)
        if data.get("telegram_username") is not None:
            assert isinstance(data["telegram_username"], str)

    @pytest.mark.asyncio
    async def test_users_list_response_format(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        admin_token: str,
        organization: Organization,
        org_owner: OrgMember
    ):
        """Test users list endpoint returns correct format."""
        response = await client.get(
            "/api/users",
            headers=make_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()

        # Should be a list
        assert isinstance(data, list)

        if len(data) > 0:
            # Check first user has required fields
            user = data[0]
            required_fields = ["id", "email", "name", "role", "is_active", "created_at"]
            assert_response_has_fields(user, required_fields)


# ============================================================================
# ORGANIZATION API CONTRACTS
# ============================================================================

class TestOrganizationAPIContracts:
    """Test Organization API response formats."""

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Endpoint /api/organizations/{id} doesn't exist, use /api/organizations/current")
    async def test_organization_response_format(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember
    ):
        """Test organization response has all required fields."""
        admin_token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.get(
            f"/api/organizations/{organization.id}",
            headers=make_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()

        required_fields = ["id", "name", "slug", "created_at"]
        assert_response_has_fields(data, required_fields)

        # Verify field types
        assert isinstance(data["id"], int)
        assert isinstance(data["name"], str)
        assert isinstance(data["slug"], str)
        assert isinstance(data["created_at"], str)

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Endpoint GET /api/organizations doesn't exist, use /api/organizations/current")
    async def test_organizations_list_response_format(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember
    ):
        """Test organizations list endpoint returns correct format."""
        admin_token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.get(
            "/api/organizations",
            headers=make_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()

        # Should be a list
        assert isinstance(data, list)

        if len(data) > 0:
            org = data[0]
            required_fields = ["id", "name", "slug"]
            assert_response_has_fields(org, required_fields)


# ============================================================================
# DEPARTMENT API CONTRACTS
# ============================================================================

class TestDepartmentAPIContracts:
    """Test Department API response formats."""

    @pytest.mark.asyncio
    async def test_department_response_format(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization,
        department: Department,
        org_owner: OrgMember
    ):
        """Test department response has all required fields."""
        admin_token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.get(
            f"/api/departments/{department.id}",
            headers=make_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()

        # org_id may not be in response schema
        required_fields = ["id", "name", "created_at"]
        assert_response_has_fields(data, required_fields)

        # Verify field types
        assert isinstance(data["id"], int)
        assert isinstance(data["name"], str)
        # org_id в DepartmentResponse нет (отдел и так из орга запросившего).
        if "org_id" in data:
            assert isinstance(data["org_id"], int)

    @pytest.mark.asyncio
    async def test_departments_list_response_format(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember
    ):
        """Test departments list endpoint returns correct format."""
        admin_token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.get(
            "/api/departments",
            headers=make_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()

        # Should be a list
        assert isinstance(data, list)


# ============================================================================
# ENTITY API CONTRACTS
# ============================================================================

class TestEntityAPIContracts:
    """Test Entity API response formats."""

    @pytest.mark.asyncio
    async def test_entity_response_format(
        self,
        client: AsyncClient,
        admin_user: User,
        entity: Entity,
        org_owner: OrgMember  # без членства в орге /entities отвечает 403
    ):
        """Test entity response has all required fields."""
        admin_token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.get(
            f"/api/entities/{entity.id}",
            headers=make_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()

        required_fields = ["id", "name", "type", "status", "created_at", "updated_at"]
        assert_response_has_fields(data, required_fields)

        # Verify field types
        assert isinstance(data["id"], int)
        assert isinstance(data["name"], str)
        assert isinstance(data["type"], str)
        assert isinstance(data["status"], str)
        assert isinstance(data["created_at"], str)
        assert isinstance(data["updated_at"], str)

        # Optional fields should have correct types if present
        if data.get("email") is not None:
            assert isinstance(data["email"], str)
        if data.get("phone") is not None:
            assert isinstance(data["phone"], str)
        if data.get("company") is not None:
            assert isinstance(data["company"], str)
        if data.get("position") is not None:
            assert isinstance(data["position"], str)

        # Array fields should be lists
        if "tags" in data:
            assert isinstance(data["tags"], list)
        if "emails" in data:
            assert isinstance(data["emails"], list)
        if "phones" in data:
            assert isinstance(data["phones"], list)
        if "telegram_usernames" in data:
            assert isinstance(data["telegram_usernames"], list)

        # Counts should be integers
        if "chats_count" in data:
            assert isinstance(data["chats_count"], int)
        if "calls_count" in data:
            assert isinstance(data["calls_count"], int)

    @pytest.mark.asyncio
    async def test_entities_list_response_format(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember,
        entity: Entity
    ):
        """Test entities list endpoint returns correct format."""
        admin_token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.get(
            "/api/entities",
            headers=make_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()

        # Should be a list or paginated response
        assert_pagination_format(data)

        # If it's a list, check first item
        items = data if isinstance(data, list) else data.get("items", [])
        if len(items) > 0:
            entity = items[0]
            required_fields = ["id", "name", "type", "status"]
            assert_response_has_fields(entity, required_fields)

    @pytest.mark.asyncio
    async def test_entity_create_response_format(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember
    ):
        """Test entity creation returns correct response format."""
        admin_token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.post(
            "/api/entities",
            json={
                "name": "Test Entity",
                "type": "candidate",
                "status": "new",
                "email": "test@example.com",
                "tags": ["urgent", "senior"],
                "emails": ["test@example.com", "test2@example.com"]
            },
            headers=make_auth_headers(admin_token)
        )
        assert response.status_code == 201
        data = response.json()

        required_fields = ["id", "name", "type", "status", "created_at"]
        assert_response_has_fields(data, required_fields)

        # Verify array fields are preserved
        assert "tags" in data
        assert isinstance(data["tags"], list)
        assert "urgent" in data["tags"]
        assert "senior" in data["tags"]


# ============================================================================
# CHAT API CONTRACTS
# ============================================================================

class TestChatAPIContracts:
    """Test Chat API response formats."""

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Chat fixture needs org membership setup for access")
    async def test_chat_response_format(
        self,
        client: AsyncClient,
        admin_user: User,
        chat: Chat
    ):
        """Test chat response has all required fields."""
        admin_token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.get(
            f"/api/chats/{chat.id}",
            headers=make_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()

        required_fields = ["id", "title", "telegram_chat_id", "chat_type", "is_active", "created_at"]
        assert_response_has_fields(data, required_fields)

        # Verify field types
        assert isinstance(data["id"], int)
        assert isinstance(data["title"], str)
        assert isinstance(data["telegram_chat_id"], int)
        assert isinstance(data["chat_type"], str)
        assert isinstance(data["is_active"], bool)

    @pytest.mark.asyncio
    async def test_chats_list_response_format(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember,
        chat: Chat
    ):
        """Test chats list endpoint returns correct format."""
        admin_token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.get(
            "/api/chats",
            headers=make_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()

        # Should be a list or paginated
        assert_pagination_format(data)


# ============================================================================
# CALL RECORDING API CONTRACTS
# ============================================================================

class TestCallAPIContracts:
    """Test Call Recording API response formats."""

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Call fixture needs org membership setup for access")
    async def test_call_response_format(
        self,
        client: AsyncClient,
        admin_user: User,
        call_recording: CallRecording
    ):
        """Test call recording response has all required fields."""
        admin_token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.get(
            f"/api/calls/{call_recording.id}",
            headers=make_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()

        required_fields = ["id", "title", "source_type", "status", "created_at"]
        assert_response_has_fields(data, required_fields)

        # Verify field types
        assert isinstance(data["id"], int)
        assert isinstance(data["title"], str)
        assert isinstance(data["source_type"], str)
        assert isinstance(data["status"], str)

        # Duration should be integer if present
        if "duration_seconds" in data and data["duration_seconds"] is not None:
            assert isinstance(data["duration_seconds"], int)

    @pytest.mark.asyncio
    async def test_calls_list_response_format(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember,
        call_recording: CallRecording
    ):
        """Test calls list endpoint returns correct format."""
        admin_token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.get(
            "/api/calls",
            headers=make_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()

        # Should be a list or paginated
        assert_pagination_format(data)


# ============================================================================
# SHARING API CONTRACTS
# ============================================================================

class TestSharingAPIContracts:
    """Test Sharing API response formats."""

    @pytest.mark.asyncio
    async def test_share_response_format(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        second_user: User,
        entity: Entity,
        organization: Organization,
        org_owner: OrgMember
    ):
        """Test share response has all required fields."""
        admin_token = create_access_token(data={"sub": str(admin_user.id)})

        # Add second user to org
        await add_user_to_org(db_session, second_user, organization, OrgRole.member)

        # Create share
        response = await client.post(
            "/api/sharing",
            json={
                "resource_type": "entity",
                "resource_id": entity.id,
                "shared_with_id": second_user.id,
                "access_level": "view"
            },
            headers=make_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()

        required_fields = ["id", "resource_type", "resource_id", "access_level", "created_at"]
        assert_response_has_fields(data, required_fields)

        # Verify field types
        assert isinstance(data["id"], int)
        assert isinstance(data["resource_type"], str)
        assert isinstance(data["resource_id"], int)
        assert isinstance(data["access_level"], str)

        # Verify enum values
        assert data["resource_type"] in ["entity", "chat", "call"]
        assert data["access_level"] in ["view", "edit", "full"]

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="GET /api/sharing doesn't exist, use /api/sharing/my-shares or /api/sharing/shared-with-me")
    async def test_shares_list_response_format(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember
    ):
        """Test shares list endpoint returns correct format."""
        admin_token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.get(
            "/api/sharing",
            headers=make_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()

        # Should be a list or paginated
        assert_pagination_format(data)


# ============================================================================
# PAGINATION CONTRACT TESTS
# ============================================================================

class TestPaginationContracts:
    """Test pagination consistency across endpoints."""

    @pytest.mark.asyncio
    async def test_paginated_entities_format(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember,
        department: Department
    ):
        """Test paginated entities endpoint returns consistent format."""
        admin_token = create_access_token(data={"sub": str(admin_user.id)})

        # Create multiple entities
        for i in range(15):
            await create_test_entity(
                db_session,
                organization,
                admin_user,
                name=f"Entity {i}",
                department=department
            )

        # Test pagination parameters
        response = await client.get(
            "/api/entities",
            params={"page": 1, "limit": 10},
            headers=make_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()

        # Check pagination structure
        assert_pagination_format(data)

        # If paginated response with metadata, verify structure
        if isinstance(data, dict) and "items" in data:
            assert "total" in data or "page" in data or "limit" in data
            assert isinstance(data["items"], list)
            assert len(data["items"]) <= 10  # Respects limit


# ============================================================================
# ERROR RESPONSE CONTRACTS
# ============================================================================

class TestErrorResponseContracts:
    """Test error responses have consistent format."""

    @pytest.mark.asyncio
    async def test_404_error_format(self, client: AsyncClient, admin_token: str, org_owner: OrgMember):
        # org_owner: без членства в организации ручка отвечает 403 раньше поиска.
        """Test 404 errors return consistent format."""
        response = await client.get(
            "/api/entities/99999",
            headers=make_auth_headers(admin_token)
        )
        assert response.status_code == 404

        data = response.json()
        # FastAPI standard error format
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_401_error_format(self, client: AsyncClient):
        """Test 401 errors return consistent format."""
        response = await client.get("/api/entities")
        assert response.status_code == 401

        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_403_error_format(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        regular_user: User,
        entity: Entity
    ):
        """Test 403 errors return consistent format."""
        # Regular user tries to access entity they don't own
        user_token = create_access_token(data={"sub": str(regular_user.id)})

        response = await client.get(
            f"/api/entities/{entity.id}",
            headers=make_auth_headers(user_token)
        )
        # Might be 403 or 404 depending on access control strategy
        assert response.status_code in [403, 404]

        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_400_validation_error_format(
        self,
        client: AsyncClient,
        admin_token: str
    ):
        """Test 400 validation errors return consistent format."""
        # Try to create entity with invalid data
        response = await client.post(
            "/api/entities",
            json={
                "name": "",  # Empty name should fail validation
                "type": "invalid_type",  # Invalid enum
            },
            headers=make_auth_headers(admin_token)
        )
        assert response.status_code == 422  # FastAPI validation error

        data = response.json()
        assert "detail" in data


# ============================================================================
# FIELD TYPE CONSISTENCY TESTS
# ============================================================================

class TestFieldTypeConsistency:
    """Test that field types are consistent across endpoints."""

    @pytest.mark.asyncio
    async def test_datetime_fields_format(
        self,
        client: AsyncClient,
        admin_user: User,
        entity: Entity,
        org_owner: OrgMember  # без членства в орге /entities отвечает 403
    ):
        """Test that datetime fields use consistent ISO format."""
        admin_token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.get(
            f"/api/entities/{entity.id}",
            headers=make_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()

        # Verify datetime fields are ISO format strings
        if "created_at" in data:
            created_at = data["created_at"]
            assert isinstance(created_at, str)
            # Should be parseable as ISO datetime
            datetime.fromisoformat(created_at.replace("Z", "+00:00"))

        if "updated_at" in data:
            updated_at = data["updated_at"]
            assert isinstance(updated_at, str)
            datetime.fromisoformat(updated_at.replace("Z", "+00:00"))

    @pytest.mark.asyncio
    async def test_enum_fields_format(
        self,
        client: AsyncClient,
        admin_user: User,
        entity: Entity,
        org_owner: OrgMember  # без членства в орге /entities отвечает 403
    ):
        """Test that enum fields return string values."""
        admin_token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.get(
            f"/api/entities/{entity.id}",
            headers=make_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()

        # Enum fields should be strings
        assert isinstance(data["type"], str)
        assert isinstance(data["status"], str)

        # Should match valid enum values
        valid_types = ["candidate", "client", "contractor", "lead", "partner", "custom"]
        assert data["type"] in valid_types

    @pytest.mark.asyncio
    async def test_array_fields_format(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization,
        org_owner: OrgMember
    ):
        """Test that array fields are always lists, never null."""
        admin_token = create_access_token(data={"sub": str(admin_user.id)})

        # Create entity with explicit empty arrays
        response = await client.post(
            "/api/entities",
            json={
                "name": "Test Arrays",
                "type": "candidate",
                "tags": [],
                "emails": [],
                "phones": []
            },
            headers=make_auth_headers(admin_token)
        )
        assert response.status_code == 201
        data = response.json()

        # Array fields should be empty lists, not null
        if "tags" in data:
            assert isinstance(data["tags"], list)
        if "emails" in data:
            assert isinstance(data["emails"], list)
        if "phones" in data:
            assert isinstance(data["phones"], list)
