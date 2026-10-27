"""Решение по одной паре дублей не снимает баннер с остальных (2026-09-15).

Раньше «разные люди» по одной из нескольких похожих анкет снимало
hidden_duplicate_id целиком — остальные похожие оставались непроверенными.
"""
from datetime import datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import (
    Department, Entity, EntityStatus, EntityType, OrgMember, Organization, User,
)
from api.services.auth import create_access_token
from tests.conftest import auth_headers


async def _candidate(db, org, dept, user, name):
    e = Entity(
        org_id=org.id, department_id=dept.id, created_by=user.id, name=name,
        email="ivanov.k@example.com", type=EntityType.candidate,
        status=EntityStatus.new, created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


async def test_dismiss_moves_banner_to_next_duplicate_then_clears(
    client: AsyncClient, db_session: AsyncSession, organization: Organization,
    department: Department, admin_user: User, org_owner: OrgMember,
):
    a = await _candidate(db_session, organization, department, admin_user, "Иванов Кирилл Петрович")
    b = await _candidate(db_session, organization, department, admin_user, "Иванов Кирилл Сергеевич")
    new = await _candidate(db_session, organization, department, admin_user, "Иванов Кирилл Владимирович")
    new.extra_data = {"hidden_duplicate_id": b.id}
    await db_session.commit()
    headers = auth_headers(create_access_token(data={"sub": str(admin_user.id)}))

    r = await client.post(f"/api/entities/{new.id}/dismiss-duplicate", json={"duplicate_id": b.id}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["next_duplicate_id"] == a.id
    await db_session.refresh(new)
    assert new.extra_data.get("hidden_duplicate_id") == a.id

    r = await client.post(f"/api/entities/{new.id}/dismiss-duplicate", json={"duplicate_id": a.id}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["next_duplicate_id"] is None
    await db_session.refresh(new)
    assert "hidden_duplicate_id" not in new.extra_data
