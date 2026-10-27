"""Сторож: увольнение не отключает аккаунт тому, кого увольнять нельзя.

Увольнение (DELETE /employees/{id} и статус «Уволен» на доске «Штат» — обе
двери идут через services/offboarding.run_offboarding) гасило ЛЮБОЙ аккаунт
целиком: админ отключал владельца, суперадмина или самого себя, а человек,
работающий ещё в одной организации, терял вход и там (до 27.10.2026).
"""
from sqlalchemy import select

from api.models.database import Employee, OrgMember, OrgRole, User
from api.services.auth import create_access_token
from api.services.offboarding import run_offboarding


def _h(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


async def _employee(db, org, user):
    emp = Employee(user_id=user.id, org_id=org.id, is_active=True)
    db.add(emp)
    await db.commit()
    return emp


async def _fresh_user(db, user_id):
    return (await db.execute(
        select(User).where(User.id == user_id).execution_options(populate_existing=True)
    )).scalar_one()


async def test_admin_cannot_dismiss_owner(
    client, db_session, organization, org_owner, org_admin, admin_user, regular_user,
):
    emp = await _employee(db_session, organization, admin_user)  # admin_user — owner

    resp = await client.delete(f"/api/employees/{emp.id}", headers=_h(regular_user))

    assert resp.status_code == 403
    assert (await _fresh_user(db_session, admin_user.id)).is_active is True
    await db_session.refresh(emp)
    assert emp.is_active is True


async def test_cannot_dismiss_self(client, db_session, organization, org_owner, admin_user):
    emp = await _employee(db_session, organization, admin_user)

    resp = await client.delete(f"/api/employees/{emp.id}", headers=_h(admin_user))

    assert resp.status_code == 400


async def test_owner_dismisses_member_and_cuts_account(
    client, db_session, organization, org_owner, org_member, admin_user, second_user,
):
    emp = await _employee(db_session, organization, second_user)

    resp = await client.delete(f"/api/employees/{emp.id}", headers=_h(admin_user))

    assert resp.status_code == 200, resp.text
    assert resp.json()["offboarding"]["cut_off_scope"] == "account"
    assert (await _fresh_user(db_session, second_user.id)).is_active is False


async def test_multi_org_member_keeps_account(
    client, db_session, organization, second_organization, org_owner, org_member, admin_user, second_user,
):
    db_session.add(OrgMember(org_id=second_organization.id, user_id=second_user.id, role=OrgRole.member))
    await db_session.commit()
    emp = await _employee(db_session, organization, second_user)

    resp = await client.delete(f"/api/employees/{emp.id}", headers=_h(admin_user))

    assert resp.status_code == 200, resp.text
    assert resp.json()["offboarding"]["cut_off_scope"] == "org_only"
    assert (await _fresh_user(db_session, second_user.id)).is_active is True
    orgs = set((await db_session.execute(
        select(OrgMember.org_id).where(OrgMember.user_id == second_user.id)
    )).scalars().all())
    assert orgs == {second_organization.id}


async def test_board_door_does_not_cut_superadmin_or_higher_role(
    db_session, organization, org_owner, org_admin, superadmin_org_member, admin_user, regular_user, superadmin_user,
):
    # Доска зовёт run_offboarding с тем, кто нажал. Админ (regular_user)
    # «увольняет» владельца и суперадмина — аккаунты остаются живыми.
    for victim in (admin_user, superadmin_user):
        checklist = await run_offboarding(db_session, organization.id, victim.id, regular_user.id, "доска")
        await db_session.commit()
        assert checklist["cut_off_scope"] == "none"
        assert (await _fresh_user(db_session, victim.id)).is_active is True
