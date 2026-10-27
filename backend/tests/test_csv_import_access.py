"""Импорт CSV — только админам HR (23.10.2026).

Страница `/import` была закрыта для всех, кроме админов, а сервер проверял
один вход: любой участник организации, даже сотрудник без HR, мог прямым
запросом залить в базу кандидатов из файла.
"""
from api.models.database import OrgMember, OrgRole, User
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


CSV = "Имя,Email\nТест Импортов,import@example.com\n".encode("utf-8")


def _file():
    return {"file": ("cands.csv", CSV, "text/csv")}


async def test_import_closed_to_member_and_recruiter(client, db_session, organization, org_member, second_user):
    recruiter = User(email="hr.import@test.local", name="Рекрутёр Импорта", password_hash="x", is_active=True)
    db_session.add(recruiter)
    await db_session.commit()
    db_session.add(OrgMember(org_id=organization.id, user_id=recruiter.id, role=OrgRole.hr))
    await db_session.commit()

    for user in (second_user, recruiter):
        r = await client.post("/api/import/preview", files=_file(), headers=_h(user))
        assert r.status_code == 403, r.text
        r = await client.post(
            "/api/import/execute", files=_file(),
            data={"column_mapping": '{"Имя": "name", "Email": "email"}'}, headers=_h(user),
        )
        assert r.status_code == 403, r.text
        r = await client.post("/api/import/execute-bulk", files=[("files", ("a.csv", CSV, "text/csv"))], headers=_h(user))
        assert r.status_code == 403, r.text


async def test_import_open_to_owner(client, organization, org_owner, admin_user):
    r = await client.post("/api/import/preview", files=_file(), headers=_h(admin_user))
    assert r.status_code == 200, r.text
    assert r.json()["row_count"] == 1
