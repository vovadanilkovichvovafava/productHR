"""
Comprehensive tests for new backend API endpoints.

This test file provides additional coverage for:
1. POST /api/entities/parse-resume - Resume parsing
2. POST /api/entities/from-resume - Candidate creation from resume
3. GET /api/entities/search - Smart search
4. GET /api/entities/{id}/similar - Similar candidates
5. GET /api/entities/{id}/duplicates - Duplicate detection
6. POST /api/entities/{id}/merge - Entity merging
7. GET /api/entities/{id}/red-flags - Red flags analysis
8. GET /api/entities/{id}/recommended-vacancies - Vacancy recommendations
9. POST /api/scoring/calculate - AI scoring
10. POST /api/scoring/vacancy/{id}/matches - Best candidate matches
11. GET /api/search/global - Global search

Focus areas:
- Authorization checks
- Edge cases
- Error handling
- Input validation
"""
import pytest
import pytest_asyncio
import io
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import json

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.models.database import (
    User, UserRole, Organization, OrgMember, OrgRole,
    Department, Entity, EntityType, EntityStatus,
    Vacancy, VacancyStatus, VacancyApplication, ApplicationStage
)
from api.services.auth import create_access_token


# ============================================================================
# HELPER FUNCTION
# ============================================================================

def auth_headers(token: str) -> dict:
    """Create authorization headers with token."""
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# AUTHORIZATION TESTS
# ============================================================================

@pytest.mark.asyncio
class TestAuthorizationChecks:
    """Test authorization for all new endpoints."""

    async def test_parse_resume_unauthorized(self, client: AsyncClient):
        """Test /api/entities/parse-resume requires auth."""
        files = {"file": ("resume.txt", io.BytesIO(b"content"), "text/plain")}
        response = await client.post("/api/entities/parse-resume", files=files)
        assert response.status_code == 401

    async def test_from_resume_unauthorized(self, client: AsyncClient):
        """Test /api/entities/from-resume requires auth."""
        files = {"file": ("resume.txt", io.BytesIO(b"content"), "text/plain")}
        response = await client.post("/api/entities/from-resume", files=files)
        assert response.status_code == 401


    async def test_similar_candidates_unauthorized(self, client: AsyncClient):
        """Test /api/entities/{id}/similar requires auth."""
        response = await client.get("/api/entities/1/similar")
        assert response.status_code == 401

    async def test_duplicates_unauthorized(self, client: AsyncClient):
        """Test /api/entities/{id}/duplicates requires auth."""
        response = await client.get("/api/entities/1/duplicates")
        assert response.status_code == 401

    async def test_merge_unauthorized(self, client: AsyncClient):
        """Test /api/entities/{id}/merge requires auth."""
        response = await client.post(
            "/api/entities/1/merge",
            json={"source_entity_id": 2, "keep_source_data": False}
        )
        assert response.status_code == 401

    async def test_red_flags_unauthorized(self, client: AsyncClient):
        """Test /api/entities/{id}/red-flags requires auth."""
        response = await client.get("/api/entities/1/red-flags")
        assert response.status_code == 401

    async def test_recommended_vacancies_unauthorized(self, client: AsyncClient):
        """Test /api/entities/{id}/recommended-vacancies requires auth."""
        response = await client.get("/api/entities/1/recommended-vacancies")
        assert response.status_code == 401

    async def test_scoring_calculate_unauthorized(self, client: AsyncClient):
        """Test /api/scoring/calculate requires auth."""
        response = await client.post(
            "/api/scoring/calculate",
            json={"entity_id": 1, "vacancy_id": 1}
        )
        assert response.status_code == 401

    async def test_scoring_matches_unauthorized(self, client: AsyncClient):
        """Test /api/scoring/vacancy/{id}/matches requires auth."""
        response = await client.post(
            "/api/scoring/vacancy/1/matches",
            json={"limit": 10, "min_score": 0}
        )
        assert response.status_code == 401

    async def test_global_search_unauthorized(self, client: AsyncClient):
        """Test /api/search/global requires auth."""
        response = await client.get("/api/search/global", params={"query": "test"})
        assert response.status_code == 401


# ============================================================================
# NOT FOUND TESTS
# ============================================================================

@pytest.mark.asyncio
class TestNotFoundErrors:
    """Test 404 errors for all endpoints with non-existent resources."""

    @pytest_asyncio.fixture
    async def auth_token(self, admin_user, org_owner):
        """Create auth token for admin user with org membership."""
        return create_access_token({"sub": str(admin_user.id)})

    async def test_similar_entity_not_found(
        self, client: AsyncClient, auth_token
    ):
        """Test /api/entities/{id}/similar with non-existent entity."""
        response = await client.get(
            "/api/entities/99999/similar",
            headers=auth_headers(auth_token)
        )
        assert response.status_code == 404

    async def test_duplicates_entity_not_found(
        self, client: AsyncClient, auth_token
    ):
        """Test /api/entities/{id}/duplicates with non-existent entity."""
        response = await client.get(
            "/api/entities/99999/duplicates",
            headers=auth_headers(auth_token)
        )
        assert response.status_code == 404

    async def test_merge_target_not_found(
        self, client: AsyncClient, auth_token, entity
    ):
        """Test /api/entities/{id}/merge with non-existent target entity."""
        response = await client.post(
            "/api/entities/99999/merge",
            headers=auth_headers(auth_token),
            json={"source_entity_id": entity.id, "keep_source_data": False}
        )
        assert response.status_code == 404

    async def test_merge_source_not_found(
        self, client: AsyncClient, auth_token, entity
    ):
        """Test /api/entities/{id}/merge with non-existent source entity."""
        response = await client.post(
            f"/api/entities/{entity.id}/merge",
            headers=auth_headers(auth_token),
            json={"source_entity_id": 99999, "keep_source_data": False}
        )
        assert response.status_code == 404

    async def test_red_flags_entity_not_found(
        self, client: AsyncClient, auth_token
    ):
        """Test /api/entities/{id}/red-flags with non-existent entity."""
        response = await client.get(
            "/api/entities/99999/red-flags",
            headers=auth_headers(auth_token)
        )
        assert response.status_code == 404

    async def test_recommended_vacancies_entity_not_found(
        self, client: AsyncClient, auth_token
    ):
        """Test /api/entities/{id}/recommended-vacancies with non-existent entity."""
        response = await client.get(
            "/api/entities/99999/recommended-vacancies",
            headers=auth_headers(auth_token)
        )
        assert response.status_code == 404

    async def test_scoring_entity_not_found(
        self, client: AsyncClient, auth_token, db_session, organization
    ):
        """Test /api/scoring/calculate with non-existent entity."""
        # Create a vacancy for testing
        vacancy = Vacancy(
            org_id=organization.id,
            title="Test Vacancy",
            status=VacancyStatus.open
        )
        db_session.add(vacancy)
        await db_session.commit()
        await db_session.refresh(vacancy)

        response = await client.post(
            "/api/scoring/calculate",
            headers=auth_headers(auth_token),
            json={"entity_id": 99999, "vacancy_id": vacancy.id}
        )
        assert response.status_code == 404

    async def test_scoring_vacancy_not_found(
        self, client: AsyncClient, auth_token, entity
    ):
        """Test /api/scoring/calculate with non-existent vacancy."""
        response = await client.post(
            "/api/scoring/calculate",
            headers=auth_headers(auth_token),
            json={"entity_id": entity.id, "vacancy_id": 99999}
        )
        assert response.status_code == 404

    async def test_scoring_matches_vacancy_not_found(
        self, client: AsyncClient, auth_token
    ):
        """Test /api/scoring/vacancy/{id}/matches with non-existent vacancy."""
        response = await client.post(
            "/api/scoring/vacancy/99999/matches",
            headers=auth_headers(auth_token),
            json={"limit": 10, "min_score": 0}
        )
        assert response.status_code == 404


# ============================================================================
# VALIDATION TESTS
# ============================================================================

@pytest.mark.asyncio
class TestValidationErrors:
    """Test input validation for all endpoints."""

    @pytest_asyncio.fixture
    async def auth_token(self, admin_user, org_owner):
        """Create auth token for admin user with org membership."""
        return create_access_token({"sub": str(admin_user.id)})



    async def test_global_search_empty_query(
        self, client: AsyncClient, auth_token
    ):
        """Test /api/search/global with empty query."""
        response = await client.get(
            "/api/search/global",
            params={"query": ""},
            headers=auth_headers(auth_token)
        )
        assert response.status_code == 422

    async def test_global_search_limit_too_high(
        self, client: AsyncClient, auth_token
    ):
        """Test /api/search/global with limit exceeding maximum."""
        response = await client.get(
            "/api/search/global",
            params={"query": "test", "limit": 100},  # Max is 20
            headers=auth_headers(auth_token)
        )
        assert response.status_code == 422

    async def test_similar_candidates_limit_too_high(
        self, client: AsyncClient, auth_token, entity
    ):
        """Test /api/entities/{id}/similar with limit exceeding maximum."""
        response = await client.get(
            f"/api/entities/{entity.id}/similar",
            params={"limit": 100},  # Max is 50
            headers=auth_headers(auth_token)
        )
        assert response.status_code == 422

    async def test_recommended_vacancies_limit_too_high(
        self, client: AsyncClient, auth_token, entity
    ):
        """Test /api/entities/{id}/recommended-vacancies with limit exceeding maximum."""
        response = await client.get(
            f"/api/entities/{entity.id}/recommended-vacancies",
            params={"limit": 100},  # Max is 20
            headers=auth_headers(auth_token)
        )
        assert response.status_code == 422

    async def test_parse_resume_unsupported_format(
        self, client: AsyncClient, auth_token
    ):
        """Test /api/entities/parse-resume with unsupported file format."""
        files = {"file": ("resume.exe", io.BytesIO(b"binary"), "application/octet-stream")}
        response = await client.post(
            "/api/entities/parse-resume",
            files=files,
            headers=auth_headers(auth_token)
        )
        assert response.status_code == 400


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases for all endpoints."""

    @pytest_asyncio.fixture
    async def auth_token(self, admin_user, org_owner):
        """Create auth token for admin user with org membership."""
        return create_access_token({"sub": str(admin_user.id)})

    @pytest_asyncio.fixture
    async def candidate_entity(
        self, db_session, organization, department, admin_user, org_owner
    ):
        """Create a candidate entity for testing."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Test Candidate",
            email="candidate@test.com",
            type=EntityType.candidate,
            status=EntityStatus.active,
            extra_data={"skills": ["Python", "FastAPI"]},
            expected_salary_min=100000,
            expected_salary_max=150000,
            expected_salary_currency="RUB"
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)
        return entity

    @pytest_asyncio.fixture
    async def client_entity(
        self, db_session, organization, department, admin_user, org_owner
    ):
        """Create a client entity for testing."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Test Client",
            email="client@test.com",
            type=EntityType.client,
            status=EntityStatus.active
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)
        return entity

    @pytest_asyncio.fixture
    async def test_vacancy(
        self, db_session, organization, admin_user, org_owner
    ):
        """Create a test vacancy."""
        vacancy = Vacancy(
            org_id=organization.id,
            title="Python Developer",
            status=VacancyStatus.open,
            salary_min=120000,
            salary_max=180000,
            salary_currency="RUB",
            requirements="Python, FastAPI, PostgreSQL"
        )
        db_session.add(vacancy)
        await db_session.commit()
        await db_session.refresh(vacancy)
        return vacancy

    async def test_similar_candidates_for_non_candidate(
        self, client: AsyncClient, auth_token, client_entity
    ):
        """Test /api/entities/{id}/similar returns 400 for non-candidate."""
        response = await client.get(
            f"/api/entities/{client_entity.id}/similar",
            headers=auth_headers(auth_token)
        )
        assert response.status_code == 400
        # Ручка похожих отвечает по-английски («only available for candidates»).
        detail = response.json()["detail"].lower()
        assert "кандидат" in detail or "candidates" in detail

    async def test_recommended_vacancies_for_non_candidate(
        self, client: AsyncClient, auth_token, client_entity
    ):
        """Test /api/entities/{id}/recommended-vacancies returns 400 for non-candidate."""
        response = await client.get(
            f"/api/entities/{client_entity.id}/recommended-vacancies",
            headers=auth_headers(auth_token)
        )
        assert response.status_code == 400

    async def test_scoring_for_non_candidate(
        self, client: AsyncClient, auth_token, client_entity, test_vacancy
    ):
        """Test /api/scoring/calculate returns 400 for non-candidate."""
        response = await client.post(
            "/api/scoring/calculate",
            headers=auth_headers(auth_token),
            json={"entity_id": client_entity.id, "vacancy_id": test_vacancy.id}
        )
        assert response.status_code == 400
        assert "кандидатов" in response.json()["detail"].lower()

    async def test_merge_entity_with_itself(
        self, client: AsyncClient, auth_token, candidate_entity
    ):
        """Test /api/entities/{id}/merge returns 400 when merging with itself."""
        response = await client.post(
            f"/api/entities/{candidate_entity.id}/merge",
            headers=auth_headers(auth_token),
            json={"source_entity_id": candidate_entity.id, "keep_source_data": False}
        )
        assert response.status_code == 400
        # Слияние отвечает по-английски («Cannot merge entity with itself»).
        detail = response.json()["detail"].lower()
        assert "саму с собой" in detail or "itself" in detail


    async def test_global_search_no_results(
        self, client: AsyncClient, auth_token
    ):
        """Test /api/search/global with query that has no matches."""
        response = await client.get(
            "/api/search/global",
            params={"query": "xyznonexistent12345"},
            headers=auth_headers(auth_token)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["candidates"] == []
        assert data["vacancies"] == []
        assert data["total"] == 0


# ============================================================================
# RESPONSE FORMAT TESTS
# ============================================================================

@pytest.mark.asyncio
class TestResponseFormats:
    """Test that all endpoints return correctly formatted responses."""

    @pytest_asyncio.fixture
    async def auth_token(self, admin_user, org_owner):
        """Create auth token for admin user with org membership."""
        return create_access_token({"sub": str(admin_user.id)})

    @pytest_asyncio.fixture
    async def candidate_with_data(
        self, db_session, organization, department, admin_user, org_owner
    ):
        """Create a candidate entity with comprehensive data."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Full Data Candidate",
            email="full@test.com",
            phone="+79991234567",
            type=EntityType.candidate,
            status=EntityStatus.interview,
            position="Python Developer",
            company="Test Corp",
            tags=["python", "backend"],
            extra_data={
                "skills": ["Python", "FastAPI", "Django", "PostgreSQL"],
                "experience_years": 5,
                "location": "Moscow",
                "education": [{"institution": "MSU", "degree": "CS"}],
                "experience": [
                    {"company": "Tech Corp", "start_date": "2020-01", "end_date": "2023-01"}
                ]
            },
            expected_salary_min=150000,
            expected_salary_max=250000,
            expected_salary_currency="RUB",
            ai_summary="Experienced Python developer"
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)
        return entity

    @pytest_asyncio.fixture
    async def open_vacancy(
        self, db_session, organization, admin_user, org_owner
    ):
        """Create an open vacancy for testing."""
        vacancy = Vacancy(
            org_id=organization.id,
            title="Senior Python Developer",
            description="Looking for experienced Python developer",
            requirements="Python, FastAPI, PostgreSQL, 5+ years",
            status=VacancyStatus.open,
            salary_min=180000,
            salary_max=300000,
            salary_currency="RUB",
            location="Moscow"
        )
        db_session.add(vacancy)
        await db_session.commit()
        await db_session.refresh(vacancy)
        return vacancy


    async def test_red_flags_response_format(
        self, client: AsyncClient, auth_token, candidate_with_data
    ):
        """Test /api/entities/{id}/red-flags returns correct response format."""
        response = await client.get(
            f"/api/entities/{candidate_with_data.id}/red-flags",
            headers=auth_headers(auth_token)
        )
        assert response.status_code == 200
        data = response.json()

        # Check required fields
        assert "flags" in data
        assert "risk_score" in data
        assert "summary" in data
        assert "flags_count" in data

        # Check that risk_score is in valid range
        assert 0 <= data["risk_score"] <= 100

        # Check flags format if any exist
        if data["flags"]:
            flag = data["flags"][0]
            assert "type" in flag
            assert "severity" in flag
            assert "description" in flag

    async def test_recommended_vacancies_response_format(
        self, client: AsyncClient, auth_token, candidate_with_data, open_vacancy
    ):
        """Test /api/entities/{id}/recommended-vacancies returns correct response format."""
        response = await client.get(
            f"/api/entities/{candidate_with_data.id}/recommended-vacancies",
            headers=auth_headers(auth_token)
        )
        assert response.status_code == 200
        data = response.json()

        # Response should be a list
        assert isinstance(data, list)

        # Check item format if any recommendations exist
        if data:
            rec = data[0]
            assert "vacancy_id" in rec
            assert "vacancy_title" in rec
            assert "match_score" in rec
            assert "match_reasons" in rec


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

@pytest.mark.asyncio
class TestIntegrationScenarios:
    """Integration tests for complete workflows."""

    @pytest_asyncio.fixture
    async def auth_token(self, admin_user, org_owner):
        """Create auth token for admin user with org membership."""
        return create_access_token({"sub": str(admin_user.id)})

    @pytest_asyncio.fixture
    async def similar_candidates(
        self, db_session, organization, department, admin_user, org_owner
    ):
        """Create two similar candidates for testing."""
        base_data = {
            "org_id": organization.id,
            "department_id": department.id,
            "created_by": admin_user.id,
            "type": EntityType.candidate,
            "status": EntityStatus.active
        }

        candidate1 = Entity(
            name="Ivan Petrov",
            email="ivan@test.com",
            phone="+79991111111",
            extra_data={"skills": ["Python", "Django", "PostgreSQL"]},
            expected_salary_min=150000,
            expected_salary_max=200000,
            expected_salary_currency="RUB",
            **base_data
        )

        candidate2 = Entity(
            name="Ivan P.",
            email="ivan.p@test.com",
            phone="+79991111111",  # Same phone - potential duplicate
            extra_data={"skills": ["Python", "FastAPI", "PostgreSQL"]},
            expected_salary_min=160000,
            expected_salary_max=220000,
            expected_salary_currency="RUB",
            **base_data
        )

        db_session.add_all([candidate1, candidate2])
        await db_session.commit()
        for c in [candidate1, candidate2]:
            await db_session.refresh(c)
        return [candidate1, candidate2]

    async def test_find_and_merge_duplicates(
        self, client: AsyncClient, auth_token, similar_candidates, db_session
    ):
        """Test workflow: find duplicates and merge them."""
        candidate1, candidate2 = similar_candidates

        # Step 1: Find duplicates
        response = await client.get(
            f"/api/entities/{candidate1.id}/duplicates",
            headers=auth_headers(auth_token)
        )
        assert response.status_code == 200
        duplicates = response.json()

        # Step 2: If duplicate found, merge them
        if duplicates:
            dup_ids = [d["entity_id"] for d in duplicates]
            if candidate2.id in dup_ids:
                merge_response = await client.post(
                    f"/api/entities/{candidate1.id}/merge",
                    headers=auth_headers(auth_token),
                    json={"source_entity_id": candidate2.id, "keep_source_data": True}
                )
                assert merge_response.status_code == 200

                merge_data = merge_response.json()
                assert merge_data["success"] is True
                assert merge_data["merged_entity_id"] == candidate1.id

                # Verify source was deleted
                result = await db_session.execute(
                    select(Entity).where(Entity.id == candidate2.id)
                )
                deleted_entity = result.scalar_one_or_none()
                assert deleted_entity is None

