"""Вход только с корпоративной почтой организации (09.11.2026).

Мария: «ограничить вход только корпоративным доменом»; владелец: для всех
участников, без входа через Google. Логика — services/email_domain.py.
"""
import pytest

from api.services.email_domain import normalize_domains

CORP = "agency-mst.com"


def _h(token):
    return {"Authorization": f"Bearer {token}"}


async def _login(client, email, password, **extra):
    return await client.post("/api/auth/login", json={"email": email, "password": password, **extra})


def test_normalize_domains():
    assert normalize_domains("@Agency-MST.com, agency-mst.com") == [CORP]
    assert normalize_domains("") == []
    with pytest.raises(ValueError):
        normalize_domains("не домен")


@pytest.mark.asyncio
async def test_domain_restriction_end_to_end(
    client, db_session, superadmin_token, admin_token, user_token,
    admin_user, regular_user, second_user, org_owner, org_admin, org_member,
):
    # Владелец с почтой @test.com не может запереть сам себя.
    r = await client.put("/api/organizations/current/email-domain", json={"domains": CORP}, headers=_h(admin_token))
    assert r.status_code == 400
    assert "Сначала смените свою почту" in r.json()["detail"]

    # Суперадмин переводит владельца на корпоративную почту.
    r = await client.patch(f"/api/users/{admin_user.id}", json={"email": f"owner@{CORP}"}, headers=_h(superadmin_token))
    assert r.status_code == 200, r.text

    # Сессия Марии (админ) открыта ДО включения ограничения.
    before = await _login(client, "user@test.com", "User123", include_refresh=True)
    assert before.status_code == 200
    refresh = before.json()["refresh_token"]

    # Пробный прогон: кто потеряет вход — и ничего не сохраняется.
    r = await client.put("/api/organizations/current/email-domain",
                         json={"domains": CORP, "dry_run": True}, headers=_h(admin_token))
    assert r.status_code == 200, r.text
    assert {m["user_id"] for m in r.json()["outside"]} == {regular_user.id, second_user.id}
    assert r.json()["saved"] is False
    assert (await _login(client, "user@test.com", "User123")).status_code == 200

    # Включаем.
    r = await client.put("/api/organizations/current/email-domain", json={"domains": CORP}, headers=_h(admin_token))
    assert r.status_code == 200 and r.json()["saved"] is True
    r = await client.get("/api/organizations/current/email-domain", headers=_h(admin_token))
    assert r.json()["domains"] == [CORP]

    # Не корпоративная почта — вход закрыт с понятным текстом, верный пароль не помогает.
    r = await _login(client, "user@test.com", "User123")
    assert r.status_code == 403
    assert f"@{CORP}" in r.json()["detail"]
    # Неверный пароль по-прежнему 401: отказ «по домену» не выдаёт, что аккаунт есть.
    assert (await _login(client, "user@test.com", "Wrong123")).status_code == 401
    # Открытая до включения сессия не продлевается.
    r = await client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401
    # Владелец с корпоративной почтой и суперадмин входят.
    assert (await _login(client, f"owner@{CORP}", "Admin123")).status_code == 200
    assert (await _login(client, "superadmin@test.com", "Superadmin123")).status_code == 200

    # Новых людей с другой почтой не завести.
    r = await client.post("/api/organizations/current/members",
                          json={"email": "new@gmail.com", "name": "Новый", "password": "Password123"},
                          headers=_h(admin_token))
    assert r.status_code == 400
    r = await client.post("/api/organizations/current/members",
                          json={"email": f"New@{CORP}", "name": "Новый", "password": "Password123"},
                          headers=_h(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["user_email"] == f"new@{CORP}"

    # Смена почты — только на корпоративную; после неё человек снова входит.
    r = await client.patch(f"/api/users/{regular_user.id}", json={"email": "maria@gmail.com"}, headers=_h(superadmin_token))
    assert r.status_code == 400
    r = await client.patch(f"/api/users/{regular_user.id}", json={"email": f"maria.gol@{CORP}"}, headers=_h(superadmin_token))
    assert r.status_code == 200, r.text
    assert (await _login(client, f"maria.gol@{CORP}", "User123")).status_code == 200

    # Общая правка настроек организации домены не трогает.
    r = await client.put("/api/organizations/current", json={"settings": {"allowed_email_domains": []}},
                         headers=_h(admin_token))
    assert r.status_code == 200
    r = await client.get("/api/organizations/current/email-domain", headers=_h(admin_token))
    assert r.json()["domains"] == [CORP]

    # Снять ограничение — пустое поле.
    r = await client.put("/api/organizations/current/email-domain", json={"domains": ""}, headers=_h(admin_token))
    assert r.status_code == 200
    assert (await _login(client, "user2@test.com", "User123")).status_code == 200


@pytest.mark.asyncio
async def test_member_cannot_change_domain(client, second_user_token, org_owner, org_member):
    r = await client.put("/api/organizations/current/email-domain", json={"domains": CORP},
                         headers=_h(second_user_token))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_org_admin_changes_member_email(
    client, db_session, admin_token, user_token, admin_user, regular_user, second_user,
    org_owner, org_admin, org_member,
):
    # Админ (не владелец) меняет почту участнику — и себе.
    r = await client.patch(f"/api/organizations/current/members/{second_user.id}/email",
                           json={"email": f"Vlada.Ver@{CORP}"}, headers=_h(user_token))
    assert r.status_code == 200, r.text
    assert r.json()["email"] == f"vlada.ver@{CORP}"
    r = await client.patch(f"/api/organizations/current/members/{regular_user.id}/email",
                           json={"email": f"maria.gol@{CORP}"}, headers=_h(user_token))
    assert r.status_code == 200, r.text
    # Почту владельца админ не меняет.
    r = await client.patch(f"/api/organizations/current/members/{admin_user.id}/email",
                           json={"email": f"x@{CORP}"}, headers=_h(user_token))
    assert r.status_code == 403
    # Занятая — 409.
    r = await client.patch(f"/api/organizations/current/members/{admin_user.id}/email",
                           json={"email": f"maria.gol@{CORP}"}, headers=_h(admin_token))
    assert r.status_code == 409
    # Пароль прежний — входит по новой почте.
    assert (await _login(client, f"vlada.ver@{CORP}", "User123")).status_code == 200
