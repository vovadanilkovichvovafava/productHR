"""
Vacancy Recommendation Service for HR-Bot.

Provides AI-powered vacancy recommendations for candidates based on:
- Skills matching (AI-enhanced)
- Experience level compatibility
- Cultural fit assessment
- Salary expectations
- Location preferences
"""

import logging
import json
import re
import hashlib
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from anthropic import AsyncAnthropic

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import (
    Entity, EntityType, EntityStatus,
    Vacancy, VacancyStatus, VacancyApplication, ApplicationStage,
    User, STAGE_SYNC_MAP
)
from ..config import get_settings

logger = logging.getLogger("hr-analyzer.vacancy_recommender")
settings = get_settings()


@dataclass
class AIMatchAnalysis:
    """Result of AI-powered match analysis."""
    overall_score: int = 0  # 0-100
    skills_score: int = 0  # 0-100
    experience_score: int = 0  # 0-100
    culture_fit_score: int = 0  # 0-100
    match_reasons: List[str] = field(default_factory=list)
    missing_requirements: List[str] = field(default_factory=list)
    summary: str = ""
    ai_analyzed: bool = False  # True if this was AI-analyzed, False if fallback

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "overall_score": self.overall_score,
            "skills_score": self.skills_score,
            "experience_score": self.experience_score,
            "culture_fit_score": self.culture_fit_score,
            "match_reasons": self.match_reasons,
            "missing_requirements": self.missing_requirements,
            "summary": self.summary,
            "ai_analyzed": self.ai_analyzed,
        }


class AIMatchCache:
    """Simple in-memory cache for AI match analysis results with TTL."""

    def __init__(self, ttl_minutes: int = 60):
        """
        Initialize cache.

        Args:
            ttl_minutes: Time-to-live for cache entries in minutes
        """
        self._cache: Dict[str, Tuple[AIMatchAnalysis, datetime]] = {}
        self._ttl = timedelta(minutes=ttl_minutes)

    def _make_key(self, entity_id: int, vacancy_id: int) -> str:
        """Create cache key from entity and vacancy IDs."""
        return f"{entity_id}:{vacancy_id}"

    def get(self, entity_id: int, vacancy_id: int) -> Optional[AIMatchAnalysis]:
        """
        Get cached analysis result if exists and not expired.

        Args:
            entity_id: Candidate entity ID
            vacancy_id: Vacancy ID

        Returns:
            Cached AIMatchAnalysis or None if not found/expired
        """
        key = self._make_key(entity_id, vacancy_id)
        if key not in self._cache:
            return None

        result, cached_at = self._cache[key]
        if datetime.utcnow() - cached_at > self._ttl:
            # Entry expired, remove it
            del self._cache[key]
            return None

        return result

    def set(self, entity_id: int, vacancy_id: int, result: AIMatchAnalysis) -> None:
        """
        Store analysis result in cache.

        Args:
            entity_id: Candidate entity ID
            vacancy_id: Vacancy ID
            result: Analysis result to cache
        """
        key = self._make_key(entity_id, vacancy_id)
        self._cache[key] = (result, datetime.utcnow())

    def invalidate(self, entity_id: Optional[int] = None, vacancy_id: Optional[int] = None) -> None:
        """
        Invalidate cache entries.

        Args:
            entity_id: If provided, invalidate all entries for this entity
            vacancy_id: If provided, invalidate all entries for this vacancy
        """
        if entity_id is None and vacancy_id is None:
            # Clear entire cache
            self._cache.clear()
            return

        keys_to_delete = []
        for key in self._cache:
            e_id, v_id = key.split(":")
            if entity_id and int(e_id) == entity_id:
                keys_to_delete.append(key)
            elif vacancy_id and int(v_id) == vacancy_id:
                keys_to_delete.append(key)

        for key in keys_to_delete:
            del self._cache[key]

    def clear_expired(self) -> int:
        """
        Remove all expired entries from cache.

        Returns:
            Number of entries removed
        """
        now = datetime.utcnow()
        keys_to_delete = [
            key for key, (_, cached_at) in self._cache.items()
            if now - cached_at > self._ttl
        ]
        for key in keys_to_delete:
            del self._cache[key]
        return len(keys_to_delete)


# Global cache instance
_ai_match_cache = AIMatchCache(ttl_minutes=60)


@dataclass
class VacancyRecommendation:
    """Represents a vacancy recommendation for a candidate."""
    vacancy_id: int
    vacancy_title: str
    match_score: int  # 0-100
    match_reasons: List[str] = field(default_factory=list)
    missing_requirements: List[str] = field(default_factory=list)
    salary_compatible: bool = True
    location_match: bool = True

    # Additional vacancy info for display
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = "RUB"
    location: Optional[str] = None
    employment_type: Optional[str] = None
    experience_level: Optional[str] = None
    department_name: Optional[str] = None
    applications_count: int = 0

    # AI analysis details
    ai_analyzed: bool = False
    skills_score: Optional[int] = None
    experience_score: Optional[int] = None
    culture_fit_score: Optional[int] = None
    ai_summary: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "vacancy_id": self.vacancy_id,
            "vacancy_title": self.vacancy_title,
            "match_score": self.match_score,
            "match_reasons": self.match_reasons,
            "missing_requirements": self.missing_requirements,
            "salary_compatible": self.salary_compatible,
            "location_match": self.location_match,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "salary_currency": self.salary_currency,
            "location": self.location,
            "employment_type": self.employment_type,
            "experience_level": self.experience_level,
            "department_name": self.department_name,
            "applications_count": self.applications_count,
            "ai_analyzed": self.ai_analyzed,
            "skills_score": self.skills_score,
            "experience_score": self.experience_score,
            "culture_fit_score": self.culture_fit_score,
            "ai_summary": self.ai_summary,
        }


@dataclass
class CandidateMatch:
    """Represents a candidate match for a vacancy."""
    entity_id: int
    entity_name: str
    match_score: int  # 0-100
    match_reasons: List[str] = field(default_factory=list)
    missing_skills: List[str] = field(default_factory=list)
    salary_compatible: bool = True

    # Additional entity info for display
    email: Optional[str] = None
    phone: Optional[str] = None
    position: Optional[str] = None
    status: Optional[str] = None
    expected_salary_min: Optional[int] = None
    expected_salary_max: Optional[int] = None
    expected_salary_currency: str = "RUB"

    # AI analysis details
    ai_analyzed: bool = False
    skills_score: Optional[int] = None
    experience_score: Optional[int] = None
    culture_fit_score: Optional[int] = None
    ai_summary: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "match_score": self.match_score,
            "match_reasons": self.match_reasons,
            "missing_skills": self.missing_skills,
            "salary_compatible": self.salary_compatible,
            "email": self.email,
            "phone": self.phone,
            "position": self.position,
            "status": self.status,
            "expected_salary_min": self.expected_salary_min,
            "expected_salary_max": self.expected_salary_max,
            "expected_salary_currency": self.expected_salary_currency,
            "ai_analyzed": self.ai_analyzed,
            "skills_score": self.skills_score,
            "experience_score": self.experience_score,
            "culture_fit_score": self.culture_fit_score,
            "ai_summary": self.ai_summary,
        }


class VacancyRecommenderService:
    """Service for recommending vacancies to candidates and vice versa."""

    def __init__(self, use_ai: bool = True, cache_ttl_minutes: int = 60):
        """
        Initialize the vacancy recommender service.

        Args:
            use_ai: Whether to use AI analysis (default True)
            cache_ttl_minutes: TTL for AI analysis cache in minutes
        """
        self._client: Optional[AsyncAnthropic] = None
        self.model = settings.claude_model
        self.use_ai = use_ai
        self._cache = AIMatchCache(ttl_minutes=cache_ttl_minutes)

        # Keywords commonly found in job requirements (fallback)
        self.skill_keywords = {
            "python", "javascript", "typescript", "react", "node", "nodejs",
            "java", "kotlin", "swift", "golang", "go", "rust", "c++", "c#",
            "sql", "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
            "docker", "kubernetes", "aws", "azure", "gcp", "devops", "ci/cd",
            "machine learning", "ml", "ai", "data science", "analytics",
            "frontend", "backend", "fullstack", "full-stack", "mobile",
            "ios", "android", "flutter", "react native",
            "agile", "scrum", "kanban", "jira",
            "management", "leadership", "team lead", "product", "pm",
            "sales", "marketing", "hr", "recruiting", "finance",
            "english", "german", "french", "chinese", "spanish",
        }

    @property
    def client(self) -> AsyncAnthropic:
        """Lazy initialization of Anthropic client."""
        if self._client is None:
            if not settings.anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY is not configured")
            self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._client

    def _is_ai_available(self) -> bool:
        """Check if AI analysis is available."""
        return self.use_ai and bool(settings.anthropic_api_key)

    def _extract_skills_from_text(self, text: Optional[str]) -> List[str]:
        """Extract skill keywords from text (requirements, position, tags, etc.)."""
        if not text:
            return []

        text_lower = text.lower()
        found_skills = []

        for skill in self.skill_keywords:
            if skill in text_lower:
                found_skills.append(skill)

        return found_skills

    def _extract_candidate_skills(self, entity: Entity) -> List[str]:
        """Extract skills from candidate's profile."""
        skills = set()

        # From position
        if entity.position:
            skills.update(self._extract_skills_from_text(entity.position))

        # From tags
        if entity.tags:
            for tag in entity.tags:
                skills.update(self._extract_skills_from_text(tag))

        # From extra_data (skills field if present)
        if entity.extra_data:
            if "skills" in entity.extra_data:
                skill_data = entity.extra_data["skills"]
                if isinstance(skill_data, list):
                    for s in skill_data:
                        skills.update(self._extract_skills_from_text(str(s)))
                elif isinstance(skill_data, str):
                    skills.update(self._extract_skills_from_text(skill_data))

            # From resume text if present
            if "resume_text" in entity.extra_data:
                skills.update(self._extract_skills_from_text(
                    str(entity.extra_data["resume_text"])
                ))

        return list(skills)

    def _extract_vacancy_requirements(self, vacancy: Vacancy) -> List[str]:
        """Extract required skills from vacancy."""
        skills = set()

        # From title
        skills.update(self._extract_skills_from_text(vacancy.title))

        # From requirements
        if vacancy.requirements:
            skills.update(self._extract_skills_from_text(vacancy.requirements))

        # From description
        if vacancy.description:
            skills.update(self._extract_skills_from_text(vacancy.description))

        # From tags
        if vacancy.tags:
            for tag in vacancy.tags:
                skills.update(self._extract_skills_from_text(tag))

        return list(skills)

    def _check_salary_compatibility(
        self,
        entity: Entity,
        vacancy: Vacancy
    ) -> tuple[bool, Optional[str]]:
        """
        Check if candidate's salary expectations match vacancy salary range.

        Returns:
            Tuple of (is_compatible, reason_if_not_compatible)
        """
        # If candidate has no salary expectations, consider compatible
        if not entity.expected_salary_min and not entity.expected_salary_max:
            return True, None

        # If vacancy has no salary info, consider compatible
        if not vacancy.salary_min and not vacancy.salary_max:
            return True, None

        # Check currency compatibility (simple approach - same currency)
        entity_currency = entity.expected_salary_currency or "RUB"
        vacancy_currency = vacancy.salary_currency or "RUB"

        if entity_currency != vacancy_currency:
            # For now, mark as potentially incompatible
            return False, f"Валюта не совпадает ({entity_currency} vs {vacancy_currency})"

        # Check salary range overlap
        entity_min = entity.expected_salary_min or 0
        entity_max = entity.expected_salary_max or float('inf')
        vacancy_min = vacancy.salary_min or 0
        vacancy_max = vacancy.salary_max or float('inf')

        # There's overlap if candidate's min <= vacancy's max AND vacancy's min <= candidate's max
        if entity_min <= vacancy_max and vacancy_min <= entity_max:
            return True, None

        if entity_min > vacancy_max:
            return False, f"Ожидания кандидата ({entity_min:,}) выше максимума вакансии ({vacancy_max:,})"

        return False, f"Зарплата вакансии ({vacancy_min:,}) выше ожиданий кандидата ({entity_max:,})"

    def _calculate_match_score(
        self,
        candidate_skills: List[str],
        vacancy_skills: List[str],
        salary_compatible: bool,
        location_match: bool = True
    ) -> int:
        """
        Calculate match score (0-100) based on various factors.

        Scoring weights:
        - Skills match: 60%
        - Salary compatibility: 25%
        - Location match: 15%
        """
        score = 0.0

        # Skills matching (60%)
        if vacancy_skills:
            matched_skills = set(candidate_skills) & set(vacancy_skills)
            skill_score = len(matched_skills) / len(vacancy_skills)
            score += skill_score * 60
        else:
            # No specific skills required, give base score
            score += 30

        # Salary compatibility (25%)
        if salary_compatible:
            score += 25

        # Location match (15%)
        if location_match:
            score += 15

        return min(100, int(score))

    def _build_entity_profile(self, entity: Entity) -> str:
        """Build a comprehensive profile string for the entity."""
        parts = [f"## Кандидат: {entity.name}"]

        if entity.position:
            parts.append(f"- **Текущая позиция:** {entity.position}")
        if entity.company:
            parts.append(f"- **Компания:** {entity.company}")

        # Expected salary
        if entity.expected_salary_min or entity.expected_salary_max:
            currency = entity.expected_salary_currency or 'RUB'
            if entity.expected_salary_min and entity.expected_salary_max:
                parts.append(f"- **Ожидаемая зарплата:** {entity.expected_salary_min:,} - {entity.expected_salary_max:,} {currency}")
            elif entity.expected_salary_min:
                parts.append(f"- **Ожидаемая зарплата:** от {entity.expected_salary_min:,} {currency}")
            elif entity.expected_salary_max:
                parts.append(f"- **Ожидаемая зарплата:** до {entity.expected_salary_max:,} {currency}")

        # Tags/skills
        if entity.tags:
            parts.append(f"- **Теги/навыки:** {', '.join(entity.tags)}")

        # AI Summary if available
        if entity.ai_summary:
            parts.append(f"\n### AI-резюме:\n{entity.ai_summary}")

        # Extra data (filtered)
        extra = entity.extra_data or {}
        if "skills" in extra:
            skills = extra["skills"]
            if isinstance(skills, list):
                parts.append(f"- **Навыки:** {', '.join(str(s) for s in skills)}")
            elif isinstance(skills, str):
                parts.append(f"- **Навыки:** {skills}")

        if "experience" in extra:
            parts.append(f"- **Опыт:** {extra['experience']}")
        if "education" in extra:
            edu = extra["education"]
            if isinstance(edu, list):
                parts.append(f"- **Образование:** {', '.join(str(e) for e in edu)}")
            else:
                parts.append(f"- **Образование:** {edu}")
        if "languages" in extra:
            langs = extra["languages"]
            if isinstance(langs, list):
                parts.append(f"- **Языки:** {', '.join(str(l) for l in langs)}")
            else:
                parts.append(f"- **Языки:** {langs}")
        if "resume_text" in extra:
            resume = str(extra["resume_text"])[:1500]  # Limit to prevent token overflow
            parts.append(f"\n### Текст резюме:\n{resume}")

        return "\n".join(parts)

    def _build_vacancy_profile(self, vacancy: Vacancy) -> str:
        """Build a comprehensive profile string for the vacancy."""
        parts = [f"## Вакансия: {vacancy.title}"]

        if vacancy.description:
            parts.append(f"\n### Описание:\n{vacancy.description}")

        if vacancy.requirements:
            parts.append(f"\n### Требования:\n{vacancy.requirements}")

        if vacancy.responsibilities:
            parts.append(f"\n### Обязанности:\n{vacancy.responsibilities}")

        # Salary range
        if vacancy.salary_min or vacancy.salary_max:
            currency = vacancy.salary_currency or 'RUB'
            if vacancy.salary_min and vacancy.salary_max:
                parts.append(f"- **Зарплата:** {vacancy.salary_min:,} - {vacancy.salary_max:,} {currency}")
            elif vacancy.salary_min:
                parts.append(f"- **Зарплата:** от {vacancy.salary_min:,} {currency}")
            elif vacancy.salary_max:
                parts.append(f"- **Зарплата:** до {vacancy.salary_max:,} {currency}")

        if vacancy.location:
            parts.append(f"- **Локация:** {vacancy.location}")

        if vacancy.employment_type:
            parts.append(f"- **Тип занятости:** {vacancy.employment_type}")

        if vacancy.experience_level:
            parts.append(f"- **Уровень опыта:** {vacancy.experience_level}")

        if vacancy.tags:
            parts.append(f"- **Теги:** {', '.join(vacancy.tags)}")

        return "\n".join(parts)

    def _build_ai_match_prompt(self, entity: Entity, vacancy: Vacancy) -> str:
        """Build the AI match analysis prompt."""
        entity_profile = self._build_entity_profile(entity)
        vacancy_profile = self._build_vacancy_profile(vacancy)

        return f"""Проанализируй соответствие кандидата вакансии.

{entity_profile}

---

{vacancy_profile}

---

Предоставь детальный анализ соответствия в формате JSON:
{{
    "overall_score": <0-100 целое число>,
    "skills_score": <0-100 целое число, соответствие навыков>,
    "experience_score": <0-100 целое число, соответствие опыта>,
    "culture_fit_score": <0-100 целое число, культурное соответствие>,
    "match_reasons": [<список 2-5 причин соответствия на русском>],
    "missing_requirements": [<список 1-4 недостающих требований на русском>],
    "summary": "<1-2 предложения общей оценки на русском>"
}}

Критерии оценки:
- **overall_score**: Общее соответствие (90-100: идеально, 70-89: хорошо, 50-69: средне, 30-49: слабо, 0-29: не подходит)
- **skills_score**: Насколько навыки кандидата соответствуют требованиям (учитывай смежные навыки, не только точные совпадения)
- **experience_score**: Релевантность опыта (годы, индустрия, похожие роли)
- **culture_fit_score**: Оценка культурного соответствия на основе профиля и описания вакансии

Отвечай ТОЛЬКО валидным JSON, без дополнительного текста."""

    def _parse_ai_match_response(self, response_text: str) -> AIMatchAnalysis:
        """Parse AI response into AIMatchAnalysis object."""
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(response_text)

            # Validate and normalize scores
            def normalize_score(value: Any) -> int:
                if isinstance(value, (int, float)):
                    return max(0, min(100, int(value)))
                return 0

            return AIMatchAnalysis(
                overall_score=normalize_score(data.get('overall_score', 0)),
                skills_score=normalize_score(data.get('skills_score', 0)),
                experience_score=normalize_score(data.get('experience_score', 0)),
                culture_fit_score=normalize_score(data.get('culture_fit_score', 0)),
                match_reasons=data.get('match_reasons', [])[:5],
                missing_requirements=data.get('missing_requirements', [])[:4],
                summary=data.get('summary', ''),
                ai_analyzed=True
            )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error(f"Failed to parse AI match response: {e}")
            return AIMatchAnalysis(
                overall_score=50,
                summary="Не удалось проанализировать соответствие из-за ошибки парсинга.",
                ai_analyzed=False
            )

    async def _ai_analyze_match(
        self,
        entity: Entity,
        vacancy: Vacancy,
        use_cache: bool = True
    ) -> AIMatchAnalysis:
        """
        Perform AI-powered match analysis between candidate and vacancy.

        Args:
            entity: Candidate entity
            vacancy: Target vacancy
            use_cache: Whether to use cached results (default True)

        Returns:
            AIMatchAnalysis with detailed scores and reasons
        """
        # Check cache first
        if use_cache:
            cached = self._cache.get(entity.id, vacancy.id)
            if cached:
                logger.debug(f"Cache hit for entity {entity.id} <-> vacancy {vacancy.id}")
                return cached

        # Check if AI is available
        if not self._is_ai_available():
            logger.debug("AI not available, using fallback scoring")
            return self._fallback_match_analysis(entity, vacancy)

        logger.info(f"AI analyzing match: entity {entity.id} <-> vacancy {vacancy.id}")

        prompt = self._build_ai_match_prompt(entity, vacancy)

        system_prompt = """Ты эксперт HR-аналитик, специализирующийся на подборе кандидатов.
Твоя задача - объективно оценить соответствие кандидата вакансии.
Будь сбалансирован и справедлив в оценке - выделяй как сильные стороны, так и потенциальные проблемы.
Всегда отвечай только валидным JSON в запрошенном формате.
Используй русский язык для текстовых полей."""

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=[{
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"}
                }],
                messages=[{"role": "user", "content": prompt}]
            )

            result_text = response.content[0].text
            analysis = self._parse_ai_match_response(result_text)

            # Cache the result
            if use_cache and analysis.ai_analyzed:
                self._cache.set(entity.id, vacancy.id, analysis)

            logger.info(
                f"AI match score: entity {entity.id} <-> vacancy {vacancy.id} = {analysis.overall_score}"
            )

            return analysis

        except Exception as e:
            logger.error(f"AI match analysis error: {e}")
            # Fallback to keyword-based analysis
            return self._fallback_match_analysis(entity, vacancy)

    def _fallback_match_analysis(
        self,
        entity: Entity,
        vacancy: Vacancy
    ) -> AIMatchAnalysis:
        """
        Fallback match analysis using keyword matching when AI is unavailable.

        Args:
            entity: Candidate entity
            vacancy: Target vacancy

        Returns:
            AIMatchAnalysis based on keyword matching
        """
        candidate_skills = self._extract_candidate_skills(entity)
        vacancy_skills = self._extract_vacancy_requirements(vacancy)
        salary_compatible, salary_reason = self._check_salary_compatibility(entity, vacancy)

        # Calculate scores
        skills_score = 0
        if vacancy_skills:
            matched = set(candidate_skills) & set(vacancy_skills)
            skills_score = int((len(matched) / len(vacancy_skills)) * 100)
        else:
            skills_score = 50  # Base score when no specific skills required

        # Simple experience and culture fit scores (fallback uses base values)
        experience_score = 50
        culture_fit_score = 50

        # Overall score calculation
        overall_score = self._calculate_match_score(
            candidate_skills,
            vacancy_skills,
            salary_compatible
        )

        # Build match reasons
        match_reasons = []
        missing_requirements = []

        if candidate_skills and vacancy_skills:
            matched = set(candidate_skills) & set(vacancy_skills)
            missing = set(vacancy_skills) - set(candidate_skills)

            if matched:
                match_reasons.append(f"Совпадающие навыки: {', '.join(sorted(matched))}")

            if missing:
                missing_requirements.append(f"Недостающие навыки: {', '.join(sorted(missing))}")

        if salary_compatible:
            match_reasons.append("Зарплатные ожидания совпадают")
        elif salary_reason:
            missing_requirements.append(salary_reason)

        summary = f"Анализ на основе ключевых слов. Совпадение навыков: {skills_score}%."

        return AIMatchAnalysis(
            overall_score=overall_score,
            skills_score=skills_score,
            experience_score=experience_score,
            culture_fit_score=culture_fit_score,
            match_reasons=match_reasons,
            missing_requirements=missing_requirements,
            summary=summary,
            ai_analyzed=False
        )

    def invalidate_cache(
        self,
        entity_id: Optional[int] = None,
        vacancy_id: Optional[int] = None
    ) -> None:
        """
        Invalidate AI analysis cache.

        Args:
            entity_id: If provided, invalidate all entries for this entity
            vacancy_id: If provided, invalidate all entries for this vacancy
        """
        self._cache.invalidate(entity_id=entity_id, vacancy_id=vacancy_id)

    async def get_recommendations(
        self,
        db: AsyncSession,
        entity: Entity,
        limit: int = 5,
        org_id: Optional[int] = None,
        use_ai: Optional[bool] = None
    ) -> List[VacancyRecommendation]:
        """
        Get vacancy recommendations for a candidate.

        Args:
            db: Database session
            entity: Entity (candidate) to get recommendations for
            limit: Maximum number of recommendations
            org_id: Optional organization ID to filter vacancies
            use_ai: Whether to use AI analysis (defaults to self.use_ai)

        Returns:
            List of VacancyRecommendation objects sorted by match score
        """
        if entity.type != EntityType.candidate:
            logger.warning(f"Entity {entity.id} is not a candidate, skipping recommendations")
            return []

        # Determine whether to use AI
        should_use_ai = use_ai if use_ai is not None else self.use_ai

        # Get active vacancies not already applied to
        applied_vacancy_ids_query = (
            select(VacancyApplication.vacancy_id)
            .where(VacancyApplication.entity_id == entity.id)
        )
        applied_result = await db.execute(applied_vacancy_ids_query)
        applied_vacancy_ids = {row[0] for row in applied_result.all()}

        # Query active vacancies
        vacancy_query = select(Vacancy).where(
            Vacancy.status == VacancyStatus.open
        )

        if org_id:
            vacancy_query = vacancy_query.where(Vacancy.org_id == org_id)

        if applied_vacancy_ids:
            vacancy_query = vacancy_query.where(
                Vacancy.id.notin_(applied_vacancy_ids)
            )

        vacancy_result = await db.execute(vacancy_query)
        vacancies = vacancy_result.scalars().all()

        # Try embeddings-based matching first (fast <100ms)
        embedding_results = await self._get_recommendations_via_embeddings(
            db, entity, limit * 2, org_id, applied_vacancy_ids
        )

        if embedding_results:
            logger.info(f"Using embeddings for recommendations, found {len(embedding_results)} matches")
            return embedding_results[:limit]

        # Fallback to existing logic (AI or keyword-based)
        logger.debug("Embeddings not available, using AI/keyword-based recommendations")

        recommendations = []

        for vacancy in vacancies:
            # Check salary compatibility (needed for both AI and fallback)
            salary_compatible, _ = self._check_salary_compatibility(entity, vacancy)

            # Use AI analysis if enabled and available
            if should_use_ai and self._is_ai_available():
                analysis = await self._ai_analyze_match(entity, vacancy)
                match_score = analysis.overall_score
                match_reasons = analysis.match_reasons
                missing_requirements = analysis.missing_requirements
                ai_analyzed = analysis.ai_analyzed
                skills_score = analysis.skills_score
                experience_score = analysis.experience_score
                culture_fit_score = analysis.culture_fit_score
                ai_summary = analysis.summary
            else:
                # Fallback to keyword-based analysis
                analysis = self._fallback_match_analysis(entity, vacancy)
                match_score = analysis.overall_score
                match_reasons = analysis.match_reasons
                missing_requirements = analysis.missing_requirements
                ai_analyzed = False
                skills_score = analysis.skills_score
                experience_score = analysis.experience_score
                culture_fit_score = analysis.culture_fit_score
                ai_summary = analysis.summary

            # Get applications count
            apps_count_result = await db.execute(
                select(func.count(VacancyApplication.id))
                .where(VacancyApplication.vacancy_id == vacancy.id)
            )
            apps_count = apps_count_result.scalar() or 0

            # Get department name if exists
            dept_name = None
            if vacancy.department_id:
                from ..models.database import Department
                dept_result = await db.execute(
                    select(Department.name).where(Department.id == vacancy.department_id)
                )
                dept_name = dept_result.scalar()

            recommendations.append(VacancyRecommendation(
                vacancy_id=vacancy.id,
                vacancy_title=vacancy.title,
                match_score=match_score,
                match_reasons=match_reasons,
                missing_requirements=missing_requirements,
                salary_compatible=salary_compatible,
                salary_min=vacancy.salary_min,
                salary_max=vacancy.salary_max,
                salary_currency=vacancy.salary_currency or "RUB",
                location=vacancy.location,
                employment_type=vacancy.employment_type,
                experience_level=vacancy.experience_level,
                department_name=dept_name,
                applications_count=apps_count,
                ai_analyzed=ai_analyzed,
                skills_score=skills_score,
                experience_score=experience_score,
                culture_fit_score=culture_fit_score,
                ai_summary=ai_summary,
            ))

        # Sort by match score (descending) and limit
        recommendations.sort(key=lambda r: r.match_score, reverse=True)

        logger.info(
            f"Generated {len(recommendations[:limit])} recommendations for entity {entity.id} "
            f"(AI: {should_use_ai and self._is_ai_available()})"
        )

        return recommendations[:limit]

    async def find_matching_candidates(
        self,
        db: AsyncSession,
        vacancy: Vacancy,
        limit: int = 10,
        exclude_applied: bool = True,
        use_ai: Optional[bool] = None
    ) -> List[CandidateMatch]:
        """
        Find candidates that match a vacancy.

        Args:
            db: Database session
            vacancy: Vacancy to find candidates for
            limit: Maximum number of candidates
            exclude_applied: Whether to exclude already applied candidates
            use_ai: Whether to use AI analysis (defaults to self.use_ai)

        Returns:
            List of CandidateMatch objects sorted by match score
        """
        # Determine whether to use AI
        should_use_ai = use_ai if use_ai is not None else self.use_ai

        # Get already applied entity IDs
        applied_entity_ids = set()
        if exclude_applied:
            applied_query = (
                select(VacancyApplication.entity_id)
                .where(VacancyApplication.vacancy_id == vacancy.id)
            )
            applied_result = await db.execute(applied_query)
            applied_entity_ids = {row[0] for row in applied_result.all()}

        # Query candidates in the same organization
        candidate_query = select(Entity).where(
            and_(
                Entity.type == EntityType.candidate,
                Entity.org_id == vacancy.org_id,
                Entity.status.notin_([EntityStatus.rejected, EntityStatus.hired])
            )
        )

        if applied_entity_ids:
            candidate_query = candidate_query.where(
                Entity.id.notin_(applied_entity_ids)
            )

        candidate_result = await db.execute(candidate_query)
        candidates = candidate_result.scalars().all()

        # Try embeddings-based matching first (fast <100ms)
        embedding_matches = await self._find_matching_candidates_via_embeddings(
            db, vacancy, limit * 2, applied_entity_ids
        )

        if embedding_matches:
            logger.info(f"Using embeddings for candidate matching, found {len(embedding_matches)} matches")
            return embedding_matches[:limit]

        # Fallback to existing logic
        logger.debug("Embeddings not available, using AI/keyword-based matching")

        matches = []

        for candidate in candidates:
            # Check salary compatibility (needed for both AI and fallback)
            salary_compatible, _ = self._check_salary_compatibility(candidate, vacancy)

            # Use AI analysis if enabled and available
            if should_use_ai and self._is_ai_available():
                analysis = await self._ai_analyze_match(candidate, vacancy)
                match_score = analysis.overall_score
                match_reasons = analysis.match_reasons
                missing_skills = analysis.missing_requirements
                ai_analyzed = analysis.ai_analyzed
                skills_score = analysis.skills_score
                experience_score = analysis.experience_score
                culture_fit_score = analysis.culture_fit_score
                ai_summary = analysis.summary
            else:
                # Fallback to keyword-based analysis
                analysis = self._fallback_match_analysis(candidate, vacancy)
                match_score = analysis.overall_score
                match_reasons = analysis.match_reasons
                missing_skills = analysis.missing_requirements
                ai_analyzed = False
                skills_score = analysis.skills_score
                experience_score = analysis.experience_score
                culture_fit_score = analysis.culture_fit_score
                ai_summary = analysis.summary

            matches.append(CandidateMatch(
                entity_id=candidate.id,
                entity_name=candidate.name,
                match_score=match_score,
                match_reasons=match_reasons,
                missing_skills=missing_skills,
                salary_compatible=salary_compatible,
                email=candidate.email,
                phone=candidate.phone,
                position=candidate.position,
                status=candidate.status.value if candidate.status else None,
                expected_salary_min=candidate.expected_salary_min,
                expected_salary_max=candidate.expected_salary_max,
                expected_salary_currency=candidate.expected_salary_currency or "RUB",
                ai_analyzed=ai_analyzed,
                skills_score=skills_score,
                experience_score=experience_score,
                culture_fit_score=culture_fit_score,
                ai_summary=ai_summary,
            ))

        # Sort by match score (descending) and limit
        matches.sort(key=lambda m: m.match_score, reverse=True)

        logger.info(
            f"Found {len(matches[:limit])} matching candidates for vacancy {vacancy.id} "
            f"(AI: {should_use_ai and self._is_ai_available()})"
        )

        return matches[:limit]

    async def auto_apply(
        self,
        db: AsyncSession,
        entity: Entity,
        vacancy: Vacancy,
        source: str = "auto_recommendation",
        created_by: Optional[int] = None
    ) -> Optional[VacancyApplication]:
        """
        Create an automatic application for a candidate to a vacancy.

        Args:
            db: Database session
            entity: Candidate entity
            vacancy: Target vacancy
            source: Source of the application
            created_by: User ID who initiated the auto-apply

        Returns:
            Created VacancyApplication or None if already applied
        """
        # Check if already applied
        existing_query = select(VacancyApplication).where(
            and_(
                VacancyApplication.vacancy_id == vacancy.id,
                VacancyApplication.entity_id == entity.id
            )
        )
        existing_result = await db.execute(existing_query)
        if existing_result.scalar():
            logger.info(
                f"Entity {entity.id} already applied to vacancy {vacancy.id}"
            )
            return None

        # Get max stage_order for 'applied' stage (HR pipeline - shown as "Новый" in UI)
        max_order_result = await db.execute(
            select(func.max(VacancyApplication.stage_order))
            .where(
                VacancyApplication.vacancy_id == vacancy.id,
                VacancyApplication.stage == ApplicationStage.applied
            )
        )
        max_order = max_order_result.scalar() or 0

        # Есть ли у кандидата другие воронки — до добавления этой (иначе
        # autoflush посчитает и её).
        has_other = (await db.execute(
            select(func.count(VacancyApplication.id)).where(VacancyApplication.entity_id == entity.id)
        )).scalar() or 0

        # Create application
        application = VacancyApplication(
            vacancy_id=vacancy.id,
            entity_id=entity.id,
            stage=ApplicationStage.applied,  # Use 'applied' (exists in DB enum, shown as "Новый" in UI)
            stage_order=max_order + 1,
            source=source,
            created_by=created_by,
            notes=f"Автоматическая заявка на основе рекомендации"
        )

        db.add(application)

        # Общий статус — только по ПЕРВОЙ воронке и не у сотрудников (то же
        # правило, что у «Добавить в воронку»): раньше рекомендация сбрасывала
        # в «Новый» и человека на оффере, и уволенного (20.10.2026).
        expected_entity_status = STAGE_SYNC_MAP.get(ApplicationStage.applied)
        keep = {EntityStatus.transferred, EntityStatus.dismissed, EntityStatus.quit}
        if has_other or entity.status in keep:
            expected_entity_status = None
        if expected_entity_status and entity.status != expected_entity_status:
            entity.status = expected_entity_status
            entity.updated_at = datetime.utcnow()
            logger.info(f"auto_apply: Synchronized entity {entity.id} status to {expected_entity_status}")

        await db.commit()
        await db.refresh(application)

        # Начальный транзишн в историю (как в create_application).
        from .stage_transitions import record_transition
        await record_transition(
            db=db,
            application_id=application.id,
            entity_id=entity.id,
            from_stage=None,
            to_stage=application.stage.value,
            changed_by_id=created_by,
            comment="Первичная заявка",
        )
        await db.commit()

        logger.info(
            f"Auto-applied entity {entity.id} to vacancy {vacancy.id}"
        )

        return application

    async def notify_new_vacancy(
        self,
        db: AsyncSession,
        vacancy: Vacancy,
        match_threshold: int = 50,
        limit: int = 20
    ) -> List[CandidateMatch]:
        """
        Find candidates to notify about a new vacancy.

        This method finds matching candidates that could be interested
        in the new vacancy based on their profile and preferences.

        Args:
            db: Database session
            vacancy: Newly created/opened vacancy
            match_threshold: Minimum match score to include (0-100)
            limit: Maximum candidates to notify

        Returns:
            List of CandidateMatch objects that should be notified
        """
        # Find matching candidates
        all_matches = await self.find_matching_candidates(
            db=db,
            vacancy=vacancy,
            limit=limit * 2,  # Get more to filter by threshold
            exclude_applied=True
        )

        # Filter by match threshold
        qualified_matches = [
            m for m in all_matches
            if m.match_score >= match_threshold
        ]

        logger.info(
            f"Found {len(qualified_matches[:limit])} candidates to notify "
            f"for vacancy {vacancy.id} (threshold: {match_threshold})"
        )

        return qualified_matches[:limit]

    async def _get_recommendations_via_embeddings(
        self,
        db: AsyncSession,
        entity: Entity,
        limit: int,
        org_id: Optional[int],
        applied_vacancy_ids: set
    ) -> List["VacancyRecommendation"]:
        """
        Fast vacancy recommendations using embeddings (pgvector).

        Returns empty list if embeddings are not available.
        """
        try:
            from .similarity_search import similarity_search

            # Check if entity has embedding
            if not hasattr(entity, 'embedding') or entity.embedding is None:
                return []

            effective_org_id = org_id or entity.org_id

            # Find matching vacancies via embeddings
            results = await similarity_search.find_matching_vacancies(
                db=db,
                entity_id=entity.id,
                org_id=effective_org_id,
                limit=limit,
                min_score=0.2  # Lower threshold
            )

            if not results:
                return []

            # Filter out already applied vacancies
            results = [r for r in results if r.id not in applied_vacancy_ids]

            # Convert to VacancyRecommendation format
            recommendations = []
            for r in results:
                match_reasons = []
                if r.tags:
                    match_reasons.append(f"Общие навыки: {', '.join(r.tags[:3])}")
                if r.score >= 0.7:
                    match_reasons.append("Высокое AI-сходство профиля с вакансией")
                elif r.score >= 0.5:
                    match_reasons.append("Среднее AI-сходство с требованиями")

                recommendations.append(VacancyRecommendation(
                    vacancy_id=r.id,
                    vacancy_title=r.name,
                    match_score=int(r.score * 100),
                    match_reasons=match_reasons,
                    missing_requirements=[],  # Not calculated in embeddings
                    salary_compatible=True,  # Assume compatible for fast results
                    salary_min=None,
                    salary_max=None,
                    salary_currency="RUB",
                    location=None,
                    employment_type=None,
                    experience_level=r.position,
                    department_name=None,
                    applications_count=0,
                    ai_analyzed=True,  # Embeddings are AI-based
                    skills_score=int(r.score * 100),
                    experience_score=int(r.score * 80),
                    culture_fit_score=50,  # Neutral
                    ai_summary=f"AI-сходство: {int(r.score * 100)}%",
                ))

            return recommendations

        except ImportError:
            logger.debug("similarity_search module not available")
            return []
        except Exception as e:
            logger.warning(f"Embeddings recommendations failed: {e}")
            return []

    async def _find_matching_candidates_via_embeddings(
        self,
        db: AsyncSession,
        vacancy: Vacancy,
        limit: int,
        applied_entity_ids: set
    ) -> List["CandidateMatch"]:
        """
        Fast candidate matching using embeddings (pgvector).

        Returns empty list if embeddings are not available.
        """
        try:
            from .similarity_search import similarity_search

            # Check if vacancy has embedding
            if not hasattr(vacancy, 'embedding') or vacancy.embedding is None:
                return []

            # Find matching candidates via embeddings
            results = await similarity_search.find_matching_candidates(
                db=db,
                vacancy_id=vacancy.id,
                org_id=vacancy.org_id,
                limit=limit,
                min_score=0.2
            )

            if not results:
                return []

            # Filter out already applied
            results = [r for r in results if r.id not in applied_entity_ids]

            # Convert to CandidateMatch format
            matches = []
            for r in results:
                match_reasons = []
                missing_skills = []

                if r.tags:
                    match_reasons.append(f"Навыки: {', '.join(r.tags[:3])}")
                if r.score >= 0.7:
                    match_reasons.append("Высокое AI-сходство с требованиями")
                elif r.score >= 0.5:
                    match_reasons.append("Среднее AI-сходство")

                matches.append(CandidateMatch(
                    entity_id=r.id,
                    entity_name=r.name,
                    match_score=int(r.score * 100),
                    match_reasons=match_reasons,
                    missing_skills=missing_skills,
                    salary_compatible=True,
                    email=r.email,
                    phone=r.phone,
                    position=r.position,
                    status=r.status,
                    expected_salary_min=None,
                    expected_salary_max=None,
                    expected_salary_currency="RUB",
                    ai_analyzed=True,
                    skills_score=int(r.score * 100),
                    experience_score=int(r.score * 80),
                    culture_fit_score=50,
                    ai_summary=f"AI-сходство: {int(r.score * 100)}%",
                ))

            return matches

        except ImportError:
            logger.debug("similarity_search module not available")
            return []
        except Exception as e:
            logger.warning(f"Embeddings matching failed: {e}")
            return []


# Global service instance
vacancy_recommender = VacancyRecommenderService()
