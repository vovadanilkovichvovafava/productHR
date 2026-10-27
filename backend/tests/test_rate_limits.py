"""Лимиты частоты запросов (24.10.2026).

- Публичные адреса (анкета кандидата, «Поделиться», приглашения) получили
  лимиты по адресу человека.
- Адрес человека берётся из X-Forwarded-For: за прокси Saturn
  `request.client.host` один на всех, и лимит был общим на компанию.
- Лимита попыток ВХОДА нет (решение владельца, 24.10.2026).
- «На пользователя» лимиты считались до вызова ручки, когда пользователя ещё
  нет, — ключ теперь берётся из токена входа (`user_or_ip`).
"""
from starlette.requests import Request

from api.limiter import RATE_LIMIT_MESSAGE, client_ip, user_or_ip
from api.services.auth import create_access_token


def _req(headers=None, cookies=None, host="10.0.0.1"):
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    if cookies:
        raw.append((b"cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()).encode()))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": raw, "client": (host, 1234)})


def test_client_ip_prefers_forwarded():
    assert client_ip(_req({"X-Forwarded-For": "5.6.7.8, 10.0.0.2"})) == "5.6.7.8"
    assert client_ip(_req({"X-Real-IP": "9.9.9.9"})) == "9.9.9.9"
    assert client_ip(_req()) == "10.0.0.1"


def test_user_or_ip_reads_token_before_handler():
    token = create_access_token(data={"sub": "42"})
    assert user_or_ip(_req({"Authorization": f"Bearer {token}"})) == "user:42"
    assert user_or_ip(_req(cookies={"access_token": token})) == "user:42"
    # Поддельный токен — номер не верим, считаем по адресу.
    assert user_or_ip(_req({"Authorization": "Bearer abc.def.ghi", "X-Forwarded-For": "5.6.7.8"})) == "5.6.7.8"


async def test_public_form_submit_is_limited_per_ip(client):
    url = "/api/forms/public/d/no-such-token/submit"
    a = {"X-Forwarded-For": "1.1.1.1"}
    for _ in range(10):
        r = await client.post(url, json={"data": {}}, headers=a)
        assert r.status_code == 404, r.text
    r = await client.post(url, json={"data": {}}, headers=a)
    assert r.status_code == 429
    assert r.json()["detail"] == RATE_LIMIT_MESSAGE
    assert r.headers.get("retry-after") == "60"
    # Другой человек (другой адрес) не страдает от чужого лимита.
    r = await client.post(url, json={"data": {}}, headers={"X-Forwarded-For": "2.2.2.2"})
    assert r.status_code == 404


async def test_public_pages_and_reports_are_limited(client):
    h = {"X-Forwarded-For": "3.3.3.3"}
    for _ in range(20):
        r = await client.post("/api/forms/public/client-error", json={"kind": "network"}, headers=h)
        assert r.status_code == 204
    r = await client.post("/api/forms/public/client-error", json={"kind": "network"}, headers=h)
    assert r.status_code == 429

    for _ in range(20):
        assert (await client.get("/api/invitations/validate/nope", headers=h)).status_code != 429
    assert (await client.get("/api/invitations/validate/nope", headers=h)).status_code == 429


async def test_login_has_no_attempt_limit(client):
    # Владелец, 24.10.2026: лимит попыток входа убран — вход никого не запирает.
    body = {"email": "nobody@example.com", "password": "wrong"}
    for _ in range(30):
        r = await client.post("/api/auth/login", json=body, headers={"X-Forwarded-For": "4.4.4.4"})
        assert r.status_code != 429
