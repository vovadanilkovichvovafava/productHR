"""Фильтр «Кандидаты: <рекрутёр>» над воронкой (владелец, 21.10.2026).

По умолчанию каждый видит своих; в фильтре выбирают любого рекрутёра воронки
или «Все рекрутёры» — и смотрят (и правят) их кандидатов. Это касается всех и
любой воронки, в том числе скрытой («Скрыта от коллег»).
"""
from datetime import datetime

import pytest
import pytest_asyncio

from api.models.database import (
    ApplicationStage, DepartmentFeature, Entity, EntityStatus, EntityType,
    Vacancy, VacancyApplication, VacancyStatus,
)
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


@pytest_asyncio.fixture(autouse=True)
async def candidate_database_feature(db_session, organization):
    db_session.add(DepartmentFeature(
        org_id=organization.id, department_id=None,
        feature_name="candidate_database", enabled=True,
    ))
    await db_session.commit()


@pytest_asyncio.fixture
async def hidden_funnel(db_session, organization, admin_user, second_user, org_owner, org_member):
    """Скрытая воронка: два кандидата у админа, один у рекрутёра, один без
    автора (старые данные — считается за владельцем вакансии, админом)."""
    v = Vacancy(
        org_id=organization.id, title="Трафик", status=VacancyStatus.open,
        created_by=admin_user.id, visible_to_all=False,
        assigned_to=[second_user.id],
        extra_data={"accepted_by": [admin_user.id, second_user.id]},
        created_at=datetime.utcnow(),
    )
    db_session.add(v)
    await db_session.commit()
    await db_session.refresh(v)
    ids = {}
    for name, author in (("Админский 1", admin_user.id), ("Админский 2", admin_user.id),
                         ("Рекрутёрский", second_user.id), ("Без автора", None)):
        e = Entity(org_id=organization.id, created_by=author or admin_user.id, name=name,
                   type=EntityType.candidate, status=EntityStatus.new, created_at=datetime.utcnow())
        db_session.add(e)
        await db_session.commit()
        await db_session.refresh(e)
        db_session.add(VacancyApplication(
            vacancy_id=v.id, entity_id=e.id, stage=ApplicationStage.applied, stage_order=1,
            created_by=author, applied_at=datetime.utcnow(),
        ))
        await db_session.commit()
        ids[name] = e.id
    return v.id, ids, admin_user.id, second_user.id


def _names(resp, ids):
    by_id = {v: k for k, v in ids.items()}
    return {by_id[a["entity_id"]] for a in resp.json()}


@pytest.mark.asyncio
async def test_recruiter_sees_own_by_default_and_colleague_on_request(client, second_user, hidden_funnel):
    v_id, ids, admin_id, _ = hidden_funnel
    H = _h(second_user)
    mine = await client.get(f"/api/vacancies/{v_id}/applications?created_by={second_user.id}", headers=H)
    assert mine.status_code == 200, mine.text
    assert _names(mine, ids) == {"Рекрутёрский"}
    # Выбрал в фильтре коллегу (админа) — видит его кандидатов, включая без автора.
    theirs = await client.get(f"/api/vacancies/{v_id}/applications?created_by={admin_id}", headers=H)
    assert _names(theirs, ids) == {"Админский 1", "Админский 2", "Без автора"}
    both = await client.get(f"/api/vacancies/{v_id}/applications?created_by={admin_id}&created_by={second_user.id}", headers=H)
    assert _names(both, ids) == set(ids)
    everyone = await client.get(f"/api/vacancies/{v_id}/applications?all_recruiters=true", headers=H)
    assert _names(everyone, ids) == set(ids)


@pytest.mark.asyncio
async def test_recruiters_list_with_counts(client, second_user, hidden_funnel):
    v_id, _, admin_id, recruiter_id = hidden_funnel
    r = await client.get(f"/api/vacancies/{v_id}/applications/recruiters", headers=_h(second_user))
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 4
    rows = r.json()["recruiters"]
    # Сначала сам смотрящий, потом остальные.
    assert rows[0]["user_id"] == recruiter_id and rows[0]["count"] == 1
    assert {x["user_id"]: x["count"] for x in rows} == {recruiter_id: 1, admin_id: 3}
    assert all(x["name"] for x in rows)


@pytest.mark.asyncio
async def test_recruiter_moves_colleague_candidate(client, db_session, second_user, hidden_funnel):
    v_id, ids, _, _ = hidden_funnel
    from sqlalchemy import select
    app_id = (await db_session.execute(
        select(VacancyApplication.id).where(VacancyApplication.entity_id == ids["Админский 1"])
    )).scalar()
    r = await client.put(f"/api/vacancies/applications/{app_id}", json={"stage": "screening"},
                         headers=_h(second_user))
    assert r.status_code == 200, r.text
    assert r.json()["stage"] == "screening"


@pytest.mark.asyncio
async def test_outsider_of_other_org_gets_nothing(client, db_session, hidden_funnel, second_organization):
    """Фильтр не открывает чужую организацию: доступ к вакансии проверяется как раньше."""
    from api.models.database import OrgMember, OrgRole, User
    from api.services.auth import hash_password
    stranger = User(email="stranger@test.local", password_hash=hash_password("x"), name="Чужой", is_active=True)
    db_session.add(stranger)
    await db_session.flush()
    db_session.add(OrgMember(org_id=second_organization.id, user_id=stranger.id, role=OrgRole.admin))
    await db_session.commit()
    await db_session.refresh(stranger)
    v_id = hidden_funnel[0]
    r = await client.get(f"/api/vacancies/{v_id}/applications?all_recruiters=true", headers=_h(stranger))
    assert r.status_code in (403, 404)
    r = await client.get(f"/api/vacancies/{v_id}/applications/recruiters", headers=_h(stranger))
    assert r.status_code in (403, 404)
