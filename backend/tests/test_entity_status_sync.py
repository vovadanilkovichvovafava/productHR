"""
Tests for Entity.status ↔ VacancyApplication.stage synchronization.

This module tests the bidirectional synchronization between:
- Entity.status (in Database/База): new, screening, practice, tech_practice, is_interview, offer, hired, rejected
- VacancyApplication.stage (in Vacancy/Вакансия): applied, screening, phone_screen, interview, assessment, offer, hired, rejected

Architecture: One candidate = max one active vacancy, with full bidirectional sync.
"""
import pytest
import pytest_asyncio
from datetime import datetime
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import (
    Vacancy, VacancyApplication, VacancyStatus, ApplicationStage,
    Entity, EntityType, EntityStatus, User, Organization, Department,
    STAGE_SYNC_MAP, STATUS_SYNC_MAP
)
from api.services.auth import create_access_token


# ============================================================================
# FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def test_vacancy(db_session: AsyncSession, organization: Organization, department: Department, admin_user: User) -> Vacancy:
    """Create a test vacancy for sync tests."""
    vacancy = Vacancy(
        org_id=organization.id,
        department_id=department.id,
        title="Sync Test Vacancy",
        description="For testing Entity/Application sync",
        status=VacancyStatus.open,
        created_by=admin_user.id,
        published_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db_session.add(vacancy)
    await db_session.commit()
    await db_session.refresh(vacancy)
    return vacancy


@pytest_asyncio.fixture
async def second_vacancy(db_session: AsyncSession, organization: Organization, admin_user: User) -> Vacancy:
    """Create a second vacancy to test one-candidate-one-vacancy restriction."""
    vacancy = Vacancy(
        org_id=organization.id,
        title="Second Test Vacancy",
        description="For testing restrictions",
        status=VacancyStatus.open,
        created_by=admin_user.id,
        published_at=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db_session.add(vacancy)
    await db_session.commit()
    await db_session.refresh(vacancy)
    return vacancy


@pytest_asyncio.fixture
async def test_candidate(db_session: AsyncSession, organization: Organization, department: Department, admin_user: User) -> Entity:
    """Create a test candidate for sync tests."""
    entity = Entity(
        org_id=organization.id,
        department_id=department.id,
        created_by=admin_user.id,
        name="Sync Test Candidate",
        email="sync.test@example.com",
        type=EntityType.candidate,
        status=EntityStatus.new,
        created_at=datetime.utcnow()
    )
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)
    return entity


@pytest_asyncio.fixture
async def test_application(
    db_session: AsyncSession,
    test_vacancy: Vacancy,
    test_candidate: Entity,
    admin_user: User
) -> VacancyApplication:
    """Create a test application."""
    app = VacancyApplication(
        vacancy_id=test_vacancy.id,
        entity_id=test_candidate.id,
        stage=ApplicationStage.applied,
        stage_order=1,
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
# TEST: Entity.status → VacancyApplication.stage SYNC
# ============================================================================

class TestEntityToApplicationSync:
    """Tests for Entity.status changes syncing to VacancyApplication.stage."""

    async def test_patch_entity_status_syncs_application_stage(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        test_candidate: Entity,
        test_vacancy: Vacancy,
        test_application: VacancyApplication,
        org_owner
    ):
        """PATCH /entities/{id}/status should sync to VacancyApplication.stage."""
        token = create_access_token(data={"sub": str(admin_user.id)})

        # Change entity status to 'screening'
        response = await client.patch(
            f"/api/entities/{test_candidate.id}/status",
            json={"status": "screening"},
            headers=auth_headers(token)
        )
        assert response.status_code == 200

        # Verify application stage was synced
        await db_session.refresh(test_application)
        expected_stage = STATUS_SYNC_MAP[EntityStatus.screening]
        assert test_application.stage == expected_stage, \
            f"Expected stage {expected_stage}, got {test_application.stage}"

    async def test_put_entity_with_status_syncs_application_stage(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        test_candidate: Entity,
        test_vacancy: Vacancy,
        test_application: VacancyApplication,
        org_owner
    ):
        """PUT /entities/{id} with status should sync to VacancyApplication.stage."""
        token = create_access_token(data={"sub": str(admin_user.id)})

        # Update entity with new status
        response = await client.put(
            f"/api/entities/{test_candidate.id}",
            json={
                "name": test_candidate.name,
                "status": "practice"  # maps to phone_screen
            },
            headers=auth_headers(token)
        )
        assert response.status_code == 200

        # Verify application stage was synced
        await db_session.refresh(test_application)
        expected_stage = STATUS_SYNC_MAP[EntityStatus.practice]
        assert test_application.stage == expected_stage, \
            f"Expected stage {expected_stage}, got {test_application.stage}"


# ============================================================================
# TEST: VacancyApplication.stage → Entity.status SYNC
# ============================================================================

class TestApplicationToEntitySync:
    """Tests for VacancyApplication.stage changes syncing to Entity.status."""

    async def test_put_application_stage_syncs_entity_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        test_candidate: Entity,
        test_vacancy: Vacancy,
        test_application: VacancyApplication,
        org_owner
    ):
        """PUT /vacancies/applications/{id} should sync to Entity.status."""
        token = create_access_token(data={"sub": str(admin_user.id)})

        # Change application stage to 'interview'
        response = await client.put(
            f"/api/vacancies/applications/{test_application.id}",
            json={"stage": "interview"},  # maps to tech_practice
            headers=auth_headers(token)
        )
        assert response.status_code == 200

        # Verify entity status was synced
        await db_session.refresh(test_candidate)
        expected_status = STAGE_SYNC_MAP[ApplicationStage.interview]
        assert test_candidate.status == expected_status, \
            f"Expected status {expected_status}, got {test_candidate.status}"

    async def test_bulk_move_syncs_entity_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        test_candidate: Entity,
        test_vacancy: Vacancy,
        test_application: VacancyApplication,
        org_owner
    ):
        """POST /vacancies/applications/bulk-move should sync Entity.status."""
        token = create_access_token(data={"sub": str(admin_user.id)})

        # Bulk move application to 'offer' stage
        response = await client.post(
            "/api/vacancies/applications/bulk-move",
            json={
                "application_ids": [test_application.id],
                "stage": "offer"  # maps to 'offer' status
            },
            headers=auth_headers(token)
        )
        assert response.status_code == 200

        # Verify entity status was synced
        await db_session.refresh(test_candidate)
        expected_status = STAGE_SYNC_MAP[ApplicationStage.offer]
        assert test_candidate.status == expected_status, \
            f"Expected status {expected_status}, got {test_candidate.status}"


# ============================================================================
# TEST: CREATE APPLICATION SYNC
# ============================================================================

class TestCreateApplicationSync:
    """Tests for Entity.status sync when creating applications."""

    async def test_create_application_uses_entity_status_as_initial_stage(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        test_candidate: Entity,
        test_vacancy: Vacancy,
        organization: Organization,
        org_owner
    ):
        """POST /{vacancy_id}/applications should use Entity.status as initial stage."""
        token = create_access_token(data={"sub": str(admin_user.id)})

        # Set candidate status to 'screening' before adding to vacancy
        test_candidate.status = EntityStatus.screening
        await db_session.commit()
        await db_session.refresh(test_candidate)

        # Create application
        # vacancy_id в теле обязателен (ApplicationCreate), без него — 422.
        response = await client.post(
            f"/api/vacancies/{test_vacancy.id}/applications",
            json={"vacancy_id": test_vacancy.id, "entity_id": test_candidate.id},
            headers=auth_headers(token)
        )
        assert response.status_code == 201
        data = response.json()

        # Verify stage matches the entity's status
        expected_stage = STATUS_SYNC_MAP[EntityStatus.screening]
        assert data["stage"] == expected_stage.value, \
            f"Expected stage {expected_stage.value}, got {data['stage']}"



# ============================================================================
# TEST: DELETE APPLICATION SYNC
# ============================================================================

class TestDeleteApplicationSync:
    """Tests for Entity.status sync when deleting applications."""

    async def test_delete_application_resets_entity_status_to_new(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        test_candidate: Entity,
        test_vacancy: Vacancy,
        test_application: VacancyApplication,
        org_owner
    ):
        """DELETE /vacancies/applications/{id} should reset Entity.status to 'new'."""
        token = create_access_token(data={"sub": str(admin_user.id)})

        # First change candidate to non-new status
        test_candidate.status = EntityStatus.offer
        await db_session.commit()

        # Delete application
        response = await client.delete(
            f"/api/vacancies/applications/{test_application.id}",
            headers=auth_headers(token)
        )
        assert response.status_code == 204

        # Verify entity status was reset to 'new'
        await db_session.refresh(test_candidate)
        assert test_candidate.status == EntityStatus.new, \
            f"Expected status 'new', got {test_candidate.status}"


# ============================================================================
# TEST: ONE CANDIDATE ONE VACANCY RESTRICTION
# ============================================================================

class TestOneCandidateSeveralVacancies:
    """Кандидат может быть в нескольких воронках сразу — это норма
    (CLAUDE.md, «Модель работы HR»). Прежнее правило «один кандидат — одна
    активная вакансия» снято; повторно в ТУ ЖЕ воронку — по-прежнему 400."""

    async def test_can_add_candidate_to_second_vacancy(
        self,
        client: AsyncClient,
        admin_user: User,
        test_candidate: Entity,
        test_vacancy: Vacancy,
        second_vacancy: Vacancy,
        test_application: VacancyApplication,
        org_owner
    ):
        token = create_access_token(data={"sub": str(admin_user.id)})

        response = await client.post(
            f"/api/vacancies/{second_vacancy.id}/applications",
            json={"vacancy_id": second_vacancy.id, "entity_id": test_candidate.id},
            headers=auth_headers(token)
        )
        assert response.status_code == 201

        # В ту же воронку второй раз — отказ.
        response = await client.post(
            f"/api/vacancies/{test_vacancy.id}/applications",
            json={"vacancy_id": test_vacancy.id, "entity_id": test_candidate.id},
            headers=auth_headers(token)
        )
        assert response.status_code == 400
        assert "уже добавлен" in response.json()["detail"].lower()


# ============================================================================
# TEST: SYNC MAPPING CORRECTNESS
# ============================================================================

class TestSyncMappings:
    """Tests for sync mapping correctness."""

    # HR pipeline statuses that should be synced
    HR_PIPELINE_STATUSES = [
        EntityStatus.new,
        EntityStatus.screening,
        EntityStatus.practice,
        EntityStatus.tech_practice,
        EntityStatus.is_interview,
        EntityStatus.offer,
        EntityStatus.hired,
        EntityStatus.rejected,
    ]

    # HR pipeline stages that should be synced (excluding withdrawn)
    HR_PIPELINE_STAGES = [
        ApplicationStage.applied,
        ApplicationStage.screening,
        ApplicationStage.phone_screen,
        ApplicationStage.interview,
        ApplicationStage.assessment,
        ApplicationStage.offer,
        ApplicationStage.hired,
        ApplicationStage.rejected,
    ]

    def test_hr_pipeline_statuses_have_mappings(self):
        """All HR pipeline EntityStatus values should map to ApplicationStage."""
        for status in self.HR_PIPELINE_STATUSES:
            assert status in STATUS_SYNC_MAP, f"Missing mapping for HR status {status}"

    def test_hr_pipeline_stages_have_mappings(self):
        """All HR pipeline ApplicationStage values should map to EntityStatus."""
        for stage in self.HR_PIPELINE_STAGES:
            assert stage in STAGE_SYNC_MAP, f"Missing mapping for HR stage {stage}"

    def test_mappings_are_bidirectional(self):
        """Mappings should be bidirectional (inverse of each other)."""
        for status, stage in STATUS_SYNC_MAP.items():
            assert STAGE_SYNC_MAP[stage] == status, \
                f"Mapping mismatch: {status} -> {stage} but {stage} -> {STAGE_SYNC_MAP[stage]}"

    def test_mapping_values_are_correct(self):
        """Verify specific mappings are correct."""
        expected_mappings = {
            EntityStatus.new: ApplicationStage.applied,
            EntityStatus.screening: ApplicationStage.screening,
            EntityStatus.practice: ApplicationStage.phone_screen,
            EntityStatus.tech_practice: ApplicationStage.interview,
            EntityStatus.is_interview: ApplicationStage.assessment,
            EntityStatus.offer: ApplicationStage.offer,
            EntityStatus.hired: ApplicationStage.hired,
            EntityStatus.rejected: ApplicationStage.rejected,
        }
        for status, expected_stage in expected_mappings.items():
            assert STATUS_SYNC_MAP[status] == expected_stage, \
                f"Wrong mapping: {status} should map to {expected_stage}, got {STATUS_SYNC_MAP[status]}"
