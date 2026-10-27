"""
Universal parser service for extracting structured data from:
- PDF resumes
- URLs (hh.ru, LinkedIn, SuperJob, Habr Career)
- Job vacancy pages
"""
import asyncio
import httpx
import re
import json
import logging
from typing import Optional, Dict, Any, Literal, Tuple
from urllib.parse import urlparse
from pydantic import BaseModel, field_validator
from anthropic import AsyncAnthropic
from .documents import document_parser
from .hh_api import parse_vacancy_via_api, HHVacancy
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class ParsedResume(BaseModel):
    """Extracted resume data (расширенная версия для URL парсинга)"""
    # Основные данные
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    # Контакты
    email: Optional[str] = None
    emails: list[str] = []
    phone: Optional[str] = None
    phones: list[str] = []
    telegram: Optional[str] = None
    whatsapp: Optional[str] = None

    # Персональные данные
    birth_date: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    citizenship: Optional[str] = None
    relocation: Optional[str] = None

    # Профессиональные данные
    position: Optional[str] = None  # Desired position
    specialization: Optional[str] = None
    company: Optional[str] = None   # Current/last company
    experience_years: Optional[float] = None  # Can be fractional (e.g., 1.5 years)

    # Навыки
    skills: list[str] = []
    skills_detailed: list[dict] = []

    # Образование и опыт
    education: list[dict] = []
    experience: list[dict] = []
    languages: list[dict] = []
    courses: list[dict] = []

    # Зарплата
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = "RUB"

    # Формат работы
    employment_type: Optional[str] = None
    schedule: Optional[str] = None

    # Локация
    location: Optional[str] = None
    metro: Optional[str] = None

    # Дополнительно
    summary: Optional[str] = None
    about: Optional[str] = None
    achievements: list[str] = []

    # Ссылки
    source_url: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    links: list[str] = []

    # Метаданные
    parse_confidence: float = 0.0
    parse_warnings: list[str] = []

    # Validators to handle None values from AI responses
    @field_validator('emails', 'phones', 'skills', 'skills_detailed', 'education',
                     'experience', 'languages', 'courses', 'achievements', 'links',
                     'parse_warnings', mode='before')
    @classmethod
    def ensure_list(cls, v):
        """Convert None to empty list"""
        if v is None:
            return []
        return v

    @field_validator('salary_currency', mode='before')
    @classmethod
    def ensure_currency(cls, v):
        """Если Claude вернул null (нет указанной валюты в резюме) —
        фолбек на RUB вместо ошибки валидации Pydantic."""
        if v is None or v == "":
            return "RUB"
        return v


class ParsedVacancy(BaseModel):
    """Extracted vacancy data"""
    title: str
    description: Optional[str] = None
    requirements: Optional[str] = None
    responsibilities: Optional[str] = None
    skills: list[str] = []  # Key skills/technologies required
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = "RUB"

    @field_validator('salary_currency', mode='before')
    @classmethod
    def ensure_currency(cls, v):
        """Тот же фолбек что и в ParsedResume — null → RUB."""
        if v is None or v == "":
            return "RUB"
        return v
    location: Optional[str] = None
    employment_type: Optional[str] = None  # full-time, part-time, remote
    experience_level: Optional[str] = None  # junior, middle, senior
    company_name: Optional[str] = None
    source_url: Optional[str] = None


# AI prompts for parsing
# Короткий разбор для окна «Загрузка из файла» (21.10.2026). Окно берёт из
# ответа ТОЛЬКО эти поля (ParserModal → createEntity), а сам файл резюме
# прикладывается к карточке, и его текст сервер достаёт без ИИ. Полный
# RESUME_PROMPT заставлял модель переписывать всё резюме в JSON (опыт с
# описаниями, образование, курсы…) — это и съедало деньги: ответ модели в 5 раз
# дороже входа, а почти всё из него выбрасывалось. Описание (summary) раньше не
# заказывалось вовсе — поле в окне всегда было пустым.
RESUME_CARD_PROMPT = """Извлеки из резюме кандидата только эти поля.
Верни ТОЛЬКО валидный JSON без markdown:

{
  "name": "Полное ФИО",
  "email": "основной email",
  "phone": "основной телефон в международном формате, если код страны указан",
  "telegram": "@username",
  "position": "желаемая должность",
  "company": "текущая или последняя компания",
  "location": "город",
  "experience_years": 5,
  "skills": ["до 30 ключевых навыков и технологий"],
  "salary_min": 200000,
  "salary_max": 300000,
  "salary_currency": "RUB",
  "summary": "2–3 предложения: кто кандидат, ключевой опыт и сильные стороны"
}

ПРАВИЛА:
- Нет данных — null (не пустая строка), для skills — [].
- Зарплата — числа без валюты; одна сумма — в salary_min.
- experience_years — общий стаж в годах (можно дробью).
- Только эти ключи, ничего больше.

Текст резюме:
"""


RESUME_PROMPT = """Ты - HR-эксперт. Извлеки ВСЮ информацию из резюме кандидата.
Верни ТОЛЬКО валидный JSON без markdown форматирования:

{
  "name": "Полное ФИО",
  "first_name": "Имя",
  "last_name": "Фамилия",
  "email": "email@example.com",
  "emails": ["все найденные email"],
  "phone": "+7...",
  "phones": ["все найденные телефоны"],
  "telegram": "@username или t.me/...",
  "whatsapp": "номер WhatsApp",
  "birth_date": "дата рождения",
  "age": 30,
  "gender": "male/female",
  "citizenship": "гражданство",
  "relocation": "yes/no/possible",
  "position": "Желаемая должность",
  "specialization": "Специализация",
  "company": "Текущая компания",
  "experience_years": 5,
  "skills": ["Python", "FastAPI", ...],
  "skills_detailed": [{"name": "Python", "level": "expert", "years": 5}],
  "education": [{"institution": "ВУЗ", "degree": "Степень", "year": "2020"}],
  "experience": [{"company": "Компания", "position": "Должность", "period": "2020-2023", "description": "..."}],
  "languages": [{"language": "English", "level": "B2"}],
  "courses": [{"name": "Курс", "organization": "Организация", "year": "2022"}],
  "salary_min": 200000,
  "salary_max": 300000,
  "salary_currency": "RUB",
  "employment_type": "full-time/part-time/project",
  "schedule": "remote/office/hybrid",
  "location": "Город",
  "metro": "Станция метро",
  "about": "О себе",
  "achievements": ["достижение1", "достижение2"],
  "linkedin": "ссылка на LinkedIn",
  "github": "ссылка на GitHub",
  "portfolio": "ссылка на портфолио",
  "links": ["все найденные ссылки"],
  "parse_confidence": 0.9,
  "parse_warnings": []
}

ПРАВИЛА:
- Если поле отсутствует - null (не пустую строку)
- Зарплата - числа без символов валюты
- skills - массив ВСЕХ навыков и технологий
- experience - от последнего места к первому
- parse_confidence: 0.9+ если всё найдено, 0.5-0.8 если частично, <0.5 если мало данных
- parse_warnings - список проблем ("Не найден email", "Нет опыта работы" и т.д.)

Текст для анализа:
"""

VACANCY_PROMPT = """Ты - опытный HR-эксперт. Твоя задача - ТОЧНО и ПОЛНОСТЬЮ разделить информацию о вакансии по полям.

ФОРМАТ ОТВЕТА (только JSON, без ```):
{
  "title": "Название должности",
  "description": "1-2 предложения о компании/позиции",
  "requirements": "Все требования к кандидату (включая soft skills, образование, опыт)",
  "responsibilities": "Все обязанности и задачи",
  "skills": ["массив", "технических", "навыков"],
  "salary_min": число_или_null,
  "salary_max": число_или_null,
  "salary_currency": "RUB",
  "location": "Город",
  "employment_type": "full-time",
  "experience_level": "middle",
  "company_name": "Компания"
}

=== КРИТИЧЕСКИ ВАЖНО: ПРАВИЛА РАСПРЕДЕЛЕНИЯ ===

1. **skills** (МАССИВ СТРОК) - ТОЛЬКО технологии и инструменты:
   ✓ Языки программирования: Python, Java, JavaScript, TypeScript, Go, C++, PHP, Ruby, Kotlin, Swift
   ✓ Фреймворки: React, Vue, Angular, Next.js, FastAPI, Django, Flask, Spring, Laravel, Rails
   ✓ Базы данных: PostgreSQL, MySQL, MongoDB, Redis, Elasticsearch, ClickHouse, Cassandra
   ✓ Инфраструктура: Docker, Kubernetes, AWS, GCP, Azure, Linux, Nginx, Terraform
   ✓ Инструменты: Git, CI/CD, Jenkins, GitLab, Jira, Figma, Postman
   ✓ Протоколы/паттерны: REST API, GraphQL, gRPC, Microservices, WebSocket, Kafka, RabbitMQ
   ✗ НИКОГДА не включай сюда: "опыт работы", "образование", "коммуникабельность"

2. **requirements** (ТЕКСТ с Markdown-форматированием) - ВСЕ требования к человеку:
   ✓ "Высшее техническое образование"
   ✓ "Опыт работы от 3 лет в разработке"
   ✓ "Английский язык B2+"
   ✓ "Умение работать в команде"
   ✓ "Опыт работы с высоконагруженными системами"
   ✓ "Понимание принципов SOLID, DRY, KISS"
   ✓ "Опыт написания unit-тестов"
   СОБИРАЙ ВСЁ из секций "Требования", "Мы ожидаем", "Что нужно", "Requirements"
   ФОРМАТИРОВАНИЕ: каждый пункт с новой строки, начинай с "• "

3. **responsibilities** (ТЕКСТ с Markdown-форматированием) - ВСЕ обязанности:
   ✓ "Разработка и поддержка backend-сервисов"
   ✓ "Проведение code review"
   ✓ "Участие в планировании спринтов"
   ✓ "Менторинг junior-разработчиков"
   ✓ "Оптимизация производительности"
   ✓ "Интеграция с внешними API"
   ✓ "Написание технической документации"
   СОБИРАЙ ВСЁ из секций "Обязанности", "Задачи", "Чем предстоит заниматься", "Responsibilities"
   ФОРМАТИРОВАНИЕ: каждый пункт с новой строки, начинай с "• "

4. **description** (ТЕКСТ, 1-3 предложения) - ТОЛЬКО краткое описание компании/вакансии:
   ✓ "Крупная IT-компания ищет senior backend разработчика для развития e-commerce платформы."
   ✓ "Стартап в сфере fintech приглашает разработчика для создания нового продукта."
   ✗ НЕ ДУБЛИРУЙ сюда requirements и responsibilities!

=== ПРИМЕРЫ ПРАВИЛЬНОГО РАЗБОРА ===

ПРИМЕР 1:
Вход: "IT-компания ищет Python-разработчика. Требования: опыт от 3 лет, знание FastAPI, PostgreSQL, английский B1+. Обязанности: разработка API, code review, участие в архитектурных решениях."

Выход:
- title: "Python-разработчик"
- description: "IT-компания ищет Python-разработчика"
- skills: ["Python", "FastAPI", "PostgreSQL"]
- requirements: "• Опыт работы от 3 лет\\n• Английский язык уровня B1+"
- responsibilities: "• Разработка API\\n• Проведение code review\\n• Участие в архитектурных решениях"

ПРИМЕР 2:
Вход: "Требуется Senior Frontend. Стек: React, TypeScript, Redux. Нужен опыт 5+ лет, знание тестирования. Задачи: разработка UI компонентов, оптимизация производительности."

Выход:
- title: "Senior Frontend разработчик"
- skills: ["React", "TypeScript", "Redux"]
- requirements: "• Опыт работы от 5 лет\\n• Знание тестирования"
- responsibilities: "• Разработка UI компонентов\\n• Оптимизация производительности"

=== ФИНАЛЬНЫЕ ПРАВИЛА ===
- Если видишь "Ключевые навыки", "Key skills", "Стек", "Технологии" → skills
- Если видишь "Требования", "Requirements", "Мы ожидаем" → requirements (НЕ skills!)
- Если видишь "Обязанности", "Задачи", "Responsibilities" → responsibilities
- Технологии из "Требований" → skills (отдельно), остальное → requirements
- Пустые поля = null, пустой skills = []
- НЕ СОКРАЩАЙ информацию - копируй ВСЁ из каждой секции!

=== ФОРМАТИРОВАНИЕ (ВАЖНО!) ===
- requirements и responsibilities ДОЛЖНЫ быть отформатированы с буллетами
- Каждый отдельный пункт начинается с "• " и отделяется переносом строки (\\n)
- Если в исходном тексте пункты слиты - раздели их на отдельные
- Группируй связанные пункты, если их много (например: **Опыт**, **Образование**)

Текст для анализа:
"""

VACANCY_SPLIT_PROMPT = """Раздели текст описания вакансии на структурированные поля.

ВХОДНЫЕ ДАННЫЕ УЖЕ СОДЕРЖАТ:
- title: есть
- skills: есть (массив ключевых навыков)
- salary, location, company: есть

ТВОЯ ЗАДАЧА - из description извлечь:
1. requirements - требования к кандидату
2. responsibilities - обязанности/задачи
3. short_description - краткое описание (1-2 предложения)

ФОРМАТ ОТВЕТА (только JSON):
{
  "requirements": "Отформатированные требования",
  "responsibilities": "Отформатированные обязанности",
  "short_description": "Краткое описание вакансии"
}

ПРАВИЛА СОДЕРЖАНИЯ:
- Ищи секции "Требования", "Обязанности", "Задачи", "Мы ожидаем" и т.д.
- requirements: опыт работы, образование, языки, личные качества
- responsibilities: что нужно делать, задачи, обязанности
- short_description: 1-2 предложения о компании/позиции
- Если секция не найдена - верни null
- НЕ включай технологии в requirements (они уже в skills)

ПРАВИЛА ФОРМАТИРОВАНИЯ (ВАЖНО!):
- Используй Markdown для красивого отображения
- Каждый пункт начинай с "• " (буллет) или "- "
- Группируй связанные пункты с заголовками (например: **Опыт**, **Образование**)
- Разделяй блоки пустой строкой для читаемости
- Если в оригинале нет структуры - создай её сам, разбив текст на логические пункты
- НЕ используй нумерацию (1, 2, 3) - только буллеты

Пример requirements:
**Опыт работы**
• 3+ года в разработке
• Опыт работы с крупными проектами

**Образование**
• Высшее техническое образование

**Личные качества**
• Ответственность
• Умение работать в команде

Текст описания:
"""


def _get_referer_for_url(url: str) -> str:
    """Generate appropriate Referer header based on URL domain."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/"


async def _fetch_with_httpx(url: str) -> str:
    """Try fetching URL with httpx (fast, lightweight).

    Returns HTML content or raises exception on failure.
    """
    import random

    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
    ]

    last_error = None
    for attempt in range(3):
        ua = user_agents[attempt % len(user_agents)]

        if attempt == 0:
            referer = _get_referer_for_url(url)
            fetch_site = 'same-origin'
        else:
            referer = 'https://www.google.com/'
            fetch_site = 'cross-site'

        headers = {
            'User-Agent': ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': referer,
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': fetch_site,
            'Sec-Fetch-User': '?1',
            'Sec-Ch-Ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Cache-Control': 'max-age=0',
            'Priority': 'u=0, i',
        }

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=30.0,
                http2=True,
            ) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                return response.text
        except httpx.HTTPStatusError as e:
            last_error = e
            status_code = e.response.status_code
            if status_code == 403 and attempt < 2:
                logger.warning(
                    f"Got 403 on attempt {attempt + 1} for {url}, retrying with different headers..."
                )
                await asyncio.sleep(1.5 * (attempt + 1) + random.uniform(0.5, 1.5))
                continue
            raise
        except Exception as e:
            last_error = e
            if attempt < 2:
                logger.warning(f"Fetch attempt {attempt + 1} failed for {url}: {e}")
                await asyncio.sleep(1.0 * (attempt + 1))
                continue
            raise

    raise last_error  # type: ignore[misc]


async def _fetch_with_playwright(url: str) -> str:
    """Fallback: fetch URL using headless Chromium via Playwright.

    This bypasses most anti-bot protections because it's a real browser
    with proper TLS fingerprint, JS execution, and cookie handling.
    """
    from .external_links import ensure_playwright_installed

    playwright_ready = await ensure_playwright_installed()
    if not playwright_ready:
        raise RuntimeError("Playwright browser not available")

    from playwright.async_api import async_playwright

    logger.info(f"Fetching URL with Playwright: {url}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--single-process',
            ]
        )
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='ru-RU',
            )
            page = await context.new_page()

            # Navigate and wait for content to load
            try:
                await page.goto(url, wait_until='networkidle', timeout=30000)
            except Exception:
                # Fallback to domcontentloaded if networkidle times out
                logger.warning(f"networkidle timeout for {url}, trying domcontentloaded")
                await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                await page.wait_for_timeout(3000)

            html_content = await page.content()
            logger.info(f"Playwright fetched {len(html_content)} chars from {url}")
            return html_content
        finally:
            await browser.close()


async def fetch_url_content(url: str) -> str:
    """Fetch and extract text content from URL.

    Strategy:
    1. Try httpx (fast, lightweight) with retry logic
    2. On 403/block, fall back to Playwright (real Chromium browser)
    3. Return user-friendly error if both fail
    """
    # Step 1: Try httpx first (fast path)
    try:
        return await _fetch_with_httpx(url)
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        if status_code == 404:
            raise ValueError(
                "Страница не найдена (404). Проверьте правильность ссылки."
            )
        if status_code != 403:
            source = detect_source(url)
            source_names = {
                'hh': 'HeadHunter', 'linkedin': 'LinkedIn',
                'superjob': 'SuperJob', 'habr': 'Хабр Карьера'
            }
            site_name = source_names.get(source, 'сайт')
            raise ValueError(
                f"Ошибка при загрузке страницы с {site_name} (код {status_code}). "
                f"Попробуйте позже или загрузите резюме файлом."
            )
        # 403 → fall through to Playwright
        logger.info(f"httpx got 403 for {url}, falling back to Playwright...")
    except Exception as httpx_err:
        logger.warning(f"httpx failed for {url}: {httpx_err}, trying Playwright...")

    # Step 2: Fallback to Playwright (real browser, bypasses most anti-bot)
    try:
        return await _fetch_with_playwright(url)
    except Exception as pw_err:
        logger.error(f"Playwright also failed for {url}: {pw_err}")

    # Step 3: Both methods failed
    source = detect_source(url)
    source_names = {
        'hh': 'HeadHunter', 'linkedin': 'LinkedIn',
        'superjob': 'SuperJob', 'habr': 'Хабр Карьера'
    }
    site_name = source_names.get(source, 'сайт')
    raise ValueError(
        f"Сайт {site_name} заблокировал доступ. "
        f"Попробуйте скопировать текст резюме и загрузить как файл (.txt/.pdf)."
    )


def detect_source(url: str) -> str:
    """Detect source type from URL"""
    url_lower = url.lower()
    if 'hh.ru' in url_lower:
        return 'hh'
    elif 'linkedin.com' in url_lower:
        return 'linkedin'
    elif 'superjob.ru' in url_lower:
        return 'superjob'
    elif 'career.habr.com' in url_lower or 'habr.com/career' in url_lower:
        return 'habr'
    return 'unknown'


def extract_text_from_html(html: str) -> str:
    """Extract readable text from HTML content"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, 'html.parser')

    # Remove script and style elements
    for element in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
        element.decompose()

    # Get text
    text = soup.get_text(separator='\n')

    # Clean up whitespace
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    text = '\n'.join(lines)

    # Truncate if too long
    max_length = 15000
    if len(text) > max_length:
        text = text[:max_length] + "\n...[text truncated]"

    return text


def _get_ai_client() -> AsyncAnthropic:
    """Get AI client for parsing"""
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY is not configured")
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


def _clean_json_response(response_text: str) -> str:
    """Clean AI response to extract valid JSON"""
    # Remove markdown code blocks if present
    if '```json' in response_text:
        match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
        if match:
            return match.group(1).strip()
    if '```' in response_text:
        match = re.search(r'```\s*(.*?)\s*```', response_text, re.DOTALL)
        if match:
            return match.group(1).strip()

    # Try to find JSON object in response
    # Find first { and last }
    start = response_text.find('{')
    end = response_text.rfind('}')
    if start != -1 and end != -1 and end > start:
        return response_text[start:end + 1]

    return response_text


def _repair_truncated_json(json_str: str) -> str:
    """Best-effort repair для усечённого JSON (Claude упёрся в max_tokens).
    Стратегия: сканируем строку, считаем открытые { и [, закрываем их;
    если оборвало посередине строки — закрываем кавычку. Не идеально,
    но лучше чем падать с invalid JSON."""
    if not json_str:
        return json_str
    s = json_str.rstrip()
    # Если последний значимый символ — запятая, отрезаем (trailing comma).
    while s.endswith(','):
        s = s[:-1].rstrip()

    # Сканируем посимвольно, отслеживая контекст строк и стеки скобок.
    in_string = False
    escape = False
    stack: list[str] = []
    for ch in s:
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            stack.append('}')
        elif ch == '[':
            stack.append(']')
        elif ch in ('}', ']'):
            if stack and stack[-1] == ch:
                stack.pop()

    # Если оборвало в строке — закрываем её.
    if in_string:
        s += '"'
    # Если последний символ перед закрытием стал запятой/двоеточием — обрезаем.
    s = re.sub(r'[,:]\s*$', '', s)
    # Закрываем оставшиеся { и [ в обратном порядке.
    for closer in reversed(stack):
        s += closer
    return s


async def parse_with_ai(
    content: str,
    parse_type: Literal["resume", "resume_card", "vacancy"],
    source: str = "unknown"
) -> Dict[str, Any]:
    """Use Claude AI to extract structured data from content.

    resume_card — короткий разбор только тех полей, что берёт окно добавления
    кандидата (RESUME_CARD_PROMPT); resume — полный (массовый импорт, ссылка)."""
    client = _get_ai_client()

    # Select prompt based on type
    if parse_type == "resume_card":
        prompt = RESUME_CARD_PROMPT + content
    elif parse_type == "resume":
        prompt = RESUME_PROMPT + content
    else:
        prompt = VACANCY_PROMPT + content

    # Add source context for better parsing
    source_context = ""
    if source != "unknown":
        source_hints = {
            "hh": "Это резюме/вакансия с сайта hh.ru (HeadHunter).",
            "linkedin": "Это профиль/вакансия с LinkedIn.",
            "superjob": "Это резюме/вакансия с сайта SuperJob.",
            "habr": "Это профиль/вакансия с Habr Career.",
        }
        source_context = source_hints.get(source, "")
        if source_context:
            prompt = source_context + "\n\n" + prompt

    response_text = ""
    try:
        response = await client.messages.create(
            model=settings.claude_model,
            # 8192 чтобы длинные резюме (опыт работы 15+ лет) не упирались
            # в лимит и JSON не обрывался на середине. Короткому разбору
            # хватает 2048: в нём нет опыта и образования.
            max_tokens=2048 if parse_type == "resume_card" else 8192,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = response.content[0].text

        # Clean and parse JSON response
        json_str = _clean_json_response(response_text)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e_strict:
            # Fallback: пробуем починить усечённый/невалидный JSON.
            # Чаще всего это max_tokens cutoff (хотя 8192 редко бьём)
            # или непроэкранированная кавычка внутри строки.
            repaired = _repair_truncated_json(json_str)
            try:
                result = json.loads(repaired)
                logger.warning(
                    f"AI JSON was malformed but repaired: {e_strict}. "
                    f"Repaired length={len(repaired)} (orig={len(json_str)})"
                )
                return result
            except json.JSONDecodeError:
                logger.error(f"Failed to parse AI response as JSON (strict + repair): {e_strict}")
                logger.debug(f"Raw response (first 1000 chars): {response_text[:1000]}")
                raise ValueError(
                    "AI вернул некорректный JSON. Попробуйте ещё раз — обычно помогает."
                )
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"AI parsing failed: {e}")
        raise


async def split_vacancy_description(description: str) -> Dict[str, Optional[str]]:
    """Use AI to split vacancy description into requirements and responsibilities.

    Args:
        description: Full vacancy description text

    Returns:
        Dict with 'requirements', 'responsibilities', 'short_description'
    """
    if not description or len(description.strip()) < 50:
        return {
            "requirements": None,
            "responsibilities": None,
            "short_description": description
        }

    client = _get_ai_client()
    prompt = VACANCY_SPLIT_PROMPT + description

    try:
        response = await client.messages.create(
            model=settings.claude_model,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = response.content[0].text
        json_str = _clean_json_response(response_text)
        result = json.loads(json_str)

        return {
            "requirements": result.get("requirements"),
            "responsibilities": result.get("responsibilities"),
            "short_description": result.get("short_description") or description[:200]
        }

    except Exception as e:
        logger.warning(f"Failed to split vacancy description: {e}")
        return {
            "requirements": None,
            "responsibilities": None,
            "short_description": description[:200] if description else None
        }


async def parse_resume_from_file(file_content: bytes, filename: str, card: bool = False) -> ParsedResume:
    """Parse resume from file using AI.

    card=True — короткий разбор для окна «Загрузка из файла» (только поля
    карточки, RESUME_CARD_PROMPT); без него — полный (массовый импорт)."""
    # Use existing DocumentParser to extract text
    parse_result = await document_parser.parse(file_content, filename)

    if parse_result.status == "failed":
        raise ValueError(f"Failed to parse document: {parse_result.error}")

    if not parse_result.content or not parse_result.content.strip():
        # Сюда доходим, только если и распознавание картинок внутри файла
        # ничего не дало (см. DocumentParser: нет текста → OCR вложенных
        # картинок). Сообщение читает рекрутёр, поэтому по-русски и с советом.
        raise ValueError(
            "В файле не нашлось текста. Если резюме вставлено картинкой, "
            "сохраните его как JPG или PNG и загрузите снова"
        )

    # Use AI to extract structured data
    data = await parse_with_ai(parse_result.content, "resume_card" if card else "resume")
    # В карточку — не больше 30 навыков (короткий разбор их так и просит).
    if isinstance(data.get("skills"), list):
        data["skills"] = data["skills"][:30]

    return ParsedResume(**data)


async def parse_resume_from_url(url: str) -> ParsedResume:
    """Parse resume from URL (hh.ru, linkedin, etc)"""
    # Detect source
    source = detect_source(url)

    # Fetch page content
    html_content = await fetch_url_content(url)

    # Extract text from HTML
    text_content = extract_text_from_html(html_content)

    if not text_content or not text_content.strip():
        raise ValueError("Could not extract text from URL")

    # Use AI to extract structured data
    data = await parse_with_ai(text_content, "resume", source)
    data["source_url"] = url

    return ParsedResume(**data)


async def parse_vacancy_from_url(url: str) -> Tuple[ParsedVacancy, str]:
    """Parse vacancy from URL - uses API when available, falls back to AI.

    Args:
        url: The vacancy URL to parse

    Returns:
        Tuple of (ParsedVacancy, method) where method is "api+ai" or "ai"
    """
    # Detect source
    source = detect_source(url)

    # Try hh.ru API first (free and instant!)
    if source == "hh":
        logger.info(f"Trying hh.ru API for: {url}")
        api_result = await parse_vacancy_via_api(url)
        if api_result:
            logger.info(f"Successfully parsed via hh.ru API: {api_result.title}")

            # Use AI to split description into requirements/responsibilities
            requirements = None
            responsibilities = None
            short_description = api_result.description

            if api_result.description and len(api_result.description) > 100:
                logger.info("Splitting description with AI...")
                split_result = await split_vacancy_description(api_result.description)
                requirements = split_result.get("requirements")
                responsibilities = split_result.get("responsibilities")
                short_description = split_result.get("short_description") or api_result.description[:300]

            vacancy = ParsedVacancy(
                title=api_result.title,
                description=short_description,
                requirements=requirements,
                responsibilities=responsibilities,
                skills=api_result.skills,
                salary_min=api_result.salary_min,
                salary_max=api_result.salary_max,
                salary_currency=api_result.salary_currency,
                location=api_result.location,
                employment_type=api_result.employment_type,
                experience_level=api_result.experience_level,
                company_name=api_result.company_name,
                source_url=url,
            )
            return vacancy, "api+ai"
        logger.warning("hh.ru API failed, falling back to AI parsing")

    # Fallback to AI parsing
    # Fetch page content
    html_content = await fetch_url_content(url)

    # Extract text from HTML
    text_content = extract_text_from_html(html_content)

    if not text_content or not text_content.strip():
        raise ValueError("Could not extract text from URL")

    # Use AI to extract structured data
    data = await parse_with_ai(text_content, "vacancy", source)
    data["source_url"] = url

    # Ensure title is present (required field)
    if not data.get("title"):
        data["title"] = "Untitled Vacancy"

    return ParsedVacancy(**data), "ai"


async def parse_vacancy_from_file(file_content: bytes, filename: str) -> ParsedVacancy:
    """Parse vacancy from uploaded file using AI.

    Args:
        file_content: Raw bytes of the file
        filename: Original filename (used for format detection)

    Returns:
        ParsedVacancy with extracted data
    """
    # Use existing DocumentParser to extract text
    parse_result = await document_parser.parse(file_content, filename)

    if parse_result.status == "failed":
        raise ValueError(f"Failed to parse document: {parse_result.error}")

    if not parse_result.content or not parse_result.content.strip():
        raise ValueError(
            "В файле не нашлось текста. Если он вставлен картинкой, "
            "сохраните его как JPG или PNG и загрузите снова"
        )

    # Use AI to extract structured vacancy data
    data = await parse_with_ai(parse_result.content, "vacancy")

    # Ensure title is present (required field)
    if not data.get("title"):
        data["title"] = "Untitled Vacancy"

    return ParsedVacancy(**data)


# Alias for backward compatibility
parse_resume_from_pdf = parse_resume_from_file
