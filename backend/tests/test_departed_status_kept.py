"""«Уволен» / «Уволился» не отменяется пересчётом по старой заявке (20.10.2026).

Общий статус кандидата сервер пересчитывает по «актуальной» заявке. Уволенный
на доске «Штат» человек оставался с заявкой на «Перешёл в отдел» (или на
«Практике» — до правки доски), и любое действие рядом — сохранение заявки без
смены этапа, удаление соседней заявки — «воскрешало» его в сотрудники или
практиканты. Уволенный правилом «Отказ после выхода в отдел» так же
превращался в обычный «Отказ». Меняет итог только реальное движение по
воронке — повторный найм.
"""
from datetime import datetime, timedelta

import pytest

from api.models.database import (
    ApplicationStage, Entity, EntityStatus, EntityType, Vacancy, VacancyApplication,
    VacancyStatus,
)
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _person(db, org, creator, status):
    e = Entity(
        org_id=org.id, name="Уволенный Иван", type=EntityType.candidate,
        status=status, created_by=creator.id, created_at=datetime.utcnow(), extra_data={},
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


async def _app(db, org, dept, user, entity, stage, title="Mob dev"):
    # Этап сменился давно — до увольнения.
    long_ago = datetime.utcnow() - timedelta(days=30)
    v = Vacancy(
        org_id=org.id, department_id=dept.id, created_by=user.id, title=title,
        status=VacancyStatus.open, salary_currency="RUB",
        created_at=long_ago, updated_at=long_ago,
    )
    db.add(v)
    await db.commit()
    a = VacancyApplication(
        vacancy_id=v.id, entity_id=entity.id, stage=stage, stage_order=1,
        created_by=user.id, applied_at=long_ago, last_stage_change_at=long_ago,
        updated_at=long_ago,
    )
    db.add(a)
    await db.commit()
    return a


async def _status(db, e):
    await db.refresh(e)
    return e.status


@pytest.mark.asyncio
@pytest.mark.parametrize("departed", [EntityStatus.dismissed, EntityStatus.quit])
async def test_saving_old_application_keeps_departed(
    client, db_session, organization, department, admin_user, org_owner, departed,
):
    e = await _person(db_session, organization, admin_user, departed)
    app = await _app(db_session, organization, department, admin_user, e, ApplicationStage.transferred)

    # Сохранение заявки без смены этапа тоже запускает пересчёт статуса.
    r = await client.put(
        f"/api/vacancies/applications/{app.id}",
        json={"stage": "transferred", "expected_entity_id": e.id},
        headers=_h(admin_user),
    )
    assert r.status_code == 200, r.text
    assert await _status(db_session, e) == departed


@pytest.mark.asyncio
async def test_application_stuck_on_practice_does_not_revive(
    client, db_session, organization, department, admin_user, org_owner,
):
    """Старые данные: заявка застряла на «Практике», человек уже уволен."""
    e = await _person(db_session, organization, admin_user, EntityStatus.dismissed)
    stuck = await _app(db_session, organization, department, admin_user, e, ApplicationStage.probation)

    r = await client.put(
        f"/api/vacancies/applications/{stuck.id}",
        json={"stage": "probation", "expected_entity_id": e.id},
        headers=_h(admin_user),
    )
    assert r.status_code == 200, r.text
    assert await _status(db_session, e) == EntityStatus.dismissed


@pytest.mark.asyncio
@pytest.mark.parametrize("staff", [EntityStatus.transferred, EntityStatus.dismissed, EntityStatus.quit])
async def test_removing_last_funnel_keeps_staff_status(
    client, db_session, organization, department, admin_user, org_owner, staff,
):
    """«Удалить с воронки» не превращает сотрудника в «Новый» — он не пропадает со «Штата»."""
    e = await _person(db_session, organization, admin_user, staff)
    app = await _app(db_session, organization, department, admin_user, e, ApplicationStage.transferred)
    r = await client.delete(f"/api/vacancies/applications/{app.id}", headers=_h(admin_user))
    assert r.status_code in (200, 204), r.text
    assert await _status(db_session, e) == staff


@pytest.mark.asyncio
async def test_removing_last_funnel_resets_candidate(
    client, db_session, organization, department, admin_user, org_owner,
):
    """Обычный кандидат после снятия с последней воронки — снова «Новый», как и было."""
    e = await _person(db_session, organization, admin_user, EntityStatus.screening)
    app = await _app(db_session, organization, department, admin_user, e, ApplicationStage.screening)
    r = await client.delete(f"/api/vacancies/applications/{app.id}", headers=_h(admin_user))
    assert r.status_code in (200, 204), r.text
    assert await _status(db_session, e) == EntityStatus.new


@pytest.mark.asyncio
async def test_dismissed_after_transfer_does_not_become_plain_rejection(
    client, db_session, organization, department, admin_user, org_owner,
):
    e = await _person(db_session, organization, admin_user, EntityStatus.transferred)
    app = await _app(db_session, organization, department, admin_user, e, ApplicationStage.transferred)

    # «Отказ» сотруднику — увольнение (правило DISMISS_AFTER_TRANSFER).
    r = await client.put(
        f"/api/vacancies/applications/{app.id}",
        json={"stage": "rejected", "expected_entity_id": e.id},
        headers=_h(admin_user),
    )
    assert r.status_code == 200, r.text
    assert await _status(db_session, e) == EntityStatus.dismissed

    # Следующее сохранение той же заявки — уже не движение.
    r = await client.put(
        f"/api/vacancies/applications/{app.id}",
        json={"stage": "rejected", "expected_entity_id": e.id},
        headers=_h(admin_user),
    )
    assert r.status_code == 200, r.text
    assert await _status(db_session, e) == EntityStatus.dismissed


@pytest.mark.asyncio
async def test_rehire_through_funnel_moves_status(
    client, db_session, organization, department, admin_user, org_owner,
):
    """Повторный найм: уволенного снова ведут по воронке — статус идёт за ней."""
    e = await _person(db_session, organization, admin_user, EntityStatus.dismissed)
    app = await _app(db_session, organization, department, admin_user, e, ApplicationStage.rejected)

    r = await client.put(
        f"/api/vacancies/applications/{app.id}",
        json={"stage": "screening", "expected_entity_id": e.id},
        headers=_h(admin_user),
    )
    assert r.status_code == 200, r.text
    assert await _status(db_session, e) == EntityStatus.screening
