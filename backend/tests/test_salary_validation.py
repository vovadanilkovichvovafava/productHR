"""
Tests for salary validation in vacancies.

This module tests:
1. Salary range validation (min <= max)
2. Negative salary values
3. Currency handling
"""
import pytest
import pytest_asyncio
from datetime import datetime
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError

from api.models.database import (
    User, Organization, Department, Vacancy, VacancyStatus
)
from api.services.auth import create_access_token
from api.routes.vacancies import VacancyCreate, VacancyUpdate


# ============================================================================
# FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def salary_test_user(db_session: AsyncSession, organization: Organization) -> User:
    """Create a user for salary validation tests."""
    from api.models.database import UserRole, OrgMember, OrgRole
    from api.services.auth import hash_password

    user = User(
        email="salary_test@test.com",
        password_hash=hash_password("TestPass123"),
        name="Salary Test User",
        role=UserRole.admin,
        is_active=True
    )
    db_session.add(user)
    await db_session.flush()

    # Add to organization as owner
    member = OrgMember(
        org_id=organization.id,
        user_id=user.id,
        role=OrgRole.owner,
        created_at=datetime.utcnow()
    )
    db_session.add(member)
    await db_session.commit()
    await db_session.refresh(user)

    return user


@pytest_asyncio.fixture
async def salary_test_department(db_session: AsyncSession, organization: Organization) -> Department:
    """Create a department for salary tests."""
    dept = Department(
        name="Salary Test Department",
        org_id=organization.id,
        created_at=datetime.utcnow()
    )
    db_session.add(dept)
    await db_session.commit()
    await db_session.refresh(dept)
    return dept


def auth_headers(token: str) -> dict:
    """Create authorization headers with token."""
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# SALARY RANGE VALIDATION TESTS (min <= max)
# ============================================================================

class TestSalaryRangeValidation:
    """Tests for salary_min <= salary_max validation."""

    def test_valid_salary_range(self):
        """Test that valid salary range (min < max) is accepted."""
        vacancy_data = VacancyCreate(
            title="Test Vacancy",
            salary_min=100000,
            salary_max=200000,
            salary_currency="RUB"
        )
        assert vacancy_data.salary_min == 100000
        assert vacancy_data.salary_max == 200000

    def test_equal_min_max_salary(self):
        """Test that equal min and max salary is accepted."""
        vacancy_data = VacancyCreate(
            title="Fixed Salary Vacancy",
            salary_min=150000,
            salary_max=150000,
            salary_currency="RUB"
        )
        assert vacancy_data.salary_min == vacancy_data.salary_max

    def test_min_greater_than_max_rejected(self):
        """Test that salary_min > salary_max is rejected."""
        with pytest.raises(ValueError) as exc_info:
            VacancyCreate(
                title="Invalid Salary Vacancy",
                salary_min=200000,
                salary_max=100000,  # Less than min
                salary_currency="RUB"
            )
        assert "salary_min cannot be greater than salary_max" in str(exc_info.value)

    def test_only_min_salary_valid(self):
        """Test that specifying only min salary is valid."""
        vacancy_data = VacancyCreate(
            title="Min Only Vacancy",
            salary_min=100000,
            salary_max=None,
            salary_currency="RUB"
        )
        assert vacancy_data.salary_min == 100000
        assert vacancy_data.salary_max is None

    def test_only_max_salary_valid(self):
        """Test that specifying only max salary is valid."""
        vacancy_data = VacancyCreate(
            title="Max Only Vacancy",
            salary_min=None,
            salary_max=200000,
            salary_currency="RUB"
        )
        assert vacancy_data.salary_min is None
        assert vacancy_data.salary_max == 200000

    def test_no_salary_valid(self):
        """Test that not specifying any salary is valid."""
        vacancy_data = VacancyCreate(
            title="No Salary Vacancy",
            salary_min=None,
            salary_max=None
        )
        assert vacancy_data.salary_min is None
        assert vacancy_data.salary_max is None

    async def test_api_valid_salary_range(
        self,
        client: AsyncClient,
        salary_test_user: User,
        salary_test_department: Department
    ):
        """Test creating vacancy with valid salary range via API."""
        token = create_access_token(data={"sub": str(salary_test_user.id)})

        response = await client.post(
            "/api/vacancies",
            json={
                "title": "Python Developer",
                "salary_min": 150000,
                "salary_max": 250000,
                "salary_currency": "RUB"
            },
            headers=auth_headers(token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["salary_min"] == 150000
        assert data["salary_max"] == 250000

    async def test_api_invalid_salary_range(
        self,
        client: AsyncClient,
        salary_test_user: User,
        salary_test_department: Department
    ):
        """Test creating vacancy with invalid salary range via API."""
        token = create_access_token(data={"sub": str(salary_test_user.id)})

        response = await client.post(
            "/api/vacancies",
            json={
                "title": "Invalid Salary Vacancy",
                "salary_min": 300000,
                "salary_max": 100000,  # Less than min
                "salary_currency": "RUB"
            },
            headers=auth_headers(token)
        )

        assert response.status_code == 422
        assert "salary" in response.text.lower()


# ============================================================================
# NEGATIVE SALARY VALUES TESTS
# ============================================================================

class TestNegativeSalaryValidation:
    """Tests for negative salary values validation."""

    def test_negative_min_salary_rejected(self):
        """Test that negative salary_min is rejected."""
        with pytest.raises(ValueError) as exc_info:
            VacancyCreate(
                title="Negative Min Vacancy",
                salary_min=-100000,
                salary_max=200000,
                salary_currency="RUB"
            )
        assert "salary cannot be negative" in str(exc_info.value)

    def test_negative_max_salary_rejected(self):
        """Test that negative salary_max is rejected."""
        with pytest.raises(ValueError) as exc_info:
            VacancyCreate(
                title="Negative Max Vacancy",
                salary_min=100000,
                salary_max=-200000,
                salary_currency="RUB"
            )
        assert "salary cannot be negative" in str(exc_info.value)

    def test_both_negative_salaries_rejected(self):
        """Test that both negative salaries are rejected."""
        with pytest.raises(ValueError):
            VacancyCreate(
                title="Both Negative Vacancy",
                salary_min=-100000,
                salary_max=-50000,
                salary_currency="RUB"
            )

    def test_zero_min_salary_valid(self):
        """Test that zero salary_min is valid."""
        vacancy_data = VacancyCreate(
            title="Zero Min Vacancy",
            salary_min=0,
            salary_max=100000,
            salary_currency="RUB"
        )
        assert vacancy_data.salary_min == 0

    def test_zero_max_salary_valid(self):
        """Test that zero salary_max is valid (e.g., for internships)."""
        vacancy_data = VacancyCreate(
            title="Internship",
            salary_min=0,
            salary_max=0,
            salary_currency="RUB"
        )
        assert vacancy_data.salary_max == 0

    async def test_api_negative_min_salary(
        self,
        client: AsyncClient,
        salary_test_user: User,
        salary_test_department: Department
    ):
        """Test creating vacancy with negative min salary via API."""
        token = create_access_token(data={"sub": str(salary_test_user.id)})

        response = await client.post(
            "/api/vacancies",
            json={
                "title": "Negative Min Vacancy",
                "salary_min": -50000,
                "salary_max": 100000,
                "salary_currency": "RUB"
            },
            headers=auth_headers(token)
        )

        assert response.status_code == 422

    async def test_api_negative_max_salary(
        self,
        client: AsyncClient,
        salary_test_user: User,
        salary_test_department: Department
    ):
        """Test creating vacancy with negative max salary via API."""
        token = create_access_token(data={"sub": str(salary_test_user.id)})

        response = await client.post(
            "/api/vacancies",
            json={
                "title": "Negative Max Vacancy",
                "salary_min": 50000,
                "salary_max": -100000,
                "salary_currency": "RUB"
            },
            headers=auth_headers(token)
        )

        assert response.status_code == 422


# ============================================================================
# CURRENCY VALIDATION TESTS
# ============================================================================

class TestCurrencyValidation:
    """Tests for salary currency handling."""

    def test_default_currency_is_rub(self):
        """Test that default currency is RUB."""
        vacancy_data = VacancyCreate(
            title="Default Currency Vacancy",
            salary_min=100000,
            salary_max=200000
        )
        assert vacancy_data.salary_currency == "RUB"

    @pytest.mark.parametrize("currency", ["RUB", "USD", "EUR", "GBP", "CNY"])
    def test_valid_currencies(self, currency):
        """Test various valid currency codes."""
        vacancy_data = VacancyCreate(
            title="Multi Currency Vacancy",
            salary_min=1000,
            salary_max=5000,
            salary_currency=currency
        )
        assert vacancy_data.salary_currency == currency

    def test_currency_preserved_in_response(self):
        """Test that currency is preserved in vacancy data."""
        vacancy_data = VacancyCreate(
            title="USD Vacancy",
            salary_min=5000,
            salary_max=10000,
            salary_currency="USD"
        )
        assert vacancy_data.salary_currency == "USD"

    async def test_api_create_with_usd(
        self,
        client: AsyncClient,
        salary_test_user: User,
        salary_test_department: Department
    ):
        """Test creating vacancy with USD currency via API."""
        token = create_access_token(data={"sub": str(salary_test_user.id)})

        response = await client.post(
            "/api/vacancies",
            json={
                "title": "USD Vacancy",
                "salary_min": 5000,
                "salary_max": 10000,
                "salary_currency": "USD"
            },
            headers=auth_headers(token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["salary_currency"] == "USD"

    async def test_api_create_with_eur(
        self,
        client: AsyncClient,
        salary_test_user: User,
        salary_test_department: Department
    ):
        """Test creating vacancy with EUR currency via API."""
        token = create_access_token(data={"sub": str(salary_test_user.id)})

        response = await client.post(
            "/api/vacancies",
            json={
                "title": "EUR Vacancy",
                "salary_min": 4000,
                "salary_max": 8000,
                "salary_currency": "EUR"
            },
            headers=auth_headers(token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["salary_currency"] == "EUR"

    async def test_api_default_currency_in_response(
        self,
        client: AsyncClient,
        salary_test_user: User,
        salary_test_department: Department
    ):
        """Test that default currency is returned in API response."""
        token = create_access_token(data={"sub": str(salary_test_user.id)})

        response = await client.post(
            "/api/vacancies",
            json={
                "title": "Default Currency Vacancy",
                "salary_min": 100000,
                "salary_max": 200000
            },
            headers=auth_headers(token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["salary_currency"] == "RUB"


# ============================================================================
# UPDATE SALARY VALIDATION TESTS
# ============================================================================

class TestSalaryUpdateValidation:
    """Tests for salary validation on vacancy updates."""

    async def test_update_salary_to_valid_range(
        self,
        db_session: AsyncSession,
        client: AsyncClient,
        salary_test_user: User,
        organization: Organization
    ):
        """Test updating vacancy to valid salary range."""
        # Create vacancy
        vacancy = Vacancy(
            org_id=organization.id,
            title="Update Test Vacancy",
            salary_min=100000,
            salary_max=200000,
            salary_currency="RUB",
            status=VacancyStatus.draft,
            created_by=salary_test_user.id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db_session.add(vacancy)
        await db_session.commit()
        await db_session.refresh(vacancy)

        token = create_access_token(data={"sub": str(salary_test_user.id)})

        # Update to new valid range
        response = await client.put(
            f"/api/vacancies/{vacancy.id}",
            json={
                "salary_min": 150000,
                "salary_max": 300000
            },
            headers=auth_headers(token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["salary_min"] == 150000
        assert data["salary_max"] == 300000

    async def test_update_salary_currency(
        self,
        db_session: AsyncSession,
        client: AsyncClient,
        salary_test_user: User,
        organization: Organization
    ):
        """Test updating vacancy salary currency."""
        # Create vacancy
        vacancy = Vacancy(
            org_id=organization.id,
            title="Currency Update Vacancy",
            salary_min=5000,
            salary_max=10000,
            salary_currency="USD",
            status=VacancyStatus.draft,
            created_by=salary_test_user.id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db_session.add(vacancy)
        await db_session.commit()
        await db_session.refresh(vacancy)

        token = create_access_token(data={"sub": str(salary_test_user.id)})

        # Update currency to EUR
        response = await client.put(
            f"/api/vacancies/{vacancy.id}",
            json={
                "salary_currency": "EUR"
            },
            headers=auth_headers(token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["salary_currency"] == "EUR"


# ============================================================================
# ENTITY EXPECTED SALARY TESTS
# ============================================================================

class TestEntityExpectedSalary:
    """Tests for entity expected salary validation."""

    async def test_entity_salary_min_less_than_max(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token,
        organization: Organization,
        department: Department,
        get_auth_headers,
        org_owner
    ):
        """Test creating entity with valid expected salary range."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "Valid Salary Candidate",
                "expected_salary_min": 100000,
                "expected_salary_max": 200000,
                "expected_salary_currency": "RUB"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["expected_salary_min"] == 100000
        assert data["expected_salary_max"] == 200000

    async def test_entity_expected_salary_currency(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token,
        organization: Organization,
        department: Department,
        get_auth_headers,
        org_owner
    ):
        """Test entity with different salary currency."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "USD Candidate",
                "expected_salary_min": 5000,
                "expected_salary_max": 8000,
                "expected_salary_currency": "USD"
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["expected_salary_currency"] == "USD"

    async def test_entity_default_salary_currency(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_token,
        organization: Organization,
        department: Department,
        get_auth_headers,
        org_owner
    ):
        """Test that entity default currency is RUB."""
        response = await client.post(
            "/api/entities",
            json={
                "type": "candidate",
                "name": "Default Currency Candidate",
                "expected_salary_min": 100000,
                "expected_salary_max": 150000
            },
            headers=get_auth_headers(admin_token)
        )

        assert response.status_code == 201
        data = response.json()
        assert data["expected_salary_currency"] == "RUB"


# ============================================================================
# EDGE CASES
# ============================================================================

class TestSalaryEdgeCases:
    """Tests for edge cases in salary validation."""

    def test_very_large_salary(self):
        """Test that very large salary values are accepted."""
        vacancy_data = VacancyCreate(
            title="Executive Position",
            salary_min=10000000,
            salary_max=50000000,
            salary_currency="RUB"
        )
        assert vacancy_data.salary_min == 10000000
        assert vacancy_data.salary_max == 50000000

    def test_small_salary(self):
        """Test that small salary values are accepted."""
        vacancy_data = VacancyCreate(
            title="Part-time Position",
            salary_min=1,
            salary_max=100,
            salary_currency="USD"
        )
        assert vacancy_data.salary_min == 1
        assert vacancy_data.salary_max == 100

    async def test_get_vacancy_includes_salary(
        self,
        db_session: AsyncSession,
        client: AsyncClient,
        salary_test_user: User,
        organization: Organization
    ):
        """Test that GET vacancy includes salary information."""
        # Create vacancy with salary
        vacancy = Vacancy(
            org_id=organization.id,
            title="Salary Info Vacancy",
            salary_min=150000,
            salary_max=250000,
            salary_currency="RUB",
            status=VacancyStatus.open,
            created_by=salary_test_user.id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db_session.add(vacancy)
        await db_session.commit()
        await db_session.refresh(vacancy)

        token = create_access_token(data={"sub": str(salary_test_user.id)})

        response = await client.get(
            f"/api/vacancies/{vacancy.id}",
            headers=auth_headers(token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data["salary_min"] == 150000
        assert data["salary_max"] == 250000
        assert data["salary_currency"] == "RUB"

    async def test_list_vacancies_includes_salary(
        self,
        db_session: AsyncSession,
        client: AsyncClient,
        salary_test_user: User,
        organization: Organization
    ):
        """Test that vacancy list includes salary information."""
        # Create vacancy with salary
        vacancy = Vacancy(
            org_id=organization.id,
            title="Listed Vacancy",
            salary_min=100000,
            salary_max=200000,
            salary_currency="EUR",
            status=VacancyStatus.open,
            created_by=salary_test_user.id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db_session.add(vacancy)
        await db_session.commit()
        await db_session.refresh(vacancy)

        token = create_access_token(data={"sub": str(salary_test_user.id)})

        response = await client.get(
            "/api/vacancies",
            headers=auth_headers(token)
        )

        assert response.status_code == 200
        data = response.json()

        # Find our vacancy
        found_vacancy = next((v for v in data if v["id"] == vacancy.id), None)
        assert found_vacancy is not None
        assert found_vacancy["salary_min"] == 100000
        assert found_vacancy["salary_max"] == 200000
        assert found_vacancy["salary_currency"] == "EUR"
