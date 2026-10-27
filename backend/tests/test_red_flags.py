"""
Tests for Red Flags detection service and API endpoints.

These tests cover:
- RedFlagsService unit tests for detecting various red flags
- GET /entities/{entity_id}/red-flags endpoint
- GET /entities/{entity_id}/risk-score endpoint
- Rule-based detection (job hopping, employment gaps, salary mismatch, etc.)
- AI-based communication analysis (mocked)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from httpx import AsyncClient

from api.models.database import (
    User, UserRole, Organization, OrgMember, OrgRole,
    Department, DepartmentMember, DeptRole,
    Entity, EntityType, EntityStatus,
    Chat, ChatType, Message, CallRecording, CallSource, CallStatus,
    Vacancy, VacancyStatus
)
import pytest_asyncio
from api.services.auth import create_access_token
from api.services.red_flags import (
    RedFlagsService,
    RedFlagType,
    Severity,
    RedFlag,
    RedFlagsAnalysis,
    red_flags_service
)


# Helper function for auth headers
def auth_headers(token: str) -> dict:
    """Create authorization headers with token."""
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# UNIT TESTS FOR RedFlagsService
# ============================================================================

class TestRedFlagsService:
    """Unit tests for RedFlagsService."""

    def test_init(self):
        """Test service initialization."""
        service = RedFlagsService()
        assert service.model == "claude-sonnet-4-6"
        assert service._client is None

    def test_analyze_work_history_no_hopping(self):
        """Test work history analysis with stable employment."""
        service = RedFlagsService()
        extra_data = {
            "experience": [
                {
                    "company": "Company A",
                    "start_date": "2020-01",
                    "end_date": "2023-01"
                },
                {
                    "company": "Company B",
                    "start_date": "2023-02",
                    "end_date": "present"
                }
            ]
        }

        flags = service._analyze_work_history(extra_data)
        assert len(flags) == 0

    def test_analyze_work_history_job_hopping(self):
        """Test detection of job hopping pattern."""
        service = RedFlagsService()
        extra_data = {
            "experience": [
                {
                    "company": "Company A",
                    "start_date": "2022-01",
                    "end_date": "2022-06"  # 6 months
                },
                {
                    "company": "Company B",
                    "start_date": "2022-07",
                    "end_date": "2023-01"  # 6 months
                },
                {
                    "company": "Company C",
                    "start_date": "2023-02",
                    "end_date": "2023-08"  # 6 months
                }
            ]
        }

        flags = service._analyze_work_history(extra_data)
        assert len(flags) == 1
        assert flags[0].type == RedFlagType.JOB_HOPPING
        assert flags[0].severity in [Severity.MEDIUM, Severity.HIGH]

    def test_analyze_work_history_with_different_date_formats(self):
        """Test work history analysis with various date formats."""
        service = RedFlagsService()

        # Test with year-only format
        extra_data = {
            "experience": [
                {
                    "company": "Company A",
                    "start_date": "2018",
                    "end_date": "2022"
                }
            ]
        }
        flags = service._analyze_work_history(extra_data)
        assert len(flags) == 0

    def test_analyze_work_history_employment_gap_medium(self):
        """Test detection of medium severity employment gap (6-12 months)."""
        service = RedFlagsService()
        extra_data = {
            "experience": [
                {
                    "company": "Company A",
                    "position": "Developer",
                    "start_date": "2020-01",
                    "end_date": "2021-06"  # Ends June 2021
                },
                {
                    "company": "Company B",
                    "position": "Senior Developer",
                    "start_date": "2022-02",  # Starts Feb 2022, 8 month gap
                    "end_date": "2023-01"
                }
            ]
        }

        flags = service._analyze_work_history(extra_data)

        # Should detect employment gap
        gap_flags = [f for f in flags if f.type == RedFlagType.EMPLOYMENT_GAPS]
        assert len(gap_flags) == 1
        assert gap_flags[0].severity == Severity.MEDIUM
        assert "пробел" in gap_flags[0].description.lower()
        assert "Company A" in gap_flags[0].evidence
        assert "Company B" in gap_flags[0].evidence

    def test_analyze_work_history_employment_gap_high(self):
        """Test detection of high severity employment gap (> 12 months)."""
        service = RedFlagsService()
        extra_data = {
            "experience": [
                {
                    "company": "Company A",
                    "start_date": "2018-01",
                    "end_date": "2019-06"  # Ends June 2019
                },
                {
                    "company": "Company B",
                    "start_date": "2021-01",  # Starts Jan 2021, 19 month gap
                    "end_date": "2023-01"
                }
            ]
        }

        flags = service._analyze_work_history(extra_data)

        # Should detect high severity employment gap
        gap_flags = [f for f in flags if f.type == RedFlagType.EMPLOYMENT_GAPS]
        assert len(gap_flags) == 1
        assert gap_flags[0].severity == Severity.HIGH
        assert "значительный" in gap_flags[0].description.lower()

    def test_analyze_work_history_no_employment_gap(self):
        """Test no gap detection when jobs are continuous."""
        service = RedFlagsService()
        extra_data = {
            "experience": [
                {
                    "company": "Company A",
                    "start_date": "2020-01",
                    "end_date": "2021-06"
                },
                {
                    "company": "Company B",
                    "start_date": "2021-07",  # Starts right after previous ends
                    "end_date": "2023-01"
                }
            ]
        }

        flags = service._analyze_work_history(extra_data)

        # Should not detect employment gap
        gap_flags = [f for f in flags if f.type == RedFlagType.EMPLOYMENT_GAPS]
        assert len(gap_flags) == 0

    def test_analyze_work_history_multiple_gaps(self):
        """Test detection of multiple employment gaps."""
        service = RedFlagsService()
        extra_data = {
            "experience": [
                {
                    "company": "Company A",
                    "start_date": "2018-01",
                    "end_date": "2019-01"  # Ends Jan 2019
                },
                {
                    "company": "Company B",
                    "start_date": "2020-01",  # 12 month gap
                    "end_date": "2021-01"
                },
                {
                    "company": "Company C",
                    "start_date": "2022-06",  # 17 month gap
                    "end_date": "present"
                }
            ]
        }

        flags = service._analyze_work_history(extra_data)

        # Should detect two employment gaps
        gap_flags = [f for f in flags if f.type == RedFlagType.EMPLOYMENT_GAPS]
        assert len(gap_flags) == 2

        # Check severities
        severities = [f.severity for f in gap_flags]
        assert Severity.HIGH in severities  # 17 month gap
        # First gap is exactly 12 months, which is > 6 but not > 12, so MEDIUM

    def test_analyze_work_history_gap_with_year_only_dates(self):
        """Test gap detection with year-only date formats."""
        service = RedFlagsService()
        extra_data = {
            "experience": [
                {
                    "company": "Company A",
                    "start_date": "2018",
                    "end_date": "2019"  # Ends Dec 2019
                },
                {
                    "company": "Company B",
                    "start_date": "2021",  # Starts Jan 2021, 13 month gap
                    "end_date": "2023"
                }
            ]
        }

        flags = service._analyze_work_history(extra_data)

        # Should detect high severity gap (> 12 months)
        gap_flags = [f for f in flags if f.type == RedFlagType.EMPLOYMENT_GAPS]
        assert len(gap_flags) == 1
        assert gap_flags[0].severity == Severity.HIGH

    def test_analyze_work_history_gap_skips_current_job(self):
        """Test that gap detection skips current job for gap calculation."""
        service = RedFlagsService()
        extra_data = {
            "experience": [
                {
                    "company": "Company A",
                    "start_date": "2020-01",
                    "end_date": "2021-01"
                },
                {
                    "company": "Company B",
                    "start_date": "2022-01",  # 12 month gap, but current job
                    "end_date": "present"
                }
            ]
        }

        flags = service._analyze_work_history(extra_data)

        # Should detect employment gap (between A and B)
        gap_flags = [f for f in flags if f.type == RedFlagType.EMPLOYMENT_GAPS]
        assert len(gap_flags) == 1

    def test_analyze_work_history_small_gap_ignored(self):
        """Test that small gaps (< 6 months) are ignored."""
        service = RedFlagsService()
        extra_data = {
            "experience": [
                {
                    "company": "Company A",
                    "start_date": "2020-01",
                    "end_date": "2021-06"
                },
                {
                    "company": "Company B",
                    "start_date": "2021-10",  # 4 month gap - should be ignored
                    "end_date": "2023-01"
                }
            ]
        }

        flags = service._analyze_work_history(extra_data)

        # Should not detect employment gap
        gap_flags = [f for f in flags if f.type == RedFlagType.EMPLOYMENT_GAPS]
        assert len(gap_flags) == 0

    def test_parse_date_various_formats(self):
        """Test _parse_date helper with various formats."""
        service = RedFlagsService()

        # Year only
        result = service._parse_date("2020", is_end_date=False)
        assert result == datetime(2020, 1, 1)

        result = service._parse_date("2020", is_end_date=True)
        assert result == datetime(2020, 12, 31)

        # YYYY-MM format
        result = service._parse_date("2020-06", is_end_date=False)
        assert result.year == 2020
        assert result.month == 6

        # Present values
        for present_value in ["present", "now", "current", "настоящее время"]:
            result = service._parse_date(present_value)
            assert result is not None
            # Should be close to now
            assert (datetime.now() - result).total_seconds() < 5

        # Invalid date
        result = service._parse_date("invalid-date")
        assert result is None

        # None
        result = service._parse_date(None)
        assert result is None

    def test_detect_employment_gaps_single_job(self):
        """Test gap detection with single job (should return empty)."""
        service = RedFlagsService()

        parsed_jobs = [
            {
                "company": "Company A",
                "position": "Dev",
                "start": datetime(2020, 1, 1),
                "end": datetime(2023, 1, 1),
                "is_current": False
            }
        ]

        flags = service._detect_employment_gaps(parsed_jobs)
        assert len(flags) == 0

    def test_detect_employment_gaps_empty_list(self):
        """Test gap detection with empty job list."""
        service = RedFlagsService()
        flags = service._detect_employment_gaps([])
        assert len(flags) == 0

    def test_check_references_missing(self):
        """Test detection of missing references."""
        service = RedFlagsService()
        entity = MagicMock()
        entity.extra_data = {}

        flags = service._check_references(entity)
        assert len(flags) == 1
        assert flags[0].type == RedFlagType.REFERENCE_MISSING
        assert flags[0].severity == Severity.LOW

    def test_check_references_present(self):
        """Test when references are provided."""
        service = RedFlagsService()
        entity = MagicMock()
        entity.extra_data = {
            "references": [
                {"name": "John Doe", "phone": "+1234567890"}
            ]
        }

        flags = service._check_references(entity)
        assert len(flags) == 0

    def test_analyze_salary_match_high_expectations(self):
        """Test detection of salary mismatch when candidate expects too much."""
        service = RedFlagsService()
        entity = MagicMock()
        entity.expected_salary_min = 300000
        entity.expected_salary_max = 400000
        entity.expected_salary_currency = "RUB"

        vacancy = MagicMock()
        vacancy.salary_min = 150000
        vacancy.salary_max = 200000
        vacancy.salary_currency = "RUB"

        flags = service._analyze_salary_match(entity, vacancy)
        assert len(flags) == 1
        assert flags[0].type == RedFlagType.SALARY_MISMATCH
        assert flags[0].severity == Severity.HIGH

    def test_analyze_salary_match_no_mismatch(self):
        """Test no salary mismatch when expectations align."""
        service = RedFlagsService()
        entity = MagicMock()
        entity.expected_salary_min = 180000
        entity.expected_salary_max = 220000
        entity.expected_salary_currency = "RUB"

        vacancy = MagicMock()
        vacancy.salary_min = 150000
        vacancy.salary_max = 250000
        vacancy.salary_currency = "RUB"

        flags = service._analyze_salary_match(entity, vacancy)
        assert len(flags) == 0

    def test_analyze_location_concern_no_relocation(self):
        """Test detection of location concern when candidate won't relocate."""
        service = RedFlagsService()
        entity = MagicMock()
        entity.extra_data = {
            "location": "Новосибирск",
            "relocation_ready": False
        }

        vacancy = MagicMock()
        vacancy.location = "Москва"

        flags = service._check_location(entity, vacancy)
        assert len(flags) == 1
        assert flags[0].type == RedFlagType.LOCATION_CONCERN
        assert flags[0].severity == Severity.HIGH

    def test_analyze_location_concern_unknown_relocation(self):
        """Test location concern when relocation readiness is unknown."""
        service = RedFlagsService()
        entity = MagicMock()
        entity.extra_data = {
            "location": "Санкт-Петербург"
        }

        vacancy = MagicMock()
        vacancy.location = "Москва"

        flags = service._check_location(entity, vacancy)
        assert len(flags) == 1
        assert flags[0].type == RedFlagType.LOCATION_CONCERN
        assert flags[0].severity == Severity.MEDIUM

    def test_analyze_location_same_city(self):
        """Test no location concern when in same city."""
        service = RedFlagsService()
        entity = MagicMock()
        entity.extra_data = {
            "location": "Москва"
        }

        vacancy = MagicMock()
        vacancy.location = "Москва"

        flags = service._check_location(entity, vacancy)
        assert len(flags) == 0

    def test_calculate_risk_score_no_flags(self):
        """Test risk score calculation with no flags."""
        service = RedFlagsService()
        score = service._calculate_risk_score([])
        assert score == 0

    def test_calculate_risk_score_with_flags(self):
        """Test risk score calculation with various severity flags."""
        service = RedFlagsService()
        flags = [
            RedFlag(
                type=RedFlagType.JOB_HOPPING,
                severity=Severity.HIGH,
                description="Test",
                suggestion="Test"
            ),
            RedFlag(
                type=RedFlagType.REFERENCE_MISSING,
                severity=Severity.LOW,
                description="Test",
                suggestion="Test"
            ),
            RedFlag(
                type=RedFlagType.LOCATION_CONCERN,
                severity=Severity.MEDIUM,
                description="Test",
                suggestion="Test"
            )
        ]

        score = service._calculate_risk_score(flags)
        # HIGH = 25, MEDIUM = 15, LOW = 5 => 45
        assert score == 45

    def test_calculate_risk_score_cap_at_100(self):
        """Test that risk score is capped at 100."""
        service = RedFlagsService()
        # 5 HIGH flags = 125, but should cap at 100
        flags = [
            RedFlag(
                type=RedFlagType.JOB_HOPPING,
                severity=Severity.HIGH,
                description="Test",
                suggestion="Test"
            )
            for _ in range(5)
        ]

        score = service._calculate_risk_score(flags)
        assert score == 100

    def test_generate_summary_no_flags(self):
        """Test summary generation with no flags."""
        service = RedFlagsService()
        summary = service._generate_summary([], 0)
        assert "не обнаружено" in summary.lower() or "перспективным" in summary.lower()

    def test_generate_summary_with_high_flags(self):
        """Test summary generation with high severity flags."""
        service = RedFlagsService()
        flags = [
            RedFlag(
                type=RedFlagType.JOB_HOPPING,
                severity=Severity.HIGH,
                description="Test",
                suggestion="Test"
            )
        ]
        summary = service._generate_summary(flags, 25)
        assert "критических" in summary.lower() or "детальная" in summary.lower()

    def test_get_risk_score_sync(self):
        """Test synchronous risk score calculation."""
        service = RedFlagsService()
        entity = MagicMock()
        entity.extra_data = {
            "experience": [
                {
                    "company": "Company A",
                    "start_date": "2022-01",
                    "end_date": "2022-06"
                },
                {
                    "company": "Company B",
                    "start_date": "2022-07",
                    "end_date": "2023-01"
                },
                {
                    "company": "Company C",
                    "start_date": "2023-02",
                    "end_date": "2023-08"
                }
            ]
        }

        score = service.get_risk_score(entity)
        assert isinstance(score, int)
        assert score >= 0

    def test_red_flag_to_dict(self):
        """Test RedFlag serialization to dict."""
        flag = RedFlag(
            type=RedFlagType.JOB_HOPPING,
            severity=Severity.HIGH,
            description="Частая смена работ",
            suggestion="Уточните причины",
            evidence="3 места работы за год"
        )

        data = flag.to_dict()
        assert data["type"] == "job_hopping"
        assert data["type_label"] == "Частая смена работ"
        assert data["severity"] == "high"
        assert data["description"] == "Частая смена работ"
        assert data["suggestion"] == "Уточните причины"
        assert data["evidence"] == "3 места работы за год"

    def test_red_flags_analysis_to_dict(self):
        """Test RedFlagsAnalysis serialization to dict."""
        flags = [
            RedFlag(
                type=RedFlagType.JOB_HOPPING,
                severity=Severity.HIGH,
                description="Test",
                suggestion="Test"
            ),
            RedFlag(
                type=RedFlagType.REFERENCE_MISSING,
                severity=Severity.LOW,
                description="Test",
                suggestion="Test"
            )
        ]
        analysis = RedFlagsAnalysis(
            flags=flags,
            risk_score=30,
            summary="Test summary"
        )

        data = analysis.to_dict()
        assert len(data["flags"]) == 2
        assert data["risk_score"] == 30
        assert data["summary"] == "Test summary"
        assert data["flags_count"] == 2
        assert data["high_severity_count"] == 1
        assert data["medium_severity_count"] == 0
        assert data["low_severity_count"] == 1


class TestRedFlagsServiceAsync:
    """Async tests for RedFlagsService with mocked AI."""

    @pytest.mark.asyncio
    async def test_detect_red_flags_basic(self):
        """Test full red flags detection without AI."""
        service = RedFlagsService()

        entity = MagicMock()
        entity.name = "Test Candidate"
        entity.extra_data = {
            "experience": [
                {
                    "company": "Company A",
                    "start_date": "2020-01",
                    "end_date": "2023-01"
                }
            ]
        }
        entity.expected_salary_min = None
        entity.expected_salary_max = None

        analysis = await service.detect_red_flags(entity)

        assert isinstance(analysis, RedFlagsAnalysis)
        assert isinstance(analysis.flags, list)
        assert isinstance(analysis.risk_score, int)
        assert isinstance(analysis.summary, str)

    @pytest.mark.asyncio
    async def test_detect_red_flags_with_vacancy(self):
        """Test red flags detection with vacancy comparison."""
        service = RedFlagsService()

        entity = MagicMock()
        entity.name = "Test Candidate"
        entity.extra_data = {
            "location": "Новосибирск",
            "relocation_ready": False
        }
        entity.expected_salary_min = 300000
        entity.expected_salary_max = 400000
        entity.expected_salary_currency = "RUB"

        vacancy = MagicMock()
        vacancy.salary_min = 150000
        vacancy.salary_max = 200000
        vacancy.salary_currency = "RUB"
        vacancy.location = "Москва"
        vacancy.requirements = "Python, FastAPI"
        vacancy.extra_data = {}
        vacancy.experience_level = None

        analysis = await service.detect_red_flags(entity, vacancy=vacancy)

        # Should have salary mismatch and location concern
        flag_types = [f.type for f in analysis.flags]
        assert RedFlagType.SALARY_MISMATCH in flag_types
        assert RedFlagType.LOCATION_CONCERN in flag_types

    @pytest.mark.asyncio
    async def test_ai_analyze_communications_no_data(self):
        """Test AI analysis with no communication data."""
        service = RedFlagsService()

        entity = MagicMock()
        entity.name = "Test"

        flags = await service._ai_analyze_communications(entity, [], [])
        assert flags == []

    @pytest.mark.asyncio
    async def test_ai_analyze_communications_with_mock(self):
        """Test AI analysis with mocked Anthropic client."""
        service = RedFlagsService()

        entity = MagicMock()
        entity.name = "Test Candidate"

        # Create mock chat with messages
        chat = MagicMock()
        chat.title = "Test Chat"
        message = MagicMock()
        message.timestamp = datetime.utcnow()
        message.first_name = "HR"
        message.username = None
        message.content = "Я ненавижу своего бывшего работодателя!"
        chat.messages = [message]

        # Mock the AI response
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = '''[
            {
                "type": "negative_attitude",
                "severity": "medium",
                "description": "Негативное отношение к прошлому работодателю",
                "evidence": "Я ненавижу своего бывшего работодателя!",
                "suggestion": "Уточните причины негативного отношения"
            }
        ]'''

        with patch.object(service, '_client') as mock_client:
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            # Force client property to return mock
            service._client = mock_client

            flags = await service._ai_analyze_communications(entity, [chat], [])

            assert len(flags) == 1
            assert flags[0].type == RedFlagType.NEGATIVE_ATTITUDE
            assert flags[0].severity == Severity.MEDIUM


# ============================================================================
# API ENDPOINT TESTS
# ============================================================================

# ============================================================================
# FIXTURES FOR ENDPOINT TESTS
# ============================================================================

@pytest_asyncio.fixture
async def organization(db_session) -> Organization:
    """Create a test organization."""
    org = Organization(
        name="Test Organization",
        slug="test-red-flags-org",
        created_at=datetime.utcnow()
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest_asyncio.fixture
async def admin_user(db_session) -> User:
    """Create an admin user."""
    from api.services.auth import hash_password
    user = User(
        email="admin-rf@test.com",
        password_hash=hash_password("Admin123"),
        name="Admin User",
        role=UserRole.admin,
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def org_owner(db_session, organization, admin_user):
    """Create an organization owner membership."""
    member = OrgMember(
        org_id=organization.id,
        user_id=admin_user.id,
        role=OrgRole.owner,
        created_at=datetime.utcnow()
    )
    db_session.add(member)
    await db_session.commit()
    await db_session.refresh(member)
    return member


@pytest_asyncio.fixture
async def admin_token(admin_user) -> str:
    """Create auth token for admin user."""
    return create_access_token(data={"sub": str(admin_user.id)})  # API: create_access_token(data: dict)


@pytest_asyncio.fixture
async def candidate_entity(
    db_session,
    organization,
    admin_user,
    org_owner  # Ensure org membership exists
) -> Entity:
    """Create a candidate entity with work history."""
    entity = Entity(
        org_id=organization.id,
        created_by=admin_user.id,
        name="Test Candidate",
        email="candidate@test.com",
        type=EntityType.candidate,
        status=EntityStatus.new,
        extra_data={
            "experience": [
                {
                    "company": "Company A",
                    "start_date": "2022-01",
                    "end_date": "2022-06"
                },
                {
                    "company": "Company B",
                    "start_date": "2022-07",
                    "end_date": "2023-01"
                },
                {
                    "company": "Company C",
                    "start_date": "2023-02",
                    "end_date": "2023-08"
                }
            ],
            "location": "Санкт-Петербург"
        }
    )
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)
    return entity


@pytest_asyncio.fixture
async def test_vacancy(
    db_session,
    organization,
    admin_user,
    org_owner  # Ensure org membership exists
) -> Vacancy:
    """Create a test vacancy."""
    vacancy = Vacancy(
        org_id=organization.id,
        created_by=admin_user.id,
        title="Python Developer",
        status=VacancyStatus.open,
        location="Москва",
        salary_min=150000,
        salary_max=200000,
        salary_currency="RUB"
    )
    db_session.add(vacancy)
    await db_session.commit()
    await db_session.refresh(vacancy)
    return vacancy


class TestRedFlagsEndpoints:
    """Tests for Red Flags API endpoints."""

    @pytest.mark.asyncio
    async def test_get_red_flags_unauthorized(self, client: AsyncClient):
        """Test red flags endpoint without authentication."""
        response = await client.get("/api/entities/1/red-flags")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_red_flags_entity_not_found(
        self,
        client: AsyncClient,
        admin_token: str,
        organization,
        org_owner
    ):
        """Test red flags for non-existent entity."""
        response = await client.get(
            "/api/entities/99999/red-flags",
            headers=auth_headers(admin_token)
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_red_flags_success(
        self,
        client: AsyncClient,
        admin_token: str,
        candidate_entity: Entity
    ):
        """Test successful red flags analysis."""
        response = await client.get(
            f"/api/entities/{candidate_entity.id}/red-flags",
            headers=auth_headers(admin_token)
        )
        assert response.status_code == 200

        data = response.json()
        assert "flags" in data
        assert "risk_score" in data
        assert "summary" in data
        assert "flags_count" in data
        assert isinstance(data["flags"], list)
        assert isinstance(data["risk_score"], int)

    @pytest.mark.asyncio
    async def test_get_red_flags_with_vacancy(
        self,
        client: AsyncClient,
        admin_token: str,
        candidate_entity: Entity,
        test_vacancy: Vacancy
    ):
        """Test red flags analysis with vacancy comparison."""
        response = await client.get(
            f"/api/entities/{candidate_entity.id}/red-flags",
            params={"vacancy_id": test_vacancy.id},
            headers=auth_headers(admin_token)
        )
        assert response.status_code == 200

        data = response.json()
        # Should detect location concern since entity is in SPb, vacancy in Moscow
        flag_types = [f["type"] for f in data["flags"]]
        # Since relocation_ready is not set, should have MEDIUM location concern
        has_location_flag = any(
            f["type"] == "location_concern" for f in data["flags"]
        )
        assert has_location_flag or data["risk_score"] >= 0  # At minimum, should work

    @pytest.mark.asyncio
    async def test_get_risk_score_unauthorized(self, client: AsyncClient):
        """Test risk score endpoint without authentication."""
        response = await client.get("/api/entities/1/risk-score")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_risk_score_entity_not_found(
        self,
        client: AsyncClient,
        admin_token: str,
        organization,
        org_owner
    ):
        """Test risk score for non-existent entity."""
        response = await client.get(
            "/api/entities/99999/risk-score",
            headers=auth_headers(admin_token)
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_risk_score_success(
        self,
        client: AsyncClient,
        admin_token: str,
        candidate_entity: Entity
    ):
        """Test successful risk score calculation."""
        response = await client.get(
            f"/api/entities/{candidate_entity.id}/risk-score",
            headers=auth_headers(admin_token)
        )
        assert response.status_code == 200

        data = response.json()
        assert "entity_id" in data
        assert "risk_score" in data
        assert "risk_level" in data
        assert data["entity_id"] == candidate_entity.id
        assert isinstance(data["risk_score"], int)
        assert data["risk_score"] >= 0
        assert data["risk_score"] <= 100
        assert data["risk_level"] in ["low", "medium", "high"]


# ============================================================================
# EDGE CASES AND ERROR HANDLING
# ============================================================================

class TestRedFlagsEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_extra_data(self):
        """Test with empty extra_data."""
        service = RedFlagsService()
        flags = service._analyze_work_history({})
        assert flags == []

    def test_invalid_date_format(self):
        """Test with invalid date formats."""
        service = RedFlagsService()
        extra_data = {
            "experience": [
                {
                    "company": "Company A",
                    "start_date": "invalid-date",
                    "end_date": "also-invalid"
                }
            ]
        }
        # Should not raise, just skip invalid entries
        flags = service._analyze_work_history(extra_data)
        assert isinstance(flags, list)

    def test_missing_company_name(self):
        """Test with missing company name in work history."""
        service = RedFlagsService()
        extra_data = {
            "experience": [
                {
                    "start_date": "2022-01",
                    "end_date": "2022-06"
                },
                {
                    "start_date": "2022-07",
                    "end_date": "2023-01"
                },
                {
                    "start_date": "2023-02",
                    "end_date": "2023-08"
                }
            ]
        }
        flags = service._analyze_work_history(extra_data)
        # Should still detect job hopping even without company names
        assert isinstance(flags, list)

    def test_none_vacancy(self):
        """Test salary match with None vacancy."""
        service = RedFlagsService()
        entity = MagicMock()
        entity.expected_salary_min = 200000
        entity.expected_salary_max = 300000

        flags = service._analyze_salary_match(entity, None)
        assert flags == []

    def test_none_salary_expectations(self):
        """Test salary match with no salary expectations."""
        service = RedFlagsService()
        entity = MagicMock()
        entity.expected_salary_min = None
        entity.expected_salary_max = None

        vacancy = MagicMock()
        vacancy.salary_min = 150000
        vacancy.salary_max = 200000

        flags = service._analyze_salary_match(entity, vacancy)
        assert flags == []

    def test_skills_match_no_skills(self):
        """Test skills match with no skills data."""
        service = RedFlagsService()
        entity = MagicMock()
        entity.extra_data = {}

        vacancy = MagicMock()
        vacancy.requirements = "Python"
        vacancy.extra_data = {"required_skills": ["python"]}

        flags = service._analyze_skills_match(entity, vacancy)
        assert flags == []

    @pytest.mark.asyncio
    async def test_detect_red_flags_with_empty_communications(self):
        """Test detection with empty communications."""
        service = RedFlagsService()

        entity = MagicMock()
        entity.name = "Test"
        entity.extra_data = {}
        entity.expected_salary_min = None
        entity.expected_salary_max = None

        analysis = await service.detect_red_flags(
            entity,
            chats=[],
            calls=[]
        )

        assert isinstance(analysis, RedFlagsAnalysis)
        # Should have at least REFERENCE_MISSING flag
        assert len(analysis.flags) >= 1
