"""
Skills Normalizer Service - normalizes skill names through LLM.

Features:
- In-memory cache for fast lookup
- Static dictionary of common aliases (no LLM call needed)
- Batch LLM normalization for unknown skills
- Redis-backed persistent cache
"""
from typing import List, Dict, Optional
from anthropic import AsyncAnthropic
import logging
import json

from ..config import get_settings
from .redis_cache import redis_cache

logger = logging.getLogger("hr-analyzer.skills-normalizer")
settings = get_settings()

# TTL for cached skill mappings (7 days)
CACHE_TTL_SECONDS = 60 * 60 * 24 * 7

# Prompt for LLM normalization
NORMALIZATION_PROMPT = """Нормализуй названия технических навыков в стандартный формат.

Входные навыки: {skills}

Правила:
- Используй официальные названия технологий (JavaScript, не JS)
- Объединяй синонимы (React.js, ReactJS → React)
- Исправляй опечатки (Pytohn → Python)
- Транслитерируй с русского (питон → Python, джава → Java)
- Soft skills пиши на английском с заглавной (Communication, Leadership)
- Frameworks и библиотеки — официальные названия (Vue.js → Vue, TensorFlow)

Верни ТОЛЬКО JSON без markdown: {{"input_skill": "normalized_skill", ...}}"""


class SkillsNormalizer:
    """
    Service for normalizing skill names using static aliases and LLM fallback.

    Usage:
        normalizer = SkillsNormalizer()
        normalized = await normalizer.normalize(["JS", "React.js", "питон"])
        # Returns: ["JavaScript", "React", "Python"]
    """

    # In-memory cache for fast lookup: "js" -> "JavaScript"
    _cache: Dict[str, str] = {}

    # Static dictionary of common aliases (no LLM needed)
    KNOWN_ALIASES: Dict[str, str] = {
        # JavaScript ecosystem
        "js": "JavaScript",
        "javascript": "JavaScript",
        "джаваскрипт": "JavaScript",
        "джс": "JavaScript",
        "ts": "TypeScript",
        "typescript": "TypeScript",
        "тайпскрипт": "TypeScript",
        "react.js": "React",
        "reactjs": "React",
        "react js": "React",
        "реакт": "React",
        "vue.js": "Vue",
        "vuejs": "Vue",
        "vue js": "Vue",
        "вью": "Vue",
        "angular.js": "Angular",
        "angularjs": "Angular",
        "ангуляр": "Angular",
        "node.js": "Node.js",
        "nodejs": "Node.js",
        "node js": "Node.js",
        "нода": "Node.js",
        "next.js": "Next.js",
        "nextjs": "Next.js",
        "nuxt.js": "Nuxt.js",
        "nuxtjs": "Nuxt.js",
        "express.js": "Express",
        "expressjs": "Express",
        "nest.js": "NestJS",
        "nestjs": "NestJS",

        # Python ecosystem
        "py": "Python",
        "python": "Python",
        "python3": "Python",
        "питон": "Python",
        "пайтон": "Python",
        "django": "Django",
        "джанго": "Django",
        "flask": "Flask",
        "фласк": "Flask",
        "fastapi": "FastAPI",
        "fast api": "FastAPI",
        "фастапи": "FastAPI",
        "pandas": "Pandas",
        "пандас": "Pandas",
        "numpy": "NumPy",
        "нампай": "NumPy",
        "pytorch": "PyTorch",
        "пайторч": "PyTorch",
        "tensorflow": "TensorFlow",
        "тензорфлоу": "TensorFlow",
        "scikit-learn": "Scikit-learn",
        "sklearn": "Scikit-learn",
        "keras": "Keras",
        "кирас": "Keras",

        # Java ecosystem
        "java": "Java",
        "джава": "Java",
        "жава": "Java",
        "spring": "Spring",
        "спринг": "Spring",
        "spring boot": "Spring Boot",
        "springboot": "Spring Boot",
        "hibernate": "Hibernate",
        "хибернейт": "Hibernate",
        "kotlin": "Kotlin",
        "котлин": "Kotlin",

        # C-family
        "c++": "C++",
        "cpp": "C++",
        "плюсы": "C++",
        "c#": "C#",
        "csharp": "C#",
        "c sharp": "C#",
        "шарп": "C#",
        "c": "C",
        "си": "C",
        ".net": ".NET",
        "dotnet": ".NET",
        "дотнет": ".NET",

        # Go
        "go": "Go",
        "golang": "Go",
        "го": "Go",
        "голанг": "Go",

        # Rust
        "rust": "Rust",
        "раст": "Rust",

        # Ruby
        "ruby": "Ruby",
        "руби": "Ruby",
        "rails": "Ruby on Rails",
        "ruby on rails": "Ruby on Rails",
        "ror": "Ruby on Rails",

        # PHP
        "php": "PHP",
        "пхп": "PHP",
        "пых-пых": "PHP",
        "laravel": "Laravel",
        "ларавел": "Laravel",
        "symfony": "Symfony",
        "симфони": "Symfony",

        # Mobile
        "swift": "Swift",
        "свифт": "Swift",
        "objective-c": "Objective-C",
        "objc": "Objective-C",
        "flutter": "Flutter",
        "флаттер": "Flutter",
        "dart": "Dart",
        "дарт": "Dart",
        "react native": "React Native",
        "reactnative": "React Native",
        "rn": "React Native",

        # Databases
        "sql": "SQL",
        "скуэль": "SQL",
        "mysql": "MySQL",
        "мускул": "MySQL",
        "postgresql": "PostgreSQL",
        "postgres": "PostgreSQL",
        "постгрес": "PostgreSQL",
        "пг": "PostgreSQL",
        "mongodb": "MongoDB",
        "монга": "MongoDB",
        "mongo": "MongoDB",
        "redis": "Redis",
        "редис": "Redis",
        "elasticsearch": "Elasticsearch",
        "elastic": "Elasticsearch",
        "эластик": "Elasticsearch",
        "clickhouse": "ClickHouse",
        "кликхаус": "ClickHouse",
        "cassandra": "Cassandra",
        "кассандра": "Cassandra",

        # DevOps
        "docker": "Docker",
        "докер": "Docker",
        "kubernetes": "Kubernetes",
        "k8s": "Kubernetes",
        "кубер": "Kubernetes",
        "кубернетес": "Kubernetes",
        "terraform": "Terraform",
        "терраформ": "Terraform",
        "ansible": "Ansible",
        "ансибл": "Ansible",
        "jenkins": "Jenkins",
        "дженкинс": "Jenkins",
        "gitlab ci": "GitLab CI",
        "gitlab-ci": "GitLab CI",
        "github actions": "GitHub Actions",
        "aws": "AWS",
        "амазон": "AWS",
        "amazon web services": "AWS",
        "gcp": "Google Cloud",
        "google cloud": "Google Cloud",
        "azure": "Azure",
        "азур": "Azure",

        # AI/ML
        "ml": "Machine Learning",
        "machine learning": "Machine Learning",
        "машинное обучение": "Machine Learning",
        "мл": "Machine Learning",
        "ai": "Artificial Intelligence",
        "artificial intelligence": "Artificial Intelligence",
        "ии": "Artificial Intelligence",
        "искусственный интеллект": "Artificial Intelligence",
        "nlp": "NLP",
        "natural language processing": "NLP",
        "обработка естественного языка": "NLP",
        "cv": "Computer Vision",
        "computer vision": "Computer Vision",
        "компьютерное зрение": "Computer Vision",
        "deep learning": "Deep Learning",
        "dl": "Deep Learning",
        "глубокое обучение": "Deep Learning",
        "llm": "LLM",
        "large language models": "LLM",

        # Frontend
        "html": "HTML",
        "html5": "HTML",
        "css": "CSS",
        "css3": "CSS",
        "sass": "Sass",
        "scss": "Sass",
        "less": "Less",
        "tailwind": "Tailwind CSS",
        "tailwindcss": "Tailwind CSS",
        "тейлвинд": "Tailwind CSS",
        "bootstrap": "Bootstrap",
        "бутстрап": "Bootstrap",
        "webpack": "Webpack",
        "вебпак": "Webpack",
        "vite": "Vite",
        "esbuild": "esbuild",

        # Testing
        "jest": "Jest",
        "pytest": "pytest",
        "unittest": "unittest",
        "mocha": "Mocha",
        "cypress": "Cypress",
        "selenium": "Selenium",
        "селениум": "Selenium",
        "playwright": "Playwright",

        # Version Control
        "git": "Git",
        "гит": "Git",
        "github": "GitHub",
        "гитхаб": "GitHub",
        "gitlab": "GitLab",
        "гитлаб": "GitLab",
        "bitbucket": "Bitbucket",

        # Other
        "graphql": "GraphQL",
        "grpc": "gRPC",
        "rest": "REST API",
        "rest api": "REST API",
        "restful": "REST API",
        "websocket": "WebSocket",
        "вебсокет": "WebSocket",
        "rabbitmq": "RabbitMQ",
        "kafka": "Apache Kafka",
        "апач кафка": "Apache Kafka",
        "linux": "Linux",
        "линукс": "Linux",
        "unix": "Unix",
        "bash": "Bash",
        "баш": "Bash",
        "shell": "Shell",
        "powershell": "PowerShell",
        "regex": "Regular Expressions",
        "regexp": "Regular Expressions",
        "регулярки": "Regular Expressions",
        "agile": "Agile",
        "аджайл": "Agile",
        "scrum": "Scrum",
        "скрам": "Scrum",
        "kanban": "Kanban",
        "канбан": "Kanban",
        "jira": "Jira",
        "джира": "Jira",
        "confluence": "Confluence",
        "конфлюенс": "Confluence",
        "figma": "Figma",
        "фигма": "Figma",

        # Soft skills (Russian -> English)
        "коммуникация": "Communication",
        "communication": "Communication",
        "лидерство": "Leadership",
        "leadership": "Leadership",
        "командная работа": "Teamwork",
        "работа в команде": "Teamwork",
        "teamwork": "Teamwork",
        "аналитическое мышление": "Analytical Thinking",
        "analytical thinking": "Analytical Thinking",
        "тайм-менеджмент": "Time Management",
        "time management": "Time Management",
        "управление временем": "Time Management",
        "решение проблем": "Problem Solving",
        "problem solving": "Problem Solving",
        "критическое мышление": "Critical Thinking",
        "critical thinking": "Critical Thinking",
        "презентация": "Presentation Skills",
        "presentation": "Presentation Skills",
        "переговоры": "Negotiation",
        "negotiation": "Negotiation",
        "менторство": "Mentoring",
        "mentoring": "Mentoring",
    }

    def __init__(self):
        self._client: Optional[AsyncAnthropic] = None
        self.model = settings.claude_model

    @property
    def client(self) -> AsyncAnthropic:
        """Lazy initialization of Anthropic client."""
        if self._client is None:
            if not settings.anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY не настроен")
            self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._client

    async def normalize(self, skills: List[str]) -> List[str]:
        """
        Normalize a list of skills, using cache first, then LLM for unknown.

        Args:
            skills: List of skill names to normalize

        Returns:
            List of normalized skill names (same order as input)
        """
        if not skills:
            return []

        results: Dict[str, str] = {}
        unknown_skills: List[str] = []

        for skill in skills:
            normalized = await self.normalize_single(skill)
            if normalized:
                results[skill] = normalized
            else:
                unknown_skills.append(skill)

        # Batch normalize unknown skills through LLM
        if unknown_skills:
            llm_results = await self._llm_normalize(unknown_skills)
            for original, normalized in llm_results.items():
                results[original] = normalized
                # Cache the result
                await self._cache_skill(original.lower(), normalized)

        # Return in original order, deduplicated but preserving first occurrence
        seen = set()
        normalized_list = []
        for skill in skills:
            normalized = results.get(skill, skill)  # Fallback to original if not found
            if normalized.lower() not in seen:
                seen.add(normalized.lower())
                normalized_list.append(normalized)

        return normalized_list

    async def normalize_single(self, skill: str) -> Optional[str]:
        """
        Normalize a single skill using cache and static aliases.

        Returns:
            Normalized skill name or None if not found in cache/aliases
        """
        if not skill or not skill.strip():
            return None

        skill_lower = skill.strip().lower()

        # 1. Check static aliases first (fastest)
        if skill_lower in self.KNOWN_ALIASES:
            return self.KNOWN_ALIASES[skill_lower]

        # 2. Check in-memory cache
        if skill_lower in self._cache:
            return self._cache[skill_lower]

        # 3. Check Redis cache
        cache_key = f"skill:normalize:{skill_lower}"
        cached = await redis_cache.get(cache_key)
        if cached:
            self._cache[skill_lower] = cached  # Populate in-memory cache
            return cached

        return None

    async def _llm_normalize(self, unknown_skills: List[str]) -> Dict[str, str]:
        """
        Batch normalize unknown skills through Claude.

        Args:
            unknown_skills: List of skills not found in cache/aliases

        Returns:
            Dict mapping original skill to normalized name
        """
        if not unknown_skills:
            return {}

        # Deduplicate for LLM call
        unique_skills = list(set(s.strip() for s in unknown_skills if s.strip()))
        if not unique_skills:
            return {}

        prompt = NORMALIZATION_PROMPT.format(skills=json.dumps(unique_skills, ensure_ascii=False))

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.content[0].text.strip()

            # Parse JSON response, handle potential markdown wrapping
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

            result = json.loads(response_text)

            # Validate result is a dict
            if not isinstance(result, dict):
                logger.error(f"LLM returned non-dict: {type(result)}")
                return {s: s for s in unknown_skills}  # Fallback to original

            logger.info(f"LLM normalized {len(result)} skills: {list(result.values())[:5]}...")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {e}")
            logger.error(f"Response was: {response_text[:200]}")
            return {s: s for s in unknown_skills}  # Fallback to original
        except Exception as e:
            logger.error(f"LLM normalization error: {e}")
            return {s: s for s in unknown_skills}  # Fallback to original

    async def _cache_skill(self, skill_lower: str, normalized: str) -> None:
        """Cache skill mapping in both in-memory and Redis."""
        self._cache[skill_lower] = normalized
        cache_key = f"skill:normalize:{skill_lower}"
        await redis_cache.set(cache_key, normalized, ttl_seconds=CACHE_TTL_SECONDS)

    def clear_cache(self) -> None:
        """Clear in-memory cache (Redis cache remains)."""
        self._cache.clear()
        logger.info("Skills normalizer in-memory cache cleared")


# Singleton instance
skills_normalizer = SkillsNormalizer()
