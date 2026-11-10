"""«Причина отказа» — из комментария при переводе в «Отказ» (владелец, 10.11.2026).

Комментарий из окна смены этапа — HTML редактора; в поле кладём простой текст.
Пишется в карточку (extra_data.rejection_reason) и в заявку (rejection_reason —
по нему отчёт «Причины отказов»).
"""
from tests.test_stage_change_paths import _headers, one_funnel  # noqa: F401

from api.models.database import EntityStatus
from api.services.stage_change import comment_plain_text


def test_comment_html_becomes_plain_text():
    assert comment_plain_text("<p>Не прошёл&nbsp;ТЗ</p><p>слабый <b>SQL</b></p>") == "Не прошёл ТЗ\nслабый SQL"
    assert comment_plain_text("строка<br>вторая") == "строка\nвторая"
    assert comment_plain_text("<p><br></p>") == ""
    assert comment_plain_text(None) == ""


async def test_rejection_comment_fills_reason(client, db_session, admin_user, one_funnel):  # noqa: F811
    entity, app = one_funnel
    r = await client.put(
        f"/api/vacancies/applications/{app.id}",
        json={"stage": "rejected", "comment": "<p>Не вышел на связь</p>", "expected_entity_id": entity.id},
        headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    await db_session.refresh(entity)
    await db_session.refresh(app)
    assert entity.extra_data["rejection_reason"] == "Не вышел на связь"
    assert app.rejection_reason == "Не вышел на связь"

    # Карточка отдаёт поле — фронту ничего дополнительно не нужно
    card = await client.get(f"/api/entities/{entity.id}", headers=_headers(admin_user))
    assert card.json()["extra_data"]["rejection_reason"] == "Не вышел на связь"


async def test_other_stage_comment_is_not_reason(client, db_session, admin_user, one_funnel):  # noqa: F811
    entity, app = one_funnel
    r = await client.put(
        f"/api/vacancies/applications/{app.id}",
        json={"stage": "screening", "comment": "ТЗ выдано", "expected_entity_id": entity.id},
        headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    await db_session.refresh(entity)
    assert "rejection_reason" not in (entity.extra_data or {})


async def test_out_of_funnel_rejection_fills_reason(client, db_session, admin_user, org_owner, candidate_entity):
    candidate_entity.status = EntityStatus.new
    await db_session.commit()
    r = await client.patch(
        f"/api/candidates/{candidate_entity.id}/status",
        json={"status": "rejected", "comment": "Ушёл в другую компанию", "stage_label": "Отказ"},
        headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    await db_session.refresh(candidate_entity)
    assert candidate_entity.extra_data["rejection_reason"] == "Ушёл в другую компанию"


async def test_reason_is_editable_by_hand(client, db_session, admin_user, one_funnel):  # noqa: F811
    entity, _app = one_funnel
    entity.extra_data = {**(entity.extra_data or {}), "rejection_reason": "старая"}
    await db_session.commit()
    r = await client.put(
        f"/api/entities/{entity.id}",
        json={"extra_data": {"rejection_reason": "уточнили: зарплата"}},
        headers=_headers(admin_user),
    )
    assert r.status_code == 200, r.text
    assert r.json()["extra_data"]["rejection_reason"] == "уточнили: зарплата"
