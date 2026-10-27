"""Контакты кандидата из шапки текста резюме — полноценный признак (22.09.2026).

Чужие контакты (рекомендатели, руководители, телефоны компаний) — ниже шапки
или помечены словами «руководитель», «контактное лицо» — не берутся. Резюме
свободной формы (без заголовков разделов) не даёт ничего.
"""
import pytest

from api.models.database import DataMigrationMark, Entity, EntityStatus, EntityType
from api.services.duplicate_matcher import compare_key_sets
from api.services.resume_contacts import (
    BACKFILL_MARK, backfill_resume_contacts_once, extract_header_contacts,
)
from api.services.resume_text_extract import set_resume_contacts
from api.services.similarity import build_dup_keys, match_level

HH = """Иванов Иван Петрович
Мужчина, 30 лет, родился 1 января 1994
+7 (999) 123-45-67 — предпочитаемый способ связи
ivan.petrov@mail.ru
Telegram: @ivan_petrov94
Проживает: Москва
Желаемая должность и зарплата
Менеджер по продажам
Опыт работы — 5 лет
ООО Ромашка, тел. +7 (495) 111-22-33
Рекомендации
Петров Пётр (руководитель), +7 (916) 555-44-33, petrov@romashka.ru"""


def test_header_contacts_taken_references_ignored():
    c = extract_header_contacts(HH)
    assert c == {"phones": ["+79991234567"], "emails": ["ivan.petrov@mail.ru"],
                 "telegrams": ["ivan_petrov94"]}


def test_contact_person_in_header_is_ignored():
    c = extract_header_contacts("Сидоров Сергей\n+7 903 222-33-44\n"
                                "Контактное лицо: Анна, +7 903 999-00-11\nОпыт работы\n")
    assert c["phones"] == ["+79032223344"]


def test_free_form_resume_gives_nothing():
    c = extract_header_contacts("Резюме. Иванов Иван. Звоните +7 999 123 45 67, "
                                "мой руководитель +7 916 555 44 33")
    assert c == {"phones": [], "emails": [], "telegrams": []}


def test_service_email_and_portal_channel_skipped():
    c = extract_header_contacts("Кулеш Руслан\n+375 (29) 521-73-36\nsupport@rabota.by\n"
                                "t.me/hh_b2b\nЖелаемая должность\n")
    assert c == {"phones": ["+375295217336"], "emails": [], "telegrams": []}


def test_resume_phone_matches_card_phone_as_identity():
    extra = {}
    assert set_resume_contacts(extra, HH, file_id=5)
    a = build_dup_keys(name="Иванов Иван", extra_data=extra)  # в карточке контактов нет
    b = build_dup_keys(name="Петров Сергей", phone="8 999 123-45-67")
    strength, confidence, signals = compare_key_sets(a, b)
    assert strength == "phone"
    sig = next(s for s in signals if s.field == "phone")
    assert sig.identity and "из текста резюме" in sig.label


def test_resume_contacts_plus_name_is_exact():
    extra = {}
    set_resume_contacts(extra, HH)
    a = build_dup_keys(name="Иванов Иван Петрович", extra_data=extra)
    b = build_dup_keys(name="Иванов Иван", email="ivan.petrov@mail.ru")
    _, confidence, signals = compare_key_sets(a, b)
    assert match_level(signals) == "exact" and confidence == 100


def test_reference_phone_does_not_match():
    extra = {}
    set_resume_contacts(extra, HH)
    a = build_dup_keys(name="Иванов Иван", extra_data=extra)
    b = build_dup_keys(name="Петров Пётр", phone="+7 916 555-44-33")  # рекомендатель
    strength, _, _ = compare_key_sets(a, b)
    assert strength is None


@pytest.mark.asyncio
async def test_backfill_once(db_session, organization):
    e = Entity(org_id=organization.id, type=EntityType.candidate, status=EntityStatus.new,
               name="Иванов Иван", extra_data={"resume_text": HH})
    f = Entity(org_id=organization.id, type=EntityType.candidate, status=EntityStatus.new,
               name="Без резюме", extra_data={})
    db_session.add_all([e, f])
    await db_session.commit()

    assert await backfill_resume_contacts_once(db_session) == 1
    await db_session.refresh(e)
    assert e.extra_data["resume_contacts"]["phones"] == ["+79991234567"]
    assert await db_session.get(DataMigrationMark, BACKFILL_MARK) is not None
    assert await backfill_resume_contacts_once(db_session) == 0
