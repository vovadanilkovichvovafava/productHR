"""Сторож: подписанный документ читает сам сотрудник или админ ЕГО организации.

`GET /documents/{id}` проверял «админ своей организации», а не организацию
документа: админ любого клиента перебором id читал чужие договоры с паспортом,
ИНН, СНИЛС и адресом (до 27.10.2026).
"""
from api.models.database import Employee, OrgMember, OrgRole, SignedDocument
from api.services.auth import create_access_token


def _h(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


async def _doc(db, org, user):
    emp = Employee(user_id=user.id, org_id=org.id, is_active=True)
    db.add(emp)
    await db.flush()
    doc = SignedDocument(employee_id=emp.id, title="Договор", content_rendered="Паспорт 1234 567890", status="pending")
    db.add(doc)
    await db.commit()
    return doc


async def test_admin_of_other_org_gets_404(
    client, db_session, organization, second_organization, org_owner, admin_user, second_user,
):
    db_session.add(OrgMember(org_id=second_organization.id, user_id=second_user.id, role=OrgRole.member))
    await db_session.commit()
    doc = await _doc(db_session, second_organization, second_user)

    resp = await client.get(f"/api/documents/{doc.id}", headers=_h(admin_user))

    assert resp.status_code == 404
    assert "1234" not in resp.text


async def test_own_and_own_org_admin_can_read(
    client, db_session, organization, org_owner, org_member, admin_user, second_user,
):
    doc = await _doc(db_session, organization, second_user)

    own = await client.get(f"/api/documents/{doc.id}", headers=_h(second_user))
    admin = await client.get(f"/api/documents/{doc.id}", headers=_h(admin_user))

    assert own.status_code == 200
    assert admin.status_code == 200


async def test_colleague_gets_404(
    client, db_session, organization, org_admin, org_member, regular_user, second_user,
):
    # Рядовой сотрудник не читает документ коллеги.
    doc = await _doc(db_session, organization, regular_user)

    resp = await client.get(f"/api/documents/{doc.id}", headers=_h(second_user))

    assert resp.status_code == 404
