"""
Tests for Entity expected salary fields.
Tests cover CRUD operations with salary fields for candidates.
"""
import pytest
from sqlalchemy import select

from api.models.database import (
    Entity, EntityType, EntityStatus
)


class TestEntitySalaryFields:
    """Test entity salary fields functionality."""

    @pytest.mark.asyncio
    async def test_create_entity_with_salary(
        self, db_session, client, admin_user, admin_token,
        organization, department, get_auth_headers, org_owner
    ):
        """Test creating a candidate entity with expected salary fields."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "John Developer",
                "status": "new",
                "email": "john@example.com",
                "position": "Senior Developer",
                "expected_salary_min": 150000,
                "expected_salary_max": 200000,
                "expected_salary_currency": "RUB"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "John Developer"
        assert data["expected_salary_min"] == 150000
        assert data["expected_salary_max"] == 200000
        assert data["expected_salary_currency"] == "RUB"

    @pytest.mark.asyncio
    async def test_create_entity_with_usd_salary(
        self, db_session, client, admin_user, admin_token,
        organization, department, get_auth_headers, org_owner
    ):
        """Test creating a candidate entity with USD salary."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "Jane Engineer",
                "expected_salary_min": 5000,
                "expected_salary_max": 7000,
                "expected_salary_currency": "USD"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["expected_salary_min"] == 5000
        assert data["expected_salary_max"] == 7000
        assert data["expected_salary_currency"] == "USD"

    @pytest.mark.asyncio
    async def test_create_entity_without_salary(
        self, db_session, client, admin_user, admin_token,
        organization, department, get_auth_headers, org_owner
    ):
        """Test creating a candidate entity without salary (default currency)."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "Bob Designer"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["expected_salary_min"] is None
        assert data["expected_salary_max"] is None
        assert data["expected_salary_currency"] == "RUB"

    @pytest.mark.asyncio
    async def test_create_entity_with_only_min_salary(
        self, db_session, client, admin_user, admin_token,
        organization, department, get_auth_headers, org_owner
    ):
        """Test creating entity with only minimum salary specified."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "Min Salary Person",
                "expected_salary_min": 100000
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["expected_salary_min"] == 100000
        assert data["expected_salary_max"] is None
        assert data["expected_salary_currency"] == "RUB"

    @pytest.mark.asyncio
    async def test_create_entity_with_only_max_salary(
        self, db_session, client, admin_user, admin_token,
        organization, department, get_auth_headers, org_owner
    ):
        """Test creating entity with only maximum salary specified."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "Max Salary Person",
                "expected_salary_max": 250000
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["expected_salary_min"] is None
        assert data["expected_salary_max"] == 250000
        assert data["expected_salary_currency"] == "RUB"

    @pytest.mark.asyncio
    async def test_update_entity_salary(
        self, db_session, client, admin_user, admin_token,
        organization, department, get_auth_headers, org_owner
    ):
        """Test updating entity salary fields."""
        # Create entity without salary
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Update Salary Test",
            type=EntityType.candidate,
            status=EntityStatus.new
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # Update with salary
        response = await client.put(
            f"/api/entities/{entity.id}",
            json={
                "expected_salary_min": 120000,
                "expected_salary_max": 180000,
                "expected_salary_currency": "EUR"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["expected_salary_min"] == 120000
        assert data["expected_salary_max"] == 180000
        assert data["expected_salary_currency"] == "EUR"

    @pytest.mark.asyncio
    async def test_get_entity_with_salary(
        self, db_session, client, admin_user, admin_token,
        organization, department, get_auth_headers, org_owner
    ):
        """Test getting entity includes salary fields."""
        # Create entity with salary
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Get Salary Test",
            type=EntityType.candidate,
            status=EntityStatus.new,
            expected_salary_min=80000,
            expected_salary_max=120000,
            expected_salary_currency="USD"
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # Get entity
        response = await client.get(
            f"/api/entities/{entity.id}",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["expected_salary_min"] == 80000
        assert data["expected_salary_max"] == 120000
        assert data["expected_salary_currency"] == "USD"

    @pytest.mark.asyncio
    async def test_list_entities_includes_salary(
        self, db_session, client, admin_user, admin_token,
        organization, department, get_auth_headers, org_owner
    ):
        """Test listing entities includes salary fields."""
        # Create entity with salary
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="List Salary Test",
            type=EntityType.candidate,
            status=EntityStatus.new,
            expected_salary_min=200000,
            expected_salary_max=300000,
            expected_salary_currency="RUB"
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # List entities
        response = await client.get(
            "/api/entities",
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()

        # Find our entity in the list
        entity_data = next((e for e in data if e["id"] == entity.id), None)
        assert entity_data is not None
        assert entity_data["expected_salary_min"] == 200000
        assert entity_data["expected_salary_max"] == 300000
        assert entity_data["expected_salary_currency"] == "RUB"

    @pytest.mark.asyncio
    async def test_clear_salary_on_update(
        self, db_session, client, admin_user, admin_token,
        organization, department, get_auth_headers, org_owner
    ):
        """Test clearing salary fields by setting to None."""
        # Create entity with salary
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Clear Salary Test",
            type=EntityType.candidate,
            status=EntityStatus.new,
            expected_salary_min=100000,
            expected_salary_max=150000,
            expected_salary_currency="RUB"
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # Update to clear salary min
        response = await client.put(
            f"/api/entities/{entity.id}",
            json={
                "expected_salary_min": None,
                "expected_salary_max": None
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["expected_salary_min"] is None
        assert data["expected_salary_max"] is None

    @pytest.mark.asyncio
    async def test_non_candidate_entity_salary(
        self, db_session, client, admin_user, admin_token,
        organization, department, get_auth_headers, org_owner
    ):
        """Test that salary fields work for non-candidate entities too."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "contractor",
                "name": "Contractor with Rate",
                "expected_salary_min": 3000,
                "expected_salary_max": 5000,
                "expected_salary_currency": "USD"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["type"] == "contractor"
        assert data["expected_salary_min"] == 3000
        assert data["expected_salary_max"] == 5000
        assert data["expected_salary_currency"] == "USD"
