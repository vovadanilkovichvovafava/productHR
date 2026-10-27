"""«В предыдущих сериях» — сегментация откликов при переоткрытии вакансии.

Проверяем:
- reopened_at проставляется СТРОГО на переходе closed→open (не paused/draft→open);
- is_previous_series=true для отклика старше reopened_at, false если новее / если
  reopened_at IS NULL;
- фоллбэк на applied_at, когда last_stage_change_at NULL.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from api.models.database import (
    Vacancy, VacancyApplication, VacancyStatus, ApplicationStage,
    Entity, EntityType, EntityStatus, Organization, User,
)
from api.services.auth import create_access_token


def _h(u: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _mk_vacancy(db, org, user, status=VacancyStatus.open, reopened_at=None) -> Vacancy:
    v = Vacancy(
        org_id=org.id, title="Test Vacancy", status=status,
        created_by=user.id, created_at=datetime.utcnow(), reopened_at=reopened_at,
    )
    db.add(v)
    await db.commit()
    await db.refresh(v)
    return v


async def _mk_application(db, vacancy, org, user, last_change=None, applied=None) -> VacancyApplication:
    ent = Entity(
        org_id=org.id, created_by=user.id, name="Cand",
        type=EntityType.candidate, status=EntityStatus.new, created_at=datetime.utcnow(),
    )
    db.add(ent)
    await db.commit()
    await db.refresh(ent)
    app = VacancyApplication(
        vacancy_id=vacancy.id, entity_id=ent.id, stage=ApplicationStage.interview,
        stage_order=1, created_by=user.id,
        applied_at=applied or datetime.utcnow(),
        last_stage_change_at=last_change,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


@pytest.mark.asyncio
async def test_reopen_sets_reopened_at_only_on_closed_to_open(
    client, db_session, organization, admin_user, org_owner
):
    closed = await _mk_vacancy(db_session, organization, admin_user, status=VacancyStatus.closed)
    r = await client.put(f"/api/vacancies/{closed.id}", headers=_h(admin_user), json={"status": "open"})
    assert r.status_code == 200, r.text
    assert r.json()["reopened_at"] is not None

    # paused→open НЕ считается переоткрытием «серии»
    paused = await _mk_vacancy(db_session, organization, admin_user, status=VacancyStatus.paused)
    r2 = await client.put(f"/api/vacancies/{paused.id}", headers=_h(admin_user), json={"status": "open"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["reopened_at"] is None


@pytest.mark.asyncio
async def test_previous_series_flag_by_date(
    client, db_session, organization, admin_user, org_owner
):
    reopened = datetime.utcnow()
    v = await _mk_vacancy(db_session, organization, admin_user, reopened_at=reopened)
    # старый отклик (двигался ДО переоткрытия) → previous series
    await _mk_application(db_session, v, organization, admin_user, last_change=reopened - timedelta(days=1))
    # свежий отклик (после переоткрытия) → активный
    await _mk_application(db_session, v, organization, admin_user, last_change=reopened + timedelta(hours=1))

    r = await client.get(f"/api/vacancies/{v.id}/applications", headers=_h(admin_user))
    assert r.status_code == 200, r.text
    flags = sorted(a["is_previous_series"] for a in r.json())
    assert flags == [False, True]


@pytest.mark.asyncio
async def test_no_reopen_means_no_previous_series(
    client, db_session, organization, admin_user, org_owner
):
    v = await _mk_vacancy(db_session, organization, admin_user, reopened_at=None)
    await _mk_application(db_session, v, organization, admin_user,
                          last_change=datetime.utcnow() - timedelta(days=30))
    r = await client.get(f"/api/vacancies/{v.id}/applications", headers=_h(admin_user))
    assert r.status_code == 200, r.text
    assert all(a["is_previous_series"] is False for a in r.json())


@pytest.mark.asyncio
async def test_null_last_stage_change_falls_back_to_applied_at(
    client, db_session, organization, admin_user, org_owner
):
    reopened = datetime.utcnow()
    v = await _mk_vacancy(db_session, organization, admin_user, reopened_at=reopened)
    # last_stage_change_at NULL, applied_at ДО переоткрытия → previous series по applied_at
    await _mk_application(db_session, v, organization, admin_user,
                          last_change=None, applied=reopened - timedelta(days=2))
    r = await client.get(f"/api/vacancies/{v.id}/applications", headers=_h(admin_user))
    assert r.status_code == 200, r.text
    assert r.json()[0]["is_previous_series"] is True
