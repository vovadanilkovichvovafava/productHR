"""Дозаливка (HR_DELTA): ответ на анкету, пришедший пакетом, уведомляет рекрутёров.

Кандидат заполнил анкету по старой ссылке Энцеладуса (Губич, 31.10.2026) — ответ
приехал дозаливкой, а «Ответ на анкету» не получил никто. hr_delta работает
через psycopg2 и SQL Postgres, поэтому тест — на настоящей базе: задайте
HR_DELTA_TEST_DSN (например postgresql://localhost/hrdelta_test). База
пересоздаётся целиком — не указывайте рабочую. Без переменной тест пропускается.
"""
import os

import pytest

DSN = os.environ.get("HR_DELTA_TEST_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="нужен HR_DELTA_TEST_DSN (пустая тестовая база Postgres)")


@pytest.fixture
def db():
    from sqlalchemy import create_engine, text

    import api.models  # noqa: F401
    from api.models.database import Base

    eng = create_engine(DSN)
    with eng.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    Base.metadata.create_all(eng)
    with eng.begin() as c:
        c.execute(text("INSERT INTO organizations (id, name, slug) VALUES (1, 'o', 'o')"))
        for uid, name in ((5, "Эльвира"), (6, "Мария"), (7, "Влада")):
            c.execute(text(
                "INSERT INTO users (id, email, password_hash, name, role, token_version) "
                f"VALUES ({uid}, 'u{uid}@x.y', 'x', '{name}', 'admin', 0)"
            ))
        c.execute(text(
            "INSERT INTO entities (id, org_id, type, name, status, extra_data, tags, is_archived, is_transferred, version, created_by) "
            "VALUES (10, 1, 'candidate', 'Губич Виктория', 'new', '{}', '[]', false, false, 1, 7)"
        ))
        c.execute(text("INSERT INTO vacancies (id, org_id, title, status, created_by) VALUES (3, 1, 'Трафик', 'open', 5)"))
        # заявку ведёт Мария; отправитель ссылки — Эльвира
        c.execute(text("INSERT INTO vacancy_applications (id, vacancy_id, entity_id, stage, stage_order, created_by) VALUES (7, 3, 10, 'screening', 1, 6)"))
        c.execute(text("INSERT INTO form_templates (id, org_id, slug, title, fields, created_by, is_template, is_active) VALUES (4, 1, 'anketa', 'Анкета трафик', '[]', 5, true, true)"))
        for seq in ("entities", "vacancies", "vacancy_applications", "form_templates", "users"):
            c.execute(text(f"SELECT setval(pg_get_serial_sequence('{seq}', 'id'), 100)"))
    yield eng
    eng.dispose()


def _bundle():
    return {"version": 1, "steps": [
        {"op": "insert", "table": "form_dispatches", "rows": [
            {"$new": "form_dispatches:472", "form_id": 4, "entity_id": 10, "token": "tok-gubich",
             "status": "submitted", "created_by": 5, "submitted_at": "2026-10-31 10:00:00"}]},
        {"op": "insert", "table": "form_submissions", "rows": [
            {"$new": "form_submissions:286", "form_id": 4, "entity_id": 10, "data": {"q": "a"},
             "dispatch_id": {"$ref": "form_dispatches:472"}, "submitted_at": "2026-10-31 10:00:00"}]},
        {"op": "update", "table": "form_dispatches", "rows": [
            {"id": {"$ref": "form_dispatches:472"}, "submission_id": {"$ref": "form_submissions:286"}}]},
    ]}


def _notifications(eng):
    from sqlalchemy import text
    with eng.connect() as c:
        return c.execute(text(
            "SELECT user_id, type, title, message, link FROM notifications ORDER BY user_id"
        )).all()


def test_new_answer_notifies_sender_and_current_recruiter_once(db):
    from api.services.hr_delta import apply_delta

    report = apply_delta(DSN, _bundle(), dry_run=False)
    assert report["form_answer_notifications"]["created"] == 2
    rows = _notifications(db)
    assert [r[0] for r in rows] == [5, 6]  # Эльвира (отправила) и Мария (ведёт), Влада — нет
    assert rows[0][1:] == (
        "form_submitted", "Ответ на анкету",
        "Губич Виктория заполнил(а) анкету «Анкета трафик»",
        "/all-candidates?entity=10&tab=anketa",
    )

    # дозаливка по уже перенесённому ответу — второй раз не уведомляем
    again = apply_delta(DSN, {"version": 1, "steps": [
        {"op": "notify_form_answers", "table": "form_submissions", "rows": [{"token": "tok-gubich"}]}]}, dry_run=False)
    assert again["steps"][0]["created"] == 0 and again["steps"][0]["already"] == 2
    assert len(_notifications(db)) == 2


def test_dry_run_creates_nothing(db):
    from api.services.hr_delta import apply_delta

    report = apply_delta(DSN, _bundle(), dry_run=True)
    assert report["form_answer_notifications"]["created"] == 2
    assert _notifications(db) == []


def test_sender_is_current_recruiter_gets_one(db):
    from sqlalchemy import text
    from api.services.hr_delta import apply_delta

    with db.begin() as c:
        c.execute(text("UPDATE vacancy_applications SET created_by = 5"))
    apply_delta(DSN, _bundle(), dry_run=False)
    assert [r[0] for r in _notifications(db)] == [5]


def test_without_live_application_card_owner_is_notified(db):
    from sqlalchemy import text
    from api.services.hr_delta import apply_delta

    with db.begin() as c:
        c.execute(text("UPDATE vacancy_applications SET stage = 'rejected'"))
    apply_delta(DSN, _bundle(), dry_run=False)
    assert [r[0] for r in _notifications(db)] == [5, 7]  # отправитель + за кем карточка
