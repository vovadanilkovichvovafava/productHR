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
