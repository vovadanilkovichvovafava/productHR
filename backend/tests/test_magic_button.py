"""Расширение «Magic Button»: проверка дублей и добавление кандидата (22.10.2026).

Нашлось при проверке расширения на проде: подписи этапов в «Уже в базе» шли из
старого словаря попапа («Практика» вместо «Интервью с HR»), комментарий из
попапа ложился в ленту отдельной строкой без воронки, в удалённую воронку можно
было добавить, а у кандидата без зарплаты стояла валюта «тенге».
"""
from datetime import datetime

import pytest
from sqlalchemy import select

from api.models.database import (
    ApplicationStage, Entity, EntityStatus, EntityType, StageTransition,
    Vacancy, VacancyApplication, VacancyStatus,
)
from api.routes import magic_button
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


@pytest.fixture(autouse=True)
def no_background(monkeypatch):
    # Фон после ответа (фото с hh, ИИ-профиль) открывает свои соединения и ходит
    # в сеть — в тестах не нужен.
    async def noop(*a, **k):
        return None
    monkeypatch.setattr(magic_button, "_generate_resume_files", noop)
    monkeypatch.setattr(magic_button, "_download_candidate_photo_eager", noop)


@pytest.fixture
async def funnel(db_session, organization, department, admin_user, org_owner):
    now = datetime.utcnow()
    v = Vacancy(org_id=organization.id, department_id=department.id, created_by=admin_user.id,
                title="Трафик", status=VacancyStatus.open, salary_currency="RUB",
                extra_data={"accepted_by": [admin_user.id]}, created_at=now, updated_at=now)
    db_session.add(v)
    await db_session.commit()
    return v.id


def _payload(**kw):
    data = {"full_name": "Смирнова Анна", "source_url": "https://hh.ru/resume/abc123", "source": "hh.ru"}
    data.update(kw)
    return data


async def test_check_duplicate_sends_russian_labels(client, db_session, organization, admin_user, funnel):
    H = _h(admin_user)
    now = datetime.utcnow()
    e = Entity(org_id=organization.id, name="Смирнова Анна", type=EntityType.candidate,
               status=EntityStatus.practice, email="anna@mail.test", created_by=admin_user.id)
    gone = Vacancy(org_id=organization.id, created_by=admin_user.id, title="Удалённая",
                   status=VacancyStatus.open, salary_currency="RUB", deleted_at=now,
                   created_at=now, updated_at=now)
    db_session.add_all([e, gone])
    await db_session.commit()
    db_session.add_all([
        VacancyApplication(vacancy_id=funnel, entity_id=e.id, stage=ApplicationStage.phone_screen,
                           stage_order=1, applied_at=now, updated_at=now),
        VacancyApplication(vacancy_id=gone.id, entity_id=e.id, stage=ApplicationStage.assessment,
                           stage_order=1, applied_at=now, updated_at=now),
    ])
    await db_session.commit()

    r = await client.post("/api/magic-button/check-duplicate", headers=H,
                          json={"full_name": "Анна Смирнова", "email": "anna@mail.test"})
    assert r.status_code == 200, r.text
    dup = r.json()["duplicates"][0]
    # Значение — сама подпись: попап прошлых версий покажет его как есть.
    assert dup["status"] == "Интервью с HR" and dup["status_key"] == "practice"
    assert [(a["vacancy_title"], a["stage"], a["stage_key"]) for a in dup["applications"]] == [
        ("Трафик", "Интервью с HR", "phone_screen"),
    ]


async def test_comment_goes_into_first_history_row(client, db_session, admin_user, funnel):
    r = await client.post("/api/magic-button/parse", headers=_h(admin_user),
                          json=_payload(vacancy_id=funnel, comment="  Сильный кандидат  "))
    assert r.status_code == 200, r.text
    eid = r.json()["entity_id"]
    e = await db_session.get(Entity, eid)
    await db_session.refresh(e)
    assert not (e.extra_data or {}).get("notes")  # не отдельной заметкой
    rows = (await db_session.execute(
        select(StageTransition).where(StageTransition.entity_id == eid)
    )).scalars().all()
    assert [(t.to_stage, t.comment) for t in rows] == [("applied", "Сильный кандидат")]
    assert e.expected_salary_currency == "RUB"


async def test_without_funnel_comment_is_a_stage_note(client, db_session, admin_user, org_owner):
    r = await client.post("/api/magic-button/parse", headers=_h(admin_user),
                          json=_payload(comment="Позвонить в пятницу",
                                        source_url="https://rabota.by/resume/x1", source="hh.ru"))
    assert r.status_code == 200, r.text
    e = await db_session.get(Entity, r.json()["entity_id"])
    await db_session.refresh(e)
    notes = e.extra_data["notes"]
    assert [(n["text"], n["stage_label"]) for n in notes] == [("Позвонить в пятницу", "Новый")]
    assert e.expected_salary_currency == "BYN"  # rabota.by


async def test_deleted_funnel_is_refused_and_nothing_is_created(client, db_session, organization, admin_user, funnel):
    v = await db_session.get(Vacancy, funnel)
    v.deleted_at = datetime.utcnow()
    await db_session.commit()
    before = (await db_session.execute(select(Entity.id))).scalars().all()

    r = await client.post("/api/magic-button/parse", headers=_h(admin_user), json=_payload(vacancy_id=funnel))
    assert r.status_code == 404
    after = (await db_session.execute(select(Entity.id))).scalars().all()
    assert after == before


async def test_duplicate_found_by_phone_in_other_format(client, db_session, organization, admin_user, org_owner):
    e = Entity(org_id=organization.id, name="Петров Пётр", type=EntityType.candidate,
               status=EntityStatus.new, phone="8 (029) 111-22-33", created_by=admin_user.id)
    db_session.add(e)
    await db_session.commit()
    eid = e.id
    r = await client.post("/api/magic-button/parse", headers=_h(admin_user),
                          json=_payload(full_name="Кандидат", phone="+375 29 111 22 33"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_duplicate"] is True and body["duplicate_info"]["entity_id"] == eid


@pytest.mark.parametrize("text,expected", [
    ("150 000 ₽", (150000, 150000, "RUB")),
    ("от 2 000 Br", (2000, None, "BYN")),
    ("до 3 000 $", (None, 3000, "USD")),
    (None, (None, None, "RUB")),
])
def test_parse_salary(text, expected):
    assert magic_button._parse_salary(text, "https://hh.ru/resume/1") == expected


async def test_extension_version(client, admin_user):
    r = await client.get("/api/extension/version", headers=_h(admin_user))
    assert r.status_code == 200
    assert r.json()["version"].count(".") == 2
