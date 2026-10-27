"""Адреса, открывавшиеся без входа, закрыты (24.10.2026).

- Практиканты из Prometheus (персональные данные) — только после входа.
- Отладка (autotasks-test тратил деньги на Claude, autotasks-log показывал
  тексты сообщений, debug/routes — карта API) — только суперадмину.
- /health остаётся открытым: на него смотрит Saturn (его код не трогали; в
  тестах он ходит в настоящую базу мимо подмены и зависает — поэтому не здесь).
"""
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


INTERNS = ["/api/interns", "/api/interns/analytics", "/api/interns/student-achievements/abc"]
DEBUG = ["/debug/routes", "/health/autotasks-log", "/health/autotasks-test"]


async def test_interns_need_login(client):
    for url in INTERNS:
        assert (await client.get(url)).status_code == 401, url


async def test_debug_only_superadmin(client, db_session, admin_user, org_owner, superadmin_user):
    for url in DEBUG:
        assert (await client.get(url)).status_code == 401, url
        assert (await client.get(url, headers=_h(admin_user))).status_code == 403, url
    r = await client.get("/debug/routes", headers=_h(superadmin_user))
    assert r.status_code == 200

