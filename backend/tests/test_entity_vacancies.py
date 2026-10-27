"""
Tests for entity-vacancy integration API routes.
"""
import pytest
import pytest_asyncio
from datetime import datetime
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import (
    Entity, EntityType, EntityStatus, Vacancy, VacancyStatus,
    VacancyApplication, ApplicationStage, User, Organization, Department,
    StageTransition
)
from api.services.auth import create_access_token


# ============================================================================
# FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def candidate_entity(
    db_session: AsyncSession,
    organization: Organization,
    department: Department,
    admin_user: User
) -> Entity:
    """Create a candidate entity for vacancy tests."""
    entity = Entity(
        org_id=organization.id,
        department_id=department.id,
        created_by=admin_user.id,
        name="John Developer",
        email="john@example.com",
        type=EntityType.candidate,
        status=EntityStatus.active,
        created_at=datetime.utcnow()
    )
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)
    return entity


@pytest_asyncio.fixture
async def test_vacancy(
    db_session: AsyncSession,
    organization: Organization,
    department: Department,
    admin_user: User
) -> Vacancy:
    """Create a test vacancy."""
    vacancy = Vacancy(
        org_id=organization.id,
        department_id=department.id,
        created_by=admin_user.id,
        title="Senior Python Developer",
        description="Build great APIs",
        requirements="5+ years Python experience",
        responsibilities="Design and implement backend services",
        status=VacancyStatus.open,
        salary_min=150000,
        salary_max=250000,
        salary_currency="RUB",
        location="Moscow",
        employment_type="full-time",
        experience_level="senior",
        priority=1,
        tags=["python", "fastapi"],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db_session.add(vacancy)
    await db_session.commit()
    await db_session.refresh(vacancy)
    return vacancy


@pytest_asyncio.fixture
async def multiple_vacancies(
    db_session: AsyncSession,
    organization: Organization,
    department: Department,
    admin_user: User
) -> list[Vacancy]:
    """Create multiple test vacancies."""
    vacancies = []
    vacancy_configs = [
        ("Frontend Developer", "React development", VacancyStatus.open),
        ("DevOps Engineer", "Cloud infrastructure", VacancyStatus.open),
        ("QA Engineer", "Testing and quality", VacancyStatus.closed),
    ]

    for title, description, status in vacancy_configs:
        vacancy = Vacancy(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            title=title,
            description=description,
            status=status,
            salary_currency="RUB",
            priority=1,
            tags=[],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db_session.add(vacancy)
        vacancies.append(vacancy)

    await db_session.commit()
    for v in vacancies:
        await db_session.refresh(v)

    return vacancies


@pytest_asyncio.fixture
async def vacancy_application(
    db_session: AsyncSession,
    candidate_entity: Entity,
    test_vacancy: Vacancy,
    admin_user: User
) -> VacancyApplication:
    """Create a test vacancy application."""
    application = VacancyApplication(
        vacancy_id=test_vacancy.id,
        entity_id=candidate_entity.id,
        stage=ApplicationStage.interview,
        stage_order=1000,
        rating=4,
        source="LinkedIn",
        notes="Strong Python background",
        created_by=admin_user.id,
        applied_at=datetime.utcnow(),
        last_stage_change_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db_session.add(application)
    await db_session.commit()
    await db_session.refresh(application)
    return application


@pytest_asyncio.fixture
async def multiple_applications(
    db_session: AsyncSession,
    candidate_entity: Entity,
    multiple_vacancies: list[Vacancy],
    admin_user: User
) -> list[VacancyApplication]:
    """Create multiple vacancy applications for one entity."""
    applications = []
    stages = [ApplicationStage.applied, ApplicationStage.interview, ApplicationStage.offer]

    for vacancy, stage in zip(multiple_vacancies, stages):
        application = VacancyApplication(
            vacancy_id=vacancy.id,
            entity_id=candidate_entity.id,
            stage=stage,
            stage_order=1000,
            source="Job Board",
            created_by=admin_user.id,
            applied_at=datetime.utcnow(),
            last_stage_change_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db_session.add(application)
        applications.append(application)

    await db_session.commit()
    for app in applications:
        await db_session.refresh(app)

    return applications


def auth_headers(token: str) -> dict:
    """Create authorization headers with token."""
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# GET ENTITY VACANCIES TESTS
# ============================================================================

class TestGetEntityVacancies:
    """Tests for GET /entities/{id}/vacancies endpoint."""

    async def test_get_entity_vacancies_empty(
        self,
        client: AsyncClient,
        admin_user: User,
        candidate_entity: Entity,
        org_owner
    ):
        """Test getting vacancies when entity has no applications."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            f"/api/entities/{candidate_entity.id}/vacancies",
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        assert response.json() == []

    async def test_get_entity_vacancies_list(
        self,
        client: AsyncClient,
        admin_user: User,
        candidate_entity: Entity,
        multiple_applications: list[VacancyApplication],
        org_owner
    ):
        """Test getting list of entity's vacancy applications."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            f"/api/entities/{candidate_entity.id}/vacancies",
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

    async def test_get_entity_vacancies_contains_vacancy_details(
        self,
        client: AsyncClient,
        admin_user: User,
        candidate_entity: Entity,
        test_vacancy: Vacancy,
        vacancy_application: VacancyApplication,
        org_owner
    ):
        """Test that response contains vacancy details."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            f"/api/entities/{candidate_entity.id}/vacancies",
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

        app_data = data[0]
        assert app_data["id"] == vacancy_application.id
        assert app_data["vacancy_id"] == test_vacancy.id
        assert app_data["vacancy_title"] == "Senior Python Developer"
        assert app_data["vacancy_status"] == "open"
        assert app_data["stage"] == "interview"
        assert app_data["rating"] == 4
        assert app_data["source"] == "LinkedIn"
        assert app_data["notes"] == "Strong Python background"

    async def test_get_entity_vacancies_contains_stage(
        self,
        client: AsyncClient,
        admin_user: User,
        candidate_entity: Entity,
        multiple_applications: list[VacancyApplication],
        org_owner
    ):
        """Test that response contains correct stages."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            f"/api/entities/{candidate_entity.id}/vacancies",
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()

        stages = [app["stage"] for app in data]
        assert "applied" in stages
        assert "interview" in stages
        assert "offer" in stages

    async def test_get_entity_vacancies_sorted_by_date(
        self,
        client: AsyncClient,
        admin_user: User,
        candidate_entity: Entity,
        multiple_applications: list[VacancyApplication],
        org_owner
    ):
        """Test that applications are sorted by applied_at descending."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            f"/api/entities/{candidate_entity.id}/vacancies",
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()

        # Verify sorting by applied_at (descending)
        dates = [app["applied_at"] for app in data]
        assert dates == sorted(dates, reverse=True)

    async def test_get_entity_vacancies_not_found(
        self,
        client: AsyncClient,
        admin_user: User,
        org_owner
    ):
        """Test getting vacancies for non-existent entity."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            "/api/entities/99999/vacancies",
            headers=auth_headers(token)
        )
        assert response.status_code == 404

    async def test_get_entity_vacancies_unauthorized(
        self,
        client: AsyncClient,
        candidate_entity: Entity
    ):
        """Test getting vacancies without authentication."""
        response = await client.get(
            f"/api/entities/{candidate_entity.id}/vacancies"
        )
        assert response.status_code == 401


# ============================================================================
# APPLY ENTITY TO VACANCY TESTS
# ============================================================================



# ============================================================================
# REMOVE ENTITY FROM VACANCY TESTS
# ============================================================================



# ============================================================================
# ACCESS CONTROL TESTS
# ============================================================================

class TestEntityVacanciesAccessControl:
    """Tests for entity vacancies access control."""

    async def test_owner_can_view_all_applications(
        self,
        client: AsyncClient,
        admin_user: User,
        candidate_entity: Entity,
        multiple_applications: list[VacancyApplication],
        org_owner
    ):
        """Test that org owner can view all applications."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            f"/api/entities/{candidate_entity.id}/vacancies",
            headers=auth_headers(token)
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3




    async def test_shared_user_with_view_can_get_vacancies(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        second_user: User,
        candidate_entity: Entity,
        vacancy_application: VacancyApplication,
        org_owner,
        org_member
    ):
        """Test that user with view access can see entity's vacancies."""
        from api.models.database import SharedAccess, ResourceType, AccessLevel

        # Share entity with second_user with view access
        share = SharedAccess(
            resource_type=ResourceType.entity,
            resource_id=candidate_entity.id,
            entity_id=candidate_entity.id,
            shared_by_id=admin_user.id,
            shared_with_id=second_user.id,
            access_level=AccessLevel.view,
            created_at=datetime.utcnow()
        )
        db_session.add(share)
        await db_session.commit()

        token = create_access_token(data={"sub": str(second_user.id)})
        response = await client.get(
            f"/api/entities/{candidate_entity.id}/vacancies",
            headers=auth_headers(token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1


# ============================================================================
# VACANCY STATUS TESTS
# ============================================================================

class TestVacancyStatus:
    """Tests for vacancy status handling."""

    async def test_response_includes_vacancy_status(
        self,
        client: AsyncClient,
        admin_user: User,
        candidate_entity: Entity,
        test_vacancy: Vacancy,
        vacancy_application: VacancyApplication,
        org_owner
    ):
        """Test that response includes vacancy status."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            f"/api/entities/{candidate_entity.id}/vacancies",
            headers=auth_headers(token)
        )

        assert response.status_code == 200
        data = response.json()
        assert data[0]["vacancy_status"] == "open"

    async def test_includes_closed_vacancy_applications(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        candidate_entity: Entity,
        organization: Organization,
        department: Department,
        org_owner
    ):
        """Test that applications to closed vacancies are still shown."""
        # Create closed vacancy
        closed_vacancy = Vacancy(
            org_id=organization.id,
            department_id=department.id,
            created_by=admin_user.id,
            title="Closed Position",
            description="No longer hiring",
            status=VacancyStatus.closed,
            salary_currency="RUB",
            priority=1,
            tags=[],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db_session.add(closed_vacancy)
        await db_session.commit()
        await db_session.refresh(closed_vacancy)

        # Create application
        application = VacancyApplication(
            vacancy_id=closed_vacancy.id,
            entity_id=candidate_entity.id,
            stage=ApplicationStage.rejected,
            stage_order=1000,
            created_by=admin_user.id,
            applied_at=datetime.utcnow(),
            last_stage_change_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db_session.add(application)
        await db_session.commit()

        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            f"/api/entities/{candidate_entity.id}/vacancies",
            headers=auth_headers(token)
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["vacancy_status"] == "closed"
        assert data[0]["vacancy_title"] == "Closed Position"


# ============================================================================
# ENTITY ACTIVITY FEED TESTS
# ============================================================================

class TestGetEntityActivity:
    """Tests for GET /entities/{id}/activity — единая лента по вакансиям."""

    async def test_activity_blocks_per_vacancy_with_history(
        self,
        client: AsyncClient,
        admin_user: User,
        candidate_entity: Entity,
        test_vacancy: Vacancy,
        db_session: AsyncSession,
        org_owner,
    ):
        app = VacancyApplication(
            vacancy_id=test_vacancy.id, entity_id=candidate_entity.id,
            stage=ApplicationStage.hired, stage_order=0,
        )
        db_session.add(app)
        await db_session.commit()
        await db_session.refresh(app)
        db_session.add(StageTransition(
            application_id=app.id, entity_id=candidate_entity.id,
            from_stage="offer", to_stage="hired", comment="Оффер принят",
        ))
        await db_session.commit()

        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            f"/api/entities/{candidate_entity.id}/activity",
            headers=auth_headers(token),
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        block = data[0]
        assert block["vacancy_id"] == test_vacancy.id
        assert block["current_stage"] == "hired"
        assert block["application_id"] == app.id
        assert any(e["comment"] == "Оффер принят" for e in block["events"])

    async def test_activity_empty_when_no_applications(
        self,
        client: AsyncClient,
        admin_user: User,
        candidate_entity: Entity,
        org_owner,
    ):
        token = create_access_token(data={"sub": str(admin_user.id)})
        response = await client.get(
            f"/api/entities/{candidate_entity.id}/activity",
            headers=auth_headers(token),
        )
        assert response.status_code == 200
        assert response.json() == []
