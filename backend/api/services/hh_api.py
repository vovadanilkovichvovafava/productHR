"""
hh.ru Official API Integration

Uses the free public API to fetch vacancy and resume data directly,
avoiding expensive AI parsing when possible.

API Documentation: https://api.hh.ru/openapi/redoc
"""
import httpx
import re
import logging
from typing import Optional, Dict, Any

from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..utils.http_client import get_http_client

logger = logging.getLogger(__name__)

HH_API_BASE = "https://api.hh.ru"


class HHVacancy(BaseModel):
    """Structured vacancy data from hh.ru API"""
    id: str
    title: str
    description: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = "RUB"
    location: Optional[str] = None
    company_name: Optional[str] = None
    employment_type: Optional[str] = None
    experience_level: Optional[str] = None
    skills: list[str] = []
    source_url: str


def extract_vacancy_id(url: str) -> Optional[str]:
    """Extract vacancy ID from hh.ru URL.

    Args:
        url: The hh.ru vacancy URL

    Returns:
        The extracted vacancy ID or None if not found
    """
    # Patterns: /vacancy/123, /vacancies/123, vacancy_id=123
    patterns = [
        r'/vacancy/(\d+)',
        r'/vacancies/(\d+)',
        r'vacancy[_-]?id[=:](\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
    reraise=True
)
async def fetch_vacancy_from_api(vacancy_id: str) -> Dict[str, Any]:
    """Fetch vacancy data from hh.ru API.

    Args:
        vacancy_id: The hh.ru vacancy ID

    Returns:
        Raw vacancy data from the API

    Raises:
        httpx.HTTPStatusError: If the API returns an error status
    """
    url = f"{HH_API_BASE}/vacancies/{vacancy_id}"
    client = get_http_client()
    response = await client.get(
        url,
        headers={"User-Agent": "HR-Bot/1.0"},
        timeout=10.0
    )
    response.raise_for_status()
    return response.json()


def map_hh_experience(experience_id: str) -> str:
    """Map hh.ru experience level to our format.

    Args:
        experience_id: The hh.ru experience identifier

    Returns:
        Mapped experience level string
    """
    mapping = {
        "noExperience": "intern",
        "between1And3": "junior",
        "between3And6": "middle",
        "moreThan6": "senior",
    }
    return mapping.get(experience_id, "middle")


def map_hh_employment(employment_id: str) -> str:
    """Map hh.ru employment type to our format.

    Args:
        employment_id: The hh.ru employment type identifier

    Returns:
        Mapped employment type string
    """
    mapping = {
        "full": "full-time",
        "part": "part-time",
        "project": "contract",
        "volunteer": "contract",
        "probation": "full-time",
    }
    return mapping.get(employment_id, "full-time")


def map_hh_currency(currency: str) -> str:
    """Map hh.ru currency code to our format.

    Args:
        currency: The hh.ru currency code

    Returns:
        Normalized currency code
    """
    mapping = {
        "RUR": "RUB",
        "RUB": "RUB",
        "USD": "USD",
        "EUR": "EUR",
        "KZT": "KZT",
        "UAH": "UAH",
        "BYR": "BYN",
    }
    return mapping.get(currency, "RUB")


def clean_html_tags(text: str) -> str:
    """Remove HTML tags from text.

    Args:
        text: HTML text to clean

    Returns:
        Plain text without HTML tags
    """
    return re.sub(r'<[^>]+>', '', text)


async def parse_vacancy_via_api(url: str) -> Optional[HHVacancy]:
    """Parse hh.ru vacancy using official API.

    Returns None if parsing fails (will fallback to AI).

    Args:
        url: The hh.ru vacancy URL

    Returns:
        HHVacancy object or None if parsing failed
    """
    vacancy_id = extract_vacancy_id(url)
    if not vacancy_id:
        logger.warning(f"Could not extract vacancy ID from URL: {url}")
        return None

    try:
        data = await fetch_vacancy_from_api(vacancy_id)

        # Extract salary
        salary = data.get("salary") or {}
        salary_min = salary.get("from")
        salary_max = salary.get("to")
        salary_currency = map_hh_currency(salary.get("currency", "RUR"))

        # Extract skills
        skills = [skill["name"] for skill in data.get("key_skills", [])]

        # Build description from API data
        description = None
        if data.get("description"):
            # Remove HTML tags
            description = clean_html_tags(data["description"])

        return HHVacancy(
            id=str(data["id"]),
            title=data["name"],
            description=description,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=salary_currency,
            location=data.get("area", {}).get("name"),
            company_name=data.get("employer", {}).get("name"),
            employment_type=map_hh_employment(data.get("employment", {}).get("id", "")),
            experience_level=map_hh_experience(data.get("experience", {}).get("id", "")),
            skills=skills,
            source_url=url,
        )

    except httpx.HTTPStatusError as e:
        logger.warning(f"hh.ru API returned {e.response.status_code} for vacancy {vacancy_id}")
        return None
    except Exception as e:
        logger.error(f"Error fetching vacancy from hh.ru API: {e}")
        return None
