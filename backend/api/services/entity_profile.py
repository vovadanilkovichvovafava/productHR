"""
Entity Profile Service - generates and manages AI profiles for similarity matching.

Features:
- Generates structured profile from entity context (files, chats, calls)
- Stores profile in entity.extra_data['ai_profile']
- Finds similar candidates based on profile matching
- No embeddings needed - uses structured fields for fast comparison
"""
from typing import List, Optional, Dict, Any
from anthropic import AsyncAnthropic
import logging
import json
from datetime import datetime

from ..config import get_settings
from ..models.database import Entity, Chat, CallRecording, EntityFile
from .entity_ai import EntityAIService
from .skills_normalizer import skills_normalizer

logger = logging.getLogger("hr-analyzer.entity-profile")
settings = get_settings()

# =============================================================================
# SCORING CONSTANTS
# =============================================================================

# Level compatibility matrix (25 points max)
# Format: (level1, level2) -> score
LEVEL_COMPATIBILITY = {
    ("junior", "junior"): 25,
    ("junior", "middle"): 15,  # Growth possible
    ("junior", "senior"): 5,   # Too big gap
    ("junior", "lead"): 0,
    ("middle", "junior"): 15,
    ("middle", "middle"): 25,
    ("middle", "senior"): 15,  # Growth possible
    ("middle", "lead"): 10,
    ("senior", "junior"): 5,
    ("senior", "middle"): 15,
    ("senior", "senior"): 25,
    ("senior", "lead"): 15,    # Growth possible
    ("lead", "junior"): 0,
    ("lead", "middle"): 10,
    ("lead", "senior"): 15,
    ("lead", "lead"): 25,
}

# Specialization similarity matrix (1.0 = same, 0.0 = completely different)
SPECIALIZATION_SIMILARITY = {
    # Backend
    ("backend", "backend"): 1.0,
    ("backend", "fullstack"): 0.7,
    ("backend", "devops"): 0.5,
    ("backend", "frontend"): 0.25,
    ("backend", "mobile"): 0.3,
    ("backend", "data"): 0.4,
    ("backend", "ml"): 0.35,
    ("backend", "qa"): 0.2,
    # Frontend
    ("frontend", "frontend"): 1.0,
    ("frontend", "fullstack"): 0.7,
    ("frontend", "backend"): 0.25,
    ("frontend", "mobile"): 0.5,
    ("frontend", "devops"): 0.15,
    ("frontend", "data"): 0.15,
    ("frontend", "ml"): 0.1,
    ("frontend", "qa"): 0.3,
    # Fullstack
    ("fullstack", "fullstack"): 1.0,
    ("fullstack", "backend"): 0.7,
    ("fullstack", "frontend"): 0.7,
    ("fullstack", "mobile"): 0.5,
    ("fullstack", "devops"): 0.4,
    ("fullstack", "data"): 0.3,
    ("fullstack", "ml"): 0.25,
    ("fullstack", "qa"): 0.3,
    # DevOps
    ("devops", "devops"): 1.0,
    ("devops", "backend"): 0.5,
    ("devops", "fullstack"): 0.4,
    ("devops", "frontend"): 0.15,
    ("devops", "mobile"): 0.15,
    ("devops", "data"): 0.4,
    ("devops", "ml"): 0.35,
    ("devops", "qa"): 0.4,
    # Mobile
    ("mobile", "mobile"): 1.0,
    ("mobile", "frontend"): 0.5,
    ("mobile", "fullstack"): 0.5,
    ("mobile", "backend"): 0.3,
    ("mobile", "devops"): 0.15,
    ("mobile", "data"): 0.15,
    ("mobile", "ml"): 0.2,
    ("mobile", "qa"): 0.3,
    # Data
    ("data", "data"): 1.0,
    ("data", "ml"): 0.7,
    ("data", "backend"): 0.4,
    ("data", "devops"): 0.4,
    ("data", "fullstack"): 0.3,
    ("data", "frontend"): 0.15,
    ("data", "mobile"): 0.15,
    ("data", "qa"): 0.25,
    # ML/AI
    ("ml", "ml"): 1.0,
    ("ml", "data"): 0.7,
    ("ml", "backend"): 0.35,
    ("ml", "devops"): 0.35,
    ("ml", "fullstack"): 0.25,
    ("ml", "frontend"): 0.1,
    ("ml", "mobile"): 0.2,
    ("ml", "qa"): 0.2,
    # QA
    ("qa", "qa"): 1.0,
    ("qa", "devops"): 0.4,
    ("qa", "frontend"): 0.3,
    ("qa", "mobile"): 0.3,
    ("qa", "backend"): 0.2,
    ("qa", "fullstack"): 0.3,
    ("qa", "data"): 0.25,
    ("qa", "ml"): 0.2,
}

# Skills synonyms for normalization
SKILLS_SYNONYMS = {
    # Languages
    "javascript": ["js", "ecmascript", "es6", "es2015", "es2020"],
    "typescript": ["ts"],
    "python": ["py", "python3", "питон"],
    "golang": ["go", "golang"],
    "csharp": ["c#", "c sharp", "си шарп"],
    "cplusplus": ["c++", "cpp", "си плюс плюс"],
    "kotlin": ["kt"],
    "swift": ["свифт"],
    # Frontend
    "react": ["reactjs", "react.js", "реакт"],
    "vue": ["vuejs", "vue.js", "vue3", "вью"],
    "angular": ["angularjs", "angular.js", "ангуляр"],
    "nextjs": ["next.js", "next", "некст"],
    "nuxtjs": ["nuxt.js", "nuxt"],
    # Backend
    "nodejs": ["node.js", "node", "нода"],
    "fastapi": ["fast api", "fast-api"],
    "django": ["джанго"],
    "flask": ["фласк"],
    "spring": ["spring boot", "springboot"],
    "express": ["expressjs", "express.js"],
    # Databases
    "postgresql": ["postgres", "psql", "pg", "постгрес"],
    "mysql": ["mariadb", "мускул"],
    "mongodb": ["mongo", "монго"],
    "redis": ["редис"],
    "elasticsearch": ["elastic", "es", "эластик"],
    # DevOps
    "kubernetes": ["k8s", "кубер", "кубернетес"],
    "docker": ["докер", "контейнеры"],
    "aws": ["amazon web services", "амазон"],
    "gcp": ["google cloud", "google cloud platform"],
    "azure": ["microsoft azure"],
    "ci_cd": ["ci/cd", "cicd", "continuous integration", "jenkins", "gitlab ci", "github actions"],
    # Other
    "graphql": ["gql"],
    "rest_api": ["rest", "restful", "rest api"],
    "sql": ["structured query language"],
    "nosql": ["no-sql", "non-relational"],
    "agile": ["scrum", "kanban", "аджайл"],
    "git": ["гит", "version control"],
}

# Build reverse lookup for fast normalization
_SKILL_TO_CANONICAL = {}
for canonical, synonyms in SKILLS_SYNONYMS.items():
    _SKILL_TO_CANONICAL[canonical.lower()] = canonical
    for syn in synonyms:
        _SKILL_TO_CANONICAL[syn.lower()] = canonical

# Work format compatibility
WORK_FORMAT_COMPATIBILITY = {
    ("remote", "remote"): 5,
    ("remote", "hybrid"): 3,
    ("remote", "office"): 0,
    ("hybrid", "remote"): 3,
    ("hybrid", "hybrid"): 5,
    ("hybrid", "office"): 3,
    ("office", "remote"): 0,
    ("office", "hybrid"): 3,
    ("office", "office"): 5,
}

# Profile generation prompt
PROFILE_GENERATION_PROMPT = """На основе ВСЕХ предоставленных данных о кандидате создай структурированный профиль.

Верни JSON в ТОЧНО таком формате (без markdown, только JSON):
{
  "skills": ["навык1", "навык2", ...],
  "experience_years": число или null,
  "level": "junior" | "middle" | "senior" | "lead" | "unknown",
  "specialization": "основная специализация одним-двумя словами",
  "salary_min": число или null,
  "salary_max": число или null,
  "salary_currency": "RUB" | "USD" | "EUR",
  "location": "город или страна" или null,
  "work_format": "office" | "remote" | "hybrid" | "unknown",
  "languages": ["язык1", "язык2", ...],
  "education": "краткое описание" или null,
  "summary": "2-3 предложения о кандидате - кто он, что умеет, чем выделяется",
  "strengths": ["сильная сторона 1", "сильная сторона 2", ...],
  "weaknesses": ["слабая сторона 1", ...],
  "red_flags": ["red flag 1", ...] или [],
  "communication_style": "краткое описание стиля общения"
}

ПРАВИЛА:
1. Извлекай информацию ТОЛЬКО из предоставленных данных
2. Если информации нет - ставь null или пустой массив
3. Skills - реальные технические и софт навыки
4. Level определяй по опыту и сложности проектов
5. Salary бери из резюме или обсуждений в чатах/звонках
6. Summary должен быть информативным и полезным для быстрой оценки
7. Red flags - только реальные проблемы, не юмор/сарказм
8. Верни ТОЛЬКО JSON, без пояснений"""


class EntityProfileService:
    """Service for generating and managing entity AI profiles"""

    def __init__(self):
        self._client: Optional[AsyncAnthropic] = None
        self.model = settings.claude_model
        self._entity_ai = EntityAIService()

    @property
    def client(self) -> AsyncAnthropic:
        if self._client is None:
            if not settings.anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY не настроен")
            self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._client

    def _normalize_skill(self, skill: str) -> str:
        """Normalize skill to canonical form using synonyms dictionary."""
        skill_lower = skill.lower().strip()
        return _SKILL_TO_CANONICAL.get(skill_lower, skill_lower)

    def _normalize_skills(self, skills: List[str]) -> set:
        """Normalize a list of skills to canonical forms."""
        return {self._normalize_skill(s) for s in skills if s}

    def _normalize_specialization(self, spec: str) -> str:
        """Normalize specialization to canonical form."""
        if not spec:
            return "unknown"

        spec_lower = spec.lower().strip()

        # Backend variations
        if any(x in spec_lower for x in ["backend", "бэкенд", "бекенд", "серверн", "server-side"]):
            return "backend"

        # Frontend variations
        if any(x in spec_lower for x in ["frontend", "фронтенд", "фронт", "ui developer", "верстальщик"]):
            return "frontend"

        # Fullstack
        if any(x in spec_lower for x in ["fullstack", "full-stack", "full stack", "фулстек", "фуллстек"]):
            return "fullstack"

        # DevOps / SRE
        if any(x in spec_lower for x in ["devops", "sre", "infrastructure", "инфраструктур", "platform engineer"]):
            return "devops"

        # Mobile
        if any(x in spec_lower for x in ["mobile", "мобильн", "ios", "android", "flutter", "react native"]):
            return "mobile"

        # Data Engineering
        if any(x in spec_lower for x in ["data engineer", "etl", "dwh", "дата инженер", "big data"]):
            return "data"

        # ML/AI
        if any(x in spec_lower for x in ["ml", "machine learning", "ai", "data scien", "нейросет", "deep learning"]):
            return "ml"

        # QA
        if any(x in spec_lower for x in ["qa", "test", "тест", "quality", "автотест", "sdet"]):
            return "qa"

        return "unknown"

    def _normalize_work_format(self, fmt: str) -> str:
        """Normalize work format to canonical form."""
        if not fmt:
            return "unknown"

        fmt_lower = fmt.lower().strip()

        if any(x in fmt_lower for x in ["remote", "удалён", "удален", "дистанц"]):
            return "remote"
        if any(x in fmt_lower for x in ["hybrid", "гибрид", "смешан"]):
            return "hybrid"
        if any(x in fmt_lower for x in ["office", "офис", "on-site", "onsite"]):
            return "office"

        return "unknown"

    def _get_specialization_similarity(self, spec1: str, spec2: str) -> float:
        """Get similarity score between two specializations."""
        norm1 = self._normalize_specialization(spec1)
        norm2 = self._normalize_specialization(spec2)

        if norm1 == "unknown" or norm2 == "unknown":
            return 0.5  # Unknown gets neutral score

        # Check direct match
        if norm1 == norm2:
            return 1.0

        # Check in similarity matrix (both directions)
        score = SPECIALIZATION_SIMILARITY.get((norm1, norm2))
        if score is not None:
            return score

        score = SPECIALIZATION_SIMILARITY.get((norm2, norm1))
        if score is not None:
            return score

        return 0.1  # Default for unmatched pairs

    async def generate_profile(
        self,
        entity: Entity,
        chats: List[Chat],
        calls: List[CallRecording],
        files: Optional[List[EntityFile]] = None
    ) -> Dict[str, Any]:
        """
        Generate AI profile for entity based on all available context.

        Returns structured profile dict that can be stored in entity.extra_data['ai_profile']
        """
        # Build context using entity_ai service
        context = await self._entity_ai._build_entity_context(entity, chats, calls, files)

        # Add existing entity data to help AI
        entity_data = {
            "name": entity.name,
            "tags": entity.tags or [],
            "position": entity.position,
            "company": entity.company,
            "expected_salary_min": entity.expected_salary_min,
            "expected_salary_max": entity.expected_salary_max,
            "expected_salary_currency": entity.expected_salary_currency
        }

        system_prompt = f"""Ты — AI для создания структурированных профилей кандидатов.

Данные о кандидате:
{context}

Базовая информация из карточки:
{json.dumps(entity_data, ensure_ascii=False)}

Создай структурированный профиль на основе ВСЕХ доступных данных."""

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                system=system_prompt,
                messages=[{"role": "user", "content": PROFILE_GENERATION_PROMPT}]
            )

            response_text = response.content[0].text.strip()

            # Try to parse JSON from response
            # Handle cases where AI might wrap in ```json
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                json_lines = []
                in_json = False
                for line in lines:
                    if line.startswith("```") and not in_json:
                        in_json = True
                        continue
                    elif line.startswith("```") and in_json:
                        break
                    elif in_json:
                        json_lines.append(line)
                response_text = "\n".join(json_lines)

            profile = json.loads(response_text)

            # Normalize skills using LLM-backed normalizer
            if profile.get("skills"):
                try:
                    profile["skills"] = await skills_normalizer.normalize(profile["skills"])
                    logger.debug(f"Normalized {len(profile['skills'])} skills for entity {entity.id}")
                except Exception as e:
                    logger.warning(f"Skills normalization failed, using original: {e}")

            # Add metadata
            profile["generated_at"] = datetime.utcnow().isoformat()
            profile["context_sources"] = {
                "chats_count": len(chats),
                "calls_count": len(calls),
                "files_count": len(files) if files else 0
            }

            logger.info(f"Generated profile for entity {entity.id}: {profile.get('specialization', 'unknown')}")
            return profile

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse profile JSON: {e}")
            logger.error(f"Response was: {response_text[:500]}")
            # Return minimal profile
            return {
                "skills": entity.tags or [],
                "experience_years": None,
                "level": "unknown",
                "specialization": entity.position or "unknown",
                "salary_min": entity.expected_salary_min,
                "salary_max": entity.expected_salary_max,
                "salary_currency": entity.expected_salary_currency or "RUB",
                "summary": f"{entity.name} - {entity.position or 'специалист'}",
                "generated_at": datetime.utcnow().isoformat(),
                "error": "Failed to generate full profile"
            }
        except Exception as e:
            logger.error(f"Profile generation error: {e}")
            raise

    def calculate_similarity(
        self,
        profile1: Dict[str, Any],
        profile2: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculate similarity between two profiles.

        Weights (100 points total):
        - Skills match:           35 points (with synonym normalization)
        - Level + trajectory:     25 points (junior/middle/senior compatibility)
        - Specialization match:   20 points (with normalization)
        - Salary range overlap:   10 points
        - Work format + location: 10 points

        NOTE: Years of experience is NOT scored separately - it's already
        reflected in the level field to avoid double-counting.

        Returns:
            {
                "score": 0-100,
                "matches": ["skill match", "similar level", ...],
                "differences": ["salary mismatch", ...],
                "summary": "краткое сравнение"
            }
        """
        score = 0
        matches = []
        differences = []

        # =================================================================
        # 1. Skills match (35 points)
        # =================================================================
        raw_skills1 = profile1.get("skills") or []
        raw_skills2 = profile2.get("skills") or []

        # Normalize skills using synonyms
        skills1 = self._normalize_skills(raw_skills1)
        skills2 = self._normalize_skills(raw_skills2)

        if skills1 and skills2:
            common_skills = skills1 & skills2
            all_skills = skills1 | skills2

            # Jaccard similarity on normalized skills
            jaccard = len(common_skills) / len(all_skills) if all_skills else 0

            # Bonus for key skill matches (if main stack overlaps)
            # Key skills are typically the first 3 skills listed
            key_skills1 = self._normalize_skills(raw_skills1[:3])
            key_skills2 = self._normalize_skills(raw_skills2[:3])
            key_overlap = key_skills1 & key_skills2

            # Base score from Jaccard (up to 25 points)
            skill_score = int(jaccard * 25)

            # Bonus for key skill matches (up to 10 points)
            if key_skills1 and key_skills2:
                key_ratio = len(key_overlap) / min(len(key_skills1), len(key_skills2))
                skill_score += int(key_ratio * 10)

            skill_score = min(skill_score, 35)  # Cap at 35
            score += skill_score

            if common_skills:
                # Show original skill names for readability
                common_original = [s for s in raw_skills1 if self._normalize_skill(s) in common_skills][:5]
                if common_original:
                    matches.append(f"Общие навыки: {', '.join(common_original)}")

            unique1 = skills1 - skills2
            unique2 = skills2 - skills1
            if len(unique1) > 3 or len(unique2) > 3:
                differences.append(f"Много уникальных навыков у каждого")
        elif not skills1 and not skills2:
            # Both have no skills - neutral
            score += 17  # Half points
        else:
            differences.append("У одного из профилей не указаны навыки")

        # =================================================================
        # 2. Level + trajectory (25 points)
        # =================================================================
        level1 = (profile1.get("level") or "unknown").lower()
        level2 = (profile2.get("level") or "unknown").lower()

        if level1 != "unknown" and level2 != "unknown":
            level_score = LEVEL_COMPATIBILITY.get((level1, level2), 0)
            score += level_score

            if level_score >= 25:
                matches.append(f"Одинаковый уровень: {level1}")
            elif level_score >= 15:
                matches.append(f"Совместимые уровни: {level1} ↔ {level2}")
            elif level_score > 0:
                differences.append(f"Большой разрыв уровней: {level1} vs {level2}")
            else:
                differences.append(f"Несовместимые уровни: {level1} vs {level2}")
        else:
            # Unknown level - give neutral score
            score += 12

        # =================================================================
        # 3. Specialization match (20 points)
        # =================================================================
        spec1 = profile1.get("specialization") or ""
        spec2 = profile2.get("specialization") or ""

        if spec1 and spec2:
            spec_similarity = self._get_specialization_similarity(spec1, spec2)
            spec_score = int(spec_similarity * 20)
            score += spec_score

            norm_spec1 = self._normalize_specialization(spec1)
            norm_spec2 = self._normalize_specialization(spec2)

            if spec_similarity >= 1.0:
                matches.append(f"Одинаковая специализация: {norm_spec1}")
            elif spec_similarity >= 0.7:
                matches.append(f"Близкие специализации: {norm_spec1} ↔ {norm_spec2}")
            elif spec_similarity >= 0.4:
                differences.append(f"Частично пересекающиеся специализации")
            else:
                differences.append(f"Разные специализации: {norm_spec1} vs {norm_spec2}")
        else:
            score += 10  # Neutral if unknown

        # =================================================================
        # 4. Salary range overlap (10 points)
        # =================================================================
        sal1_min = profile1.get("salary_min") or profile1.get("expected_salary_min")
        sal1_max = profile1.get("salary_max") or profile1.get("expected_salary_max")
        sal2_min = profile2.get("salary_min") or profile2.get("expected_salary_min")
        sal2_max = profile2.get("salary_max") or profile2.get("expected_salary_max")

        if sal1_min and sal2_min:
            # Normalize to same range if max not provided
            min1, max1 = sal1_min, sal1_max or sal1_min * 1.3
            min2, max2 = sal2_min, sal2_max or sal2_min * 1.3

            # Calculate overlap
            overlap = min(max1, max2) - max(min1, min2)

            if overlap > 0:
                # Full overlap
                score += 10
                matches.append("Совпадающие зарплатные ожидания")
            else:
                # Calculate percentage difference
                diff_percent = abs(min1 - min2) / max(min1, min2) * 100 if max(min1, min2) > 0 else 100

                if diff_percent < 20:
                    score += 7
                    differences.append(f"Близкие зарплаты (разница ~{int(diff_percent)}%)")
                elif diff_percent < 40:
                    score += 3
                    differences.append(f"Умеренная разница в зарплате (~{int(diff_percent)}%)")
                else:
                    differences.append(f"Большая разница в зарплате (~{int(diff_percent)}%)")
        else:
            score += 5  # Neutral if salary not specified

        # =================================================================
        # 5. Work format + location (10 points)
        # =================================================================
        fmt1 = self._normalize_work_format(profile1.get("work_format") or "")
        fmt2 = self._normalize_work_format(profile2.get("work_format") or "")

        loc1 = (profile1.get("location") or "").lower().strip()
        loc2 = (profile2.get("location") or "").lower().strip()

        # Work format (up to 5 points)
        if fmt1 != "unknown" and fmt2 != "unknown":
            format_score = WORK_FORMAT_COMPATIBILITY.get((fmt1, fmt2), 0)
            score += format_score

            if format_score >= 5:
                matches.append(f"Одинаковый формат работы: {fmt1}")
            elif format_score >= 3:
                # Compatible but different - no message needed
                pass
            else:
                differences.append(f"Несовместимый формат: {fmt1} vs {fmt2}")
        else:
            score += 2  # Partial points if unknown

        # Location (up to 5 points)
        if loc1 and loc2:
            # Simple check - same city/country
            if loc1 == loc2:
                score += 5
                matches.append(f"Одинаковая локация: {loc1}")
            elif loc1 in loc2 or loc2 in loc1:
                # Partial match (e.g., "Moscow" in "Moscow, Russia")
                score += 3
            else:
                # Different locations - but might not matter for remote
                if fmt1 == "remote" or fmt2 == "remote":
                    score += 2  # Less important for remote
                else:
                    differences.append(f"Разные локации: {loc1} vs {loc2}")
        else:
            score += 2  # Partial points if unknown

        # =================================================================
        # Generate summary
        # =================================================================
        final_score = min(score, 100)  # Cap at 100

        if final_score >= 80:
            summary = "Отличное совпадение профилей"
        elif final_score >= 65:
            summary = "Хорошее совпадение профилей"
        elif final_score >= 50:
            summary = "Частичное совпадение"
        elif final_score >= 35:
            summary = "Есть общие черты"
        else:
            summary = "Профили не совпадают"

        return {
            "score": final_score,
            "matches": matches,
            "differences": differences,
            "summary": summary
        }

    def find_similar(
        self,
        target_profile: Dict[str, Any],
        candidates: List[tuple],  # List of (entity, profile) tuples
        min_score: int = 30,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find similar candidates based on profile matching.

        Args:
            target_profile: Profile to match against
            candidates: List of (entity, profile) tuples
            min_score: Minimum similarity score (0-100)
            limit: Max results to return

        Returns:
            List of {entity_id, entity_name, score, matches, differences, summary}
        """
        results = []

        for entity, profile in candidates:
            if not profile:
                continue

            similarity = self.calculate_similarity(target_profile, profile)

            if similarity["score"] >= min_score:
                results.append({
                    "entity_id": entity.id,
                    "entity_name": entity.name,
                    "entity_position": entity.position,
                    "entity_status": entity.status.value if hasattr(entity.status, 'value') else entity.status,
                    "profile_summary": profile.get("summary", ""),
                    "profile_level": profile.get("level", "unknown"),
                    "profile_specialization": profile.get("specialization", ""),
                    **similarity
                })

        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)

        return results[:limit]

    async def normalize_profile_skills(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize skills in a profile using LLM-backed normalizer.

        This can be called before calculate_similarity() for better matching.
        Returns a copy of the profile with normalized skills.
        """
        if not profile or not profile.get("skills"):
            return profile

        normalized_profile = profile.copy()
        try:
            normalized_profile["skills"] = await skills_normalizer.normalize(profile["skills"])
        except Exception as e:
            logger.warning(f"Profile skills normalization failed: {e}")

        return normalized_profile

    async def calculate_similarity_async(
        self,
        profile1: Dict[str, Any],
        profile2: Dict[str, Any],
        normalize_skills: bool = True
    ) -> Dict[str, Any]:
        """
        Async version of calculate_similarity with optional skill normalization.

        Args:
            profile1: First profile
            profile2: Second profile
            normalize_skills: Whether to normalize skills before comparison (default True)

        Returns:
            Similarity result dict with score, matches, differences, summary
        """
        if normalize_skills:
            profile1 = await self.normalize_profile_skills(profile1)
            profile2 = await self.normalize_profile_skills(profile2)

        return self.calculate_similarity(profile1, profile2)

    async def find_similar_async(
        self,
        target_profile: Dict[str, Any],
        candidates: List[tuple],
        min_score: int = 30,
        limit: int = 10,
        normalize_skills: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Async version of find_similar with skill normalization.

        Args:
            target_profile: Profile to match against
            candidates: List of (entity, profile) tuples
            min_score: Minimum similarity score (0-100)
            limit: Max results to return
            normalize_skills: Whether to normalize skills before comparison

        Returns:
            List of similar candidates
        """
        if normalize_skills:
            target_profile = await self.normalize_profile_skills(target_profile)

        results = []

        for entity, profile in candidates:
            if not profile:
                continue

            if normalize_skills:
                profile = await self.normalize_profile_skills(profile)

            similarity = self.calculate_similarity(target_profile, profile)

            if similarity["score"] >= min_score:
                results.append({
                    "entity_id": entity.id,
                    "entity_name": entity.name,
                    "entity_position": entity.position,
                    "entity_status": entity.status.value if hasattr(entity.status, 'value') else entity.status,
                    "profile_summary": profile.get("summary", ""),
                    "profile_level": profile.get("level", "unknown"),
                    "profile_specialization": profile.get("specialization", ""),
                    **similarity
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]


# Singleton instance
entity_profile_service = EntityProfileService()
