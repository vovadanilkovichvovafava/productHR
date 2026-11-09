"""Скоуп по этапам: «видит только кандидатов на „Практике“» (09.11.2026).

Мария: «возможно дать доступ к кандидатам Владу и Егору, только на этапе
„практика“». Это наблюдатели-наставники: им нужны практиканты, а не вся база.

`org_members.scope_statuses` — список статусов кандидата. Пусто — ограничения
нет. Непустой — кандидат виден только в этих статусах, а в воронке — только
заявки на этих этапах. Складывается со скоупом по воронкам. Проверки стоят в
тех же горлышках, что и у скоупа по воронкам (`services/vacancy_scope.py`),
поэтому здесь проверяем именно горлышки: карточку, «Все кандидаты», воронку,
счётчики, историю заявки, блоки воронок в карточке.
"""
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import (
    ApplicationStage, Department, Entity, EntityStatus, EntityType, OrgMember,
    Organization, User, Vacancy, VacancyApplication, VacancyStatus,
)
from api.services.auth import create_access_token
from api.services.vacancy_scope import (
    Scope, application_scope_filter, clean_scope_statuses, entity_scope_filter,
)
from tests.conftest import auth_headers


def _headers(user: User) -> dict:
    return auth_headers(create_access_token(data={"sub": str(user.id)}))


def _sql(clause) -> str:
    return str(clause.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


async def _vacancy(db, org, dept, user, title):
    now = datetime.utcnow()
    v = Vacancy(
        org_id=org.id, department_id=dept.id, created_by=user.id, title=title,
        status=VacancyStatus.open, salary_currency="RUB", created_at=now, updated_at=now,
        visible_to_all=True,
    )
    db.add(v)
    await db.commit()
    return v


async def _entity(db, org, dept, user, name, status):
    e = Entity(
        org_id=org.id, department_id=dept.id, created_by=user.id, name=name,
        type=EntityType.candidate, status=status, created_at=datetime.utcnow(),
    )
    db.add(e)
    await db.commit()
    return e


async def _application(db, vacancy, entity, user, stage):
    now = datetime.utcnow()
    app = VacancyApplication(
        vacancy_id=vacancy.id, entity_id=entity.id, stage=stage, stage_order=1,
        created_by=user.id, applied_at=now, last_stage_change_at=now, updated_at=now,
    )
    db.add(app)
    await db.commit()
    return app


@pytest_asyncio.fixture
async def practice_only(
    db_session: AsyncSession, organization: Organization, department: Department,
    admin_user: User, org_owner: OrgMember, regular_user: User, org_admin: OrgMember,
):
    """regular_user — наблюдатель, видит только «Практику».

    * Практикант — на практике в «Трафике», а в «SEO» у него отказ;
    * Новичок — на этапе «Новый» в «Трафике»;
    * Без воронки — практикант вне воронок.
    """
    traffic = await _vacancy(db_session, organization, department, admin_user, "Трафик")
    seo = await _vacancy(db_session, organization, department, admin_user, "SEO")
    trainee = await _entity(db_session, organization, department, admin_user, "Практикант", EntityStatus.probation)
    newbie = await _entity(db_session, organization, department, admin_user, "Новичок", EntityStatus.new)
    loose = await _entity(db_session, organization, department, admin_user, "Без воронки", EntityStatus.probation)
    app_trainee = await _application(db_session, traffic, trainee, admin_user, ApplicationStage.probation)
    app_trainee_seo = await _application(db_session, seo, trainee, admin_user, ApplicationStage.rejected)
    app_newbie = await _application(db_session, traffic, newbie, admin_user, ApplicationStage.applied)
    org_admin.is_readonly = True
    org_admin.scope_statuses = ["probation"]
    await db_session.commit()
    return {
        "traffic": traffic, "seo": seo, "trainee": trainee, "newbie": newbie, "loose": loose,
        "app_trainee": app_trainee, "app_trainee_seo": app_trainee_seo, "app_newbie": app_newbie,
    }


# --- правила -----------------------------------------------------------------

def test_clean_statuses_drops_garbage_and_keeps_order():
    assert clean_scope_statuses(["probation", "мусор", "new"]) == ["new", "probation"]
    assert clean_scope_statuses([]) is None
    assert clean_scope_statuses(None) is None
    assert clean_scope_statuses(["мусор"]) is None


def test_scope_is_truthy_even_without_vacancies():
    """В организации без вакансий множество пустое — но ограничение есть.
    Места вида `if scope_ids:` не должны принять его за «без ограничения»."""
    assert bool(Scope((), statuses={"probation"}, all_vacancies=True)) is True


def test_stage_only_scope_filters_by_status_not_by_funnel():
    sql = _sql(entity_scope_filter(Scope({1, 2}, statuses={"probation"}, all_vacancies=True)))
    assert "entities.status IN" in sql
    assert "vacancy_applications" not in sql  # практикант без воронки тоже виден


def test_application_filter_uses_stage():
    sql = _sql(application_scope_filter(Scope({1}, statuses={"probation"}, all_vacancies=True)))
    assert "vacancy_applications.stage IN" in sql
    assert application_scope_filter(None) is None


# --- карточка и списки -------------------------------------------------------

async def test_card_of_other_stage_is_404(client: AsyncClient, regular_user: User, practice_only):
    h = _headers(regular_user)
    assert (await client.get(f"/api/entities/{practice_only['trainee'].id}", headers=h)).status_code == 200
    assert (await client.get(f"/api/entities/{practice_only['loose'].id}", headers=h)).status_code == 200
    r = await client.get(f"/api/entities/{practice_only['newbie'].id}", headers=h)
    assert r.status_code == 404, r.text


async def test_all_candidates_board_shows_only_practice(client: AsyncClient, regular_user: User, practice_only):
    r = await client.get("/api/candidates/kanban?per_column=100", headers=_headers(regular_user))
    assert r.status_code == 200, r.text
    names = {c["name"] for col in r.json()["columns"] for c in col["cards"]}
    assert names == {"Практикант", "Без воронки"}
    counts = {col["status"]: col["count"] for col in r.json()["columns"] if col["count"]}
    assert counts == {"probation": 2}


async def test_funnel_lists_only_practice_applications(client: AsyncClient, regular_user: User, practice_only):
    r = await client.get(
        f"/api/vacancies/{practice_only['traffic'].id}/applications?all_recruiters=true",
        headers=_headers(regular_user),
    )
    assert r.status_code == 200, r.text
    assert [a["entity_name"] for a in r.json()] == ["Практикант"]


async def test_vacancy_stage_counts_match_list(client: AsyncClient, regular_user: User, practice_only):
    r = await client.get("/api/vacancies", headers=_headers(regular_user))
    assert r.status_code == 200, r.text
    by_id = {v["id"]: v for v in r.json()}
    traffic = by_id[practice_only["traffic"].id]
    assert traffic["stage_counts"] == {"probation": 1}
    assert traffic["applications_count"] == 1


async def test_history_of_other_stage_application_is_404(client: AsyncClient, regular_user: User, practice_only):
    h = _headers(regular_user)
    ok = await client.get(f"/api/vacancies/applications/{practice_only['app_trainee'].id}/history", headers=h)
    assert ok.status_code == 200, ok.text
    r = await client.get(f"/api/vacancies/applications/{practice_only['app_newbie'].id}/history", headers=h)
    assert r.status_code == 404, r.text


async def test_card_shows_only_practice_funnel_block(client: AsyncClient, regular_user: User, practice_only):
    r = await client.get(f"/api/entities/{practice_only['trainee'].id}/activity", headers=_headers(regular_user))
    assert r.status_code == 200, r.text
    body = r.json()
    blocks = body if isinstance(body, list) else body.get("applications") or body.get("vacancies") or []
    assert [b.get("vacancy_id") for b in blocks] == [practice_only["traffic"].id]


async def test_without_scope_everything_is_visible(
    client: AsyncClient, regular_user: User, practice_only, db_session: AsyncSession,
):
    member = (await db_session.execute(
        select(OrgMember).where(OrgMember.user_id == regular_user.id)
    )).scalar_one()
    member.scope_statuses = None
    await db_session.commit()
    r = await client.get(f"/api/entities/{practice_only['newbie'].id}", headers=_headers(regular_user))
    assert r.status_code == 200, r.text


# --- настройка ---------------------------------------------------------------

async def test_superadmin_sets_and_clears_stage_scope(
    client: AsyncClient, superadmin_user: User, regular_user: User, org_admin: OrgMember,
    db_session: AsyncSession,
):
    h = _headers(superadmin_user)
    r = await client.patch(f"/api/users/{regular_user.id}", json={"scope_statuses": ["probation", "мусор"]}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["scope_statuses"] == ["probation"]
    r = await client.patch(f"/api/users/{regular_user.id}", json={"scope_statuses": []}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["scope_statuses"] == []


async def test_card_hides_comments_of_hidden_funnel(
    client: AsyncClient, regular_user: User, practice_only, db_session: AsyncSession,
):
    """У практиканта отказ в «SEO»: её комментарий наблюдателю «только
    Практика» не показываем — ни в карточке, ни в строке списка."""
    trainee = practice_only["trainee"]
    trainee.extra_data = {"notes": [
        {"id": "a", "text": "по трафику", "vacancy_id": practice_only["traffic"].id},
        {"id": "b", "text": "отказ в SEO", "vacancy_id": practice_only["seo"].id},
        {"id": "c", "text": "общий"},
    ]}
    await db_session.commit()
    h = _headers(regular_user)
    r = await client.get(f"/api/entities/{trainee.id}", headers=h)
    assert r.status_code == 200, r.text
    assert [n["text"] for n in r.json()["extra_data"]["notes"]] == ["по трафику", "общий"]
    board = (await client.get("/api/candidates/kanban?per_column=100", headers=h)).json()
    row = next(c for col in board["columns"] for c in col["cards"] if c["id"] == trainee.id)
    assert [n["text"] for n in (row.get("extra_data") or {}).get("notes", [])] == ["по трафику", "общий"]
