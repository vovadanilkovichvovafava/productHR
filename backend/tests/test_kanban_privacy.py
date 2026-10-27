"""Приватность воронки: «общая воронка, но каждый видит только своих» (2026-07-13).

Модель: обычный рекрутёр (member без полного доступа) видит на kanban-доске
конкретной вакансии ТОЛЬКО кандидатов, которых сам добавил
(VacancyApplication.created_by == self). Админ/владелец/суперадмин видят всех.
Ограничение действует только в воронке; глобальная база остаётся общей.
"""
from datetime import datetime

import pytest
import pytest_asyncio

from api.models.database import (
    Vacancy, VacancyStatus, VacancyApplication, ApplicationStage,
    Entity, EntityType, EntityStatus, DepartmentFeature,
)
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


@pytest_asyncio.fixture(autouse=True)
async def candidate_database_feature(db_session, organization):
    """check_vacancy_access требует фичу candidate_database для member."""
    db_session.add(DepartmentFeature(
        org_id=organization.id, department_id=None,
        feature_name="candidate_database", enabled=True,
    ))
    await db_session.commit()


async def _mk_entity(db, org, creator, name) -> Entity:
    e = Entity(
        org_id=org.id, created_by=creator.id, name=name,
        type=EntityType.candidate, status=EntityStatus.new,
        created_at=datetime.utcnow(),
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


async def _mk_app(db, vacancy, entity, creator) -> VacancyApplication:
    app = VacancyApplication(
        vacancy_id=vacancy.id, entity_id=entity.id,
        stage=ApplicationStage.applied, stage_order=1,
        created_by=creator.id, applied_at=datetime.utcnow(),
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


@pytest_asyncio.fixture
async def shared_vacancy_with_two_apps(
    db_session, organization, admin_user, second_user
):
    """ПРИВАТНАЯ воронка («Скрыта от коллег», visible_to_all=False) с двумя
    откликами: один добавил admin, другой — second_user (обычный рекрутёр).
    Рекрутёр НАЗНАЧЕН (assigned_to) → имеет доступ к воронке, но по приватности
    видит только своих кандидатов."""
    v = Vacancy(
        org_id=organization.id, title="Приватная воронка", status=VacancyStatus.open,
        created_by=admin_user.id, visible_to_all=False,
        assigned_to=[second_user.id],  # рекрутёр — участник воронки (даёт доступ)
        created_at=datetime.utcnow(),
    )
    db_session.add(v)
    await db_session.commit()
    await db_session.refresh(v)

    e_admin = await _mk_entity(db_session, organization, admin_user, "Кандидат Админа")
    e_member = await _mk_entity(db_session, organization, second_user, "Кандидат Рекрутёра")
    await _mk_app(db_session, v, e_admin, admin_user)
    await _mk_app(db_session, v, e_member, second_user)
    return v, e_admin.id, e_member.id


@pytest_asyncio.fixture
async def collegial_vacancy_with_two_apps(
    db_session, organization, admin_user, second_user
):
    """КОЛЛЕГИАЛЬНАЯ воронка («Видна коллегам», visible_to_all=True) с двумя
    откликами. Рекрутёр назначен → на такой воронке видит и МОЖЕТ двигать ВСЕХ
    кандидатов (по запросу юзера 2026-08-04), а не только своих."""
    v = Vacancy(
        org_id=organization.id, title="Коллегиальная воронка", status=VacancyStatus.open,
        created_by=admin_user.id, visible_to_all=True,
        assigned_to=[second_user.id],
        created_at=datetime.utcnow(),
    )
    db_session.add(v)
    await db_session.commit()
    await db_session.refresh(v)

    e_admin = await _mk_entity(db_session, organization, admin_user, "Кандидат Админа")
    e_member = await _mk_entity(db_session, organization, second_user, "Кандидат Рекрутёра")
    await _mk_app(db_session, v, e_admin, admin_user)
    await _mk_app(db_session, v, e_member, second_user)
    return v, e_admin.id, e_member.id


def _all_entity_ids(board_json) -> set:
    ids = set()
    for col in board_json["columns"]:
        for app in col["applications"]:
            ids.add(app["entity_id"])
    return ids


@pytest.mark.asyncio
async def test_recruiter_sees_only_own_on_board(
    client, db_session, organization, admin_user, org_owner,
    second_user, org_member, shared_vacancy_with_two_apps,
):
    v, e_admin_id, e_member_id = shared_vacancy_with_two_apps

    # Обычный рекрутёр (member) видит ТОЛЬКО своего кандидата
    r = await client.get(f"/api/vacancies/{v.id}/kanban", headers=_h(second_user))
    assert r.status_code == 200, r.text
    ids = _all_entity_ids(r.json())
    assert ids == {e_member_id}
    assert r.json()["total_count"] == 1


@pytest.mark.asyncio
async def test_admin_sees_all_on_board(
    client, db_session, organization, admin_user, org_owner,
    second_user, org_member, shared_vacancy_with_two_apps,
):
    v, e_admin_id, e_member_id = shared_vacancy_with_two_apps

    # Админ видит обоих
    r = await client.get(f"/api/vacancies/{v.id}/kanban", headers=_h(admin_user))
    assert r.status_code == 200, r.text
    ids = _all_entity_ids(r.json())
    assert ids == {e_admin_id, e_member_id}
    assert r.json()["total_count"] == 2


@pytest.mark.asyncio
async def test_admin_can_filter_by_recruiter(
    client, db_session, organization, admin_user, org_owner,
    second_user, org_member, shared_vacancy_with_two_apps,
):
    v, e_admin_id, e_member_id = shared_vacancy_with_two_apps

    # Админ фильтрует по рекрутёру second_user → только его кандидат
    r = await client.get(
        f"/api/vacancies/{v.id}/kanban?created_by={second_user.id}",
        headers=_h(admin_user),
    )
    assert r.status_code == 200, r.text
    assert _all_entity_ids(r.json()) == {e_member_id}


@pytest.mark.asyncio
async def test_recruiter_column_load_more_scoped(
    client, db_session, organization, admin_user, org_owner,
    second_user, org_member, shared_vacancy_with_two_apps,
):
    v, e_admin_id, e_member_id = shared_vacancy_with_two_apps

    # Догрузка колонки (infinite scroll) тоже отдаёт только своих
    r = await client.get(
        f"/api/vacancies/{v.id}/kanban/column/applied", headers=_h(second_user)
    )
    assert r.status_code == 200, r.text
    ids = {a["entity_id"] for a in r.json()["applications"]}
    assert ids == {e_member_id}
    assert r.json()["total_count"] == 1


@pytest.mark.asyncio
async def test_recruiter_sees_legacy_null_author(
    client, db_session, organization, admin_user, org_owner,
    second_user, org_member, shared_vacancy_with_two_apps,
):
    """Legacy-отклик без автора (created_by=NULL) виден рекрутёру (fallback)."""
    v, e_admin_id, e_member_id = shared_vacancy_with_two_apps

    # Добавляем «ничей» отклик (старый импорт) — created_by=NULL
    e_legacy = await _mk_entity(db_session, organization, admin_user, "Старый импорт")
    legacy = VacancyApplication(
        vacancy_id=v.id, entity_id=e_legacy.id,
        stage=ApplicationStage.applied, stage_order=1,
        created_by=None, applied_at=datetime.utcnow(),
    )
    db_session.add(legacy)
    await db_session.commit()

    r = await client.get(f"/api/vacancies/{v.id}/kanban", headers=_h(second_user))
    assert r.status_code == 200, r.text
    ids = _all_entity_ids(r.json())
    # свой + legacy без автора; чужой (админский) — скрыт
    assert ids == {e_member_id, e_legacy.id}


@pytest.mark.asyncio
async def test_recruiter_applications_only_own(
    client, db_session, organization, admin_user, org_owner,
    second_user, org_member, shared_vacancy_with_two_apps,
):
    """GET /applications (страница /my-funnels) тоже скоупится: рекрутёр видит
    только своих кандидатов."""
    v, e_admin_id, e_member_id = shared_vacancy_with_two_apps

    r = await client.get(f"/api/vacancies/{v.id}/applications", headers=_h(second_user))
    assert r.status_code == 200, r.text
    ids = {a["entity_id"] for a in r.json()}
    assert ids == {e_member_id}


@pytest.mark.asyncio
async def test_admin_applications_filter_by_recruiter(
    client, db_session, organization, admin_user, org_owner,
    second_user, org_member, shared_vacancy_with_two_apps,
):
    """Админ видит всех, а с ?created_by=<id> скоупит воронку по рекрутёру
    (селектор «Вакансии: <имя>» в сайдбаре)."""
    v, e_admin_id, e_member_id = shared_vacancy_with_two_apps

    r_all = await client.get(f"/api/vacancies/{v.id}/applications", headers=_h(admin_user))
    assert r_all.status_code == 200, r_all.text
    assert {a["entity_id"] for a in r_all.json()} == {e_admin_id, e_member_id}

    r_scoped = await client.get(
        f"/api/vacancies/{v.id}/applications?created_by={second_user.id}",
        headers=_h(admin_user),
    )
    assert r_scoped.status_code == 200, r_scoped.text
    assert {a["entity_id"] for a in r_scoped.json()} == {e_member_id}


@pytest.mark.asyncio
async def test_recruiter_can_move_foreign_candidate(
    client, db_session, organization, admin_user, org_owner,
    second_user, org_member, shared_vacancy_with_two_apps,
):
    """С 21.10.2026 (владелец): в фильтре воронки выбирают любого рекрутёра —
    его кандидатов и смотрят, и правят. Чужой перевод в скрытой воронке — 200."""
    v, e_admin_id, e_member_id = shared_vacancy_with_two_apps

    # Находим отклик чужого кандидата (админского) и двигаем его
    from sqlalchemy import select
    app_id = (await db_session.execute(
        select(VacancyApplication.id).where(
            VacancyApplication.vacancy_id == v.id,
            VacancyApplication.entity_id == e_admin_id,
        )
    )).scalar()

    r = await client.put(
        f"/api/vacancies/applications/{app_id}",
        headers=_h(second_user), json={"stage": "screening"},
    )
    assert r.status_code == 200, r.text


# ============================================================================
# «Видна коллегам» (visible_to_all): рекрутёр видит и двигает ВСЕХ (2026-08-04)
# ============================================================================


@pytest.mark.asyncio
async def test_recruiter_sees_all_on_collegial_board(
    client, db_session, organization, admin_user, org_owner,
    second_user, org_member, collegial_vacancy_with_two_apps,
):
    """«Видна коллегам»: рекрутёр видит на доске ВСЕХ кандидатов воронки."""
    v, e_admin_id, e_member_id = collegial_vacancy_with_two_apps

    r = await client.get(f"/api/vacancies/{v.id}/kanban", headers=_h(second_user))
    assert r.status_code == 200, r.text
    assert _all_entity_ids(r.json()) == {e_admin_id, e_member_id}
    assert r.json()["total_count"] == 2


@pytest.mark.asyncio
async def test_recruiter_sees_all_in_collegial_column(
    client, db_session, organization, admin_user, org_owner,
    second_user, org_member, collegial_vacancy_with_two_apps,
):
    """Догрузка колонки на «Видна коллегам» тоже отдаёт всех."""
    v, e_admin_id, e_member_id = collegial_vacancy_with_two_apps

    r = await client.get(
        f"/api/vacancies/{v.id}/kanban/column/applied", headers=_h(second_user)
    )
    assert r.status_code == 200, r.text
    ids = {a["entity_id"] for a in r.json()["applications"]}
    assert ids == {e_admin_id, e_member_id}
    assert r.json()["total_count"] == 2


@pytest.mark.asyncio
async def test_recruiter_sees_all_collegial_applications(
    client, db_session, organization, admin_user, org_owner,
    second_user, org_member, collegial_vacancy_with_two_apps,
):
    """GET /applications (страница /my-funnels) на «Видна коллегам» — все."""
    v, e_admin_id, e_member_id = collegial_vacancy_with_two_apps

    r = await client.get(f"/api/vacancies/{v.id}/applications", headers=_h(second_user))
    assert r.status_code == 200, r.text
    assert {a["entity_id"] for a in r.json()} == {e_admin_id, e_member_id}


@pytest.mark.asyncio
async def test_recruiter_only_mine_on_collegial(
    client, db_session, organization, admin_user, org_owner,
    second_user, org_member, collegial_vacancy_with_two_apps,
):
    """Чекбокс «Только мои» (?created_by=<self>): рекрутёр даже на «Видна коллегам»
    может оставить ТОЛЬКО своих кандидатов (доска + applications)."""
    v, e_admin_id, e_member_id = collegial_vacancy_with_two_apps

    r = await client.get(
        f"/api/vacancies/{v.id}/kanban?created_by={second_user.id}", headers=_h(second_user)
    )
    assert r.status_code == 200, r.text
    assert _all_entity_ids(r.json()) == {e_member_id}

    r2 = await client.get(
        f"/api/vacancies/{v.id}/applications?created_by={second_user.id}", headers=_h(second_user)
    )
    assert r2.status_code == 200, r2.text
    assert {a["entity_id"] for a in r2.json()} == {e_member_id}


@pytest.mark.asyncio
async def test_recruiter_cannot_scope_to_other_on_collegial(
    client, db_session, organization, admin_user, org_owner,
    second_user, org_member, collegial_vacancy_with_two_apps,
):
    """Не-админ может скоупить ТОЛЬКО на себя: ?created_by=<чужой> игнорируется —
    на «Видна коллегам» он всё равно видит всех (нет утечки чужой приватности)."""
    v, e_admin_id, e_member_id = collegial_vacancy_with_two_apps

    r = await client.get(
        f"/api/vacancies/{v.id}/kanban?created_by={admin_user.id}", headers=_h(second_user)
    )
    assert r.status_code == 200, r.text
    assert _all_entity_ids(r.json()) == {e_admin_id, e_member_id}


@pytest.mark.asyncio
async def test_recruiter_can_move_foreign_on_collegial(
    client, db_session, organization, admin_user, org_owner,
    second_user, org_member, collegial_vacancy_with_two_apps,
):
    """«Видна коллегам»: рекрутёр может двигать и ЧУЖОГО кандидата (иначе виден,
    но drag → 403). Проверяем и одиночный PUT, и bulk-move."""
    from sqlalchemy import select
    v, e_admin_id, e_member_id = collegial_vacancy_with_two_apps

    app_id = (await db_session.execute(
        select(VacancyApplication.id).where(
            VacancyApplication.vacancy_id == v.id,
            VacancyApplication.entity_id == e_admin_id,
        )
    )).scalar()

    # Одиночный перенос чужого кандидата рекрутёром — теперь ok.
    r = await client.put(
        f"/api/vacancies/applications/{app_id}",
        headers=_h(second_user), json={"stage": "screening"},
    )
    assert r.status_code == 200, r.text

    # Массовый перенос чужого — тоже ok.
    r_bulk = await client.post(
        "/api/vacancies/applications/bulk-move",
        headers=_h(second_user),
        json={"application_ids": [app_id], "stage": "interview"},
    )
    assert r_bulk.status_code == 200, r_bulk.text


@pytest.mark.asyncio
async def test_null_author_belongs_to_vacancy_owner_in_recruiter_scope(
    client, db_session, organization, admin_user, org_owner,
    second_user, org_member, collegial_vacancy_with_two_apps,
):
    """Заявка без автора (created_by=NULL) в скоупе по рекрутёру принадлежит
    ВЛАДЕЛЬЦУ вакансии — как авто-метка «HR: …» (hr_tags, coalesce). Прод
    2026-09-21: метка «HR: Мария · Трафик», а в воронке Марии кандидата не было."""
    v, e_admin_id, e_member_id = collegial_vacancy_with_two_apps  # владелец — admin_user

    e_legacy = await _mk_entity(db_session, organization, admin_user, "Без автора")
    db_session.add(VacancyApplication(
        vacancy_id=v.id, entity_id=e_legacy.id,
        stage=ApplicationStage.applied, stage_order=1,
        created_by=None, applied_at=datetime.utcnow(),
    ))
    await db_session.commit()

    def ids(r):
        assert r.status_code == 200, r.text
        return {a["entity_id"] for a in r.json()}

    # Скоуп на владельца вакансии — «ничей» кандидат его.
    r_owner = await client.get(
        f"/api/vacancies/{v.id}/applications?created_by={admin_user.id}",
        headers=_h(admin_user),
    )
    assert ids(r_owner) == {e_admin_id, e_legacy.id}

    # Скоуп на другого рекрутёра — «ничей» кандидат не его.
    r_other = await client.get(
        f"/api/vacancies/{v.id}/applications?created_by={second_user.id}",
        headers=_h(admin_user),
    )
    assert ids(r_other) == {e_member_id}

    # Канбан-доска с тем же скоупом ведёт себя так же.
    r_board = await client.get(
        f"/api/vacancies/{v.id}/kanban?created_by={admin_user.id}",
        headers=_h(admin_user),
    )
    assert r_board.status_code == 200, r_board.text
    assert _all_entity_ids(r_board.json()) == {e_admin_id, e_legacy.id}
