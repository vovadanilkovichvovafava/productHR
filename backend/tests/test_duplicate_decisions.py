"""Решения «разные люди» — отдельная таблица, переживают объединение (22.09.2026).

Раньше решение лежало в extra_data.dismissed_duplicate_ids и терялось при
слиянии: рекрутёр снова решал уже решённую пару.
"""
import pytest
from sqlalchemy import select

from api.models.database import (
    DataMigrationMark, DuplicatePairDecision, Entity, EntityStatus, EntityType,
)
from api.services.duplicate_decisions import (
    LEGACY_IMPORT_MARK, dismissed_for, import_legacy_once, mark_different, repoint_on_merge,
)
from api.services.similarity import detect_archived_duplicate, similarity_service


async def _mk(db, org_id, name, **kw):
    e = Entity(org_id=org_id, type=EntityType.candidate, name=name, status=EntityStatus.new, **kw)
    db.add(e)
    await db.flush()
    return e


async def _pairs(db):
    rows = (await db.execute(
        select(DuplicatePairDecision.entity_a_id, DuplicatePairDecision.entity_b_id)
    )).all()
    return {tuple(r) for r in rows}


@pytest.mark.asyncio
async def test_decision_is_one_row_visible_from_both_sides(db_session, organization):
    a = await _mk(db_session, organization.id, "Иван Иванов", email="same@x.com")
    b = await _mk(db_session, organization.id, "Иван Иванов", email="same@x.com")
    assert await mark_different(db_session, organization.id, b.id, a.id) is True
    assert await mark_different(db_session, organization.id, a.id, b.id) is False  # не дублируется
    assert await _pairs(db_session) == {(a.id, b.id)}
    assert b.id in await dismissed_for(db_session, a)
    assert a.id in await dismissed_for(db_session, b)
    # Ни одна сторона больше не предлагает другую.
    assert await detect_archived_duplicate(db_session, a) is None
    assert await detect_archived_duplicate(db_session, b) is None


@pytest.mark.asyncio
async def test_decision_survives_merge_of_the_decided_candidate(db_session, organization):
    # Главный сценарий бага: A и B — «разные люди». Потом A объединили с его
    # настоящим двойником A2 (выжил A2, A удалён). Раньше решение A пропадало, и
    # A2 ↔ B всплывало снова.
    a = await _mk(db_session, organization.id, "Иван Иванов", phone="+7 910 111-22-33")
    b = await _mk(db_session, organization.id, "Иван Иванов", email="other@x.com")
    a2 = await _mk(db_session, organization.id, "Иван Иванов", phone="8 910 1112233")
    await mark_different(db_session, organization.id, a.id, b.id)
    await db_session.commit()

    await similarity_service.merge_entities(db=db_session, source_entity=a, target_entity=a2)
    await db_session.commit()

    assert await _pairs(db_session) == {tuple(sorted((a2.id, b.id)))}
    assert b.id in await dismissed_for(db_session, a2)
    assert await detect_archived_duplicate(db_session, a2) is None


@pytest.mark.asyncio
async def test_repoint_drops_pair_between_merged_candidates(db_session, organization):
    # «Разные люди» между source и target после их слияния теряет смысл — удаляется.
    s = await _mk(db_session, organization.id, "Пётр Петров")
    t = await _mk(db_session, organization.id, "Пётр Петров")
    x = await _mk(db_session, organization.id, "Пётр Петров")
    await mark_different(db_session, organization.id, s.id, t.id)
    await mark_different(db_session, organization.id, s.id, x.id)
    await mark_different(db_session, organization.id, t.id, x.id)  # у target уже есть пара с x

    moved = await repoint_on_merge(db_session, s.id, t.id)
    assert moved == 0
    assert await _pairs(db_session) == {tuple(sorted((t.id, x.id)))}


@pytest.mark.asyncio
async def test_legacy_lists_are_imported_once(db_session, organization, second_organization):
    a = await _mk(db_session, organization.id, "Анна")
    b = await _mk(db_session, organization.id, "Анна", extra_data={})
    foreign = await _mk(db_session, second_organization.id, "Анна")
    a.extra_data = {"dismissed_duplicate_ids": [b.id, 999999, foreign.id, a.id]}
    b.extra_data = {"dismissed_duplicate_ids": [a.id]}
    await db_session.commit()

    assert await import_legacy_once(db_session) == 1
    # удалённая анкета (999999), чужая организация и сам себе — отброшены
    assert await _pairs(db_session) == {(a.id, b.id)}
    assert await db_session.get(DataMigrationMark, LEGACY_IMPORT_MARK) is not None
    assert await import_legacy_once(db_session) == 0  # второй старт ничего не делает


@pytest.mark.asyncio
async def test_dismiss_endpoint_repoints_other_side(
    client, db_session, organization, admin_user, org_owner, admin_token,
):
    # «Разные люди» на одной анкете снимает флаг, смотревший на неё, и у второй.
    a = await _mk(db_session, organization.id, "Олег Сидоров", email="os@x.com",
                  created_by=admin_user.id)
    b = await _mk(db_session, organization.id, "Олег Сидоров", email="os@x.com",
                  created_by=admin_user.id)
    a.extra_data = {"hidden_duplicate_id": b.id}
    b.extra_data = {"hidden_duplicate_id": a.id}
    await db_session.commit()

    r = await client.post(
        f"/api/entities/{a.id}/dismiss-duplicate",
        json={"duplicate_id": b.id}, headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    await db_session.refresh(a)
    await db_session.refresh(b)
    assert "hidden_duplicate_id" not in (a.extra_data or {})
    assert "hidden_duplicate_id" not in (b.extra_data or {})
    assert await _pairs(db_session) == {tuple(sorted((a.id, b.id)))}
