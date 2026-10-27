"""Отметки у вех — не только галочка (Мария, 28.09.2026).

В ClickUp в этих колонках ставили ✓, ✗, месяц («Сентябрь») или «Бонус
сотруднику». Раньше у нас была булева галочка, а импортированные месяцы
превращались в неё же — понять, что там стоял «Сентябрь», было нельзя.
"""
from datetime import datetime

import pytest

from api.models.database import Entity, EntityStatus, EntityType
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _person(db, org, creator, extra=None):
    e = Entity(
        org_id=org.id, name="Вехин Вадим", type=EntityType.candidate,
        status=EntityStatus.transferred, created_by=creator.id,
        created_at=datetime.utcnow(), extra_data=extra or {},
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


async def _row(client, user, eid):
    r = await client.get("/api/staff-board/rows", headers=_h(user))
    assert r.status_code == 200, r.text
    return next(x for x in r.json() if x["entity_id"] == eid)


@pytest.mark.asyncio
@pytest.mark.parametrize("mark", ["✓", "✗", "Сентябрь", "Бонус сотруднику"])
async def test_mark_is_saved_as_text(client, db_session, organization, admin_user, org_owner, mark):
    e = await _person(db_session, organization, admin_user)
    r = await client.patch(
        f"/api/staff-board/rows/{e.id}", json={"dept_done": mark}, headers=_h(admin_user)
    )
    assert r.status_code == 200, r.text
    assert r.json()["dept_done"] == mark
    assert (await _row(client, admin_user, e.id))["dept_done"] == mark


@pytest.mark.asyncio
async def test_mark_can_be_cleared(client, db_session, organization, admin_user, org_owner):
    e = await _person(db_session, organization, admin_user)
    await client.patch(f"/api/staff-board/rows/{e.id}", json={"m1_done": "Май"}, headers=_h(admin_user))
    r = await client.patch(f"/api/staff-board/rows/{e.id}", json={"m1_done": None}, headers=_h(admin_user))
    assert not r.json()["m1_done"]


@pytest.mark.asyncio
async def test_junk_mark_rejected(client, db_session, organization, admin_user, org_owner):
    e = await _person(db_session, organization, admin_user)
    r = await client.patch(
        f"/api/staff-board/rows/{e.id}", json={"y1_done": "что попало"}, headers=_h(admin_user)
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_old_checkbox_reads_as_tick(client, db_session, organization, admin_user, org_owner):
    """Старая булева галочка и импорт из ClickUp читаются как «✓» и месяц."""
    e = await _person(db_session, organization, admin_user, {
        "w2_done": True,
        "cf:(3 мес)": "Сентябрь",
    })
    row = await _row(client, admin_user, e.id)
    assert row["w2_done"] == "✓"
    assert row["m3_done"] == "Сентябрь"
