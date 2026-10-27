"""Из «Перешёл в отдел» — только в практику и оффер; всё прочее = «Уволен».

Встреча 24.09.2026: статуса «уволен» в воронке нет, HR нажимает «Отказ», и
человек должен появиться в уволенных на доске «Статусы». Раньше он просто
возвращался в кандидаты, и Мария не понимала, как люди попадают в «Уволен».
"""
from datetime import datetime

import pytest

from api.models.database import (
    ApplicationStage, Entity, EntityStatus, EntityType,
    Vacancy, VacancyApplication, VacancyStatus,
)
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _setup(db, org, user, status=EntityStatus.transferred):
    v = Vacancy(
        org_id=org.id, title="Воронка", status=VacancyStatus.open,
        created_by=user.id, created_at=datetime.utcnow(),
    )
    e = Entity(
        org_id=org.id, name="Перешёл Пётр", type=EntityType.candidate,
        status=status, created_by=user.id, created_at=datetime.utcnow(),
    )
    db.add_all([v, e])
    await db.commit()
    await db.refresh(v)
    await db.refresh(e)
    app = VacancyApplication(
        vacancy_id=v.id, entity_id=e.id, stage=ApplicationStage.transferred,
        stage_order=1, created_by=user.id, applied_at=datetime.utcnow(),
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return v, e, app


async def _move(client, user, app_id, stage):
    r = await client.put(
        f"/api/vacancies/applications/{app_id}",
        json={"stage": stage.value},
        headers=_h(user),
    )
    assert r.status_code in (200, 201), r.text
    return r


@pytest.mark.parametrize("stage", [
    ApplicationStage.rejected,
    ApplicationStage.withdrawn,
    ApplicationStage.reserve,
    ApplicationStage.applied,
])
@pytest.mark.asyncio
async def test_leaving_department_means_dismissed(
    client, db_session, organization, admin_user, org_owner, stage
):
    _, e, app = await _setup(db_session, organization, admin_user)
    await _move(client, admin_user, app.id, stage)
    await db_session.refresh(e)
    assert e.status == EntityStatus.dismissed


@pytest.mark.parametrize("stage", [
    ApplicationStage.probation,
    ApplicationStage.offer,
    ApplicationStage.hired,
])
@pytest.mark.asyncio
async def test_practice_and_offer_are_not_dismissal(
    client, db_session, organization, admin_user, org_owner, stage
):
    """Практика и оффер — это движение внутри компании, а не увольнение."""
    _, e, app = await _setup(db_session, organization, admin_user)
    await _move(client, admin_user, app.id, stage)
    await db_session.refresh(e)
    assert e.status != EntityStatus.dismissed


@pytest.mark.asyncio
async def test_candidate_without_transfer_is_untouched(
    client, db_session, organization, admin_user, org_owner
):
    """Обычному кандидату «Отказ» — это отказ, а не увольнение."""
    _, e, app = await _setup(db_session, organization, admin_user, status=EntityStatus.offer)
    await _move(client, admin_user, app.id, ApplicationStage.rejected)
    await db_session.refresh(e)
    assert e.status == EntityStatus.rejected
