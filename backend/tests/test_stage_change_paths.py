"""Смена этапа — один путь на весь HR (services/stage_change.py, 20.10.2026).

До рефакторинга этап меняли четыре эндпоинта, и каждый по-своему: правка
карточки и PATCH /entities/{id}/status двигали заявку молча, без истории
(перевод нельзя было ни увидеть, ни отменить); PATCH /candidates/{id}/status
выравнивал под новый этап ВСЕ заявки кандидата; массовый перевод сообщал
«из Новый», откуда бы кандидат ни шёл; перевод вне воронок фронт делал двумя
запросами (запись в ленту, потом статус). Тест сторожит общие правила.
"""
from datetime import datetime

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import (
    ApplicationStage, Department, Entity, EntityStatus, OrgMember, Organization,
    StageTransition, User, Vacancy, VacancyApplication, VacancyStatus,
)
from api.services.auth import create_access_token
from tests.conftest import auth_headers


def _headers(user: User) -> dict:
    return auth_headers(create_access_token(data={"sub": str(user.id)}))


async def _vacancy(db, org, dept, user, title, status=VacancyStatus.open):
    now = datetime.utcnow()
    v = Vacancy(
        org_id=org.id, department_id=dept.id, created_by=user.id, title=title,
        status=status, salary_currency="RUB", created_at=now, updated_at=now,
    )
    db.add(v)
    await db.commit()
    return v


async def _application(db, vacancy, entity, user, stage):
    now = datetime.utcnow()
    app = VacancyApplication(
        vacancy_id=vacancy.id, entity_id=entity.id, stage=stage, stage_order=1,
        created_by=user.id, applied_at=now, last_stage_change_at=now, updated_at=now,
    )
    db.add(app)
    await db.commit()
    return app


async def _transitions(db, app_id):
    rows = (await db.execute(
        select(StageTransition)
        .where(StageTransition.application_id == app_id)
        .order_by(StageTransition.id)
    )).scalars().all()
    return [(r.from_stage, r.to_stage, r.comment) for r in rows]


@pytest_asyncio.fixture
async def one_funnel(
    db_session: AsyncSession, organization: Organization, department: Department,
    admin_user: User, org_owner: OrgMember, candidate_entity: Entity,
):
    vac = await _vacancy(db_session, organization, department, admin_user, "Трафик")
    app = await _application(db_session, vac, candidate_entity, admin_user, ApplicationStage.applied)
    candidate_entity.status = EntityStatus.new
    await db_session.commit()
    return candidate_entity, app


async def test_put_application_writes_history_with_comment(
    client: AsyncClient, db_session: AsyncSession, admin_user: User, one_funnel, caplog,
):
    entity, app = one_funnel
    caplog.set_level("INFO", logger="hr-analyzer.stage_change")
    r = await client.put(
        f"/api/vacancies/applications/{app.id}",
        json={"stage": "screening", "comment": "ТЗ выдано", "expected_entity_id": entity.id},
        headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    assert r.json()["entity_status"] == "screening"
    assert await _transitions(db_session, app.id) == [("applied", "screening", "ТЗ выдано")]
    assert any(
        "STAGE_CHANGE" in m and f"app={app.id}" in m and "applied -> screening" in m
        for m in caplog.messages
    )


async def test_put_application_same_stage_writes_nothing(
    client: AsyncClient, db_session: AsyncSession, admin_user: User, one_funnel,
):
    entity, app = one_funnel
    r = await client.put(
        f"/api/vacancies/applications/{app.id}",
        json={"stage": "applied", "expected_entity_id": entity.id},
        headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    assert await _transitions(db_session, app.id) == []


async def test_put_application_stage_order_only_reorders(
    client: AsyncClient, db_session: AsyncSession, admin_user: User, one_funnel,
):
    _entity, app = one_funnel
    r = await client.put(
        f"/api/vacancies/applications/{app.id}",
        json={"stage_order": 42},
        headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    await db_session.refresh(app)
    assert app.stage_order == 42
    assert app.stage == ApplicationStage.applied


async def test_bulk_move_history_keeps_real_from_stage(
    client: AsyncClient, db_session: AsyncSession, organization: Organization,
    department: Department, admin_user: User, org_owner: OrgMember,
    candidate_entity: Entity,
):
    vac = await _vacancy(db_session, organization, department, admin_user, "Трафик")
    app = await _application(db_session, vac, candidate_entity, admin_user, ApplicationStage.interview)
    r = await client.post(
        "/api/vacancies/applications/bulk-move",
        json={"application_ids": [app.id], "stage": "offer"},
        headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    assert await _transitions(db_session, app.id) == [("interview", "offer", None)]


async def test_out_of_funnel_status_and_record_in_one_request(
    client: AsyncClient, db_session: AsyncSession, admin_user: User,
    org_owner: OrgMember, candidate_entity: Entity,
):
    """Кандидат без воронок: запись о переводе пишет сервер, вместе с переводом."""
    candidate_entity.status = EntityStatus.new
    await db_session.commit()
    r = await client.patch(
        f"/api/candidates/{candidate_entity.id}/status",
        json={"status": "practice", "comment": "созвон в пятницу", "stage_label": "Практика"},
        headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["entity_status"] == "practice"
    assert body["application_id"] is None
    note = body["note"]
    assert note["text"] == "созвон в пятницу"
    assert note["stage"] == "practice"
    assert note["stage_label"] == "Практика"
    assert note["from_status"] == "new"

    await db_session.refresh(candidate_entity)
    assert candidate_entity.status == EntityStatus.practice
    assert [n["id"] for n in candidate_entity.extra_data["notes"]] == [note["id"]]

    # Удаление этой записи возвращает кандидата назад (NOTE_STAGE_UNDO).
    r = await client.delete(
        f"/api/entities/{candidate_entity.id}/notes/{note['id']}",
        headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    assert r.json()["entity_status"] == "new"


async def test_out_of_funnel_record_without_comment(
    client: AsyncClient, db_session: AsyncSession, admin_user: User,
    org_owner: OrgMember, candidate_entity: Entity,
):
    """Перевод без комментария всё равно оставляет строку в ленте (28.09.2026)."""
    candidate_entity.status = EntityStatus.new
    await db_session.commit()
    r = await client.patch(
        f"/api/candidates/{candidate_entity.id}/status",
        json={"status": "screening"},
        headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    assert r.json()["note"]["text"] == ""


async def test_out_of_funnel_probation_goes_to_sandbox(
    client: AsyncClient, db_session: AsyncSession, admin_user: User,
    org_owner: OrgMember, candidate_entity: Entity, monkeypatch,
):
    """Практика ведёт в песочницу и из этого пути (раньше — только из соседнего)."""
    calls = []

    async def fake_ensure(db, entity_id, vacancy=None, org_id=None):
        calls.append((entity_id, vacancy, org_id))
        return True

    monkeypatch.setattr(
        "api.services.board_placements.ensure_sandbox_placement", fake_ensure,
    )
    candidate_entity.status = EntityStatus.offer
    await db_session.commit()
    r = await client.patch(
        f"/api/candidates/{candidate_entity.id}/status",
        json={"status": "probation"},
        headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    assert calls == [(candidate_entity.id, None, candidate_entity.org_id)]


async def test_candidate_status_in_one_funnel_moves_that_funnel(
    client: AsyncClient, db_session: AsyncSession, admin_user: User, one_funnel,
):
    entity, app = one_funnel
    r = await client.patch(
        f"/api/candidates/{entity.id}/status",
        json={"status": "screening", "comment": "ок"},
        headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    assert r.json()["application_id"] == app.id
    assert r.json()["note"] is None
    assert await _transitions(db_session, app.id) == [("applied", "screening", "ок")]


async def test_candidate_status_in_two_funnels_refuses_without_moving(
    client: AsyncClient, db_session: AsyncSession, organization: Organization,
    department: Department, admin_user: User, org_owner: OrgMember,
    candidate_entity: Entity,
):
    """Раньше выравнивались ВСЕ воронки (17.09.2026). Теперь — отказ и ничего."""
    vac_a = await _vacancy(db_session, organization, department, admin_user, "A")
    vac_b = await _vacancy(db_session, organization, department, admin_user, "B")
    app_a = await _application(db_session, vac_a, candidate_entity, admin_user, ApplicationStage.applied)
    app_b = await _application(db_session, vac_b, candidate_entity, admin_user, ApplicationStage.interview)
    r = await client.patch(
        f"/api/candidates/{candidate_entity.id}/status",
        json={"status": "rejected"},
        headers=_headers(admin_user),
    )
    assert r.status_code == 409, r.text
    await db_session.refresh(app_a)
    await db_session.refresh(app_b)
    assert (app_a.stage, app_b.stage) == (ApplicationStage.applied, ApplicationStage.interview)
    assert await _transitions(db_session, app_a.id) == []


async def test_closed_funnel_is_not_touched(
    client: AsyncClient, db_session: AsyncSession, organization: Organization,
    department: Department, admin_user: User, org_owner: OrgMember,
    candidate_entity: Entity,
):
    """Заявка в закрытой вакансии — архив: переводим кандидата вне воронок."""
    vac = await _vacancy(db_session, organization, department, admin_user, "Старая", VacancyStatus.closed)
    app = await _application(db_session, vac, candidate_entity, admin_user, ApplicationStage.rejected)
    candidate_entity.status = EntityStatus.rejected
    await db_session.commit()
    r = await client.patch(
        f"/api/candidates/{candidate_entity.id}/status",
        json={"status": "new"},
        headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    await db_session.refresh(app)
    assert app.stage == ApplicationStage.rejected
    assert r.json()["note"]["from_status"] == "rejected"


async def test_entity_status_endpoint_now_writes_history(
    client: AsyncClient, db_session: AsyncSession, admin_user: User, one_funnel,
):
    """PATCH /entities/{id}/status двигал заявку молча — теперь с историей."""
    entity, app = one_funnel
    r = await client.patch(
        f"/api/entities/{entity.id}/status",
        json={"status": "screening"},
        headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    assert await _transitions(db_session, app.id) == [("applied", "screening", None)]


async def test_entity_edit_with_status_now_writes_history(
    client: AsyncClient, db_session: AsyncSession, admin_user: User, one_funnel,
):
    entity, app = one_funnel
    r = await client.put(
        f"/api/entities/{entity.id}",
        json={"name": entity.name, "status": "practice"},
        headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    assert await _transitions(db_session, app.id) == [("applied", "phone_screen", None)]
