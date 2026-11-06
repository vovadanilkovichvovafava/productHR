"""Страница «Анкеты → Ответы» (06.11.2026): все анкеты и потерянные ответы.

Владелец: «отдельная страница с анкетами — на случай, если кандидат
потеряется или анкета от него не дойдёт и не отобразится». На проде лежало 9
ответов без кандидата: карточку удалили, ссылка стёрлась каскадом, а сам ответ
остался и не был виден нигде.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from api.models.database import (
    ApplicationStage, Entity, EntityStatus, EntityType, FormClientError, FormDispatch,
    FormSubmission, FormTemplate, OrgMember, OrgRole, User, Vacancy, VacancyApplication,
    VacancyStatus,
)
from api.services.auth import create_access_token
from api.services.form_inbox import summarize, who_hint

FIELDS = [
    {"id": "f1", "type": "text", "label": "ФИО", "required": False},
    {"id": "f2", "type": "text", "label": "Опыт", "required": False},
]


def _h(user):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(user.id)})}"}


@pytest.fixture
async def recruiter(db_session, organization):
    u = User(email="hr.inbox@test.local", name="Пётр", password_hash="x", is_active=True)
    db_session.add(u)
    await db_session.commit()
    db_session.add(OrgMember(org_id=organization.id, user_id=u.id, role=OrgRole.hr))
    await db_session.commit()
    return u


@pytest.fixture
async def board(db_session, organization, department, admin_user):
    """Анкета и четыре строки: заполнена, открыта, не открыта, ответ без кандидата."""
    now = datetime.utcnow()
    form = FormTemplate(org_id=organization.id, created_by=admin_user.id, title="Вводная",
                        slug="inbox-vvodnaya", fields=FIELDS)
    anna = Entity(org_id=organization.id, type=EntityType.candidate, name="Анна Иванова", status=EntityStatus.new)
    boris = Entity(org_id=organization.id, type=EntityType.candidate, name="Борис Петров", status=EntityStatus.new)
    vera = Entity(org_id=organization.id, type=EntityType.candidate, name="Вера Сидорова", status=EntityStatus.new)
    db_session.add_all([form, anna, boris, vera])
    await db_session.commit()

    sub = FormSubmission(form_id=form.id, entity_id=anna.id, data={"f1": "Анна Иванова", "f2": "3 года"},
                         submitted_at=now - timedelta(hours=1))
    lost = FormSubmission(form_id=form.id, entity_id=None, data={"f1": "Глеб Потерянный", "f2": "нет"},
                          submitted_at=now - timedelta(days=40))
    db_session.add_all([sub, lost])
    await db_session.commit()
    done = FormDispatch(form_id=form.id, entity_id=anna.id, token="tok-done-1", status="submitted",
                        submission_id=sub.id, created_by=admin_user.id, created_at=now - timedelta(days=1),
                        submitted_at=now - timedelta(hours=1))
    opened = FormDispatch(form_id=form.id, entity_id=boris.id, token="tok-open-1", status="opened",
                          created_by=admin_user.id, created_at=now - timedelta(days=2),
                          opened_at=now - timedelta(days=2))
    sent = FormDispatch(form_id=form.id, entity_id=vera.id, token="tok-sent-1", status="sent",
                        created_by=admin_user.id, created_at=now - timedelta(days=3))
    db_session.add_all([done, opened, sent])
    await db_session.commit()

    # Воронка, в которой только Борис, — для проверки скоупа.
    v = Vacancy(org_id=organization.id, department_id=department.id, created_by=admin_user.id, title="Трафик",
                status=VacancyStatus.open, salary_currency="RUB", created_at=now, updated_at=now)
    db_session.add(v)
    await db_session.commit()
    db_session.add(VacancyApplication(vacancy_id=v.id, entity_id=boris.id, stage=ApplicationStage.screening,
                                      stage_order=1, applied_at=now, last_stage_change_at=now, updated_at=now))
    await db_session.commit()
    return {"form": form, "anna": anna, "boris": boris, "vera": vera, "done": done, "opened": opened,
            "sent": sent, "lost": lost, "vacancy": v}


async def test_lists_everything_with_counts(client, board, admin_user, org_owner):
    r = await client.get("/api/form-answers", headers=_h(admin_user))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["counts"] == {"all": 4, "submitted": 1, "opened": 1, "sent": 1, "orphan": 1}
    by_status = {i["status"]: i for i in body["items"]}
    assert by_status["submitted"]["entity_name"] == "Анна Иванова"
    assert by_status["sent"]["token"] == "tok-sent-1"
    # Чей ответ без кандидата — по тому, что он вписал в «ФИО».
    assert by_status["orphan"]["hint"] == "Глеб Потерянный"
    assert body["can_attach"] is True
    assert body["forms"] == [{"id": board["form"].id, "title": "Вводная"}]


async def test_status_tab_does_not_change_counts(client, board, admin_user, org_owner):
    r = await client.get("/api/form-answers?status=orphan", headers=_h(admin_user))
    body = r.json()
    assert [i["status"] for i in body["items"]] == ["orphan"]
    assert body["counts"]["all"] == 4  # бейджи — по всем вкладкам, как в списке


async def test_search_and_period(client, board, admin_user, org_owner):
    r = await client.get("/api/form-answers?q=борис", headers=_h(admin_user))
    assert [i["entity_name"] for i in r.json()["items"]] == ["Борис Петров"]
    r = await client.get("/api/form-answers?q=глеб", headers=_h(admin_user))
    assert [i["status"] for i in r.json()["items"]] == ["orphan"]
    # За 30 дней ответа без кандидата (40 дней назад) нет — и в бейдже тоже.
    r = await client.get("/api/form-answers?days=30", headers=_h(admin_user))
    assert r.json()["counts"]["orphan"] == 0


async def test_member_without_hr_gets_403(client, board, second_user, org_member):
    r = await client.get("/api/form-answers", headers=_h(second_user))
    assert r.status_code == 403


async def test_scoped_recruiter_sees_only_own_funnel(client, db_session, board, recruiter):
    m = (await db_session.execute(select(OrgMember).where(OrgMember.user_id == recruiter.id))).scalar_one()
    m.scope_vacancy_ids = [board["vacancy"].id]
    await db_session.commit()
    r = await client.get("/api/form-answers", headers=_h(recruiter))
    body = r.json()
    assert [i["entity_name"] for i in body["items"]] == ["Борис Петров"]
    assert body["counts"]["orphan"] == 0  # чей ответ — неизвестно, скоупу не показываем
    assert body["can_attach"] is False
    r = await client.get(f"/api/form-answers/dispatch/{board['done'].id}", headers=_h(recruiter))
    assert r.status_code == 404
    r = await client.get(f"/api/form-answers/submission/{board['lost'].id}", headers=_h(recruiter))
    assert r.status_code == 404


async def test_other_org_is_hidden(client, db_session, board, second_organization, second_user):
    db_session.add(OrgMember(org_id=second_organization.id, user_id=second_user.id, role=OrgRole.owner))
    await db_session.commit()
    r = await client.get("/api/form-answers", headers=_h(second_user))
    assert r.json()["counts"]["all"] == 0
    r = await client.get(f"/api/form-answers/dispatch/{board['done'].id}", headers=_h(second_user))
    assert r.status_code == 404


async def test_answer_views(client, board, admin_user, org_owner):
    r = await client.get(f"/api/form-answers/dispatch/{board['done'].id}", headers=_h(admin_user))
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["answers"] == {"f1": "Анна Иванова", "f2": "3 года"}
    assert v["field_labels"]["f2"] == "Опыт"
    assert v["entity_name"] == "Анна Иванова"
    r = await client.get(f"/api/form-answers/submission/{board['lost'].id}", headers=_h(admin_user))
    assert r.status_code == 200, r.text
    assert r.json()["answers"]["f1"] == "Глеб Потерянный"
    assert r.json()["entity_id"] is None


async def test_attach_puts_answer_into_card(client, board, admin_user, org_owner, recruiter):
    lost, vera = board["lost"], board["vera"]
    r = await client.post(f"/api/form-answers/submission/{lost.id}/attach",
                          json={"entity_id": vera.id}, headers=_h(recruiter))
    assert r.status_code == 403  # привязывает только админ HR

    r = await client.post(f"/api/form-answers/submission/{lost.id}/attach",
                          json={"entity_id": vera.id}, headers=_h(admin_user))
    assert r.status_code == 200, r.text

    # Ответ виден во вкладке «Анкета» карточки, как обычная заполненная анкета.
    r = await client.get(f"/api/forms/entity/{vera.id}/all-dispatches", headers=_h(admin_user))
    filled = [d for d in r.json() if d["submission_id"] == lost.id]
    assert len(filled) == 1 and filled[0]["status"] == "submitted"
    assert filled[0]["answers"]["f1"] == "Глеб Потерянный"

    # А со страницы «без кандидата» он ушёл; второй раз привязать нельзя.
    r = await client.get("/api/form-answers?status=orphan", headers=_h(admin_user))
    assert r.json()["items"] == []
    r = await client.post(f"/api/form-answers/submission/{lost.id}/attach",
                          json={"entity_id": vera.id}, headers=_h(admin_user))
    assert r.status_code == 409


async def test_client_error_is_saved_and_shown(client, db_session, board, admin_user, org_owner):
    # Новая страница анкеты шлёт полный токен…
    r = await client.post("/api/forms/public/client-error", json={
        "link": "tok-op", "token": "tok-open-1", "kind": "network", "message": "Network Error", "online": False,
    })
    assert r.status_code == 204
    # …а открытая до деплоя — только начало ссылки.
    r = await client.post("/api/forms/public/client-error", json={"link": "tok-se", "kind": "server_status",
                                                                   "status": 502, "message": "Bad Gateway"})
    assert r.status_code == 204
    rows = (await db_session.execute(select(FormClientError))).scalars().all()
    assert {e.dispatch_id for e in rows} == {board["opened"].id, board["sent"].id}

    items = {i["status"]: i for i in (await client.get("/api/form-answers", headers=_h(admin_user))).json()["items"]}
    assert items["opened"]["error"]["kind"] == "network"
    assert items["sent"]["error"]["status"] == 502
    assert items["submitted"]["error"] is None


async def test_unknown_link_is_saved_without_dispatch(client, db_session, board):
    # Начало, которого нет ни у одной ссылки, и слишком короткое — не угадываем,
    # но отчёт сохраняем: по нему видно, что у кого-то не отправилось.
    for link in ("zzzzzz", "tok-"):
        r = await client.post("/api/forms/public/client-error", json={"link": link, "kind": "client"})
        assert r.status_code == 204
    rows = (await db_session.execute(select(FormClientError))).scalars().all()
    assert len(rows) == 2 and all(e.dispatch_id is None for e in rows)


def test_summarize_and_hint_are_pure():
    now = datetime(2026, 11, 6, 12, 0)
    items = [
        {"status": "sent", "created_at": "2026-11-05T10:00:00", "form_id": 1, "entity_name": "Ёлкина Анна"},
        {"status": "orphan", "submitted_at": "2026-09-01T10:00:00", "form_id": 1, "hint": "Глеб"},
    ]
    out = summarize(items, status=None, q="елкина", now=now)
    assert out["counts"]["all"] == 1 and out["items"][0]["entity_name"] == "Ёлкина Анна"
    out = summarize(items, status="sent", days=7, now=now)
    assert out["counts"] == {"submitted": 0, "opened": 0, "sent": 1, "orphan": 0, "all": 1}
    assert who_hint({"a": "Глеб", "b": "+375 29 1", "c": "x"},
                    [{"id": "a", "label": "Имя"}, {"id": "b", "label": "Телефон"}, {"id": "c", "label": "Опыт"}]) \
        == "Глеб · +375 29 1"
