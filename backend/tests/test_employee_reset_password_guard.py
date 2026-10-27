"""Сторож: кому админ может выдать новый пароль в «Сотрудниках».

`POST /employees/{id}/reset-password` проверял только «я админ организации
сотрудника». Пароль же — от всего аккаунта, а запись Employee автосинк заводит
каждому участнику, в том числе владельцу и суперадмину. До 27.10.2026 админ
сбрасывал им пароль и получал их аккаунты; старые сессии жертвы при этом
продолжали работать.
"""
from sqlalchemy import select

from api.models.database import Employee, OrgMember, OrgRole, RefreshToken, User
from api.services.auth import create_access_token, verify_password


def _h(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


async def _employee(db, org, user):
    emp = Employee(user_id=user.id, org_id=org.id, is_active=True)
    db.add(emp)
    await db.commit()
    return emp


async def _reset(client, actor, emp):
    return await client.post(f"/api/employees/{emp.id}/reset-password", headers=_h(actor))


async def test_admin_cannot_reset_owner(
    client, db_session, organization, org_owner, org_admin, admin_user, regular_user,
):
    # regular_user — admin, admin_user — owner.
    emp = await _employee(db_session, organization, admin_user)

    resp = await _reset(client, regular_user, emp)

    assert resp.status_code == 403
    await db_session.refresh(admin_user)
    assert verify_password("Admin123", admin_user.password_hash)


async def test_admin_cannot_reset_superadmin(
    client, db_session, organization, org_admin, superadmin_org_member, regular_user, superadmin_user,
):
    emp = await _employee(db_session, organization, superadmin_user)

    resp = await _reset(client, regular_user, emp)

    assert resp.status_code == 403
    await db_session.refresh(superadmin_user)
    assert verify_password("Superadmin123", superadmin_user.password_hash)


async def test_admin_cannot_reset_peer_admin(
    client, db_session, organization, org_admin, regular_user, second_user,
):
    db_session.add(OrgMember(org_id=organization.id, user_id=second_user.id, role=OrgRole.admin))
    await db_session.commit()
    emp = await _employee(db_session, organization, second_user)

    resp = await _reset(client, regular_user, emp)

    assert resp.status_code == 403


async def test_cannot_reset_member_of_another_org(
    client, db_session, organization, second_organization, org_owner, org_member, admin_user, second_user,
):
    # second_user — рядовой сотрудник здесь, но состоит и во второй организации.
    db_session.add(OrgMember(org_id=second_organization.id, user_id=second_user.id, role=OrgRole.owner))
    await db_session.commit()
    emp = await _employee(db_session, organization, second_user)

    resp = await _reset(client, admin_user, emp)

    assert resp.status_code == 403


async def test_owner_resets_member_and_old_sessions_die(
    client, db_session, organization, org_owner, org_member, admin_user, second_user,
):
    from datetime import datetime, timedelta
    db_session.add(RefreshToken(
        user_id=second_user.id, token_hash="h" * 64,
        expires_at=datetime.utcnow() + timedelta(days=7),
    ))
    await db_session.commit()
    old_version = second_user.token_version or 0
    emp = await _employee(db_session, organization, second_user)

    resp = await _reset(client, admin_user, emp)

    assert resp.status_code == 200
    temp = resp.json()["temporary_password"]
    user = (await db_session.execute(
        select(User).where(User.id == second_user.id).execution_options(populate_existing=True)
    )).scalar_one()
    assert verify_password(temp, user.password_hash)
    assert user.must_change_password is True
    assert user.token_version == old_version + 1
    tokens = (await db_session.execute(
        select(RefreshToken).where(RefreshToken.user_id == second_user.id)
        .execution_options(populate_existing=True)
    )).scalars().all()
    assert tokens and all(t.revoked_at is not None for t in tokens)
