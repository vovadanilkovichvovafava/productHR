"""«Не столбим кандидатов»: любой рекрутёр орга управляет любым кандидатом.

Модель A (общий пул): read — любому члену орга; edit (взять в воронку, двигать,
менять этап…) — любому РЕКРУТЁРУ (hr/admin/owner); full (удаление/трансфер) —
остаётся у создателя/админа. Cross-org закрыт.
"""
from datetime import datetime

import pytest

from api.models.database import (
    Entity, EntityType, EntityStatus, User, OrgMember, OrgRole, AccessLevel,
)
from api.routes.entities.common import check_entity_access


async def _member(db, org_id, name, email, role) -> User:
    u = User(email=email, password_hash="x", name=name)
    db.add(u)
    await db.flush()
    db.add(OrgMember(org_id=org_id, user_id=u.id, role=role, created_at=datetime.utcnow()))
    await db.flush()
    return u


async def _cand(db, org_id, creator_id) -> Entity:
    e = Entity(
        org_id=org_id, created_by=creator_id, name="Чужой Кандидат",
        type=EntityType.candidate, status=EntityStatus.active, created_at=datetime.utcnow(),
    )
    db.add(e)
    await db.flush()
    return e


@pytest.mark.asyncio
async def test_recruiter_can_manage_others_candidate(db_session, organization):
    creator = await _member(db_session, organization.id, "Создатель", "c@t.co", OrgRole.hr)
    other = await _member(db_session, organization.id, "Другой рекрутёр", "o@t.co", OrgRole.hr)
    plain = await _member(db_session, organization.id, "Обычный", "p@t.co", OrgRole.member)
    cand = await _cand(db_session, organization.id, creator.id)
    await db_session.commit()

    # Рекрутёр (НЕ создатель): видит и УПРАВЛЯЕТ, но не удаляет.
    assert await check_entity_access(cand, other, organization.id, db_session, None) is True
    assert await check_entity_access(cand, other, organization.id, db_session, AccessLevel.edit) is True
    assert await check_entity_access(cand, other, organization.id, db_session, AccessLevel.full) is False

    # Обычный член (не рекрутёр): видит, но НЕ управляет.
    assert await check_entity_access(cand, plain, organization.id, db_session, None) is True
    assert await check_entity_access(cand, plain, organization.id, db_session, AccessLevel.edit) is False


@pytest.mark.asyncio
async def test_no_cross_org_edit(db_session, organization, second_organization):
    creator = await _member(db_session, organization.id, "Создатель", "c2@t.co", OrgRole.hr)
    outsider = await _member(db_session, second_organization.id, "Чужой рекрутёр", "x@t.co", OrgRole.hr)
    cand = await _cand(db_session, organization.id, creator.id)
    await db_session.commit()

    # Рекрутёр ДРУГОЙ организации не получает edit к кандидату не своей орг
    # (read cross-org проверяется в других тестах: он доходит до PG-only
    # jsonb-запроса, который на SQLite не выполняется — здесь не дёргаем).
    assert await check_entity_access(cand, outsider, organization.id, db_session, AccessLevel.edit) is False
