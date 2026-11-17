"""«Скрыта от коллег» — вакансию видят только свои (владелец, 17.11.2026).

Раньше флаг прятал заявку только из списков «Заявки»: рекрутёр, которого не
назначали, открывал её через выбор владельца в «Мои вакансии» или по ссылке и
видел кандидатов. Теперь чужому рекрутёру скрытая вакансия — 404 и её нет ни
в списке вакансий, ни в блоках воронок карточки, ни в чипах списка кандидатов.
Видят: админы/владелец/суперадмин, автор, назначенные, взявшие, и те, у кого
в воронке свои кандидаты (services/private_vacancy.py).
"""
from datetime import datetime

import pytest
import pytest_asyncio

from api.models.database import (
    ApplicationStage, DepartmentFeature, Entity, EntityStatus, EntityType, OrgMember, OrgRole,
    Vacancy, VacancyApplication, VacancyStatus,
)
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


@pytest_asyncio.fixture
async def setup(db_session, organization, admin_user, second_user, regular_user, org_owner):
    db_session.add(DepartmentFeature(org_id=organization.id, department_id=None,
                                     feature_name="candidate_database", enabled=True))
    for u in (second_user, regular_user):  # оба — рекрутёры (hr)
        db_session.add(OrgMember(org_id=organization.id, user_id=u.id, role=OrgRole.hr,
                                 created_at=datetime.utcnow()))
    hidden = Vacancy(org_id=organization.id, title="Скрытая Петра", status=VacancyStatus.open,
                     created_by=admin_user.id, visible_to_all=False, assigned_to=[second_user.id],
                     extra_data={"accepted_by": [second_user.id]}, created_at=datetime.utcnow())
    shared = Vacancy(org_id=organization.id, title="Общая", status=VacancyStatus.open,
                     created_by=admin_user.id, visible_to_all=True, assigned_to=[second_user.id],
                     created_at=datetime.utcnow())
    db_session.add_all([hidden, shared])
    await db_session.commit()
    e = Entity(org_id=organization.id, created_by=second_user.id, name="Кандидат Скрытой",
               type=EntityType.candidate, status=EntityStatus.new, created_at=datetime.utcnow())
    db_session.add(e)
    await db_session.commit()
    db_session.add(VacancyApplication(vacancy_id=hidden.id, entity_id=e.id, stage=ApplicationStage.applied,
                                      stage_order=1, created_by=second_user.id, applied_at=datetime.utcnow()))
    await db_session.commit()
    return hidden, shared, e


def _ids(resp):
    return {v["id"] for v in resp.json()}


@pytest.mark.asyncio
async def test_outsider_recruiter_does_not_see_hidden_vacancy(client, setup, regular_user):
    hidden, shared, e = setup
    h = _h(regular_user)
    ids = _ids(await client.get("/api/vacancies", headers=h))
    assert shared.id in ids and hidden.id not in ids
    assert (await client.get(f"/api/vacancies/{hidden.id}", headers=h)).status_code == 404
    assert (await client.get(f"/api/vacancies/{hidden.id}/applications?all_recruiters=true",
                             headers=h)).status_code == 404
    # Карточка кандидата открыта (кандидаты общие), но блока скрытой воронки нет.
    act = await client.get(f"/api/entities/{e.id}/activity", headers=h)
    assert act.status_code == 200
    assert all(b.get("vacancy_id") != hidden.id for b in act.json())
    board = (await client.get("/api/candidates/kanban", headers=h)).json()
    card = next(c for col in board["columns"] for c in col["cards"] if c["id"] == e.id)
    assert all(f["vacancy_title"] != "Скрытая Петра" for f in card.get("funnels") or [])


@pytest.mark.asyncio
async def test_assigned_owner_and_admin_see_hidden_vacancy(client, setup, second_user, admin_user):
    hidden, _, e = setup
    for u in (second_user, admin_user):
        h = _h(u)
        assert hidden.id in _ids(await client.get("/api/vacancies", headers=h))
        assert (await client.get(f"/api/vacancies/{hidden.id}", headers=h)).status_code == 200
        act = (await client.get(f"/api/entities/{e.id}/activity", headers=h)).json()
        assert any(b.get("vacancy_id") == hidden.id for b in act)


@pytest.mark.asyncio
async def test_visible_to_colleagues_opens_it_again(client, db_session, setup, regular_user):
    hidden, _, _ = setup
    hidden.visible_to_all = True
    await db_session.commit()
    h = _h(regular_user)
    assert hidden.id in _ids(await client.get("/api/vacancies", headers=h))
    assert (await client.get(f"/api/vacancies/{hidden.id}", headers=h)).status_code == 200


@pytest.mark.asyncio
async def test_own_candidates_keep_hidden_vacancy_visible(client, db_session, setup, regular_user):
    """Кто ведёт в скрытой воронке своих кандидатов (сняли с назначения, а люди
    остались) — доступ к ним не теряет."""
    hidden, _, _ = setup
    e2 = Entity(org_id=hidden.org_id, created_by=regular_user.id, name="Свой", type=EntityType.candidate,
                status=EntityStatus.new, created_at=datetime.utcnow())
    db_session.add(e2)
    await db_session.commit()
    db_session.add(VacancyApplication(vacancy_id=hidden.id, entity_id=e2.id, stage=ApplicationStage.applied,
                                      stage_order=2, created_by=regular_user.id, applied_at=datetime.utcnow()))
    await db_session.commit()
    assert (await client.get(f"/api/vacancies/{hidden.id}", headers=_h(regular_user))).status_code == 200
