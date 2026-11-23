"""Привязка Telegram через сайт (прод 23.11.2026): баннер вёл на «?start=bind_<id>»,
а бот такие ссылки отклоняет («Эта ссылка устарела») — привязать Telegram было нельзя."""


async def test_link_info_has_no_dead_bind_link(client, admin_user, admin_token, get_auth_headers, monkeypatch):
    monkeypatch.setattr("api.config.settings.telegram_bot_username", "Staffwise_bot")
    admin_user.telegram_id = None
    r = await client.get("/api/auth/telegram-link", headers=get_auth_headers(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert body["is_linked"] is False and body["bot_username"] == "Staffwise_bot"
    assert body["link_url"] is None  # мёртвой ссылки bind_<id> больше нет


async def test_bind_link_is_one_time_token(client, admin_user, admin_token, get_auth_headers, monkeypatch):
    monkeypatch.setattr("api.config.settings.telegram_bot_username", "Staffwise_bot")
    r = await client.post("/api/auth/telegram-bind-link", json={}, headers=get_auth_headers(admin_token))
    assert r.status_code == 200
    link = r.json()["link"]
    assert link.startswith("https://t.me/Staffwise_bot?start=")
    assert "bind_" not in link
