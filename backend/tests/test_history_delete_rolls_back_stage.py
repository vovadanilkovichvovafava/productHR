"""Удаление записи истории этапов (2026-09-23, разбор видео Huntflow).

ПОСЛЕДНЯЯ запись — это сам перевод, которым кандидат попал на текущий этап:
удаляя её, рекрутёр отменяет ошибочный перевод, и заявка едет назад на
from_stage. СТАРЫЕ записи — чистка лога, этап не трогаем.

История вопроса: 11.09–16.09 откат уже был, 16.09 его выключили (Мария удаляла
запись и не ожидала переезда), а 23.09 рекрутёры попросили вернуть — но теперь
только для последней записи, у которой to_stage совпадает с текущим этапом.
"""
from datetime import datetime, timedelta

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import (
    ApplicationStage, Department, Entity, EntityStatus, EntityType, OrgMember,
    Organization, STAGE_SYNC_MAP, StageTransition, User, Vacancy,
    VacancyApplication, VacancyStatus,
)
from api.services.auth import create_access_token
from tests.conftest import auth_headers

FIRST = ApplicationStage.applied
SECOND = [s for s in ApplicationStage if s != FIRST][0]


@pytest_asyncio.fixture
async def moved_application(
    db_session: AsyncSession, organization: Organization, department: Department,
    admin_user: User, org_owner: OrgMember, candidate_entity: Entity,
):
    now = datetime.utcnow()
    vacancy = Vacancy(
        org_id=organization.id, department_id=department.id, created_by=admin_user.id,
        title="Трафик", status=VacancyStatus.open, salary_currency="RUB",
        created_at=now, updated_at=now,
    )
    db_session.add(vacancy)
    await db_session.commit()
    app = VacancyApplication(
        vacancy_id=vacancy.id, entity_id=candidate_entity.id, stage=SECOND, stage_order=1,
        created_by=admin_user.id, applied_at=now, last_stage_change_at=now, updated_at=now,
    )
    db_session.add(app)
    await db_session.commit()
    initial = StageTransition(
        application_id=app.id, entity_id=candidate_entity.id, from_stage=None,
        to_stage=FIRST.value, changed_by=admin_user.id, created_at=now - timedelta(minutes=5),
    )
    moved = StageTransition(
        application_id=app.id, entity_id=candidate_entity.id, from_stage=FIRST.value,
        to_stage=SECOND.value, changed_by=admin_user.id, created_at=now,
    )
    db_session.add_all([initial, moved])
    await db_session.commit()
    return app, initial, moved


def _headers(user: User) -> dict:
    return auth_headers(create_access_token(data={"sub": str(user.id)}))


async def test_deleting_latest_transition_rolls_back_stage(
    client: AsyncClient, db_session: AsyncSession, admin_user: User, moved_application,
):
    """Удалили запись о переводе — кандидат вернулся на прежний этап."""
    app, _initial, moved = moved_application
    r = await client.delete(
        f"/api/vacancies/applications/{app.id}/history/{moved.id}", headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rolled_back"] is True
    assert body["stage"] == FIRST.value
    await db_session.refresh(app)
    assert app.stage == FIRST


async def test_rollback_needs_matching_current_stage(
    client: AsyncClient, db_session: AsyncSession, admin_user: User, moved_application,
):
    """Этап уже сменили руками — запись больше не описывает текущий этап.

    Тогда удаление её только чистит лог: иначе кандидат уехал бы туда, где он
    точно не должен быть.
    """
    app, _initial, moved = moved_application
    app.stage = FIRST
    await db_session.commit()
    r = await client.delete(
        f"/api/vacancies/applications/{app.id}/history/{moved.id}", headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    assert r.json()["rolled_back"] is False
    await db_session.refresh(app)
    assert app.stage == FIRST


async def test_rollback_recomputes_entity_status(
    client: AsyncClient, db_session: AsyncSession, admin_user: User,
    candidate_entity: Entity, moved_application,
):
    """Общий статус кандидата («Все кандидаты») едет назад вместе с заявкой.

    Иначе карточка справа показывала бы прежний этап, а колонка в списке —
    тот, откуда его только что вернули.
    """
    app, _initial, moved = moved_application
    r = await client.delete(
        f"/api/vacancies/applications/{app.id}/history/{moved.id}", headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    expected = STAGE_SYNC_MAP[FIRST]
    assert r.json()["entity_status"] == expected.value
    await db_session.refresh(candidate_entity)
    assert candidate_entity.status == expected


async def test_first_transition_without_from_stage_is_only_deleted(
    client: AsyncClient, db_session: AsyncSession, admin_user: User, moved_application,
):
    """У самой первой записи («добавлен в воронку») from_stage пуст.

    Возвращать некуда — запись просто удаляется, этап остаётся.
    """
    app, initial, moved = moved_application
    # Сначала убираем более свежую запись, чтобы первая стала последней.
    await client.delete(
        f"/api/vacancies/applications/{app.id}/history/{moved.id}", headers=_headers(admin_user),
    )
    r = await client.delete(
        f"/api/vacancies/applications/{app.id}/history/{initial.id}", headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    assert r.json()["rolled_back"] is False
    await db_session.refresh(app)
    assert app.stage == FIRST  # тот, куда вернул первый откат


async def test_same_second_transitions_pick_latest_by_id(
    client: AsyncClient, db_session: AsyncSession, admin_user: User,
    candidate_entity: Entity, moved_application,
):
    """Два перевода в одну секунду: «последняя» — та, что с большим id.

    created_at у быстрых переводов и у импорта совпадает до секунды, и без
    второго ключа сортировки откатывалась бы не та запись.
    """
    app, _initial, moved = moved_application
    third = StageTransition(
        application_id=app.id, entity_id=candidate_entity.id,
        from_stage=SECOND.value, to_stage=ApplicationStage.offer.value,
        changed_by=admin_user.id, created_at=moved.created_at,
    )
    db_session.add(third)
    app.stage = ApplicationStage.offer
    await db_session.commit()

    # Запись с тем же created_at, но меньшим id — уже не последняя.
    r = await client.delete(
        f"/api/vacancies/applications/{app.id}/history/{moved.id}", headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    assert r.json()["rolled_back"] is False
    await db_session.refresh(app)
    assert app.stage == ApplicationStage.offer

    r = await client.delete(
        f"/api/vacancies/applications/{app.id}/history/{third.id}", headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    assert r.json()["rolled_back"] is True
    await db_session.refresh(app)
    assert app.stage == SECOND


async def test_deleting_older_transition_keeps_stage(
    client: AsyncClient, db_session: AsyncSession, admin_user: User, moved_application,
):
    """Старая запись из середины лога — этап остаётся на месте."""
    app, initial, _moved = moved_application
    r = await client.delete(
        f"/api/vacancies/applications/{app.id}/history/{initial.id}", headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    assert r.json()["rolled_back"] is False
    await db_session.refresh(app)
    assert app.stage == SECOND


async def test_stage_change_rejects_wrong_candidate(
    client: AsyncClient, db_session: AsyncSession, admin_user: User, moved_application,
):
    """Страховка: если фронт ждал другого кандидата — этап не меняется (409)."""
    app, _initial, _moved = moved_application
    r = await client.put(
        f"/api/vacancies/applications/{app.id}",
        json={"stage": FIRST.value, "expected_entity_id": app.entity_id + 999},
        headers=_headers(admin_user),
    )
    assert r.status_code == 409, r.text
    await db_session.refresh(app)
    assert app.stage == SECOND


async def test_stage_change_applies_for_matching_candidate(
    client: AsyncClient, db_session: AsyncSession, admin_user: User, moved_application,
):
    app, _initial, _moved = moved_application
    r = await client.put(
        f"/api/vacancies/applications/{app.id}",
        json={"stage": FIRST.value, "expected_entity_id": app.entity_id},
        headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    await db_session.refresh(app)
    assert app.stage == FIRST


@pytest_asyncio.fixture
async def second_application(
    db_session: AsyncSession, organization: Organization, department: Department,
    admin_user: User, moved_application,
):
    """Второй РЕАЛЬНЫЙ кандидат в той же воронке — как у Марии 15.09.

    Проверка с `entity_id + 999` ловит только несуществующего кандидата, а
    промах был именно между двумя живыми людьми одной воронки.
    """
    app, _initial, _moved = moved_application
    now = datetime.utcnow()
    other = Entity(
        org_id=organization.id, department_id=department.id, created_by=admin_user.id,
        name="Никитина", type=EntityType.candidate, status=EntityStatus.interview,
        created_at=now,
    )
    db_session.add(other)
    await db_session.commit()
    other_app = VacancyApplication(
        vacancy_id=app.vacancy_id, entity_id=other.id, stage=FIRST, stage_order=2,
        created_by=admin_user.id, applied_at=now, last_stage_change_at=now, updated_at=now,
    )
    db_session.add(other_app)
    await db_session.commit()
    return other, other_app


async def test_stale_application_id_of_neighbour_is_rejected(
    client: AsyncClient, db_session: AsyncSession, admin_user: User,
    moved_application, second_application,
):
    """Баг Марии 2026-09-15 в том виде, в каком его теперь шлёт фронт.

    Открыта Никитина, а applicationId прилетел из устаревшей ленты и принадлежит
    соседу по воронке. expected_entity_id берётся у ОТКРЫТОГО кандидата, поэтому
    сверка не сходится: 409, и ни одна из двух заявок не двигается.
    """
    stale_app, _initial, _moved = moved_application     # заявка соседа
    open_entity, open_app = second_application          # кого видит пользователь

    r = await client.put(
        f"/api/vacancies/applications/{stale_app.id}",
        json={"stage": FIRST.value, "expected_entity_id": open_entity.id},
        headers=_headers(admin_user),
    )
    assert r.status_code == 409, r.text

    await db_session.refresh(stale_app)
    await db_session.refresh(open_app)
    assert stale_app.stage == SECOND, "заявка соседа не должна была сдвинуться"
    assert open_app.stage == FIRST, "заявка открытого кандидата тоже не тронута"


async def test_update_returns_entity_status_of_live_funnel(
    client: AsyncClient, db_session: AsyncSession, organization: Organization,
    department: Department, admin_user: User, org_owner: OrgMember,
    candidate_entity: Entity, moved_application,
):
    """Ответ на смену этапа несёт ОБЩИЙ статус кандидата, а не выбранный этап.

    Кандидат в двух воронках: отказ в одной не должен уводить его карточку в
    «Все кандидаты» в колонку «Отказ» — общий статус держится по живой второй
    воронке. Фронт ставит карточку по этому полю, иначе список расходится с
    сервером до F5 (23.09.2026).
    """
    app_live, _initial, _moved = moved_application     # живая воронка, этап SECOND
    now = datetime.utcnow()
    second_vacancy = Vacancy(
        org_id=organization.id, department_id=department.id, created_by=admin_user.id,
        title="Вторая воронка", status=VacancyStatus.open, salary_currency="RUB",
        created_at=now, updated_at=now,
    )
    db_session.add(second_vacancy)
    await db_session.commit()
    app_other = VacancyApplication(
        vacancy_id=second_vacancy.id, entity_id=candidate_entity.id, stage=FIRST,
        stage_order=1, created_by=admin_user.id, applied_at=now,
        last_stage_change_at=now, updated_at=now,
    )
    db_session.add(app_other)
    await db_session.commit()

    r = await client.put(
        f"/api/vacancies/applications/{app_other.id}",
        json={"stage": "rejected", "expected_entity_id": candidate_entity.id},
        headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stage"] == "rejected"                      # этап самой заявки
    assert body["entity_status"] == STAGE_SYNC_MAP[SECOND].value  # а статус — по живой воронке


async def test_entity_status_follows_live_funnel_not_rejection(
    client: AsyncClient, db_session: AsyncSession, organization: Organization,
    department: Department, admin_user: User, org_owner: OrgMember,
    candidate_entity: Entity, moved_application,
):
    """Отказ в одной воронке не перебивает живую работу в другой (17.09).

    Общий статус кандидата (колонка «Все кандидаты») считается по самой свежей
    ЖИВОЙ заявке; отказ учитывается, только когда живых воронок не осталось.
    """
    app_live, _initial, _moved = moved_application
    now = datetime.utcnow()
    second_vacancy = Vacancy(
        org_id=organization.id, department_id=department.id, created_by=admin_user.id,
        title="Вторая воронка", status=VacancyStatus.open, salary_currency="RUB",
        created_at=now, updated_at=now,
    )
    db_session.add(second_vacancy)
    await db_session.commit()
    app_other = VacancyApplication(
        vacancy_id=second_vacancy.id, entity_id=candidate_entity.id, stage=FIRST,
        stage_order=1, created_by=admin_user.id, applied_at=now,
        last_stage_change_at=now, updated_at=now,
    )
    db_session.add(app_other)
    await db_session.commit()

    # Отказ во ВТОРОЙ воронке — позже всех остальных изменений.
    r = await client.put(
        f"/api/vacancies/applications/{app_other.id}",
        json={"stage": "rejected", "expected_entity_id": candidate_entity.id},
        headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    await db_session.refresh(candidate_entity)
    assert candidate_entity.status != EntityStatus.rejected

    # Живых воронок не осталось — тогда отказ и становится общим статусом.
    r = await client.put(
        f"/api/vacancies/applications/{app_live.id}",
        json={"stage": "rejected", "expected_entity_id": candidate_entity.id},
        headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    await db_session.refresh(candidate_entity)
    assert candidate_entity.status == EntityStatus.rejected


async def test_undo_of_transfer_returns_to_rejected_not_dismissed(
    client: AsyncClient, db_session: AsyncSession, admin_user: User,
    organization: Organization, department: Department, org_owner: OrgMember,
    candidate_entity: Entity,
):
    """Отмена перевода в отдел возвращает «Отказ», а не «Уволен».

    Случай Саленик (21.10.2026): кандидата с отказом перевели с доски «Штат» в
    отдел, затем удалили запись истории. Заявка вернулась в «Отказ», но защита
    «отказ у оформленного в отдел = увольнение» подменяла статус на «Уволен», и
    карточка с доской расходились. Отмена перевода — не новое решение по
    человеку: он возвращается ровно туда, откуда его подняли.
    """
    now = datetime.utcnow()
    vacancy = Vacancy(
        org_id=organization.id, department_id=department.id, created_by=admin_user.id,
        title="Персональный ассистент", status=VacancyStatus.open, salary_currency="RUB",
        created_at=now, updated_at=now,
    )
    db_session.add(vacancy)
    await db_session.commit()
    app = VacancyApplication(
        vacancy_id=vacancy.id, entity_id=candidate_entity.id,
        stage=ApplicationStage.transferred, stage_order=1, created_by=admin_user.id,
        applied_at=now, last_stage_change_at=now, updated_at=now,
    )
    db_session.add(app)
    candidate_entity.status = EntityStatus.transferred
    await db_session.commit()
    moved = StageTransition(
        application_id=app.id, entity_id=candidate_entity.id,
        from_stage=ApplicationStage.rejected.value,
        to_stage=ApplicationStage.transferred.value,
        changed_by=admin_user.id, created_at=now,
    )
    db_session.add(moved)
    await db_session.commit()

    r = await client.delete(
        f"/api/vacancies/applications/{app.id}/history/{moved.id}",
        headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    assert r.json()["entity_status"] == EntityStatus.rejected.value
    await db_session.refresh(candidate_entity)
    assert candidate_entity.status == EntityStatus.rejected
