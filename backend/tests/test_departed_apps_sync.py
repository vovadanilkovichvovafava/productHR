"""Разовое закрытие заявок у уволенных до 20.10.2026 (Лушников, 11.11.2026)."""
from datetime import datetime

from sqlalchemy import select

from api.models.database import (
    ApplicationStage, Entity, EntityStatus, EntityType, StageTransition, Vacancy,
    VacancyApplication, VacancyStatus,
)
from api.services.departed_apps_sync import close_departed_applications_once


async def _setup(db, org, user):
    now = datetime.utcnow()
    v = Vacancy(org_id=org.id, title="Трафик", status=VacancyStatus.open, created_by=user.id,
                salary_currency="RUB", created_at=now, updated_at=now)
    db.add(v)
    await db.flush()
    gone = Entity(org_id=org.id, type=EntityType.candidate, name="Лушников", status=EntityStatus.dismissed,
                  created_by=user.id, created_at=now)
    works = Entity(org_id=org.id, type=EntityType.candidate, name="Работает", status=EntityStatus.transferred,
                   created_by=user.id, created_at=now)
    db.add_all([gone, works])
    await db.flush()
    a_gone = VacancyApplication(vacancy_id=v.id, entity_id=gone.id, stage=ApplicationStage.transferred,
                                stage_order=1, created_by=user.id, applied_at=now, last_stage_change_at=now)
    a_works = VacancyApplication(vacancy_id=v.id, entity_id=works.id, stage=ApplicationStage.transferred,
                                 stage_order=2, created_by=user.id, applied_at=now, last_stage_change_at=now)
    db.add_all([a_gone, a_works])
    await db.commit()
    return gone.id, a_gone.id, a_works.id


async def test_closes_live_applications_of_departed_once(db_session, organization, admin_user):
    gone_id, a_gone, a_works = await _setup(db_session, organization, admin_user)
    assert await close_departed_applications_once(db_session) == [gone_id]
    db_session.expire_all()
    assert (await db_session.get(VacancyApplication, a_gone)).stage == ApplicationStage.rejected
    assert (await db_session.get(VacancyApplication, a_works)).stage == ApplicationStage.transferred
    gone = await db_session.get(Entity, gone_id)
    assert gone.status == EntityStatus.dismissed
    assert "rejection_reason" not in (gone.extra_data or {})  # сверка — не причина отказа
    assert (await db_session.get(VacancyApplication, a_gone)).rejection_reason is None
    hist = (await db_session.execute(
        select(StageTransition).where(StageTransition.application_id == a_gone)
    )).scalars().all()
    assert [h.to_stage for h in hist] == [ApplicationStage.rejected]
    assert "сверке" in (hist[0].comment or "")
    # второй запуск — ничего
    assert await close_departed_applications_once(db_session) == []
