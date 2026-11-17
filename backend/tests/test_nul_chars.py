"""Нулевой символ в extra_data карточки ронял поиск у всех (17.11.2026).

Колонка json: Postgres её принимает, но `extra_data -> 'notes'` на такой строке
падает «unsupported Unicode escape sequence», и /candidates/kanban?q=… отдавал
500 на любой запрос. Сторож: при записи символ вырезается, старые строки
вычищает шаг при старте (services/nul_chars.py).
"""
import pytest
from sqlalchemy import select

from api.models.database import Entity, EntityStatus, EntityType
from api.services.nul_chars import has_nul, strip_nul


def test_strip_nul_nested():
    dirty = {"resume_text": "a\x00b", "list": ["x\x00", {"k\x00": "v"}], "n": 1}
    clean = strip_nul(dirty)
    assert clean == {"resume_text": "ab", "list": ["x", {"k": "v"}], "n": 1}
    assert has_nul(dirty) and not has_nul(clean)


@pytest.mark.asyncio
async def test_entity_save_strips_nul(db_session, organization, admin_user):
    e = Entity(org_id=organization.id, name="Нуль Тест", type=EntityType.candidate,
               status=EntityStatus.new, created_by=admin_user.id,
               extra_data={"resume_text": "до\x00после"})
    db_session.add(e)
    await db_session.commit()
    assert e.extra_data["resume_text"] == "допосле"

    e.extra_data = {**e.extra_data, "notes": [{"text": "ник\x00 @x"}]}
    await db_session.commit()
    stored = (await db_session.execute(select(Entity.extra_data).where(Entity.id == e.id))).scalar_one()
    assert not has_nul(stored)
