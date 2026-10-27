"""«Анкеты»: исправления полного прохода 20.10.2026.

Проверка анкеты, приём ответа кандидата (один путь для JSON и файлов),
снимок вопросов, защита удаления, доступ ИИ-чата, «Открыта» только кандидатом.
"""
import json
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import select

from api.models.database import (
    Entity, EntityFile, EntityStatus, EntityType, FormDispatch, FormSubmission, FormTemplate,
    OrgMember, OrgRole, User, Vacancy, VacancyStatus,
)
from api.services.auth import create_access_token, hash_password
from api.services.form_answers import AnswerError, clean_answers, form_problem, required_problem


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


FIELDS = [
    {"id": "name", "type": "text", "label": "ФИО", "required": True},
    {"id": "langs", "type": "multiselect", "label": "Языки", "required": True, "options": ["Python", "Go"]},
    {"id": "eng", "type": "scale", "label": "Английский", "required": False, "min": 1, "max": 5},
    {"id": "cv", "type": "file", "label": "Резюме", "required": True},
]


# --- чистые функции ---------------------------------------------------------

def test_form_problem_catches_what_candidate_would_get_stuck_on():
    assert form_problem("", FIELDS) == "У анкеты нет названия"
    assert form_problem("А", []) == "В анкете нет ни одного вопроса"
    assert "два разных варианта" in form_problem("А", [
        {"id": "r", "type": "radio", "label": "Выбор", "options": ["Да", " да ", ""]}])
    assert "меньше максимума" in form_problem("А", [
        {"id": "s", "type": "scale", "label": "Шкала", "min": 12, "max": 10}])
    assert "не больше 20" in form_problem("А", [
        {"id": "s", "type": "scale", "label": "Шкала", "min": 0, "max": 100}])
    assert form_problem("Анкета", FIELDS) is None


def test_clean_answers_keeps_only_known_questions_of_right_type():
    out = clean_answers(FIELDS, {"name": "  Иван  ", "langs": "Go", "eng": "4", "evil": "x" * 10})
    assert out == {"name": "Иван", "langs": ["Go"], "eng": 4}
    with pytest.raises(AnswerError):
        clean_answers(FIELDS, ["not", "a", "dict"])
    with pytest.raises(AnswerError):
        clean_answers(FIELDS, {"eng": 9})


def test_required_file_counts_only_if_file_arrived():
    answers = {"name": "Иван", "langs": ["Go"], "cv": "cv.pdf"}
    assert "Прикрепите файл" in required_problem(FIELDS, answers, uploaded_names=[])
    assert required_problem(FIELDS, answers, uploaded_names=["cv.pdf"]) is None
    assert "Языки" in required_problem(FIELDS, {**answers, "langs": []}, ["cv.pdf"])
    assert "ФИО" in required_problem(FIELDS, {**answers, "name": ""}, ["cv.pdf"])


# --- ручки ---------------------------------------------------------------------

@pytest.fixture(autouse=True)
def no_resume_autopromote(monkeypatch):
    """Фоновое «PDF → вкладка Резюме» открывает своё соединение с базой и в
    тестах его не закрывает — pytest потом не завершается."""
    import api.services.resume_autopromote as ra

    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(ra, "promote_pdf_to_resume_if_needed", _noop)


@pytest_asyncio.fixture
async def setup(db_session, organization, admin_user, org_owner):
    hr = User(email="hr-forms@test.local", password_hash=hash_password("x"), name="Рекрутёр", is_active=True)
    db_session.add(hr)
    await db_session.flush()
    db_session.add(OrgMember(org_id=organization.id, user_id=hr.id, role=OrgRole.hr))
    form = FormTemplate(org_id=organization.id, created_by=admin_user.id, title="Анкета",
                        slug="anketa-rev", fields=FIELDS, is_template=True, is_active=True)
    cand = Entity(org_id=organization.id, type=EntityType.candidate, name="Кандидат",
                  status=EntityStatus.new, created_by=admin_user.id)
    db_session.add_all([form, cand])
    await db_session.flush()
    disp = FormDispatch(form_id=form.id, entity_id=cand.id, token="tok-rev", created_by=admin_user.id)
    db_session.add(disp)
    await db_session.commit()
    for o in (hr, form, cand, disp, admin_user):
        await db_session.refresh(o)
    return {"hr": hr, "owner": admin_user, "form_id": form.id, "cand_id": cand.id, "disp_id": disp.id}


GOOD = {"name": "Иван", "langs": ["Python"], "eng": 3, "cv": "cv.pdf"}


async def _submit_with_file(client, token="tok-rev", data=GOOD):
    return await client.post(
        f"/api/forms/public/d/{token}/submit-with-files",
        data={"data": json.dumps(data)},
        files=[("files", ("cv.pdf", b"%PDF-1.4 test", "application/pdf"))],
    )


async def test_required_file_cannot_be_faked_by_name(client, setup):
    r = await client.post("/api/forms/public/d/tok-rev/submit", json={"data": GOOD})
    assert r.status_code == 422 and "Прикрепите файл" in r.json()["detail"]


async def test_list_instead_of_answers_is_422_not_500(client, setup):
    r = await client.post("/api/forms/public/d/tok-rev/submit-with-files", data={"data": "[]"})
    assert r.status_code == 422, r.text


async def test_submit_with_file_stores_answer_snapshot_and_file(client, db_session, setup):
    r = await _submit_with_file(client)
    assert r.status_code == 200, r.text
    sub = (await db_session.execute(
        select(FormSubmission).where(FormSubmission.dispatch_id == setup["disp_id"])
    )).scalar_one()
    assert sub.data == GOOD
    assert [f["id"] for f in sub.fields_snapshot] == ["name", "langs", "eng", "cv"]
    files = (await db_session.execute(
        select(EntityFile.file_name).where(EntityFile.entity_id == setup["cand_id"])
    )).scalars().all()
    assert "cv.pdf" in files
    # Второе «Отправить» — 409, второго ответа нет.
    r = await _submit_with_file(client)
    assert r.status_code == 409


async def test_old_answers_keep_their_questions_after_template_edit(client, db_session, setup):
    assert (await _submit_with_file(client)).status_code == 200
    H = _h(setup["owner"])
    new_fields = [{"id": "name", "type": "text", "label": "Имя и фамилия", "required": True}]
    r = await client.put(f"/api/forms/{setup['form_id']}", json={"fields": new_fields}, headers=H)
    assert r.status_code == 200, r.text
    rows = (await client.get(f"/api/forms/entity/{setup['cand_id']}/all-dispatches", headers=H)).json()
    labels = rows[0]["field_labels"]
    assert labels["name"] == "ФИО" and labels["langs"] == "Языки"
    assert rows[0]["file_links"]["cv"].startswith(f"/api/entities/{setup['cand_id']}/files/")


async def test_form_with_answers_cannot_be_deleted(client, setup):
    assert (await _submit_with_file(client)).status_code == 200
    r = await client.delete(f"/api/forms/{setup['form_id']}", headers=_h(setup["owner"]))
    assert r.status_code == 409


async def test_only_author_or_admin_deletes_form(client, setup):
    r = await client.delete(f"/api/forms/{setup['form_id']}", headers=_h(setup["hr"]))
    assert r.status_code == 403
    r = await client.delete(f"/api/forms/{setup['form_id']}", headers=_h(setup["owner"]))
    assert r.status_code == 200


async def test_inactive_or_broken_form_is_not_dispatched(client, db_session, setup):
    H = _h(setup["owner"])
    await client.put(f"/api/forms/{setup['form_id']}", json={"is_active": False}, headers=H)
    r = await client.post(f"/api/forms/{setup['form_id']}/dispatch", json={"entity_id": setup["cand_id"]}, headers=H)
    assert r.status_code == 400 and "выключена" in r.json()["detail"]
    await client.put(f"/api/forms/{setup['form_id']}", json={
        "is_active": True,
        "fields": [{"id": "s", "type": "scale", "label": "Шкала", "min": 12, "max": 10}],
    }, headers=H)
    r = await client.post(f"/api/forms/{setup['form_id']}/dispatch", json={"entity_id": setup["cand_id"]}, headers=H)
    assert r.status_code == 400 and "нельзя отправить" in r.json()["detail"]


async def test_submitted_link_opens_after_form_deactivated(client, setup):
    assert (await _submit_with_file(client)).status_code == 200
    await client.put(f"/api/forms/{setup['form_id']}", json={"is_active": False}, headers=_h(setup["owner"]))
    r = await client.get("/api/forms/public/d/tok-rev")
    assert r.status_code == 200 and r.json()["already_submitted"] is True


async def test_recruiter_opening_link_does_not_mark_it_opened(client, db_session, setup):
    r = await client.get("/api/forms/public/d/tok-rev", headers=_h(setup["hr"]))
    assert r.status_code == 200
    d = await db_session.get(FormDispatch, setup["disp_id"], populate_existing=True)
    assert d.status == "sent"
    r = await client.get("/api/forms/public/d/tok-rev")  # кандидат, без входа
    d = await db_session.get(FormDispatch, setup["disp_id"], populate_existing=True)
    assert d.status == "opened"


async def test_ai_chat_refuses_candidate_of_other_org(client, db_session, setup, second_organization):
    stranger = Entity(org_id=second_organization.id, type=EntityType.candidate, name="Чужой",
                      status=EntityStatus.new)
    db_session.add(stranger)
    await db_session.commit()
    await db_session.refresh(stranger)
    r = await client.post("/api/forms/ai-chat", json={"entity_id": stranger.id, "messages": []},
                          headers=_h(setup["hr"]))
    assert r.status_code in (403, 404), r.text


async def test_foreign_vacancy_ids_are_dropped(client, db_session, setup, second_organization):
    alien = Vacancy(org_id=second_organization.id, title="Чужая", status=VacancyStatus.open, salary_currency="RUB")
    db_session.add(alien)
    await db_session.commit()
    await db_session.refresh(alien)
    r = await client.post("/api/forms", json={"title": "Новая", "vacancy_ids": [alien.id, 999999], "fields": []},
                          headers=_h(setup["owner"]))
    assert r.status_code == 200, r.text
    assert r.json()["vacancy_ids"] == []
