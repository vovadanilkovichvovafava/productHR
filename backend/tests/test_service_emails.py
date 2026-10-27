"""Служебные почты сайтов и город больше не делают кандидатов «похожими» (22.09.2026).

Прод: у шести разных людей с rabota.by почта support@rabota.by (расширение брало
ссылку поддержки сайта) + город Минск → жёлтая плашка 68% между всеми.
"""
import pytest
from sqlalchemy import select

from api.models.database import DataMigrationMark, Entity, EntityStatus, EntityType
from api.services.duplicate_matcher import compare_key_sets
from api.services.service_email_cleanup import CLEANUP_MARK, remove_service_emails_once
from api.services.similarity import build_dup_keys, is_service_email, score_soft_identity


@pytest.mark.parametrize("email", [
    "support@rabota.by", "SUPPORT@RABOTA.BY", "noreply@hh.ru", "help@minsk.rabota.by",
    "robot@superjob.ru", "no-reply@company.com", "notifications@anything.io",
])
def test_service_emails_detected(email):
    assert is_service_email(email)


@pytest.mark.parametrize("email", [
    "ivan.petrov@gmail.com", "anna@mail.ru", "rabota.by.fan@gmail.com", "k.ivanova@yandex.by",
])
def test_personal_emails_not_service(email):
    assert not is_service_email(email)


def test_rabota_by_support_email_and_city_do_not_match():
    # Ровно прод-случай: разные люди, одна «почта» сайта, один город.
    a = build_dup_keys(name="Макрицкая Екатерина", email="support@rabota.by",
                       extra_data={"city": "Минск"})
    b = build_dup_keys(name="Кулеш Руслан Валерьевич", email="support@rabota.by",
                       phone="+375 29 521 73 36", extra_data={"city": "Минск"})
    strength, confidence, signals = compare_key_sets(a, b)
    assert strength is None
    assert not signals


def test_city_is_not_in_percentage_or_reasons():
    a = build_dup_keys(name="Сидоров Иван", phone="+7 495 000-11-22",
                       extra_data={"birth_date": "14.05.1990", "city": "Москва"})
    b = build_dup_keys(name="Петров Александр", phone="+7 916 000-11-22",
                       extra_data={"birth_date": "1990-05-14", "city": "Москва"})
    soft = score_soft_identity(a, b)
    assert soft.confidence == 75  # ДР 40 + 7 цифр 35, город больше не +8
    assert "Город совпал" not in soft.reasons
    _, _, signals = compare_key_sets(a, b)
    assert not any(s.field == "city" for s in signals)


def test_extension_payload_drops_service_email():
    from api.routes.magic_button import DuplicateCheckRequest, MagicButtonData
    assert MagicButtonData(full_name="X", email="support@rabota.by",
                           source_url="u", source="rabota.by").email is None
    assert MagicButtonData(full_name="X", email="ivan@mail.ru",
                           source_url="u", source="hh.ru").email == "ivan@mail.ru"
    assert DuplicateCheckRequest(full_name="X", email="noreply@hh.ru").email is None


@pytest.mark.asyncio
async def test_cleanup_removes_service_email_and_stale_flags(db_session, organization):
    def mk(name, **kw):
        e = Entity(org_id=organization.id, type=EntityType.candidate, name=name,
                   status=EntityStatus.new, **kw)
        db_session.add(e)
        return e

    a = mk("Макрицкая Екатерина", email="support@rabota.by", extra_data={"city": "Минск"})
    b = mk("Кулеш Руслан", email="support@rabota.by", emails=["support@rabota.by", "ruslan@mail.ru"])
    c = mk("Иван Иванов", email="ivan@gmail.com")
    await db_session.flush()
    a.extra_data = {"city": "Минск", "hidden_duplicate_id": b.id,
                    "hidden_duplicate_meta": {"strength": "email", "level": "possible"}}
    b.extra_data = {"hidden_duplicate_id": a.id,
                    "hidden_duplicate_meta": {"strength": "email", "level": "possible"}}
    await db_session.commit()

    assert await remove_service_emails_once(db_session) == 2
    for e in (a, b, c):
        await db_session.refresh(e)
    assert a.email is None and b.email is None
    assert b.emails == ["ruslan@mail.ru"]
    assert c.email == "ivan@gmail.com"
    # Плашки держались на «почте» сайта — сняты сразу.
    assert "hidden_duplicate_id" not in (a.extra_data or {})
    assert "hidden_duplicate_id" not in (b.extra_data or {})
    assert await db_session.get(DataMigrationMark, CLEANUP_MARK) is not None
    assert await remove_service_emails_once(db_session) == 0
