"""«Все кандидаты» показывают ВСЕХ — требование владельца 18.09.2026.

Жалоба Эльвиры: расширение находит кандидата в базе, по ссылке карточка не
открывается, поиск руками его не находит — «но он в базе есть». Причина: доска
отбирала кандидатов только со статусами воронки (KANBAN_STATUSES), а всё
остальное — «Отозван», уволенные, легаси-статусы — выпадало и с доски, и из
поиска. Карточка существует, открывается по id, но найти её невозможно.
"""
from datetime import datetime

import pytest

from api.models.database import Entity, EntityStatus, EntityType
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _mk(db, org, name, status, creator=None):
    e = Entity(
        org_id=org.id, name=name, type=EntityType.candidate, status=status,
        created_by=creator.id if creator else None, created_at=datetime.utcnow(),
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


def _cards(board):
    return {c["name"]: col["status"] for col in board["columns"] for c in col["cards"]}


@pytest.mark.asyncio
async def test_withdrawn_candidate_is_on_the_board(client, db_session, organization, admin_user, org_owner):
    """«Отозван» — обычная колонка, а не дыра: статус есть у кандидата, значит он
    должен быть виден в общем списке."""
    await _mk(db_session, organization, "Отозванов Олег", EntityStatus.withdrawn, admin_user)

    r = await client.get("/api/candidates/kanban?per_column=500", headers=_h(admin_user))
    assert r.status_code == 200, r.text
    assert _cards(r.json()).get("Отозванов Олег") == "withdrawn"


@pytest.mark.asyncio
async def test_status_outside_funnel_lands_in_other_column(client, db_session, organization, admin_user, org_owner):
    """Статусы вне воронки (легаси) собираются в «Вне воронки» — кандидат
    остаётся видимым, а не исчезает с доски.

    Уволенные со «Штата» с 20.10.2026 сюда больше не попадают: для базы
    кандидатов это «Отказ» (владелец: «меняю статус с практики на уволен — в
    ATS он тоже перемещается в отказ»), см. test_board_ats_sync.py.
    """
    await _mk(db_session, organization, "Уволенов Урал", EntityStatus.dismissed, admin_user)
    await _mk(db_session, organization, "Легасин Лев", EntityStatus.active, admin_user)

    r = await client.get("/api/candidates/kanban?per_column=500", headers=_h(admin_user))
    cards = _cards(r.json())
    assert cards.get("Уволенов Урал") == "rejected"
    assert cards.get("Легасин Лев") == "other"

    labels = {c["status"]: c["label"] for c in r.json()["columns"]}
    assert labels["other"] == "Вне воронки"


@pytest.mark.asyncio
async def test_search_finds_candidate_with_off_funnel_status(client, db_session, organization, admin_user, org_owner):
    """Главный сценарий жалобы: кандидат в базе есть, а поиск по ФИО его не
    находил, потому что доска резала по статусу."""
    await _mk(db_session, organization, "Кузнецов Владислав Александрович", EntityStatus.withdrawn, admin_user)

    r = await client.get(
        "/api/candidates/kanban?q=Кузнецов&per_column=500", headers=_h(admin_user)
    )
    assert r.status_code == 200, r.text
    assert "Кузнецов Владислав Александрович" in _cards(r.json())


@pytest.mark.asyncio
async def test_counts_match_visible_cards(client, db_session, organization, admin_user, org_owner):
    """Счётчик колонки не должен обещать кандидатов, которых в ней нет: раньше
    «Все 1» соседствовало с пустым списком, и это читалось как потеря карточки."""
    await _mk(db_session, organization, "Счётный Семён", EntityStatus.withdrawn, admin_user)

    r = await client.get("/api/candidates/kanban?q=Счётный&per_column=500", headers=_h(admin_user))
    board = r.json()
    total_count = sum(col["count"] for col in board["columns"])
    total_cards = sum(len(col["cards"]) for col in board["columns"])
    assert total_count == total_cards == 1


@pytest.mark.asyncio
async def test_column_over_500_is_loaded_in_full(client, db_session, organization, admin_user, org_owner):
    """Этап больше 500 человек приходит ЦЕЛИКОМ (прод 21.09.2026: «Новый» — 468
    при лимите 500; дальше хвост молча терялся бы при верном бейдже)."""
    db_session.add_all([
        Entity(
            org_id=organization.id, name=f"Новичков {i}", type=EntityType.candidate,
            status=EntityStatus.new, created_by=admin_user.id, created_at=datetime.utcnow(),
        )
        for i in range(520)
    ])
    await db_session.commit()

    r = await client.get("/api/candidates/kanban?per_column=2000", headers=_h(admin_user))
    assert r.status_code == 200, r.text
    col = next(c for c in r.json()["columns"] if c["status"] == "new")
    assert col["count"] == 520
    assert len(col["cards"]) == 520

    # Поиск по-прежнему работает и ограничен своим лимитом.
    r_q = await client.get(
        "/api/candidates/kanban?q=" + "Новичков" + "&per_column=500", headers=_h(admin_user)
    )
    assert r_q.status_code == 200, r_q.text
    col_q = next(c for c in r_q.json()["columns"] if c["status"] == "new")
    assert col_q["count"] == 520
    assert len(col_q["cards"]) == 500
