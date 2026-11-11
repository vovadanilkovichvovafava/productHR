"""«Объединить» пересчитывает статус выжившей карточки (11.11.2026).

Мария: «на статусе „Новые“ висят отказники». Новую карточку («Новые», без
воронок) объединяли со старой, где был «Отказ» в «Трафике»: заявка
переезжала, статус оставался «Новые». Теперь — пересчёт по заявкам, но только
у карточки в «Новых»: статус, поставленный HR без воронки, старый отказ не
перебивает. И разовый шаг для уже испорченных карточек.
"""
from datetime import datetime

from api.models.database import (
    ApplicationStage, DataMigrationMark, Entity, EntityStatus, EntityType, Vacancy,
    VacancyApplication, VacancyStatus,
)
from api.services.auth import create_access_token
from api.services.merged_status_sync import SYNC_MARK, resettle_merged_new_once


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _pair(db, org, user, target_status):
    now = datetime.utcnow()
    v = Vacancy(org_id=org.id, title="Трафик", status=VacancyStatus.open, created_by=user.id,
                salary_currency="RUB", created_at=now, updated_at=now)
    old = Entity(org_id=org.id, type=EntityType.candidate, name="Никонов Семён", status=EntityStatus.rejected,
                 created_by=user.id, created_at=now, email="old@x.com")
    new = Entity(org_id=org.id, type=EntityType.candidate, name="Никонов Семён", status=target_status,
                 created_by=user.id, created_at=now, email="new@x.com")
    db.add_all([v, old, new])
    await db.flush()
    db.add(VacancyApplication(vacancy_id=v.id, entity_id=old.id, stage=ApplicationStage.rejected,
                              stage_order=1, created_by=user.id, applied_at=now, last_stage_change_at=now))
    await db.commit()
    return old.id, new.id


async def _merge(client, user, target_id, source_id):
    r = await client.post(f"/api/entities/{target_id}/merge-shadow",
                          json={"duplicate_id": source_id}, headers=_h(user))
    assert r.status_code == 200, r.text


async def test_new_card_merged_with_rejected_becomes_rejected(
    client, db_session, organization, admin_user, org_owner,
):
    old_id, new_id = await _pair(db_session, organization, admin_user, EntityStatus.new)
    await _merge(client, admin_user, new_id, old_id)
    db_session.expire_all()
    assert (await db_session.get(Entity, new_id)).status == EntityStatus.rejected


async def test_status_set_by_hr_without_funnel_is_kept(
    client, db_session, organization, admin_user, org_owner,
):
    old_id, new_id = await _pair(db_session, organization, admin_user, EntityStatus.probation)
    await _merge(client, admin_user, new_id, old_id)
    db_session.expire_all()
    assert (await db_session.get(Entity, new_id)).status == EntityStatus.probation


async def test_one_time_sync_fixes_already_merged_cards(db_session, organization, admin_user):
    now = datetime.utcnow()
    v = Vacancy(org_id=organization.id, title="Трафик", status=VacancyStatus.open, created_by=admin_user.id,
                salary_currency="RUB", created_at=now, updated_at=now)
    merged = Entity(org_id=organization.id, type=EntityType.candidate, name="Тихомиров", status=EntityStatus.new,
                    created_by=admin_user.id, created_at=now, extra_data={"merged_from": [{"id": 1}]})
    plain = Entity(org_id=organization.id, type=EntityType.candidate, name="Просто новый", status=EntityStatus.new,
                   created_by=admin_user.id, created_at=now)
    db_session.add_all([v, merged, plain])
    await db_session.flush()
    for e in (merged, plain):
        db_session.add(VacancyApplication(vacancy_id=v.id, entity_id=e.id, stage=ApplicationStage.rejected,
                                          stage_order=1, created_by=admin_user.id, applied_at=now,
                                          last_stage_change_at=now))
    await db_session.commit()
    mid, pid = merged.id, plain.id
    assert await resettle_merged_new_once(db_session) == [mid]
    db_session.expire_all()
    assert (await db_session.get(Entity, mid)).status == EntityStatus.rejected
    assert (await db_session.get(Entity, pid)).status == EntityStatus.new  # не объединённую не трогаем
    assert await db_session.get(DataMigrationMark, SYNC_MARK) is not None
    assert await resettle_merged_new_once(db_session) == []
