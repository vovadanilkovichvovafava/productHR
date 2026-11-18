"""Одна смена статуса — одна строка в ленте карточки (18.11.2026).

Мария: «поменяла статус на „мы уволили“, а в итоге получила 2 статуса» —
увольнение из карточки писало и перевод заявки «Отказ — Мы уволили — …», и
отдельную запись-комментарий. Сторож проходит ВСЕ статусы по всем путям,
которыми их меняет интерфейс, и считает строки ленты: переводы заявок
(StageTransition) + записи в extra_data.notes.
- карточка «Все кандидаты», кандидат в воронке: этап — PUT заявки, «Мы
  уволили» / «Сам уволился» — PATCH /candidates/{id}/status;
- карточка «Все кандидаты», кандидат вне воронок: PATCH /candidates/{id}/status;
- доска «Штат»: PATCH /staff-board/rows/{id}.
"""
from datetime import datetime

import pytest
from sqlalchemy import func, select

from api.models.database import (
    STATUS_SYNC_MAP, ApplicationStage, Entity, EntityStatus, EntityType, StageTransition,
    Vacancy, VacancyApplication, VacancyStatus,
)
from api.services.auth import create_access_token
from api.services.hr_stages import STATUS_LABELS

DEPARTED = {EntityStatus.dismissed, EntityStatus.quit}
# Статусы, которые предлагает окно смены этапа (у каждого есть подпись).
PICKER = [s for s in EntityStatus if s.value in STATUS_LABELS and (s in STATUS_SYNC_MAP or s in DEPARTED)]
BOARD = [EntityStatus.hired, EntityStatus.probation, EntityStatus.transferred, *DEPARTED]


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


def _start_for(target: EntityStatus) -> EntityStatus:
    return EntityStatus.screening if target == EntityStatus.new else EntityStatus.new


async def _person(db, org, user, status):
    e = Entity(org_id=org.id, created_by=user.id, name="Лента Проверка", type=EntityType.candidate,
               status=status, created_at=datetime.utcnow(), extra_data={})
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


async def _funnel(db, org, user, entity, stage, title="Трафик"):
    now = datetime.utcnow()
    v = Vacancy(org_id=org.id, created_by=user.id, title=title, status=VacancyStatus.open,
                salary_currency="RUB", created_at=now, updated_at=now, visible_to_all=True)
    db.add(v)
    await db.commit()
    await db.refresh(v)
    a = VacancyApplication(vacancy_id=v.id, entity_id=entity.id, stage=stage, stage_order=1,
                           created_by=user.id, applied_at=now, last_stage_change_at=now, updated_at=now)
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return a


async def _feed_rows(db, entity_id) -> int:
    db.expire_all()
    transitions = (await db.execute(
        select(func.count()).select_from(StageTransition).where(StageTransition.entity_id == entity_id)
    )).scalar()
    entity = await db.get(Entity, entity_id)
    return transitions + len((entity.extra_data or {}).get("notes") or [])


@pytest.mark.asyncio
@pytest.mark.parametrize("target", PICKER, ids=lambda s: s.value)
async def test_card_in_funnel(client, db_session, organization, admin_user, org_owner, target):
    headers = _h(admin_user)
    start = _start_for(target)
    e = await _person(db_session, organization, admin_user, start)
    eid = e.id
    app = await _funnel(db_session, organization, admin_user, e, STATUS_SYNC_MAP[start])
    app_id = app.id
    before = await _feed_rows(db_session, eid)
    if target in DEPARTED:
        r = await client.patch(f"/api/candidates/{eid}/status",
                               json={"status": target.value, "comment": "причина"}, headers=headers)
    else:
        r = await client.put(f"/api/vacancies/applications/{app_id}",
                             json={"stage": STATUS_SYNC_MAP[target].value, "comment": "коммент",
                                   "expected_entity_id": eid},
                             headers=headers)
    assert r.status_code == 200, r.text
    assert await _feed_rows(db_session, eid) - before == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("target", PICKER, ids=lambda s: s.value)
async def test_card_out_of_funnel(client, db_session, organization, admin_user, org_owner, target):
    headers = _h(admin_user)
    e = await _person(db_session, organization, admin_user, _start_for(target))
    eid = e.id
    before = await _feed_rows(db_session, eid)
    r = await client.patch(f"/api/candidates/{eid}/status",
                           json={"status": target.value, "comment": "причина"}, headers=headers)
    assert r.status_code == 200, r.text
    assert await _feed_rows(db_session, eid) - before == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("with_funnel", [True, False], ids=["в воронке", "вне воронок"])
@pytest.mark.parametrize("target", BOARD, ids=lambda s: s.value)
async def test_staff_board(client, db_session, organization, admin_user, org_owner, target, with_funnel):
    headers = _h(admin_user)
    start = EntityStatus.transferred if target == EntityStatus.probation else EntityStatus.probation
    e = await _person(db_session, organization, admin_user, start)
    eid = e.id
    if with_funnel:
        await _funnel(db_session, organization, admin_user, e, STATUS_SYNC_MAP[start])
    before = await _feed_rows(db_session, eid)
    body = {"status": target.value}
    if target in DEPARTED:
        body["rejection_reason"] = "причина"
    r = await client.patch(f"/api/staff-board/rows/{eid}", json=body, headers=headers)
    assert r.status_code == 200, r.text
    assert await _feed_rows(db_session, eid) - before == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("target", sorted(DEPARTED, key=lambda s: s.value), ids=lambda s: s.value)
async def test_departure_two_funnels_one_row_per_funnel(
    client, db_session, organization, admin_user, org_owner, target,
):
    """Две воронки — по строке в КАЖДОЙ (у каждой свой блок в карточке), без
    общей записи-комментария сверху."""
    headers = _h(admin_user)
    e = await _person(db_session, organization, admin_user, EntityStatus.probation)
    eid = e.id
    await _funnel(db_session, organization, admin_user, e, ApplicationStage.probation)
    await _funnel(db_session, organization, admin_user, e, ApplicationStage.screening, title="SEO")
    before = await _feed_rows(db_session, eid)
    r = await client.patch(f"/api/candidates/{eid}/status",
                           json={"status": target.value, "comment": "причина"}, headers=headers)
    assert r.status_code == 200, r.text
    assert await _feed_rows(db_session, eid) - before == 2
    db_session.expire_all()
    assert not ((await db_session.get(Entity, eid)).extra_data or {}).get("notes")
