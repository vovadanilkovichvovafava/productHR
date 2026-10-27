"""Вакансия чужой организации — «не найдено», а не «нет доступа» (24.10.2026).

Иначе по разнице 403/404 перебором номеров видно, какие вакансии существуют.
Наблюдатель своей организации видит вакансии как раньше (владелец: «у
наблюдателя есть доступ, он лишь наблюдает — его ограничивать нельзя»).
"""
from datetime import datetime

from api.models.database import (
    ApplicationStage, Entity, EntityStatus, EntityType, OrgMember, OrgRole, Organization,
    User, Vacancy, VacancyApplication, VacancyStatus,
)
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _vacancy(db, org, dept, owner):
    now = datetime.utcnow()
    v = Vacancy(org_id=org.id, department_id=dept.id, created_by=owner.id, title="Трафик",
                status=VacancyStatus.open, salary_currency="RUB", created_at=now, updated_at=now)
    e = Entity(org_id=org.id, type=EntityType.candidate, name="Анна", status=EntityStatus.new, created_by=owner.id)
    db.add_all([v, e])
    await db.commit()
    a = VacancyApplication(vacancy_id=v.id, entity_id=e.id, stage=ApplicationStage.applied, stage_order=1,
                           created_by=owner.id, applied_at=now, last_stage_change_at=now, updated_at=now)
    db.add(a)
    await db.commit()
    return v, a


async def test_other_org_gets_not_found(client, db_session, organization, department, admin_user, org_owner):
    v, a = await _vacancy(db_session, organization, department, admin_user)
    other_org = Organization(name="Чужая", slug="chuzhaya")
    stranger = User(email="stranger@test.local", name="Чужой", password_hash="x", is_active=True)
    db_session.add_all([other_org, stranger])
    await db_session.commit()
    db_session.add(OrgMember(org_id=other_org.id, user_id=stranger.id, role=OrgRole.owner))
    await db_session.commit()

    for url in (f"/api/vacancies/{v.id}", f"/api/vacancies/{v.id}/applications",
                f"/api/vacancies/{v.id}/kanban"):
        r = await client.get(url, headers=_h(stranger))
        assert r.status_code == 404, (url, r.status_code, r.text)
    # Такой же ответ, как у несуществующей вакансии.
    assert (await client.get("/api/vacancies/999999", headers=_h(stranger))).status_code == 404
    # Заявка чужой вакансии по номеру — тоже «не найдено».
    r = await client.put(f"/api/vacancies/applications/{a.id}", json={"stage": "screening"}, headers=_h(stranger))
    assert r.status_code == 404, r.text


async def test_observer_of_same_org_still_sees(client, db_session, organization, department, admin_user, org_owner):
    v, _ = await _vacancy(db_session, organization, department, admin_user)
    observer = User(email="observer.v@test.local", name="Наблюдатель", password_hash="x", is_active=True)
    db_session.add(observer)
    await db_session.commit()
    db_session.add(OrgMember(org_id=organization.id, user_id=observer.id, role=OrgRole.admin, is_readonly=True))
    await db_session.commit()

    r = await client.get(f"/api/vacancies/{v.id}", headers=_h(observer))
    assert r.status_code == 200, r.text
    r = await client.get(f"/api/vacancies/{v.id}/applications", headers=_h(observer))
    assert r.status_code == 200, r.text
