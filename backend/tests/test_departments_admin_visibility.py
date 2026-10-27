"""Регресс: орг-админ (OrgRole.admin) должен видеть ВСЕ отделы через
GET /api/departments. Раньше админ без своего отдела получал [] — из-за чего
пустел селект отдела в «Взять в штат» у HR-админов.
"""
import pytest
from httpx import AsyncClient

from api.models.database import Department
from api.services.auth import create_access_token


def _headers(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(user.id)})}"}


@pytest.mark.asyncio
async def test_org_admin_sees_all_departments(
    client: AsyncClient, db_session, organization, regular_user, org_admin
):
    # org_admin fixture делает regular_user'а OrgRole.admin в organization,
    # членства в отделе у него НЕТ (как у maria@/nastya@ в проде).
    db_session.add(Department(org_id=organization.id, name="Тестовый отдел", is_active=True))
    await db_session.commit()

    resp = await client.get("/api/departments", headers=_headers(regular_user))
    assert resp.status_code == 200, resp.text
    names = [d["name"] for d in resp.json()]
    assert "Тестовый отдел" in names, f"админ не видит отдел: {names}"
