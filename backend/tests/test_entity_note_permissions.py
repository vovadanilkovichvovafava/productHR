"""Права на удаление/редактирование комментариев кандидата (extra_data.notes).

_note_can_modify докстрингом всегда обещал «автор ИЛИ админ/owner ИЛИ superadmin»,
но код проверял только superadmin+автора — обычный org-admin/owner получал 403 при
попытке удалить чужой комментарий (в т.ч. с @-упоминанием). Проверяем все 4 роли.
"""
import pytest
from sqlalchemy import select

from api.models.database import Entity, EntityType, EntityStatus
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _make_candidate_with_note(db_session, organization, author):
    entity = Entity(
        org_id=organization.id, type=EntityType.candidate, name="Тест",
        status=EntityStatus.new,
        extra_data={"notes": [{"id": "note-1", "text": "@упоминание", "author_id": author.id, "author_name": author.name}]},
    )
    db_session.add(entity)
    await db_session.commit()
    return entity.id


@pytest.mark.asyncio
async def test_author_can_delete_own_note(client, db_session, organization, second_user, org_member):
    eid = await _make_candidate_with_note(db_session, organization, second_user)
    r = await client.delete(f"/api/entities/{eid}/notes/note-1", headers=_h(second_user))
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_org_admin_can_delete_others_note(
    client, db_session, organization, second_user, org_member, admin_user, org_owner
):
    """Регрессия: раньше org-owner/admin получал 403 на чужой комментарий."""
    eid = await _make_candidate_with_note(db_session, organization, second_user)
    r = await client.delete(f"/api/entities/{eid}/notes/note-1", headers=_h(admin_user))
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_plain_member_cannot_delete_others_note(
    client, db_session, organization, admin_user, org_owner, second_user, org_member
):
    """Обычный member (не автор, не admin/owner) — по-прежнему 403.

    Заметка автора admin_user (owner), удаляет её second_user (plain member).
    """
    eid = await _make_candidate_with_note(db_session, organization, admin_user)
    r = await client.delete(f"/api/entities/{eid}/notes/note-1", headers=_h(second_user))
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_deleted_note_actually_removed(client, db_session, organization, second_user, org_member, admin_user, org_owner):
    eid = await _make_candidate_with_note(db_session, organization, second_user)
    r = await client.delete(f"/api/entities/{eid}/notes/note-1", headers=_h(admin_user))
    assert r.status_code == 200, r.text
    entity = (await db_session.execute(select(Entity).where(Entity.id == eid))).scalar_one()
    assert entity.extra_data.get("notes") == []
