"""End-to-end flow test for personal questionnaire dispatch (MVP-1).

Drives the real ASGI app through the whole feature in one sequence:
HR creates a form -> dispatches it to an EXISTING candidate -> candidate opens
the personal link and submits WITHOUT auth -> answers attach to the same
candidate (no new entity) -> badge shows 1 unread -> mark-seen clears it.
"""
import pytest
from sqlalchemy import select

from api.models.database import (
    FormTemplate, FormDispatch, FormSubmission, Entity, EntityType, EntityStatus, Organization,
)
from api.services.auth import create_access_token


def _h(user):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(user.id)})}"}


@pytest.mark.asyncio
async def test_full_dispatch_flow_e2e(client, db_session, organization: Organization, admin_user, org_owner):
    # An EXISTING candidate already in the recruiter's org
    cand = Entity(org_id=organization.id, type=EntityType.candidate, name="Пётр Кандидатов", status=EntityStatus.new)
    db_session.add(cand)
    await db_session.commit()
    cand_id = cand.id
    H = _h(admin_user)

    # 1. HR creates an anketa (with a scale field)
    r = await client.post("/api/forms", json={
        "title": "Скрининг",
        "fields": [
            {"id": "name", "type": "text", "label": "ФИО", "required": True},
            {"id": "exp", "type": "scale", "label": "Опыт", "required": False, "min": 1, "max": 10},
        ],
    }, headers=H)
    assert r.status_code == 200, r.text
    form_id = r.json()["id"]

    # 2. HR dispatches it to the existing candidate -> personal token
    r = await client.post(f"/api/forms/{form_id}/dispatch", json={"entity_id": cand_id}, headers=H)
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    assert r.json()["url"] == f"/form/{token}"  # короткая ссылка (c782bb7e)

    # 3. Candidate opens the personal link (NO auth) -> sees their name, status -> opened
    r = await client.get(f"/api/forms/public/d/{token}")
    assert r.status_code == 200, r.text
    assert r.json()["candidate_name"] == "Пётр Кандидатов"

    # 4. Candidate submits (NO auth) -> must NOT create a new candidate
    before = len((await db_session.execute(select(Entity))).scalars().all())
    r = await client.post(f"/api/forms/public/d/{token}/submit",
                          json={"data": {"name": "Пётр Кандидатов", "exp": 8}})
    assert r.status_code == 200, r.text
    after = len((await db_session.execute(select(Entity))).scalars().all())
    assert after == before, "новый кандидат не должен создаваться — ответ к существующему"

    # 5. Badge shows 1 unread answer for this candidate
    r = await client.get(f"/api/forms/entity/{cand_id}/unread-count", headers=H)
    assert r.status_code == 200 and r.json()["count"] == 1

    # 6. Answers are attached to the SAME candidate and readable in the card
    r = await client.get(f"/api/forms/entity/{cand_id}/all-dispatches", headers=H)
    body = r.json()
    assert len(body) == 1
    assert body[0]["status"] == "submitted"
    assert body[0]["answers"]["exp"] == 8
    sub = (await db_session.execute(select(FormSubmission))).scalar_one()
    assert sub.entity_id == cand_id

    # 7. Opening responses (mark-seen) clears the badge
    r = await client.patch(f"/api/forms/entity/{cand_id}/dispatches/seen", headers=H)
    assert r.status_code == 200
    r = await client.get(f"/api/forms/entity/{cand_id}/unread-count", headers=H)
    assert r.json()["count"] == 0

    # 8. Re-submitting the same personal link is rejected (one dispatch = one answer)
    r = await client.post(f"/api/forms/public/d/{token}/submit", json={"data": {"name": "x"}})
    assert r.status_code == 409
