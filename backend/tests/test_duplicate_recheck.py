"""Правка карточки сразу пересчитывает совпадения (этап 4 дедупа, 22.09.2026).

Раньше PUT /entities дублей не касался: новая плашка ждала повторного открытия
карточки, а после исправленной опечатки в телефоне старая висела у обеих анкет.
"""
from unittest.mock import patch

import pytest

from api.models.database import Entity, EntityStatus, EntityType
from api.services.duplicate_decisions import mark_different


async def _mk(db, org_id, name, **kw):
    e = Entity(org_id=org_id, type=EntityType.candidate, name=name, status=EntityStatus.new, **kw)
    db.add(e)
    await db.flush()
    return e


def _h(token):
    return {"Authorization": f"Bearer {token}"}


async def _put(client, token, eid, body):
    r = await client.put(f"/api/entities/{eid}", json=body, headers=_h(token))
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_new_phone_raises_flag_immediately(
    client, db_session, organization, admin_user, org_owner, admin_token,
):
    old = await _mk(db_session, organization.id, "Азиз Каримов", phone="+998 90 123-45-67",
                    created_by=admin_user.id)
    new = await _mk(db_session, organization.id, "Бекзод Рахимов", created_by=admin_user.id)
    await db_session.commit()

    body = await _put(client, admin_token, new.id, {"phone": "90 123 45 67"})
    # Ответ сохранения уже несёт плашку — интерфейс покажет её без перезагрузки.
    assert body["extra_data"]["hidden_duplicate_id"] == old.id
    assert body["extra_data"]["hidden_duplicate_meta"]["level"] == "possible"
    await db_session.refresh(old)
    assert old.extra_data["hidden_duplicate_id"] == new.id


@pytest.mark.asyncio
async def test_fixed_typo_clears_flag_on_both_sides(
    client, db_session, organization, admin_user, org_owner, admin_token,
):
    a = await _mk(db_session, organization.id, "Анна Смирнова", phone="+7 916 111-22-33",
                  created_by=admin_user.id)
    b = await _mk(db_session, organization.id, "Ольга Петрова", phone="+7 916 111-22-33",
                  created_by=admin_user.id)
    a.extra_data = {"hidden_duplicate_id": b.id, "hidden_duplicate_meta": {"strength": "phone", "level": "possible"}}
    b.extra_data = {"hidden_duplicate_id": a.id, "hidden_duplicate_meta": {"strength": "phone", "level": "possible"}}
    await db_session.commit()

    body = await _put(client, admin_token, b.id, {"phone": "+7 916 999-88-77"})
    assert "hidden_duplicate_id" not in body["extra_data"]
    assert "hidden_duplicate_meta" not in body["extra_data"]
    await db_session.refresh(a)
    assert "hidden_duplicate_id" not in (a.extra_data or {})


@pytest.mark.asyncio
async def test_non_identity_edit_does_not_recheck(
    client, db_session, organization, admin_user, org_owner, admin_token,
):
    e = await _mk(db_session, organization.id, "Анна Смирнова", created_by=admin_user.id)
    await db_session.commit()
    with patch("api.services.similarity.recheck_duplicates_after_edit",
               side_effect=AssertionError("пересчёт на правке должности")):
        await _put(client, admin_token, e.id, {"position": "Бухгалтер"})


@pytest.mark.asyncio
async def test_recheck_respects_different_people_decision(
    client, db_session, organization, admin_user, org_owner, admin_token,
):
    a = await _mk(db_session, organization.id, "Анна Смирнова", email="anna@x.com",
                  created_by=admin_user.id)
    b = await _mk(db_session, organization.id, "Ольга Петрова", created_by=admin_user.id)
    await mark_different(db_session, organization.id, a.id, b.id)
    await db_session.commit()

    body = await _put(client, admin_token, b.id, {"email": "anna@x.com"})
    assert "hidden_duplicate_id" not in body["extra_data"]


@pytest.mark.asyncio
async def test_text_twin_flag_survives_name_edit(
    client, db_session, organization, admin_user, org_owner, admin_token,
):
    # Совпадение по тексту резюме от ФИО не зависит — правка имени его не снимает.
    a = await _mk(db_session, organization.id, "Анна Смирнова", created_by=admin_user.id)
    b = await _mk(db_session, organization.id, "Ольга Петрова", created_by=admin_user.id)
    b.extra_data = {"hidden_duplicate_id": a.id,
                    "hidden_duplicate_meta": {"strength": "text", "confidence": 92, "matched_id": a.id}}
    await db_session.commit()

    body = await _put(client, admin_token, b.id, {"name": "Ольга Сергеевна Петрова"})
    assert body["extra_data"]["hidden_duplicate_id"] == a.id


@pytest.mark.asyncio
async def test_recheck_failure_does_not_break_save(
    client, db_session, organization, admin_user, org_owner, admin_token,
):
    e = await _mk(db_session, organization.id, "Анна Смирнова", created_by=admin_user.id)
    await db_session.commit()
    with patch("api.services.similarity.recheck_duplicates_after_edit",
               side_effect=RuntimeError("boom")):
        body = await _put(client, admin_token, e.id, {"phone": "+7 916 123-45-67"})
    assert body["phone"] == "+7 916 123-45-67"
