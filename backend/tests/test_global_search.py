"""
Tests for global search API (Command Palette).
"""
import pytest
import pytest_asyncio
from datetime import datetime
from httpx import AsyncClient

from api.models.database import (
    User, Organization, OrgMember, Entity, Vacancy,
    UserRole, OrgRole, EntityType, EntityStatus, VacancyStatus
)
from api.services.auth import create_access_token


class TestGlobalSearch:
    """Tests for GET /api/search/global endpoint."""

    @pytest_asyncio.fixture
    async def user_with_org(self, db_session, organization, admin_user):
        """Create user with organization membership."""
        org_member = OrgMember(
            org_id=organization.id,
            user_id=admin_user.id,
            role=OrgRole.owner
        )
        db_session.add(org_member)
        await db_session.commit()
        return admin_user

    @pytest_asyncio.fixture
    def auth_headers(self, user_with_org):
        """Generate auth headers for user."""
        token = create_access_token({"sub": str(user_with_org.id)})
        return {"Authorization": f"Bearer {token}"}

    @pytest_asyncio.fixture
    async def test_candidates(self, db_session, organization, user_with_org):
        """Create test candidates."""
        candidates = []
        for i, (name, email, phone, position) in enumerate([
            ("John Doe", "john@example.com", "+1234567890", "Python Developer"),
            ("Jane Smith", "jane@example.com", "+0987654321", "Frontend Developer"),
            ("Bob Johnson", "bob@example.com", "+1122334455", "Data Analyst"),
            ("Alice Brown", "alice@example.com", "+5566778899", "Project Manager"),
        ]):
            entity = Entity(
                org_id=organization.id,
                type=EntityType.candidate,
                name=name,
                email=email,
                phone=phone,
                position=position,
                status=EntityStatus.new,
                created_by=user_with_org.id
            )
            db_session.add(entity)
            candidates.append(entity)

        await db_session.commit()
        for c in candidates:
            await db_session.refresh(c)
        return candidates

    @pytest_asyncio.fixture
    async def test_vacancies(self, db_session, organization, user_with_org):
        """Create test vacancies."""
        vacancies = []
        for title, status in [
            ("Senior Python Developer", VacancyStatus.open),
            ("Junior Frontend Developer", VacancyStatus.open),
            ("Data Scientist", VacancyStatus.paused),
            ("DevOps Engineer", VacancyStatus.draft),
            ("Closed Position", VacancyStatus.closed),  # Should not appear in search
        ]:
            vacancy = Vacancy(
                org_id=organization.id,
                title=title,
                status=status,
                created_by=user_with_org.id
            )
            db_session.add(vacancy)
            vacancies.append(vacancy)

        await db_session.commit()
        for v in vacancies:
            await db_session.refresh(v)
        return vacancies

    @pytest.mark.asyncio
    async def test_search_candidates_by_name(
        self, client: AsyncClient, auth_headers, test_candidates
    ):
        """Test searching candidates by name."""
        response = await client.get(
            "/api/search/global",
            params={"query": "John"},
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert "candidates" in data
        assert len(data["candidates"]) >= 1

        # John Doe should be in results
        names = [c["name"] for c in data["candidates"]]
        assert "John Doe" in names

    @pytest.mark.asyncio
    async def test_search_candidates_by_email(
        self, client: AsyncClient, auth_headers, test_candidates
    ):
        """Test searching candidates by email."""
        response = await client.get(
            "/api/search/global",
            params={"query": "jane@example"},
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        candidates = data["candidates"]
        # Jane Smith should be in results
        assert any(c["email"] == "jane@example.com" for c in candidates)

    @pytest.mark.asyncio
    async def test_search_candidates_by_position(
        self, client: AsyncClient, auth_headers, test_candidates
    ):
        """Test searching candidates by position."""
        response = await client.get(
            "/api/search/global",
            params={"query": "Developer"},
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Should find candidates with Developer in position
        candidates = data["candidates"]
        assert len(candidates) >= 2

    @pytest.mark.asyncio
    async def test_search_vacancies_by_title(
        self, client: AsyncClient, auth_headers, test_vacancies
    ):
        """Test searching vacancies by title."""
        response = await client.get(
            "/api/search/global",
            params={"query": "Python"},
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        vacancies = data["vacancies"]
        assert len(vacancies) >= 1
        assert any("Python" in v["title"] for v in vacancies)

    @pytest.mark.asyncio
    async def test_search_excludes_closed_vacancies(
        self, client: AsyncClient, auth_headers, test_vacancies
    ):
        """Test that closed vacancies are excluded from search."""
        response = await client.get(
            "/api/search/global",
            params={"query": "Closed"},
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Closed position should not appear
        vacancy_titles = [v["title"] for v in data["vacancies"]]
        assert "Closed Position" not in vacancy_titles

    @pytest.mark.asyncio
    async def test_search_combined_results(
        self, client: AsyncClient, auth_headers, test_candidates, test_vacancies
    ):
        """Test searching both candidates and vacancies."""
        response = await client.get(
            "/api/search/global",
            params={"query": "Developer"},
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Should have results from both categories
        assert len(data["candidates"]) >= 1
        assert len(data["vacancies"]) >= 1
        assert data["total"] >= 2

    @pytest.mark.asyncio
    async def test_search_with_limit(
        self, client: AsyncClient, auth_headers, test_candidates
    ):
        """Test search result limit."""
        response = await client.get(
            "/api/search/global",
            params={"query": "e", "limit": 2},  # 'e' matches multiple candidates
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Should respect limit per category
        assert len(data["candidates"]) <= 2
        assert len(data["vacancies"]) <= 2

    @pytest.mark.asyncio
    async def test_search_empty_query_rejected(
        self, client: AsyncClient, auth_headers
    ):
        """Test that empty query is rejected."""
        response = await client.get(
            "/api/search/global",
            params={"query": ""},
            headers=auth_headers
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_search_case_insensitive(
        self, client: AsyncClient, auth_headers, test_candidates
    ):
        """Test that search is case-insensitive."""
        response = await client.get(
            "/api/search/global",
            params={"query": "JOHN"},
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        names = [c["name"] for c in data["candidates"]]
        assert "John Doe" in names

    @pytest.mark.asyncio
    async def test_search_requires_auth(self, client: AsyncClient):
        """Test that search requires authentication."""
        response = await client.get(
            "/api/search/global",
            params={"query": "test"}
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_search_respects_org_boundaries(
        self, client: AsyncClient, db_session, auth_headers,
        test_candidates, second_organization
    ):
        """Test that search only returns results from user's org."""
        # Create candidate in different org
        other_candidate = Entity(
            org_id=second_organization.id,
            type=EntityType.candidate,
            name="Other Org User",
            email="other@other.com",
            status=EntityStatus.new
        )
        db_session.add(other_candidate)
        await db_session.commit()

        response = await client.get(
            "/api/search/global",
            params={"query": "Other Org"},
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Should not find candidate from other org
        names = [c["name"] for c in data["candidates"]]
        assert "Other Org User" not in names

    @pytest.mark.asyncio
    async def test_search_relevance_scoring(
        self, client: AsyncClient, auth_headers, test_candidates
    ):
        """Test that results have relevance scores."""
        response = await client.get(
            "/api/search/global",
            params={"query": "John"},
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        for candidate in data["candidates"]:
            assert "relevance_score" in candidate
            assert isinstance(candidate["relevance_score"], (int, float))

    @pytest.mark.asyncio
    async def test_search_returns_required_fields(
        self, client: AsyncClient, auth_headers, test_candidates, test_vacancies
    ):
        """Test that search returns all required fields."""
        response = await client.get(
            "/api/search/global",
            params={"query": "a"},  # Broad search
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Check candidate fields
        if data["candidates"]:
            candidate = data["candidates"][0]
            assert "id" in candidate
            assert "name" in candidate
            assert "status" in candidate
            assert "relevance_score" in candidate

        # Check vacancy fields
        if data["vacancies"]:
            vacancy = data["vacancies"][0]
            assert "id" in vacancy
            assert "title" in vacancy
            assert "status" in vacancy
            assert "relevance_score" in vacancy

    @pytest.mark.asyncio
    async def test_search_max_limit(self, client: AsyncClient, auth_headers):
        """Test that limit is capped at maximum value."""
        response = await client.get(
            "/api/search/global",
            params={"query": "test", "limit": 100},  # Over max
            headers=auth_headers
        )

        assert response.status_code == 422  # Validation error - limit > 20
