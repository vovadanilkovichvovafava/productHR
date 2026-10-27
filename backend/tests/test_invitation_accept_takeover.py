"""Сторож: принять приглашение на СУЩЕСТВУЮЩИЙ аккаунт можно только с его паролем.

До 27.10.2026 `POST /invitations/accept/{token}` для уже зарегистрированного
email просто брал этого пользователя: пароль не проверялся, email приглашения с
email формы не сверялся. Ответ при этом нёс токен входа и ссылку привязки
Telegram ЖЕРТВЫ — любой обладатель ссылки приглашения забирал чужой аккаунт.
"""
from sqlalchemy import select

from jose import jwt

from api.config import settings
from api.models.database import Invitation, OrgMember, OrgRole


async def _invite(db, org, inviter, token, email=None):
    inv = Invitation(
        token=token, org_id=org.id, email=email,
        org_role=OrgRole.member, invited_by_id=inviter.id,
    )
    db.add(inv)
    await db.commit()
    return inv


async def test_existing_user_wrong_password_rejected(
    client, db_session, admin_user, second_organization, regular_user,
):
    # Приглашение без адреса: атакующий подставляет email жертвы.
    inv = await _invite(db_session, second_organization, admin_user, "open_inv")

    resp = await client.post(
        "/api/invitations/accept/open_inv",
        json={"email": regular_user.email, "name": "x", "password": "not-her-password"},
    )

    assert resp.status_code == 401
    assert "access_token" not in resp.json()
    # Жертва не добавлена в организацию, приглашение не сгорело, bind-токен не выдан.
    member = (await db_session.execute(
        select(OrgMember).where(
            OrgMember.user_id == regular_user.id,
            OrgMember.org_id == second_organization.id,
        )
    )).scalar_one_or_none()
    assert member is None
    await db_session.refresh(inv)
    assert inv.used_at is None
    await db_session.refresh(regular_user)
    assert regular_user.telegram_bind_token is None


async def test_invitation_for_other_email_rejected(
    client, db_session, admin_user, second_organization, regular_user,
):
    await _invite(db_session, second_organization, admin_user, "addr_inv", email="newbie@test.com")

    # Даже зная пароль жертвы, чужое приглашение на её адрес не принять.
    resp = await client.post(
        "/api/invitations/accept/addr_inv",
        json={"email": regular_user.email, "name": "x", "password": "User123"},
    )

    assert resp.status_code == 400


async def test_existing_user_with_own_password_accepts(
    client, db_session, admin_user, second_organization, regular_user,
):
    await _invite(
        db_session, second_organization, admin_user, "own_inv",
        email=regular_user.email.upper(),  # регистр адреса не важен
    )

    resp = await client.post(
        "/api/invitations/accept/own_inv",
        json={"email": regular_user.email, "name": "x", "password": "User123"},
    )

    assert resp.status_code == 200
    assert resp.json()["user_id"] == regular_user.id


async def test_accept_token_carries_token_version(
    client, db_session, admin_user, second_organization, regular_user,
):
    regular_user.token_version = 3
    await db_session.commit()
    await _invite(db_session, second_organization, admin_user, "ver_inv", email=regular_user.email)

    resp = await client.post(
        "/api/invitations/accept/ver_inv",
        json={"email": regular_user.email, "name": "x", "password": "User123"},
    )

    assert resp.status_code == 200
    # Без token_version токен считался бы версией 0 и не отзывался сменой пароля.
    payload = jwt.decode(
        resp.json()["access_token"], settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    assert payload["token_version"] == 3
