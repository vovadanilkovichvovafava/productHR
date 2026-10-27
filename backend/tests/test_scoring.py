"""
Tests for AI Scoring Service - Candidate-Vacancy Compatibility Scoring.

Tests cover:
- Scoring service core functionality
- API endpoints for scoring
- Score caching in applications
- Bulk scoring operations
"""
import pytest
import pytest_asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import json

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import (
    Entity, Vacancy, VacancyApplication,
    EntityType, EntityStatus, VacancyStatus, ApplicationStage
)
from api.services.ai_scoring import (
    AIScoringService, CompatibilityScore, Recommendation, ai_scoring_service
)
from tests.conftest import auth_headers


@pytest.fixture(autouse=True)
def scoring_env(monkeypatch, mock_anthropic_client):
    """Окружение скоринга: без живого Redis и с мок-клиентом Claude.

    1. Кэш скоринга сначала ходит в Redis (redis://localhost:6379 по
       умолчанию). На машине разработчика Redis запущен, и тесты писали ключи
       в настоящую базу локального бэкенда, а счётчики «сброшено 3» видели
       хвосты прошлых прогонов и соседних тестов (8, 6, 5). Выключаем Redis и
       даём каждому тесту пустой запасной кэш.
    2. ai_scoring импортирует AsyncAnthropic при загрузке модуля, поэтому
       подмена anthropic.AsyncAnthropic в общей фикстуре до него не доходит, а
       без ключа клиент падает и скоринг отдаёт запасные 50 баллов. Отдаём
       синглтону мок напрямую.
    """
    import api.services.redis_cache as rc
    monkeypatch.setattr(rc, "_redis_available", False)
    monkeypatch.setattr(rc, "_redis_client", None)
    # Без Redis RedisCacheService падает в СВОЙ in-memory слой, который
    # clear_all_sync() кэша скоринга не чистит, — свежий на каждый тест.
    monkeypatch.setattr(rc.RedisCacheService, "_memory_cache", {})
    monkeypatch.setattr(ai_scoring_service, "_client", mock_anthropic_client)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def vacancy(db_session: AsyncSession, organization, department) -> Vacancy:
    """Create a test vacancy."""
    vacancy = Vacancy(
        org_id=organization.id,
        department_id=department.id,
        title="Senior Python Developer",
        description="We are looking for an experienced Python developer to join our team.",
        requirements="5+ years of Python experience, FastAPI, SQLAlchemy, PostgreSQL",
        responsibilities="Design and develop backend services, code reviews, mentoring",
        salary_min=200000,
        salary_max=350000,
        salary_currency="RUB",
        location="Moscow",
        employment_type="full-time",
        experience_level="senior",
        status=VacancyStatus.open,
        tags=["python", "backend", "fastapi"],
        created_at=datetime.utcnow()
    )
    db_session.add(vacancy)
    await db_session.commit()
    await db_session.refresh(vacancy)
    return vacancy


@pytest_asyncio.fixture
async def candidate_for_scoring(db_session: AsyncSession, organization, department, admin_user) -> Entity:
    """Create a candidate entity with skills and experience data."""
    entity = Entity(
        org_id=organization.id,
        department_id=department.id,
        created_by=admin_user.id,
        name="Ivan Petrov",
        email="ivan.petrov@example.com",
        phone="+7 999 123 4567",
        type=EntityType.candidate,
        status=EntityStatus.interview,
        position="Python Developer",
        company="Tech Corp",
        tags=["python", "django", "postgresql"],
        extra_data={
            "skills": ["Python", "FastAPI", "Django", "PostgreSQL", "Redis"],
            "experience_years": 6,
            "education": "Computer Science, MSc",
            "languages": ["Russian", "English"],
            "about": "Experienced backend developer focused on high-load systems"
        },
        expected_salary_min=250000,
        expected_salary_max=300000,
        expected_salary_currency="RUB",
        ai_summary="Experienced Python developer with 6 years in backend development. Strong skills in FastAPI and database optimization.",
        created_at=datetime.utcnow()
    )
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)
    return entity


@pytest_asyncio.fixture
async def second_candidate(db_session: AsyncSession, organization, department, admin_user) -> Entity:
    """Create a second candidate for bulk scoring tests."""
    entity = Entity(
        org_id=organization.id,
        department_id=department.id,
        created_by=admin_user.id,
        name="Maria Ivanova",
        email="maria.ivanova@example.com",
        type=EntityType.candidate,
        status=EntityStatus.screening,
        position="Junior Developer",
        tags=["javascript", "react"],
        extra_data={
            "skills": ["JavaScript", "React", "Node.js"],
            "experience_years": 2
        },
        expected_salary_min=100000,
        expected_salary_max=150000,
        expected_salary_currency="RUB",
        created_at=datetime.utcnow()
    )
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)
    return entity


@pytest_asyncio.fixture
async def application(db_session: AsyncSession, vacancy, candidate_for_scoring) -> VacancyApplication:
    """Create a vacancy application."""
    app = VacancyApplication(
        vacancy_id=vacancy.id,
        entity_id=candidate_for_scoring.id,
        stage=ApplicationStage.interview,
        source="linkedin",
        applied_at=datetime.utcnow()
    )
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)
    return app


# ============================================================================
# UNIT TESTS - AI SCORING SERVICE
# ============================================================================

class TestCompatibilityScore:
    """Tests for CompatibilityScore dataclass."""

    def test_create_default_score(self):
        """Test creating a default compatibility score."""
        score = CompatibilityScore()
        assert score.overall_score == 0
        assert score.skills_match == 0
        assert score.experience_match == 0
        assert score.salary_match == 0
        assert score.culture_fit == 0
        assert score.strengths == []
        assert score.weaknesses == []
        assert score.recommendation == Recommendation.MAYBE.value

    def test_create_full_score(self):
        """Test creating a fully populated score."""
        score = CompatibilityScore(
            overall_score=85,
            skills_match=90,
            experience_match=80,
            salary_match=95,
            culture_fit=75,
            strengths=["Strong Python skills", "Leadership experience"],
            weaknesses=["No FastAPI experience"],
            recommendation=Recommendation.HIRE.value,
            summary="Excellent candidate",
            key_factors=["Technical skills", "Team fit"]
        )
        assert score.overall_score == 85
        assert score.skills_match == 90
        assert len(score.strengths) == 2
        assert score.recommendation == "hire"

    def test_score_to_dict(self):
        """Test converting score to dictionary."""
        score = CompatibilityScore(
            overall_score=75,
            skills_match=80,
            strengths=["Good skills"]
        )
        d = score.to_dict()
        assert isinstance(d, dict)
        assert d["overall_score"] == 75
        assert d["skills_match"] == 80
        assert d["strengths"] == ["Good skills"]

    def test_score_from_dict(self):
        """Test creating score from dictionary."""
        data = {
            "overall_score": 70,
            "skills_match": 75,
            "experience_match": 80,
            "salary_match": 90,
            "culture_fit": 65,
            "strengths": ["Fast learner"],
            "weaknesses": ["Junior level"],
            "recommendation": "maybe",
            "summary": "Good potential",
            "key_factors": ["Growth potential"]
        }
        score = CompatibilityScore.from_dict(data)
        assert score.overall_score == 70
        assert score.recommendation == "maybe"


class TestAIScoringServiceHelpers:
    """Tests for AI Scoring Service helper methods."""

    def test_extract_entity_skills_from_list(self):
        """Test extracting skills from extra_data list."""
        service = AIScoringService()
        entity = MagicMock()
        entity.extra_data = {"skills": ["Python", "FastAPI", "SQL"]}
        entity.tags = []

        skills = service._extract_entity_skills(entity)
        assert "Python" in skills
        assert "FastAPI" in skills
        assert "SQL" in skills

    def test_extract_entity_skills_from_string(self):
        """Test extracting skills from comma-separated string."""
        service = AIScoringService()
        entity = MagicMock()
        entity.extra_data = {"skills": "Python, FastAPI, SQL"}
        entity.tags = []

        skills = service._extract_entity_skills(entity)
        assert "Python" in skills
        assert "FastAPI" in skills
        assert "SQL" in skills

    def test_extract_entity_skills_includes_tags(self):
        """Test that tags are included in skills."""
        service = AIScoringService()
        entity = MagicMock()
        entity.extra_data = {"skills": ["Python"]}
        entity.tags = ["backend", "senior"]

        skills = service._extract_entity_skills(entity)
        assert "Python" in skills
        assert "backend" in skills
        assert "senior" in skills

    def test_extract_entity_experience_from_int(self):
        """Test extracting experience years from integer."""
        service = AIScoringService()
        entity = MagicMock()
        entity.extra_data = {"experience_years": 5}

        exp = service._extract_entity_experience(entity)
        assert exp == 5

    def test_extract_entity_experience_from_string(self):
        """Test extracting experience years from string."""
        service = AIScoringService()
        entity = MagicMock()
        entity.extra_data = {"experience": "3 years"}

        exp = service._extract_entity_experience(entity)
        assert exp == 3

    def test_extract_entity_experience_none(self):
        """Test extracting experience when not available."""
        service = AIScoringService()
        entity = MagicMock()
        entity.extra_data = {}

        exp = service._extract_entity_experience(entity)
        assert exp is None


class TestAIScoringServiceProfiles:
    """Tests for profile building methods."""

    def test_build_entity_profile(self):
        """Test building entity profile string."""
        service = AIScoringService()
        entity = MagicMock()
        entity.name = "Test User"
        entity.position = "Developer"
        entity.company = "Tech Corp"
        entity.email = "test@example.com"
        entity.status = MagicMock(value="interview")
        entity.expected_salary_min = 100000
        entity.expected_salary_max = 150000
        entity.expected_salary_currency = "RUB"
        entity.extra_data = {"skills": ["Python"]}
        entity.tags = []
        entity.ai_summary = "Good candidate"

        profile = service._build_entity_profile(entity)
        assert "Test User" in profile
        assert "Developer" in profile
        assert "Tech Corp" in profile
        assert "Python" in profile
        assert "100,000" in profile or "100000" in profile

    def test_build_vacancy_profile(self):
        """Test building vacancy profile string."""
        service = AIScoringService()
        vacancy = MagicMock()
        vacancy.title = "Python Developer"
        vacancy.description = "Backend development role"
        vacancy.requirements = "5+ years Python"
        vacancy.responsibilities = "Develop APIs"
        vacancy.salary_min = 200000
        vacancy.salary_max = 300000
        vacancy.salary_currency = "RUB"
        vacancy.location = "Remote"
        vacancy.employment_type = "full-time"
        vacancy.experience_level = "senior"
        vacancy.tags = ["python", "backend"]

        profile = service._build_vacancy_profile(vacancy)
        assert "Python Developer" in profile
        assert "Backend development role" in profile
        assert "5+ years Python" in profile
        assert "200,000" in profile or "200000" in profile


class TestAIScoringServiceParser:
    """Tests for AI response parsing."""

    def test_parse_valid_response(self):
        """Test parsing valid AI response."""
        service = AIScoringService()
        response = json.dumps({
            "overall_score": 85,
            "skills_match": 90,
            "experience_match": 80,
            "salary_match": 95,
            "culture_fit": 75,
            "strengths": ["Strong skills"],
            "weaknesses": ["Minor gaps"],
            "recommendation": "hire",
            "summary": "Great match",
            "key_factors": ["Technical"]
        })

        score = service._parse_ai_response(response)
        assert score.overall_score == 85
        assert score.recommendation == "hire"

    def test_parse_response_with_extra_text(self):
        """Test parsing response with surrounding text."""
        service = AIScoringService()
        response = """Here is the analysis:
        {"overall_score": 70, "skills_match": 75, "experience_match": 65,
         "salary_match": 80, "culture_fit": 70, "strengths": [],
         "weaknesses": [], "recommendation": "maybe", "summary": "OK",
         "key_factors": []}
        This is my assessment."""

        score = service._parse_ai_response(response)
        assert score.overall_score == 70

    def test_parse_invalid_response(self):
        """Test parsing invalid response returns default score."""
        service = AIScoringService()
        response = "This is not valid JSON"

        score = service._parse_ai_response(response)
        assert score.overall_score == 50  # Default fallback
        assert "parsing error" in score.summary.lower()

    def test_parse_normalizes_scores(self):
        """Test that scores are normalized to 0-100 range."""
        service = AIScoringService()
        response = json.dumps({
            "overall_score": 150,  # Over 100
            "skills_match": -10,  # Negative
            "experience_match": 80,
            "salary_match": 95,
            "culture_fit": 75,
            "strengths": [],
            "weaknesses": [],
            "recommendation": "hire",
            "summary": "Test",
            "key_factors": []
        })

        score = service._parse_ai_response(response)
        assert score.overall_score == 100  # Clamped to max
        assert score.skills_match == 0  # Clamped to min


# ============================================================================
# INTEGRATION TESTS - API ENDPOINTS
# ============================================================================

class TestScoringEndpoints:
    """Tests for scoring API endpoints."""

    @pytest.mark.asyncio
    async def test_calculate_score_success(
        self,
        client: AsyncClient,
        admin_user,
        admin_token,
        org_owner,
        vacancy,
        candidate_for_scoring,
        mock_anthropic_client
    ):
        """Test calculating compatibility score via API."""
        # Mock AI response for scoring
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "overall_score": 85,
            "skills_match": 90,
            "experience_match": 80,
            "salary_match": 95,
            "culture_fit": 75,
            "strengths": ["Strong Python skills", "Good experience"],
            "weaknesses": ["Could improve communication"],
            "recommendation": "hire",
            "summary": "Excellent match for the position",
            "key_factors": ["Technical skills", "Experience level"]
        }))]
        mock_anthropic_client.messages.create = AsyncMock(return_value=mock_response)

        response = await client.post(
            "/api/scoring/calculate",
            json={
                "entity_id": candidate_for_scoring.id,
                "vacancy_id": vacancy.id
            },
            headers=auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert "score" in data
        assert data["score"]["overall_score"] == 85
        assert data["score"]["recommendation"] == "hire"
        assert len(data["score"]["strengths"]) > 0

    @pytest.mark.asyncio
    async def test_calculate_score_unauthorized(
        self,
        client: AsyncClient,
        vacancy,
        candidate_for_scoring
    ):
        """Test that unauthorized requests are rejected."""
        response = await client.post(
            "/api/scoring/calculate",
            json={
                "entity_id": candidate_for_scoring.id,
                "vacancy_id": vacancy.id
            }
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_calculate_score_entity_not_found(
        self,
        client: AsyncClient,
        admin_user,
        admin_token,
        org_owner,
        vacancy
    ):
        """Test handling of non-existent entity."""
        response = await client.post(
            "/api/scoring/calculate",
            json={
                "entity_id": 99999,
                "vacancy_id": vacancy.id
            },
            headers=auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_calculate_score_vacancy_not_found(
        self,
        client: AsyncClient,
        admin_user,
        admin_token,
        org_owner,
        candidate_for_scoring
    ):
        """Test handling of non-existent vacancy."""
        response = await client.post(
            "/api/scoring/calculate",
            json={
                "entity_id": candidate_for_scoring.id,
                "vacancy_id": 99999
            },
            headers=auth_headers(admin_token)
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_calculate_score_non_candidate(
        self,
        client: AsyncClient,
        admin_user,
        admin_token,
        org_owner,
        vacancy,
        second_entity  # This is a client, not candidate
    ):
        """Test that scoring only works for candidates."""
        response = await client.post(
            "/api/scoring/calculate",
            json={
                "entity_id": second_entity.id,
                "vacancy_id": vacancy.id
            },
            headers=auth_headers(admin_token)
        )

        assert response.status_code == 400
        assert "кандидатов" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_application_score_cached(
        self,
        client: AsyncClient,
        admin_user,
        admin_token,
        org_owner,
        db_session,
        vacancy,
        candidate_for_scoring,
        application
    ):
        """Test getting cached score from application."""
        # Set cached score on application
        application.compatibility_score = {
            "overall_score": 75,
            "skills_match": 80,
            "experience_match": 70,
            "salary_match": 85,
            "culture_fit": 70,
            "strengths": ["Cached strength"],
            "weaknesses": ["Cached weakness"],
            "recommendation": "maybe",
            "summary": "Cached summary",
            "key_factors": ["Cached factor"]
        }
        await db_session.commit()

        response = await client.get(
            f"/api/scoring/application/{application.id}",
            headers=auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["cached"] is True
        assert data["score"]["overall_score"] == 75

    @pytest.mark.asyncio
    async def test_recalculate_application_score(
        self,
        client: AsyncClient,
        admin_user,
        admin_token,
        org_owner,
        vacancy,
        candidate_for_scoring,
        application,
        mock_anthropic_client
    ):
        """Test forcing recalculation of application score."""
        # Mock AI response
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "overall_score": 90,
            "skills_match": 95,
            "experience_match": 85,
            "salary_match": 90,
            "culture_fit": 85,
            "strengths": ["Recalculated strength"],
            "weaknesses": [],
            "recommendation": "hire",
            "summary": "Recalculated summary",
            "key_factors": []
        }))]
        mock_anthropic_client.messages.create = AsyncMock(return_value=mock_response)

        response = await client.post(
            f"/api/scoring/application/{application.id}/recalculate",
            headers=auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["cached"] is False
        assert data["score"]["overall_score"] == 90


class TestBestMatchesEndpoint:
    """Tests for finding best matches endpoint."""

    @pytest.mark.asyncio
    async def test_find_best_matches_for_vacancy(
        self,
        client: AsyncClient,
        admin_user,
        admin_token,
        org_owner,
        vacancy,
        candidate_for_scoring,
        second_candidate,
        mock_anthropic_client
    ):
        """Test finding best matching candidates for a vacancy."""
        # Mock AI responses for both candidates
        call_count = 0

        async def mock_create(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            score = 85 if call_count == 1 else 60
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=json.dumps({
                "overall_score": score,
                "skills_match": score,
                "experience_match": score,
                "salary_match": score,
                "culture_fit": score,
                "strengths": [f"Strength {call_count}"],
                "weaknesses": [],
                "recommendation": "hire" if score > 70 else "maybe",
                "summary": f"Summary {call_count}",
                "key_factors": []
            }))]
            return mock_response

        mock_anthropic_client.messages.create = mock_create

        response = await client.post(
            f"/api/scoring/vacancy/{vacancy.id}/matches",
            json={"limit": 10, "min_score": 0},
            headers=auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["vacancy_id"] == vacancy.id
        assert "matches" in data
        # Results should be sorted by score descending
        if len(data["matches"]) > 1:
            scores = [m["score"]["overall_score"] for m in data["matches"]]
            assert scores == sorted(scores, reverse=True)


class TestMatchingVacanciesEndpoint:
    """Tests for finding matching vacancies endpoint."""

    @pytest.mark.asyncio
    async def test_find_matching_vacancies_for_entity(
        self,
        client: AsyncClient,
        admin_user,
        admin_token,
        org_owner,
        vacancy,
        candidate_for_scoring,
        mock_anthropic_client
    ):
        """Test finding matching vacancies for a candidate."""
        # Mock AI response
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "overall_score": 80,
            "skills_match": 85,
            "experience_match": 75,
            "salary_match": 90,
            "culture_fit": 70,
            "strengths": ["Good match"],
            "weaknesses": [],
            "recommendation": "hire",
            "summary": "Good vacancy match",
            "key_factors": []
        }))]
        mock_anthropic_client.messages.create = AsyncMock(return_value=mock_response)

        response = await client.post(
            f"/api/scoring/entity/{candidate_for_scoring.id}/vacancies",
            json={"limit": 10, "min_score": 0},
            headers=auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["entity_id"] == candidate_for_scoring.id
        assert "matches" in data


# ============================================================================
# SERVICE INTEGRATION TESTS
# ============================================================================

class TestAIScoringServiceIntegration:
    """Integration tests for AI Scoring Service."""

    @pytest.mark.asyncio
    async def test_calculate_compatibility_mocked(
        self,
        candidate_for_scoring,
        vacancy,
        mock_anthropic_client
    ):
        """Test full scoring flow with mocked AI."""
        # Mock AI response
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "overall_score": 82,
            "skills_match": 88,
            "experience_match": 78,
            "salary_match": 85,
            "culture_fit": 75,
            "strengths": ["Strong Python", "FastAPI experience"],
            "weaknesses": ["Could improve soft skills"],
            "recommendation": "hire",
            "summary": "Very good candidate for this role",
            "key_factors": ["Technical match", "Experience level"]
        }))]
        mock_anthropic_client.messages.create = AsyncMock(return_value=mock_response)

        service = AIScoringService()
        # Override client to use mock
        service._client = mock_anthropic_client

        score = await service.calculate_compatibility(candidate_for_scoring, vacancy)

        assert score.overall_score == 82
        assert score.skills_match == 88
        assert score.recommendation == "hire"
        assert len(score.strengths) == 2

    @pytest.mark.asyncio
    async def test_bulk_score_mocked(
        self,
        candidate_for_scoring,
        second_candidate,
        vacancy,
        mock_anthropic_client
    ):
        """Test bulk scoring with mocked AI."""
        call_count = 0

        async def mock_create(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            score = 85 if call_count == 1 else 55
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=json.dumps({
                "overall_score": score,
                "skills_match": score,
                "experience_match": score,
                "salary_match": score,
                "culture_fit": score,
                "strengths": [],
                "weaknesses": [],
                "recommendation": "hire" if score > 70 else "maybe",
                "summary": f"Candidate {call_count}",
                "key_factors": []
            }))]
            return mock_response

        mock_anthropic_client.messages.create = mock_create

        service = AIScoringService()
        service._client = mock_anthropic_client

        results = await service.bulk_score(
            [candidate_for_scoring, second_candidate],
            vacancy
        )

        assert len(results) == 2
        # Should be sorted by score descending
        assert results[0]["score"]["overall_score"] >= results[1]["score"]["overall_score"]


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestScoringErrorHandling:
    """Tests for error handling in scoring service."""

    @pytest.mark.asyncio
    async def test_ai_error_returns_default_score(
        self,
        candidate_for_scoring,
        vacancy,
        mock_anthropic_client
    ):
        """Test that AI errors return a default score."""
        mock_anthropic_client.messages.create = AsyncMock(
            side_effect=Exception("API Error")
        )

        service = AIScoringService()
        service._client = mock_anthropic_client

        score = await service.calculate_compatibility(candidate_for_scoring, vacancy)

        # Should return default score on error
        assert score.overall_score == 50
        assert "error" in score.summary.lower() or "Could not" in score.summary

    @pytest.mark.asyncio
    async def test_invalid_json_response(
        self,
        candidate_for_scoring,
        vacancy,
        mock_anthropic_client
    ):
        """Test handling of invalid JSON from AI."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="This is not valid JSON at all")]
        mock_anthropic_client.messages.create = AsyncMock(return_value=mock_response)

        service = AIScoringService()
        service._client = mock_anthropic_client

        score = await service.calculate_compatibility(candidate_for_scoring, vacancy)

        # Should return default score on parse error
        assert score.overall_score == 50


# ============================================================================
# RECOMMENDATION TESTS
# ============================================================================

class TestRecommendation:
    """Tests for recommendation enum."""

    def test_recommendation_values(self):
        """Test recommendation enum values."""
        assert Recommendation.HIRE.value == "hire"
        assert Recommendation.MAYBE.value == "maybe"
        assert Recommendation.REJECT.value == "reject"

    def test_recommendation_is_string(self):
        """Test that recommendation can be used as string."""
        rec = Recommendation.HIRE
        assert str(rec.value) == "hire"
        assert rec.value == "hire"


# ============================================================================
# SCORING CACHE TESTS
# ============================================================================

from api.services.cache import ScoringCacheService, scoring_cache


class TestScoringCacheService:
    """Tests for ScoringCacheService in-memory cache."""

    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear scoring cache before and after each test."""
        ScoringCacheService.clear_all_sync()
        yield
        ScoringCacheService.clear_all_sync()

    def test_make_score_key(self):
        """Test cache key generation."""
        key = ScoringCacheService.make_score_key(123, 456)
        assert key == "score:123:456"

    @pytest.mark.asyncio
    async def test_set_and_get_cached_score(self):
        """Test setting and getting cached scores."""
        score_data = {
            "overall_score": 85,
            "skills_match": 90,
            "experience_match": 80,
            "salary_match": 95,
            "culture_fit": 75,
            "strengths": ["Strong skills"],
            "weaknesses": [],
            "recommendation": "hire",
            "summary": "Great match",
            "key_factors": []
        }

        # Set cached score
        await ScoringCacheService.set_cached_score(1, 2, score_data)

        # Get cached score
        cached = await ScoringCacheService.get_cached_score(1, 2)

        assert cached is not None
        assert cached["overall_score"] == 85
        assert cached["recommendation"] == "hire"

    @pytest.mark.asyncio
    async def test_cache_miss(self):
        """Test that cache returns None when no entry exists."""
        cached = await ScoringCacheService.get_cached_score(999, 888)
        assert cached is None

    @pytest.mark.asyncio
    async def test_cache_ttl_expiry(self, monkeypatch):
        """Test that cache entries expire after TTL."""
        from datetime import datetime, timedelta

        score_data = {"overall_score": 70}

        # Set with very short TTL (already expired)
        await ScoringCacheService.set_cached_score(1, 2, score_data, ttl_seconds=1)

        # Запись лежит в ДВУХ слоях: основном (Redis или его запасной
        # in-memory) и резервном ScoringCacheService._cache, а читается сначала
        # основной — поэтому «состарить» только _cache (как было) мало.
        # Переводим часы модуля кэша на 10 секунд вперёд: истекают оба слоя.
        import api.services.cache as cache_module

        class _Later(datetime):
            @classmethod
            def utcnow(cls):
                return datetime.utcnow() + timedelta(seconds=10)

        monkeypatch.setattr(cache_module, "datetime", _Later)

        # Should return None (expired)
        cached = await ScoringCacheService.get_cached_score(1, 2)
        assert cached is None

    @pytest.mark.asyncio
    async def test_invalidate_entity_scores(self):
        """Test invalidating all scores for an entity."""
        # Cache scores for entity 1 with multiple vacancies
        await ScoringCacheService.set_cached_score(1, 10, {"overall_score": 80})
        await ScoringCacheService.set_cached_score(1, 20, {"overall_score": 75})
        await ScoringCacheService.set_cached_score(1, 30, {"overall_score": 70})
        # Cache score for different entity
        await ScoringCacheService.set_cached_score(2, 10, {"overall_score": 60})

        # Verify all are cached
        assert await ScoringCacheService.get_cached_score(1, 10) is not None
        assert await ScoringCacheService.get_cached_score(1, 20) is not None
        assert await ScoringCacheService.get_cached_score(1, 30) is not None
        assert await ScoringCacheService.get_cached_score(2, 10) is not None

        # Invalidate all scores for entity 1
        count = await ScoringCacheService.invalidate_entity_scores(1)

        assert count == 3  # 3 entries for entity 1

        # Verify entity 1 scores are gone
        assert await ScoringCacheService.get_cached_score(1, 10) is None
        assert await ScoringCacheService.get_cached_score(1, 20) is None
        assert await ScoringCacheService.get_cached_score(1, 30) is None

        # Verify entity 2 score still exists
        assert await ScoringCacheService.get_cached_score(2, 10) is not None

    @pytest.mark.asyncio
    async def test_invalidate_vacancy_scores(self):
        """Test invalidating all scores for a vacancy."""
        # Cache scores for vacancy 10 with multiple entities
        await ScoringCacheService.set_cached_score(1, 10, {"overall_score": 80})
        await ScoringCacheService.set_cached_score(2, 10, {"overall_score": 75})
        await ScoringCacheService.set_cached_score(3, 10, {"overall_score": 70})
        # Cache score for different vacancy
        await ScoringCacheService.set_cached_score(1, 20, {"overall_score": 60})

        # Invalidate all scores for vacancy 10
        count = await ScoringCacheService.invalidate_vacancy_scores(10)

        assert count == 3  # 3 entries for vacancy 10

        # Verify vacancy 10 scores are gone
        assert await ScoringCacheService.get_cached_score(1, 10) is None
        assert await ScoringCacheService.get_cached_score(2, 10) is None
        assert await ScoringCacheService.get_cached_score(3, 10) is None

        # Verify other vacancy score still exists
        assert await ScoringCacheService.get_cached_score(1, 20) is not None

    @pytest.mark.asyncio
    async def test_invalidate_single_score(self):
        """Test invalidating a specific entity-vacancy score."""
        await ScoringCacheService.set_cached_score(1, 10, {"overall_score": 80})
        await ScoringCacheService.set_cached_score(1, 20, {"overall_score": 75})

        # Invalidate only 1-10
        result = await ScoringCacheService.invalidate_score(1, 10)
        assert result is True

        # 1-10 should be gone
        assert await ScoringCacheService.get_cached_score(1, 10) is None
        # 1-20 should still exist
        assert await ScoringCacheService.get_cached_score(1, 20) is not None

    @pytest.mark.asyncio
    async def test_invalidate_nonexistent_score(self):
        """Test invalidating a score that doesn't exist."""
        result = await ScoringCacheService.invalidate_score(999, 888)
        assert result is False

    @pytest.mark.asyncio
    async def test_clear_all(self):
        """Test clearing entire cache."""
        await ScoringCacheService.set_cached_score(1, 10, {"overall_score": 80})
        await ScoringCacheService.set_cached_score(2, 20, {"overall_score": 75})

        count = await ScoringCacheService.clear_all()
        assert count == 2

        assert await ScoringCacheService.get_cached_score(1, 10) is None
        assert await ScoringCacheService.get_cached_score(2, 20) is None

    def test_get_cache_stats(self):
        """Test getting cache statistics."""
        stats = ScoringCacheService.get_cache_stats()
        assert "total_entries" in stats
        assert "keys" in stats


class TestScoringCacheIntegration:
    """Integration tests for scoring cache with API endpoints."""

    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear scoring cache before and after each test."""
        ScoringCacheService.clear_all_sync()
        yield
        ScoringCacheService.clear_all_sync()

    @pytest.mark.asyncio
    async def test_calculate_score_caches_without_application(
        self,
        client: AsyncClient,
        admin_user,
        admin_token,
        org_owner,
        vacancy,
        candidate_for_scoring,
        mock_anthropic_client
    ):
        """Test that scores are cached in memory when no VacancyApplication exists."""
        # Mock AI response
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "overall_score": 85,
            "skills_match": 90,
            "experience_match": 80,
            "salary_match": 95,
            "culture_fit": 75,
            "strengths": ["Strong Python skills"],
            "weaknesses": [],
            "recommendation": "hire",
            "summary": "Great match",
            "key_factors": ["Technical skills"]
        }))]
        mock_anthropic_client.messages.create = AsyncMock(return_value=mock_response)

        # First request - should calculate and cache
        response1 = await client.post(
            "/api/scoring/calculate",
            json={
                "entity_id": candidate_for_scoring.id,
                "vacancy_id": vacancy.id
            },
            headers=auth_headers(admin_token)
        )
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["cached"] is False
        assert data1["score"]["overall_score"] == 85

        # Verify score is cached in memory
        cached = await ScoringCacheService.get_cached_score(
            candidate_for_scoring.id, vacancy.id
        )
        assert cached is not None
        assert cached["overall_score"] == 85

        # Second request - should return cached score
        response2 = await client.post(
            "/api/scoring/calculate",
            json={
                "entity_id": candidate_for_scoring.id,
                "vacancy_id": vacancy.id
            },
            headers=auth_headers(admin_token)
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["cached"] is True
        assert data2["score"]["overall_score"] == 85

    @pytest.mark.asyncio
    async def test_calculate_score_prefers_application_cache(
        self,
        client: AsyncClient,
        admin_user,
        admin_token,
        org_owner,
        vacancy,
        candidate_for_scoring,
        application,
        db_session
    ):
        """Test that application cache is used when it exists."""
        # Set cached score on application
        application.compatibility_score = {
            "overall_score": 90,
            "skills_match": 95,
            "experience_match": 85,
            "salary_match": 100,
            "culture_fit": 80,
            "strengths": ["From application cache"],
            "weaknesses": [],
            "recommendation": "hire",
            "summary": "Application cached",
            "key_factors": []
        }
        await db_session.commit()

        # Also set a different score in memory cache
        await ScoringCacheService.set_cached_score(
            candidate_for_scoring.id, vacancy.id,
            {"overall_score": 50}  # Different score
        )

        # Request should return application cache, not memory cache
        response = await client.post(
            "/api/scoring/calculate",
            json={
                "entity_id": candidate_for_scoring.id,
                "vacancy_id": vacancy.id
            },
            headers=auth_headers(admin_token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["cached"] is True
        assert data["score"]["overall_score"] == 90  # From application, not memory cache


class TestScoringCacheInvalidation:
    """Tests for cache invalidation on entity/vacancy updates."""

    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear scoring cache before and after each test."""
        ScoringCacheService.clear_all_sync()
        yield
        ScoringCacheService.clear_all_sync()

    @pytest.mark.asyncio
    async def test_entity_update_invalidates_score_cache(
        self,
        client: AsyncClient,
        admin_user,
        admin_token,
        org_owner,
        vacancy,
        candidate_for_scoring
    ):
        """Test that updating entity invalidates its cached scores."""
        # Pre-populate cache
        await ScoringCacheService.set_cached_score(
            candidate_for_scoring.id, vacancy.id,
            {"overall_score": 80}
        )

        # Verify cache exists
        cached = await ScoringCacheService.get_cached_score(
            candidate_for_scoring.id, vacancy.id
        )
        assert cached is not None

        # Update entity with scoring-relevant field (tags/skills)
        # Правка карточки/вакансии — PUT (PATCH-ручек нет, был 405).
        response = await client.put(
            f"/api/entities/{candidate_for_scoring.id}",
            json={
                "tags": ["python", "fastapi", "docker", "kubernetes"]
            },
            headers=auth_headers(admin_token)
        )
        assert response.status_code == 200

        # Cache should be invalidated
        cached_after = await ScoringCacheService.get_cached_score(
            candidate_for_scoring.id, vacancy.id
        )
        assert cached_after is None

    @pytest.mark.asyncio
    async def test_entity_update_salary_invalidates_cache(
        self,
        client: AsyncClient,
        admin_user,
        admin_token,
        org_owner,
        vacancy,
        candidate_for_scoring
    ):
        """Test that updating entity salary invalidates cached scores."""
        # Pre-populate cache
        await ScoringCacheService.set_cached_score(
            candidate_for_scoring.id, vacancy.id,
            {"overall_score": 80}
        )

        # Update entity salary
        # Правка карточки/вакансии — PUT (PATCH-ручек нет, был 405).
        response = await client.put(
            f"/api/entities/{candidate_for_scoring.id}",
            json={
                "expected_salary_min": 300000,
                "expected_salary_max": 400000
            },
            headers=auth_headers(admin_token)
        )
        assert response.status_code == 200

        # Cache should be invalidated
        cached_after = await ScoringCacheService.get_cached_score(
            candidate_for_scoring.id, vacancy.id
        )
        assert cached_after is None

    @pytest.mark.asyncio
    async def test_entity_update_non_scoring_field_preserves_cache(
        self,
        client: AsyncClient,
        admin_user,
        admin_token,
        org_owner,
        vacancy,
        candidate_for_scoring
    ):
        """Test that updating non-scoring fields does not invalidate cache."""
        # Pre-populate cache
        await ScoringCacheService.set_cached_score(
            candidate_for_scoring.id, vacancy.id,
            {"overall_score": 80}
        )

        # Update entity with non-scoring field (phone)
        # Правка карточки/вакансии — PUT (PATCH-ручек нет, был 405).
        response = await client.put(
            f"/api/entities/{candidate_for_scoring.id}",
            json={
                "phone": "+7 999 888 7777"
            },
            headers=auth_headers(admin_token)
        )
        assert response.status_code == 200

        # Cache should still exist
        cached_after = await ScoringCacheService.get_cached_score(
            candidate_for_scoring.id, vacancy.id
        )
        assert cached_after is not None
        assert cached_after["overall_score"] == 80

    @pytest.mark.asyncio
    async def test_vacancy_update_invalidates_score_cache(
        self,
        client: AsyncClient,
        admin_user,
        admin_token,
        org_owner,
        vacancy,
        candidate_for_scoring
    ):
        """Test that updating vacancy invalidates all its cached scores."""
        # Pre-populate cache for multiple entities
        await ScoringCacheService.set_cached_score(
            candidate_for_scoring.id, vacancy.id,
            {"overall_score": 80}
        )
        await ScoringCacheService.set_cached_score(
            999, vacancy.id,  # Another entity
            {"overall_score": 70}
        )

        # Update vacancy with scoring-relevant field
        # Правка карточки/вакансии — PUT (PATCH-ручек нет, был 405).
        response = await client.put(
            f"/api/vacancies/{vacancy.id}",
            json={
                "requirements": "7+ years of Python experience, team leadership"
            },
            headers=auth_headers(admin_token)
        )
        assert response.status_code == 200

        # Both cached scores should be invalidated
        cached1 = await ScoringCacheService.get_cached_score(
            candidate_for_scoring.id, vacancy.id
        )
        cached2 = await ScoringCacheService.get_cached_score(999, vacancy.id)

        assert cached1 is None
        assert cached2 is None

    @pytest.mark.asyncio
    async def test_vacancy_salary_update_invalidates_cache(
        self,
        client: AsyncClient,
        admin_user,
        admin_token,
        org_owner,
        vacancy,
        candidate_for_scoring
    ):
        """Test that updating vacancy salary invalidates cached scores."""
        # Pre-populate cache
        await ScoringCacheService.set_cached_score(
            candidate_for_scoring.id, vacancy.id,
            {"overall_score": 80}
        )

        # Update vacancy salary
        # Правка карточки/вакансии — PUT (PATCH-ручек нет, был 405).
        response = await client.put(
            f"/api/vacancies/{vacancy.id}",
            json={
                "salary_min": 250000,
                "salary_max": 400000
            },
            headers=auth_headers(admin_token)
        )
        assert response.status_code == 200

        # Cache should be invalidated
        cached_after = await ScoringCacheService.get_cached_score(
            candidate_for_scoring.id, vacancy.id
        )
        assert cached_after is None

    @pytest.mark.asyncio
    async def test_vacancy_update_non_scoring_field_preserves_cache(
        self,
        client: AsyncClient,
        admin_user,
        admin_token,
        org_owner,
        vacancy,
        candidate_for_scoring
    ):
        """Test that updating non-scoring fields does not invalidate cache."""
        # Pre-populate cache
        await ScoringCacheService.set_cached_score(
            candidate_for_scoring.id, vacancy.id,
            {"overall_score": 80}
        )

        # Update vacancy with non-scoring field (location)
        # Правка карточки/вакансии — PUT (PATCH-ручек нет, был 405).
        response = await client.put(
            f"/api/vacancies/{vacancy.id}",
            json={
                "location": "Saint Petersburg"
            },
            headers=auth_headers(admin_token)
        )
        assert response.status_code == 200

        # Cache should still exist
        cached_after = await ScoringCacheService.get_cached_score(
            candidate_for_scoring.id, vacancy.id
        )
        assert cached_after is not None
        assert cached_after["overall_score"] == 80
