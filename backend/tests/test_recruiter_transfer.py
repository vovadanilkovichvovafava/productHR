"""Передача дел уходящего рекрутёра (POST /api/users/reassign-split).

Уходящий X → живой Y по воронкам: заявки, вакансии, кандидаты и участие в
воронках меняют владельца, HR-метки пересчитываются. Строго в рамках орга.
С 26.10.2026 — вливание в такую же воронку получателя, итог «без изменений»
(dry_run), получатель только рекрутёр/админ (не наблюдатель). «Передать всё»
(reassign-ownership) удалена: интерфейс её не вызывал.
"""
from datetime import datetime

import pytest
from sqlalchemy import select

from api.models.database import (
    Entity, EntityType, EntityStatus, Vacancy, VacancyStatus,
    VacancyApplication, ApplicationStage, User, OrgMember, OrgRole,
)
from api.services.hr_tags import sync_for_entity, EXTRA_KEY


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _member(db, org_id, name, email, role=OrgRole.member) -> User:
    u = User(email=email, password_hash="x", name=name)
    db.add(u)
    await db.flush()
    db.add(OrgMember(org_id=org_id, user_id=u.id, role=role, created_at=datetime.utcnow()))
    await db.flush()
    return u


async def _vac(db, org_id, creator_id, title, **extra) -> Vacancy:
    v = Vacancy(
        org_id=org_id, created_by=creator_id, title=title,
        status=VacancyStatus.open, salary_currency="RUB", priority=1, tags=[],
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(), **extra,
    )
    db.add(v)
    await db.flush()
    return v


async def _cand(db, org_id, creator_id, name) -> Entity:
    e = Entity(
        org_id=org_id, created_by=creator_id, name=name,
        type=EntityType.candidate, status=EntityStatus.active, created_at=datetime.utcnow(),
    )
    db.add(e)
    await db.flush()
    return e


async def _app(db, vac_id, entity_id, creator_id) -> VacancyApplication:
    a = VacancyApplication(
        vacancy_id=vac_id, entity_id=entity_id, stage=ApplicationStage.interview,
        stage_order=1000, created_by=creator_id, applied_at=datetime.utcnow(),
        last_stage_change_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    db.add(a)
    await db.flush()
    return a


@pytest.mark.asyncio
async def test_handover_summary_and_split(
    client, db_session, organization, admin_user, org_owner, admin_token,
):
    """Раздельная передача: воронку V1 → Y1, воронку V2 → Y2, пул → Y1."""
    org = organization.id
    x = await _member(db_session, org, "Уходящий", "sx@t.co", OrgRole.hr)
    y1 = await _member(db_session, org, "Приёмник 1", "sy1@t.co", OrgRole.hr)
    y2 = await _member(db_session, org, "Приёмник 2", "sy2@t.co", OrgRole.hr)

    v1 = await _vac(db_session, org, x.id, "Воронка 1", assigned_to=[x.id])
    c1 = await _cand(db_session, org, x.id, "Кандидат В1")
    await _app(db_session, v1.id, c1.id, x.id)
    v2 = await _vac(db_session, org, x.id, "Воронка 2", assigned_to=[x.id])
    c2 = await _cand(db_session, org, x.id, "Кандидат В2")
    await _app(db_session, v2.id, c2.id, x.id)
    # Кандидат вне воронок (без заявки).
    c_pool = await _cand(db_session, org, x.id, "Кандидат Пул")
    v1_id, v2_id, c1_id, c2_id, cpool_id = v1.id, v2.id, c1.id, c2.id, c_pool.id
    xid, y1id, y2id = x.id, y1.id, y2.id
    await db_session.commit()

    # Сводка: 2 воронки (по 1 кандидату) + 1 вне воронок.
    r = await client.get(f"/api/users/{xid}/handover-summary", headers=_h(admin_token))
    assert r.status_code == 200, r.text
    summ = r.json()
    assert summ["pool_candidates"] == 1, summ
    by_vid = {f["vacancy_id"]: f for f in summ["funnels"]}
    assert by_vid[v1_id]["candidates"] == 1 and by_vid[v2_id]["candidates"] == 1, summ

    # Раздельная передача.
    r = await client.post(
        "/api/users/reassign-split",
        json={
            "from_user_id": xid,
            "assignments": [
                {"vacancy_id": v1_id, "to_user_id": y1id},
                {"vacancy_id": v2_id, "to_user_id": y2id},
            ],
            "pool_to_user_id": y1id,
        },
        headers=_h(admin_token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["vacancies"] == 2 and body["applications"] == 2, body

    for cid, expect in ((c1_id, y1id), (c2_id, y2id), (cpool_id, y1id)):
        e = await db_session.get(Entity, cid)
        await db_session.refresh(e)
        assert e.created_by == expect, (cid, e.created_by, expect)
    vv1 = await db_session.get(Vacancy, v1_id)
    vv2 = await db_session.get(Vacancy, v2_id)
    assert vv1.created_by == y1id and vv2.created_by == y2id
    # Получатель стал ведущим (accepted_by) — иначе воронка «повиснет» в сайдбаре.
    assert y1id in ((vv1.extra_data or {}).get("accepted_by") or []) and xid not in (vv1.assigned_to or [])
    assert y2id in ((vv2.extra_data or {}).get("accepted_by") or [])


@pytest.mark.asyncio
async def test_split_rejects_cross_org_recipient(
    client, db_session, organization, second_organization, admin_user, org_owner, admin_token,
):
    x = await _member(db_session, organization.id, "X", "sx2@t.co", OrgRole.hr)
    v = await _vac(db_session, organization.id, x.id, "V", assigned_to=[x.id])
    y_other = await _member(db_session, second_organization.id, "Чужой", "so@t.co", OrgRole.hr)
    vid, xid, yo = v.id, x.id, y_other.id
    await db_session.commit()

    r = await client.post(
        "/api/users/reassign-split",
        json={"from_user_id": xid, "assignments": [{"vacancy_id": vid, "to_user_id": yo}]},
        headers=_h(admin_token),
    )
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_split_moves_ownership_and_hr_tags(
    client, db_session, organization, admin_user, org_owner, admin_token,
):
    org = organization.id
    x = await _member(db_session, org, "Уходящий X", "x@t.co", OrgRole.hr)
    y = await _member(db_session, org, "Живой Y", "y@t.co", OrgRole.hr)
    v_solo = await _vac(db_session, org, x.id, "Solo X")
    c1 = await _cand(db_session, org, x.id, "Кандидат Один")
    a1 = await _app(db_session, v_solo.id, c1.id, x.id)
    # Общая воронка Y, куда X добавил кандидата (заявка X, ведущий — Y).
    v_shared = await _vac(db_session, org, y.id, "Shared Y", assigned_to=[x.id, y.id])
    c2 = await _cand(db_session, org, x.id, "Кандидат Два")
    a2 = await _app(db_session, v_shared.id, c2.id, x.id)
    ids = dict(a1=a1.id, a2=a2.id, solo=v_solo.id, shared=v_shared.id, c1=c1.id, c2=c2.id, x=x.id, y=y.id)
    await db_session.commit()
    await sync_for_entity(db_session, ids["c1"])
    await sync_for_entity(db_session, ids["c2"])
    await db_session.commit()

    r = await client.post("/api/users/reassign-split", json={
        "from_user_id": ids["x"],
        "assignments": [{"vacancy_id": ids["solo"], "to_user_id": ids["y"]},
                        {"vacancy_id": ids["shared"], "to_user_id": ids["y"]}],
    }, headers=_h(admin_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["applications"] == 2 and body["candidates"] == 2, body
    assert body["per_recipient"] == {str(ids["y"]): 2}, body

    for aid in (ids["a1"], ids["a2"]):
        a = await db_session.get(VacancyApplication, aid, populate_existing=True)
        assert a.created_by == ids["y"]
    for cid in (ids["c1"], ids["c2"]):
        e = await db_session.get(Entity, cid, populate_existing=True)
        assert e.created_by == ids["y"]
        tags = (e.extra_data or {}).get(EXTRA_KEY) or []
        assert tags and all(t["hr_id"] == ids["y"] for t in tags), tags
    vs = await db_session.get(Vacancy, ids["shared"], populate_existing=True)
    assert ids["x"] not in (vs.assigned_to or []) and ids["y"] in (vs.assigned_to or [])


@pytest.mark.asyncio
async def test_split_requires_admin(client, db_session, organization, admin_user, org_owner):
    from api.services.auth import create_access_token
    x = await _member(db_session, organization.id, "X", "x3@t.co", OrgRole.hr)
    plain = await _member(db_session, organization.id, "Обычный", "plain@t.co", role=OrgRole.member)
    y = await _member(db_session, organization.id, "Y", "y3@t.co", OrgRole.hr)
    v = await _vac(db_session, organization.id, x.id, "V", assigned_to=[x.id])
    xid, yid, vid = x.id, y.id, v.id
    await db_session.commit()
    token = create_access_token({"sub": str(plain.id), "token_version": 0})
    r = await client.post("/api/users/reassign-split", json={
        "from_user_id": xid, "assignments": [{"vacancy_id": vid, "to_user_id": yid}],
    }, headers=_h(token))
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_observer_or_member_is_not_a_recipient(
    client, db_session, organization, admin_user, org_owner, admin_token,
):
    org = organization.id
    x = await _member(db_session, org, "X", "x4@t.co", OrgRole.hr)
    obs = await _member(db_session, org, "Наблюдатель", "obs@t.co", OrgRole.admin)
    member = await _member(db_session, org, "Сотрудник", "mem@t.co", OrgRole.member)
    (await db_session.execute(select(OrgMember).where(OrgMember.user_id == obs.id))).scalar_one().is_readonly = True
    v = await _vac(db_session, org, x.id, "V", assigned_to=[x.id])
    xid, vid, oid, mid = x.id, v.id, obs.id, member.id
    await db_session.commit()
    for to in (oid, mid):
        r = await client.post("/api/users/reassign-split", json={
            "from_user_id": xid, "assignments": [{"vacancy_id": vid, "to_user_id": to}],
        }, headers=_h(admin_token))
        assert r.status_code == 400, r.text


async def _twin_funnels(db, org):
    """У X и Y по своей воронке «Трафик». Анна — в обеих: у X её довели дальше
    и позже (Интервью), у Y она на «Новом» давно. Борис — только у X."""
    from datetime import timedelta
    x = await _member(db, org, "Пётр", "petr@t.co", OrgRole.hr)
    y = await _member(db, org, "Мария", "maria@t.co", OrgRole.hr)
    vx = await _vac(db, org, x.id, "Трафик", assigned_to=[x.id], extra_data={"accepted_by": [x.id]})
    vy = await _vac(db, org, y.id, "трафик ", assigned_to=[y.id], extra_data={"accepted_by": [y.id]})
    anna = await _cand(db, org, x.id, "Анна")
    boris = await _cand(db, org, x.id, "Борис")
    old = datetime.utcnow() - timedelta(days=10)
    ay = VacancyApplication(vacancy_id=vy.id, entity_id=anna.id, stage=ApplicationStage.applied,
                            stage_order=0, created_by=y.id, applied_at=old, last_stage_change_at=old, updated_at=old)
    db.add(ay)
    ax = await _app(db, vx.id, anna.id, x.id)          # interview, сейчас
    bx = await _app(db, vx.id, boris.id, x.id)
    await db.flush()
    return x, y, vx, vy, anna, boris, ax, ay, bx


@pytest.mark.asyncio
async def test_merge_into_receivers_twin_funnel(
    client, db_session, organization, admin_user, org_owner, admin_token,
):
    from api.models.database import StageTransition
    x, y, vx, vy, anna, boris, ax, ay, bx = await _twin_funnels(db_session, organization.id)
    ids = dict(x=x.id, y=y.id, vx=vx.id, vy=vy.id, anna=anna.id, boris=boris.id, ay=ay.id)
    await db_session.commit()

    # Сводка: у воронки X есть «такая же» у Y, с Y среди участников.
    summ = (await client.get(f"/api/users/{ids['x']}/handover-summary", headers=_h(admin_token))).json()
    f = next(f for f in summ["funnels"] if f["vacancy_id"] == ids["vx"])
    m = next(m for m in f["matches"] if m["vacancy_id"] == ids["vy"])
    assert ids["y"] in m["participants"]

    req = {"from_user_id": ids["x"], "assignments": [
        {"vacancy_id": ids["vx"], "to_user_id": ids["y"], "merge_into_vacancy_id": ids["vy"]}]}
    # Итог без изменений: 2 кандидата, Анна уже есть — останется её более свежий этап.
    pre = (await client.post("/api/users/reassign-split", json={**req, "dry_run": True}, headers=_h(admin_token))).json()
    assert pre["per_recipient"] == {str(ids["y"]): 2}, pre
    assert pre["merges"][0]["overlapping"] == [{"entity_id": ids["anna"], "name": "Анна", "stage": "interview"}]
    assert (await db_session.get(Vacancy, ids["vx"], populate_existing=True)).status == VacancyStatus.open

    r = await client.post("/api/users/reassign-split", json=req, headers=_h(admin_token))
    assert r.status_code == 200, r.text
    # Копия X закрыта, всё в воронке Марии; у Анны одна заявка с этапом Интервью.
    assert (await db_session.get(Vacancy, ids["vx"], populate_existing=True)).status == VacancyStatus.closed
    apps = (await db_session.execute(select(VacancyApplication).where(
        VacancyApplication.entity_id.in_([ids["anna"], ids["boris"]])).execution_options(populate_existing=True))).scalars().all()
    assert {(a.entity_id, a.vacancy_id) for a in apps} == {(ids["anna"], ids["vy"]), (ids["boris"], ids["vy"])}
    anna_app = next(a for a in apps if a.entity_id == ids["anna"])
    assert anna_app.id == ids["ay"] and anna_app.stage == ApplicationStage.interview
    last = (await db_session.execute(select(StageTransition).where(
        StageTransition.application_id == ids["ay"]).order_by(StageTransition.id.desc()))).scalars().first()
    assert last.to_stage == "interview" and "объединены" in (last.comment or "")
    assert all(a.created_by == ids["y"] for a in apps)


@pytest.mark.asyncio
async def test_merge_keeps_shared_funnel_for_others(
    client, db_session, organization, admin_user, org_owner, admin_token,
):
    """В воронке X работает ещё и W — переезжают только кандидаты X, воронка
    остаётся у W открытой, Мария в ней не участник (иначе снова две копии)."""
    x, y, vx, vy, anna, boris, ax, ay, bx = await _twin_funnels(db_session, organization.id)
    w = await _member(db_session, organization.id, "Влад", "w@t.co", OrgRole.hr)
    vx.assigned_to = [x.id, w.id]
    cw = await _cand(db_session, organization.id, w.id, "Кандидат W")
    aw = await _app(db_session, vx.id, cw.id, w.id)
    ids = dict(x=x.id, y=y.id, vx=vx.id, vy=vy.id, boris=boris.id, aw=aw.id)
    await db_session.commit()

    r = await client.post("/api/users/reassign-split", json={"from_user_id": ids["x"], "assignments": [
        {"vacancy_id": ids["vx"], "to_user_id": ids["y"], "merge_into_vacancy_id": ids["vy"]}]},
        headers=_h(admin_token))
    assert r.status_code == 200, r.text
    v = await db_session.get(Vacancy, ids["vx"], populate_existing=True)
    assert v.status == VacancyStatus.open
    assert ids["y"] not in (v.assigned_to or []) and ids["y"] not in ((v.extra_data or {}).get("accepted_by") or [])
    assert (await db_session.get(VacancyApplication, ids["aw"], populate_existing=True)).vacancy_id == ids["vx"]
    boris_app = (await db_session.execute(select(VacancyApplication).where(
        VacancyApplication.entity_id == ids["boris"]).execution_options(populate_existing=True))).scalar_one()
    assert boris_app.vacancy_id == ids["vy"]


@pytest.mark.asyncio
async def test_merge_only_into_receivers_own_funnel(
    client, db_session, organization, admin_user, org_owner, admin_token,
):
    x, y, vx, vy, *_ = await _twin_funnels(db_session, organization.id)
    z = await _member(db_session, organization.id, "Чужой", "z@t.co", OrgRole.hr)
    ids = dict(x=x.id, vx=vx.id, vy=vy.id, z=z.id)
    await db_session.commit()
    r = await client.post("/api/users/reassign-split", json={"from_user_id": ids["x"], "assignments": [
        {"vacancy_id": ids["vx"], "to_user_id": ids["z"], "merge_into_vacancy_id": ids["vy"]}]},
        headers=_h(admin_token))
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_pool_includes_cards_outside_own_funnels(
    client, db_session, organization, admin_user, org_owner, admin_token,
):
    """Карточка X, которую потом добавила в свою воронку Мария, — тоже его:
    раньше она не попадала ни в воронки, ни в «без воронки» и не передавалась."""
    org = organization.id
    x = await _member(db_session, org, "X", "x5@t.co", OrgRole.hr)
    y = await _member(db_session, org, "Y", "y5@t.co", OrgRole.hr)
    vy = await _vac(db_session, org, y.id, "Чужая", assigned_to=[y.id])
    c = await _cand(db_session, org, x.id, "Добавлен Марией")
    await _app(db_session, vy.id, c.id, y.id)
    ids = dict(x=x.id, y=y.id, c=c.id)
    await db_session.commit()
    summ = (await client.get(f"/api/users/{ids['x']}/handover-summary", headers=_h(admin_token))).json()
    assert summ["pool_candidates"] == 1, summ
    r = await client.post("/api/users/reassign-split", json={
        "from_user_id": ids["x"], "assignments": [], "pool_to_user_id": ids["y"]}, headers=_h(admin_token))
    assert r.status_code == 200, r.text
    assert (await db_session.get(Entity, ids["c"], populate_existing=True)).created_by == ids["y"]
