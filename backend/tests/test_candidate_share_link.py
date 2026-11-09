"""Публичный предпросмотр кандидата (share-link, модуль 3)."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from api.models.database import (
    CandidateShareLink, Entity, EntityFile, EntityFileType,
    EntityType, EntityStatus,
)
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _mk_candidate(db, org, user) -> Entity:
    e = Entity(
        org_id=org.id, created_by=user.id, name="Пётр Кандидатов",
        type=EntityType.candidate, status=EntityStatus.new,
        phone="+79990001122", email="petr@example.com",
        position="QA engineer", company="ООО Тест",
        extra_data={
            "resume_text": "Опыт 5 лет, автотесты",
            "city": "Казань",
            "notes": [
                {"id": "n1", "text": "Хороший кандидат", "author_name": "Мария", "date": "2026-07-01"},
                {"id": "n2", "text": "", "author_name": "Мария"},  # пустой — не отдаём
            ],
        },
        created_at=datetime.utcnow(),
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


@pytest.mark.asyncio
async def test_create_and_read_share_link(
    client, db_session, organization, admin_user, org_owner
):
    cand = await _mk_candidate(db_session, organization, admin_user)
    r = await client.post(f"/api/entities/{cand.id}/share-link", headers=_h(admin_user))
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    assert r.json()["url_path"] == f"/candidate-preview/{token}"

    # Публичное чтение — БЕЗ заголовков авторизации
    pub = await client.get(f"/api/entities/public/candidate-preview/{token}")
    assert pub.status_code == 200, pub.text
    body = pub.json()
    assert body["name"] == "Пётр Кандидатов"
    assert body["phone"] == "+79990001122"
    assert body["city"] == "Казань"
    # Пустой комментарий отфильтрован, содержательный — в таймлайне
    assert [n["text"] for n in body["timeline"]] == ["Хороший кандидат"]
    assert body["files"] == []  # файлов нет
    assert body["resume_files"] == []
    assert body["stage_label"] is None  # заявок нет — этап не показываем


@pytest.mark.asyncio
async def test_public_files_preview(
    client, db_session, organization, admin_user, org_owner
):
    """Резюме-PDF отдаётся inline по токену; docx в предпросмотр не отдаём."""
    cand = await _mk_candidate(db_session, organization, admin_user)
    pdf = EntityFile(
        entity_id=cand.id, org_id=organization.id,
        file_type=EntityFileType.resume, file_name="resume.pdf",
        file_data=b"%PDF-1.4 fake", file_size=13, mime_type="application/pdf",
    )
    docx = EntityFile(
        entity_id=cand.id, org_id=organization.id,
        file_type=EntityFileType.other, file_name="offer.docx",
        file_data=b"PK fake docx", file_size=12,
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    db_session.add_all([pdf, docx])
    await db_session.commit()
    await db_session.refresh(pdf)
    await db_session.refresh(docx)

    r = await client.post(f"/api/entities/{cand.id}/share-link", headers=_h(admin_user))
    token = r.json()["token"]

    body = (await client.get(f"/api/entities/public/candidate-preview/{token}")).json()
    assert [f["id"] for f in body["resume_files"]] == [pdf.id]
    assert body["resume_files"][0]["previewable"] is True
    assert [f["name"] for f in body["files"]] == ["offer.docx"]
    assert body["files"][0]["previewable"] is False

    # PDF — inline по токену
    fr = await client.get(f"/api/entities/public/candidate-preview/{token}/files/{pdf.id}")
    assert fr.status_code == 200
    assert fr.headers["content-type"].startswith("application/pdf")
    assert fr.content == b"%PDF-1.4 fake"

    # docx публично не раздаём
    fr2 = await client.get(f"/api/entities/public/candidate-preview/{token}/files/{docx.id}")
    assert fr2.status_code == 403

    # чужой file_id (не этого кандидата) — 404
    fr3 = await client.get(f"/api/entities/public/candidate-preview/{token}/files/999999")
    assert fr3.status_code == 404


@pytest.mark.asyncio
async def test_unknown_token_404(client):
    r = await client.get("/api/entities/public/candidate-preview/nope-token")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_expired_token_410(
    client, db_session, organization, admin_user, org_owner
):
    cand = await _mk_candidate(db_session, organization, admin_user)
    r = await client.post(f"/api/entities/{cand.id}/share-link", headers=_h(admin_user))
    token = r.json()["token"]
    # Протухляем ссылку напрямую в БД
    link = (await db_session.execute(
        select(CandidateShareLink).where(CandidateShareLink.token == token)
    )).scalar_one()
    link.expires_at = datetime.utcnow() - timedelta(days=1)
    await db_session.commit()

    pub = await client.get(f"/api/entities/public/candidate-preview/{token}")
    assert pub.status_code == 410


# --- «Поделиться» наблюдателем и права ссылки (09.11.2026) --------------------

async def _vac(db, org, user, title):
    from api.models.database import Vacancy, VacancyStatus
    now = datetime.utcnow()
    v = Vacancy(org_id=org.id, created_by=user.id, title=title, status=VacancyStatus.open,
                salary_currency="RUB", created_at=now, updated_at=now, visible_to_all=True)
    db.add(v)
    await db.commit()
    return v


async def _app(db, vacancy, entity, user, stage, applied_at):
    from api.models.database import VacancyApplication
    a = VacancyApplication(vacancy_id=vacancy.id, entity_id=entity.id, stage=stage, stage_order=1,
                           created_by=user.id, applied_at=applied_at,
                           last_stage_change_at=applied_at, updated_at=applied_at)
    db.add(a)
    await db.commit()
    return a


@pytest.mark.asyncio
async def test_observer_shares_only_what_he_sees(
    client, db_session, organization, admin_user, org_owner, regular_user, org_admin,
):
    """Наблюдатель с «только Практика» делится практикантом: ссылка работает без
    входа, но чужой воронки (свежий отказ в «SEO», её комментарий) на ней нет.
    Кандидат ушёл с «Практики» — ссылка больше не открывается."""
    from api.models.database import ApplicationStage
    traffic = await _vac(db_session, organization, admin_user, "Трафик")
    seo = await _vac(db_session, organization, admin_user, "SEO")
    cand = await _mk_candidate(db_session, organization, admin_user)
    cand.status = EntityStatus.probation
    cand.extra_data = {**cand.extra_data, "notes": [
        {"id": "a", "text": "По трафику ок", "vacancy_id": traffic.id, "date": "2026-11-01"},
        {"id": "b", "text": "В SEO отказ", "vacancy_id": seo.id, "date": "2026-11-02"},
    ]}
    await db_session.commit()
    now = datetime.utcnow()
    await _app(db_session, traffic, cand, admin_user, ApplicationStage.probation, now - timedelta(days=5))
    await _app(db_session, seo, cand, admin_user, ApplicationStage.rejected, now)  # свежее
    org_admin.is_readonly = True
    org_admin.scope_statuses = ["probation"]
    await db_session.commit()

    r = await client.post(f"/api/entities/{cand.id}/share-link", headers=_h(regular_user))
    assert r.status_code == 200, r.text  # наблюдателю «Поделиться» доступна
    token = r.json()["token"]

    body = (await client.get(f"/api/entities/public/candidate-preview/{token}")).json()
    assert body["vacancy_title"] == "Трафик"
    assert body["stage"] == "probation"
    assert [t["text"] for t in body["timeline"] if t.get("text")] == ["По трафику ок"]

    # У админа без ограничений — вся картина, как и раньше.
    r = await client.post(f"/api/entities/{cand.id}/share-link", headers=_h(admin_user))
    full = (await client.get(f"/api/entities/public/candidate-preview/{r.json()['token']}")).json()
    assert full["vacancy_title"] == "SEO"

    # Кандидат ушёл с «Практики» — ссылка наблюдателя закрылась.
    cand.status = EntityStatus.transferred
    await db_session.commit()
    assert (await client.get(f"/api/entities/public/candidate-preview/{token}")).status_code == 404
    assert (await client.get(f"/api/entities/public/candidate-preview/{token}/photo")).status_code == 404


@pytest.mark.asyncio
async def test_observer_cannot_share_hidden_candidate(
    client, db_session, organization, admin_user, org_owner, regular_user, org_admin,
):
    cand = await _mk_candidate(db_session, organization, admin_user)  # статус «Новый»
    org_admin.is_readonly = True
    org_admin.scope_statuses = ["probation"]
    await db_session.commit()
    r = await client.post(f"/api/entities/{cand.id}/share-link", headers=_h(regular_user))
    assert r.status_code in (403, 404), r.text
