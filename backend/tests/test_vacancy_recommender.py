"""
Tests for Vacancy Recommender Service.

Tests cover:
- VacancyRecommendation dataclass
- CandidateMatch dataclass
- VacancyRecommenderService methods
- API endpoints for recommendations
"""

import pytest
import pytest_asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient

from api.models.database import (
    Entity, EntityType, EntityStatus,
    Vacancy, VacancyStatus, VacancyApplication, ApplicationStage,
    Organization, Department, User
)
from api.services.vacancy_recommender import (
    VacancyRecommendation,
    CandidateMatch,
    VacancyRecommenderService,
    vacancy_recommender
)


# ============================================================================
# DATACLASS TESTS
# ============================================================================

class TestVacancyRecommendation:
    """Tests for VacancyRecommendation dataclass."""

    def test_vacancy_recommendation_creation(self):
        """Test creating a VacancyRecommendation instance."""
        rec = VacancyRecommendation(
            vacancy_id=1,
            vacancy_title="Python Developer",
            match_score=85,
            match_reasons=["Skills match", "Salary compatible"],
            missing_requirements=["Docker experience"],
            salary_compatible=True
        )

        assert rec.vacancy_id == 1
        assert rec.vacancy_title == "Python Developer"
        assert rec.match_score == 85
        assert len(rec.match_reasons) == 2
        assert len(rec.missing_requirements) == 1
        assert rec.salary_compatible is True
        assert rec.location_match is True  # Default value

    def test_vacancy_recommendation_to_dict(self):
        """Test converting VacancyRecommendation to dictionary."""
        rec = VacancyRecommendation(
            vacancy_id=1,
            vacancy_title="Python Developer",
            match_score=85,
            salary_min=100000,
            salary_max=200000,
            salary_currency="RUB"
        )

        data = rec.to_dict()

        assert data["vacancy_id"] == 1
        assert data["vacancy_title"] == "Python Developer"
        assert data["match_score"] == 85
        assert data["salary_min"] == 100000
        assert data["salary_max"] == 200000
        assert data["salary_currency"] == "RUB"

    def test_vacancy_recommendation_defaults(self):
        """Test default values in VacancyRecommendation."""
        rec = VacancyRecommendation(
            vacancy_id=1,
            vacancy_title="Test",
            match_score=50
        )

        assert rec.match_reasons == []
        assert rec.missing_requirements == []
        assert rec.salary_compatible is True
        assert rec.location_match is True
        assert rec.salary_currency == "RUB"
        assert rec.applications_count == 0


class TestCandidateMatch:
    """Tests for CandidateMatch dataclass."""

    def test_candidate_match_creation(self):
        """Test creating a CandidateMatch instance."""
        match = CandidateMatch(
            entity_id=1,
            entity_name="John Doe",
            match_score=75,
            match_reasons=["Python skills"],
            missing_skills=["Docker"],
            salary_compatible=True
        )

        assert match.entity_id == 1
        assert match.entity_name == "John Doe"
        assert match.match_score == 75
        assert "Python skills" in match.match_reasons
        assert "Docker" in match.missing_skills

    def test_candidate_match_to_dict(self):
        """Test converting CandidateMatch to dictionary."""
        match = CandidateMatch(
            entity_id=1,
            entity_name="John Doe",
            match_score=75,
            email="john@example.com",
            phone="+1234567890",
            position="Senior Developer"
        )

        data = match.to_dict()

        assert data["entity_id"] == 1
        assert data["entity_name"] == "John Doe"
        assert data["email"] == "john@example.com"
        assert data["phone"] == "+1234567890"
        assert data["position"] == "Senior Developer"


# ============================================================================
# SERVICE TESTS
# ============================================================================

class TestVacancyRecommenderService:
    """Tests for VacancyRecommenderService."""

    @pytest.fixture
    def service(self):
        """Create a VacancyRecommenderService instance."""
        return VacancyRecommenderService()

    def test_extract_skills_from_text(self, service):
        """Test extracting skills from text."""
        text = "Looking for Python developer with Docker and Kubernetes experience"
        skills = service._extract_skills_from_text(text)

        assert "python" in skills
        assert "docker" in skills
        assert "kubernetes" in skills

    def test_extract_skills_from_empty_text(self, service):
        """Test extracting skills from empty/None text."""
        assert service._extract_skills_from_text(None) == []
        assert service._extract_skills_from_text("") == []

    def test_extract_skills_case_insensitive(self, service):
        """Test that skill extraction is case insensitive."""
        text = "PYTHON, JavaScript, React"
        skills = service._extract_skills_from_text(text)

        assert "python" in skills
        assert "javascript" in skills
        assert "react" in skills

    def test_calculate_match_score_full_match(self, service):
        """Test match score calculation with full skill match."""
        candidate_skills = ["python", "docker", "sql"]
        vacancy_skills = ["python", "docker", "sql"]

        score = service._calculate_match_score(
            candidate_skills,
            vacancy_skills,
            salary_compatible=True,
            location_match=True
        )

        # Full skills (60) + salary (25) + location (15) = 100
        assert score == 100

    def test_calculate_match_score_partial_match(self, service):
        """Test match score calculation with partial skill match."""
        candidate_skills = ["python", "sql"]
        vacancy_skills = ["python", "docker", "sql", "kubernetes"]

        score = service._calculate_match_score(
            candidate_skills,
            vacancy_skills,
            salary_compatible=True,
            location_match=True
        )

        # 2/4 skills (30) + salary (25) + location (15) = 70
        assert score == 70

    def test_calculate_match_score_no_skills(self, service):
        """Test match score calculation when vacancy has no skills."""
        candidate_skills = ["python"]
        vacancy_skills = []

        score = service._calculate_match_score(
            candidate_skills,
            vacancy_skills,
            salary_compatible=True,
            location_match=True
        )

        # Base score (30) + salary (25) + location (15) = 70
        assert score == 70

    def test_calculate_match_score_salary_incompatible(self, service):
        """Test match score with incompatible salary."""
        candidate_skills = ["python"]
        vacancy_skills = ["python"]

        score = service._calculate_match_score(
            candidate_skills,
            vacancy_skills,
            salary_compatible=False,
            location_match=True
        )

        # Skills (60) + location (15) = 75
        assert score == 75


# ============================================================================
# DATABASE INTEGRATION TESTS
# ============================================================================

@pytest_asyncio.fixture
async def test_vacancy(
    db_session: AsyncSession,
    organization: Organization,
    admin_user: User
) -> Vacancy:
    """Create a test vacancy."""
    vacancy = Vacancy(
        org_id=organization.id,
        title="Python Developer",
        description="Looking for experienced Python developer",
        requirements="Python, Docker, SQL, Kubernetes",
        status=VacancyStatus.open,
        salary_min=150000,
        salary_max=250000,
        salary_currency="RUB",
        created_by=admin_user.id
    )
    db_session.add(vacancy)
    await db_session.commit()
    await db_session.refresh(vacancy)
    return vacancy


@pytest_asyncio.fixture
async def candidate_with_skills(
    db_session: AsyncSession,
    organization: Organization,
    department: Department,
    admin_user: User
) -> Entity:
    """Create a candidate entity with skills."""
    entity = Entity(
        org_id=organization.id,
        department_id=department.id,
        created_by=admin_user.id,
        name="Skilled Candidate",
        email="skilled@test.com",
        type=EntityType.candidate,
        status=EntityStatus.active,
        position="Python Backend Developer",
        tags=["python", "docker", "sql"],
        expected_salary_min=140000,
        expected_salary_max=220000,
        expected_salary_currency="RUB",
        extra_data={"skills": ["python", "docker", "sql", "fastapi"]}
    )
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)
    return entity


@pytest_asyncio.fixture
async def candidate_without_skills(
    db_session: AsyncSession,
    organization: Organization,
    department: Department,
    admin_user: User
) -> Entity:
    """Create a candidate entity without matching skills."""
    entity = Entity(
        org_id=organization.id,
        department_id=department.id,
        created_by=admin_user.id,
        name="Junior Candidate",
        email="junior@test.com",
        type=EntityType.candidate,
        status=EntityStatus.active,
        position="Junior Developer"
    )
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)
    return entity


class TestVacancyRecommenderIntegration:
    """Integration tests for VacancyRecommenderService with database."""

    @pytest.mark.asyncio
    async def test_get_recommendations_for_candidate(
        self,
        db_session: AsyncSession,
        candidate_with_skills: Entity,
        test_vacancy: Vacancy,
        organization: Organization
    ):
        """Test getting recommendations for a candidate."""
        recommendations = await vacancy_recommender.get_recommendations(
            db=db_session,
            entity=candidate_with_skills,
            limit=5,
            org_id=organization.id
        )

        assert len(recommendations) > 0
        # First recommendation should be our test vacancy
        rec = recommendations[0]
        assert rec.vacancy_id == test_vacancy.id
        assert rec.match_score > 0
        assert rec.salary_compatible is True

    @pytest.mark.asyncio
    async def test_get_recommendations_non_candidate(
        self,
        db_session: AsyncSession,
        entity: Entity,  # This is a client entity from conftest
        organization: Organization
    ):
        """Test that non-candidates get empty recommendations."""
        # Entity from conftest is a candidate, so let's modify it
        entity.type = EntityType.client
        await db_session.commit()

        recommendations = await vacancy_recommender.get_recommendations(
            db=db_session,
            entity=entity,
            limit=5,
            org_id=organization.id
        )

        assert len(recommendations) == 0

    @pytest.mark.asyncio
    async def test_find_matching_candidates(
        self,
        db_session: AsyncSession,
        test_vacancy: Vacancy,
        candidate_with_skills: Entity,
        candidate_without_skills: Entity
    ):
        """Test finding matching candidates for a vacancy."""
        matches = await vacancy_recommender.find_matching_candidates(
            db=db_session,
            vacancy=test_vacancy,
            limit=10,
            exclude_applied=True
        )

        assert len(matches) >= 2
        # Skilled candidate should have higher score
        skilled_match = next((m for m in matches if m.entity_id == candidate_with_skills.id), None)
        unskilled_match = next((m for m in matches if m.entity_id == candidate_without_skills.id), None)

        assert skilled_match is not None
        assert unskilled_match is not None
        assert skilled_match.match_score > unskilled_match.match_score

    @pytest.mark.asyncio
    async def test_auto_apply(
        self,
        db_session: AsyncSession,
        candidate_with_skills: Entity,
        test_vacancy: Vacancy,
        admin_user: User
    ):
        """Test auto-applying a candidate to a vacancy."""
        application = await vacancy_recommender.auto_apply(
            db=db_session,
            entity=candidate_with_skills,
            vacancy=test_vacancy,
            source="test_auto_apply",
            created_by=admin_user.id
        )

        assert application is not None
        assert application.vacancy_id == test_vacancy.id
        assert application.entity_id == candidate_with_skills.id
        assert application.stage == ApplicationStage.applied
        assert application.source == "test_auto_apply"

    @pytest.mark.asyncio
    async def test_auto_apply_duplicate(
        self,
        db_session: AsyncSession,
        candidate_with_skills: Entity,
        test_vacancy: Vacancy,
        admin_user: User
    ):
        """Test that auto-apply doesn't create duplicate applications."""
        # First application
        first_app = await vacancy_recommender.auto_apply(
            db=db_session,
            entity=candidate_with_skills,
            vacancy=test_vacancy,
            created_by=admin_user.id
        )
        assert first_app is not None

        # Second application should return None
        second_app = await vacancy_recommender.auto_apply(
            db=db_session,
            entity=candidate_with_skills,
            vacancy=test_vacancy,
            created_by=admin_user.id
        )
        assert second_app is None

    @pytest.mark.asyncio
    async def test_notify_new_vacancy(
        self,
        db_session: AsyncSession,
        test_vacancy: Vacancy,
        candidate_with_skills: Entity,
        candidate_without_skills: Entity
    ):
        """Test finding candidates to notify about a new vacancy."""
        candidates = await vacancy_recommender.notify_new_vacancy(
            db=db_session,
            vacancy=test_vacancy,
            match_threshold=30,
            limit=20
        )

        assert len(candidates) >= 1
        # Should include at least the skilled candidate
        entity_ids = [c.entity_id for c in candidates]
        assert candidate_with_skills.id in entity_ids


# ============================================================================
# API ENDPOINT TESTS
# ============================================================================

class TestVacancyRecommendationEndpoints:
    """Tests for vacancy recommendation API endpoints."""

    @pytest.mark.asyncio
    async def test_get_recommended_vacancies_endpoint(
        self,
        client: AsyncClient,
        admin_token: str,
        candidate_with_skills: Entity,
        test_vacancy: Vacancy,
        org_owner  # Ensure admin is in org
    ):
        """Test GET /api/entities/{id}/recommended-vacancies endpoint."""
        response = await client.get(
            f"/api/entities/{candidate_with_skills.id}/recommended-vacancies",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"limit": 5}
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if len(data) > 0:
            rec = data[0]
            assert "vacancy_id" in rec
            assert "match_score" in rec
            assert "match_reasons" in rec

    @pytest.mark.asyncio
    async def test_get_recommended_vacancies_non_candidate(
        self,
        client: AsyncClient,
        admin_token: str,
        entity: Entity,  # Client entity
        db_session: AsyncSession,
        org_owner
    ):
        """Test that non-candidates get 400 error."""
        # Change entity type to client
        entity.type = EntityType.client
        await db_session.commit()

        response = await client.get(
            f"/api/entities/{entity.id}/recommended-vacancies",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_auto_apply_endpoint(
        self,
        client: AsyncClient,
        admin_token: str,
        candidate_with_skills: Entity,
        test_vacancy: Vacancy,
        org_owner
    ):
        """Test POST /api/entities/{id}/auto-apply/{vacancy_id} endpoint."""
        response = await client.post(
            f"/api/entities/{candidate_with_skills.id}/auto-apply/{test_vacancy.id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["vacancy_id"] == test_vacancy.id
        assert data["entity_id"] == candidate_with_skills.id
        assert "message" in data

    @pytest.mark.asyncio
    async def test_auto_apply_duplicate_returns_error(
        self,
        client: AsyncClient,
        admin_token: str,
        candidate_with_skills: Entity,
        test_vacancy: Vacancy,
        org_owner
    ):
        """Test that duplicate auto-apply returns 400."""
        # First apply
        response1 = await client.post(
            f"/api/entities/{candidate_with_skills.id}/auto-apply/{test_vacancy.id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response1.status_code == 200

        # Second apply should fail
        response2 = await client.post(
            f"/api/entities/{candidate_with_skills.id}/auto-apply/{test_vacancy.id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response2.status_code == 400

# ============================================================================
# EDGE CASE TESTS
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    def service(self):
        return VacancyRecommenderService()

    def test_salary_compatibility_no_entity_salary(self, service):
        """Test salary check when entity has no salary expectations."""
        entity = MagicMock()
        entity.expected_salary_min = None
        entity.expected_salary_max = None

        vacancy = MagicMock()
        vacancy.salary_min = 100000
        vacancy.salary_max = 200000
        vacancy.salary_currency = "RUB"

        is_compatible, reason = service._check_salary_compatibility(entity, vacancy)
        assert is_compatible is True

    def test_salary_compatibility_no_vacancy_salary(self, service):
        """Test salary check when vacancy has no salary info."""
        entity = MagicMock()
        entity.expected_salary_min = 150000
        entity.expected_salary_max = 200000
        entity.expected_salary_currency = "RUB"

        vacancy = MagicMock()
        vacancy.salary_min = None
        vacancy.salary_max = None
        vacancy.salary_currency = "RUB"

        is_compatible, reason = service._check_salary_compatibility(entity, vacancy)
        assert is_compatible is True

    def test_salary_compatibility_currency_mismatch(self, service):
        """Test salary check with different currencies."""
        entity = MagicMock()
        entity.expected_salary_min = 3000
        entity.expected_salary_max = 5000
        entity.expected_salary_currency = "USD"

        vacancy = MagicMock()
        vacancy.salary_min = 150000
        vacancy.salary_max = 250000
        vacancy.salary_currency = "RUB"

        is_compatible, reason = service._check_salary_compatibility(entity, vacancy)
        assert is_compatible is False
        assert "Валюта" in reason

    def test_salary_compatibility_entity_too_high(self, service):
        """Test when entity expects more than vacancy offers."""
        entity = MagicMock()
        entity.expected_salary_min = 300000
        entity.expected_salary_max = 400000
        entity.expected_salary_currency = "RUB"

        vacancy = MagicMock()
        vacancy.salary_min = 100000
        vacancy.salary_max = 200000
        vacancy.salary_currency = "RUB"

        is_compatible, reason = service._check_salary_compatibility(entity, vacancy)
        assert is_compatible is False
        assert "Ожидания кандидата" in reason

    def test_extract_candidate_skills_from_extra_data(self, service):
        """Test extracting skills from extra_data."""
        entity = MagicMock()
        entity.position = "Developer"
        entity.tags = ["backend"]
        entity.extra_data = {
            "skills": ["python", "javascript", "docker"],
            "resume_text": "Experience with SQL and PostgreSQL"
        }

        skills = service._extract_candidate_skills(entity)

        assert "python" in skills
        assert "javascript" in skills
        assert "docker" in skills
        assert "sql" in skills
        assert "postgresql" in skills

    def test_extract_vacancy_requirements(self, service):
        """Test extracting requirements from vacancy."""
        vacancy = MagicMock()
        vacancy.title = "Senior Python Developer"
        vacancy.description = "We are looking for an experienced backend developer"
        vacancy.requirements = "Python, FastAPI, Docker, Kubernetes, SQL"
        vacancy.tags = ["remote", "fullstack"]

        skills = service._extract_vacancy_requirements(vacancy)

        assert "python" in skills
        assert "docker" in skills
        assert "kubernetes" in skills
        assert "sql" in skills
        assert "backend" in skills
        assert "fullstack" in skills


# ============================================================================
# AI ANALYSIS TESTS
# ============================================================================

from api.services.vacancy_recommender import (
    AIMatchAnalysis,
    AIMatchCache,
)


class TestAIMatchAnalysis:
    """Tests for AIMatchAnalysis dataclass."""

    def test_ai_match_analysis_creation(self):
        """Test creating an AIMatchAnalysis instance."""
        analysis = AIMatchAnalysis(
            overall_score=85,
            skills_score=90,
            experience_score=80,
            culture_fit_score=75,
            match_reasons=["Strong Python skills", "Relevant experience"],
            missing_requirements=["Docker experience"],
            summary="Good candidate for the role.",
            ai_analyzed=True
        )

        assert analysis.overall_score == 85
        assert analysis.skills_score == 90
        assert analysis.experience_score == 80
        assert analysis.culture_fit_score == 75
        assert len(analysis.match_reasons) == 2
        assert len(analysis.missing_requirements) == 1
        assert analysis.summary == "Good candidate for the role."
        assert analysis.ai_analyzed is True

    def test_ai_match_analysis_to_dict(self):
        """Test converting AIMatchAnalysis to dictionary."""
        analysis = AIMatchAnalysis(
            overall_score=75,
            skills_score=80,
            experience_score=70,
            culture_fit_score=65,
            match_reasons=["Skills match"],
            missing_requirements=["Leadership experience"],
            summary="Decent candidate.",
            ai_analyzed=True
        )

        data = analysis.to_dict()

        assert data["overall_score"] == 75
        assert data["skills_score"] == 80
        assert data["experience_score"] == 70
        assert data["culture_fit_score"] == 65
        assert data["match_reasons"] == ["Skills match"]
        assert data["missing_requirements"] == ["Leadership experience"]
        assert data["summary"] == "Decent candidate."
        assert data["ai_analyzed"] is True

    def test_ai_match_analysis_defaults(self):
        """Test default values in AIMatchAnalysis."""
        analysis = AIMatchAnalysis()

        assert analysis.overall_score == 0
        assert analysis.skills_score == 0
        assert analysis.experience_score == 0
        assert analysis.culture_fit_score == 0
        assert analysis.match_reasons == []
        assert analysis.missing_requirements == []
        assert analysis.summary == ""
        assert analysis.ai_analyzed is False


class TestAIMatchCache:
    """Tests for AIMatchCache."""

    def test_cache_set_and_get(self):
        """Test setting and getting cache entries."""
        cache = AIMatchCache(ttl_minutes=60)
        analysis = AIMatchAnalysis(overall_score=80, ai_analyzed=True)

        cache.set(entity_id=1, vacancy_id=2, result=analysis)
        retrieved = cache.get(entity_id=1, vacancy_id=2)

        assert retrieved is not None
        assert retrieved.overall_score == 80

    def test_cache_miss(self):
        """Test cache miss for non-existent entry."""
        cache = AIMatchCache(ttl_minutes=60)

        result = cache.get(entity_id=999, vacancy_id=999)

        assert result is None

    def test_cache_invalidate_by_entity(self):
        """Test invalidating cache entries by entity ID."""
        cache = AIMatchCache(ttl_minutes=60)
        analysis = AIMatchAnalysis(overall_score=75, ai_analyzed=True)

        cache.set(entity_id=1, vacancy_id=1, result=analysis)
        cache.set(entity_id=1, vacancy_id=2, result=analysis)
        cache.set(entity_id=2, vacancy_id=1, result=analysis)

        cache.invalidate(entity_id=1)

        assert cache.get(entity_id=1, vacancy_id=1) is None
        assert cache.get(entity_id=1, vacancy_id=2) is None
        assert cache.get(entity_id=2, vacancy_id=1) is not None

    def test_cache_invalidate_by_vacancy(self):
        """Test invalidating cache entries by vacancy ID."""
        cache = AIMatchCache(ttl_minutes=60)
        analysis = AIMatchAnalysis(overall_score=75, ai_analyzed=True)

        cache.set(entity_id=1, vacancy_id=1, result=analysis)
        cache.set(entity_id=2, vacancy_id=1, result=analysis)
        cache.set(entity_id=1, vacancy_id=2, result=analysis)

        cache.invalidate(vacancy_id=1)

        assert cache.get(entity_id=1, vacancy_id=1) is None
        assert cache.get(entity_id=2, vacancy_id=1) is None
        assert cache.get(entity_id=1, vacancy_id=2) is not None

    def test_cache_invalidate_all(self):
        """Test invalidating all cache entries."""
        cache = AIMatchCache(ttl_minutes=60)
        analysis = AIMatchAnalysis(overall_score=75, ai_analyzed=True)

        cache.set(entity_id=1, vacancy_id=1, result=analysis)
        cache.set(entity_id=2, vacancy_id=2, result=analysis)

        cache.invalidate()

        assert cache.get(entity_id=1, vacancy_id=1) is None
        assert cache.get(entity_id=2, vacancy_id=2) is None


class TestAIAnalysisMethods:
    """Tests for AI analysis methods in VacancyRecommenderService."""

    @pytest.fixture
    def service(self):
        """Create a VacancyRecommenderService instance with AI disabled."""
        return VacancyRecommenderService(use_ai=False)

    @pytest.fixture
    def service_with_ai(self):
        """Create a VacancyRecommenderService instance with AI enabled."""
        return VacancyRecommenderService(use_ai=True)

    def test_is_ai_available_without_key(self, service_with_ai, monkeypatch):
        """Test _is_ai_available when API key is not set."""
        monkeypatch.setattr("api.services.vacancy_recommender.settings.anthropic_api_key", "")
        assert service_with_ai._is_ai_available() is False

    def test_is_ai_available_with_key(self, service_with_ai, monkeypatch):
        """Test _is_ai_available when API key is set."""
        monkeypatch.setattr("api.services.vacancy_recommender.settings.anthropic_api_key", "test-key")
        assert service_with_ai._is_ai_available() is True

    def test_is_ai_available_when_disabled(self, service, monkeypatch):
        """Test _is_ai_available when use_ai is False."""
        monkeypatch.setattr("api.services.vacancy_recommender.settings.anthropic_api_key", "test-key")
        assert service._is_ai_available() is False

    def test_build_entity_profile(self, service):
        """Test building entity profile string."""
        entity = MagicMock()
        entity.name = "John Doe"
        entity.position = "Senior Developer"
        entity.company = "Tech Corp"
        entity.expected_salary_min = 150000
        entity.expected_salary_max = 250000
        entity.expected_salary_currency = "RUB"
        entity.tags = ["python", "docker"]
        entity.ai_summary = "Experienced developer"
        entity.extra_data = {"skills": ["python", "sql"], "experience": "5 years"}

        profile = service._build_entity_profile(entity)

        assert "John Doe" in profile
        assert "Senior Developer" in profile
        assert "Tech Corp" in profile
        assert "150,000" in profile
        assert "250,000" in profile
        assert "python" in profile
        assert "docker" in profile
        assert "Experienced developer" in profile

    def test_build_vacancy_profile(self, service):
        """Test building vacancy profile string."""
        vacancy = MagicMock()
        vacancy.title = "Python Developer"
        vacancy.description = "Great opportunity"
        vacancy.requirements = "Python, Docker"
        vacancy.responsibilities = "Develop and maintain"
        vacancy.salary_min = 100000
        vacancy.salary_max = 200000
        vacancy.salary_currency = "RUB"
        vacancy.location = "Moscow"
        vacancy.employment_type = "Full-time"
        vacancy.experience_level = "Senior"
        vacancy.tags = ["backend", "remote"]

        profile = service._build_vacancy_profile(vacancy)

        assert "Python Developer" in profile
        assert "Great opportunity" in profile
        assert "Python, Docker" in profile
        assert "100,000" in profile
        assert "200,000" in profile
        assert "Moscow" in profile
        assert "Full-time" in profile

    def test_parse_ai_match_response_valid_json(self, service):
        """Test parsing valid AI response."""
        response = '''{
            "overall_score": 85,
            "skills_score": 90,
            "experience_score": 80,
            "culture_fit_score": 75,
            "match_reasons": ["Good Python skills", "Relevant experience"],
            "missing_requirements": ["Docker experience"],
            "summary": "Strong candidate for the position."
        }'''

        analysis = service._parse_ai_match_response(response)

        assert analysis.overall_score == 85
        assert analysis.skills_score == 90
        assert analysis.experience_score == 80
        assert analysis.culture_fit_score == 75
        assert len(analysis.match_reasons) == 2
        assert len(analysis.missing_requirements) == 1
        assert "Strong candidate" in analysis.summary
        assert analysis.ai_analyzed is True

    def test_parse_ai_match_response_invalid_json(self, service):
        """Test parsing invalid AI response."""
        response = "This is not valid JSON"

        analysis = service._parse_ai_match_response(response)

        assert analysis.overall_score == 50
        assert analysis.ai_analyzed is False

    def test_parse_ai_match_response_score_normalization(self, service):
        """Test that scores are normalized to 0-100 range."""
        response = '''{
            "overall_score": 150,
            "skills_score": -10,
            "experience_score": 200,
            "culture_fit_score": 75,
            "match_reasons": [],
            "missing_requirements": [],
            "summary": "Test"
        }'''

        analysis = service._parse_ai_match_response(response)

        assert analysis.overall_score == 100  # Capped at 100
        assert analysis.skills_score == 0  # Capped at 0
        assert analysis.experience_score == 100  # Capped at 100

    def test_fallback_match_analysis(self, service):
        """Test fallback match analysis when AI is unavailable."""
        entity = MagicMock()
        entity.position = "Python Developer"
        entity.tags = ["python", "docker"]
        entity.extra_data = {"skills": ["python", "docker", "sql"]}
        entity.expected_salary_min = 150000
        entity.expected_salary_max = 200000
        entity.expected_salary_currency = "RUB"

        vacancy = MagicMock()
        vacancy.title = "Senior Python Developer"
        vacancy.description = "Looking for Python expert"
        vacancy.requirements = "Python, Docker, Kubernetes"
        vacancy.tags = ["backend"]
        vacancy.salary_min = 140000
        vacancy.salary_max = 220000
        vacancy.salary_currency = "RUB"

        analysis = service._fallback_match_analysis(entity, vacancy)

        assert analysis.overall_score > 0
        assert analysis.skills_score > 0
        assert analysis.ai_analyzed is False
        assert len(analysis.match_reasons) > 0

    def test_invalidate_cache(self, service):
        """Test cache invalidation through service."""
        analysis = AIMatchAnalysis(overall_score=80, ai_analyzed=True)
        service._cache.set(1, 1, analysis)

        assert service._cache.get(1, 1) is not None

        service.invalidate_cache(entity_id=1)

        assert service._cache.get(1, 1) is None


class TestAIAnalysisIntegration:
    """Integration tests for AI analysis with mocked AI client."""

    @pytest.mark.asyncio
    async def test_ai_analyze_match_success(
        self,
        mock_anthropic_client,
        monkeypatch
    ):
        """Test successful AI analysis with mocked client."""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='''{
            "overall_score": 85,
            "skills_score": 90,
            "experience_score": 80,
            "culture_fit_score": 75,
            "match_reasons": ["Strong Python skills"],
            "missing_requirements": ["Docker experience"],
            "summary": "Good candidate."
        }''')]
        mock_anthropic_client.messages.create = AsyncMock(return_value=mock_response)
        monkeypatch.setattr("api.services.vacancy_recommender.settings.anthropic_api_key", "test-key")

        service = VacancyRecommenderService(use_ai=True)
        service._client = mock_anthropic_client

        entity = MagicMock()
        entity.id = 1
        entity.name = "Test Candidate"
        entity.position = "Developer"
        entity.company = None
        entity.expected_salary_min = None
        entity.expected_salary_max = None
        entity.expected_salary_currency = "RUB"
        entity.tags = []
        entity.ai_summary = None
        entity.extra_data = {}

        vacancy = MagicMock()
        vacancy.id = 1
        vacancy.title = "Python Developer"
        vacancy.description = "Test vacancy"
        vacancy.requirements = "Python"
        vacancy.responsibilities = None
        vacancy.salary_min = None
        vacancy.salary_max = None
        vacancy.salary_currency = "RUB"
        vacancy.location = None
        vacancy.employment_type = None
        vacancy.experience_level = None
        vacancy.tags = []

        analysis = await service._ai_analyze_match(entity, vacancy, use_cache=False)

        assert analysis.overall_score == 85
        assert analysis.skills_score == 90
        assert analysis.ai_analyzed is True
        mock_anthropic_client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_ai_analyze_match_with_cache(
        self,
        mock_anthropic_client,
        monkeypatch
    ):
        """Test that AI analysis uses cache."""
        monkeypatch.setattr("api.services.vacancy_recommender.settings.anthropic_api_key", "test-key")

        service = VacancyRecommenderService(use_ai=True)

        # Pre-populate cache
        cached_analysis = AIMatchAnalysis(
            overall_score=70,
            skills_score=75,
            ai_analyzed=True
        )
        service._cache.set(1, 1, cached_analysis)

        entity = MagicMock()
        entity.id = 1

        vacancy = MagicMock()
        vacancy.id = 1

        analysis = await service._ai_analyze_match(entity, vacancy, use_cache=True)

        # Should return cached result without calling API
        assert analysis.overall_score == 70
        assert analysis.skills_score == 75
        mock_anthropic_client.messages.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_ai_analyze_match_fallback_on_error(
        self,
        mock_anthropic_client,
        monkeypatch
    ):
        """Test that AI analysis falls back on error."""
        mock_anthropic_client.messages.create = AsyncMock(side_effect=Exception("API Error"))
        monkeypatch.setattr("api.services.vacancy_recommender.settings.anthropic_api_key", "test-key")

        service = VacancyRecommenderService(use_ai=True)
        service._client = mock_anthropic_client

        entity = MagicMock()
        entity.id = 1
        entity.name = "Test"
        entity.position = "Developer"
        entity.company = None
        entity.expected_salary_min = None
        entity.expected_salary_max = None
        entity.expected_salary_currency = "RUB"
        entity.tags = []
        entity.ai_summary = None
        entity.extra_data = {}

        vacancy = MagicMock()
        vacancy.id = 1
        vacancy.title = "Developer"
        vacancy.description = None
        vacancy.requirements = None
        vacancy.responsibilities = None
        vacancy.salary_min = None
        vacancy.salary_max = None
        vacancy.salary_currency = "RUB"
        vacancy.location = None
        vacancy.employment_type = None
        vacancy.experience_level = None
        vacancy.tags = []

        analysis = await service._ai_analyze_match(entity, vacancy, use_cache=False)

        # Should return fallback result
        assert analysis.ai_analyzed is False

    @pytest.mark.asyncio
    async def test_get_recommendations_with_ai(
        self,
        db_session: AsyncSession,
        candidate_with_skills: Entity,
        test_vacancy: Vacancy,
        organization: Organization,
        mock_anthropic_client,
        monkeypatch
    ):
        """Test get_recommendations with AI enabled."""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='''{
            "overall_score": 88,
            "skills_score": 92,
            "experience_score": 85,
            "culture_fit_score": 80,
            "match_reasons": ["Excellent Python skills", "Docker experience"],
            "missing_requirements": ["Kubernetes knowledge"],
            "summary": "Strong candidate with relevant experience."
        }''')]
        mock_anthropic_client.messages.create = AsyncMock(return_value=mock_response)
        monkeypatch.setattr("api.services.vacancy_recommender.settings.anthropic_api_key", "test-key")

        service = VacancyRecommenderService(use_ai=True)
        service._client = mock_anthropic_client

        recommendations = await service.get_recommendations(
            db=db_session,
            entity=candidate_with_skills,
            limit=5,
            org_id=organization.id,
            use_ai=True
        )

        assert len(recommendations) > 0
        rec = recommendations[0]
        assert rec.ai_analyzed is True
        assert rec.match_score == 88
        assert rec.skills_score == 92
        assert rec.experience_score == 85
        assert rec.culture_fit_score == 80
        assert "Excellent Python skills" in rec.match_reasons

    @pytest.mark.asyncio
    async def test_get_recommendations_without_ai(
        self,
        db_session: AsyncSession,
        candidate_with_skills: Entity,
        test_vacancy: Vacancy,
        organization: Organization
    ):
        """Test get_recommendations with AI disabled falls back to keywords."""
        service = VacancyRecommenderService(use_ai=False)

        recommendations = await service.get_recommendations(
            db=db_session,
            entity=candidate_with_skills,
            limit=5,
            org_id=organization.id,
            use_ai=False
        )

        assert len(recommendations) > 0
        rec = recommendations[0]
        assert rec.ai_analyzed is False
        assert rec.match_score > 0

    @pytest.mark.asyncio
    async def test_find_matching_candidates_with_ai(
        self,
        db_session: AsyncSession,
        test_vacancy: Vacancy,
        candidate_with_skills: Entity,
        mock_anthropic_client,
        monkeypatch
    ):
        """Test find_matching_candidates with AI enabled."""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='''{
            "overall_score": 82,
            "skills_score": 88,
            "experience_score": 78,
            "culture_fit_score": 72,
            "match_reasons": ["Python expertise"],
            "missing_requirements": ["Kubernetes"],
            "summary": "Solid candidate."
        }''')]
        mock_anthropic_client.messages.create = AsyncMock(return_value=mock_response)
        monkeypatch.setattr("api.services.vacancy_recommender.settings.anthropic_api_key", "test-key")

        service = VacancyRecommenderService(use_ai=True)
        service._client = mock_anthropic_client

        matches = await service.find_matching_candidates(
            db=db_session,
            vacancy=test_vacancy,
            limit=10,
            exclude_applied=True,
            use_ai=True
        )

        assert len(matches) >= 1
        # Check that AI was used
        for match in matches:
            assert match.ai_analyzed is True

    @pytest.mark.asyncio
    async def test_find_matching_candidates_without_ai(
        self,
        db_session: AsyncSession,
        test_vacancy: Vacancy,
        candidate_with_skills: Entity,
        candidate_without_skills: Entity
    ):
        """Test find_matching_candidates with AI disabled."""
        service = VacancyRecommenderService(use_ai=False)

        matches = await service.find_matching_candidates(
            db=db_session,
            vacancy=test_vacancy,
            limit=10,
            exclude_applied=True,
            use_ai=False
        )

        assert len(matches) >= 2
        # Check that AI was not used
        for match in matches:
            assert match.ai_analyzed is False


class TestVacancyRecommendationWithAIFields:
    """Tests for VacancyRecommendation with new AI fields."""

    def test_vacancy_recommendation_with_ai_fields(self):
        """Test VacancyRecommendation with AI-specific fields."""
        rec = VacancyRecommendation(
            vacancy_id=1,
            vacancy_title="Python Developer",
            match_score=85,
            ai_analyzed=True,
            skills_score=90,
            experience_score=82,
            culture_fit_score=78,
            ai_summary="Strong candidate for the role."
        )

        assert rec.ai_analyzed is True
        assert rec.skills_score == 90
        assert rec.experience_score == 82
        assert rec.culture_fit_score == 78
        assert rec.ai_summary == "Strong candidate for the role."

    def test_vacancy_recommendation_to_dict_with_ai_fields(self):
        """Test to_dict includes AI fields."""
        rec = VacancyRecommendation(
            vacancy_id=1,
            vacancy_title="Developer",
            match_score=75,
            ai_analyzed=True,
            skills_score=80,
            experience_score=70,
            culture_fit_score=65,
            ai_summary="Good match."
        )

        data = rec.to_dict()

        assert data["ai_analyzed"] is True
        assert data["skills_score"] == 80
        assert data["experience_score"] == 70
        assert data["culture_fit_score"] == 65
        assert data["ai_summary"] == "Good match."


class TestCandidateMatchWithAIFields:
    """Tests for CandidateMatch with new AI fields."""

    def test_candidate_match_with_ai_fields(self):
        """Test CandidateMatch with AI-specific fields."""
        match = CandidateMatch(
            entity_id=1,
            entity_name="John Doe",
            match_score=78,
            ai_analyzed=True,
            skills_score=85,
            experience_score=75,
            culture_fit_score=70,
            ai_summary="Promising candidate."
        )

        assert match.ai_analyzed is True
        assert match.skills_score == 85
        assert match.experience_score == 75
        assert match.culture_fit_score == 70
        assert match.ai_summary == "Promising candidate."

    def test_candidate_match_to_dict_with_ai_fields(self):
        """Test to_dict includes AI fields."""
        match = CandidateMatch(
            entity_id=1,
            entity_name="Jane Doe",
            match_score=82,
            ai_analyzed=True,
            skills_score=88,
            experience_score=80,
            culture_fit_score=75,
            ai_summary="Excellent fit."
        )

        data = match.to_dict()

        assert data["ai_analyzed"] is True
        assert data["skills_score"] == 88
        assert data["experience_score"] == 80
        assert data["culture_fit_score"] == 75
        assert data["ai_summary"] == "Excellent fit."
