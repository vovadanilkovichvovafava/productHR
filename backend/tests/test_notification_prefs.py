"""Настройки типов уведомлений: дефолты, фильтр списка/счётчика, PUT/GET prefs."""
import pytest

from api.models.database import Notification
from api.services.auth import create_access_token


def _h(user):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(user.id)})}"}


@pytest.mark.asyncio
async def test_notification_prefs_default_and_toggle(client, db_session, admin_user):
    for t in ["comment_mentioned", "form_submitted", "new_candidate", "stage_change"]:
        db_session.add(Notification(user_id=admin_user.id, type=t, title=t, is_read=False))
    await db_session.commit()
    H = _h(admin_user)

    # По умолчанию видны только упоминания и ответ на анкету.
    r = await client.get("/api/notifications", headers=H)
    assert r.status_code == 200, r.text
    assert sorted(n["type"] for n in r.json()) == ["comment_mentioned", "form_submitted"]
    r = await client.get("/api/notifications/unread-count", headers=H)
    assert r.json()["count"] == 2

    # Включаем «Новый кандидат» — появляется и в списке, и в счётчике.
    r = await client.put("/api/notifications/prefs", json={"prefs": {"new_candidate": True}}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["prefs"]["new_candidate"] is True

    r = await client.get("/api/notifications", headers=H)
    assert sorted(n["type"] for n in r.json()) == ["comment_mentioned", "form_submitted", "new_candidate"]
    r = await client.get("/api/notifications/unread-count", headers=H)
    assert r.json()["count"] == 3

    # Выключаем упоминания — пропадают.
    await client.put("/api/notifications/prefs", json={"prefs": {"comment_mentioned": False}}, headers=H)
    r = await client.get("/api/notifications", headers=H)
    assert sorted(n["type"] for n in r.json()) == ["form_submitted", "new_candidate"]

    # GET prefs отдаёт полную эффективную карту.
    r = await client.get("/api/notifications/prefs", headers=H)
    p = r.json()["prefs"]
    assert p["form_submitted"] is True
    assert p["comment_mentioned"] is False
    assert p["new_candidate"] is True
    assert p["stage_change"] is False
