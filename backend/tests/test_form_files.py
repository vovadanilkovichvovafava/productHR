"""Публичный сабмит анкеты С ФАЙЛАМИ.

Гард на баг `entity_files.org_id` NOT NULL (сабмит с файлом падал 500) и на
поддержку файлов по ПЕРСОНАЛЬНОЙ ссылке (token submit-with-files) — файл
привязывается к существующему кандидату, нового entity не создаётся.
"""
import json
import pytest
from sqlalchemy import select

from api.models.database import (
    Entity, EntityType, EntityStatus, EntityFile, FormTemplate, Organization,
)
from api.services.auth import create_access_token


@pytest.fixture(autouse=True)
def no_resume_autopromote(monkeypatch):
    """Фоновое «PDF → вкладка Резюме» открывает своё соединение с базой и в
    тестах его не закрывает — pytest потом не завершается."""
    import api.services.resume_autopromote as ra

    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(ra, "promote_pdf_to_resume_if_needed", _noop)


def _h(user):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(user.id)})}"}


@pytest.mark.asyncio
async def test_slug_submit_no_longer_creates_candidate(client, db_session, organization: Organization, admin_user, org_owner):
    """Анонимный сабмит по публичному slug ОТКЛЮЧЁН: анкета заполняется только по
    персональной ссылке существующим кандидатом и НЕ плодит новых кандидатов."""
    H = _h(admin_user)
    r = await client.post("/api/forms", json={
        "title": "Публичная с файлом",
        "fields": [
            {"id": "name", "type": "text", "label": "ФИО", "required": True},
            {"id": "cv", "type": "file", "label": "Резюме"},
        ],
    }, headers=H)
    assert r.status_code == 200, r.text
    slug = (await db_session.execute(
        select(FormTemplate.slug).where(FormTemplate.id == r.json()["id"])
    )).scalar_one()

    before = len((await db_session.execute(select(Entity))).scalars().all())
    r = await client.post(
        f"/api/forms/public/{slug}/submit-with-files",
        data={"data": json.dumps({"name": "Иван", "cv": ""})},
        files={"files": ("portfolio.png", b"\x89PNG fake bytes", "image/png")},
    )
    assert r.status_code == 403, r.text
    after = len((await db_session.execute(select(Entity))).scalars().all())
    assert after == before  # новый кандидат НЕ создан


@pytest.mark.asyncio
async def test_token_submit_with_files_attaches_to_existing_candidate(client, db_session, organization: Organization, admin_user, org_owner):
    """Личная ссылка с файлом: файл и ответы привязаны к существующему кандидату."""
    cand = Entity(org_id=organization.id, type=EntityType.candidate, name="Файл Кандидатов", status=EntityStatus.new)
    db_session.add(cand)
    await db_session.commit()
    cand_id = cand.id
    H = _h(admin_user)

    r = await client.post("/api/forms", json={
        "title": "Личная с файлом",
        "fields": [
            {"id": "name", "type": "text", "label": "ФИО", "required": True},
            {"id": "cv", "type": "file", "label": "Резюме"},
        ],
    }, headers=H)
    assert r.status_code == 200, r.text
    form_id = r.json()["id"]
    r = await client.post(f"/api/forms/{form_id}/dispatch", json={"entity_id": cand_id}, headers=H)
    assert r.status_code == 200, r.text
    token = r.json()["token"]

    before = len((await db_session.execute(select(Entity))).scalars().all())
    r = await client.post(
        f"/api/forms/public/d/{token}/submit-with-files",
        data={"data": json.dumps({"name": "Файл Кандидатов", "cv": ""})},
        files={"files": ("portfolio.png", b"\x89PNG fake bytes", "image/png")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["files_saved"] == 1
    assert r.json()["entity_id"] == cand_id
    after = len((await db_session.execute(select(Entity))).scalars().all())
    assert after == before, "новый кандидат не должен создаваться — файл к существующему"

    efiles = (await db_session.execute(
        select(EntityFile).where(EntityFile.entity_id == cand_id)
    )).scalars().all()
    assert len(efiles) == 1
    assert efiles[0].org_id == organization.id
    # Содержимое сохранено в БД (bytea) — переживает эфемерный диск прода.
    assert efiles[0].file_data, "file_data должен храниться в БД"

    # Повторная отправка по той же ссылке — отклоняется (одна анкета = один ответ).
    r = await client.post(
        f"/api/forms/public/d/{token}/submit-with-files",
        data={"data": json.dumps({"name": "x"})},
        files={"files": ("a.png", b"x", "image/png")},
    )
    assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_anketa_file_link_in_dispatch_answers(client, db_session, organization: Organization, admin_user, org_owner):
    """Ответы анкеты отдают file_links для поля-файла → файл можно посмотреть."""
    cand = Entity(org_id=organization.id, type=EntityType.candidate, name="Файл Линк", status=EntityStatus.new)
    db_session.add(cand)
    await db_session.commit()
    cand_id = cand.id
    H = _h(admin_user)

    r = await client.post("/api/forms", json={
        "title": "С файлом",
        "fields": [
            {"id": "name", "type": "text", "label": "ФИО", "required": True},
            {"id": "cv", "type": "file", "label": "Файл"},
        ],
    }, headers=H)
    form_id = r.json()["id"]
    r = await client.post(f"/api/forms/{form_id}/dispatch", json={"entity_id": cand_id}, headers=H)
    token = r.json()["token"]
    # Имя файла записывается и в data поля-файла (как делает фронт).
    r = await client.post(
        f"/api/forms/public/d/{token}/submit-with-files",
        data={"data": json.dumps({"name": "Файл Линк", "cv": "portfolio.png"})},
        files={"files": ("portfolio.png", b"\x89PNG fake", "image/png")},
    )
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/forms/entity/{cand_id}/all-dispatches", headers=H)
    assert r.status_code == 200, r.text
    d = next(x for x in r.json() if x["status"] == "submitted")
    assert d["answers"]["cv"] == "portfolio.png"
    assert d["file_links"].get("cv", "").endswith("/download")

    # Публичный просмотр заполненной анкеты (по токену) тоже отдаёт file_links.
    r = await client.get(f"/api/forms/public/d/{token}")
    assert r.status_code == 200, r.text
    assert r.json()["file_links"].get("cv", "").endswith("/download")
