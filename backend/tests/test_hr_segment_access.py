"""Права HR-раздела: сотрудник без HR-роли не читает и не трогает базу.

Найдено при разборе и подтверждено на копиях базы 12.11.2026: пользователь с
ролью member (без HR-раздела — в меню его нет, закрыт был только интерфейс)
через API читал всех кандидатов (`/candidates/kanban` отдал 49 из 49), любую
карточку (`/entities/{id}`), список вакансий, удалял карточки массовой ручкой
мимо корзины и правил строки доски «Штат».

Правило: HR-раздел = superadmin, owner, admin, hr и «Наблюдатель»
(`has_hr_segment`). Роутеры кандидатов, воронок, «Штата» и старой «Базы
кандидатов» закрыты целиком (403). Карточка — через `check_entity_access`: у
сотрудника остаются только ЯВНЫЕ связи (сам добавил, расшарили, нанимающий
менеджер / назначен на вакансию), чужая карточка — 404, как везде.
"""
from datetime import datetime

import pytest
from sqlalchemy import select

from api.models.database import (
    AccessLevel, Entity, EntityStatus, EntityType, OrgMember, OrgRole,
    ResourceType, SharedAccess, User, Vacancy, VacancyApplication, VacancyStatus,
    ApplicationStage, DepartmentFeature,
)
from api.services.auth import create_access_token

pytestmark = pytest.mark.asyncio


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _user(db, org, email, role, readonly=False):
    u = User(email=email, name=email.split("@")[0], password_hash="x", is_active=True)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    db.add(OrgMember(org_id=org.id, user_id=u.id, role=role, is_readonly=readonly))
    await db.commit()
    return u


async def _candidate(db, org, creator, name="Кандидатов Пётр"):
    e = Entity(
        org_id=org.id, name=name, type=EntityType.candidate,
        status=EntityStatus.probation, created_by=creator.id,
        created_at=datetime.utcnow(), extra_data={},
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


async def _vacancy(db, org, creator, **kw):
    v = Vacancy(org_id=org.id, title="Трафик", status=VacancyStatus.open,
                created_by=creator.id, **kw)
    db.add(v)
    await db.commit()
    await db.refresh(v)
    return v


@pytest.fixture(autouse=True)
async def candidate_database_feature(db_session, organization):
    """Воронки у hr/admin ещё закрыты фичей отдела «candidate_database» — включаем,
    иначе тест проверял бы её, а не HR-раздел."""
    db_session.add(DepartmentFeature(
        org_id=organization.id, department_id=None,
        feature_name="candidate_database", enabled=True,
    ))
    await db_session.commit()


@pytest.fixture
async def people(db_session, organization, admin_user, org_owner, second_user, org_member):
    """owner (admin_user), member (second_user), hr, admin, наблюдатель."""
    hr = await _user(db_session, organization, "hr.seg@test.local", OrgRole.hr)
    adm = await _user(db_session, organization, "adm.seg@test.local", OrgRole.admin)
    obs = await _user(db_session, organization, "obs.seg@test.local", OrgRole.member, readonly=True)
    return {"owner": admin_user, "member": second_user, "hr": hr, "admin": adm, "observer": obs}


# Ручки ЧТЕНИЯ HR-раздела, которые закрыты для сотрудника без HR (403).
READ_URLS = [
    "/api/candidates/kanban",
    "/api/candidates/search",
    "/api/candidates/ids",
    "/api/candidates/recruiters",
    "/api/candidates/tags",
    "/api/vacancies",
    "/api/staff-board/rows",
    "/api/staff-board/departments",
    "/api/candidate-database",
    "/api/entities/trash",
]


@pytest.mark.parametrize("url", READ_URLS)
async def test_member_gets_403_on_hr_reads(client, people, url):
    r = await client.get(url, headers=_h(people["member"]))
    assert r.status_code == 403, (url, r.status_code, r.text)


@pytest.mark.parametrize("who", ["owner", "admin", "hr", "observer"])
async def test_hr_roles_still_read(client, db_session, organization, people, who):
    e = await _candidate(db_session, organization, people["owner"])
    v = await _vacancy(db_session, organization, people["owner"])
    u = people[who]
    urls = [
        "/api/candidates/recruiters",
        "/api/vacancies",
        f"/api/vacancies/{v.id}",
        "/api/staff-board/rows",
        f"/api/entities/{e.id}",
    ]
    for url in urls:
        r = await client.get(url, headers=_h(u))
        assert r.status_code == 200, (who, url, r.status_code, r.text)


async def test_member_cannot_open_foreign_card(client, db_session, organization, people):
    e = await _candidate(db_session, organization, people["owner"])
    r = await client.get(f"/api/entities/{e.id}", headers=_h(people["member"]))
    # 404, а не 403: сам факт существования карточки — тоже информация.
    assert r.status_code == 404, r.text
    # Мелкие ручки карточки, которые ходят мимо check_entity_access, — тоже.
    for url in (f"/api/tags/entities/{e.id}/tags", f"/api/entities/{e.id}/recommended-vacancies"):
        r = await client.get(url, headers=_h(people["member"]))
        assert r.status_code in (403, 404), (url, r.status_code, r.text)


async def test_member_card_via_public_vacancy_is_closed(client, db_session, organization, people):
    """«Вакансия видна всем» — это про рекрутёров; сотруднику карточку не открывает."""
    e = await _candidate(db_session, organization, people["owner"])
    v = await _vacancy(db_session, organization, people["owner"], visible_to_all=True)
    db_session.add(VacancyApplication(vacancy_id=v.id, entity_id=e.id, stage=ApplicationStage.applied))
    await db_session.commit()
    r = await client.get(f"/api/entities/{e.id}", headers=_h(people["member"]))
    assert r.status_code == 404, r.text


async def test_member_keeps_explicit_access(client, db_session, organization, people):
    """Законные случаи остаются: свой кандидат, расшаренный, нанимающий менеджер."""
    member = people["member"]
    own = await _candidate(db_session, organization, member, name="Свой Кандидат")
    shared = await _candidate(db_session, organization, people["owner"], name="Расшаренный Кандидат")
    db_session.add(SharedAccess(
        resource_type=ResourceType.entity, resource_id=shared.id, entity_id=shared.id,
        shared_by_id=people["owner"].id, shared_with_id=member.id, access_level=AccessLevel.view,
    ))
    managed = await _candidate(db_session, organization, people["owner"], name="Кандидат Менеджера")
    v = await _vacancy(db_session, organization, people["owner"], hiring_manager_id=member.id)
    db_session.add(VacancyApplication(vacancy_id=v.id, entity_id=managed.id, stage=ApplicationStage.applied))
    await db_session.commit()

    for e in (own, shared, managed):
        r = await client.get(f"/api/entities/{e.id}", headers=_h(member))
        assert r.status_code == 200, (e.name, r.status_code, r.text)


async def test_member_global_search_has_no_candidates(client, db_session, organization, people):
    await _candidate(db_session, organization, people["owner"], name="Искомый Кандидат")
    r = await client.get("/api/search/global", params={"query": "Искомый"}, headers=_h(people["member"]))
    assert r.status_code == 200, r.text
    assert r.json()["candidates"] == [] and r.json()["vacancies"] == []


async def test_member_bulk_delete_forbidden(client, db_session, organization, people):
    e = await _candidate(db_session, organization, people["owner"])
    r = await client.post("/api/candidates/bulk-action",
                          json={"entity_ids": [e.id], "action": "delete"}, headers=_h(people["member"]))
    assert r.status_code == 403, r.text
    eid = e.id
    db_session.expire_all()
    assert (await db_session.execute(select(Entity).where(Entity.id == eid))).scalar() is not None


@pytest.mark.parametrize("who", ["hr", "admin", "owner"])
async def test_bulk_delete_removed_for_everyone(client, db_session, organization, people, who):
    """Массового удаления нет: интерфейс его не зовёт, а ручка стирала мимо корзины
    и без проверки «удаляет автор или админ». Удаление — только из карточки."""
    e = await _candidate(db_session, organization, people["owner"])
    r = await client.post("/api/candidates/bulk-action",
                          json={"entity_ids": [e.id], "action": "delete"}, headers=_h(people[who]))
    assert r.status_code == 400, r.text
    eid = e.id
    db_session.expire_all()
    assert (await db_session.execute(select(Entity).where(Entity.id == eid))).scalar() is not None


async def test_member_cannot_patch_staff_board(client, db_session, organization, people):
    e = await _candidate(db_session, organization, people["owner"])
    r = await client.patch(f"/api/staff-board/rows/{e.id}",
                           json={"position": "Взломщик"}, headers=_h(people["member"]))
    assert r.status_code == 403, r.text
    # а рекрутёру — можно
    r = await client.patch(f"/api/staff-board/rows/{e.id}",
                           json={"position": "Медиабаер"}, headers=_h(people["hr"]))
    assert r.status_code == 200, r.text


async def test_candidate_database_merge_admin_only(client, db_session, organization, people):
    a = await _candidate(db_session, organization, people["owner"], name="Дубль Один")
    b = await _candidate(db_session, organization, people["owner"], name="Дубль Два")
    aid = a.id
    for who in ("member", "hr"):
        r = await client.post("/api/candidate-database/merge",
                              params={"source_id": a.id, "target_id": b.id}, headers=_h(people[who]))
        assert r.status_code == 403, (who, r.status_code, r.text)
    db_session.expire_all()
    assert (await db_session.execute(select(Entity).where(Entity.id == aid))).scalar() is not None
