"""Доска «Штат» и база «Все кандидаты» — одна система (20.10.2026).

Владелец: «если я на борде меняю статус у сотрудника с практики на уволен, то
в ATS он тоже перемещается в статус отказ». Проверено на проде 20.10.2026:
у троих уволенных заявки висели на «Оффер принят», а сами они лежали в колонке
«Вне воронки».
"""
from datetime import datetime

import pytest
from sqlalchemy import select

from api.models.database import (
    ApplicationStage, Entity, EntityStatus, EntityType, StageTransition,
    Vacancy, VacancyApplication, VacancyStatus,
)
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _candidate(db, org, user, status=EntityStatus.probation):
    e = Entity(
        org_id=org.id, name="Пак Артем", type=EntityType.candidate, status=status,
        created_by=user.id, created_at=datetime.utcnow(), extra_data={},
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


async def _application(db, org, user, entity, title, stage):
    now = datetime.utcnow()
    v = Vacancy(
        org_id=org.id, created_by=user.id, title=title, status=VacancyStatus.open,
        created_at=now, updated_at=now,
    )
    db.add(v)
    await db.commit()
    app = VacancyApplication(
        vacancy_id=v.id, entity_id=entity.id, stage=stage, stage_order=1,
        created_by=user.id, applied_at=now, last_stage_change_at=now, updated_at=now,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


async def _stages(db, ids):
    rows = (await db.execute(
        select(VacancyApplication.id, VacancyApplication.stage)
        .where(VacancyApplication.id.in_(ids))
    )).all()
    return {i: st for i, st in rows}


@pytest.mark.asyncio
async def test_dismissal_closes_all_live_applications(
    client, db_session, organization, admin_user, org_owner
):
    e = await _candidate(db_session, organization, admin_user)
    live = await _application(db_session, organization, admin_user, e, "Growth", ApplicationStage.hired)
    other = await _application(db_session, organization, admin_user, e, "Трафик", ApplicationStage.probation)
    closed = await _application(db_session, organization, admin_user, e, "SEO", ApplicationStage.withdrawn)

    r = await client.patch(f"/api/staff-board/rows/{e.id}",
                           json={"status": "dismissed"}, headers=_h(admin_user))
    assert r.status_code == 200, r.text

    stages = await _stages(db_session, [live.id, other.id, closed.id])
    assert stages[live.id] == ApplicationStage.rejected
    assert stages[other.id] == ApplicationStage.rejected
    # «Отозван» не трогаем — заявка и так закрыта.
    assert stages[closed.id] == ApplicationStage.withdrawn

    # Перевод должен остаться в истории воронки, а не произойти молча.
    moves = (await db_session.execute(
        select(StageTransition).where(StageTransition.entity_id == e.id)
    )).scalars().all()
    assert {m.application_id for m in moves} == {live.id, other.id}
    assert all(m.to_stage == ApplicationStage.rejected.value for m in moves)
    # В ленте видно, почему «Отказ»: уволен на доске.
    assert all(m.comment == "Уволен — доска «Штат»" for m in moves)


@pytest.mark.asyncio
async def test_single_funnel_follows_board_status(
    client, db_session, organization, admin_user, org_owner
):
    """Оффер принят на доске — заявка едет на тот же этап (как в «Все кандидаты»)."""
    e = await _candidate(db_session, organization, admin_user, EntityStatus.probation)
    app = await _application(db_session, organization, admin_user, e, "Growth", ApplicationStage.offer)

    r = await client.patch(f"/api/staff-board/rows/{e.id}",
                           json={"status": "hired"}, headers=_h(admin_user))
    assert r.status_code == 200, r.text
    assert (await _stages(db_session, [app.id]))[app.id] == ApplicationStage.hired


@pytest.mark.asyncio
async def test_two_funnels_move_only_the_actual_application(
    client, db_session, organization, admin_user, org_owner
):
    """Воронок несколько — двигается «актуальная» (по ней сервер считает
    общий статус), вторая не трогается. Если не двигать ничего, на доске
    человек «Практика», а заявка висит на прежнем этапе, и первое же действие
    в воронке вернёт статус назад (жалоба Марии 20.10.2026)."""
    from datetime import timedelta

    e = await _candidate(db_session, organization, admin_user, EntityStatus.hired)
    a1 = await _application(db_session, organization, admin_user, e, "Growth", ApplicationStage.offer)
    a2 = await _application(db_session, organization, admin_user, e, "Трафик", ApplicationStage.hired)
    a1.last_stage_change_at = datetime.utcnow() - timedelta(days=3)  # a2 — актуальная
    await db_session.commit()

    r = await client.patch(f"/api/staff-board/rows/{e.id}",
                           json={"status": "probation"}, headers=_h(admin_user))
    assert r.status_code == 200, r.text
    stages = await _stages(db_session, [a1.id, a2.id])
    assert stages[a1.id] == ApplicationStage.offer
    assert stages[a2.id] == ApplicationStage.probation


@pytest.mark.asyncio
async def test_dismissed_candidate_sits_in_rejected_column(
    client, db_session, organization, admin_user, org_owner
):
    """В базе «Все кандидаты» уволенный — в «Отказе», а не в «Вне воронки»."""
    e = await _candidate(db_session, organization, admin_user, EntityStatus.dismissed)

    r = await client.get("/api/candidates/kanban", headers=_h(admin_user))
    assert r.status_code == 200, r.text
    columns = {c["status"]: c for c in r.json()["columns"]}
    assert e.id in [c["id"] for c in columns["rejected"]["cards"]]
    assert e.id not in [c["id"] for c in columns["other"]["cards"]]

    # «Выбрать всех» на вкладке «Отказ» обязано отбирать тех же людей.
    ids = await client.get("/api/candidates/ids?status=rejected", headers=_h(admin_user))
    assert e.id in ids.json()["ids"]
