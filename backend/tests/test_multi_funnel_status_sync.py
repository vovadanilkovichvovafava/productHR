"""Кандидат в двух воронках: как считается общий статус.

Entity.status — ОДНО поле, заявок может быть несколько. Правило сейчас
(services/stage_change.settle_entities, CLAUDE.md «Кандидат в нескольких
воронках»): общий статус = этап «актуальной» заявки — самой свежей ЖИВОЙ;
отказ/резерв учитываются, только когда живых не осталось. Поэтому перевод
в одной воронке двигает общий статус, а отказ в одной воронке не уводит
кандидата в «Отказ», пока он работается в другой.
"""
from datetime import datetime

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import (
    ApplicationStage, Department, Entity, EntityStatus, EntityType, OrgMember,
    Organization, User, Vacancy, VacancyApplication, VacancyStatus,
)
from api.services.auth import create_access_token
from tests.conftest import auth_headers


def _headers(user: User) -> dict:
    return auth_headers(create_access_token(data={"sub": str(user.id)}))


async def _make_vacancy(db, org, dept, user, title):
    now = datetime.utcnow()
    v = Vacancy(
        org_id=org.id, department_id=dept.id, created_by=user.id, title=title,
        status=VacancyStatus.open, salary_currency="RUB", created_at=now, updated_at=now,
    )
    db.add(v)
    await db.commit()
    return v


@pytest_asyncio.fixture
async def candidate_in_two_funnels(
    db_session: AsyncSession, organization: Organization, department: Department,
    admin_user: User, org_owner: OrgMember, candidate_entity: Entity,
):
    """Кандидат в двух ОТКРЫТЫХ воронках: A=applied, B=interview."""
    now = datetime.utcnow()
    vac_a = await _make_vacancy(db_session, organization, department, admin_user, "Воронка A")
    vac_b = await _make_vacancy(db_session, organization, department, admin_user, "Воронка B")

    app_a = VacancyApplication(
        vacancy_id=vac_a.id, entity_id=candidate_entity.id, stage=ApplicationStage.applied,
        stage_order=1, created_by=admin_user.id, applied_at=now,
        last_stage_change_at=now, updated_at=now,
    )
    app_b = VacancyApplication(
        vacancy_id=vac_b.id, entity_id=candidate_entity.id, stage=ApplicationStage.interview,
        stage_order=1, created_by=admin_user.id, applied_at=now,
        last_stage_change_at=now, updated_at=now,
    )
    db_session.add_all([app_a, app_b])

    candidate_entity.status = EntityStatus.new
    await db_session.commit()
    return candidate_entity, app_a, app_b, vac_a, vac_b


async def test_stage_change_in_one_funnel_keeps_global_status(
    client: AsyncClient, db_session: AsyncSession, admin_user: User,
    candidate_in_two_funnels,
):
    """Двигаем воронку A — общий статус идёт за ней (она теперь самая свежая
    живая заявка), вторая воронка не тронута."""
    entity, app_a, app_b, _va, _vb = candidate_in_two_funnels

    r = await client.put(
        f"/api/vacancies/applications/{app_a.id}",
        json={"stage": ApplicationStage.offer.value, "expected_entity_id": entity.id},
        headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text

    await db_session.refresh(entity)
    await db_session.refresh(app_a)
    await db_session.refresh(app_b)
    assert app_a.stage == ApplicationStage.offer, "своя воронка двигается"
    assert app_b.stage == ApplicationStage.interview, "чужая воронка не тронута"
    assert entity.status == EntityStatus.offer, (
        "общий статус — по самой свежей живой заявке (A, «Оффер»)"
    )


async def test_bulk_move_keeps_global_status_for_multi_funnel(
    client: AsyncClient, db_session: AsyncSession, admin_user: User,
    candidate_in_two_funnels,
):
    """Массовый перевод A в «Отказ»: B ещё живая (interview), поэтому общий
    статус — её этап, а не «Отказ»."""
    entity, app_a, app_b, _va, _vb = candidate_in_two_funnels

    r = await client.post(
        "/api/vacancies/applications/bulk-move",
        json={"application_ids": [app_a.id], "stage": ApplicationStage.rejected.value},
        headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text

    await db_session.refresh(entity)
    await db_session.refresh(app_a)
    assert app_a.stage == ApplicationStage.rejected
    assert entity.status == EntityStatus.tech_practice  # = interview воронки B


async def test_single_funnel_still_syncs(
    client: AsyncClient, db_session: AsyncSession, organization: Organization,
    department: Department, admin_user: User, org_owner: OrgMember,
    candidate_entity: Entity,
):
    """Одна воронка — синк работает как раньше (регресс на пере-закручивание гайки)."""
    now = datetime.utcnow()
    vac = await _make_vacancy(db_session, organization, department, admin_user, "Одна воронка")
    app = VacancyApplication(
        vacancy_id=vac.id, entity_id=candidate_entity.id, stage=ApplicationStage.applied,
        stage_order=1, created_by=admin_user.id, applied_at=now,
        last_stage_change_at=now, updated_at=now,
    )
    db_session.add(app)
    candidate_entity.status = EntityStatus.new
    await db_session.commit()

    r = await client.put(
        f"/api/vacancies/applications/{app.id}",
        json={"stage": ApplicationStage.offer.value, "expected_entity_id": candidate_entity.id},
        headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text

    await db_session.refresh(candidate_entity)
    assert candidate_entity.status == EntityStatus.offer


async def test_adding_to_second_funnel_keeps_global_status(
    client: AsyncClient, db_session: AsyncSession, organization: Organization,
    department: Department, admin_user: User, org_owner: OrgMember,
    candidate_entity: Entity,
):
    """Добавление во ВТОРУЮ воронку не сбрасывает статус в «Новый».

    Раньше у новой заявки этап applied, синк был безусловным — и кандидат,
    стоящий на оффере, визуально откатывался на старт просто потому, что его
    позвали ещё в одну вакансию.
    """
    now = datetime.utcnow()
    vac_a = await _make_vacancy(db_session, organization, department, admin_user, "Первая")
    vac_b = await _make_vacancy(db_session, organization, department, admin_user, "Вторая")
    app_a = VacancyApplication(
        vacancy_id=vac_a.id, entity_id=candidate_entity.id, stage=ApplicationStage.offer,
        stage_order=1, created_by=admin_user.id, applied_at=now,
        last_stage_change_at=now, updated_at=now,
    )
    db_session.add(app_a)
    candidate_entity.status = EntityStatus.offer
    await db_session.commit()

    r = await client.post(
        f"/api/vacancies/{vac_b.id}/applications",
        json={
            "vacancy_id": vac_b.id,
            "entity_id": candidate_entity.id,
            "stage": ApplicationStage.applied.value,
        },
        headers=_headers(admin_user),
    )
    assert r.status_code in (200, 201), r.text

    await db_session.refresh(candidate_entity)
    assert candidate_entity.status == EntityStatus.offer, (
        "приглашение во вторую воронку не откатывает кандидата на «Новый»"
    )
