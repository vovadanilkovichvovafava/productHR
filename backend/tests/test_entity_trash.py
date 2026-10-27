"""Корзина кандидатов (20.10.2026, services/entity_trash.py).

19.10.2026 кандидатку удалили, и ни кто, ни когда — не осталось, а вернуть было
нечем: удаление стирает кандидата каскадом. Теперь удаление кладёт полный слепок
в корзину на 7 дней, админ возвращает кандидата как был, журнал «кто, кого,
когда» остаётся.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from api.models.database import (
    ApplicationStage, CallRecording, DeletedEntity, Entity, EntityFile, EntityFileType,
    EntityStatus, EntityType, StageTransition, Vacancy, VacancyApplication, VacancyStatus,
)
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


@pytest.fixture
async def doomed(db_session, organization, department, admin_user, org_owner):
    now = datetime.utcnow()
    e = Entity(
        org_id=organization.id, name="Муравьева Елизавета", type=EntityType.candidate,
        status=EntityStatus.screening, created_by=admin_user.id, created_at=now,
        email="liza@example.com",
        extra_data={"notes": [{"id": "n1", "text": "созвон прошёл", "date": now.isoformat()}]},
    )
    db_session.add(e)
    v = Vacancy(org_id=organization.id, department_id=department.id, created_by=admin_user.id,
                title="Трафик", status=VacancyStatus.open, salary_currency="RUB",
                created_at=now, updated_at=now)
    db_session.add(v)
    await db_session.commit()
    app = VacancyApplication(vacancy_id=v.id, entity_id=e.id, stage=ApplicationStage.screening,
                             stage_order=1, created_by=admin_user.id, applied_at=now,
                             last_stage_change_at=now, updated_at=now)
    db_session.add(app)
    await db_session.commit()
    db_session.add(StageTransition(application_id=app.id, entity_id=e.id, from_stage="applied",
                                   to_stage="screening", changed_by=admin_user.id,
                                   comment="ТЗ выдано", created_at=now))
    db_session.add(EntityFile(entity_id=e.id, org_id=organization.id, file_type=EntityFileType.resume,
                              file_name="cv.pdf", file_data=b"%PDF-1.4 resume", mime_type="application/pdf",
                              uploaded_by=admin_user.id))
    call = CallRecording(org_id=organization.id, owner_id=admin_user.id, entity_id=e.id,
                         source_type="upload", title="Созвон")
    db_session.add(call)
    await db_session.commit()
    return e, v, app, call


async def _delete(client, user, entity_id):
    r = await client.delete(f"/api/entities/{entity_id}", headers=_h(user))
    assert r.status_code in (200, 204), r.text
    return r.json()


async def test_delete_goes_to_trash_and_restores_everything(client, db_session, admin_user, doomed):
    e, v, app, call = doomed
    eid, app_id, call_id, vid = e.id, app.id, call.id, v.id
    H, admin_name = _h(admin_user), admin_user.name
    res = await _delete(client, admin_user, eid)
    assert res["trash_id"]

    db_session.expire_all()
    assert (await db_session.execute(select(Entity).where(Entity.id == eid))).scalar() is None
    assert (await db_session.get(CallRecording, call_id)).entity_id is None

    trash = (await client.get("/api/entities/trash", headers=H)).json()["items"]
    item = next(i for i in trash if i["entity_id"] == eid)
    assert item["name"] == "Муравьева Елизавета"
    assert item["deleted_by_name"] == admin_name
    assert item["restorable"] is True
    assert item["summary"] == {"applications": 1, "history": 1, "files": 1}

    r = await client.post(f"/api/entities/trash/{item['id']}/restore", headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["skipped"] == {}

    db_session.expire_all()
    back = (await db_session.execute(select(Entity).where(Entity.id == eid))).scalar_one()
    assert back.status == EntityStatus.screening
    assert back.extra_data["notes"][0]["text"] == "созвон прошёл"
    a = (await db_session.execute(select(VacancyApplication).where(VacancyApplication.id == app_id))).scalar_one()
    assert a.stage == ApplicationStage.screening and a.vacancy_id == vid
    hist = (await db_session.execute(
        select(StageTransition.comment).where(StageTransition.application_id == app_id)
    )).scalars().all()
    assert hist == ["ТЗ выдано"]
    f = (await db_session.execute(select(EntityFile).where(EntityFile.entity_id == eid))).scalar_one()
    assert f.file_data == b"%PDF-1.4 resume" and f.file_type == EntityFileType.resume
    # Обнулённая при удалении ссылка звонка вернулась.
    assert (await db_session.get(CallRecording, call_id)).entity_id == eid

    # Второй раз — нельзя, а в журнале видно, кто вернул.
    r = await client.post(f"/api/entities/trash/{item['id']}/restore", headers=H)
    assert r.status_code == 409
    item = next(i for i in (await client.get("/api/entities/trash", headers=H)).json()["items"]
                if i["entity_id"] == eid)
    assert item["restored_by_name"] == admin_name and item["restorable"] is False


async def test_after_seven_days_cannot_restore_but_journal_stays(client, db_session, admin_user, doomed):
    e, *_ = doomed
    eid = e.id
    res = await _delete(client, admin_user, eid)
    rec = await db_session.get(DeletedEntity, res["trash_id"])
    rec.purge_after = datetime.utcnow() - timedelta(minutes=1)
    await db_session.commit()

    items = (await client.get("/api/entities/trash", headers=_h(admin_user))).json()["items"]
    item = next(i for i in items if i["entity_id"] == eid)
    assert item["restorable"] is False and item["purged_at"]
    await db_session.refresh(rec)
    assert rec.snapshot is None  # слепок стёрт, строка журнала — нет
    r = await client.post(f"/api/entities/trash/{rec.id}/restore", headers=_h(admin_user))
    assert r.status_code == 410


async def test_restore_skips_rows_whose_parent_is_gone(client, db_session, admin_user, doomed):
    """За неделю удалили воронку — карточка возвращается, заявка нет, и это видно."""
    e, v, app, _ = doomed
    eid = e.id
    res = await _delete(client, admin_user, eid)
    await db_session.delete(await db_session.get(Vacancy, v.id))
    await db_session.commit()
    r = await client.post(f"/api/entities/trash/{res['trash_id']}/restore", headers=_h(admin_user))
    assert r.status_code == 200, r.text
    assert r.json()["skipped"].get("vacancy_applications") == 1
    db_session.expire_all()
    assert (await db_session.execute(select(Entity).where(Entity.id == eid))).scalar() is not None


async def test_trash_is_closed_to_non_hr(client, db_session, admin_user, regular_user, org_member, second_user, doomed):
    # Сотрудник без HR (role=member) корзину не видит; рекрутёры — видят
    # (владелец, 23.10.2026), см. test_recruiter_opens_deleted_card.
    e, *_ = doomed
    res = await _delete(client, admin_user, e.id)
    r = await client.get("/api/entities/trash", headers=_h(second_user))
    assert r.status_code == 403
    r = await client.post(f"/api/entities/trash/{res['trash_id']}/restore", headers=_h(second_user))
    assert r.status_code == 403


async def test_recruiter_opens_deleted_card(client, db_session, organization, admin_user, doomed):
    """Владелец, 23.10.2026: корзина — всем рекрутёрам, удалённая карточка
    открывается как обычная (только чтение) и её файлы скачиваются."""
    from api.models.database import OrgMember, OrgRole, User
    e, v, app, call = doomed
    eid = e.id
    recruiter = User(email="hr.trash@test.local", name="Рекрутёр Корзины", password_hash="x", is_active=True)
    db_session.add(recruiter)
    await db_session.commit()
    db_session.add(OrgMember(org_id=organization.id, user_id=recruiter.id, role=OrgRole.hr))
    await db_session.commit()
    H = _h(recruiter)

    res = await _delete(client, admin_user, eid)
    tid = res["trash_id"]
    items = (await client.get("/api/entities/trash", headers=H)).json()["items"]
    assert any(i["id"] == tid for i in items)

    view = (await client.get(f"/api/entities/trash/{tid}/card", headers=H)).json()
    assert view["card"]["name"] == "Муравьева Елизавета" and view["card"]["email"] == "liza@example.com"
    assert [n["text"] for n in view["card"]["extra_data"]["notes"]] == ["созвон прошёл"]
    block = view["blocks"][0]
    assert (block["vacancy_title"], block["current_stage"]) == ("Трафик", "screening")
    assert [(ev["to_stage"], ev["comment"]) for ev in block["events"]] == [("screening", "ТЗ выдано")]
    assert view["trash"]["restorable"] is True
    f = view["files"][0]
    assert f["file_name"] == "cv.pdf" and "file_data" not in f

    r = await client.get(f"/api/entities/trash/{tid}/files/{f['id']}", headers=H)
    assert r.status_code == 200 and r.content == b"%PDF-1.4 resume"
    assert (await client.get(f"/api/entities/trash/{tid}/files/999999", headers=H)).status_code == 404

    r = await client.post(f"/api/entities/trash/{tid}/restore", headers=H)
    assert r.status_code == 200, r.text
