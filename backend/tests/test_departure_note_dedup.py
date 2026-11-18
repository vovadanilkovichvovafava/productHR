"""Разовая чистка задвоенных «Мы уволили» (services/departure_note_dedup.py).

До 18.11.2026 увольнение из карточки писало перевод заявки «Отказ — Мы
уволили — причина» и запись-комментарий «Мы уволили — причина». Чистка
убирает только запись, у которой есть такой перевод рядом по времени.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from api.models.database import (
    ApplicationStage, DataMigrationMark, Entity, EntityStatus, EntityType, StageTransition,
    Vacancy, VacancyApplication, VacancyStatus,
)
from api.services.departure_note_dedup import SYNC_MARK, dedup_departure_notes_once


def _note(nid, text, when, stage="dismissed", label="Мы уволили"):
    return {"id": nid, "text": text, "date": when.replace(tzinfo=timezone.utc).isoformat(),
            "stage": stage, "stage_label": label, "from_status": "probation", "author_id": 1}


async def _person(db, org, user, notes):
    e = Entity(org_id=org.id, created_by=user.id, name="Уволенный Тест", type=EntityType.candidate,
               status=EntityStatus.dismissed, created_at=datetime.utcnow(),
               extra_data={"notes": notes, "pinned_entry_key": f"n:{notes[0]['id']}" if notes else None})
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


async def _rejected_transition(db, org, user, entity, comment, when):
    v = Vacancy(org_id=org.id, created_by=user.id, title="Трафик", status=VacancyStatus.open,
                salary_currency="RUB", created_at=when, updated_at=when)
    db.add(v)
    await db.commit()
    await db.refresh(v)
    a = VacancyApplication(vacancy_id=v.id, entity_id=entity.id, stage=ApplicationStage.rejected,
                           stage_order=1, created_by=user.id, applied_at=when,
                           last_stage_change_at=when, updated_at=when)
    db.add(a)
    await db.commit()
    await db.refresh(a)
    db.add(StageTransition(application_id=a.id, entity_id=entity.id, from_stage="probation",
                           to_stage="rejected", changed_by=user.id, comment=comment, created_at=when))
    await db.commit()


@pytest.mark.asyncio
async def test_removes_only_paired_departure_notes(db_session, organization, admin_user):
    now = datetime.utcnow().replace(microsecond=0)
    # Пара от одного действия: запись + перевод через 1 секунду.
    paired = await _person(db_session, organization, admin_user, [
        _note("dup", "темп хромает", now),
        {"id": "plain", "text": "обычный комментарий", "date": now.isoformat()},
    ])
    await _rejected_transition(db_session, organization, admin_user, paired,
                               "Мы уволили — темп хромает", now + timedelta(seconds=1))
    # Та же пара, но время перевода записано базой в поясе Москвы (+3 ч).
    msk = await _person(db_session, organization, admin_user, [_note("msk", "опоздания", now)])
    await _rejected_transition(db_session, organization, admin_user, msk,
                               "Мы уволили — опоздания", now + timedelta(hours=3, seconds=1))
    # Уволен без воронок — запись единственная, её не трогаем.
    alone = await _person(db_session, organization, admin_user, [_note("alone", "прогулы", now, "quit", "Сам уволился")])
    # Перевод с тем же текстом, но через 20 минут — другое действие, не трогаем.
    later = await _person(db_session, organization, admin_user, [_note("later", "x", now)])
    await _rejected_transition(db_session, organization, admin_user, later,
                               "Мы уволили — x", now + timedelta(minutes=20))
    ids = (paired.id, alone.id, later.id, msk.id)

    assert await dedup_departure_notes_once(db_session) == 2

    db_session.expire_all()
    p, a, l, m = [await db_session.get(Entity, i) for i in ids]
    assert m.extra_data["notes"] == []
    assert [n["id"] for n in p.extra_data["notes"]] == ["plain"]
    assert "pinned_entry_key" not in p.extra_data          # закреп на убранной записи снят
    assert [n["id"] for n in a.extra_data["notes"]] == ["alone"]
    assert [n["id"] for n in l.extra_data["notes"]] == ["later"]
    # Переводы остаются: строка в ленте и отмена корзиной — на них.
    assert (await db_session.execute(select(func.count()).select_from(StageTransition))).scalar() == 3
    assert await db_session.get(DataMigrationMark, SYNC_MARK) is not None
    assert await dedup_departure_notes_once(db_session) == 0   # разово
