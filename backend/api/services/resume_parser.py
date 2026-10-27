"""
Сервис парсинга резюме с использованием AI.

Извлекает структурированные данные из резюме в форматах PDF, DOC, DOCX.
Использует Anthropic Claude API для интеллектуального парсинга.
"""

import logging
import json
import re
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from anthropic import AsyncAnthropic

from ..config import get_settings
from .documents import document_parser

logger = logging.getLogger("hr-analyzer.resume-parser")
settings = get_settings()


# ============================================================================
# Утилиты для валидации и нормализации контактов
# ============================================================================

def normalize_phone(phone: str) -> str:
    """
    Нормализация телефонного номера.
    Приводит к формату +7XXXXXXXXXX для российских номеров.
    """
    if not phone:
        return phone

    # Номер с однозначной страной — сразу в международный формат (+375…, +998…).
    # Старое правило ниже дописывало +7 к любому 11-значному номеру на 8 и
    # превращало белорусское «8 029 …» в несуществующее «+7 029 …».
    from .phone_keys import to_e164_if_certain
    certain = to_e164_if_certain(phone)
    if certain:
        return certain

    # Удаляем всё кроме цифр и +
    cleaned = re.sub(r'[^\d+]', '', phone)

    # Если начинается с 8 и имеет 11 цифр - это российский номер
    if cleaned.startswith('8') and len(cleaned) == 11:
        cleaned = '+7' + cleaned[1:]

    # Если начинается с 7 без + и имеет 11 цифр
    elif cleaned.startswith('7') and len(cleaned) == 11:
        cleaned = '+' + cleaned

    # Если только 10 цифр (без кода страны)
    elif len(cleaned) == 10 and cleaned[0] == '9':
        cleaned = '+7' + cleaned

    return cleaned


def validate_phone(phone: str) -> bool:
    """Проверка валидности телефонного номера."""
    if not phone:
        return False

    cleaned = re.sub(r'[^\d]', '', phone)

    # Российские номера: 10-11 цифр
    if len(cleaned) >= 10 and len(cleaned) <= 15:
        return True

    return False


def normalize_email(email: str) -> str:
    """Нормализация email адреса."""
    if not email:
        return email

    return email.lower().strip()


def validate_email(email: str) -> bool:
    """Проверка валидности email адреса."""
    if not email:
        return False

    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def normalize_telegram(telegram: str) -> str:
    """
    Нормализация Telegram username.
    Возвращает username без @ и ссылки.
    """
    if not telegram:
        return telegram

    tg = telegram.strip()

    # Убираем различные форматы ссылок
    prefixes = [
        'https://t.me/',
        'http://t.me/',
        't.me/',
        'https://telegram.me/',
        'http://telegram.me/',
        'telegram.me/',
        '@'
    ]

    for prefix in prefixes:
        if tg.lower().startswith(prefix.lower()):
            tg = tg[len(prefix):]
            break

    # Убираем параметры из ссылки
    if '?' in tg:
        tg = tg.split('?')[0]

    return tg.strip()


def extract_links_by_type(links: List[str]) -> Dict[str, Optional[str]]:
    """
    Извлечение специфичных ссылок из общего списка.
    Возвращает dict с linkedin, github, portfolio и т.д.
    """
    result = {
        'linkedin': None,
        'github': None,
        'portfolio': None,
        'hh_resume_url': None,
    }

    for link in links or []:
        link_lower = link.lower()

        if 'linkedin.com' in link_lower:
            result['linkedin'] = link
        elif 'github.com' in link_lower:
            result['github'] = link
        elif 'hh.ru/resume' in link_lower:
            result['hh_resume_url'] = link
        elif any(x in link_lower for x in ['portfolio', 'behance', 'dribbble', 'artstation']):
            result['portfolio'] = link

    return result


@dataclass
class ParsedResume:
    """Структурированные данные из резюме (улучшенная версия как в HuntFlow)."""
    # Основные данные
    name: Optional[str] = None
    first_name: Optional[str] = None  # Имя отдельно
    last_name: Optional[str] = None   # Фамилия отдельно
    middle_name: Optional[str] = None  # Отчество

    # Контакты (расширенные)
    phone: Optional[str] = None
    phones: List[str] = None  # Все найденные телефоны
    email: Optional[str] = None
    emails: List[str] = None  # Все найденные email
    telegram: Optional[str] = None
    whatsapp: Optional[str] = None
    skype: Optional[str] = None

    # Персональные данные
    birth_date: Optional[str] = None  # Дата рождения (YYYY-MM-DD или текст)
    age: Optional[int] = None  # Возраст
    gender: Optional[str] = None  # Пол (male/female)
    citizenship: Optional[str] = None  # Гражданство
    work_permit: Optional[str] = None  # Разрешение на работу
    relocation: Optional[str] = None  # Готовность к переезду (yes/no/possible)
    business_trip: Optional[str] = None  # Готовность к командировкам

    # Профессиональные данные
    position: Optional[str] = None  # Желаемая должность
    specialization: Optional[str] = None  # Специализация / направление
    company: Optional[str] = None  # Текущая/последняя компания
    experience_years: Optional[int] = None  # Общий опыт в годах
    experience_months: Optional[int] = None  # Дополнительные месяцы опыта

    # Зарплатные ожидания
    expected_salary_min: Optional[int] = None
    expected_salary_max: Optional[int] = None
    expected_salary_currency: str = "RUB"

    # Формат работы
    employment_type: Optional[str] = None  # Тип занятости: full-time, part-time, project, internship
    schedule: Optional[str] = None  # График: remote, office, hybrid, flexible

    # Навыки и образование
    skills: List[str] = None  # Ключевые навыки
    skills_detailed: List[Dict[str, Any]] = None  # [{name, level, years}] - с уровнем владения
    education: List[Dict[str, str]] = None  # [{institution, degree, faculty, year, education_level}]
    courses: List[Dict[str, str]] = None  # [{name, organization, year}] - курсы и сертификаты
    experience: List[Dict[str, str]] = None  # [{company, position, period, start_date, end_date, description, achievements}]
    languages: List[Dict[str, str]] = None  # [{language, level}]

    # Дополнительные данные
    location: Optional[str] = None  # Город проживания
    metro: Optional[str] = None  # Ближайшее метро
    about: Optional[str] = None  # Краткое описание / о себе
    achievements: List[str] = None  # Ключевые достижения
    recommendations: List[Dict[str, str]] = None  # [{name, position, company, contact}]

    # Ссылки и портфолио
    links: List[str] = None  # Все ссылки
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    hh_resume_url: Optional[str] = None  # Ссылка на резюме hh.ru

    # Дополнительная информация
    driver_license: List[str] = None  # Категории прав ["A", "B", "C"]
    has_car: Optional[bool] = None  # Наличие автомобиля
    military_status: Optional[str] = None  # Военный статус

    # Метаданные парсинга
    raw_text: Optional[str] = None
    source: Optional[str] = None  # Источник (file, hh.ru, linkedin, etc)
    parse_confidence: float = 0.0  # Уверенность парсинга 0-1
    parse_warnings: List[str] = None
    parsed_at: Optional[str] = None  # Время парсинга ISO

    def __post_init__(self):
        """Инициализация списков по умолчанию."""
        if self.phones is None:
            self.phones = []
        if self.emails is None:
            self.emails = []
        if self.skills is None:
            self.skills = []
        if self.skills_detailed is None:
            self.skills_detailed = []
        if self.education is None:
            self.education = []
        if self.courses is None:
            self.courses = []
        if self.experience is None:
            self.experience = []
        if self.languages is None:
            self.languages = []
        if self.achievements is None:
            self.achievements = []
        if self.recommendations is None:
            self.recommendations = []
        if self.links is None:
            self.links = []
        if self.driver_license is None:
            self.driver_license = []
        if self.parse_warnings is None:
            self.parse_warnings = []

    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь для API."""
        return asdict(self)

    def to_entity_data(self) -> Dict[str, Any]:
        """
        Конвертация в формат данных для создания Entity.
        Возвращает поля, совместимые с EntityCreate.
        """
        # Формируем extra_data с дополнительной информацией
        extra_data = {}

        # Основные данные
        if self.first_name:
            extra_data["first_name"] = self.first_name
        if self.last_name:
            extra_data["last_name"] = self.last_name
        if self.middle_name:
            extra_data["middle_name"] = self.middle_name

        # Персональные данные
        if self.birth_date:
            extra_data["birth_date"] = self.birth_date
        if self.age:
            extra_data["age"] = self.age
        if self.gender:
            extra_data["gender"] = self.gender
        if self.citizenship:
            extra_data["citizenship"] = self.citizenship
        if self.relocation:
            extra_data["relocation"] = self.relocation

        # Профессиональные данные
        if self.skills:
            extra_data["skills"] = self.skills
        if self.skills_detailed:
            extra_data["skills_detailed"] = self.skills_detailed
        if self.specialization:
            extra_data["specialization"] = self.specialization
        if self.education:
            extra_data["education"] = self.education
        if self.courses:
            extra_data["courses"] = self.courses
        if self.experience:
            extra_data["experience"] = self.experience
        if self.languages:
            extra_data["languages"] = self.languages
        if self.location:
            extra_data["location"] = self.location
        if self.metro:
            extra_data["metro"] = self.metro
        if self.about:
            extra_data["about"] = self.about
        if self.achievements:
            extra_data["achievements"] = self.achievements
        if self.recommendations:
            extra_data["recommendations"] = self.recommendations
        if self.links:
            extra_data["links"] = self.links
        if self.experience_years:
            extra_data["experience_years"] = self.experience_years
        if self.experience_months:
            extra_data["experience_months"] = self.experience_months

        # Формат работы
        if self.employment_type:
            extra_data["employment_type"] = self.employment_type
        if self.schedule:
            extra_data["schedule"] = self.schedule

        # Дополнительные ссылки
        if self.linkedin:
            extra_data["linkedin"] = self.linkedin
        if self.github:
            extra_data["github"] = self.github
        if self.portfolio:
            extra_data["portfolio"] = self.portfolio
        if self.hh_resume_url:
            extra_data["hh_resume_url"] = self.hh_resume_url

        # Дополнительная информация
        if self.driver_license:
            extra_data["driver_license"] = self.driver_license
        if self.has_car is not None:
            extra_data["has_car"] = self.has_car
        if self.military_status:
            extra_data["military_status"] = self.military_status
        if self.raw_text:
            extra_data["full_text"] = self.raw_text

        # Контакты
        if self.whatsapp:
            extra_data["whatsapp"] = self.whatsapp
        if self.skype:
            extra_data["skype"] = self.skype

        # Собираем telegram usernames
        telegram_usernames = []
        if self.telegram:
            # Нормализуем telegram username (убираем @ и t.me/)
            tg = self.telegram.lower().strip()
            tg = tg.replace("@", "").replace("https://t.me/", "").replace("t.me/", "")
            if tg:
                telegram_usernames.append(tg)

        # Собираем emails (основной + все найденные)
        emails = []
        if self.email:
            emails.append(self.email.lower().strip())
        for e in self.emails or []:
            normalized = e.lower().strip()
            if normalized and normalized not in emails:
                emails.append(normalized)

        # Собираем phones (основной + все найденные)
        phones = []
        if self.phone:
            phones.append(self.phone.strip())
        for p in self.phones or []:
            normalized = p.strip()
            if normalized and normalized not in phones:
                phones.append(normalized)

        return {
            "name": self.name or "Неизвестный кандидат",
            "phone": self.phone,
            "email": self.email,
            "telegram_usernames": telegram_usernames,
            "emails": emails,
            "phones": phones,
            "position": self.position,
            "company": self.company,
            "expected_salary_min": self.expected_salary_min,
            "expected_salary_max": self.expected_salary_max,
            "expected_salary_currency": self.expected_salary_currency,
            "extra_data": extra_data,
            "tags": ["resume_parsed"] + (self.skills[:5] if self.skills else [])
        }


# Промпт для AI парсинга резюме (улучшенная версия как в HuntFlow)
RESUME_PARSE_PROMPT = """Ты - профессиональный HR-специалист и эксперт по анализу резюме.
Твоя задача - максимально полно и точно извлечь ВСЕ данные из резюме кандидата.

ТЕКСТ РЕЗЮМЕ:
---
{resume_text}
---

Извлеки ВСЮ следующую информацию в формате JSON. Будь внимателен к деталям!

{{
    "name": "Полное ФИО кандидата",
    "first_name": "Имя",
    "last_name": "Фамилия",
    "middle_name": "Отчество (если есть)",

    "phone": "Основной телефон в исходном формате",
    "phones": ["все найденные телефоны"],
    "email": "Основной email",
    "emails": ["все найденные email адреса"],
    "telegram": "Telegram (@username или ссылка t.me/)",
    "whatsapp": "WhatsApp номер (если указан отдельно)",
    "skype": "Skype логин",

    "birth_date": "Дата рождения в формате YYYY-MM-DD или как указано",
    "age": возраст (число или null),
    "gender": "male" или "female" или null,
    "citizenship": "Гражданство",
    "relocation": "yes/no/possible - готовность к переезду",
    "business_trip": "yes/no - готовность к командировкам",

    "position": "Желаемая должность",
    "specialization": "Специализация / профессиональная область",
    "company": "Текущая или последняя компания",
    "experience_years": общий опыт в годах (целое число),
    "experience_months": дополнительные месяцы опыта,

    "expected_salary_min": минимальная зарплата (число),
    "expected_salary_max": максимальная зарплата (число),
    "expected_salary_currency": "RUB" / "USD" / "EUR" / "KZT",

    "employment_type": "full-time/part-time/project/internship",
    "schedule": "remote/office/hybrid/flexible",

    "skills": ["навык1", "навык2", ...],
    "skills_detailed": [
        {{"name": "Python", "level": "expert/advanced/intermediate/beginner", "years": 5}}
    ],

    "education": [
        {{
            "institution": "Название учебного заведения",
            "faculty": "Факультет",
            "degree": "Степень/специальность",
            "education_level": "higher/bachelor/master/phd/secondary/courses",
            "year": "Год окончания"
        }}
    ],

    "courses": [
        {{"name": "Название курса/сертификата", "organization": "Организация", "year": "Год"}}
    ],

    "experience": [
        {{
            "company": "Название компании",
            "position": "Должность",
            "period": "Период работы (как написано)",
            "start_date": "YYYY-MM или YYYY",
            "end_date": "YYYY-MM или 'настоящее время'",
            "description": "Описание обязанностей",
            "achievements": ["достижение1", "достижение2"]
        }}
    ],

    "languages": [
        {{"language": "Язык", "level": "native/fluent/advanced/intermediate/basic"}}
    ],

    "location": "Город проживания",
    "metro": "Ближайшее метро (если указано)",
    "about": "Краткое описание о себе (до 500 символов)",
    "achievements": ["ключевое достижение 1", "ключевое достижение 2"],

    "recommendations": [
        {{"name": "ФИО", "position": "Должность", "company": "Компания", "contact": "Контакт"}}
    ],

    "links": ["все найденные ссылки"],
    "linkedin": "ссылка на LinkedIn профиль",
    "github": "ссылка на GitHub",
    "portfolio": "ссылка на портфолио",

    "driver_license": ["A", "B", "C"],
    "has_car": true/false/null,
    "military_status": "статус воинской обязанности",

    "parse_confidence": число от 0.0 до 1.0,
    "parse_warnings": ["предупреждение1", ...]
}}

ВАЖНЫЕ ПРАВИЛА ИЗВЛЕЧЕНИЯ:

1. КОНТАКТЫ:
   - Ищи ВСЕ телефоны (могут быть в разных форматах: +7, 8, с пробелами, скобками)
   - Telegram может быть как @username так и ссылкой t.me/username
   - WhatsApp обычно указывают отдельно от обычного телефона

2. ФИО:
   - Разбей на first_name, last_name, middle_name если возможно
   - Для русских ФИО: Фамилия Имя Отчество

3. ОПЫТ РАБОТЫ:
   - Вычисли общий опыт в годах на основе дат работы
   - Сортируй от последнего места к первому
   - Выдели достижения отдельно от обязанностей

4. НАВЫКИ:
   - Извлеки как простой список skills
   - Если возможно определить уровень - добавь в skills_detailed

5. ОБРАЗОВАНИЕ:
   - Различай основное образование и курсы/сертификаты
   - Определи уровень образования (higher, bachelor, master, phd)

6. ЗАРПЛАТА:
   - Конвертируй в числа (100000, не "100 000 руб")
   - Определи валюту из контекста
   - "от 200" - это min, "до 300" - это max

7. ФОРМАТ РАБОТЫ:
   - employment_type: full-time (полная), part-time (частичная), project (проектная)
   - schedule: remote (удалённо), office (офис), hybrid (гибрид)

8. УВЕРЕННОСТЬ ПАРСИНГА:
   - 0.9-1.0: все основные поля найдены (ФИО, контакты, опыт)
   - 0.7-0.9: найдено большинство, есть мелкие пробелы
   - 0.5-0.7: много пропущенных полей
   - <0.5: критично мало данных

9. ПРЕДУПРЕЖДЕНИЯ:
   - Добавь в parse_warnings все проблемы:
     - "Не найден телефон"
     - "Не найден email"
     - "Неоднозначная дата рождения"
     - "Опыт работы не указан"
     - и т.д.

Верни ТОЛЬКО валидный JSON без markdown разметки и дополнительного текста!"""


class ResumeParserService:
    """Сервис парсинга резюме."""

    def __init__(self):
        self._client = None
        self.model = settings.claude_model

    @property
    def client(self) -> AsyncAnthropic:
        """Ленивая инициализация клиента Anthropic."""
        if self._client is None:
            if not settings.anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY не настроен!")
            self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._client

    async def extract_text_from_file(
        self,
        file_bytes: bytes,
        filename: str
    ) -> str:
        """
        Извлечение текста из файла резюме.

        Поддерживает форматы: PDF, DOC, DOCX, TXT, RTF.
        Использует существующий DocumentParser.

        Args:
            file_bytes: Содержимое файла в байтах
            filename: Имя файла с расширением

        Returns:
            Извлечённый текст

        Raises:
            ValueError: Если формат файла не поддерживается или парсинг не удался
        """
        # Проверяем расширение
        ext = filename.lower().split('.')[-1] if '.' in filename else ''
        allowed_extensions = {'pdf', 'doc', 'docx', 'txt', 'rtf', 'odt', 'html', 'htm', 'zip'}

        if ext not in allowed_extensions:
            raise ValueError(
                f"Неподдерживаемый формат файла: .{ext}. "
                f"Поддерживаются: {', '.join(allowed_extensions)}"
            )

        # Используем существующий DocumentParser
        result = await document_parser.parse(file_bytes, filename)

        if result.status == "failed":
            raise ValueError(f"Ошибка парсинга файла: {result.error}")

        if not result.content or not result.content.strip():
            raise ValueError("Не удалось извлечь текст из файла. Файл пуст или защищён.")

        logger.info(f"Извлечён текст из {filename}: {len(result.content)} символов")
        return result.content

    async def parse_resume_with_ai(self, text: str) -> ParsedResume:
        """
        AI-парсинг структуры резюме.

        Использует Claude API для извлечения структурированных данных.

        Args:
            text: Текст резюме

        Returns:
            ParsedResume с извлечёнными данными
        """
        if not text or len(text.strip()) < 50:
            return ParsedResume(
                parse_confidence=0.0,
                parse_warnings=["Текст резюме слишком короткий для анализа"]
            )

        # Ограничиваем длину текста для API
        max_text_length = 50000
        if len(text) > max_text_length:
            text = text[:max_text_length]
            logger.warning(f"Текст резюме обрезан до {max_text_length} символов")

        prompt = RESUME_PARSE_PROMPT.format(resume_text=text)

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.content[0].text.strip()

            # Извлекаем JSON из ответа
            parsed_data = self._extract_json(response_text)

            if not parsed_data:
                logger.warning("AI не вернул валидный JSON")
                return ParsedResume(
                    raw_text=text[:1000],
                    parse_confidence=0.0,
                    parse_warnings=["AI не смог распарсить резюме"]
                )

            # Создаём ParsedResume из данных
            resume = self._dict_to_parsed_resume(parsed_data)
            resume.raw_text = text

            # Постобработка: нормализация контактов
            resume = self._postprocess_resume(resume)

            return resume

        except Exception as e:
            logger.error(f"Ошибка AI парсинга: {e}")
            return ParsedResume(
                raw_text=text[:1000],
                parse_confidence=0.0,
                parse_warnings=[f"Ошибка AI парсинга: {str(e)}"]
            )

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Извлечение JSON из текста ответа AI."""
        # Пробуем напрямую
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Ищем JSON в markdown блоке
        json_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Ищем JSON по фигурным скобкам
        brace_match = re.search(r'\{[\s\S]*\}', text)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def _dict_to_parsed_resume(self, data: Dict[str, Any]) -> ParsedResume:
        """Конвертация словаря в ParsedResume с валидацией."""

        def safe_int(value: Any) -> Optional[int]:
            """Безопасная конвертация в int."""
            if value is None:
                return None
            if isinstance(value, int):
                return value
            if isinstance(value, float):
                return int(value)
            if isinstance(value, str):
                # Удаляем всё кроме цифр
                cleaned = re.sub(r'[^\d]', '', value)
                return int(cleaned) if cleaned else None
            return None

        def safe_float(value: Any, default: float = 0.0) -> float:
            """Безопасная конвертация в float."""
            if value is None:
                return default
            try:
                return float(value)
            except (ValueError, TypeError):
                return default

        def safe_list(value: Any) -> List:
            """Безопасная конвертация в список."""
            if value is None:
                return []
            if isinstance(value, list):
                return value
            return []

        def safe_str(value: Any) -> Optional[str]:
            """Безопасная конвертация в строку."""
            if value is None:
                return None
            if isinstance(value, str):
                return value.strip() if value.strip() else None
            return str(value).strip() or None

        def safe_bool(value: Any) -> Optional[bool]:
            """Безопасная конвертация в bool."""
            if value is None:
                return None
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                lower = value.lower().strip()
                if lower in ('true', 'yes', 'да', '1'):
                    return True
                if lower in ('false', 'no', 'нет', '0'):
                    return False
            return None

        return ParsedResume(
            # Основные данные
            name=safe_str(data.get("name")),
            first_name=safe_str(data.get("first_name")),
            last_name=safe_str(data.get("last_name")),
            middle_name=safe_str(data.get("middle_name")),

            # Контакты
            phone=safe_str(data.get("phone")),
            phones=safe_list(data.get("phones")),
            email=safe_str(data.get("email")),
            emails=safe_list(data.get("emails")),
            telegram=safe_str(data.get("telegram")),
            whatsapp=safe_str(data.get("whatsapp")),
            skype=safe_str(data.get("skype")),

            # Персональные данные
            birth_date=safe_str(data.get("birth_date")),
            age=safe_int(data.get("age")),
            gender=safe_str(data.get("gender")),
            citizenship=safe_str(data.get("citizenship")),
            work_permit=safe_str(data.get("work_permit")),
            relocation=safe_str(data.get("relocation")),
            business_trip=safe_str(data.get("business_trip")),

            # Профессиональные данные
            position=safe_str(data.get("position")),
            specialization=safe_str(data.get("specialization")),
            company=safe_str(data.get("company")),
            experience_years=safe_int(data.get("experience_years")),
            experience_months=safe_int(data.get("experience_months")),

            # Зарплата
            expected_salary_min=safe_int(data.get("expected_salary_min")),
            expected_salary_max=safe_int(data.get("expected_salary_max")),
            expected_salary_currency=safe_str(data.get("expected_salary_currency")) or "RUB",

            # Формат работы
            employment_type=safe_str(data.get("employment_type")),
            schedule=safe_str(data.get("schedule")),

            # Навыки и образование
            skills=safe_list(data.get("skills")),
            skills_detailed=safe_list(data.get("skills_detailed")),
            education=safe_list(data.get("education")),
            courses=safe_list(data.get("courses")),
            experience=safe_list(data.get("experience")),
            languages=safe_list(data.get("languages")),

            # Дополнительные данные
            location=safe_str(data.get("location")),
            metro=safe_str(data.get("metro")),
            about=safe_str(data.get("about")),
            achievements=safe_list(data.get("achievements")),
            recommendations=safe_list(data.get("recommendations")),

            # Ссылки
            links=safe_list(data.get("links")),
            linkedin=safe_str(data.get("linkedin")),
            github=safe_str(data.get("github")),
            portfolio=safe_str(data.get("portfolio")),
            hh_resume_url=safe_str(data.get("hh_resume_url")),

            # Дополнительная информация
            driver_license=safe_list(data.get("driver_license")),
            has_car=safe_bool(data.get("has_car")),
            military_status=safe_str(data.get("military_status")),

            # Метаданные
            parse_confidence=safe_float(data.get("parse_confidence"), 0.5),
            parse_warnings=safe_list(data.get("parse_warnings"))
        )

    def _postprocess_resume(self, resume: ParsedResume) -> ParsedResume:
        """
        Постобработка распарсенного резюме.
        Нормализация контактов, валидация, дополнение данных.
        """
        from datetime import datetime

        # 1. Нормализация телефонов
        if resume.phone:
            resume.phone = normalize_phone(resume.phone)
            if not validate_phone(resume.phone):
                if resume.parse_warnings is None:
                    resume.parse_warnings = []
                resume.parse_warnings.append(f"Телефон может быть некорректным: {resume.phone}")

        if resume.phones:
            resume.phones = [normalize_phone(p) for p in resume.phones if p]
            resume.phones = [p for p in resume.phones if validate_phone(p)]

        # 2. Нормализация email
        if resume.email:
            resume.email = normalize_email(resume.email)
            if not validate_email(resume.email):
                if resume.parse_warnings is None:
                    resume.parse_warnings = []
                resume.parse_warnings.append(f"Email может быть некорректным: {resume.email}")

        if resume.emails:
            resume.emails = [normalize_email(e) for e in resume.emails if e]
            resume.emails = [e for e in resume.emails if validate_email(e)]

        # 3. Нормализация Telegram
        if resume.telegram:
            resume.telegram = normalize_telegram(resume.telegram)

        # 4. Извлечение специфичных ссылок из общего списка
        if resume.links:
            extracted = extract_links_by_type(resume.links)
            if not resume.linkedin and extracted['linkedin']:
                resume.linkedin = extracted['linkedin']
            if not resume.github and extracted['github']:
                resume.github = extracted['github']
            if not resume.portfolio and extracted['portfolio']:
                resume.portfolio = extracted['portfolio']
            if not resume.hh_resume_url and extracted['hh_resume_url']:
                resume.hh_resume_url = extracted['hh_resume_url']

        # 5. Добавляем timestamp парсинга
        resume.parsed_at = datetime.utcnow().isoformat()

        # 6. Дедупликация телефонов и email
        if resume.phones:
            # Добавляем основной телефон в список если его там нет
            if resume.phone and resume.phone not in resume.phones:
                resume.phones.insert(0, resume.phone)
            # Убираем дубликаты, сохраняя порядок
            seen = set()
            unique_phones = []
            for p in resume.phones:
                if p not in seen:
                    seen.add(p)
                    unique_phones.append(p)
            resume.phones = unique_phones

        if resume.emails:
            if resume.email and resume.email not in resume.emails:
                resume.emails.insert(0, resume.email)
            seen = set()
            unique_emails = []
            for e in resume.emails:
                if e not in seen:
                    seen.add(e)
                    unique_emails.append(e)
            resume.emails = unique_emails

        # 7. Проверка критичных полей и корректировка confidence
        warnings = resume.parse_warnings or []

        if not resume.name:
            warnings.append("ФИО не найдено")
        if not resume.phone and not resume.phones:
            warnings.append("Телефон не найден")
        if not resume.email and not resume.emails:
            warnings.append("Email не найден")
        if not resume.position:
            warnings.append("Желаемая должность не указана")

        # Корректируем confidence на основе найденных данных
        critical_fields = [resume.name, resume.phone or resume.phones, resume.email or resume.emails]
        important_fields = [resume.position, resume.experience, resume.skills]

        critical_found = sum(1 for f in critical_fields if f)
        important_found = sum(1 for f in important_fields if f)

        # Пересчитываем confidence если слишком оптимистичный
        max_confidence = (critical_found / 3) * 0.6 + (important_found / 3) * 0.4
        if resume.parse_confidence > max_confidence + 0.2:
            resume.parse_confidence = max_confidence

        resume.parse_warnings = warnings

        return resume

    async def parse_resume(
        self,
        file_bytes: bytes,
        filename: str
    ) -> ParsedResume:
        """
        Полный парсинг резюме: извлечение текста + AI-анализ.

        Args:
            file_bytes: Содержимое файла
            filename: Имя файла

        Returns:
            ParsedResume со всеми извлечёнными данными
        """
        # Шаг 1: Извлечение текста
        text = await self.extract_text_from_file(file_bytes, filename)

        # Шаг 2: AI парсинг
        resume = await self.parse_resume_with_ai(text)

        return resume


# Глобальный экземпляр сервиса
resume_parser_service = ResumeParserService()
