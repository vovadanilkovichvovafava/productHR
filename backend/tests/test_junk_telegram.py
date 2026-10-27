"""hh_b2b — канал hh.ru, а не Telegram кандидата (прод, 22.09.2026).

У 42 активных карточка и окно сравнения показывали «hh_b2b» (он был первым в
списке), а совпадение считалось по настоящему нику, шедшему вторым, — рекрутёр
видел «Совпадение Telegram» при разных никах.
"""
import pytest
from sqlalchemy import select

from api.models.database import DataMigrationMark, Entity, EntityStatus, EntityType
from api.routes.entities.common import normalize_and_validate_identifiers
from api.services.service_email_cleanup import JUNK_TG_CLEANUP_MARK, remove_junk_telegram_once
from api.services.similarity import first_real_telegram, is_junk_telegram


def test_junk_detection():
    for v in ("hh_b2b", "@hh_b2b", "HH_B2B", "telegram", "hh"):
        assert is_junk_telegram(v)
    for v in ("yrsrss", "@ivan_petrov", "hh_b2b_fan"):
        assert not is_junk_telegram(v)


def test_first_real_telegram_skips_portal_channel():
    assert first_real_telegram(["hh_b2b", "yrsrss"]) == "yrsrss"
    assert first_real_telegram(["hh_b2b"]) is None
    assert first_real_telegram(None) is None


def test_saving_drops_portal_channel():
    tgs, _, _ = normalize_and_validate_identifiers(telegram_usernames=["@hh_b2b", "@yrsrss"])
    assert tgs == ["yrsrss"]


def test_extension_payload_drops_portal_channel():
    from api.routes.magic_button import DuplicateCheckRequest, MagicButtonData
    assert MagicButtonData(full_name="X", telegram="@hh_b2b", source_url="u", source="hh.ru").telegram is None
    assert MagicButtonData(full_name="X", telegram="@yrsrss", source_url="u", source="hh.ru").telegram == "@yrsrss"
    assert DuplicateCheckRequest(full_name="X", telegram="hh_b2b").telegram is None


@pytest.mark.asyncio
async def test_cleanup_removes_portal_channel_once(db_session, organization):
    a = Entity(org_id=organization.id, type=EntityType.candidate, status=EntityStatus.new,
               name="Филатов Ярослав", telegram_usernames=["hh_b2b", "yrsrss"])
    b = Entity(org_id=organization.id, type=EntityType.candidate, status=EntityStatus.new,
               name="Другой", telegram_usernames=["hh_b2b"])
    c = Entity(org_id=organization.id, type=EntityType.candidate, status=EntityStatus.new,
               name="Третий", telegram_usernames=["ivan"])
    db_session.add_all([a, b, c])
    await db_session.commit()

    assert await remove_junk_telegram_once(db_session) == 2
    for e in (a, b, c):
        await db_session.refresh(e)
    assert a.telegram_usernames == ["yrsrss"]
    assert b.telegram_usernames == []
    assert c.telegram_usernames == ["ivan"]
    assert await db_session.get(DataMigrationMark, JUNK_TG_CLEANUP_MARK) is not None
    assert await remove_junk_telegram_once(db_session) == 0
