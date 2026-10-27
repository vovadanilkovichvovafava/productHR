"""Кому приходит «Ответ на анкету» (владелец, 24.10.2026).

Отправителю ссылки И текущему рекрутёру кандидата — но если это один и тот же
человек, уведомление ОДНО. Раньше — только отправителю: кандидата забрал
другой рекрутёр, а об ответе узнавал прежний.
"""
from datetime import datetime

import pytest
from sqlalchemy import select

from api.models.database import (
    ApplicationStage, Entity, EntityStatus, EntityType, FormDispatch, FormTemplate,
    Notification, OrgMember, OrgRole, User, Vacancy, VacancyApplication, VacancyStatus,
)

FIELDS = [{"id": "f1", "type": "text", "label": "Опыт", "required": False}]


@pytest.fixture
async def recruiter(db_session, organization):
    u = User(email="hr.forms@test.local", name="Пётр Рекрутёр", password_hash="x", is_active=True)
    db_session.add(u)
    await db_session.commit()
    db_session.add(OrgMember(org_id=organization.id, user_id=u.id, role=OrgRole.hr))
    await db_session.commit()
    return u


async def _setup(db, org, department, sender, *, app_author=None, card_owner=None, token):
    now = datetime.utcnow()
    form = FormTemplate(org_id=org.id, created_by=sender.id, title="Вводная", slug=f"s-{token}", fields=FIELDS)
    e = Entity(org_id=org.id, type=EntityType.candidate, name="Анна Иванова",
               status=EntityStatus.new, created_by=card_owner.id if card_owner else None)
    db.add_all([form, e])
    await db.commit()
    if app_author is not None:
        v = Vacancy(org_id=org.id, department_id=department.id, created_by=sender.id, title="Трафик",
                    status=VacancyStatus.open, salary_currency="RUB", created_at=now, updated_at=now)
        db.add(v)
        await db.commit()
        db.add(VacancyApplication(vacancy_id=v.id, entity_id=e.id, stage=ApplicationStage.screening,
                                  stage_order=1, created_by=app_author.id, applied_at=now,
                                  last_stage_change_at=now, updated_at=now))
    db.add(FormDispatch(form_id=form.id, entity_id=e.id, token=token, created_by=sender.id))
    await db.commit()


async def _notified(db, user):
    rows = await db.execute(select(Notification).where(
        Notification.user_id == user.id, Notification.type == "form_submitted"))
    return len(rows.scalars().all())


async def test_sender_and_current_recruiter_both_notified(
    client, db_session, organization, department, admin_user, org_owner, recruiter,
):
    # Анкету отправила Мария (admin_user), кандидат сейчас у Петра в воронке.
    await _setup(db_session, organization, department, admin_user, app_author=recruiter, token="t-both")
    r = await client.post("/api/forms/public/d/t-both/submit", json={"data": {"f1": "3 года"}})
    assert r.status_code == 200, r.text
    assert await _notified(db_session, admin_user) == 1
    assert await _notified(db_session, recruiter) == 1


async def test_same_person_gets_one_notification(
    client, db_session, organization, department, admin_user, org_owner, recruiter,
):
    # Отправил и ведёт кандидата один и тот же человек — одно уведомление, не два.
    await _setup(db_session, organization, department, recruiter, app_author=recruiter, token="t-same")
    r = await client.post("/api/forms/public/d/t-same/submit", json={"data": {"f1": "3 года"}})
    assert r.status_code == 200, r.text
    assert await _notified(db_session, recruiter) == 1
    assert await _notified(db_session, admin_user) == 0


async def test_out_of_funnel_candidate_owner_notified(
    client, db_session, organization, department, admin_user, org_owner, recruiter,
):
    # Кандидат вне воронок: «его рекрутёр» — тот, за кем карточка.
    await _setup(db_session, organization, department, admin_user, card_owner=recruiter, token="t-card")
    r = await client.post("/api/forms/public/d/t-card/submit", json={"data": {}})
    assert r.status_code == 200, r.text
    assert await _notified(db_session, admin_user) == 1
    assert await _notified(db_session, recruiter) == 1


async def test_realtime_once_per_person(
    client, db_session, organization, department, admin_user, org_owner, recruiter, monkeypatch,
):
    from api.routes import realtime as rt
    sent = []

    async def fake_to_user(user_id, event_type, payload):
        if event_type == "form.submission":
            sent.append(user_id)

    monkeypatch.setattr(rt.manager, "broadcast_to_user", fake_to_user)
    await _setup(db_session, organization, department, recruiter, app_author=recruiter, token="t-rt1")
    await client.post("/api/forms/public/d/t-rt1/submit", json={"data": {}})
    assert sent == [recruiter.id]
