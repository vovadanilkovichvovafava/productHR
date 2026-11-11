"""Две живые вакансии с одним названием — нельзя (Мария, 11.11.2026).

Влада и Эльвира завели каждая свой «Video Editor»: кандидаты разошлись по двум
воронкам, у одного человека два этапа и две истории. Теперь создание,
переименование и переоткрытие в уже занятое название — 409 с понятным
текстом. Название сравнивается без регистра, «ё» и лишних пробелов; закрытые
и удалённые вакансии не мешают.
"""
from datetime import datetime

from api.models.database import Vacancy, VacancyStatus
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _vac(db, org, user, title, status=VacancyStatus.open, deleted=False):
    v = Vacancy(
        org_id=org.id, title=title, status=status, created_by=user.id, salary_currency="RUB",
        extra_data={"accepted_by": [user.id]}, created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        deleted_at=datetime.utcnow() if deleted else None,
    )
    db.add(v)
    await db.commit()
    await db.refresh(v)
    return v


async def test_create_with_taken_title_is_409(client, db_session, organization, admin_user, org_owner):
    v = await _vac(db_session, organization, admin_user, "Video Editor")
    r = await client.post("/api/vacancies", json={"title": "  video  EDITOR ", "status": "open"}, headers=_h(admin_user))
    assert r.status_code == 409, r.text
    assert f"№{v.id}" in r.json()["detail"] and "Video Editor" in r.json()["detail"]


async def test_yo_and_e_are_the_same(client, db_session, organization, admin_user, org_owner):
    await _vac(db_session, organization, admin_user, "Сорсёр")
    r = await client.post("/api/vacancies", json={"title": "Сорсер", "status": "open"}, headers=_h(admin_user))
    assert r.status_code == 409, r.text


async def test_closed_and_deleted_do_not_block(client, db_session, organization, admin_user, org_owner):
    await _vac(db_session, organization, admin_user, "Трафик", status=VacancyStatus.closed)
    await _vac(db_session, organization, admin_user, "Трафик", deleted=True)
    r = await client.post("/api/vacancies", json={"title": "Трафик", "status": "open"}, headers=_h(admin_user))
    assert r.status_code == 201, r.text


async def test_rename_into_taken_title_is_409_but_saving_same_title_is_ok(
    client, db_session, organization, admin_user, org_owner,
):
    await _vac(db_session, organization, admin_user, "Video Editor")
    other = await _vac(db_session, organization, admin_user, "SEO")
    oid = other.id
    r = await client.put(f"/api/vacancies/{oid}", json={"title": "Video editor"}, headers=_h(admin_user))
    assert r.status_code == 409, r.text
    r = await client.put(f"/api/vacancies/{oid}", json={"title": "SEO", "description": "x"}, headers=_h(admin_user))
    assert r.status_code == 200, r.text


async def test_reopening_closed_duplicate_is_409(client, db_session, organization, admin_user, org_owner):
    await _vac(db_session, organization, admin_user, "Трафик")
    old = await _vac(db_session, organization, admin_user, "Трафик", status=VacancyStatus.closed)
    r = await client.put(f"/api/vacancies/{old.id}", json={"status": "open"}, headers=_h(admin_user))
    assert r.status_code == 409, r.text
