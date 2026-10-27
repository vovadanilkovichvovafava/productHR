"""
Tests for vacancies API routes - Kanban board and vacancy management.
"""
import pytest
import pytest_asyncio
from datetime import datetime
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import (
    Vacancy, VacancyApplication, VacancyStatus, ApplicationStage,
    Entity, EntityType, EntityStatus, User, Organization, Department
)
from api.services.auth import create_access_token


# ============================================================================
# FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def vacancy(db_session: AsyncSession, organization: Organization, department: Department, admin_user: User) -> Vacancy:
    """Create a test vacancy."""
    vacancy = Vacancy(
        org_id=organization.id,
        department_id=department.id,
        title="Senior Python Developer",
        description="We are looking for an experienced Python developer",
        requirements="5+ years experience with Python, FastAPI, PostgreSQL",
        responsibilities="Develop and maintain backend services",
        salary_min=150000,
        salary_max=250000,
        salary_currency="RUB",
        location="Moscow",
        employment_type="full-time",
        experience_level="senior",
        status=VacancyStatus.open,
        priority=1,
        tags=["python", "backend", "fastapi"],
        hiring_manager_id=admin_user.id,
        created_by=admin_user.id,
        published_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db_session.add(vacancy)
    await db_session.commit()
    await db_session.refresh(vacancy)
    return vacancy


@pytest_asyncio.fixture
async def draft_vacancy(db_session: AsyncSession, organization: Organization, admin_user: User) -> Vacancy:
    """Create a draft vacancy."""
    vacancy = Vacancy(
        org_id=organization.id,
        title="Junior Frontend Developer",
        description="Entry level frontend position",
        status=VacancyStatus.draft,
        created_by=admin_user.id,
        created_at=datetime.utcnow()
    )
    db_session.add(vacancy)
    await db_session.commit()
    await db_session.refresh(vacancy)
    return vacancy


@pytest_asyncio.fixture
async def candidate_for_vacancy(db_session: AsyncSession, organization: Organization, department: Department, admin_user: User) -> Entity:
    """Create a candidate entity for vacancy application."""
    entity = Entity(
        org_id=organization.id,
        department_id=department.id,
        created_by=admin_user.id,
        name="John Developer",
        email="john@example.com",
        phone="+79991234567",
        type=EntityType.candidate,
        status=EntityStatus.new,
        position="Python Developer",
        created_at=datetime.utcnow()
    )
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)
    return entity


@pytest_asyncio.fixture
async def second_candidate(db_session: AsyncSession, organization: Organization, department: Department, admin_user: User) -> Entity:
    """Create a second candidate entity."""
    entity = Entity(
        org_id=organization.id,
        department_id=department.id,
        created_by=admin_user.id,
        name="Jane Smith",
        email="jane@example.com",
        type=EntityType.candidate,
        status=EntityStatus.new,
        created_at=datetime.utcnow()
    )
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)
    return entity


@pytest_asyncio.fixture
async def application(
    db_session: AsyncSession,
    vacancy: Vacancy,
    candidate_for_vacancy: Entity,
    admin_user: User
) -> VacancyApplication:
    """Create a vacancy application."""
    app = VacancyApplication(
        vacancy_id=vacancy.id,
        entity_id=candidate_for_vacancy.id,
        stage=ApplicationStage.applied,
        stage_order=1,
        source="linkedin",
        created_by=admin_user.id,
        applied_at=datetime.utcnow()
    )
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)
    return app


def auth_headers(token: str) -> dict:
    """Create authorization headers with token."""
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# VACANCY CRUD TESTS
# ============================================================================

class TestVacancyCRUD:
    """Tests for vacancy CRUD operations."""

    async def test_list_vacancies_empty(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        org_owner
    ):
        """Test listing vacancies when none exist."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            "/api/vacancies",
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        assert response.json() == []

    async def test_create_vacancy(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        department: Department,
        org_owner
    ):
        """Test creating a new vacancy."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        vacancy_data = {
            "title": "Backend Developer",
            "description": "Build amazing APIs",
            "requirements": "Python, FastAPI",
            "salary_min": 100000,
            "salary_max": 200000,
            "location": "Remote",
            "employment_type": "full-time",
            "experience_level": "middle",
            "status": "open",
            "department_id": department.id,
            "tags": ["python", "api"]
        }
        response = await client.post(
            "/api/vacancies",
            json=vacancy_data,
            headers=auth_headers(token)
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Backend Developer"
        assert data["status"] == "open"
        assert data["salary_min"] == 100000
        assert data["published_at"] is not None  # Should be set when status is open

    async def test_create_draft_vacancy(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        org_owner
    ):
        """Test creating a draft vacancy (not published)."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        vacancy_data = {
            "title": "Draft Position",
            "status": "draft"
        }
        response = await client.post(
            "/api/vacancies",
            json=vacancy_data,
            headers=auth_headers(token)
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "draft"
        assert data["published_at"] is None

    async def test_get_vacancy(
        self,
        client: AsyncClient,
        admin_user: User,
        vacancy: Vacancy,
        org_owner
    ):
        """Test getting a single vacancy."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            f"/api/vacancies/{vacancy.id}",
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == vacancy.id
        assert data["title"] == vacancy.title
        assert "stage_counts" in data

    async def test_get_vacancy_not_found(
        self,
        client: AsyncClient,
        admin_user: User,
        org_owner
    ):
        """Test getting non-existent vacancy."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            "/api/vacancies/99999",
            headers=auth_headers(token)
        )
        assert response.status_code == 404

    async def test_update_vacancy(
        self,
        client: AsyncClient,
        admin_user: User,
        vacancy: Vacancy,
        org_owner
    ):
        """Test updating a vacancy."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        update_data = {
            "title": "Updated Title",
            "salary_max": 300000,
            "priority": 2
        }
        response = await client.put(
            f"/api/vacancies/{vacancy.id}",
            json=update_data,
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"
        assert data["salary_max"] == 300000
        assert data["priority"] == 2

    async def test_update_vacancy_status_to_open(
        self,
        client: AsyncClient,
        admin_user: User,
        draft_vacancy: Vacancy,
        org_owner
    ):
        """Test publishing a draft vacancy (sets published_at)."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.put(
            f"/api/vacancies/{draft_vacancy.id}",
            json={"status": "open"},
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "open"
        assert data["published_at"] is not None

    async def test_delete_vacancy(
        self,
        client: AsyncClient,
        admin_user: User,
        vacancy: Vacancy,
        org_owner
    ):
        """Test deleting a vacancy."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.delete(
            f"/api/vacancies/{vacancy.id}",
            headers=auth_headers(token)
        )
        assert response.status_code == 204

        # Удаление мягкое (deleted_at): вакансия уходит из рабочего списка,
        # но открывается по id и видна в фильтре «Удалённые» — её можно вернуть.
        response = await client.get(
            "/api/vacancies",
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        assert vacancy.id not in [v["id"] for v in response.json()]
        response = await client.get(
            "/api/vacancies?deleted=true",
            headers=auth_headers(token)
        )
        assert vacancy.id in [v["id"] for v in response.json()]

    async def test_list_vacancies_with_filter(
        self,
        client: AsyncClient,
        admin_user: User,
        vacancy: Vacancy,
        draft_vacancy: Vacancy,
        org_owner
    ):
        """Test listing vacancies with status filter."""
        token = create_access_token(data={"sub": str(admin_user.id)})

        # Filter by open status
        response = await client.get(
            "/api/vacancies?status=open",
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["status"] == "open"

        # Filter by draft status
        response = await client.get(
            "/api/vacancies?status=draft",
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["status"] == "draft"

    async def test_search_vacancies(
        self,
        client: AsyncClient,
        admin_user: User,
        vacancy: Vacancy,
        org_owner
    ):
        """Test searching vacancies by title."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            "/api/vacancies?search=Python",
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert "Python" in data[0]["title"]


# ============================================================================
# APPLICATION TESTS
# ============================================================================

class TestVacancyApplications:
    """Tests for vacancy application management."""

    async def test_add_candidate_to_vacancy(
        self,
        client: AsyncClient,
        admin_user: User,
        vacancy: Vacancy,
        candidate_for_vacancy: Entity,
        org_owner
    ):
        """Test adding a candidate to vacancy pipeline."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.post(
            f"/api/vacancies/{vacancy.id}/applications",
            json={
                "vacancy_id": vacancy.id,
                "entity_id": candidate_for_vacancy.id,
                "source": "referral"
            },
            headers=auth_headers(token)
        )
        assert response.status_code == 201
        data = response.json()
        assert data["entity_id"] == candidate_for_vacancy.id
        assert data["stage"] == "applied"
        assert data["source"] == "referral"

    async def test_cannot_add_duplicate_application(
        self,
        client: AsyncClient,
        admin_user: User,
        vacancy: Vacancy,
        candidate_for_vacancy: Entity,
        application: VacancyApplication,
        org_owner
    ):
        """Test that duplicate applications are rejected."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.post(
            f"/api/vacancies/{vacancy.id}/applications",
            json={
                "vacancy_id": vacancy.id,
                "entity_id": candidate_for_vacancy.id
            },
            headers=auth_headers(token)
        )
        assert response.status_code == 400
        # Сообщения сервера теперь по-русски.
        assert "уже добавлен" in response.json()["detail"].lower()

    async def test_list_applications(
        self,
        client: AsyncClient,
        admin_user: User,
        vacancy: Vacancy,
        application: VacancyApplication,
        org_owner
    ):
        """Test listing applications for a vacancy."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            f"/api/vacancies/{vacancy.id}/applications",
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["vacancy_id"] == vacancy.id

    async def test_update_application_stage(
        self,
        client: AsyncClient,
        admin_user: User,
        application: VacancyApplication,
        org_owner
    ):
        """Test moving candidate to next stage."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.put(
            f"/api/vacancies/applications/{application.id}",
            json={"stage": "screening"},
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stage"] == "screening"

    async def test_update_application_rating(
        self,
        client: AsyncClient,
        admin_user: User,
        application: VacancyApplication,
        org_owner
    ):
        """Test adding rating to application."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.put(
            f"/api/vacancies/applications/{application.id}",
            json={"rating": 5, "notes": "Great candidate!"},
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["rating"] == 5
        assert data["notes"] == "Great candidate!"

    async def test_reject_application(
        self,
        client: AsyncClient,
        admin_user: User,
        application: VacancyApplication,
        org_owner
    ):
        """Test rejecting a candidate."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.put(
            f"/api/vacancies/applications/{application.id}",
            json={
                "stage": "rejected",
                "rejection_reason": "Not enough experience"
            },
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stage"] == "rejected"
        assert data["rejection_reason"] == "Not enough experience"

    async def test_delete_application(
        self,
        client: AsyncClient,
        admin_user: User,
        application: VacancyApplication,
        org_owner
    ):
        """Test removing candidate from pipeline."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.delete(
            f"/api/vacancies/applications/{application.id}",
            headers=auth_headers(token)
        )
        assert response.status_code == 204


# ============================================================================
# KANBAN BOARD TESTS
# ============================================================================

class TestKanbanBoard:
    """Tests for Kanban board functionality."""

    async def test_get_kanban_board(
        self,
        client: AsyncClient,
        admin_user: User,
        vacancy: Vacancy,
        application: VacancyApplication,
        org_owner
    ):
        """Test getting Kanban board data."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            f"/api/vacancies/{vacancy.id}/kanban",
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["vacancy_id"] == vacancy.id
        assert data["vacancy_title"] == vacancy.title
        assert "columns" in data
        assert len(data["columns"]) > 0

        # Check that all stages are present
        stages = [col["stage"] for col in data["columns"]]
        assert "applied" in stages
        assert "screening" in stages
        assert "interview" in stages
        assert "hired" in stages
        assert "rejected" in stages

    async def test_kanban_shows_candidates_in_correct_column(
        self,
        client: AsyncClient,
        admin_user: User,
        vacancy: Vacancy,
        application: VacancyApplication,
        org_owner
    ):
        """Test that candidates appear in correct Kanban column."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            f"/api/vacancies/{vacancy.id}/kanban",
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()

        # Find the 'applied' column
        applied_column = next(
            (col for col in data["columns"] if col["stage"] == "applied"),
            None
        )
        assert applied_column is not None
        assert applied_column["count"] >= 1
        assert len(applied_column["applications"]) >= 1

    async def test_bulk_move_applications(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        vacancy: Vacancy,
        candidate_for_vacancy: Entity,
        second_candidate: Entity,
        org_owner
    ):
        """Test moving multiple candidates to a new stage."""
        token = create_access_token(data={"sub": str(admin_user.id)})

        # Create two applications
        app1 = VacancyApplication(
            vacancy_id=vacancy.id,
            entity_id=candidate_for_vacancy.id,
            stage=ApplicationStage.applied,
            created_by=admin_user.id
        )
        app2 = VacancyApplication(
            vacancy_id=vacancy.id,
            entity_id=second_candidate.id,
            stage=ApplicationStage.applied,
            created_by=admin_user.id
        )
        db_session.add_all([app1, app2])
        await db_session.commit()
        await db_session.refresh(app1)
        await db_session.refresh(app2)

        # Bulk move to screening
        response = await client.post(
            "/api/vacancies/applications/bulk-move",
            json={
                "application_ids": [app1.id, app2.id],
                "stage": "screening"
            },
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all(app["stage"] == "screening" for app in data)


# Тест /stats/overview удалён вместе с ручкой (20.10.2026, интерфейс её не звал).


# ============================================================================
# AUTHORIZATION TESTS
# ============================================================================

class TestVacancyAuthorization:
    """Tests for vacancy authorization."""

    async def test_unauthorized_access(self, client: AsyncClient):
        """Test that unauthorized requests are rejected."""
        response = await client.get("/api/vacancies")
        assert response.status_code == 401

    async def test_vacancy_with_stage_counts(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        vacancy: Vacancy,
        candidate_for_vacancy: Entity,
        second_candidate: Entity,
        org_owner
    ):
        """Test that vacancy response includes accurate stage counts."""
        token = create_access_token(data={"sub": str(admin_user.id)})

        # Create applications at different stages
        app1 = VacancyApplication(
            vacancy_id=vacancy.id,
            entity_id=candidate_for_vacancy.id,
            stage=ApplicationStage.applied,
            created_by=admin_user.id
        )
        app2 = VacancyApplication(
            vacancy_id=vacancy.id,
            entity_id=second_candidate.id,
            stage=ApplicationStage.interview,
            created_by=admin_user.id
        )
        db_session.add_all([app1, app2])
        await db_session.commit()

        response = await client.get(
            f"/api/vacancies/{vacancy.id}",
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["applications_count"] == 2
        assert data["stage_counts"]["applied"] == 1
        assert data["stage_counts"]["interview"] == 1


# ============================================================================
# VALIDATION TESTS
# ============================================================================

class TestVacancyValidation:
    """Tests for vacancy schema validation."""

    # === Title Validation ===

    async def test_create_vacancy_title_too_short(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        org_owner
    ):
        """Test that title with less than 3 characters is rejected."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        vacancy_data = {
            "title": "AB",  # Only 2 characters
            "status": "draft"
        }
        response = await client.post(
            "/api/vacancies",
            json=vacancy_data,
            headers=auth_headers(token)
        )
        assert response.status_code == 422
        assert "title must be at least 3 characters" in response.text.lower()

    async def test_create_vacancy_title_empty(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        org_owner
    ):
        """Test that empty title is rejected."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        vacancy_data = {
            "title": "   ",  # Only whitespace
            "status": "draft"
        }
        response = await client.post(
            "/api/vacancies",
            json=vacancy_data,
            headers=auth_headers(token)
        )
        assert response.status_code == 422
        assert "title cannot be empty" in response.text.lower()

    async def test_update_vacancy_title_too_short(
        self,
        client: AsyncClient,
        admin_user: User,
        vacancy: Vacancy,
        org_owner
    ):
        """Test that updating title to less than 3 characters is rejected."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.put(
            f"/api/vacancies/{vacancy.id}",
            json={"title": "AB"},
            headers=auth_headers(token)
        )
        assert response.status_code == 422
        assert "title must be at least 3 characters" in response.text.lower()

    # === Salary Validation ===

    async def test_create_vacancy_negative_salary_min(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        org_owner
    ):
        """Test that negative salary_min is rejected."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        vacancy_data = {
            "title": "Test Position",
            "salary_min": -1000
        }
        response = await client.post(
            "/api/vacancies",
            json=vacancy_data,
            headers=auth_headers(token)
        )
        assert response.status_code == 422
        assert "salary cannot be negative" in response.text.lower()

    async def test_create_vacancy_negative_salary_max(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        org_owner
    ):
        """Test that negative salary_max is rejected."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        vacancy_data = {
            "title": "Test Position",
            "salary_max": -5000
        }
        response = await client.post(
            "/api/vacancies",
            json=vacancy_data,
            headers=auth_headers(token)
        )
        assert response.status_code == 422
        assert "salary cannot be negative" in response.text.lower()

    async def test_create_vacancy_salary_min_greater_than_max(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        org_owner
    ):
        """Test that salary_min > salary_max is rejected."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        vacancy_data = {
            "title": "Test Position",
            "salary_min": 200000,
            "salary_max": 100000
        }
        response = await client.post(
            "/api/vacancies",
            json=vacancy_data,
            headers=auth_headers(token)
        )
        assert response.status_code == 422
        assert "salary_min cannot be greater than salary_max" in response.text.lower()

    async def test_update_vacancy_negative_salary(
        self,
        client: AsyncClient,
        admin_user: User,
        vacancy: Vacancy,
        org_owner
    ):
        """Test that updating to negative salary is rejected."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.put(
            f"/api/vacancies/{vacancy.id}",
            json={"salary_min": -1000},
            headers=auth_headers(token)
        )
        assert response.status_code == 422
        assert "salary cannot be negative" in response.text.lower()

    async def test_update_vacancy_salary_range_invalid(
        self,
        client: AsyncClient,
        admin_user: User,
        vacancy: Vacancy,
        org_owner
    ):
        """Test that updating salary_max below existing salary_min is rejected."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        # vacancy has salary_min=150000, salary_max=250000
        response = await client.put(
            f"/api/vacancies/{vacancy.id}",
            json={"salary_max": 100000},  # Below existing salary_min of 150000
            headers=auth_headers(token)
        )
        assert response.status_code == 422
        assert "salary_min cannot be greater than salary_max" in response.text.lower()

    async def test_update_vacancy_salary_min_above_existing_max(
        self,
        client: AsyncClient,
        admin_user: User,
        vacancy: Vacancy,
        org_owner
    ):
        """Test that updating salary_min above existing salary_max is rejected."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        # vacancy has salary_min=150000, salary_max=250000
        response = await client.put(
            f"/api/vacancies/{vacancy.id}",
            json={"salary_min": 300000},  # Above existing salary_max of 250000
            headers=auth_headers(token)
        )
        assert response.status_code == 422
        assert "salary_min cannot be greater than salary_max" in response.text.lower()

    # === Priority Validation ===

    async def test_create_vacancy_priority_too_low(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        org_owner
    ):
        """Test that priority below 0 is rejected."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        vacancy_data = {
            "title": "Test Position",
            "priority": -1
        }
        response = await client.post(
            "/api/vacancies",
            json=vacancy_data,
            headers=auth_headers(token)
        )
        assert response.status_code == 422
        assert "priority must be between 0 and 2" in response.text.lower()

    async def test_create_vacancy_priority_too_high(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        org_owner
    ):
        """Test that priority above 2 is rejected."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        vacancy_data = {
            "title": "Test Position",
            "priority": 5
        }
        response = await client.post(
            "/api/vacancies",
            json=vacancy_data,
            headers=auth_headers(token)
        )
        assert response.status_code == 422
        assert "priority must be between 0 and 2" in response.text.lower()

    async def test_update_vacancy_invalid_priority(
        self,
        client: AsyncClient,
        admin_user: User,
        vacancy: Vacancy,
        org_owner
    ):
        """Test that updating to invalid priority is rejected."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.put(
            f"/api/vacancies/{vacancy.id}",
            json={"priority": 10},
            headers=auth_headers(token)
        )
        assert response.status_code == 422
        assert "priority must be between 0 and 2" in response.text.lower()

    async def test_create_vacancy_valid_priority_range(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        org_owner
    ):
        """Test that valid priority values (0, 1, 2) are accepted."""
        token = create_access_token(data={"sub": str(admin_user.id)})

        for priority in [0, 1, 2]:
            vacancy_data = {
                "title": f"Test Position Priority {priority}",
                "priority": priority
            }
            response = await client.post(
                "/api/vacancies",
                json=vacancy_data,
                headers=auth_headers(token)
            )
            assert response.status_code == 201
            assert response.json()["priority"] == priority

    # === closes_at Validation ===

    async def test_create_vacancy_closes_at_in_past(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        org_owner
    ):
        """Test that closes_at in the past is rejected."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        from datetime import timedelta
        past_date = (datetime.utcnow() - timedelta(days=7)).isoformat()
        vacancy_data = {
            "title": "Test Position",
            "closes_at": past_date
        }
        response = await client.post(
            "/api/vacancies",
            json=vacancy_data,
            headers=auth_headers(token)
        )
        assert response.status_code == 422
        assert "closes_at cannot be in the past" in response.text.lower()

    async def test_update_vacancy_closes_at_in_past(
        self,
        client: AsyncClient,
        admin_user: User,
        vacancy: Vacancy,
        org_owner
    ):
        """Test that updating closes_at to past date is rejected."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        from datetime import timedelta
        past_date = (datetime.utcnow() - timedelta(days=1)).isoformat()
        response = await client.put(
            f"/api/vacancies/{vacancy.id}",
            json={"closes_at": past_date},
            headers=auth_headers(token)
        )
        assert response.status_code == 422
        assert "closes_at cannot be in the past" in response.text.lower()

    async def test_create_vacancy_closes_at_in_future(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        org_owner
    ):
        """Test that closes_at in the future is accepted."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        from datetime import timedelta
        future_date = (datetime.utcnow() + timedelta(days=30)).isoformat()
        vacancy_data = {
            "title": "Test Position",
            "closes_at": future_date
        }
        response = await client.post(
            "/api/vacancies",
            json=vacancy_data,
            headers=auth_headers(token)
        )
        assert response.status_code == 201
        assert response.json()["closes_at"] is not None

    # === Tags and Extra Data Validation ===

    async def test_create_vacancy_with_null_tags(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        org_owner
    ):
        """Test that null tags is converted to empty list."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        vacancy_data = {
            "title": "Test Position",
            "tags": None
        }
        response = await client.post(
            "/api/vacancies",
            json=vacancy_data,
            headers=auth_headers(token)
        )
        assert response.status_code == 201
        assert response.json()["tags"] == []

    async def test_create_vacancy_with_null_extra_data(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        org_owner
    ):
        """Test that null extra_data is converted to empty dict."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        vacancy_data = {
            "title": "Test Position",
            "extra_data": None
        }
        response = await client.post(
            "/api/vacancies",
            json=vacancy_data,
            headers=auth_headers(token)
        )
        assert response.status_code == 201
        assert response.json()["extra_data"] == {}

    async def test_create_vacancy_invalid_tags_type(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        org_owner
    ):
        """Test that tags with invalid type is rejected."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        vacancy_data = {
            "title": "Test Position",
            "tags": "not_a_list"
        }
        response = await client.post(
            "/api/vacancies",
            json=vacancy_data,
            headers=auth_headers(token)
        )
        assert response.status_code == 422

    async def test_create_vacancy_invalid_extra_data_type(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        org_owner
    ):
        """Test that extra_data with invalid type is rejected."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        vacancy_data = {
            "title": "Test Position",
            "extra_data": "not_a_dict"
        }
        response = await client.post(
            "/api/vacancies",
            json=vacancy_data,
            headers=auth_headers(token)
        )
        assert response.status_code == 422

    async def test_update_vacancy_null_tags_to_empty_list(
        self,
        client: AsyncClient,
        admin_user: User,
        vacancy: Vacancy,
        org_owner
    ):
        """Test that updating tags to null converts to empty list."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        # First verify vacancy has tags
        assert vacancy.tags == ["python", "backend", "fastapi"]

        response = await client.put(
            f"/api/vacancies/{vacancy.id}",
            json={"tags": None},
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        assert response.json()["tags"] == []

    async def test_update_vacancy_null_extra_data_to_empty_dict(
        self,
        client: AsyncClient,
        admin_user: User,
        vacancy: Vacancy,
        org_owner
    ):
        """Test that updating extra_data to null converts to empty dict."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.put(
            f"/api/vacancies/{vacancy.id}",
            json={"extra_data": None},
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        assert response.json()["extra_data"] == {}

    # === Valid Values Tests ===

    async def test_create_vacancy_with_all_valid_values(
        self,
        client: AsyncClient,
        admin_user: User,
        organization: Organization,
        department: Department,
        org_owner
    ):
        """Test creating vacancy with all valid values."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        from datetime import timedelta
        future_date = (datetime.utcnow() + timedelta(days=60)).isoformat()

        vacancy_data = {
            "title": "Senior Developer",
            "description": "Great opportunity",
            "requirements": "5+ years experience",
            "salary_min": 100000,
            "salary_max": 200000,
            "salary_currency": "USD",
            "priority": 2,
            "tags": ["python", "senior", "remote"],
            "extra_data": {"benefits": ["health", "dental"]},
            "closes_at": future_date,
            "department_id": department.id
        }
        response = await client.post(
            "/api/vacancies",
            json=vacancy_data,
            headers=auth_headers(token)
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Senior Developer"
        assert data["salary_min"] == 100000
        assert data["salary_max"] == 200000
        assert data["priority"] == 2
        assert data["tags"] == ["python", "senior", "remote"]
        assert data["extra_data"] == {"benefits": ["health", "dental"]}

    async def test_update_vacancy_valid_salary_range_update(
        self,
        client: AsyncClient,
        admin_user: User,
        vacancy: Vacancy,
        org_owner
    ):
        """Test updating both salary_min and salary_max together."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.put(
            f"/api/vacancies/{vacancy.id}",
            json={"salary_min": 200000, "salary_max": 350000},
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["salary_min"] == 200000
        assert data["salary_max"] == 350000


# ============================================================================
# PAGINATED KANBAN COLUMN TESTS
# ============================================================================

class TestKanbanColumnPagination:
    """Tests for paginated Kanban column endpoint."""

    async def test_get_kanban_column_basic(
        self,
        client: AsyncClient,
        admin_user: User,
        vacancy: Vacancy,
        application: VacancyApplication,
        org_owner
    ):
        """Test getting a specific Kanban column."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            f"/api/vacancies/{vacancy.id}/kanban/column/applied",
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stage"] == "applied"
        # Подпись — из справочника этапов (services/hr_stages.py).
        assert data["title"] == "Новый"
        assert data["count"] >= 1
        assert "applications" in data
        assert "total_count" in data
        assert "has_more" in data

    async def test_get_kanban_column_with_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        vacancy: Vacancy,
        org_owner
    ):
        """Test Kanban column pagination with skip and limit."""
        token = create_access_token(data={"sub": str(admin_user.id)})

        # Create multiple candidates and applications
        for i in range(5):
            entity = Entity(
                org_id=vacancy.org_id,
                created_by=admin_user.id,
                name=f"Candidate {i}",
                email=f"candidate{i}@example.com",
                type=EntityType.candidate,
                status=EntityStatus.new,
                created_at=datetime.utcnow()
            )
            db_session.add(entity)
            await db_session.flush()

            app = VacancyApplication(
                vacancy_id=vacancy.id,
                entity_id=entity.id,
                stage=ApplicationStage.applied,
                stage_order=i + 1,
                created_by=admin_user.id
            )
            db_session.add(app)

        await db_session.commit()

        # Get first page
        response = await client.get(
            f"/api/vacancies/{vacancy.id}/kanban/column/applied?skip=0&limit=2",
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert data["total_count"] == 5
        assert data["has_more"] is True

        # Get second page
        response = await client.get(
            f"/api/vacancies/{vacancy.id}/kanban/column/applied?skip=2&limit=2",
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert data["has_more"] is True

        # Get last page
        response = await client.get(
            f"/api/vacancies/{vacancy.id}/kanban/column/applied?skip=4&limit=2",
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["has_more"] is False

    async def test_get_kanban_column_empty(
        self,
        client: AsyncClient,
        admin_user: User,
        vacancy: Vacancy,
        org_owner
    ):
        """Test getting an empty Kanban column."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            f"/api/vacancies/{vacancy.id}/kanban/column/hired",
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stage"] == "hired"
        assert data["count"] == 0
        assert data["total_count"] == 0
        assert data["has_more"] is False
        assert data["applications"] == []

    async def test_get_kanban_column_vacancy_not_found(
        self,
        client: AsyncClient,
        admin_user: User,
        org_owner
    ):
        """Test getting column for non-existent vacancy."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            "/api/vacancies/99999/kanban/column/applied",
            headers=auth_headers(token)
        )
        assert response.status_code == 404


# ============================================================================
# BULK MOVE ORGANIZATION VALIDATION TESTS
# ============================================================================

class TestBulkMoveOrgValidation:
    """Tests for organization validation in bulk-move endpoint."""

    async def test_bulk_move_validates_vacancy_org(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        vacancy: Vacancy,
        candidate_for_vacancy: Entity,
        second_organization: Organization,
        org_owner
    ):
        """Test that bulk-move validates vacancy belongs to user's org."""
        token = create_access_token(data={"sub": str(admin_user.id)})

        # Create application
        app = VacancyApplication(
            vacancy_id=vacancy.id,
            entity_id=candidate_for_vacancy.id,
            stage=ApplicationStage.applied,
            created_by=admin_user.id
        )
        db_session.add(app)
        await db_session.commit()
        await db_session.refresh(app)

        # Try to bulk move - should work since vacancy is in user's org
        response = await client.post(
            "/api/vacancies/applications/bulk-move",
            json={
                "application_ids": [app.id],
                "stage": "screening"
            },
            headers=auth_headers(token)
        )
        assert response.status_code == 200

    async def test_bulk_move_validates_all_apps_same_vacancy(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        vacancy: Vacancy,
        draft_vacancy: Vacancy,
        candidate_for_vacancy: Entity,
        second_candidate: Entity,
        org_owner
    ):
        """Test that bulk-move validates all applications belong to same vacancy."""
        token = create_access_token(data={"sub": str(admin_user.id)})

        # Create applications for different vacancies
        app1 = VacancyApplication(
            vacancy_id=vacancy.id,
            entity_id=candidate_for_vacancy.id,
            stage=ApplicationStage.applied,
            created_by=admin_user.id
        )
        app2 = VacancyApplication(
            vacancy_id=draft_vacancy.id,
            entity_id=second_candidate.id,
            stage=ApplicationStage.applied,
            created_by=admin_user.id
        )
        db_session.add_all([app1, app2])
        await db_session.commit()
        await db_session.refresh(app1)
        await db_session.refresh(app2)

        # Try to bulk move apps from different vacancies
        response = await client.post(
            "/api/vacancies/applications/bulk-move",
            json={
                "application_ids": [app1.id, app2.id],
                "stage": "screening"
            },
            headers=auth_headers(token)
        )
        assert response.status_code == 400
        assert "same vacancy" in response.json()["detail"].lower()

    async def test_bulk_move_validates_entity_org(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        organization: Organization,
        second_organization: Organization,
        vacancy: Vacancy,
        org_owner
    ):
        """Test that bulk-move validates entity belongs to same org."""
        token = create_access_token(data={"sub": str(admin_user.id)})

        # Create entity in different organization
        cross_org_entity = Entity(
            org_id=second_organization.id,
            created_by=admin_user.id,
            name="Cross Org Candidate",
            email="crossorg@example.com",
            type=EntityType.candidate,
            status=EntityStatus.new,
            created_at=datetime.utcnow()
        )
        db_session.add(cross_org_entity)
        await db_session.flush()

        # Create application with cross-org entity (this simulates data corruption)
        app = VacancyApplication(
            vacancy_id=vacancy.id,
            entity_id=cross_org_entity.id,
            stage=ApplicationStage.applied,
            created_by=admin_user.id
        )
        db_session.add(app)
        await db_session.commit()
        await db_session.refresh(app)

        # Try to bulk move - should fail due to cross-org entity
        response = await client.post(
            "/api/vacancies/applications/bulk-move",
            json={
                "application_ids": [app.id],
                "stage": "screening"
            },
            headers=auth_headers(token)
        )
        assert response.status_code == 403
        assert "does not belong to your organization" in response.json()["detail"]


# ============================================================================
# STAGE ORDER REBALANCE TESTS
# ============================================================================

class TestStageOrderRebalance:
    """Tests for stage_order rebalancing functionality."""

    async def test_update_application_negative_order_triggers_rebalance(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        vacancy: Vacancy,
        candidate_for_vacancy: Entity,
        second_candidate: Entity,
        org_owner
    ):
        """Test that negative stage_order triggers rebalancing."""
        token = create_access_token(data={"sub": str(admin_user.id)})

        # Create applications with positive orders
        app1 = VacancyApplication(
            vacancy_id=vacancy.id,
            entity_id=candidate_for_vacancy.id,
            stage=ApplicationStage.applied,
            stage_order=100,
            created_by=admin_user.id
        )
        app2 = VacancyApplication(
            vacancy_id=vacancy.id,
            entity_id=second_candidate.id,
            stage=ApplicationStage.applied,
            stage_order=200,
            created_by=admin_user.id
        )
        db_session.add_all([app1, app2])
        await db_session.commit()
        await db_session.refresh(app1)
        await db_session.refresh(app2)

        # Update to negative order
        response = await client.put(
            f"/api/vacancies/applications/{app1.id}",
            json={"stage_order": -5},
            headers=auth_headers(token)
        )
        assert response.status_code == 200

        # Verify the order is now positive (rebalanced)
        data = response.json()
        # After rebalance, orders should be positive (1000, 2000, etc.)
        assert data["stage_order"] >= 0

    async def test_bulk_move_uses_proper_order_spacing(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        vacancy: Vacancy,
        candidate_for_vacancy: Entity,
        second_candidate: Entity,
        org_owner
    ):
        """Test that bulk move uses proper order spacing."""
        token = create_access_token(data={"sub": str(admin_user.id)})

        # Create applications
        app1 = VacancyApplication(
            vacancy_id=vacancy.id,
            entity_id=candidate_for_vacancy.id,
            stage=ApplicationStage.applied,
            created_by=admin_user.id
        )
        app2 = VacancyApplication(
            vacancy_id=vacancy.id,
            entity_id=second_candidate.id,
            stage=ApplicationStage.applied,
            created_by=admin_user.id
        )
        db_session.add_all([app1, app2])
        await db_session.commit()
        await db_session.refresh(app1)
        await db_session.refresh(app2)

        # Bulk move to screening
        response = await client.post(
            "/api/vacancies/applications/bulk-move",
            json={
                "application_ids": [app1.id, app2.id],
                "stage": "screening"
            },
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()

        # Verify orders have proper spacing (1000 apart)
        orders = [app["stage_order"] for app in data]
        assert len(orders) == 2
        assert orders[1] - orders[0] == 1000
