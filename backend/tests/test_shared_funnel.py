"""Общая воронка без клонов (модель 2026-07-02).

- «Взять в работу» = join: рекрутёр добавляется в assigned_to ТОЙ ЖЕ вакансии,
  заявка pending_review→open, клон НЕ создаётся.
- «Закрыть вакансию» участником при других активных участниках = ВЫХОД (leave):
  статус не меняется, участник снимается (assigned_to + dismissed_by).
- Закрытие последним участником = реальное закрытие.
- Легаси-клоны продолжают закрываться по-старому (dismissed_by на оригинале).
"""
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import select, func

from api.models.database import Vacancy, VacancyStatus, DepartmentFeature
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


@pytest_asyncio.fixture(autouse=True)
async def candidate_database_feature(db_session, organization):
    """check_vacancy_access требует фичу candidate_database для member —
    включаем org-wide (department_id=NULL), иначе second_user ловит 403."""
    db_session.add(DepartmentFeature(
        org_id=organization.id, department_id=None,
        feature_name="candidate_database", enabled=True,
    ))
    await db_session.commit()


async def _mk_request(db, org, creator, assigned=None, status=VacancyStatus.pending_review) -> Vacancy:
    v = Vacancy(
        org_id=org.id, title="Общая заявка", status=status,
        created_by=creator.id, assigned_to=assigned or [],
        created_at=datetime.utcnow(),
    )
    db.add(v)
    await db.commit()
    await db.refresh(v)
    return v


@pytest.mark.asyncio
async def test_take_joins_same_vacancy_no_clone(
    client, db_session, organization, admin_user, org_owner, second_user, org_member
):
    v = await _mk_request(db_session, organization, admin_user, assigned=[second_user.id])
    before = (await db_session.execute(select(func.count(Vacancy.id)))).scalar()

    r = await client.post(f"/api/vacancies/{v.id}/take", headers=_h(second_user))
    assert r.status_code == 200, r.text
    body = r.json()
    # Та же вакансия (не клон), стала open, рекрутёр в assigned_to
    assert body["id"] == v.id
    assert body["status"] == "open"
    assert second_user.id in (body.get("assigned_to") or [])

    after = (await db_session.execute(select(func.count(Vacancy.id)))).scalar()
    assert after == before  # клон НЕ создан


@pytest.mark.asyncio
async def test_close_with_other_participants_is_leave(
    client, db_session, organization, admin_user, org_owner, second_user, org_member, regular_user, org_admin
):
    """regular_user (второй участник) остаётся → закрытие second_user = выход."""
    # ВАЖНО: regular_user имеет org-роль admin (фикстура org_admin) — поэтому
    # закрываем именно second_user (member), у которого нет полного доступа.
    v = await _mk_request(
        db_session, organization, admin_user,
        assigned=[second_user.id, regular_user.id], status=VacancyStatus.open,
    )
    r = await client.put(f"/api/vacancies/{v.id}", headers=_h(second_user), json={"status": "closed"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "open"  # воронка ЖИВА для остальных
    assert second_user.id not in (body.get("assigned_to") or [])
    await db_session.refresh(v)
    assert second_user.id in ((v.extra_data or {}).get("dismissed_by") or [])


@pytest.mark.asyncio
async def test_close_by_last_participant_really_closes(
    client, db_session, organization, admin_user, org_owner, second_user, org_member
):
    """second_user — единственный активный участник (создатель-админ не в счёт?
    Нет: создатель тоже участник, поэтому делаем создателем самого second_user)."""
    v = await _mk_request(db_session, organization, second_user, assigned=[second_user.id], status=VacancyStatus.open)
    r = await client.put(f"/api/vacancies/{v.id}", headers=_h(second_user), json={"status": "closed"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "closed"


@pytest.mark.asyncio
async def test_admin_close_is_real_close_even_with_participants(
    client, db_session, organization, admin_user, org_owner, second_user, org_member
):
    v = await _mk_request(
        db_session, organization, admin_user,
        assigned=[second_user.id], status=VacancyStatus.open,
    )
    r = await client.put(f"/api/vacancies/{v.id}", headers=_h(admin_user), json={"status": "closed"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "closed"


@pytest.mark.asyncio
async def test_legacy_clone_close_still_dismisses_on_original(
    client, db_session, organization, admin_user, org_owner, second_user, org_member
):
    original = await _mk_request(db_session, organization, admin_user, assigned=[second_user.id])
    clone = Vacancy(
        org_id=organization.id, title="Общая заявка", status=VacancyStatus.open,
        created_by=second_user.id,
        extra_data={"cloned_from_request_id": original.id},
        created_at=datetime.utcnow(),
    )
    db_session.add(clone)
    await db_session.commit()
    await db_session.refresh(clone)

    r = await client.put(f"/api/vacancies/{clone.id}", headers=_h(second_user), json={"status": "closed"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "closed"  # клон закрывается реально
    await db_session.refresh(original)
    assert second_user.id not in (original.assigned_to or [])
    assert second_user.id in ((original.extra_data or {}).get("dismissed_by") or [])


@pytest.mark.asyncio
async def test_reassign_prunes_accepted_by(
    client, db_session, organization, org_owner, second_user, org_member
):
    # accepted_by=[second_user, 999999], переназначаем только на second_user →
    # 999999 (сняли с назначения) выпадает из accepted_by. Фейковый id для
    # «снимаемого» — assign валидирует только user_ids, не accepted_by.
    # org_member в сигнатуре ради членства user 2 в орге (иначе assign даёт 400).
    OTHER = 999999
    v = Vacancy(
        org_id=organization.id, title="Заявка", status=VacancyStatus.open,
        created_by=org_owner.id, assigned_to=[second_user.id, OTHER],
        extra_data={"accepted_by": [second_user.id, OTHER]},
        created_at=datetime.utcnow(),
    )
    db_session.add(v); await db_session.commit(); await db_session.refresh(v)
    vid = v.id

    r = await client.post(
        f"/api/vacancies/{vid}/assign", headers=_h(org_owner),
        json={"user_ids": [second_user.id], "all": False},
    )
    assert r.status_code == 200, r.text
    assert (r.json().get("extra_data") or {}).get("accepted_by") == [second_user.id]


@pytest.mark.asyncio
async def test_reassign_all_keeps_accepted_by(
    client, db_session, organization, org_owner, second_user
):
    v = Vacancy(
        org_id=organization.id, title="Заявка", status=VacancyStatus.open,
        created_by=org_owner.id, assigned_to=[second_user.id],
        extra_data={"accepted_by": [second_user.id]},
        created_at=datetime.utcnow(),
    )
    db_session.add(v); await db_session.commit(); await db_session.refresh(v)
    vid = v.id

    r = await client.post(
        f"/api/vacancies/{vid}/assign", headers=_h(org_owner),
        json={"user_ids": [], "all": True},
    )
    assert r.status_code == 200, r.text
    # all=True → accepted_by не трогаем
    assert (r.json().get("extra_data") or {}).get("accepted_by") == [second_user.id]


@pytest.mark.asyncio
async def test_assign_to_open_funnel_makes_lead(
    client, db_session, organization, org_owner, second_user, org_member
):
    # ВОРОНКА (open): «назначил = сразу ведёт» — назначенный сразу в accepted_by
    # (карточка «Рекрутер: …» + «Мои вакансии»), без «Взять в работу».
    v = Vacancy(
        org_id=organization.id, title="Воронка", status=VacancyStatus.open,
        created_by=org_owner.id, assigned_to=[],
        created_at=datetime.utcnow(),
    )
    db_session.add(v); await db_session.commit(); await db_session.refresh(v)
    vid = v.id

    r = await client.post(
        f"/api/vacancies/{vid}/assign", headers=_h(org_owner),
        json={"user_ids": [second_user.id], "all": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body.get("extra_data") or {}).get("accepted_by") == [second_user.id]
    assert body["status"] == "open"


@pytest.mark.asyncio
async def test_assign_to_request_stays_request(
    client, db_session, organization, org_owner, second_user, org_member
):
    # ЗАЯВКА (pending_review): назначение = РАЗДАЧА. Статус НЕ меняется, рекрутёр
    # НЕ становится ведущим (accepted_by пуст) — он сам жмёт «Взять в работу».
    # Но он назначен (в assigned_to) → видит заявку в «Заявки».
    v = Vacancy(
        org_id=organization.id, title="Заявка", status=VacancyStatus.pending_review,
        created_by=org_owner.id, assigned_to=[],
        created_at=datetime.utcnow(),
    )
    db_session.add(v); await db_session.commit(); await db_session.refresh(v)
    vid = v.id

    r = await client.post(
        f"/api/vacancies/{vid}/assign", headers=_h(org_owner),
        json={"user_ids": [second_user.id], "all": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "pending_review"  # осталась заявкой
    assert (body.get("extra_data") or {}).get("accepted_by") in (None, [])  # не ведущий
    assert second_user.id in (body.get("assigned_to") or [])  # но назначен


@pytest.mark.asyncio
async def test_reassign_undismisses_added_recruiter(
    client, db_session, organization, org_owner, second_user, org_member
):
    # second_user был снят/вышел (в dismissed_by). Повторно назначаем его →
    # dismissed_by очищается, иначе он остаётся невидимым (isVacancyParticipant).
    v = Vacancy(
        org_id=organization.id, title="Заявка", status=VacancyStatus.open,
        created_by=org_owner.id, assigned_to=[],
        extra_data={"dismissed_by": [second_user.id, 999999]},
        created_at=datetime.utcnow(),
    )
    db_session.add(v); await db_session.commit(); await db_session.refresh(v)
    vid = v.id

    r = await client.post(
        f"/api/vacancies/{vid}/assign", headers=_h(org_owner),
        json={"user_ids": [second_user.id], "all": False},
    )
    assert r.status_code == 200, r.text
    extra = r.json().get("extra_data") or {}
    # назначенный снят с dismissed_by, чужой (999999) остаётся
    assert second_user.id not in (extra.get("dismissed_by") or [])
    assert 999999 in (extra.get("dismissed_by") or [])
    assert second_user.id in (r.json().get("assigned_to") or [])


@pytest.mark.asyncio
async def test_assign_all_clears_dismissed_by(
    client, db_session, organization, org_owner, second_user, org_member
):
    """«Всем рекрутёрам» ПОЛНОСТЬЮ чистит dismissed_by — иначе ранее отказавшийся
    рекрутёр не увидит вакансию, хотя ему придёт уведомление (аудит 2026-08-07)."""
    v = Vacancy(
        org_id=organization.id, title="Заявка", status=VacancyStatus.open,
        created_by=org_owner.id, assigned_to=[],
        extra_data={"dismissed_by": [second_user.id]},
        created_at=datetime.utcnow(),
    )
    db_session.add(v); await db_session.commit(); await db_session.refresh(v)
    vid = v.id

    r = await client.post(
        f"/api/vacancies/{vid}/assign", headers=_h(org_owner),
        json={"user_ids": [], "all": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["assigned_to_all"] is True
    assert (body.get("extra_data") or {}).get("dismissed_by") in (None, [])


@pytest.mark.asyncio
async def test_assign_drops_phantom_stale_assignee(
    client, db_session, organization, org_owner, second_user, org_member, regular_user, org_admin
):
    """«Фантомный» назначенец (в assigned_to, но без OrgMember — вышел/удалён)
    НЕ должен блокировать редактирование списка рекрутёров. Фронт шлёт весь
    assigned_to (включая невидимый фантом), и раньше это роняло сейв с 400
    «Users not in org». Теперь фантом молча вычищается, а нового валидного
    рекрутёра можно добавить."""
    PHANTOM = 999999  # нет OrgMember в орге
    v = Vacancy(
        org_id=organization.id, title="Воронка", status=VacancyStatus.open,
        created_by=org_owner.id, assigned_to=[second_user.id, PHANTOM],
        created_at=datetime.utcnow(),
    )
    db_session.add(v); await db_session.commit(); await db_session.refresh(v)
    vid = v.id

    # Фронт пере-шлёт весь список (second_user + фантом) + добавляет regular_user.
    r = await client.post(
        f"/api/vacancies/{vid}/assign", headers=_h(org_owner),
        json={"user_ids": [second_user.id, PHANTOM, regular_user.id], "all": False},
    )
    assert r.status_code == 200, r.text
    assigned = r.json().get("assigned_to") or []
    assert PHANTOM not in assigned            # фантом вычищен
    assert second_user.id in assigned          # существующий валидный сохранён
    assert regular_user.id in assigned         # новый валидный добавлен


@pytest.mark.asyncio
async def test_assign_rejects_newly_added_phantom(
    client, db_session, organization, org_owner, second_user, org_member
):
    """Ново добавляемый невалидный юзер (не в орге и не был назначен) по-прежнему
    отвергается 400 — послабление касается только УЖЕ назначенных фантомов."""
    PHANTOM = 999999
    v = Vacancy(
        org_id=organization.id, title="Воронка", status=VacancyStatus.open,
        created_by=org_owner.id, assigned_to=[second_user.id],
        created_at=datetime.utcnow(),
    )
    db_session.add(v); await db_session.commit(); await db_session.refresh(v)
    vid = v.id

    r = await client.post(
        f"/api/vacancies/{vid}/assign", headers=_h(org_owner),
        json={"user_ids": [second_user.id, PHANTOM], "all": False},
    )
    assert r.status_code == 400, r.text
    assert "not in org" in r.text.lower()


@pytest.mark.asyncio
async def test_member_can_delete_vacancy(
    client, db_session, organization, org_owner, second_user, org_member
):
    """По запросу юзера 2026-08-04 удаление доступно ВСЕМ, включая рекрутёра-
    member (разворот прежнего admin-only). Раньше member ловил 403."""
    v = Vacancy(
        org_id=organization.id, title="Воронка", status=VacancyStatus.open,
        created_by=org_owner.id, assigned_to=[second_user.id],
        created_at=datetime.utcnow(),
    )
    db_session.add(v); await db_session.commit(); await db_session.refresh(v)
    vid = v.id

    r = await client.delete(f"/api/vacancies/{vid}", headers=_h(second_user))
    assert r.status_code == 204, r.text
    # Мягкое удаление: deleted_at проставлен.
    await db_session.refresh(v)
    assert v.deleted_at is not None
