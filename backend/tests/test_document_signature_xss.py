"""Сторож: подпись документа — только настоящий PNG с холста.

`POST /documents/{id}/sign` проверял лишь `startswith("data:image/")`. В строку
подписи дописывали `" onerror="…`, и при «Скачать PDF» у HR это выполнялось в
его сессии (хранимый XSS, до 27.10.2026). Размер не ограничивался.
"""
import base64

import pytest

from api.models.database import Employee, SignedDocument
from api.services.auth import create_access_token

PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32).decode()


def _h(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


async def _doc(db, org, user):
    emp = Employee(user_id=user.id, org_id=org.id, is_active=True)
    db.add(emp)
    await db.flush()
    doc = SignedDocument(employee_id=emp.id, title="NDA", content_rendered="Текст {{signature}}", status="pending")
    db.add(doc)
    await db.commit()
    return doc


@pytest.mark.parametrize("bad", [
    'data:image/png;base64,AA" onerror="alert(1)',
    "data:image/svg+xml;base64,PHN2ZyBvbmxvYWQ9YWxlcnQoMSk+",
    "data:image/png;base64," + base64.b64encode(b"GIF89a" + b"\x00" * 8).decode(),  # не PNG внутри
    "data:image/png;base64," + "A" * 500_000,  # слишком большая
    "javascript:alert(1)",
])
async def test_bad_signature_rejected(client, db_session, organization, org_member, second_user, bad):
    doc = await _doc(db_session, organization, second_user)

    resp = await client.post(f"/api/documents/{doc.id}/sign", json={"signature_data": bad}, headers=_h(second_user))

    assert resp.status_code == 400
    await db_session.refresh(doc)
    assert doc.status == "pending"
    assert doc.signature_data is None


async def test_png_signature_accepted_once(client, db_session, organization, org_member, second_user):
    doc = await _doc(db_session, organization, second_user)

    ok = await client.post(f"/api/documents/{doc.id}/sign", json={"signature_data": PNG}, headers=_h(second_user))
    again = await client.post(f"/api/documents/{doc.id}/sign", json={"signature_data": PNG}, headers=_h(second_user))

    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "signed"
    assert again.status_code == 400


def test_render_does_not_expand_markers_from_employee_data():
    from types import SimpleNamespace
    from api.routes.documents import _render_template

    emp = SimpleNamespace(position="Dev", department=None, phone="", telegram_username="",
                          extra_data={"address": "ул. {{signature}} {{passport_number}}", "passport_number": "AB1"})
    user = SimpleNamespace(name="Иван", email="i@x")

    out = _render_template("Адрес: {{address}}. Паспорт: {{passport_number}}. Подпись: {{signature}}", emp, user)

    assert out.count("{{signature}}") == 1  # только из шаблона
    assert "AB1" in out and "Адрес: ул. { {signature} } { {passport_number} }" in out


@pytest.mark.parametrize("title,nda,contract", [
    ("NDA", True, False),
    ("Соглашение NDA для разработчиков", True, False),
    ("Agenda", False, False),
    ("Standard terms", False, False),
    ("Трудовой договор", False, True),
    ("Контракт", False, True),
])
async def test_signing_flags_by_word(client, db_session, organization, org_member, second_user, title, nda, contract):
    from api.models.database import DocumentTemplate

    tmpl = DocumentTemplate(org_id=organization.id, name=title, content="x")
    db_session.add(tmpl)
    await db_session.flush()
    doc = await _doc(db_session, organization, second_user)
    doc.template_id = tmpl.id
    await db_session.commit()

    resp = await client.post(f"/api/documents/{doc.id}/sign", json={"signature_data": PNG}, headers=_h(second_user))

    assert resp.status_code == 200, resp.text
    emp = await db_session.get(Employee, doc.employee_id)
    await db_session.refresh(emp)
    assert bool(emp.nda_signed) is nda
    assert bool(emp.contract_signed) is contract


def test_frontend_template_variables_match_server():
    """Окно шаблона перечисляет и проверяет переменные по списку во фронте
    (factorial/lib/templateVariables.ts) — он должен совпадать с тем, что
    подставляет сервер, иначе HR увидит ложное «неизвестная переменная»."""
    import re
    from pathlib import Path
    from types import SimpleNamespace
    from api.routes.documents import _render_template

    ts = (Path(__file__).resolve().parents[2] / "frontend/src/factorial/lib/templateVariables.ts").read_text()
    front = set(re.findall(r"'([a-z_]+)'", ts))
    emp = SimpleNamespace(position="", department=None, phone="", telegram_username="", extra_data={})
    user = SimpleNamespace(name="", email="")
    probe = " ".join("{{%s}}" % v for v in front)
    left = set(re.findall(r"\{\{([a-z_]+)\}\}", _render_template(probe, emp, user)))
    assert left == {"signature"}, f"сервер не знает: {left - {'signature'}}"
