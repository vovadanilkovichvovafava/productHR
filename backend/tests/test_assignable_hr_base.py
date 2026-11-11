"""«Назначенные рекрутеры» — только HR базы (Мария, 11.11.2026).

Список `GET /vacancies/assignable-users` (форма заявки, «Назначить», «Забрать»,
выбор владельца вакансий) не показывает тех, кто не может войти из-за
ограничения по почте, и служебные адреса из «Исключений» домена (тестовый
аккаунт). Без ограничения по почте список прежний.
"""
from api.models.database import OrgMember, OrgRole, User
from api.services.auth import create_access_token, hash_password


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _hr(db, org, email, name, role=OrgRole.hr):
    u = User(email=email, password_hash=hash_password("x"), name=name, is_active=True)
    db.add(u)
    await db.flush()
    db.add(OrgMember(org_id=org.id, user_id=u.id, role=role))
    await db.commit()
    await db.refresh(u)
    return u


async def _names(client, user):
    r = await client.get("/api/vacancies/assignable-users", headers=_h(user))
    assert r.status_code == 200, r.text
    return {u["name"] for u in r.json()}


async def test_only_people_who_can_log_in_and_are_not_service_accounts(
    client, db_session, organization, admin_user, org_owner,
):
    maria = await _hr(db_session, organization, "maria@agency-mst.com", "Мария", OrgRole.admin)
    await _hr(db_session, organization, "elvira@agency-mst.com", "Эльвира")
    await _hr(db_session, organization, "valentina@gmail.com", "Валентина")
    await _hr(db_session, organization, "test.recruiter@gmail.com", "Рекрутер тест")

    assert await _names(client, maria) >= {"Мария", "Эльвира", "Валентина", "Рекрутер тест"}

    organization.settings = {
        **(organization.settings or {}),
        "allowed_email_domains": ["agency-mst.com"],
        "allowed_email_exceptions": ["test.recruiter@gmail.com"],
    }
    await db_session.commit()
    assert await _names(client, maria) == {"Мария", "Эльвира"}
