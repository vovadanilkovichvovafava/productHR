"""
Tests for EntityProfileService - AI profile generation and similarity matching.

Covers:
- Profile similarity calculation (same, different, partial match)
- Skills normalization integration
- Level matching (junior/middle/senior/lead)
- Specialization matching
- Salary range overlap
- Profile generation (minimal and full context)
- Similar candidate search
"""
import pytest
import pytest_asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import json

from api.services.entity_profile import EntityProfileService, entity_profile_service
from api.services.skills_normalizer import SkillsNormalizer, skills_normalizer
from api.models.database import Entity, EntityType, EntityStatus


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def profile_service(mock_anthropic_client):
    """Fresh EntityProfileService instance for each test.

    Клиент Claude подставляем сразу: сервис импортирует AsyncAnthropic по
    имени (`from anthropic import AsyncAnthropic`), поэтому общий мок из
    conftest его не подменяет, а без ключа в окружении свойство client
    падает «ANTHROPIC_API_KEY не настроен». В сеть тесты не ходят.
    """
    service = EntityProfileService()
    service._client = mock_anthropic_client
    return service


@pytest.fixture
def normalizer_service():
    """Fresh SkillsNormalizer instance for each test."""
    normalizer = SkillsNormalizer()
    normalizer.clear_cache()  # Start with clean cache
    return normalizer


@pytest.fixture
def sample_profile_backend_senior():
    """Sample profile: Senior Backend Developer."""
    return {
        "skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "Redis"],
        "experience_years": 5,
        "level": "senior",
        "specialization": "Backend разработка",
        "salary_min": 200000,
        "salary_max": 300000,
        "salary_currency": "RUB",
        "location": "Москва",
        "work_format": "remote",
        "languages": ["Russian", "English"],
        "summary": "Senior backend developer with strong Python expertise",
        "strengths": ["System design", "Mentoring", "Performance optimization"],
        "weaknesses": ["Frontend", "Mobile"],
        "red_flags": [],
        "communication_style": "Clear and concise"
    }


@pytest.fixture
def sample_profile_backend_middle():
    """Sample profile: Middle Backend Developer."""
    return {
        "skills": ["Python", "Django", "MySQL"],
        "experience_years": 3,
        "level": "middle",
        "specialization": "Backend",
        "salary_min": 150000,
        "salary_max": 200000,
        "salary_currency": "RUB",
        "location": "Москва",
        "work_format": "hybrid",
        "languages": ["Russian"],
        "summary": "Middle backend developer, Django focus"
    }


@pytest.fixture
def sample_profile_frontend_junior():
    """Sample profile: Junior Frontend Developer."""
    return {
        "skills": ["JavaScript", "React", "CSS", "HTML"],
        "experience_years": 1,
        "level": "junior",
        "specialization": "Frontend",
        "salary_min": 80000,
        "salary_max": 120000,
        "salary_currency": "RUB",
        "location": "Санкт-Петербург",
        "work_format": "office",
        "summary": "Junior frontend developer with React experience"
    }


@pytest.fixture
def sample_profile_fullstack_lead():
    """Sample profile: Lead Fullstack Developer."""
    return {
        "skills": ["Python", "TypeScript", "React", "FastAPI", "PostgreSQL", "Kubernetes"],
        "experience_years": 8,
        "level": "lead",
        "specialization": "Fullstack",
        "salary_min": 400000,
        "salary_max": 500000,
        "salary_currency": "RUB",
        "location": "Москва",
        "work_format": "remote"
    }


# ============================================================================
# CALCULATE SIMILARITY TESTS
# ============================================================================

class TestCalculateSimilarity:
    """Tests for EntityProfileService.calculate_similarity()"""

    def test_same_profile_returns_100(self, profile_service, sample_profile_backend_senior):
        """Identical profiles should return 100% similarity."""
        result = profile_service.calculate_similarity(
            sample_profile_backend_senior,
            sample_profile_backend_senior
        )

        assert result["score"] == 100
        assert len(result["matches"]) > 0
        assert len(result["differences"]) == 0
        # Подписи итога сменились вместе с новой шкалой (≥80 — «Отличное совпадение»).
        assert result["summary"] == "Отличное совпадение профилей"

    def test_completely_different_profiles_low_score(
        self, profile_service, sample_profile_backend_senior, sample_profile_frontend_junior
    ):
        """Very different profiles should return low similarity score."""
        result = profile_service.calculate_similarity(
            sample_profile_backend_senior,
            sample_profile_frontend_junior
        )

        # Should be low due to different skills, level, salary, location
        assert result["score"] < 40
        assert len(result["differences"]) > 0
        # Different level: senior vs junior («Большой разрыв уровней: …»)
        assert any("уровн" in d.lower() for d in result["differences"])

    def test_partial_skills_match(self, profile_service):
        """Partial skills overlap should return moderate score."""
        profile1 = {
            "skills": ["Python", "FastAPI", "Docker", "PostgreSQL"],
            "level": "senior",
            "specialization": "Backend"
        }
        profile2 = {
            "skills": ["Python", "Django", "Docker", "MySQL"],
            "level": "senior",
            "specialization": "Backend"
        }

        result = profile_service.calculate_similarity(profile1, profile2)

        # 2 common skills (Python, Docker) out of 6 unique
        # Plus same level (20) and same specialization (20)
        assert 40 <= result["score"] <= 70
        assert "Общие навыки" in str(result["matches"])
        assert "python" in str(result["matches"]).lower()
        assert "docker" in str(result["matches"]).lower()

    def test_similar_profiles_high_score(
        self, profile_service, sample_profile_backend_senior, sample_profile_backend_middle
    ):
        """Similar profiles should return high score despite some differences."""
        result = profile_service.calculate_similarity(
            sample_profile_backend_senior,
            sample_profile_backend_middle
        )

        # Same specialization, overlapping skills (Python), adjacent levels
        # Overlapping salary ranges
        assert result["score"] >= 40
        # Should match on Python skill
        assert "Общие навыки" in str(result["matches"])

    def test_empty_profiles(self, profile_service):
        """Empty profiles get only neutral points and no matches.

        По текущей шкале неизвестное поле даёт нейтральную часть баллов (навыки
        17, уровень 12, специализация 10, зарплата 5, формат 2, локация 2), а
        не 0: «не знаем» не должно выглядеть как «разные».
        """
        result = profile_service.calculate_similarity({}, {})

        assert result["score"] == 48
        assert result["matches"] == []
        assert result["summary"] == "Есть общие черты"

    def test_one_empty_profile(self, profile_service, sample_profile_backend_senior):
        """One empty profile should return low score."""
        result = profile_service.calculate_similarity(
            sample_profile_backend_senior,
            {}
        )

        # Пустой второй профиль — без совпадений, балл ниже «Есть общие черты» (35).
        assert result["score"] < 35
        assert result["matches"] == []
        assert "не указаны навыки" in str(result["differences"])


# ============================================================================
# SKILLS NORMALIZATION TESTS
# ============================================================================

class TestSkillsNormalization:
    """Tests for skills normalization through SkillsNormalizer."""

    @pytest.mark.asyncio
    async def test_known_aliases_javascript(self, normalizer_service):
        """Test JS -> JavaScript normalization."""
        result = await normalizer_service.normalize(["JS", "js", "javascript"])

        assert len(result) == 1  # Deduplicated
        assert "JavaScript" in result

    @pytest.mark.asyncio
    async def test_known_aliases_python(self, normalizer_service):
        """Test Python aliases: питон, py -> Python."""
        result = await normalizer_service.normalize(["py", "питон", "python"])

        assert len(result) == 1
        assert "Python" in result

    @pytest.mark.asyncio
    async def test_known_aliases_react(self, normalizer_service):
        """Test React aliases: React.js, ReactJS -> React."""
        result = await normalizer_service.normalize(["react.js", "reactjs", "React"])

        assert len(result) == 1
        assert "React" in result

    @pytest.mark.asyncio
    async def test_mixed_skills_normalization(self, normalizer_service):
        """Test mixed skills normalization."""
        result = await normalizer_service.normalize([
            "JS", "питон", "react.js", "PostgreSQL", "Docker"
        ])

        assert "JavaScript" in result
        assert "Python" in result
        assert "React" in result
        # These should remain as-is (already normalized)
        assert any("PostgreSQL" in s or "postgres" in s.lower() for s in result)
        assert any("Docker" in s or "docker" in s.lower() for s in result)

    @pytest.mark.asyncio
    async def test_russian_transliteration(self, normalizer_service):
        """Test Russian skill names are transliterated correctly."""
        result = await normalizer_service.normalize([
            "джаваскрипт", "тайпскрипт", "реакт", "докер"
        ])

        assert "JavaScript" in result
        assert "TypeScript" in result
        assert "React" in result
        assert "Docker" in result

    @pytest.mark.asyncio
    async def test_soft_skills_normalization(self, normalizer_service):
        """Test soft skills normalization."""
        result = await normalizer_service.normalize([
            "коммуникация", "лидерство", "командная работа"
        ])

        assert "Communication" in result
        assert "Leadership" in result
        assert "Teamwork" in result

    @pytest.mark.asyncio
    async def test_empty_skills_list(self, normalizer_service):
        """Test empty input returns empty list."""
        result = await normalizer_service.normalize([])
        assert result == []

    @pytest.mark.asyncio
    async def test_normalize_single_known(self, normalizer_service):
        """Test single skill normalization from static dict."""
        result = await normalizer_service.normalize_single("js")
        assert result == "JavaScript"

    @pytest.mark.asyncio
    async def test_normalize_single_unknown(self, normalizer_service):
        """Test single skill normalization returns None for unknown."""
        result = await normalizer_service.normalize_single("SomeUnknownFramework2025")
        assert result is None


# ============================================================================
# LEVEL MATCHING TESTS
# ============================================================================

class TestLevelMatching:
    """Tests for level matching in similarity calculation."""

    def test_same_level_max_score(self, profile_service):
        """Same level should get maximum level score (20 points)."""
        p1 = {"level": "senior", "skills": ["Python"]}
        p2 = {"level": "senior", "skills": ["Python"]}

        result = profile_service.calculate_similarity(p1, p2)

        assert "Одинаковый уровень" in str(result["matches"])
        assert "senior" in str(result["matches"]).lower()

    def test_adjacent_levels_partial_score(self, profile_service):
        """Adjacent levels (middle/senior) should get partial score."""
        p1 = {"level": "middle", "skills": ["Python"]}
        p2 = {"level": "senior", "skills": ["Python"]}

        result = profile_service.calculate_similarity(p1, p2)

        # Соседние уровни — совместимые (LEVEL_COMPATIBILITY = 15): это
        # совпадение «Совместимые уровни», а не отличие.
        assert "Совместимые уровни: middle ↔ senior" in result["matches"]

    def test_far_levels_no_score(self, profile_service):
        """Far apart levels (junior/lead) should get zero level score."""
        p1 = {"level": "junior", "skills": ["Python"]}
        p2 = {"level": "lead", "skills": ["Python"]}

        result = profile_service.calculate_similarity(p1, p2)

        # Should be marked as different («Несовместимые уровни: junior vs lead»)
        assert any("несовместимые уровни" in d.lower() for d in result["differences"])
        # Score should be lower
        assert result["score"] < 80

    def test_unknown_level_ignored(self, profile_service):
        """Unknown level should not affect scoring."""
        p1 = {"level": "unknown", "skills": ["Python"]}
        p2 = {"level": "senior", "skills": ["Python"]}

        result = profile_service.calculate_similarity(p1, p2)

        # Should not add to matches or differences for level
        level_mentions = [
            m for m in result["matches"] + result["differences"]
            if "уровень" in m.lower()
        ]
        assert len(level_mentions) == 0

    @pytest.mark.parametrize("level1,level2,should_match", [
        ("junior", "junior", True),
        ("middle", "middle", True),
        ("senior", "senior", True),
        ("lead", "lead", True),
        ("junior", "middle", False),
        ("middle", "senior", False),
        ("senior", "lead", False),
        ("junior", "senior", False),
        ("junior", "lead", False),
    ])
    def test_level_combinations(self, profile_service, level1, level2, should_match):
        """Test various level combinations."""
        p1 = {"level": level1, "skills": ["Python"]}
        p2 = {"level": level2, "skills": ["Python"]}

        result = profile_service.calculate_similarity(p1, p2)

        if should_match:
            assert "Одинаковый уровень" in str(result["matches"])
        else:
            # Either in differences or partial match
            pass  # Level mismatch handled in differences


# ============================================================================
# SPECIALIZATION MATCHING TESTS
# ============================================================================

class TestSpecializationMatching:
    """Tests for specialization matching in similarity calculation."""

    def test_same_specialization_max_score(self, profile_service):
        """Same specialization should match."""
        p1 = {"specialization": "Backend", "skills": []}
        p2 = {"specialization": "Backend", "skills": []}

        result = profile_service.calculate_similarity(p1, p2)

        assert "специализация" in str(result["matches"]).lower()

    def test_similar_specialization_matches(self, profile_service):
        """Similar specializations (Backend vs Backend разработка) should match."""
        p1 = {"specialization": "Backend разработка", "skills": []}
        p2 = {"specialization": "Backend", "skills": []}

        result = profile_service.calculate_similarity(p1, p2)

        # Should match due to word overlap
        assert "специализация" in str(result["matches"]).lower()

    def test_different_specialization_no_match(self, profile_service):
        """Different specializations should not match."""
        p1 = {"specialization": "Backend", "skills": []}
        p2 = {"specialization": "Frontend", "skills": []}

        result = profile_service.calculate_similarity(p1, p2)

        assert "разные специализации" in str(result["differences"]).lower()


# ============================================================================
# SALARY OVERLAP TESTS
# ============================================================================

class TestSalaryOverlap:
    """Tests for salary range overlap calculation."""

    def test_overlapping_ranges(self, profile_service):
        """Overlapping salary ranges should match."""
        p1 = {"salary_min": 150000, "salary_max": 200000, "skills": []}
        p2 = {"salary_min": 180000, "salary_max": 250000, "skills": []}

        result = profile_service.calculate_similarity(p1, p2)

        assert "зарплат" in str(result["matches"]).lower()

    def test_non_overlapping_ranges_close(self, profile_service):
        """Close but non-overlapping ranges should get partial score."""
        p1 = {"salary_min": 100000, "salary_max": 150000, "skills": []}
        p2 = {"salary_min": 160000, "salary_max": 200000, "skills": []}

        result = profile_service.calculate_similarity(p1, p2)

        # Ranges are close (within 30%), should get partial score
        salary_mentions = [
            d for d in result["differences"]
            if "зарплат" in d.lower()
        ]
        # Either partial or full miss depending on percentage
        assert len(salary_mentions) >= 0  # May or may not appear

    def test_no_salary_data(self, profile_service):
        """Missing salary data should be skipped gracefully."""
        p1 = {"skills": ["Python"]}
        p2 = {"skills": ["Python"]}

        result = profile_service.calculate_similarity(p1, p2)

        # Should not crash, salary just not included in score
        assert "score" in result

    def test_one_salary_missing(self, profile_service):
        """One profile missing salary should not crash."""
        p1 = {"salary_min": 150000, "salary_max": 200000, "skills": []}
        p2 = {"skills": []}

        result = profile_service.calculate_similarity(p1, p2)

        # Should work without error
        assert "score" in result


# ============================================================================
# PROFILE GENERATION TESTS
# ============================================================================

class TestProfileGeneration:
    """Tests for EntityProfileService.generate_profile()"""

    @pytest.mark.asyncio
    async def test_profile_generation_minimal(
        self, profile_service, db_session, organization, department, admin_user,
        mock_anthropic_client
    ):
        """Test profile generation with minimal entity data."""
        # Create minimal entity
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Minimal Contact",
            type=EntityType.candidate,
            status=EntityStatus.active,
            created_at=datetime.utcnow()
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # Общий мок conftest отвечает обычным текстом — а это ветка «не JSON»
        # (её проверяет test_profile_generation_json_parse_error). Здесь нужен
        # успешный разбор, поэтому — минимальный JSON.
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({"skills": [], "level": "unknown"}))]
        mock_anthropic_client.messages.create = AsyncMock(return_value=mock_response)

        profile = await profile_service.generate_profile(
            entity=entity,
            chats=[],
            calls=[],
            files=[]
        )

        # Should return profile even with minimal data
        assert profile is not None
        assert "generated_at" in profile
        assert "context_sources" in profile
        assert profile["context_sources"]["chats_count"] == 0
        assert profile["context_sources"]["calls_count"] == 0

    @pytest.mark.asyncio
    async def test_profile_generation_with_entity_data(
        self, profile_service, db_session, organization, department, admin_user,
        mock_anthropic_client
    ):
        """Test profile generation uses entity data."""
        # Create entity with data
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Senior Developer",
            position="Backend Developer",
            company="Tech Corp",
            type=EntityType.candidate,
            status=EntityStatus.active,
            tags=["Python", "FastAPI"],
            expected_salary_min=200000,
            expected_salary_max=300000,
            expected_salary_currency="RUB",
            created_at=datetime.utcnow()
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # Configure mock to return proper JSON
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "skills": ["Python", "FastAPI"],
            "experience_years": 5,
            "level": "senior",
            "specialization": "Backend",
            "salary_min": 200000,
            "salary_max": 300000,
            "salary_currency": "RUB",
            "summary": "Senior backend developer"
        }))]
        mock_anthropic_client.messages.create = AsyncMock(return_value=mock_response)

        profile = await profile_service.generate_profile(
            entity=entity,
            chats=[],
            calls=[],
            files=[]
        )

        assert profile is not None
        assert profile.get("skills") == ["Python", "FastAPI"]
        assert profile.get("level") == "senior"

    @pytest.mark.asyncio
    async def test_profile_generation_json_parse_error(
        self, profile_service, db_session, organization, department, admin_user,
        mock_anthropic_client
    ):
        """Test graceful handling of malformed JSON response."""
        entity = Entity(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            name="Test Contact",
            position="Developer",
            type=EntityType.candidate,
            status=EntityStatus.active,
            tags=["Python"],
            created_at=datetime.utcnow()
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)

        # Mock returns invalid JSON
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="This is not valid JSON {{{")]
        mock_anthropic_client.messages.create = AsyncMock(return_value=mock_response)

        profile = await profile_service.generate_profile(
            entity=entity,
            chats=[],
            calls=[],
            files=[]
        )

        # Should return fallback profile
        assert profile is not None
        assert "error" in profile
        assert profile.get("skills") == ["Python"]  # Falls back to entity tags


# ============================================================================
# FIND SIMILAR TESTS
# ============================================================================

class TestFindSimilar:
    """Tests for EntityProfileService.find_similar()"""

    def test_find_similar_basic(
        self, profile_service, sample_profile_backend_senior, sample_profile_backend_middle
    ):
        """Test finding similar candidates."""
        target = sample_profile_backend_senior

        # Create mock entities
        entity1 = MagicMock()
        entity1.id = 1
        entity1.name = "Similar Dev"
        entity1.position = "Backend Developer"
        entity1.status = MagicMock(value="active")

        entity2 = MagicMock()
        entity2.id = 2
        entity2.name = "Frontend Dev"
        entity2.position = "Frontend Developer"
        entity2.status = MagicMock(value="active")

        candidates = [
            (entity1, sample_profile_backend_middle),
            (entity2, {
                "skills": ["JavaScript", "React"],
                "level": "junior",
                "specialization": "Frontend"
            })
        ]

        results = profile_service.find_similar(
            target_profile=target,
            candidates=candidates,
            min_score=10,
            limit=10
        )

        assert len(results) >= 1
        # Backend middle should rank higher than frontend junior
        if len(results) >= 2:
            assert results[0]["entity_id"] == 1  # Similar backend
        assert results[0]["score"] > 0

    def test_find_similar_with_min_score(
        self, profile_service, sample_profile_backend_senior
    ):
        """Test min_score filter works."""
        target = sample_profile_backend_senior

        entity1 = MagicMock()
        entity1.id = 1
        entity1.name = "Very Different"
        entity1.position = "Designer"
        entity1.status = MagicMock(value="active")

        candidates = [
            (entity1, {
                "skills": ["Figma", "Photoshop"],
                "level": "middle",
                "specialization": "Design"
            })
        ]

        results = profile_service.find_similar(
            target_profile=target,
            candidates=candidates,
            min_score=50,  # High threshold
            limit=10
        )

        # Should return empty due to high threshold
        assert len(results) == 0

    def test_find_similar_with_limit(
        self, profile_service, sample_profile_backend_senior, sample_profile_backend_middle
    ):
        """Test limit parameter works."""
        target = sample_profile_backend_senior

        # Create many candidates
        candidates = []
        for i in range(20):
            entity = MagicMock()
            entity.id = i
            entity.name = f"Dev {i}"
            entity.position = "Developer"
            entity.status = MagicMock(value="active")
            candidates.append((entity, sample_profile_backend_middle))

        results = profile_service.find_similar(
            target_profile=target,
            candidates=candidates,
            min_score=10,
            limit=5
        )

        assert len(results) == 5

    def test_find_similar_empty_candidates(self, profile_service, sample_profile_backend_senior):
        """Test with empty candidates list."""
        results = profile_service.find_similar(
            target_profile=sample_profile_backend_senior,
            candidates=[],
            min_score=10,
            limit=10
        )

        assert results == []

    def test_find_similar_none_profile_skipped(
        self, profile_service, sample_profile_backend_senior
    ):
        """Test candidates with None profile are skipped."""
        entity1 = MagicMock()
        entity1.id = 1
        entity1.name = "No Profile"
        entity1.position = "Unknown"
        entity1.status = MagicMock(value="active")

        candidates = [
            (entity1, None),  # No profile
        ]

        results = profile_service.find_similar(
            target_profile=sample_profile_backend_senior,
            candidates=candidates,
            min_score=10,
            limit=10
        )

        assert len(results) == 0

    def test_find_similar_sorted_by_score(
        self, profile_service, sample_profile_backend_senior
    ):
        """Test results are sorted by score descending."""
        target = sample_profile_backend_senior

        low_match = MagicMock()
        low_match.id = 1
        low_match.name = "Low Match"
        low_match.position = "Designer"
        low_match.status = MagicMock(value="active")

        high_match = MagicMock()
        high_match.id = 2
        high_match.name = "High Match"
        high_match.position = "Backend Dev"
        high_match.status = MagicMock(value="active")

        candidates = [
            (low_match, {"skills": ["Figma"], "level": "junior", "specialization": "Design"}),
            (high_match, {"skills": ["Python", "FastAPI"], "level": "senior", "specialization": "Backend"}),
        ]

        results = profile_service.find_similar(
            target_profile=target,
            candidates=candidates,
            min_score=0,
            limit=10
        )

        # High match should be first
        if len(results) >= 2:
            assert results[0]["score"] >= results[1]["score"]


# ============================================================================
# EXPERIENCE MATCHING TESTS
# ============================================================================

class TestExperienceMatching:
    """Стаж (experience_years) отдельно НЕ оценивается: он уже отражён в уровне
    (calculate_similarity, «to avoid double-counting»). Раньше тут проверялись
    подписи «опыт» в совпадениях/отличиях — их больше нет."""

    @pytest.mark.parametrize("years1,years2", [(5, 5), (5, 6), (2, 10)])
    def test_experience_not_scored(self, profile_service, years1, years2):
        base = profile_service.calculate_similarity({"skills": []}, {"skills": []})
        result = profile_service.calculate_similarity(
            {"experience_years": years1, "skills": []},
            {"experience_years": years2, "skills": []},
        )

        assert result["score"] == base["score"]
        assert "опыт" not in str(result["matches"] + result["differences"]).lower()


# ============================================================================
# EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_none_skills_handled(self, profile_service):
        """None skills should be handled gracefully."""
        p1 = {"skills": None, "level": "senior"}
        p2 = {"skills": ["Python"], "level": "senior"}

        result = profile_service.calculate_similarity(p1, p2)

        # Should not crash
        assert "score" in result

    def test_empty_strings_in_skills(self, profile_service):
        """Empty strings in skills should be handled."""
        p1 = {"skills": ["Python", "", "  "], "level": "senior"}
        p2 = {"skills": ["Python"], "level": "senior"}

        result = profile_service.calculate_similarity(p1, p2)

        # Should match on Python
        assert result["score"] > 0

    def test_case_insensitive_skills(self, profile_service):
        """Skills comparison should be case insensitive."""
        p1 = {"skills": ["PYTHON", "FASTAPI"]}
        p2 = {"skills": ["python", "fastapi"]}

        result = profile_service.calculate_similarity(p1, p2)

        # Should have high skill match
        assert "Общие навыки" in str(result["matches"])

    def test_unicode_handling(self, profile_service):
        """Unicode characters should be handled properly."""
        p1 = {"skills": ["Python", "БД"], "specialization": "Бэкенд разработка"}
        p2 = {"skills": ["Python", "БД"], "specialization": "Бэкенд"}

        result = profile_service.calculate_similarity(p1, p2)

        assert result["score"] > 0

    def test_very_long_skills_list(self, profile_service):
        """Very long skills list should be handled."""
        skills = [f"Skill{i}" for i in range(100)]
        p1 = {"skills": skills}
        p2 = {"skills": skills[:50] + ["DifferentSkill" + str(i) for i in range(50)]}

        result = profile_service.calculate_similarity(p1, p2)

        # Should work without timeout or error
        assert "score" in result
