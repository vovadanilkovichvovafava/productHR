"""
Тесты схлопывания легаси-клонов вакансий (reconcile_clones):
- dry_run не мутирует, но отдаёт точный отчёт
- реальный прогон переносит заявки клона в оригинал, дедупит по кандидату,
  мягко удаляет клон
- accepted_by спасается из клона только если у оригинала он пуст
- superadmin-гейт
"""
from datetime import datetime

import pytest
from sqlalchemy import select

from api.models.database import (
    Entity, EntityType, EntityStatus, Vacancy, VacancyApplication,
)


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _cand(db, org_id, name):
    e = Entity(org_id=org_id, type=EntityType.candidate, name=name, status=EntityStatus.new)
    db.add(e)
    await db.flush()
    return e


async def _vac(db, org_id, title, extra=None):
    v = Vacancy(org_id=org_id, title=title, extra_data=extra or {})
    db.add(v)
    await db.flush()
    return v


async def _app(db, vac_id, entity_id):
    a = VacancyApplication(vacancy_id=vac_id, entity_id=entity_id)
    db.add(a)
    await db.flush()
    return a


async def _entities_of(db, vac_id):
    return set((await db.execute(
        select(VacancyApplication.entity_id).where(VacancyApplication.vacancy_id == vac_id)
    )).scalars().all())


async def _deleted_at(db, vac_id):
    return (await db.execute(
        select(Vacancy.deleted_at).where(Vacancy.id == vac_id)
    )).scalar_one()


async def _accepted_by(db, vac_id):
    extra = (await db.execute(
        select(Vacancy.extra_data).where(Vacancy.id == vac_id)
    )).scalar_one() or {}
    return extra.get("accepted_by")


@pytest.mark.asyncio
async def test_reconcile_merges_clone_into_original(
    db_session, client, organization, superadmin_token
):
    original = await _vac(db_session, organization.id, "Трафик", {"accepted_by": [85, 86]})
    clone = await _vac(db_session, organization.id, "Трафик",
                       {"accepted_by": [51], "cloned_from_request_id": original.id})
    c1 = await _cand(db_session, organization.id, "Оригинальный 1")
    c2 = await _cand(db_session, organization.id, "Оригинальный 2")
    c3 = await _cand(db_session, organization.id, "Клоновый уникальный")
    await _app(db_session, original.id, c1.id)
    await _app(db_session, original.id, c2.id)
    await _app(db_session, clone.id, c2.id)   # общий → дедуп
    await _app(db_session, clone.id, c3.id)   # уникальный → перенос
    await db_session.commit()
    original_id, clone_id = original.id, clone.id
    c1i, c2i, c3i = c1.id, c2.id, c3.id

    # dry-run: отчёт есть, данные НЕ тронуты
    r = await client.post(
        "/api/vacancies/admin/reconcile-clones?dry_run=true", headers=_h(superadmin_token)
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["dry_run"] is True
    assert data["clones_found"] == 1
    assert data["merged"] == 1
    assert data["apps_moved"] == 1     # c3
    assert data["apps_deduped"] == 1   # c2
    db_session.expire_all()
    assert await _deleted_at(db_session, clone_id) is None
    assert len(await _entities_of(db_session, clone_id)) == 2

    # реальный прогон
    r2 = await client.post(
        "/api/vacancies/admin/reconcile-clones?dry_run=false", headers=_h(superadmin_token)
    )
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2["apps_moved"] == 1 and d2["apps_deduped"] == 1

    db_session.expire_all()
    assert await _deleted_at(db_session, clone_id) is not None  # клон мягко удалён
    assert await _entities_of(db_session, original_id) == {c1i, c2i, c3i}  # без дублей
    assert await _entities_of(db_session, clone_id) == set()  # заявок не осталось
    # accepted_by оригинала не тронут (был не пуст) — владелец клона (51) НЕ добавлен
    assert await _accepted_by(db_session, original_id) == [85, 86]


@pytest.mark.asyncio
async def test_reconcile_rescues_accepted_by_when_original_empty(
    db_session, client, organization, superadmin_token
):
    original = await _vac(db_session, organization.id, "Reverse", {})
    clone = await _vac(db_session, organization.id, "Reverse",
                       {"accepted_by": [51], "cloned_from_request_id": original.id})
    await db_session.commit()
    original_id = original.id

    r = await client.post(
        "/api/vacancies/admin/reconcile-clones?dry_run=false", headers=_h(superadmin_token)
    )
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["accepted_rescued"] is True
    db_session.expire_all()
    assert await _accepted_by(db_session, original_id) == [51]


@pytest.mark.asyncio
async def test_reconcile_skips_when_original_deleted(
    db_session, client, organization, superadmin_token
):
    original = await _vac(db_session, organization.id, "Осиротевший", {})
    clone = await _vac(db_session, organization.id, "Осиротевший",
                       {"cloned_from_request_id": original.id})
    original.deleted_at = datetime.utcnow()  # оригинал удалён
    await db_session.commit()
    clone_id = clone.id

    r = await client.post(
        "/api/vacancies/admin/reconcile-clones?dry_run=false", headers=_h(superadmin_token)
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["merged"] == 0 and d["skipped"] == 1
    db_session.expire_all()
    assert await _deleted_at(db_session, clone_id) is None  # клон не тронут


@pytest.mark.asyncio
async def test_reconcile_superadmin_only(
    db_session, client, organization, admin_token
):
    r = await client.post(
        "/api/vacancies/admin/reconcile-clones?dry_run=true", headers=_h(admin_token)
    )
    assert r.status_code == 403
