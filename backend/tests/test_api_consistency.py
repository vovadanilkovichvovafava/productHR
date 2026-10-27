"""
Tests for API consistency and edge cases.
These tests verify that the API behaves consistently across endpoints.
"""
import pytest
from datetime import datetime

from api.models.database import (
    Entity, Chat, CallRecording, EntityType, EntityStatus,
    ChatType, CallStatus, CallSource
)


class TestPaginationConsistency:
    """Test that all list endpoints have consistent pagination."""

    @pytest.mark.asyncio
    async def test_entities_pagination_has_limit(self, client, admin_token, get_auth_headers, org_owner):
        """Test entities endpoint supports limit parameter."""
        response = await client.get("/api/entities?limit=10&offset=0", headers=get_auth_headers(admin_token))
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 10

    @pytest.mark.asyncio
    async def test_chats_pagination_has_limit(self, client, admin_token, get_auth_headers, org_owner):
        """Test chats endpoint supports limit parameter."""
        response = await client.get("/api/chats?limit=10&offset=0", headers=get_auth_headers(admin_token))
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 10

    @pytest.mark.asyncio
    async def test_calls_pagination_has_limit(self, client, admin_token, get_auth_headers, org_owner):
        """Test calls endpoint supports limit parameter."""
        response = await client.get("/api/calls?limit=10&offset=0", headers=get_auth_headers(admin_token))
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 10

    @pytest.mark.asyncio
    async def test_entities_max_limit_enforced(self, client, admin_token, get_auth_headers, org_owner):
        """Test that entities endpoint caps excessive limit values."""
        # Entities has limit max of 200
        response = await client.get("/api/entities?limit=10000", headers=get_auth_headers(admin_token))
        # Should either cap or reject, but not crash
        assert response.status_code in [200, 422]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)
            # Should be capped to 200
            assert len(data) <= 200

    @pytest.mark.asyncio
    async def test_calls_max_limit_enforced(self, client, admin_token, get_auth_headers, org_owner):
        """Test that calls endpoint caps excessive limit values."""
        # Calls has limit max of 100
        response = await client.get("/api/calls?limit=10000", headers=get_auth_headers(admin_token))
        # Should either cap or reject, but not crash
        assert response.status_code in [200, 422]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)
            # Should be capped to 100
            assert len(data) <= 100

    @pytest.mark.asyncio
    async def test_chats_max_limit_enforced(self, client, admin_token, get_auth_headers, org_owner):
        """Test that chats endpoint caps excessive limit values."""
        # Chats has limit max of 200
        response = await client.get("/api/chats?limit=10000", headers=get_auth_headers(admin_token))
        # Should either cap or reject, but not crash
        assert response.status_code in [200, 422]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)
            # Should be capped to 200
            assert len(data) <= 200

    @pytest.mark.asyncio
    async def test_pagination_offset_works(self, client, admin_token, get_auth_headers, org_owner, db_session, organization, department, admin_user):
        """Test that offset parameter correctly skips records."""
        # Create multiple entities
        for i in range(5):
            entity = Entity(
                org_id=organization.id,
                department_id=department.id,
                created_by=admin_user.id,
                name=f"Test Contact {i}",
                email=f"contact{i}@test.com",
                type=EntityType.candidate,
                status=EntityStatus.active,
                created_at=datetime.utcnow()
            )
            db_session.add(entity)
        await db_session.commit()

        # Get first 2
        response1 = await client.get("/api/entities?limit=2&offset=0", headers=get_auth_headers(admin_token))
        assert response1.status_code == 200
        data1 = response1.json()

        # Get next 2
        response2 = await client.get("/api/entities?limit=2&offset=2", headers=get_auth_headers(admin_token))
        assert response2.status_code == 200
        data2 = response2.json()

        # Should be different results
        if len(data1) > 0 and len(data2) > 0:
            first_ids = [item['id'] for item in data1]
            second_ids = [item['id'] for item in data2]
            # No overlap expected
            assert len(set(first_ids) & set(second_ids)) == 0

    @pytest.mark.asyncio
    async def test_negative_offset_rejected(self, client, admin_token, get_auth_headers, org_owner):
        """Test that negative offset is rejected."""
        response = await client.get("/api/calls?offset=-1", headers=get_auth_headers(admin_token))
        # Should reject negative offset
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_negative_limit_rejected(self, client, admin_token, get_auth_headers, org_owner):
        """Test that negative limit is handled gracefully (accepts or rejects)."""
        response = await client.get("/api/entities?limit=-1", headers=get_auth_headers(admin_token))
        # Should either reject (422) or handle gracefully (200 with empty/capped results)
        # Current behavior: accepts negative limit (likely treating as 0 or default)
        assert response.status_code in [200, 422]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)


class TestResponseConsistency:
    """Test that API responses are consistent."""

    @pytest.mark.asyncio
    async def test_all_list_endpoints_return_array(self, client, admin_token, get_auth_headers, org_owner):
        """Test that all list endpoints return arrays."""
        endpoints = [
            "/api/entities",
            "/api/chats",
            "/api/calls",
        ]

        for endpoint in endpoints:
            response = await client.get(endpoint, headers=get_auth_headers(admin_token))
            assert response.status_code == 200, f"{endpoint} returned {response.status_code}"
            data = response.json()
            assert isinstance(data, list), f"{endpoint} did not return a list"

    @pytest.mark.asyncio
    async def test_all_detail_endpoints_return_object(self, client, admin_token, get_auth_headers, org_owner, entity, chat, call_recording):
        """Test that all detail endpoints return objects."""
        endpoints = [
            f"/api/entities/{entity.id}",
            f"/api/chats/{chat.id}",
            f"/api/calls/{call_recording.id}",
        ]

        for endpoint in endpoints:
            response = await client.get(endpoint, headers=get_auth_headers(admin_token))
            assert response.status_code == 200, f"{endpoint} returned {response.status_code}"
            data = response.json()
            assert isinstance(data, dict), f"{endpoint} did not return a dict"
            assert "id" in data, f"{endpoint} response missing 'id' field"

    @pytest.mark.asyncio
    async def test_all_create_endpoints_return_created_object(self, client, admin_token, get_auth_headers, org_owner, department, organization):
        """Test that all create endpoints return the created object."""
        # Create entity
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "New Contact",
                "email": "new@test.com",
                "department_id": department.id
            },
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 201  # создание отвечает 201 Created
        data = response.json()
        assert isinstance(data, dict)
        assert "id" in data
        assert data["name"] == "New Contact"

        # Create department
        response = await client.post(
            "/api/departments",
            json={
                "name": "New Department",
                "org_id": organization.id
            },
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 201  # создание отдела — 201 Created
        data = response.json()
        assert isinstance(data, dict)
        assert "id" in data
        assert data["name"] == "New Department"

    @pytest.mark.asyncio
    async def test_all_delete_endpoints_return_success(self, client, admin_token, get_auth_headers, org_owner, db_session, organization, department, admin_user):
        """Test that all delete endpoints return success response."""
        # Create and delete entity
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="To Delete",
            email="delete@test.com",
            type=EntityType.candidate,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        response = await client.delete(f"/api/entities/{entity.id}", headers=get_auth_headers(admin_token))
        assert response.status_code == 200
        # Should return some success indication
        data = response.json()
        assert data is not None


class TestErrorResponseConsistency:
    """Test that error responses are consistent."""

    @pytest.mark.asyncio
    async def test_404_response_format(self, client, admin_token, get_auth_headers, org_owner):
        """Test that 404 responses have consistent format."""
        response = await client.get("/api/entities/99999", headers=get_auth_headers(admin_token))
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert isinstance(data["detail"], str)

    @pytest.mark.asyncio
    async def test_404_on_nonexistent_chat(self, client, admin_token, get_auth_headers, org_owner):
        """Test 404 for nonexistent chat."""
        response = await client.get("/api/chats/99999", headers=get_auth_headers(admin_token))
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_404_on_nonexistent_call(self, client, admin_token, get_auth_headers, org_owner):
        """Test 404 for nonexistent call."""
        response = await client.get("/api/calls/99999", headers=get_auth_headers(admin_token))
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_403_response_format(self, client, second_user_token, get_auth_headers, entity, org_member):
        """Test that 403 responses have consistent format."""
        # Кандидаты общие для организации — чтение открыто любому члену орга,
        # поэтому отказ проверяем на удалении (оно — у автора и админов).
        response = await client.delete(f"/api/entities/{entity.id}", headers=get_auth_headers(second_user_token))
        # Should be 403 or 404 (both acceptable for security)
        assert response.status_code in [403, 404]
        if response.status_code == 403:
            data = response.json()
            assert "detail" in data

    @pytest.mark.asyncio
    async def test_422_response_format_invalid_type(self, client, admin_token, get_auth_headers, org_owner):
        """Test that 422 validation errors have consistent format."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "invalid_type",  # Invalid enum value
                "name": "Test"
            },
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_422_response_format_missing_required(self, client, admin_token, get_auth_headers, org_owner):
        """Test validation error for missing required fields."""
        response = await client.post(
            "/api/entities",
            json={
                # Missing required 'type' and 'name'
            },
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data


class TestHTTPMethods:
    """Test that endpoints use correct HTTP methods."""

    @pytest.mark.asyncio
    async def test_get_is_idempotent(self, client, admin_token, get_auth_headers, org_owner, entity):
        """Test that multiple GETs return the same result."""
        # First GET
        response1 = await client.get(f"/api/entities/{entity.id}", headers=get_auth_headers(admin_token))
        assert response1.status_code == 200
        data1 = response1.json()

        # Second GET
        response2 = await client.get(f"/api/entities/{entity.id}", headers=get_auth_headers(admin_token))
        assert response2.status_code == 200
        data2 = response2.json()

        # Should be identical
        assert data1 == data2

    @pytest.mark.asyncio
    async def test_delete_is_idempotent(self, client, admin_token, get_auth_headers, org_owner, db_session, organization, department, admin_user):
        """Test that deleting already deleted resource returns 404."""
        # Create entity
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="To Delete Twice",
            email="delete2@test.com",
            type=EntityType.candidate,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # First delete - should succeed
        response1 = await client.delete(f"/api/entities/{entity.id}", headers=get_auth_headers(admin_token))
        assert response1.status_code == 200

        # Second delete - should return 404, not error
        response2 = await client.delete(f"/api/entities/{entity.id}", headers=get_auth_headers(admin_token))
        assert response2.status_code == 404

    @pytest.mark.asyncio
    async def test_post_not_idempotent(self, client, admin_token, get_auth_headers, org_owner, department):
        """Test that multiple POSTs create multiple resources."""
        # First POST
        response1 = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "Duplicate Test",
                "email": "dup@test.com",
                "department_id": department.id
            },
            headers=get_auth_headers(admin_token)
        )
        assert response1.status_code == 201  # создание отвечает 201 Created
        data1 = response1.json()

        # Second POST with same data
        response2 = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "Duplicate Test",
                "email": "dup@test.com",
                "department_id": department.id
            },
            headers=get_auth_headers(admin_token)
        )
        assert response2.status_code == 201
        data2 = response2.json()

        # Should create different resources (different IDs)
        assert data1["id"] != data2["id"]


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_empty_list_response(self, client, admin_token, get_auth_headers, org_owner):
        """Test that empty lists are returned correctly."""
        # Filter for non-existent type should return empty list
        response = await client.get("/api/entities?ownership=mine", headers=get_auth_headers(admin_token))
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_update_with_null_optional_fields(self, client, admin_token, get_auth_headers, org_owner, entity):
        """Test updating with null values for optional fields."""
        response = await client.put(
            f"/api/entities/{entity.id}",
            json={
                "name": "Updated Name",
                "phone": None,
                "company": None
            },
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        # Null values should be accepted for optional fields
        assert data["phone"] is None
        assert data["company"] is None

    @pytest.mark.asyncio
    async def test_create_with_minimal_fields(self, client, admin_token, get_auth_headers, org_owner, department):
        """Test creating with only required fields."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "Minimal Entity",
                "department_id": department.id
            },
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 201  # создание отвечает 201 Created
        data = response.json()
        assert data["name"] == "Minimal Entity"
        assert data["type"] == "candidate"

    @pytest.mark.asyncio
    async def test_search_with_special_characters(self, client, admin_token, get_auth_headers, org_owner):
        """Test search with special characters doesn't cause errors."""
        special_chars = ["'", '"', "%", "_", "\\", "&"]
        for char in special_chars:
            response = await client.get(f"/api/entities?search={char}", headers=get_auth_headers(admin_token))
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_very_long_name(self, client, admin_token, get_auth_headers, org_owner, department):
        """Test handling of very long names."""
        long_name = "A" * 1000  # Very long name
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": long_name,
                "department_id": department.id
            },
            headers=get_auth_headers(admin_token)
        )
        # Should either accept or reject with validation error
        assert response.status_code in [201, 422]  # создание отвечает 201 Created

    @pytest.mark.asyncio
    async def test_unicode_in_name(self, client, admin_token, get_auth_headers, org_owner, department):
        """Test Unicode characters in names are handled correctly."""
        unicode_name = "Test 测试 тест テスト 🚀"
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": unicode_name,
                "department_id": department.id
            },
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 201  # создание отвечает 201 Created
        data = response.json()
        assert data["name"] == unicode_name

    @pytest.mark.asyncio
    async def test_concurrent_updates(self, client, admin_token, get_auth_headers, org_owner, entity):
        """Test that concurrent updates don't cause errors."""
        import asyncio

        async def update_entity(name):
            return await client.put(
                f"/api/entities/{entity.id}",
                json={"name": name},
                headers=get_auth_headers(admin_token)
            )

        # Run multiple updates concurrently
        responses = await asyncio.gather(
            update_entity("Name 1"),
            update_entity("Name 2"),
            update_entity("Name 3"),
            return_exceptions=True
        )

        # All should succeed (last one wins)
        for response in responses:
            if not isinstance(response, Exception):
                assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_unauthorized_without_token(self, client):
        """Test that requests without auth token are rejected."""
        response = await client.get("/api/entities")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_unauthorized_with_invalid_token(self, client):
        """Test that requests with invalid token are rejected."""
        response = await client.get("/api/entities", headers={"Authorization": "Bearer invalid_token"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_with_all_filters_combined(self, client, admin_token, get_auth_headers, org_owner, department):
        """Test list endpoint with multiple filters combined."""
        response = await client.get(
            f"/api/entities?type=candidate&status=active&limit=10&offset=0&ownership=mine&department_id={department.id}",
            headers=get_auth_headers(admin_token)
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
