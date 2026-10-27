"""
Smart Search Service for HR-bot.

Provides AI-powered natural language search for candidates with:
- Query parsing to structured filters
- Full-text search across all fields
- Relevance ranking with scoring
"""

import json
import logging
import re
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field, asdict
from anthropic import AsyncAnthropic
from sqlalchemy import select, func, or_, and_, cast, String, Float
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import get_settings
from ..models.database import Entity, EntityType, EntityStatus

logger = logging.getLogger("hr-analyzer.smart_search")
settings = get_settings()


@dataclass
class ParsedSearchQuery:
    """Structured search query parsed from natural language."""

    # Skills and technologies
    skills: List[str] = field(default_factory=list)

    # Experience requirements
    experience_min_years: Optional[int] = None
    experience_max_years: Optional[int] = None
    experience_level: Optional[str] = None  # junior, middle, senior, lead

    # Salary requirements
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: Optional[str] = None

    # Location
    location: Optional[str] = None
    remote_ok: Optional[bool] = None

    # Position/role
    position: Optional[str] = None

    # Entity type and status
    entity_type: Optional[str] = None
    status: Optional[str] = None

    # Tags
    tags: List[str] = field(default_factory=list)

    # Full-text search terms (what doesn't fit into structured fields)
    text_query: Optional[str] = None

    # Original query for reference
    original_query: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {k: v for k, v in asdict(self).items() if v is not None and v != []}


class SmartSearchService:
    """Service for AI-powered smart search of candidates."""

    def __init__(self):
        self._client = None
        self.model = settings.claude_model

    @property
    def client(self) -> AsyncAnthropic:
        """Lazy initialization of Anthropic client."""
        if self._client is None:
            if not settings.anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY not configured")
            self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._client

    async def parse_search_query(self, query: str) -> ParsedSearchQuery:
        """
        Parse natural language search query into structured filters using AI.

        Args:
            query: Natural language search query (e.g., "Python developers with 3+ years experience")

        Returns:
            ParsedSearchQuery with structured filters
        """
        # If query is very short or simple, try rule-based parsing first
        parsed = self._rule_based_parse(query)

        # For complex queries, use AI parsing
        if self._needs_ai_parsing(query, parsed):
            try:
                ai_parsed = await self._ai_parse_query(query)
                # Merge AI results with rule-based results
                parsed = self._merge_parsed_queries(parsed, ai_parsed)
            except Exception as e:
                logger.warning(f"AI parsing failed, using rule-based results: {e}")

        parsed.original_query = query
        return parsed

    def _rule_based_parse(self, query: str) -> ParsedSearchQuery:
        """
        Rule-based parsing for common patterns.

        Handles patterns like:
        - "Python developer" -> skill: Python, position: developer
        - "3+ years experience" -> experience_min_years: 3
        - "salary up to 200000" -> salary_max: 200000
        - "Moscow" -> location: Moscow
        """
        parsed = ParsedSearchQuery()
        query_lower = query.lower()

        # Extract experience patterns
        exp_patterns = [
            (r'(?:опыт|experience)\s*(?:от|from)?\s*(\d+)\s*(?:лет|год|years?)', 'min'),
            (r'(\d+)\+?\s*(?:лет|год|years?)\s*(?:опыт|experience)?', 'min'),
            (r'(?:до|to|up\s*to)\s*(\d+)\s*(?:лет|год|years?)', 'max'),
        ]
        for pattern, exp_type in exp_patterns:
            match = re.search(pattern, query_lower)
            if match:
                years = int(match.group(1))
                if exp_type == 'min':
                    parsed.experience_min_years = years
                else:
                    parsed.experience_max_years = years

        # Extract salary patterns
        salary_patterns = [
            (r'(?:зарплата|salary|зп)\s*(?:от|from)?\s*(\d+)', 'min'),
            (r'(?:от|from)\s*(\d+)\s*(?:руб|рублей|\$|usd|eur|€)?', 'min'),
            (r'(?:до|to|up\s*to)\s*(\d+)\s*(?:руб|рублей|\$|usd|eur|€)?', 'max'),
            (r'(\d{5,})\s*(?:руб|рублей|\$|usd|eur|€)?', 'any'),
        ]
        for pattern, sal_type in salary_patterns:
            match = re.search(pattern, query_lower)
            if match:
                amount = int(match.group(1))
                if sal_type == 'min':
                    parsed.salary_min = amount
                elif sal_type == 'max':
                    parsed.salary_max = amount
                elif sal_type == 'any' and not parsed.salary_min and not parsed.salary_max:
                    # Assume it's a max if no direction specified
                    parsed.salary_max = amount

        # Detect currency
        if '$' in query or 'usd' in query_lower:
            parsed.salary_currency = 'USD'
        elif '€' in query or 'eur' in query_lower:
            parsed.salary_currency = 'EUR'
        elif 'руб' in query_lower:
            parsed.salary_currency = 'RUB'

        # Extract experience level
        level_patterns = {
            'junior': r'\b(?:junior|джуниор|джун)\b',
            'middle': r'\b(?:middle|мидл|средний)\b',
            'senior': r'\b(?:senior|сеньор|старший)\b',
            'lead': r'\b(?:lead|лид|ведущий|тимлид|team\s*lead)\b',
        }
        for level, pattern in level_patterns.items():
            if re.search(pattern, query_lower):
                parsed.experience_level = level
                break

        # Extract common skills/technologies
        tech_keywords = [
            'python', 'java', 'javascript', 'typescript', 'react', 'vue', 'angular',
            'node', 'nodejs', 'go', 'golang', 'rust', 'c++', 'c#', 'php', 'ruby',
            'sql', 'postgresql', 'mysql', 'mongodb', 'redis', 'docker', 'kubernetes',
            'aws', 'azure', 'gcp', 'linux', 'devops', 'ci/cd', 'git', 'agile',
            'flutter', 'swift', 'kotlin', 'android', 'ios', 'mobile',
            'ml', 'machine learning', 'ai', 'data science', 'analytics',
            'frontend', 'backend', 'fullstack', 'full-stack', 'full stack',
        ]
        found_skills = []
        for tech in tech_keywords:
            pattern = rf'\b{re.escape(tech)}\b'
            if re.search(pattern, query_lower):
                found_skills.append(tech.title() if tech.lower() not in ['ml', 'ai', 'aws', 'gcp', 'ios', 'ci/cd'] else tech.upper())
        parsed.skills = found_skills

        # Extract locations (common Russian cities)
        locations = [
            ('москва', 'Москва'), ('moscow', 'Москва'),
            ('санкт-петербург', 'Санкт-Петербург'), ('спб', 'Санкт-Петербург'), ('питер', 'Санкт-Петербург'),
            ('новосибирск', 'Новосибирск'), ('екатеринбург', 'Екатеринбург'),
            ('казань', 'Казань'), ('нижний новгород', 'Нижний Новгород'),
            ('remote', 'Удалённо'), ('удалённо', 'Удалённо'), ('удаленно', 'Удалённо'),
        ]
        for pattern, city in locations:
            if pattern in query_lower:
                if city == 'Удалённо':
                    parsed.remote_ok = True
                else:
                    parsed.location = city
                break

        # Extract entity status keywords
        # Основы слов, а не формы: «на собеседовании», «в отказе», «новых».
        # Статусы — настоящие этапы HR (hr_stages); прежние interview/active у
        # кандидатов не встречаются, и фильтр по ним находил пустоту (24.10.2026).
        status_keywords = {
            'new': ['новы', 'новог', 'new'],
            'screening': ['тестов', 'выполняет тз', 'скрининг', 'screening'],
            'practice': ['собеседовани', 'интервью с hr', 'interview'],
            'tech_practice': ['интервью с заказчик'],
            'offer': ['оффер', 'offer'],
            'probation': ['практик', 'стажир'],
            'hired': ['принят', 'нанят', 'hired'],
            'rejected': ['отказ', 'rejected'],
            'reserve': ['резерв', 'reserve'],
        }
        for status, keywords in status_keywords.items():
            for kw in keywords:
                if kw in query_lower:
                    parsed.status = status
                    break

        # Keep remaining text for full-text search
        remaining_text = query
        # Remove extracted patterns
        patterns_to_remove = [
            r'(?:опыт|experience)\s*(?:от|from)?\s*\d+\s*(?:лет|год|years?)',
            r'\d+\+?\s*(?:лет|год|years?)',
            r'(?:зарплата|salary|зп)\s*(?:от|from|до|to)?\s*\d+',
            r'(?:от|до|from|to|up\s*to)\s*\d+\s*(?:руб|рублей|\$|usd|eur|€)?',
        ]
        for pattern in patterns_to_remove:
            remaining_text = re.sub(pattern, '', remaining_text, flags=re.IGNORECASE)

        remaining_text = remaining_text.strip()
        if remaining_text and len(remaining_text) > 2:
            parsed.text_query = remaining_text

        return parsed

    def _needs_ai_parsing(self, query: str, parsed: ParsedSearchQuery) -> bool:
        """Determine if AI parsing is needed for the query."""
        # Use AI for longer, complex queries
        if len(query) > 50:
            return True
        # Use AI if rule-based parsing found little
        if not parsed.skills and not parsed.experience_min_years and not parsed.salary_max:
            return True
        # Use AI for queries with complex natural language
        complex_patterns = [
            r'(?:который|которые|who|that|with|having)',
            r'(?:ищу|нужен|нужны|looking for|need)',
            r'(?:умеет|знает|владеет|knows|can|able)',
        ]
        for pattern in complex_patterns:
            if re.search(pattern, query.lower()):
                return True
        return False

    async def _ai_parse_query(self, query: str) -> ParsedSearchQuery:
        """Use AI to parse complex natural language query."""
        system_prompt = """You are a search query parser for an HR system.
Parse the user's natural language search query into structured filters.

Return a JSON object with these fields (only include fields that are explicitly mentioned or clearly implied):
- skills: array of technical skills/technologies mentioned
- experience_min_years: minimum years of experience (integer)
- experience_max_years: maximum years of experience (integer)
- experience_level: one of "junior", "middle", "senior", "lead"
- salary_min: minimum salary (integer, in original currency)
- salary_max: maximum salary (integer, in original currency)
- salary_currency: "RUB", "USD", or "EUR"
- location: city name
- remote_ok: true if remote work is mentioned positively
- position: job title/role
- tags: array of other relevant tags
- text_query: any remaining search terms that don't fit structured fields

Examples:
Query: "Python разработчики с опытом от 3 лет"
{"skills": ["Python"], "experience_min_years": 3, "position": "разработчик"}

Query: "Frontend React зарплата до 200000"
{"skills": ["React", "Frontend"], "salary_max": 200000, "salary_currency": "RUB"}

Query: "Москва Java senior"
{"skills": ["Java"], "experience_level": "senior", "location": "Москва"}

Respond ONLY with valid JSON, no explanations."""

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=500,
                system=system_prompt,
                messages=[{"role": "user", "content": f"Parse this search query: {query}"}]
            )

            result_text = response.content[0].text.strip()
            # Extract JSON from response
            if result_text.startswith('{'):
                result = json.loads(result_text)
            else:
                # Try to find JSON in the response
                json_match = re.search(r'\{[^{}]*\}', result_text)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    result = {}

            return ParsedSearchQuery(
                skills=result.get('skills', []),
                experience_min_years=result.get('experience_min_years'),
                experience_max_years=result.get('experience_max_years'),
                experience_level=result.get('experience_level'),
                salary_min=result.get('salary_min'),
                salary_max=result.get('salary_max'),
                salary_currency=result.get('salary_currency'),
                location=result.get('location'),
                remote_ok=result.get('remote_ok'),
                position=result.get('position'),
                tags=result.get('tags', []),
                text_query=result.get('text_query'),
            )
        except Exception as e:
            logger.error(f"AI query parsing error: {e}")
            return ParsedSearchQuery()

    def _merge_parsed_queries(
        self,
        rule_based: ParsedSearchQuery,
        ai_parsed: ParsedSearchQuery
    ) -> ParsedSearchQuery:
        """Merge rule-based and AI-parsed results, preferring AI for complex fields."""
        # Combine skills (unique)
        all_skills = list(set(rule_based.skills + ai_parsed.skills))

        return ParsedSearchQuery(
            skills=all_skills,
            experience_min_years=ai_parsed.experience_min_years or rule_based.experience_min_years,
            experience_max_years=ai_parsed.experience_max_years or rule_based.experience_max_years,
            experience_level=ai_parsed.experience_level or rule_based.experience_level,
            salary_min=ai_parsed.salary_min or rule_based.salary_min,
            salary_max=ai_parsed.salary_max or rule_based.salary_max,
            salary_currency=ai_parsed.salary_currency or rule_based.salary_currency,
            location=ai_parsed.location or rule_based.location,
            remote_ok=ai_parsed.remote_ok if ai_parsed.remote_ok is not None else rule_based.remote_ok,
            position=ai_parsed.position or rule_based.position,
            entity_type=ai_parsed.entity_type or rule_based.entity_type,
            status=ai_parsed.status or rule_based.status,
            tags=list(set(rule_based.tags + ai_parsed.tags)),
            text_query=ai_parsed.text_query or rule_based.text_query,
            original_query=rule_based.original_query or ai_parsed.original_query,
        )

    def build_search_filters(
        self,
        parsed: ParsedSearchQuery,
        org_id: Optional[int] = None
    ) -> List:
        """
        Build SQLAlchemy filter conditions from parsed query.

        Args:
            parsed: Structured search query
            org_id: Organization ID for filtering

        Returns:
            List of SQLAlchemy filter conditions
        """
        conditions = []

        # Теневая база: архивные кандидаты не участвуют в умном поиске
        conditions.append(Entity.is_archived.is_not(True))

        # Organization filter
        if org_id is not None:
            conditions.append(Entity.org_id == org_id)

        # Skills filter (search in extra_data JSON and tags)
        if parsed.skills:
            skill_conditions = []
            for skill in parsed.skills:
                skill_lower = skill.lower()
                # Search in extra_data (skills field)
                skill_conditions.append(
                    func.lower(cast(Entity.extra_data, String)).contains(skill_lower)
                )
                # Search in tags
                skill_conditions.append(
                    func.lower(cast(Entity.tags, String)).contains(skill_lower)
                )
                # Search in position
                skill_conditions.append(
                    func.lower(Entity.position).contains(skill_lower)
                )
                # Search in AI summary
                skill_conditions.append(
                    func.lower(Entity.ai_summary).contains(skill_lower)
                )
            conditions.append(or_(*skill_conditions))

        # Experience level filter
        if parsed.experience_level:
            level = parsed.experience_level.lower()
            level_conditions = [
                func.lower(Entity.position).contains(level),
                func.lower(cast(Entity.extra_data, String)).contains(level),
            ]
            conditions.append(or_(*level_conditions))

        # Salary filter
        if parsed.salary_min:
            conditions.append(
                or_(
                    Entity.expected_salary_max >= parsed.salary_min,
                    Entity.expected_salary_min >= parsed.salary_min,
                    Entity.expected_salary_max.is_(None)
                )
            )

        if parsed.salary_max:
            conditions.append(
                or_(
                    Entity.expected_salary_min <= parsed.salary_max,
                    Entity.expected_salary_max <= parsed.salary_max,
                    Entity.expected_salary_min.is_(None)
                )
            )

        if parsed.salary_currency:
            conditions.append(
                or_(
                    Entity.expected_salary_currency == parsed.salary_currency,
                    Entity.expected_salary_currency.is_(None)
                )
            )

        # Location filter
        if parsed.location:
            location_lower = parsed.location.lower()
            conditions.append(
                or_(
                    func.lower(cast(Entity.extra_data, String)).contains(location_lower),
                    func.lower(Entity.company).contains(location_lower),
                )
            )

        # Position filter
        if parsed.position:
            position_lower = parsed.position.lower()
            conditions.append(
                or_(
                    func.lower(Entity.position).contains(position_lower),
                    func.lower(Entity.name).contains(position_lower),
                )
            )

        # Status filter
        if parsed.status:
            try:
                status_enum = EntityStatus(parsed.status)
                conditions.append(Entity.status == status_enum)
            except ValueError:
                pass

        # Entity type filter (default to candidate for HR searches)
        if parsed.entity_type:
            try:
                type_enum = EntityType(parsed.entity_type)
                conditions.append(Entity.type == type_enum)
            except ValueError:
                pass

        # Tags filter
        if parsed.tags:
            for tag in parsed.tags:
                conditions.append(Entity.tags.contains([tag]))

        # Full-text search on remaining text
        if parsed.text_query:
            text_lower = parsed.text_query.lower()
            from .search_index import name_search_conditions, contact_search_conditions
            text_conditions = [
                *name_search_conditions(text_lower),  # умный поиск по имени (транслит+порядок+опечатки)
                *contact_search_conditions(text_lower),  # почта/телефон(норм.)/telegram + доп-списки
                func.lower(Entity.company).contains(text_lower),
                func.lower(Entity.position).contains(text_lower),
                func.lower(cast(Entity.extra_data, String)).contains(text_lower),
                func.lower(Entity.ai_summary).contains(text_lower),
            ]
            conditions.append(or_(*text_conditions))

        return conditions

    def rank_results(
        self,
        entities: List[Entity],
        parsed: ParsedSearchQuery
    ) -> List[Tuple[Entity, float]]:
        """
        Rank search results by relevance score.

        Scoring factors:
        - Skill match: +10 per matched skill
        - Position match: +15
        - Experience level match: +10
        - Salary match (within range): +5
        - Location match: +8
        - Recent activity: +5 for updated in last 30 days
        - Has AI summary: +3

        Args:
            entities: List of entities to rank
            parsed: Parsed search query

        Returns:
            List of (entity, score) tuples sorted by score descending
        """
        from datetime import datetime, timedelta

        scored_results = []

        for entity in entities:
            score = 0.0

            # Extra data for checking
            extra_data_str = json.dumps(entity.extra_data or {}).lower()
            tags_str = json.dumps(entity.tags or []).lower()
            ai_summary = (entity.ai_summary or "").lower()
            position = (entity.position or "").lower()

            # Skill match scoring
            if parsed.skills:
                for skill in parsed.skills:
                    skill_lower = skill.lower()
                    if skill_lower in extra_data_str:
                        score += 10
                    elif skill_lower in tags_str:
                        score += 8
                    elif skill_lower in position:
                        score += 6
                    elif skill_lower in ai_summary:
                        score += 4

            # Position match
            if parsed.position:
                if parsed.position.lower() in position:
                    score += 15
                elif parsed.position.lower() in (entity.name or "").lower():
                    score += 8

            # Experience level match
            if parsed.experience_level:
                level = parsed.experience_level.lower()
                if level in position or level in extra_data_str:
                    score += 10

            # Salary match
            if parsed.salary_min or parsed.salary_max:
                salary_min = entity.expected_salary_min
                salary_max = entity.expected_salary_max

                if salary_min or salary_max:
                    # Check if salary ranges overlap
                    query_min = parsed.salary_min or 0
                    query_max = parsed.salary_max or float('inf')
                    entity_min = salary_min or 0
                    entity_max = salary_max or float('inf')

                    if entity_min <= query_max and entity_max >= query_min:
                        score += 5

            # Location match
            if parsed.location:
                if parsed.location.lower() in extra_data_str:
                    score += 8

            # Recent activity bonus
            if entity.updated_at:
                days_since_update = (datetime.utcnow() - entity.updated_at).days
                if days_since_update <= 30:
                    score += 5
                elif days_since_update <= 90:
                    score += 2

            # Has AI summary bonus
            if entity.ai_summary:
                score += 3

            # Has complete profile bonus
            if entity.email and entity.phone:
                score += 2

            scored_results.append((entity, score))

        # Sort by score descending
        scored_results.sort(key=lambda x: x[1], reverse=True)

        return scored_results

    async def search(
        self,
        db: AsyncSession,
        query: str,
        org_id: Optional[int] = None,
        user_id: Optional[int] = None,
        entity_type: Optional[EntityType] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Perform smart search with AI parsing and ranking.

        Args:
            db: Database session
            query: Natural language search query
            org_id: Organization ID for filtering
            user_id: Current user ID for access control
            entity_type: Filter by entity type (default: candidate)
            limit: Maximum results
            offset: Results offset

        Returns:
            Dictionary with results, parsed_query, and metadata
        """
        # Parse the query
        parsed = await self.parse_search_query(query)

        # Apply default entity type if not specified
        if entity_type:
            parsed.entity_type = entity_type.value
        elif not parsed.entity_type:
            parsed.entity_type = "candidate"

        # Build filters
        conditions = self.build_search_filters(parsed, org_id)

        # Build and execute query
        stmt = select(Entity)
        if conditions:
            stmt = stmt.where(and_(*conditions))

        # Apply default ordering by updated_at
        stmt = stmt.order_by(Entity.updated_at.desc())

        # Get total count
        count_stmt = select(func.count(Entity.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        count_result = await db.execute(count_stmt)
        total_count = count_result.scalar() or 0

        # Fetch results with a larger limit for ranking
        ranking_limit = min(limit * 3, 200)  # Get more for ranking
        stmt = stmt.limit(ranking_limit)
        result = await db.execute(stmt)
        entities = list(result.scalars().all())

        # Rank results
        if entities:
            ranked = self.rank_results(entities, parsed)
            # Apply offset and limit after ranking
            ranked = ranked[offset:offset + limit]
            entities = [entity for entity, score in ranked]
            scores = {entity.id: score for entity, score in ranked}
        else:
            scores = {}

        # Build response
        return {
            "results": entities,
            "scores": scores,
            "total": total_count,
            "parsed_query": parsed.to_dict(),
            "offset": offset,
            "limit": limit,
        }


# Global service instance
smart_search_service = SmartSearchService()
