"""Смена этапа чужой организации — org-граница в update_application.

`is_org_admin_or_owner` проверяет роль в СВОЕЙ орге вызывающего и, вернув True,
замыкала `or` в проверке доступа: граница организаций живёт внутри
`can_access_vacancy` и не выполнялась вовсе. Admin орга A мог двигать заявку
орга B, зная только её id.
"""
from datetime import datetime

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import (
    ApplicationStage, Department, Entity, EntityStatus, EntityType, OrgMember,
    Organization, User, Vacancy, VacancyApplication, VacancyStatus,
)
from api.services.auth import create_access_token
from tests.conftest import auth_headers

FOREIGN_STAGE = ApplicationStage.screening


@pytest_asyncio.fixture
async def foreign_application(
    db_session: AsyncSession, second_organization: Organization, admin_user: User,
):
    """Заявка, целиком принадлежащая ЧУЖОЙ организации."""
    now = datetime.utcnow()
    dept = Department(
        name="Чужой отдел", org_id=second_organization.id, created_at=now,
    )
    db_session.add(dept)
    await db_session.commit()

    entity = Entity(
        org_id=second_organization.id, department_id=dept.id, name="Чужой кандидат",
        type=EntityType.candidate, status=EntityStatus.screening, created_at=now,
    )
    vacancy = Vacancy(
        org_id=second_organization.id, department_id=dept.id, title="Чужая воронка",
        status=VacancyStatus.open, salary_currency="RUB", created_at=now, updated_at=now,
    )
    db_session.add_all([entity, vacancy])
    await db_session.commit()

    app = VacancyApplication(
        vacancy_id=vacancy.id, entity_id=entity.id, stage=FOREIGN_STAGE, stage_order=1,
        applied_at=now, last_stage_change_at=now, updated_at=now,
    )
    db_session.add(app)
    await db_session.commit()
    return app, entity


def _headers(user: User) -> dict:
    return auth_headers(create_access_token(data={"sub": str(user.id)}))


async def test_org_admin_cannot_move_foreign_application(
    client: AsyncClient, db_session: AsyncSession, admin_user: User,
    org_owner: OrgMember, foreign_application,
):
    """Owner своей орги не двигает заявку чужой — 404, этап на месте."""
    app, _entity = foreign_application
    r = await client.put(
        f"/api/vacancies/applications/{app.id}",
        json={"stage": ApplicationStage.rejected.value},
        headers=_headers(admin_user),
    )
    assert r.status_code == 404, r.text
    await db_session.refresh(app)
    assert app.stage == FOREIGN_STAGE


async def test_foreign_application_status_not_synced_to_entity(
    client: AsyncClient, db_session: AsyncSession, admin_user: User,
    org_owner: OrgMember, foreign_application,
):
    """Отказ по границе — до синка Entity.status дело не доходит.

    Проверка отдельно от этапа: синхронизация статуса кандидата идёт ПОСЛЕ
    проверок доступа, и утечка туда означала бы правку чужого кандидата даже
    при неизменившемся этапе.
    """
    app, entity = foreign_application
    before = entity.status
    r = await client.put(
        f"/api/vacancies/applications/{app.id}",
        json={"stage": ApplicationStage.offer.value},
        headers=_headers(admin_user),
    )
    assert r.status_code == 404, r.text
    await db_session.refresh(entity)
    assert entity.status == before
