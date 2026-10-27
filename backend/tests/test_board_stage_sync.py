"""Разовое выравнивание заявок за доской «Штат» (services/board_stage_sync.py)."""
from datetime import datetime

import pytest
from sqlalchemy import select

from api.models.database import (
    ApplicationStage, DataMigrationMark, Entity, EntityStatus, EntityType,
    StageTransition, Vacancy, VacancyApplication, VacancyStatus,
)
from api.services.board_stage_sync import SYNC_MARK, sync_transferred_applications_once


async def _person(db, org, user, status, stage, vstatus=VacancyStatus.open):
    now = datetime.utcnow()
    e = Entity(org_id=org.id, name="Человек", type=EntityType.candidate, status=status,
               created_by=user.id, created_at=now, extra_data={})
    db.add(e)
    v = Vacancy(org_id=org.id, created_by=user.id, title="Mob dev", status=vstatus,
                salary_currency="RUB", created_at=now, updated_at=now)
    db.add(v)
    await db.commit()
    a = VacancyApplication(vacancy_id=v.id, entity_id=e.id, stage=stage, stage_order=1,
                           created_by=user.id, applied_at=now, last_stage_change_at=now,
                           updated_at=now)
    db.add(a)
    await db.commit()
    return e, a


@pytest.mark.asyncio
async def test_sync_fixes_only_board_mismatch(db_session, organization, admin_user):
    stuck, stuck_app = await _person(db_session, organization, admin_user,
                                     EntityStatus.transferred, ApplicationStage.probation)
    ok, ok_app = await _person(db_session, organization, admin_user,
                               EntityStatus.transferred, ApplicationStage.transferred)
    practice, practice_app = await _person(db_session, organization, admin_user,
                                           EntityStatus.probation, ApplicationStage.probation)
    closed, closed_app = await _person(db_session, organization, admin_user,
                                       EntityStatus.transferred, ApplicationStage.probation,
                                       vstatus=VacancyStatus.closed)

    fixed = await sync_transferred_applications_once(db_session)
    assert fixed == [stuck.id]

    for app in (stuck_app, ok_app, practice_app, closed_app):
        await db_session.refresh(app)
    assert stuck_app.stage == ApplicationStage.transferred
    assert ok_app.stage == ApplicationStage.transferred
    assert practice_app.stage == ApplicationStage.probation  # обычный практикант
    assert closed_app.stage == ApplicationStage.probation    # закрытая воронка — архив
    # Истории не пишем: перевод был раньше.
    assert (await db_session.execute(select(StageTransition))).scalars().all() == []
    assert await db_session.get(DataMigrationMark, SYNC_MARK) is not None


@pytest.mark.asyncio
async def test_sync_runs_once(db_session, organization, admin_user):
    await sync_transferred_applications_once(db_session)
    e, app = await _person(db_session, organization, admin_user,
                           EntityStatus.transferred, ApplicationStage.probation)
    assert await sync_transferred_applications_once(db_session) == []
    await db_session.refresh(app)
    assert app.stage == ApplicationStage.probation
