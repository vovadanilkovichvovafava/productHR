"""
AI Scoring Service - Candidate-Vacancy Compatibility Scoring.

Provides AI-powered compatibility scoring between candidates and vacancies:
- Overall compatibility score (0-100)
- Skills match scoring
- Experience match scoring
- Salary expectations match
- Culture fit assessment
- Strengths and weaknesses analysis
- Hiring recommendation

Uses Claude API for intelligent analysis.
"""
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
from anthropic import AsyncAnthropic
import json
import re

from ..config import get_settings
from ..models.database import Entity, Vacancy

logger = logging.getLogger("hr-analyzer.ai-scoring")
settings = get_settings()


class Recommendation(str, Enum):
    """Hiring recommendation based on compatibility score."""
    HIRE = "hire"           # Strong recommendation to hire (score >= 70)
    MAYBE = "maybe"         # Consider with reservations (score 40-69)
    REJECT = "reject"       # Not recommended (score < 40)


@dataclass
class CompatibilityScore:
    """Detailed compatibility score between candidate and vacancy."""

    # Core scores (0-100)
    overall_score: int = 0
    skills_match: int = 0
    experience_match: int = 0
    salary_match: int = 0
    culture_fit: int = 0

    # Analysis
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    recommendation: str = Recommendation.MAYBE.value

    # Additional context
    summary: str = ""
    key_factors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CompatibilityScore":
        """Create from dictionary."""
        return cls(**data)


class AIScoringService:
    """AI-powered candidate-vacancy compatibility scoring service."""

    def __init__(self):
        self._client: Optional[AsyncAnthropic] = None
        self.model = settings.claude_model

    @property
    def client(self) -> AsyncAnthropic:
        """Lazy initialization of Anthropic client."""
        if self._client is None:
            if not settings.anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY is not configured")
            self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._client

    def _extract_entity_skills(self, entity: Entity) -> List[str]:
        """Extract skills from entity extra_data."""
        skills = []
        extra_data = entity.extra_data or {}

        # Check common skill field names
        for key in ['skills', 'skill_list', 'technical_skills', 'competencies']:
            if key in extra_data:
                value = extra_data[key]
                if isinstance(value, list):
                    skills.extend(value)
                elif isinstance(value, str):
                    skills.extend([s.strip() for s in value.split(',') if s.strip()])

        # Also check tags for skills
        if entity.tags:
            skills.extend(entity.tags)

        return list(set(skills))  # Deduplicate

    def _extract_entity_experience(self, entity: Entity) -> Optional[int]:
        """Extract years of experience from entity extra_data."""
        extra_data = entity.extra_data or {}

        # Check common experience field names
        for key in ['experience', 'experience_years', 'years_experience', 'years_of_experience']:
            if key in extra_data:
                value = extra_data[key]
                if isinstance(value, (int, float)):
                    return int(value)
                elif isinstance(value, str):
                    # Try to extract number from string like "5 years" or "3+"
                    numbers = re.findall(r'\d+', value)
                    if numbers:
                        return int(numbers[0])

        return None

    def _build_entity_profile(self, entity: Entity) -> str:
        """Build a comprehensive profile string for the entity."""
        parts = [f"## Candidate: {entity.name}"]

        if entity.position:
            parts.append(f"- **Current Position:** {entity.position}")
        if entity.company:
            parts.append(f"- **Current Company:** {entity.company}")
        if entity.email:
            parts.append(f"- **Email:** {entity.email}")

        # Status
        parts.append(f"- **Status:** {entity.status.value}")

        # Expected salary
        if entity.expected_salary_min or entity.expected_salary_max:
            currency = entity.expected_salary_currency or 'RUB'
            if entity.expected_salary_min and entity.expected_salary_max:
                parts.append(f"- **Expected Salary:** {entity.expected_salary_min:,} - {entity.expected_salary_max:,} {currency}")
            elif entity.expected_salary_min:
                parts.append(f"- **Expected Salary:** from {entity.expected_salary_min:,} {currency}")
            elif entity.expected_salary_max:
                parts.append(f"- **Expected Salary:** up to {entity.expected_salary_max:,} {currency}")

        # Skills
        skills = self._extract_entity_skills(entity)
        if skills:
            parts.append(f"- **Skills:** {', '.join(skills)}")

        # Experience
        experience = self._extract_entity_experience(entity)
        if experience:
            parts.append(f"- **Experience:** {experience} years")

        # AI Summary if available
        if entity.ai_summary:
            parts.append(f"\n### AI Summary:\n{entity.ai_summary}")

        # Extra data (filtered)
        extra = entity.extra_data or {}
        relevant_fields = ['education', 'languages', 'location', 'achievements', 'certifications', 'about']
        for key in relevant_fields:
            if key in extra and extra[key]:
                value = extra[key]
                if isinstance(value, list):
                    value = ', '.join(str(v) for v in value)
                parts.append(f"- **{key.title()}:** {value}")

        return "\n".join(parts)

    def _build_vacancy_profile(self, vacancy: Vacancy) -> str:
        """Build a comprehensive profile string for the vacancy."""
        parts = [f"## Vacancy: {vacancy.title}"]

        if vacancy.description:
            parts.append(f"\n### Description:\n{vacancy.description}")

        if vacancy.requirements:
            parts.append(f"\n### Requirements:\n{vacancy.requirements}")

        if vacancy.responsibilities:
            parts.append(f"\n### Responsibilities:\n{vacancy.responsibilities}")

        # Salary range
        if vacancy.salary_min or vacancy.salary_max:
            currency = vacancy.salary_currency or 'RUB'
            if vacancy.salary_min and vacancy.salary_max:
                parts.append(f"- **Salary Range:** {vacancy.salary_min:,} - {vacancy.salary_max:,} {currency}")
            elif vacancy.salary_min:
                parts.append(f"- **Salary:** from {vacancy.salary_min:,} {currency}")
            elif vacancy.salary_max:
                parts.append(f"- **Salary:** up to {vacancy.salary_max:,} {currency}")

        if vacancy.location:
            parts.append(f"- **Location:** {vacancy.location}")

        if vacancy.employment_type:
            parts.append(f"- **Employment Type:** {vacancy.employment_type}")

        if vacancy.experience_level:
            parts.append(f"- **Experience Level:** {vacancy.experience_level}")

        if vacancy.tags:
            parts.append(f"- **Tags:** {', '.join(vacancy.tags)}")

        return "\n".join(parts)

    def _build_scoring_prompt(self, entity: Entity, vacancy: Vacancy) -> str:
        """Build the scoring analysis prompt."""
        entity_profile = self._build_entity_profile(entity)
        vacancy_profile = self._build_vacancy_profile(vacancy)

        return f"""Analyze the compatibility between this candidate and vacancy.

{entity_profile}

---

{vacancy_profile}

---

Provide a detailed compatibility analysis in JSON format with the following structure:
{{
    "overall_score": <0-100 integer>,
    "skills_match": <0-100 integer>,
    "experience_match": <0-100 integer>,
    "salary_match": <0-100 integer>,
    "culture_fit": <0-100 integer>,
    "strengths": [<list of 2-5 candidate strengths for this role>],
    "weaknesses": [<list of 1-4 potential risks or missing qualifications>],
    "recommendation": "<hire|maybe|reject>",
    "summary": "<1-2 sentence overall assessment>",
    "key_factors": [<list of 2-3 key decision factors>]
}}

Scoring Guidelines:
- **overall_score**: Overall fit (90-100: ideal, 70-89: strong, 50-69: moderate, 30-49: weak, 0-29: poor)
- **skills_match**: How well candidate's skills match requirements (technical + soft skills)
- **experience_match**: Experience level relevance (years, industry, similar roles)
- **salary_match**: Alignment between expectations and offered range (100 if within range, lower if mismatch)
- **culture_fit**: Estimated cultural alignment based on profile and vacancy description

Recommendation:
- "hire": score >= 70, strong match, recommend proceeding
- "maybe": score 40-69, some concerns but worth considering
- "reject": score < 40, significant mismatches

Respond ONLY with valid JSON, no additional text."""

    def _parse_ai_response(self, response_text: str) -> CompatibilityScore:
        """Parse AI response into CompatibilityScore object."""
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

            return CompatibilityScore(
                overall_score=normalize_score(data.get('overall_score', 0)),
                skills_match=normalize_score(data.get('skills_match', 0)),
                experience_match=normalize_score(data.get('experience_match', 0)),
                salary_match=normalize_score(data.get('salary_match', 0)),
                culture_fit=normalize_score(data.get('culture_fit', 0)),
                strengths=data.get('strengths', [])[:5],
                weaknesses=data.get('weaknesses', [])[:4],
                recommendation=data.get('recommendation', Recommendation.MAYBE.value),
                summary=data.get('summary', ''),
                key_factors=data.get('key_factors', [])[:3]
            )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error(f"Failed to parse AI scoring response: {e}")
            # Return default score on parse failure
            return CompatibilityScore(
                overall_score=50,
                summary="Could not analyze compatibility due to parsing error."
            )

    async def calculate_compatibility(
        self,
        entity: Entity,
        vacancy: Vacancy
    ) -> CompatibilityScore:
        """
        Calculate AI-powered compatibility score between candidate and vacancy.

        Args:
            entity: The candidate entity
            vacancy: The job vacancy

        Returns:
            CompatibilityScore with detailed analysis
        """
        logger.info(f"Calculating compatibility: entity {entity.id} <-> vacancy {vacancy.id}")

        prompt = self._build_scoring_prompt(entity, vacancy)

        system_prompt = """You are an expert HR analyst specializing in candidate-vacancy matching.
Your task is to objectively evaluate how well a candidate fits a job vacancy.
Be balanced and fair in your assessment - highlight both strengths and potential concerns.
Always respond with valid JSON only, following the exact structure requested.
Use Russian language for text fields (summary, strengths, weaknesses, key_factors).
"""

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=[{
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"}
                }],
                messages=[{"role": "user", "content": prompt}]
            )

            result_text = response.content[0].text
            score = self._parse_ai_response(result_text)

            logger.info(
                f"Compatibility calculated: entity {entity.id} <-> vacancy {vacancy.id} = {score.overall_score}"
            )

            return score

        except Exception as e:
            logger.error(f"AI scoring error: {e}")
            # Return a default score on error
            return CompatibilityScore(
                overall_score=50,
                summary=f"Could not calculate compatibility: {str(e)}"
            )

    async def bulk_score(
        self,
        entities: List[Entity],
        vacancy: Vacancy,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Score multiple candidates against a single vacancy.

        Args:
            entities: List of candidate entities
            vacancy: The job vacancy
            limit: Optional limit on number to score

        Returns:
            List of dicts with entity_id and compatibility score
        """
        if limit:
            entities = entities[:limit]

        results = []
        for entity in entities:
            try:
                score = await self.calculate_compatibility(entity, vacancy)
                results.append({
                    "entity_id": entity.id,
                    "entity_name": entity.name,
                    "score": score.to_dict()
                })
            except Exception as e:
                logger.error(f"Error scoring entity {entity.id}: {e}")
                results.append({
                    "entity_id": entity.id,
                    "entity_name": entity.name,
                    "score": CompatibilityScore(
                        overall_score=0,
                        summary=f"Error: {str(e)}"
                    ).to_dict()
                })

        # Sort by overall score descending
        results.sort(key=lambda x: x["score"]["overall_score"], reverse=True)

        return results

    async def find_best_matches(
        self,
        vacancy: Vacancy,
        candidates: List[Entity],
        limit: int = 10,
        min_score: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Find the best matching candidates for a vacancy.

        Args:
            vacancy: The job vacancy
            candidates: List of candidate entities to evaluate
            limit: Maximum number of matches to return
            min_score: Minimum overall score threshold

        Returns:
            List of top matching candidates with scores, sorted by score
        """
        results = await self.bulk_score(candidates, vacancy)

        # Filter by minimum score
        if min_score > 0:
            results = [r for r in results if r["score"]["overall_score"] >= min_score]

        # Return top matches up to limit
        return results[:limit]

    async def find_matching_vacancies(
        self,
        entity: Entity,
        vacancies: List[Vacancy],
        limit: int = 10,
        min_score: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Find the best matching vacancies for a candidate.

        Args:
            entity: The candidate entity
            vacancies: List of vacancies to evaluate
            limit: Maximum number of matches to return
            min_score: Minimum overall score threshold

        Returns:
            List of top matching vacancies with scores, sorted by score
        """
        results = []

        for vacancy in vacancies:
            try:
                score = await self.calculate_compatibility(entity, vacancy)
                results.append({
                    "vacancy_id": vacancy.id,
                    "vacancy_title": vacancy.title,
                    "score": score.to_dict()
                })
            except Exception as e:
                logger.error(f"Error scoring vacancy {vacancy.id}: {e}")
                results.append({
                    "vacancy_id": vacancy.id,
                    "vacancy_title": vacancy.title,
                    "score": CompatibilityScore(
                        overall_score=0,
                        summary=f"Error: {str(e)}"
                    ).to_dict()
                })

        # Sort by overall score descending
        results.sort(key=lambda x: x["score"]["overall_score"], reverse=True)

        # Filter by minimum score
        if min_score > 0:
            results = [r for r in results if r["score"]["overall_score"] >= min_score]

        # Return top matches up to limit
        return results[:limit]


# Singleton instance
ai_scoring_service = AIScoringService()
