"""Журнал действий (21.10.2026, services/audit.py + middleware/correlation.py).

Каждый изменяющий запрос — строка: кто, когда, что, над кем, с какими данными.
Пароли вырезаются, просмотры и служебные запросы не пишутся, читают журнал
только админы HR.
"""
from datetime import datetime

import pytest
from sqlalchemy import select

from api.models.database import (
    AuditEvent, Entity, EntityStatus, EntityType, OrgMember, OrgRole, User,
)
from api.services.audit import clean_body, describe, ids_from, should_audit
from api.services.auth import create_access_token, hash_password
from main import app


def _h(u_id):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u_id)})}"}


@pytest.fixture(autouse=True)
def audit_on():
    """В тестах журнал в базу выключен — здесь включаем."""
    app.state.audit_in_tests = True
    yield
    app.state.audit_in_tests = False


# --- чистые функции ---------------------------------------------------------

def test_what_is_audited():
    assert should_audit("POST", "/api/entities/5/notes")
    assert not should_audit("GET", "/api/entities/5")
    assert not should_audit("POST", "/api/auth/refresh")
    assert not should_audit("POST", "/api/entities/5/detect-duplicate")
    assert describe("PUT", "/api/vacancies/applications/7") == "Сменил этап / изменил заявку в воронке"
    assert describe("DELETE", "/api/vacancies/applications/7") == "Убрал кандидата из воронки"
    assert describe("DELETE", "/api/vacancies/applications/7/history/3") == "Удалил запись истории (откат этапа)"
    assert describe("POST", "/api/entities") == "Создал кандидата"
    assert describe("POST", "/api/whatever/1") == "POST /api/whatever/1"


def test_ids_and_secrets():
    assert ids_from("/api/vacancies/applications/7", None) == {"entity_id": None, "vacancy_id": None, "application_id": 7}
    assert ids_from("/api/vacancies/3/applications", {"entity_id": 9})["entity_id"] == 9
    body = clean_body(b'{"email": "a@b.c", "password": "secret", "nested": {"api_key": "x"}}',
                      "application/json", None, "")
    assert body == {"email": "a@b.c", "password": "***", "nested": {"api_key": "***"}}
    long = clean_body(('{"text": "' + "я" * 5000 + '"}').encode(), "application/json", None, "")
    assert len(long["text"]) < 2100 and "симв." in long["text"]
    assert clean_body(None, "multipart/form-data; boundary=x", 123456, "")["_файл_или_большое_тело"] == "123456 байт"


# --- через приложение ---------------------------------------------------------

@pytest.fixture
async def setup(db_session, organization, admin_user, org_owner):
    hr = User(email="hr-audit@test.local", password_hash=hash_password("x"), name="Рекрутёр Аудит", is_active=True)
    db_session.add(hr)
    await db_session.flush()
    db_session.add(OrgMember(org_id=organization.id, user_id=hr.id, role=OrgRole.hr))
    e = Entity(org_id=organization.id, type=EntityType.candidate, name="Кандидат Журнала",
               status=EntityStatus.new, created_by=admin_user.id, created_at=datetime.utcnow())
    db_session.add(e)
    await db_session.commit()
    return {"admin": admin_user.id, "admin_name": admin_user.name, "hr": hr.id, "eid": e.id}


async def test_note_is_written_with_who_what_whom(client, db_session, setup):
    r = await client.post(f"/api/entities/{setup['eid']}/notes", json={"text": "созвон прошёл"},
                          headers=_h(setup["admin"]))
    assert r.status_code == 200, r.text
    row = (await db_session.execute(
        select(AuditEvent).where(AuditEvent.entity_id == setup["eid"]).order_by(AuditEvent.id.desc())
    )).scalars().first()
    assert row is not None
    assert row.user_id == setup["admin"] and row.user_name == setup["admin_name"]
    assert row.action == "Добавил комментарий" and row.status == 200
    assert row.body == {"text": "созвон прошёл"}


async def test_views_are_not_written(client, db_session, setup):
    before = len((await db_session.execute(select(AuditEvent.id))).all())
    r = await client.get(f"/api/entities/{setup['eid']}", headers=_h(setup["admin"]))
    assert r.status_code == 200
    after = len((await db_session.execute(select(AuditEvent.id))).all())
    assert after == before


async def test_failed_attempt_is_written_too(client, db_session, setup):
    r = await client.delete(f"/api/entities/{setup['eid']}", headers=_h(setup["hr"]))
    assert r.status_code == 403
    row = (await db_session.execute(
        select(AuditEvent).where(AuditEvent.user_id == setup["hr"])
    )).scalars().first()
    assert row is not None and row.status == 403 and row.action == "Удалил кандидата (в корзину)"


async def test_journal_is_for_hr_admins_only(client, db_session, setup):
    await client.post(f"/api/entities/{setup['eid']}/notes", json={"text": "x"}, headers=_h(setup["admin"]))
    r = await client.get("/api/audit", headers=_h(setup["hr"]))
    assert r.status_code == 403
    r = await client.get(f"/api/audit?entity_id={setup['eid']}", headers=_h(setup["admin"]))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert items and items[0]["entity_name"] == "Кандидат Журнала"
    users = (await client.get("/api/audit/users", headers=_h(setup["admin"]))).json()["items"]
    assert any(u["user_id"] == setup["admin"] for u in users)


def test_vacancy_merge_report_is_not_logged_as_merge():
    # 26.10.2026: отчёт «без изменений» записался как «Слил вакансию-дубль».
    from api.services.audit import describe
    assert describe("POST", "/api/vacancies/1/merge-from/19", "dry_run=true").startswith("Посмотрел отчёт")
    assert describe("POST", "/api/vacancies/1/merge-from/19").startswith("Посмотрел отчёт")
    assert describe("POST", "/api/vacancies/1/merge-from/19", "dry_run=false") == "Слил вакансию-дубль"


def test_management_actions_have_russian_labels():
    """Действия «Управления» в журнале — по-русски, не «МЕТОД путь» (28.10.2026)."""
    cases = {
        ("POST", "/api/employees/me/passport"): "Загрузил свой скан паспорта",
        ("PUT", "/api/employees/me"): "Изменил свой профиль сотрудника",
        ("PUT", "/api/employees/7"): "Изменил карточку сотрудника",
        ("DELETE", "/api/employees/7"): "Уволил сотрудника",
        ("PUT", "/api/employees/leave-requests/3/approve"): "Одобрил заявку на отпуск",
        ("POST", "/api/documents/12/sign"): "Подписал документ",
        ("POST", "/api/invitations"): "Создал приглашение",
        ("POST", "/api/invitations/accept/abcDEF_123"): "Принял приглашение",
        ("PUT", "/api/org-units/assign/4"): "Оргсхема: перевёл сотрудника в отдел",
        ("POST", "/api/org-units"): "Оргсхема: отдел",
    }
    for (method, path), label in cases.items():
        assert describe(method, path) == label, (method, path)
