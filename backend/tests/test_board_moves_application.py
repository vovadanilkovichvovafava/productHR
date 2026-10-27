"""Перевод на доске «Штат» двигает и заявку в воронке (20.10.2026).

Мария: «на этапе „Перешёл в отдел“ висят кандидаты со статусом практика».
Доска меняла только общий статус человека, заявка оставалась на «Практике»:
на «Все кандидаты» он стоял в колонке «Перешёл в отдел», а в строке — чип
«Практика · Mob dev», и первое же действие в воронке пересчитывало статус
обратно. Теперь доска переводит «актуальную» открытую заявку тем же путём,
что и воронка (services/stage_change.py).
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from api.models.database import (
    ApplicationStage, Entity, EntityStatus, EntityType, StageTransition, Vacancy,
    VacancyApplication, VacancyStatus,
)
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _person(db, org, creator, status=EntityStatus.probation):
    e = Entity(
        org_id=org.id, name="Клементьев Егор", type=EntityType.candidate,
        status=status, created_by=creator.id, created_at=datetime.utcnow(), extra_data={},
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


async def _app(db, org, dept, user, entity, stage, title="Mob dev",
               status=VacancyStatus.open, when=None):
    now = when or datetime.utcnow()
    v = Vacancy(
        org_id=org.id, department_id=dept.id, created_by=user.id, title=title,
        status=status, salary_currency="RUB", created_at=now, updated_at=now,
    )
    db.add(v)
    await db.commit()
    a = VacancyApplication(
        vacancy_id=v.id, entity_id=entity.id, stage=stage, stage_order=1,
        created_by=user.id, applied_at=now, last_stage_change_at=now, updated_at=now,
    )
    db.add(a)
    await db.commit()
    return a


async def _history(db, app_id):
    rows = (await db.execute(
        select(StageTransition).where(StageTransition.application_id == app_id)
    )).scalars().all()
    return [(r.from_stage, r.to_stage) for r in rows]


@pytest.mark.asyncio
async def test_transfer_on_board_moves_funnel_application(
    client, db_session, organization, department, admin_user, org_owner,
):
    e = await _person(db_session, organization, admin_user)
    app = await _app(db_session, organization, department, admin_user, e, ApplicationStage.probation)

    r = await client.patch(
        f"/api/staff-board/rows/{e.id}",
        json={"status": EntityStatus.transferred.value}, headers=_h(admin_user),
    )
    assert r.status_code == 200, r.text

    await db_session.refresh(app)
    await db_session.refresh(e)
    assert app.stage == ApplicationStage.transferred
    assert e.status == EntityStatus.transferred
    # Перевод — строка истории заявки (корзина его отменяет), без второй
    # записи-комментария в ленте.
    assert await _history(db_session, app.id) == [("probation", "transferred")]
    assert not (e.extra_data or {}).get("notes")


@pytest.mark.asyncio
async def test_old_mismatch_is_fixed_by_choosing_status_again(
    client, db_session, organization, department, admin_user, org_owner,
):
    """Статус уже «Перешёл в отдел», заявка на «Практике» — повторный выбор доводит её."""
    e = await _person(db_session, organization, admin_user, status=EntityStatus.transferred)
    app = await _app(db_session, organization, department, admin_user, e, ApplicationStage.probation)

    r = await client.patch(
        f"/api/staff-board/rows/{e.id}",
        json={"status": EntityStatus.transferred.value}, headers=_h(admin_user),
    )
    assert r.status_code == 200, r.text
    await db_session.refresh(app)
    assert app.stage == ApplicationStage.transferred


@pytest.mark.asyncio
async def test_board_moves_the_actual_application_only(
    client, db_session, organization, department, admin_user, org_owner,
):
    """Две воронки: двигаем актуальную (свежую живую), вторую не трогаем."""
    e = await _person(db_session, organization, admin_user)
    old = datetime.utcnow() - timedelta(days=10)
    stale = await _app(db_session, organization, department, admin_user, e,
                       ApplicationStage.screening, title="Трафик", when=old)
    actual = await _app(db_session, organization, department, admin_user, e,
                        ApplicationStage.probation, title="Mob dev")

    r = await client.patch(
        f"/api/staff-board/rows/{e.id}",
        json={"status": EntityStatus.transferred.value}, headers=_h(admin_user),
    )
    assert r.status_code == 200, r.text
    await db_session.refresh(stale)
    await db_session.refresh(actual)
    assert actual.stage == ApplicationStage.transferred
    assert stale.stage == ApplicationStage.screening


@pytest.mark.asyncio
async def test_closed_funnel_and_no_funnel_keep_timeline_note(
    client, db_session, organization, department, admin_user, org_owner,
):
    """Нет открытой воронки — как раньше: запись в ленте, закрытую заявку не трогаем."""
    e = await _person(db_session, organization, admin_user)
    closed = await _app(db_session, organization, department, admin_user, e,
                        ApplicationStage.probation, status=VacancyStatus.closed)

    r = await client.patch(
        f"/api/staff-board/rows/{e.id}",
        json={"status": EntityStatus.transferred.value}, headers=_h(admin_user),
    )
    assert r.status_code == 200, r.text
    await db_session.refresh(closed)
    await db_session.refresh(e)
    assert closed.stage == ApplicationStage.probation
    notes = (e.extra_data or {}).get("notes") or []
    assert [n["stage"] for n in notes] == ["transferred"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status, note", [
    (EntityStatus.dismissed, "Уволен — доска «Штат»"),
    (EntityStatus.quit, "Уволился — доска «Штат»"),
])
async def test_dismissal_moves_application_to_rejected(
    client, db_session, organization, department, admin_user, org_owner, status, note,
):
    """«Уволен» на доске = «Отказ» в воронке (Мария, 20.10.2026: «борд и АТС —
    единая система»). Раньше заявка оставалась на прежнем этапе."""
    e = await _person(db_session, organization, admin_user, status=EntityStatus.transferred)
    app = await _app(db_session, organization, department, admin_user, e, ApplicationStage.transferred)

    r = await client.patch(
        f"/api/staff-board/rows/{e.id}",
        json={"status": status.value}, headers=_h(admin_user),
    )
    assert r.status_code == 200, r.text
    await db_session.refresh(app)
    await db_session.refresh(e)
    assert app.stage == ApplicationStage.rejected
    assert await _history(db_session, app.id) == [("transferred", "rejected")]
    comment = (await db_session.execute(
        select(StageTransition.comment).where(StageTransition.application_id == app.id)
    )).scalar()
    assert comment == note
    # Точный статус остаётся — на доске он «Уволен», а не просто «Отказ».
    assert e.status == status


@pytest.mark.asyncio
async def test_dismissed_stands_in_rejected_tab_and_select_all(
    client, db_session, organization, department, admin_user, org_owner,
):
    """На «Все кандидаты» уволенный — во вкладке «Отказ», и «Выбрать всех»
    на этой вкладке берёт его тоже (бейдж и выбор не расходятся)."""
    e = await _person(db_session, organization, admin_user, status=EntityStatus.dismissed)
    r = await client.get("/api/candidates/kanban", headers=_h(admin_user))
    assert r.status_code == 200, r.text
    cols = {c["status"]: c for c in r.json()["columns"]}
    assert e.id in [c["id"] for c in cols["rejected"]["cards"]]
    assert e.id not in [c["id"] for c in cols.get("other", {}).get("cards", [])]

    ids = (await client.get("/api/candidates/ids?status=rejected", headers=_h(admin_user))).json()["ids"]
    assert e.id in ids
    all_ids = (await client.get("/api/candidates/ids", headers=_h(admin_user))).json()["ids"]
    assert e.id in all_ids
