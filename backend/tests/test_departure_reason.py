"""«Мы уволили» / «Сам уволился» — только с причиной (Мария, 12.11.2026).

«Рекрутер при переводе на статус обязательно должен указать причину
увольнения, без причины — не переведётся, она и будет видна на борде».
Причина живёт в поле карточки `rejection_reason` — его показывает колонка
«Причина отказа» на доске «Штат».
"""
from datetime import datetime

import pytest
from sqlalchemy import select

from api.models.database import Entity, EntityStatus, EntityType
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _person(db, org, user, status=EntityStatus.transferred):
    e = Entity(org_id=org.id, created_by=user.id, name="Пётр Уходящий",
               type=EntityType.candidate, status=status, created_at=datetime.utcnow())
    db.add(e)
    await db.commit()
    return e


async def _fresh(db, eid):
    return (await db.execute(
        select(Entity).where(Entity.id == eid).execution_options(populate_existing=True)
    )).scalar_one()


async def _reason(db, eid):
    e = await _fresh(db, eid)
    return (e.extra_data or {}).get("rejection_reason"), e.status


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["dismissed", "quit"])
async def test_card_requires_reason(client, db_session, organization, admin_user, org_owner, status):
    e = await _person(db_session, organization, admin_user)
    eid = e.id
    url = f"/api/candidates/{eid}/status"

    for empty in (None, "", "   ", "<p><br></p>"):
        r = await client.patch(url, json={"status": status, "comment": empty}, headers=_h(admin_user))
        assert r.status_code == 400, r.text
        assert "причину увольнения" in r.json()["detail"]
    assert (await _reason(db_session, eid))[1] == EntityStatus.transferred

    r = await client.patch(url, json={"status": status, "comment": "<p>Не прошёл испытательный</p>"},
                           headers=_h(admin_user))
    assert r.status_code == 200, r.text
    reason, st = await _reason(db_session, eid)
    assert st.value == status
    assert reason == "Не прошёл испытательный"


@pytest.mark.asyncio
async def test_board_requires_reason_and_shows_it(client, db_session, organization, admin_user, org_owner):
    e = await _person(db_session, organization, admin_user)
    eid = e.id
    url = f"/api/staff-board/rows/{eid}"

    r = await client.patch(url, json={"status": "dismissed"}, headers=_h(admin_user))
    assert r.status_code == 400, r.text
    assert (await _reason(db_session, eid))[1] == EntityStatus.transferred

    r = await client.patch(url, json={"status": "dismissed", "rejection_reason": "Прогулы"},
                           headers=_h(admin_user))
    assert r.status_code == 200, r.text
    assert r.json()["rejection_reason"] == "Прогулы"
    reason, st = await _reason(db_session, eid)
    assert st == EntityStatus.dismissed
    assert reason == "Прогулы"
    # Перевод виден в ленте вместе с причиной.
    e = await _fresh(db_session, eid)
    note = (e.extra_data or {}).get("notes", [])[-1]
    assert note["stage"] == "dismissed" and note["text"] == "Прогулы"

    # Уволен → Уволился: это тоже новый статус, причина нужна снова.
    r = await client.patch(url, json={"status": "quit"}, headers=_h(admin_user))
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_other_board_statuses_need_no_reason(client, db_session, organization, admin_user, org_owner):
    e = await _person(db_session, organization, admin_user, status=EntityStatus.probation)
    r = await client.patch(f"/api/staff-board/rows/{e.id}", json={"status": "transferred"},
                           headers=_h(admin_user))
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_direct_status_paths_cannot_dismiss(client, db_session, organization, admin_user, org_owner):
    """Правка карточки и PATCH /entities/{id}/status причины не несут — уволить
    через них нельзя (интерфейс их для этого не зовёт)."""
    e = await _person(db_session, organization, admin_user)
    r = await client.patch(f"/api/entities/{e.id}/status", json={"status": "dismissed"},
                           headers=_h(admin_user))
    assert r.status_code == 400, r.text
    r = await client.put(f"/api/entities/{e.id}", json={"status": "quit"}, headers=_h(admin_user))
    assert r.status_code == 400, r.text
    assert (await _reason(db_session, e.id))[1] == EntityStatus.transferred
