"""Вход по почте без учёта регистра и смена почты суперадмином (09.11.2026).

Мария попросила перевести вход HR на корпоративные адреса @agency-mst.com.
Почту меняет суперадмин («Пользователи → Редактировать»), пароль остаётся.
Сторожим: адрес хранится в нижнем регистре, вход не зависит от регистра,
занятая почта — понятный 409, а не 500.
"""
import pytest

from api.models.database import User, UserRole
from api.services.auth import hash_password


@pytest.mark.asyncio
async def test_login_ignores_case_and_spaces(client, admin_user):
    r = await client.post("/api/auth/login", json={"email": "  ADMIN@Test.com ", "password": "Admin123"})
    # EmailStr сам срезает пробелы; главное — регистр не мешает
    assert r.status_code == 200, r.text
    assert r.json()["user"]["id"] == admin_user.id


@pytest.mark.asyncio
async def test_superadmin_changes_email_and_user_logs_in_with_it(
    client, db_session, superadmin_token, get_auth_headers, admin_user,
):
    r = await client.patch(
        f"/api/users/{admin_user.id}",
        json={"email": "Maria.Gol@Agency-MST.com"},
        headers=get_auth_headers(superadmin_token),
    )
    assert r.status_code == 200, r.text
    await db_session.refresh(admin_user)
    assert admin_user.email == "maria.gol@agency-mst.com"

    old = await client.post("/api/auth/login", json={"email": "admin@test.com", "password": "Admin123"})
    assert old.status_code == 401
    new = await client.post("/api/auth/login", json={"email": "maria.gol@agency-mst.com", "password": "Admin123"})
    assert new.status_code == 200, new.text
    assert new.json()["user"]["email"] == "maria.gol@agency-mst.com"


@pytest.mark.asyncio
async def test_taken_email_is_409_not_500(
    client, db_session, superadmin_token, get_auth_headers, admin_user,
):
    other = User(
        email="elvira.efi@agency-mst.com", password_hash=hash_password("Other123"),
        name="Другая", role=UserRole.admin, is_active=True,
    )
    db_session.add(other)
    await db_session.commit()

    r = await client.patch(
        f"/api/users/{admin_user.id}",
        json={"email": "Elvira.Efi@agency-mst.com"},
        headers=get_auth_headers(superadmin_token),
    )
    assert r.status_code == 409
    assert "уже у другого" in r.json()["detail"]
    await db_session.refresh(admin_user)
    assert admin_user.email == "admin@test.com"
