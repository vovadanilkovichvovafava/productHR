"""«Мы уволили» / «Сам уволился» из карточки «Все кандидаты» (10.11.2026).

Мария утвердила список статусов базы, где у уволенных свои вкладки. Раньше
поставить их можно было только с доски «Штат»; из карточки кандидат в
воронке получал «этот этап нельзя поставить заявке». Теперь — то же правило,
что у доски: все живые заявки закрываются «Отказом», статус точный, в ленте
запись (её корзина вернёт прежний статус).

18.11.2026 (Мария: «поменяла статус на „мы уволили“, а получила 2 статуса»):
одно действие — одна строка. Есть воронки — строка это перевод заявки
«Мы уволили — причина», отдельной записи-комментария нет; воронок нет —
только запись-комментарий.
"""
from datetime import datetime

import pytest
from sqlalchemy import select

from api.models.database import (
    ApplicationStage, StageTransition, Entity, EntityStatus, EntityType, Vacancy, VacancyApplication, VacancyStatus,
)
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _vac(db, org, user, title):
    now = datetime.utcnow()
    v = Vacancy(org_id=org.id, created_by=user.id, title=title, status=VacancyStatus.open,
                salary_currency="RUB", created_at=now, updated_at=now, visible_to_all=True)
    db.add(v)
    await db.commit()
    return v


@pytest.mark.asyncio
@pytest.mark.parametrize("status, label", [("dismissed", "Мы уволили"), ("quit", "Сам уволился")])
async def test_depart_closes_every_funnel(
    client, db_session, organization, admin_user, org_owner, status, label,
):
    traffic = await _vac(db_session, organization, admin_user, "Трафик")
    seo = await _vac(db_session, organization, admin_user, "SEO")
    e = Entity(org_id=organization.id, created_by=admin_user.id, name="Пётр Уходящий",
               type=EntityType.candidate, status=EntityStatus.transferred, created_at=datetime.utcnow())
    db_session.add(e)
    await db_session.commit()
    eid = e.id
    headers = _h(admin_user)
    now = datetime.utcnow()
    for v, stage in ((traffic, ApplicationStage.transferred), (seo, ApplicationStage.screening)):
        db_session.add(VacancyApplication(vacancy_id=v.id, entity_id=e.id, stage=stage, stage_order=1,
                                          created_by=admin_user.id, applied_at=now,
                                          last_stage_change_at=now, updated_at=now))
    await db_session.commit()

    r = await client.patch(f"/api/candidates/{e.id}/status",
                           json={"status": status, "comment": "по собственному"},
                           headers=headers)
    assert r.status_code == 200, r.text  # две воронки — не 409
    assert r.json()["entity_status"] == status
    assert r.json()["note"] is None  # строка в ленте — перевод заявки, не дубль

    db_session.expire_all()
    ent = await db_session.get(Entity, eid)
    assert not [n for n in (ent.extra_data or {}).get("notes") or [] if n.get("stage")]
    comments = (await db_session.execute(
        select(StageTransition.comment).where(StageTransition.entity_id == eid)
    )).scalars().all()
    assert comments == [f"{label} — по собственному"] * 2

    db_session.expire_all()
    stages = (await db_session.execute(
        select(VacancyApplication.stage).where(VacancyApplication.entity_id == eid)
    )).scalars().all()
    assert set(stages) == {ApplicationStage.rejected}
    board = (await client.get("/api/candidates/kanban", headers=headers)).json()
    cols = {c["status"]: c for c in board["columns"]}
    assert cols[status]["label"] == label
    assert eid in [c["id"] for c in cols[status]["cards"]]


@pytest.mark.asyncio
async def test_depart_without_funnels_writes_one_note(client, db_session, organization, admin_user, org_owner):
    e = Entity(org_id=organization.id, created_by=admin_user.id, name="Без Воронок",
               type=EntityType.candidate, status=EntityStatus.transferred, created_at=datetime.utcnow())
    db_session.add(e)
    await db_session.commit()
    eid = e.id
    r = await client.patch(f"/api/candidates/{eid}/status",
                           json={"status": "dismissed", "comment": "прогулы"},
                           headers=_h(admin_user))
    assert r.status_code == 200, r.text
    assert r.json()["note"]["stage"] == "dismissed"
    db_session.expire_all()
    ent = await db_session.get(Entity, eid)
    stage_notes = [n for n in (ent.extra_data or {}).get("notes") or [] if n.get("stage")]
    assert len(stage_notes) == 1 and stage_notes[0]["text"] == "прогулы"
    assert ent.status == EntityStatus.dismissed
