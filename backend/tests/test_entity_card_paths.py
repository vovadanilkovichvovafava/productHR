"""Карточка кандидата на сервере — одно место на правило (20.10.2026).

До разбора routes/entities/crud.py одно и то же жило копиями, и копии
разъехались:
* ответ собирался словарём в четырёх ручках, а фильтр скоупа по воронкам стоял
  только в GET — правка и создание отдавали заметки и метки чужих воронок;
* по WebSocket всей организации уходила карточка целиком (контакты, все
  комментарии) — и сотрудникам без HR-раздела;
* «сменить статус» было в двух ручках: песочница на практике и выход из архива
  срабатывали только в PATCH /status, а сохранение карточки их не делало;
* пять ручек ленты (комментарий, реакция, закреп, правка, удаление) и PATCH
  /status не проверяли скоуп: по номеру можно было писать чужому кандидату.
"""
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import (
    ApplicationStage, Department, Entity, EntityStatus, OrgMember, Organization,
    User, Vacancy, VacancyApplication, VacancyStatus,
)
from api.services.auth import create_access_token
from api.services.entity_card import entity_broadcast_payload
from tests.conftest import auth_headers


def _headers(user: User) -> dict:
    return auth_headers(create_access_token(data={"sub": str(user.id)}))


async def _vacancy(db, org, dept, user, title):
    now = datetime.utcnow()
    v = Vacancy(
        org_id=org.id, department_id=dept.id, created_by=user.id, title=title,
        status=VacancyStatus.open, salary_currency="RUB", created_at=now, updated_at=now,
    )
    db.add(v)
    await db.commit()
    return v


async def _application(db, vacancy, entity, user, stage=ApplicationStage.applied):
    now = datetime.utcnow()
    app = VacancyApplication(
        vacancy_id=vacancy.id, entity_id=entity.id, stage=stage, stage_order=1,
        created_by=user.id, applied_at=now, last_stage_change_at=now, updated_at=now,
    )
    db.add(app)
    await db.commit()
    return app


@pytest.fixture
def sandbox_calls(monkeypatch):
    """Кого и в какую воронку ставили в песочницу."""
    calls = []

    async def fake(db, entity_id, vacancy, org_id=None):
        calls.append((entity_id, getattr(vacancy, "id", None)))

    monkeypatch.setattr("api.services.board_placements.ensure_sandbox_placement", fake)
    return calls


@pytest.fixture
def broadcasts(monkeypatch):
    sent = []

    async def fake(org_id, payload, db=None):
        sent.append(payload)

    monkeypatch.setattr("api.routes.entities.crud.broadcast_entity_updated", fake)
    monkeypatch.setattr("api.routes.entities.crud.broadcast_entity_created", fake)
    return sent


# --- WebSocket ---------------------------------------------------------------

def test_broadcast_payload_has_no_contacts_or_notes():
    e = Entity(
        id=5, name="Иванова", phone="+79990000000", email="a@b.c",
        extra_data={"notes": [{"text": "секрет"}]}, version=3,
    )
    payload = entity_broadcast_payload(e)
    assert set(payload) == {"id", "type", "name", "status", "updated_at", "version"}
    assert payload["id"] == 5 and payload["version"] == 3


async def test_put_broadcasts_without_contacts(
    client: AsyncClient, admin_user: User, org_owner: OrgMember,
    candidate_entity: Entity, broadcasts,
):
    r = await client.put(
        f"/api/entities/{candidate_entity.id}",
        json={"position": "Медиабайер"},
        headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    assert broadcasts, "событие не ушло"
    assert "email" not in broadcasts[-1] and "extra_data" not in broadcasts[-1]


# --- Смена статуса: одно правило для PUT и PATCH -----------------------------

@pytest_asyncio.fixture
async def one_funnel(
    db_session: AsyncSession, organization: Organization, department: Department,
    admin_user: User, org_owner: OrgMember, candidate_entity: Entity,
):
    vac = await _vacancy(db_session, organization, department, admin_user, "Трафик")
    app = await _application(db_session, vac, candidate_entity, admin_user)
    candidate_entity.status = EntityStatus.new
    await db_session.commit()
    return candidate_entity, vac, app


@pytest.mark.parametrize("path", ["put", "patch"])
async def test_probation_places_into_sandbox_on_both_paths(
    client: AsyncClient, db_session: AsyncSession, admin_user: User, one_funnel,
    sandbox_calls, path,
):
    entity, vac, app = one_funnel
    if path == "put":
        r = await client.put(
            f"/api/entities/{entity.id}", json={"status": "probation"}, headers=_headers(admin_user),
        )
    else:
        r = await client.patch(
            f"/api/entities/{entity.id}/status", json={"status": "probation"}, headers=_headers(admin_user),
        )
    assert r.status_code == 200, r.text
    # Раньше сохранение карточки (PUT) песочницу не ставило вовсе.
    assert sandbox_calls == [(entity.id, vac.id)]
    await db_session.refresh(app)
    assert app.stage == ApplicationStage.probation


async def test_saving_archived_card_does_not_unarchive(
    client: AsyncClient, db_session: AsyncSession, admin_user: User, one_funnel,
):
    entity, _, _ = one_funnel
    entity.is_archived = True
    await db_session.commit()
    # Форма правки шлёт статус при каждом сохранении — это ещё не «вернуть в работу».
    r = await client.put(
        f"/api/entities/{entity.id}",
        json={"status": "new", "position": "QA"},
        headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    await db_session.refresh(entity)
    assert entity.is_archived is True
    # А настоящая смена статуса выводит из архива — как PATCH /status.
    r = await client.put(
        f"/api/entities/{entity.id}", json={"status": "screening"}, headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    await db_session.refresh(entity)
    assert entity.is_archived is False


# --- Скоуп по воронкам --------------------------------------------------------

@pytest_asyncio.fixture
async def scoped(
    db_session: AsyncSession, organization: Organization, department: Department,
    admin_user: User, org_owner: OrgMember, regular_user: User, org_admin: OrgMember,
    candidate_entity: Entity,
):
    """regular_user допущен только к «Трафику». Кандидат — в «Трафике» и в «SEO»,
    второй кандидат — только в «SEO»."""
    traffic = await _vacancy(db_session, organization, department, admin_user, "Трафик")
    seo = await _vacancy(db_session, organization, department, admin_user, "SEO")
    await _application(db_session, traffic, candidate_entity, admin_user)
    await _application(db_session, seo, candidate_entity, admin_user)
    candidate_entity.extra_data = {"notes": [
        {"id": "a", "text": "про трафик", "vacancy_id": traffic.id},
        {"id": "b", "text": "про SEO", "vacancy_id": seo.id},
    ]}
    foreign = Entity(
        org_id=organization.id, department_id=department.id, created_by=admin_user.id,
        name="Чужой Кандидат", type=candidate_entity.type, status=EntityStatus.new,
        created_at=datetime.utcnow(),
    )
    db_session.add(foreign)
    await db_session.commit()
    await _application(db_session, seo, foreign, admin_user)
    org_admin.scope_vacancy_ids = [traffic.id]
    await db_session.commit()
    return candidate_entity, foreign


async def test_put_response_hides_foreign_funnel_notes(
    client: AsyncClient, regular_user: User, scoped, broadcasts,
):
    entity, _ = scoped
    r = await client.put(
        f"/api/entities/{entity.id}", json={"position": "Медиабайер"}, headers=_headers(regular_user),
    )
    assert r.status_code == 200, r.text
    texts = [n["text"] for n in r.json()["extra_data"].get("notes", [])]
    assert texts == ["про трафик"]


@pytest.mark.parametrize(
    "method, suffix, body",
    [
        ("post", "/notes", {"text": "привет"}),
        ("post", "/timeline-reaction", {"entry_key": "created", "emoji": "👍"}),
        ("put", "/pin", {"entry_key": "created"}),
        ("patch", "/status", {"status": "screening"}),
    ],
)
async def test_foreign_candidate_timeline_and_status_are_404(
    client: AsyncClient, regular_user: User, scoped, method, suffix, body,
):
    _, foreign = scoped
    r = await getattr(client, method)(
        f"/api/entities/{foreign.id}{suffix}", json=body, headers=_headers(regular_user),
    )
    assert r.status_code == 404, r.text


async def test_own_scope_candidate_comment_still_works(
    client: AsyncClient, regular_user: User, scoped,
):
    entity, _ = scoped
    r = await client.post(
        f"/api/entities/{entity.id}/notes", json={"text": "созвон"}, headers=_headers(regular_user),
    )
    assert r.status_code == 200, r.text
