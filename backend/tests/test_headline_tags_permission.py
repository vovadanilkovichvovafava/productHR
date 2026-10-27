"""Рекрутёр правит кандидата коллеги (2026-09-10 теги, 2026-09-15 все поля).

Раньше PUT /entities/{id} пускал только автора/админа, и рекрутёр на кандидате
коллеги получал 403 («Ошибка сохранения тега», «Ошибка сохранения» в форме).
Теперь любого кандидата может править любой рекрутёр орга; member — нет.
"""
from datetime import datetime

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import Entity, OrgMember, OrgRole, Organization, User
from api.services.auth import create_access_token
from tests.conftest import auth_headers

TAGS = [{"text": "Сильный", "color": "green"}]


@pytest_asyncio.fixture
async def hr_member(db_session: AsyncSession, organization: Organization, second_user: User) -> OrgMember:
    member = OrgMember(
        org_id=organization.id,
        user_id=second_user.id,
        role=OrgRole.hr,
        created_at=datetime.utcnow(),
    )
    db_session.add(member)
    await db_session.commit()
    return member


def _headers(user: User) -> dict:
    return auth_headers(create_access_token(data={"sub": str(user.id)}))


async def test_recruiter_can_set_headline_tags_on_colleagues_candidate(
    client: AsyncClient, db_session: AsyncSession, candidate_entity: Entity,
    hr_member: OrgMember, second_user: User,
):
    r = await client.put(
        f"/api/entities/{candidate_entity.id}",
        json={"extra_data": {"headline_tags": TAGS}},
        headers=_headers(second_user),
    )
    assert r.status_code == 200, r.text
    await db_session.refresh(candidate_entity)
    assert candidate_entity.extra_data["headline_tags"] == TAGS


async def test_recruiter_can_edit_any_field_of_colleagues_candidate(
    client: AsyncClient, db_session: AsyncSession, candidate_entity: Entity,
    hr_member: OrgMember, second_user: User,
):
    r = await client.put(
        f"/api/entities/{candidate_entity.id}",
        json={"telegram_usernames": ["@Bannucchio"], "extra_data": {"city": "Israel"}},
        headers=_headers(second_user),
    )
    assert r.status_code == 200, r.text
    await db_session.refresh(candidate_entity)
    assert candidate_entity.telegram_usernames == ["bannucchio"]
    assert candidate_entity.extra_data["city"] == "Israel"


async def test_plain_member_still_cannot_edit(
    client: AsyncClient, db_session: AsyncSession, organization: Organization,
    candidate_entity: Entity, second_user: User,
):
    db_session.add(OrgMember(
        org_id=organization.id, user_id=second_user.id, role=OrgRole.member,
        created_at=datetime.utcnow(),
    ))
    await db_session.commit()
    r = await client.put(
        f"/api/entities/{candidate_entity.id}",
        json={"name": "Другое имя"},
        headers=_headers(second_user),
    )
    assert r.status_code == 403
