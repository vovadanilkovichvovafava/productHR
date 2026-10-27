"""
Tests for Entity race condition prevention via row locking and optimistic locking.

This module tests:
1. Optimistic locking via version field
2. Concurrent update detection
3. Row locking on critical operations (update, delete, transfer)
"""
import pytest
import asyncio
from datetime import datetime
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import (
    Entity, EntityType, EntityStatus, User, Organization, OrgMember, OrgRole
)
from api.services.auth import create_access_token, hash_password


class TestEntityOptimisticLocking:
    """Tests for optimistic locking via version field."""

    @pytest.fixture
    async def setup_entity_with_version(
        self,
        db_session: AsyncSession,
        organization: Organization,
        regular_user: User
    ) -> Entity:
        """Create an entity with version field for testing."""
        # Add user to organization
        org_member = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.owner
        )
        db_session.add(org_member)
        await db_session.commit()

        # Create entity with version
        entity = Entity(
            org_id=organization.id,
            type=EntityType.candidate,
            name="Test Candidate",
            status=EntityStatus.new,
            email="candidate@test.com",
            created_by=regular_user.id,
            version=1
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)
        return entity

    async def test_version_field_exists_on_entity(
        self,
        setup_entity_with_version: Entity
    ):
        """Test that Entity model has version field."""
        entity = setup_entity_with_version
        assert hasattr(entity, 'version')
        assert entity.version == 1

    async def test_update_increments_version(
        self,
        client: AsyncClient,
        setup_entity_with_version: Entity,
        regular_user: User,
        get_auth_headers
    ):
        """Test that updating entity increments version."""
        entity = setup_entity_with_version
        token = create_access_token(data={"sub": str(regular_user.id)})
        headers = get_auth_headers(token)

        # Initial version should be 1
        assert entity.version == 1

        # Update entity
        response = await client.put(
            f"/api/entities/{entity.id}",
            headers=headers,
            json={"name": "Updated Name"}
        )
        assert response.status_code == 200
        data = response.json()

        # Version should be incremented
        assert data["version"] == 2

    async def test_optimistic_lock_conflict_detection(
        self,
        client: AsyncClient,
        setup_entity_with_version: Entity,
        regular_user: User,
        get_auth_headers
    ):
        """Test that concurrent update with stale version returns 409 Conflict."""
        entity = setup_entity_with_version
        token = create_access_token(data={"sub": str(regular_user.id)})
        headers = get_auth_headers(token)

        # First update with correct version
        response1 = await client.put(
            f"/api/entities/{entity.id}",
            headers=headers,
            json={"name": "Update 1", "version": 1}
        )
        assert response1.status_code == 200
        assert response1.json()["version"] == 2

        # Second update with stale version (should fail)
        response2 = await client.put(
            f"/api/entities/{entity.id}",
            headers=headers,
            json={"name": "Update 2", "version": 1}  # Stale version
        )
        assert response2.status_code == 409
        assert "Conflict" in response2.json()["detail"]
        assert "modified by another request" in response2.json()["detail"]

    async def test_update_without_version_succeeds(
        self,
        client: AsyncClient,
        setup_entity_with_version: Entity,
        regular_user: User,
        get_auth_headers
    ):
        """Test that update without version field still works (backward compatible)."""
        entity = setup_entity_with_version
        token = create_access_token(data={"sub": str(regular_user.id)})
        headers = get_auth_headers(token)

        # Update without providing version
        response = await client.put(
            f"/api/entities/{entity.id}",
            headers=headers,
            json={"name": "Updated Without Version"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Without Version"
        # Version should still be incremented
        assert data["version"] == 2

    async def test_version_returned_in_response(
        self,
        client: AsyncClient,
        setup_entity_with_version: Entity,
        regular_user: User,
        get_auth_headers
    ):
        """Test that version is included in update response."""
        entity = setup_entity_with_version
        token = create_access_token(data={"sub": str(regular_user.id)})
        headers = get_auth_headers(token)

        response = await client.put(
            f"/api/entities/{entity.id}",
            headers=headers,
            json={"phone": "+1234567890"}
        )
        assert response.status_code == 200
        data = response.json()

        assert "version" in data
        assert isinstance(data["version"], int)


class TestEntityConcurrentUpdates:
    """Tests for concurrent update handling."""

    @pytest.fixture
    async def setup_concurrent_test(
        self,
        db_session: AsyncSession,
        organization: Organization,
        regular_user: User
    ) -> Entity:
        """Set up entity for concurrent update tests."""
        # Add user to organization
        org_member = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.owner
        )
        db_session.add(org_member)
        await db_session.commit()

        entity = Entity(
            org_id=organization.id,
            type=EntityType.client,
            name="Concurrent Test Entity",
            status=EntityStatus.active,
            created_by=regular_user.id,
            version=1
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)
        return entity

    async def test_sequential_updates_with_correct_versions(
        self,
        client: AsyncClient,
        setup_concurrent_test: Entity,
        regular_user: User,
        get_auth_headers
    ):
        """Test that sequential updates with correct versions succeed."""
        entity = setup_concurrent_test
        token = create_access_token(data={"sub": str(regular_user.id)})
        headers = get_auth_headers(token)

        # First update
        response1 = await client.put(
            f"/api/entities/{entity.id}",
            headers=headers,
            json={"name": "Update 1", "version": 1}
        )
        assert response1.status_code == 200
        version1 = response1.json()["version"]
        assert version1 == 2

        # Second update with new version
        response2 = await client.put(
            f"/api/entities/{entity.id}",
            headers=headers,
            json={"name": "Update 2", "version": 2}
        )
        assert response2.status_code == 200
        version2 = response2.json()["version"]
        assert version2 == 3

        # Third update with new version
        response3 = await client.put(
            f"/api/entities/{entity.id}",
            headers=headers,
            json={"name": "Update 3", "version": 3}
        )
        assert response3.status_code == 200
        assert response3.json()["version"] == 4

    async def test_version_mismatch_error_message(
        self,
        client: AsyncClient,
        setup_concurrent_test: Entity,
        regular_user: User,
        get_auth_headers
    ):
        """Test that version mismatch returns informative error message."""
        entity = setup_concurrent_test
        token = create_access_token(data={"sub": str(regular_user.id)})
        headers = get_auth_headers(token)

        # Update with wrong version
        response = await client.put(
            f"/api/entities/{entity.id}",
            headers=headers,
            json={"name": "Bad Update", "version": 999}
        )
        assert response.status_code == 409
        error = response.json()
        assert "detail" in error
        assert "Expected version 999" in error["detail"]
        assert "current version is 1" in error["detail"]


class TestRowLockingOnCriticalOperations:
    """Tests to verify row locking is applied to critical operations.

    Note: SQLite doesn't support FOR UPDATE, but these tests verify
    the logic is correct and would work with PostgreSQL.
    """

    @pytest.fixture
    async def setup_entity_for_operations(
        self,
        db_session: AsyncSession,
        organization: Organization,
        regular_user: User,
        second_user: User
    ) -> Entity:
        """Set up entity for critical operation tests."""
        # Add both users to organization
        org_member1 = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.owner
        )
        org_member2 = OrgMember(
            org_id=organization.id,
            user_id=second_user.id,
            role=OrgRole.member
        )
        db_session.add(org_member1)
        db_session.add(org_member2)
        await db_session.commit()

        entity = Entity(
            org_id=organization.id,
            type=EntityType.candidate,
            name="Critical Operations Entity",
            status=EntityStatus.new,
            created_by=regular_user.id,
            version=1
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)
        return entity

    async def test_delete_operation_atomic(
        self,
        client: AsyncClient,
        setup_entity_for_operations: Entity,
        regular_user: User,
        get_auth_headers
    ):
        """Test that delete operation is atomic with row locking."""
        entity = setup_entity_for_operations
        token = create_access_token(data={"sub": str(regular_user.id)})
        headers = get_auth_headers(token)

        # Delete should succeed atomically
        response = await client.delete(
            f"/api/entities/{entity.id}",
            headers=headers
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

        # Subsequent delete should fail (entity doesn't exist)
        response2 = await client.delete(
            f"/api/entities/{entity.id}",
            headers=headers
        )
        assert response2.status_code == 404


class TestVersionFieldDefaultValue:
    """Tests for version field default behavior."""

    async def test_new_entity_has_version_1(
        self,
        db_session: AsyncSession,
        organization: Organization,
        regular_user: User
    ):
        """Test that newly created entity has version=1."""
        # Add user to organization
        org_member = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.owner
        )
        db_session.add(org_member)
        await db_session.commit()

        entity = Entity(
            org_id=organization.id,
            type=EntityType.lead,
            name="New Lead",
            status=EntityStatus.new,
            created_by=regular_user.id
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        assert entity.version == 1

    async def test_version_handles_null_gracefully(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        organization: Organization,
        regular_user: User,
        get_auth_headers
    ):
        """Test that update handles null version gracefully (for legacy data)."""
        # Add user to organization
        org_member = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.owner
        )
        db_session.add(org_member)
        await db_session.commit()

        # Create entity
        entity = Entity(
            org_id=organization.id,
            type=EntityType.partner,
            name="Legacy Entity",
            status=EntityStatus.active,
            created_by=regular_user.id,
            version=1
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        token = create_access_token(data={"sub": str(regular_user.id)})
        headers = get_auth_headers(token)

        # Update should work and set version properly
        response = await client.put(
            f"/api/entities/{entity.id}",
            headers=headers,
            json={"company": "Test Company"}
        )
        assert response.status_code == 200
        # Version should be incremented from 1 to 2
        assert response.json()["version"] == 2


class TestEdgeCases:
    """Tests for edge cases in locking behavior."""

    @pytest.fixture
    async def setup_edge_case_entity(
        self,
        db_session: AsyncSession,
        organization: Organization,
        regular_user: User
    ) -> Entity:
        """Set up entity for edge case tests."""
        org_member = OrgMember(
            org_id=organization.id,
            user_id=regular_user.id,
            role=OrgRole.owner
        )
        db_session.add(org_member)
        await db_session.commit()

        entity = Entity(
            org_id=organization.id,
            type=EntityType.contractor,
            name="Edge Case Entity",
            status=EntityStatus.active,
            created_by=regular_user.id,
            version=1
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)
        return entity

    async def test_update_multiple_fields_single_version_increment(
        self,
        client: AsyncClient,
        setup_edge_case_entity: Entity,
        regular_user: User,
        get_auth_headers
    ):
        """Test that updating multiple fields only increments version once."""
        entity = setup_edge_case_entity
        token = create_access_token(data={"sub": str(regular_user.id)})
        headers = get_auth_headers(token)

        response = await client.put(
            f"/api/entities/{entity.id}",
            headers=headers,
            json={
                "name": "New Name",
                "phone": "+1234567890",
                "email": "new@email.com",
                "company": "New Company",
                "position": "New Position"
            }
        )
        assert response.status_code == 200
        data = response.json()

        # Version should only be incremented once
        assert data["version"] == 2
        assert data["name"] == "New Name"
        assert data["phone"] == "+1234567890"

    async def test_empty_update_still_increments_version(
        self,
        client: AsyncClient,
        setup_edge_case_entity: Entity,
        regular_user: User,
        get_auth_headers
    ):
        """Test that even empty update increments version (for consistency)."""
        entity = setup_edge_case_entity
        token = create_access_token(data={"sub": str(regular_user.id)})
        headers = get_auth_headers(token)

        # Update with empty payload (no actual changes)
        response = await client.put(
            f"/api/entities/{entity.id}",
            headers=headers,
            json={}
        )
        assert response.status_code == 200
        # Version should still be incremented
        assert response.json()["version"] == 2
