"""Архивный кандидат (Entity.is_archived=True) должен ВЫХОДИТЬ из архива,
когда его реально начинают вести: смена статуса/этапа воронки или взятие
на вакансию. Кандидат в активной работе не должен висеть в теневом архиве
дедупа (см. models/database.py Entity.is_archived, default=True)."""
import pytest
from sqlalchemy import select

from api.models.database import (
    Entity, EntityType, EntityStatus, Vacancy, VacancyStatus, VacancyApplication,
    ApplicationStage,
)
from api.services.auth import create_access_token


def _h(user):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(user.id)})}"}




@pytest.mark.asyncio
async def test_update_application_stage_change_unarchives_entity(client, db_session, organization, admin_user, org_owner):
    """PUT /vacancies/applications/{id} со сменой stage выводит архивного кандидата из архива."""
    ent = Entity(
        org_id=organization.id, type=EntityType.candidate, name="Архив Стейдж",
        status=EntityStatus.new, is_archived=True,
    )
    vac = Vacancy(org_id=organization.id, title="Воронка Стейдж", status=VacancyStatus.open, created_by=admin_user.id)
    db_session.add_all([ent, vac])
    await db_session.commit()
    await db_session.refresh(ent)
    await db_session.refresh(vac)

    app = VacancyApplication(
        vacancy_id=vac.id, entity_id=ent.id, stage=ApplicationStage.applied,
        stage_order=1, created_by=admin_user.id,
    )
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)
    H = _h(admin_user)

    r = await client.put(
        f"/api/vacancies/applications/{app.id}",
        json={"stage": "screening"},
        headers=H,
    )
    assert r.status_code == 200, r.text

    await db_session.refresh(ent)
    assert ent.is_archived is False


