"""Слияние вакансии-дубля в главную (решение владельца 21.09.2026).

Две вакансии «User Acquisition Manager» у Эльвиры (своя + переданная от
Валентины). Главная — целевая: кандидаты исходной переезжают как есть, у
пересечений остаётся этап целевой, история и комментарии не теряются.
"""
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from api.models.database import (
    ApplicationCoRecruiter, ApplicationStage, Entity, EntityStatus, EntityType,
    OrgMember, OrgRole, StageTransition, User, UserRole, Vacancy,
    VacancyApplication, VacancyStatus,
)
from api.services.auth import create_access_token, hash_password


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _user(db, org, email, name, role=OrgRole.hr):
    u = User(email=email, password_hash=hash_password("x"), name=name, role=UserRole.admin)
    db.add(u)
    await db.flush()
    db.add(OrgMember(org_id=org.id, user_id=u.id, role=role))
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def s(db_session, organization, admin_user, org_owner):
    elvira = await _user(db_session, organization, "elvira@t.ru", "Эльвира")
    petr = await _user(db_session, organization, "petr@t.ru", "Пётр")
    now = datetime.utcnow()

    def vac(title):
        return Vacancy(
            org_id=organization.id, title=title, status=VacancyStatus.open,
            created_by=elvira.id, assigned_to=[elvira.id],
            extra_data={"accepted_by": [elvira.id]}, created_at=now,
        )

    target, source = vac("User Acquisition Manager"), vac("User Acquisition Manager")
    only_src = Entity(
        org_id=organization.id, name="Только в исходной", type=EntityType.candidate,
        status=EntityStatus.interview, created_by=elvira.id, created_at=now,
    )
    both = Entity(
        org_id=organization.id, name="Morozov", type=EntityType.candidate,
        status=EntityStatus.rejected, created_by=elvira.id, created_at=now,
    )
    db_session.add_all([target, source, only_src, both])
    await db_session.commit()

    a_only = VacancyApplication(
        vacancy_id=source.id, entity_id=only_src.id, stage=ApplicationStage.interview,
        stage_order=-3000, created_by=elvira.id, source="resume_upload",
        applied_at=now - timedelta(days=10), last_stage_change_at=now - timedelta(days=2),
    )
    a_both_tgt = VacancyApplication(
        vacancy_id=target.id, entity_id=both.id, stage=ApplicationStage.applied,
        stage_order=0, created_by=elvira.id, source="taken",
        applied_at=now - timedelta(days=5), last_stage_change_at=now - timedelta(days=5),
    )
    a_both_src = VacancyApplication(
        vacancy_id=source.id, entity_id=both.id, stage=ApplicationStage.rejected,
        stage_order=0, created_by=elvira.id, source="resume_upload",
        notes="заметка из исходной",
        applied_at=now - timedelta(days=15), last_stage_change_at=now - timedelta(days=1),
    )
    db_session.add_all([a_only, a_both_tgt, a_both_src])
    await db_session.commit()

    db_session.add_all([
        StageTransition(application_id=a_only.id, entity_id=only_src.id,
                        from_stage="applied", to_stage="interview", changed_by=elvira.id),
        StageTransition(application_id=a_both_src.id, entity_id=both.id,
                        from_stage="applied", to_stage="rejected", changed_by=elvira.id),
        ApplicationCoRecruiter(application_id=a_both_src.id, user_id=petr.id),
    ])
    both.extra_data = {"notes": [
        {"id": "n1", "text": "коммент в исходной", "vacancy_id": source.id},
        {"id": "n2", "text": "коммент в целевой", "vacancy_id": target.id},
        {"id": "n3", "text": "общий коммент"},
    ]}
    await db_session.commit()
    return {
        "target": target, "source": source, "only": only_src, "both": both,
        "a_only": a_only, "a_both_tgt": a_both_tgt, "a_both_src": a_both_src,
        "elvira": elvira, "petr": petr,
    }


def _url(s, dry):
    return (f"/api/vacancies/{s['target'].id}/merge-from/{s['source'].id}"
            f"?dry_run={'true' if dry else 'false'}")


@pytest.mark.asyncio
async def test_dry_run_reports_and_changes_nothing(client, db_session, admin_user, s):
    r = await client.post(_url(s, True), headers=_h(admin_user))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["moved_count"] == 1
    assert body["overlapping_count"] == 1
    assert body["overlapping_different_stage"] == 1
    assert body["overlapping"][0]["target_stage"] == "applied"
    assert body["overlapping"][0]["source_stage"] == "rejected"
    assert body["transitions_reattached"] == 1
    assert body["notes_repointed"] == 1

    await db_session.refresh(s["a_only"])
    await db_session.refresh(s["source"])
    assert s["a_only"].vacancy_id == s["source"].id
    assert s["source"].status == VacancyStatus.open
    assert await db_session.get(VacancyApplication, s["a_both_src"].id) is not None


@pytest.mark.asyncio
async def test_merge_moves_candidates_as_is(client, db_session, admin_user, s):
    # id заранее: после expire_all объекты фикстуры протухают.
    I = {k: v.id for k, v in s.items()}
    r = await client.post(_url(s, False), headers=_h(admin_user))
    assert r.status_code == 200, r.text
    db_session.expire_all()

    # Только в исходной: переехал, остальное как было.
    a = await db_session.get(VacancyApplication, I["a_only"])
    assert a.vacancy_id == I["target"]
    assert a.stage == ApplicationStage.interview
    assert a.stage_order == -3000
    assert a.created_by == I["elvira"]
    assert a.source == "resume_upload"
    hist = (await db_session.execute(
        select(StageTransition).where(StageTransition.application_id == a.id)
    )).scalars().all()
    assert [h.to_stage for h in hist] == ["interview"]


@pytest.mark.asyncio
async def test_overlap_keeps_target_stage_and_all_history(client, db_session, admin_user, s):
    # id заранее: после expire_all объекты фикстуры протухают.
    I = {k: v.id for k, v in s.items()}
    r = await client.post(_url(s, False), headers=_h(admin_user))
    assert r.status_code == 200, r.text
    db_session.expire_all()

    apps = (await db_session.execute(
        select(VacancyApplication).where(VacancyApplication.entity_id == I["both"])
    )).scalars().all()
    assert len(apps) == 1
    app = apps[0]
    assert app.id == I["a_both_tgt"]
    assert app.vacancy_id == I["target"]
    assert app.stage == ApplicationStage.applied  # целевая главнее
    assert app.source == "taken"
    assert "заметка из исходной" in (app.notes or "")

    # История исходной заявки теперь у целевой.
    hist = (await db_session.execute(
        select(StageTransition).where(StageTransition.entity_id == I["both"])
    )).scalars().all()
    hist = sorted(hist, key=lambda h: h.id)
    assert [(h.application_id, h.to_stage) for h in hist] == [(app.id, "rejected"), (app.id, "applied")]
    # Последняя — отметка слияния на текущем этапе главной: её «отмена» ничего не
    # двигает (иначе последней была бы запись дубля, и корзина у неё вернула бы
    # заявку на этап, где в главной она не была).
    assert hist[-1].from_stage == hist[-1].to_stage == "applied"
    assert "Слияние вакансий" in hist[-1].comment

    # Со-рекрутёр исходной переехал.
    co = (await db_session.execute(
        select(ApplicationCoRecruiter.user_id).where(ApplicationCoRecruiter.application_id == app.id)
    )).scalars().all()
    assert co == [I["petr"]]

    # Комментарии: исходной перепомечен, остальные как были.
    ent = await db_session.get(Entity, I["both"])
    notes = {n["id"]: n for n in ent.extra_data["notes"]}
    assert notes["n1"]["vacancy_id"] == I["target"]
    assert notes["n1"]["text"] == "коммент в исходной"
    assert notes["n2"]["vacancy_id"] == I["target"]
    assert "vacancy_id" not in notes["n3"]

    # Общий статус — по оставшейся заявке (Новый), не «Отказ» из удалённой.
    assert ent.status != EntityStatus.rejected

    # Метка Эльвиры по этой вакансии — одна (не две); Пётр — со-рекрутёр
    # из исходной заявки, у него своя.
    tags = ent.extra_data.get("system_hr_tags") or []
    assert sorted(t["name"] for t in tags) == ["Пётр", "Эльвира"], tags


@pytest.mark.asyncio
async def test_source_closed_not_deleted(client, db_session, admin_user, s):
    # id заранее: после expire_all объекты фикстуры протухают.
    I = {k: v.id for k, v in s.items()}
    r = await client.post(_url(s, False), headers=_h(admin_user))
    assert r.status_code == 200, r.text
    db_session.expire_all()
    src = await db_session.get(Vacancy, I["source"])
    assert src.status == VacancyStatus.closed
    assert src.deleted_at is None
    assert src.extra_data["merged_into"] == I["target"]
    left = (await db_session.execute(
        select(VacancyApplication).where(VacancyApplication.vacancy_id == src.id)
    )).scalars().all()
    assert left == []


@pytest.mark.asyncio
async def test_recruiter_cannot_merge(client, db_session, s):
    r = await client.post(_url(s, True), headers=_h(s["elvira"]))
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_same_vacancy_rejected(client, admin_user, s):
    r = await client.post(
        f"/api/vacancies/{s['target'].id}/merge-from/{s['target'].id}", headers=_h(admin_user)
    )
    assert r.status_code == 400, r.text
