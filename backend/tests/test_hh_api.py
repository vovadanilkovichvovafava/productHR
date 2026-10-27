"""
Tests for hh.ru Official API Integration.

Tests cover:
- Vacancy ID extraction from URLs
- Currency/experience/employment mapping
- API data parsing
- Error handling
"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, HTTPStatusError, Response

from api.services.hh_api import (
    HHVacancy,
    extract_vacancy_id,
    fetch_vacancy_from_api,
    map_hh_experience,
    map_hh_employment,
    map_hh_currency,
    clean_html_tags,
    parse_vacancy_via_api,
)


# ============================================================================
# UNIT TESTS - Vacancy ID Extraction
# ============================================================================

class TestExtractVacancyId:
    """Tests for extracting vacancy ID from hh.ru URLs."""

    def test_extract_from_standard_url(self):
        """Test extraction from standard /vacancy/ID URL."""
        url = "https://hh.ru/vacancy/12345678"
        assert extract_vacancy_id(url) == "12345678"

    def test_extract_from_www_url(self):
        """Test extraction from www.hh.ru URL."""
        url = "https://www.hh.ru/vacancy/87654321"
        assert extract_vacancy_id(url) == "87654321"

    def test_extract_from_regional_subdomain(self):
        """Test extraction from regional subdomain URLs."""
        urls = [
            ("https://spb.hh.ru/vacancy/11111111", "11111111"),
            ("https://msk.hh.ru/vacancy/22222222", "22222222"),
            ("https://ekb.hh.ru/vacancy/33333333", "33333333"),
            ("https://nn.hh.ru/vacancy/44444444", "44444444"),
        ]
        for url, expected_id in urls:
            assert extract_vacancy_id(url) == expected_id

    def test_extract_from_vacancies_url(self):
        """Test extraction from /vacancies/ID URL pattern."""
        url = "https://hh.ru/vacancies/55555555"
        assert extract_vacancy_id(url) == "55555555"

    def test_extract_with_query_params(self):
        """Test extraction from URL with query parameters."""
        url = "https://hh.ru/vacancy/66666666?from=search&hhtmFrom=vacancy_search_list"
        assert extract_vacancy_id(url) == "66666666"

    def test_extract_with_fragment(self):
        """Test extraction from URL with fragment."""
        url = "https://hh.ru/vacancy/77777777#skills"
        assert extract_vacancy_id(url) == "77777777"

    def test_extract_vacancy_id_param(self):
        """Test extraction from vacancy_id query parameter."""
        url = "https://hh.ru/applicant/resumes?vacancy_id=88888888"
        assert extract_vacancy_id(url) == "88888888"

    def test_extract_case_insensitive(self):
        """Test that extraction is case-insensitive."""
        url = "https://HH.RU/VACANCY/99999999"
        assert extract_vacancy_id(url) == "99999999"

    def test_extract_returns_none_for_invalid_url(self):
        """Test that None is returned for URLs without vacancy ID."""
        urls = [
            "https://hh.ru/employer/123",
            "https://hh.ru/resume/abc123",
            "https://linkedin.com/jobs/view/123456",
            "https://example.com/vacancy",
            "",
            "not-a-url",
        ]
        for url in urls:
            assert extract_vacancy_id(url) is None


# ============================================================================
# UNIT TESTS - Experience Mapping
# ============================================================================

class TestMapHHExperience:
    """Tests for mapping hh.ru experience levels."""

    def test_map_no_experience(self):
        """Test mapping no experience to intern."""
        assert map_hh_experience("noExperience") == "intern"

    def test_map_1_to_3_years(self):
        """Test mapping 1-3 years to junior."""
        assert map_hh_experience("between1And3") == "junior"

    def test_map_3_to_6_years(self):
        """Test mapping 3-6 years to middle."""
        assert map_hh_experience("between3And6") == "middle"

    def test_map_more_than_6_years(self):
        """Test mapping 6+ years to senior."""
        assert map_hh_experience("moreThan6") == "senior"

    def test_map_unknown_experience(self):
        """Test that unknown experience defaults to middle."""
        assert map_hh_experience("unknown") == "middle"
        assert map_hh_experience("") == "middle"


# ============================================================================
# UNIT TESTS - Employment Mapping
# ============================================================================

class TestMapHHEmployment:
    """Tests for mapping hh.ru employment types."""

    def test_map_full_time(self):
        """Test mapping full time employment."""
        assert map_hh_employment("full") == "full-time"

    def test_map_part_time(self):
        """Test mapping part time employment."""
        assert map_hh_employment("part") == "part-time"

    def test_map_project(self):
        """Test mapping project/contract employment."""
        assert map_hh_employment("project") == "contract"

    def test_map_volunteer(self):
        """Test mapping volunteer work."""
        assert map_hh_employment("volunteer") == "contract"

    def test_map_probation(self):
        """Test mapping probation period."""
        assert map_hh_employment("probation") == "full-time"

    def test_map_unknown_employment(self):
        """Test that unknown employment defaults to full-time."""
        assert map_hh_employment("unknown") == "full-time"
        assert map_hh_employment("") == "full-time"


# ============================================================================
# UNIT TESTS - Currency Mapping
# ============================================================================

class TestMapHHCurrency:
    """Tests for mapping hh.ru currency codes."""

    def test_map_rur_to_rub(self):
        """Test mapping old RUR code to RUB."""
        assert map_hh_currency("RUR") == "RUB"

    def test_map_rub(self):
        """Test mapping RUB currency."""
        assert map_hh_currency("RUB") == "RUB"

    def test_map_usd(self):
        """Test mapping USD currency."""
        assert map_hh_currency("USD") == "USD"

    def test_map_eur(self):
        """Test mapping EUR currency."""
        assert map_hh_currency("EUR") == "EUR"

    def test_map_kzt(self):
        """Test mapping Kazakh tenge."""
        assert map_hh_currency("KZT") == "KZT"

    def test_map_uah(self):
        """Test mapping Ukrainian hryvnia."""
        assert map_hh_currency("UAH") == "UAH"

    def test_map_byr_to_byn(self):
        """Test mapping old BYR code to BYN."""
        assert map_hh_currency("BYR") == "BYN"

    def test_map_unknown_currency(self):
        """Test that unknown currency defaults to RUB."""
        assert map_hh_currency("GBP") == "RUB"
        assert map_hh_currency("") == "RUB"


# ============================================================================
# UNIT TESTS - HTML Tag Cleaning
# ============================================================================

class TestCleanHtmlTags:
    """Tests for HTML tag removal."""

    def test_clean_simple_tags(self):
        """Test removing simple HTML tags."""
        html = "<p>Hello <strong>World</strong></p>"
        assert clean_html_tags(html) == "Hello World"

    def test_clean_nested_tags(self):
        """Test removing nested HTML tags."""
        html = "<div><p>Test <span>content</span></p></div>"
        assert clean_html_tags(html) == "Test content"

    def test_clean_tags_with_attributes(self):
        """Test removing tags with attributes."""
        html = '<a href="https://example.com" class="link">Click here</a>'
        assert clean_html_tags(html) == "Click here"

    def test_clean_br_tags(self):
        """Test handling br tags."""
        html = "Line 1<br>Line 2<br/>Line 3"
        assert clean_html_tags(html) == "Line 1Line 2Line 3"

    def test_clean_empty_string(self):
        """Test cleaning empty string."""
        assert clean_html_tags("") == ""

    def test_clean_no_tags(self):
        """Test text without HTML tags."""
        text = "Plain text without tags"
        assert clean_html_tags(text) == "Plain text without tags"


# ============================================================================
# UNIT TESTS - HHVacancy Model
# ============================================================================

class TestHHVacancyModel:
    """Tests for HHVacancy Pydantic model."""

    def test_create_minimal_vacancy(self):
        """Test creating vacancy with minimal required fields."""
        vacancy = HHVacancy(
            id="12345",
            title="Python Developer",
            source_url="https://hh.ru/vacancy/12345"
        )
        assert vacancy.id == "12345"
        assert vacancy.title == "Python Developer"
        assert vacancy.skills == []
        assert vacancy.salary_currency == "RUB"

    def test_create_full_vacancy(self):
        """Test creating vacancy with all fields."""
        vacancy = HHVacancy(
            id="67890",
            title="Senior Backend Developer",
            description="We are looking for an experienced developer",
            salary_min=200000,
            salary_max=350000,
            salary_currency="RUB",
            location="Moscow",
            company_name="TechCorp",
            employment_type="full-time",
            experience_level="senior",
            skills=["Python", "FastAPI", "PostgreSQL"],
            source_url="https://hh.ru/vacancy/67890"
        )
        assert vacancy.salary_min == 200000
        assert vacancy.salary_max == 350000
        assert vacancy.location == "Moscow"
        assert len(vacancy.skills) == 3
        assert "Python" in vacancy.skills

    def test_vacancy_default_values(self):
        """Test default values for optional fields."""
        vacancy = HHVacancy(
            id="11111",
            title="Test Position",
            source_url="https://hh.ru/vacancy/11111"
        )
        assert vacancy.description is None
        assert vacancy.salary_min is None
        assert vacancy.salary_max is None
        assert vacancy.salary_currency == "RUB"
        assert vacancy.location is None
        assert vacancy.company_name is None
        assert vacancy.employment_type is None
        assert vacancy.experience_level is None
        assert vacancy.skills == []


# ============================================================================
# INTEGRATION TESTS - API Fetching (Mocked)
# ============================================================================

class TestFetchVacancyFromApi:
    """Tests for fetching vacancy data from hh.ru API."""

    @pytest.mark.asyncio
    async def test_fetch_vacancy_success(self):
        """Test successful vacancy fetch from API."""
        import api.services.hh_api as hh_module

        mock_response_data = {
            "id": 12345678,
            "name": "Python Developer",
            "description": "<p>Job description</p>",
            "salary": {"from": 150000, "to": 250000, "currency": "RUR"},
            "area": {"name": "Moscow"},
            "employer": {"name": "TechCorp"},
            "employment": {"id": "full"},
            "experience": {"id": "between3And6"},
            "key_skills": [{"name": "Python"}, {"name": "Django"}]
        }

        # Запрос идёт через общий клиент get_http_client() (не через
        # `async with httpx.AsyncClient()`), поэтому подменяем его. Прежняя
        # подмена httpx.AsyncClient до общего клиента не доставала — тест мог
        # уйти в настоящий hh.ru.
        class FakeClient:
            def __init__(self):
                self.get_called = False
                self.kwargs = None

            async def get(self, *args, **kwargs):
                self.get_called = True
                self.kwargs = kwargs
                resp = MagicMock()
                resp.json.return_value = mock_response_data
                resp.raise_for_status = MagicMock()
                return resp

        mock_client = FakeClient()

        with patch.object(hh_module, "get_http_client", return_value=mock_client):
            result = await fetch_vacancy_from_api("12345678")

        assert result["id"] == 12345678
        assert result["name"] == "Python Developer"
        assert mock_client.get_called
        assert mock_client.kwargs.get("timeout")  # запрос к hh.ru — с таймаутом

    @pytest.mark.asyncio
    async def test_fetch_vacancy_http_error(self):
        """Test handling of HTTP errors from API."""
        import api.services.hh_api as hh_module

        # Create a mock response that raises HTTPStatusError on raise_for_status
        mock_request = MagicMock()
        mock_request.url = "https://api.hh.ru/vacancies/99999999"
        mock_response_obj = MagicMock()
        mock_response_obj.status_code = 404

        http_error = HTTPStatusError(
            "Not Found",
            request=mock_request,
            response=mock_response_obj
        )

        class FakeClient:
            async def get(self, *args, **kwargs):
                resp = MagicMock()
                resp.status_code = 404
                resp.raise_for_status = MagicMock(side_effect=http_error)
                return resp

        # Подменяем общий клиент get_http_client() (см. test_fetch_vacancy_success).
        with patch.object(hh_module, "get_http_client", return_value=FakeClient()):
            with pytest.raises(HTTPStatusError):
                await fetch_vacancy_from_api("99999999")


# ============================================================================
# INTEGRATION TESTS - Full Parsing Flow (Mocked)
# ============================================================================

class TestParseVacancyViaApi:
    """Tests for full vacancy parsing via API."""

    @pytest.mark.asyncio
    async def test_parse_vacancy_success(self):
        """Test successful vacancy parsing via API."""
        mock_api_data = {
            "id": 12345678,
            "name": "Senior Python Developer",
            "description": "<p>We are looking for an experienced <strong>developer</strong></p>",
            "salary": {"from": 200000, "to": 350000, "currency": "RUR"},
            "area": {"name": "Moscow"},
            "employer": {"name": "TechCorp"},
            "employment": {"id": "full"},
            "experience": {"id": "moreThan6"},
            "key_skills": [
                {"name": "Python"},
                {"name": "FastAPI"},
                {"name": "PostgreSQL"}
            ]
        }

        with patch('api.services.hh_api.fetch_vacancy_from_api', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_api_data

            result = await parse_vacancy_via_api("https://hh.ru/vacancy/12345678")

            assert result is not None
            assert result.id == "12345678"
            assert result.title == "Senior Python Developer"
            assert result.salary_min == 200000
            assert result.salary_max == 350000
            assert result.salary_currency == "RUB"
            assert result.location == "Moscow"
            assert result.company_name == "TechCorp"
            assert result.employment_type == "full-time"
            assert result.experience_level == "senior"
            assert len(result.skills) == 3
            assert "Python" in result.skills
            # Check HTML was cleaned from description
            assert "<p>" not in result.description
            assert "<strong>" not in result.description

    @pytest.mark.asyncio
    async def test_parse_vacancy_no_salary(self):
        """Test parsing vacancy without salary information."""
        mock_api_data = {
            "id": 11111111,
            "name": "Junior Developer",
            "description": "Entry level position",
            "salary": None,
            "area": {"name": "Saint Petersburg"},
            "employer": {"name": "StartupXYZ"},
            "employment": {"id": "full"},
            "experience": {"id": "noExperience"},
            "key_skills": []
        }

        with patch('api.services.hh_api.fetch_vacancy_from_api', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_api_data

            result = await parse_vacancy_via_api("https://hh.ru/vacancy/11111111")

            assert result is not None
            assert result.salary_min is None
            assert result.salary_max is None
            assert result.salary_currency == "RUB"
            assert result.experience_level == "intern"

    @pytest.mark.asyncio
    async def test_parse_vacancy_partial_salary(self):
        """Test parsing vacancy with only min or max salary."""
        # Only minimum salary
        mock_api_data = {
            "id": 22222222,
            "name": "Middle Developer",
            "description": "Good position",
            "salary": {"from": 150000, "to": None, "currency": "RUR"},
            "area": {"name": "Remote"},
            "employer": {"name": "RemoteCo"},
            "employment": {"id": "part"},
            "experience": {"id": "between1And3"},
            "key_skills": [{"name": "JavaScript"}]
        }

        with patch('api.services.hh_api.fetch_vacancy_from_api', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_api_data

            result = await parse_vacancy_via_api("https://hh.ru/vacancy/22222222")

            assert result.salary_min == 150000
            assert result.salary_max is None
            assert result.employment_type == "part-time"
            assert result.experience_level == "junior"

    @pytest.mark.asyncio
    async def test_parse_vacancy_invalid_url(self):
        """Test that invalid URL returns None."""
        result = await parse_vacancy_via_api("https://linkedin.com/jobs/view/123")
        assert result is None

    @pytest.mark.asyncio
    async def test_parse_vacancy_empty_url(self):
        """Test that empty URL returns None."""
        result = await parse_vacancy_via_api("")
        assert result is None

    @pytest.mark.asyncio
    async def test_parse_vacancy_api_404_error(self):
        """Test that 404 error returns None."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch('api.services.hh_api.fetch_vacancy_from_api', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = HTTPStatusError(
                "Not Found",
                request=MagicMock(),
                response=mock_response
            )

            result = await parse_vacancy_via_api("https://hh.ru/vacancy/99999999")
            assert result is None

    @pytest.mark.asyncio
    async def test_parse_vacancy_api_500_error(self):
        """Test that 500 error returns None."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch('api.services.hh_api.fetch_vacancy_from_api', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = HTTPStatusError(
                "Internal Server Error",
                request=MagicMock(),
                response=mock_response
            )

            result = await parse_vacancy_via_api("https://hh.ru/vacancy/88888888")
            assert result is None

    @pytest.mark.asyncio
    async def test_parse_vacancy_connection_error(self):
        """Test that connection error returns None."""
        with patch('api.services.hh_api.fetch_vacancy_from_api', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = Exception("Connection timeout")

            result = await parse_vacancy_via_api("https://hh.ru/vacancy/77777777")
            assert result is None

    @pytest.mark.asyncio
    async def test_parse_vacancy_usd_currency(self):
        """Test parsing vacancy with USD salary."""
        mock_api_data = {
            "id": 33333333,
            "name": "Remote Developer",
            "description": "Work from anywhere",
            "salary": {"from": 5000, "to": 8000, "currency": "USD"},
            "area": {"name": "Remote"},
            "employer": {"name": "GlobalTech"},
            "employment": {"id": "full"},
            "experience": {"id": "between3And6"},
            "key_skills": []
        }

        with patch('api.services.hh_api.fetch_vacancy_from_api', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_api_data

            result = await parse_vacancy_via_api("https://hh.ru/vacancy/33333333")

            assert result.salary_min == 5000
            assert result.salary_max == 8000
            assert result.salary_currency == "USD"

    @pytest.mark.asyncio
    async def test_parse_vacancy_regional_url(self):
        """Test parsing vacancy from regional subdomain URL."""
        mock_api_data = {
            "id": 44444444,
            "name": "Local Developer",
            "description": "Local position",
            "salary": {"from": 100000, "to": 150000, "currency": "RUR"},
            "area": {"name": "Saint Petersburg"},
            "employer": {"name": "LocalCorp"},
            "employment": {"id": "full"},
            "experience": {"id": "between1And3"},
            "key_skills": [{"name": "Java"}]
        }

        with patch('api.services.hh_api.fetch_vacancy_from_api', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_api_data

            result = await parse_vacancy_via_api("https://spb.hh.ru/vacancy/44444444")

            assert result is not None
            assert result.id == "44444444"
            assert result.location == "Saint Petersburg"

    @pytest.mark.asyncio
    async def test_parse_vacancy_missing_optional_fields(self):
        """Test parsing vacancy with missing optional fields in API response."""
        mock_api_data = {
            "id": 55555555,
            "name": "Minimal Vacancy",
            # No description, salary, area, employer, etc.
        }

        with patch('api.services.hh_api.fetch_vacancy_from_api', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_api_data

            result = await parse_vacancy_via_api("https://hh.ru/vacancy/55555555")

            assert result is not None
            assert result.id == "55555555"
            assert result.title == "Minimal Vacancy"
            assert result.description is None
            assert result.salary_min is None
            assert result.location is None
            assert result.company_name is None
            assert result.skills == []


# ============================================================================
# TESTS - URL Patterns
# ============================================================================

class TestVacancyUrlPatterns:
    """Tests for various hh.ru URL patterns."""

    @pytest.mark.asyncio
    async def test_standard_vacancy_url(self):
        """Test standard vacancy URL pattern."""
        url = "https://hh.ru/vacancy/12345678"
        vacancy_id = extract_vacancy_id(url)
        assert vacancy_id == "12345678"

    @pytest.mark.asyncio
    async def test_mobile_url(self):
        """Test mobile hh.ru URL."""
        url = "https://m.hh.ru/vacancy/12345678"
        # Mobile URLs should also work with standard pattern
        vacancy_id = extract_vacancy_id(url)
        assert vacancy_id == "12345678"

    @pytest.mark.asyncio
    async def test_url_with_utm_params(self):
        """Test URL with UTM tracking parameters."""
        url = "https://hh.ru/vacancy/12345678?utm_source=google&utm_medium=cpc"
        vacancy_id = extract_vacancy_id(url)
        assert vacancy_id == "12345678"

    @pytest.mark.asyncio
    async def test_employer_vacancy_url(self):
        """Test employer-specific vacancy URL."""
        url = "https://hh.ru/employer/1234/vacancies/12345678"
        vacancy_id = extract_vacancy_id(url)
        # This pattern includes /vacancies/ which should be matched
        assert vacancy_id == "12345678"


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

class TestEdgeCases:
    """Edge case tests for hh.ru API integration."""

    @pytest.mark.asyncio
    async def test_very_long_description(self):
        """Test handling of very long vacancy descriptions."""
        long_description = "<p>" + "A" * 50000 + "</p>"
        mock_api_data = {
            "id": 66666666,
            "name": "Test Vacancy",
            "description": long_description,
            "salary": None,
            "area": {"name": "Moscow"},
            "employer": {"name": "TestCorp"},
            "employment": {"id": "full"},
            "experience": {"id": "between1And3"},
            "key_skills": []
        }

        with patch('api.services.hh_api.fetch_vacancy_from_api', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_api_data

            result = await parse_vacancy_via_api("https://hh.ru/vacancy/66666666")

            assert result is not None
            assert "<p>" not in result.description
            assert len(result.description) == 50000

    @pytest.mark.asyncio
    async def test_special_characters_in_title(self):
        """Test handling of special characters in vacancy title."""
        mock_api_data = {
            "id": 77777777,
            "name": "C++ Developer / Python & JavaScript",
            "description": "Multi-language position",
            "salary": None,
            "area": {"name": "Moscow"},
            "employer": {"name": "TestCorp"},
            "employment": {"id": "full"},
            "experience": {"id": "between3And6"},
            "key_skills": []
        }

        with patch('api.services.hh_api.fetch_vacancy_from_api', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_api_data

            result = await parse_vacancy_via_api("https://hh.ru/vacancy/77777777")

            assert result is not None
            assert result.title == "C++ Developer / Python & JavaScript"

    @pytest.mark.asyncio
    async def test_unicode_in_vacancy(self):
        """Test handling of Unicode characters in vacancy data."""
        mock_api_data = {
            "id": 88888888,
            "name": "Python-Developer",
            "description": "Work with Python data",
            "salary": {"from": 200000, "to": 300000, "currency": "RUR"},
            "area": {"name": "Moscow City"},
            "employer": {"name": "TechCorp LLC"},
            "employment": {"id": "full"},
            "experience": {"id": "between3And6"},
            "key_skills": [{"name": "Python"}, {"name": "FastAPI"}]
        }

        with patch('api.services.hh_api.fetch_vacancy_from_api', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_api_data

            result = await parse_vacancy_via_api("https://hh.ru/vacancy/88888888")

            assert result is not None
            assert "Python" in result.title

    @pytest.mark.asyncio
    async def test_empty_skills_list(self):
        """Test handling of empty skills list."""
        mock_api_data = {
            "id": 99999999,
            "name": "Test Position",
            "description": "No skills required",
            "salary": None,
            "area": {"name": "Remote"},
            "employer": {"name": "TestCorp"},
            "employment": {"id": "full"},
            "experience": {"id": "noExperience"},
            "key_skills": []
        }

        with patch('api.services.hh_api.fetch_vacancy_from_api', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_api_data

            result = await parse_vacancy_via_api("https://hh.ru/vacancy/99999999")

            assert result is not None
            assert result.skills == []

    @pytest.mark.asyncio
    async def test_many_skills(self):
        """Test handling of vacancy with many skills."""
        skills = [{"name": f"Skill{i}"} for i in range(50)]
        mock_api_data = {
            "id": 10101010,
            "name": "Multi-Skill Position",
            "description": "Requires many skills",
            "salary": {"from": 500000, "to": 700000, "currency": "RUR"},
            "area": {"name": "Moscow"},
            "employer": {"name": "BigCorp"},
            "employment": {"id": "full"},
            "experience": {"id": "moreThan6"},
            "key_skills": skills
        }

        with patch('api.services.hh_api.fetch_vacancy_from_api', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_api_data

            result = await parse_vacancy_via_api("https://hh.ru/vacancy/10101010")

            assert result is not None
            assert len(result.skills) == 50
            assert "Skill0" in result.skills
            assert "Skill49" in result.skills
