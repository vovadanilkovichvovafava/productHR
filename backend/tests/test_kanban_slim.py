"""Список «Все кандидаты» — без тяжёлых полей карточки (16.11.2026).

Владелец: «разберись со скоростью списка». На проде 250 строк весили 2,3 МБ
(539 КБ сжатыми), 91% — extra_data: анкеты прохождений ClickUp, текст резюме,
описания опыта, навыки. Строке они не нужны, открытая карточка перечитывает
кандидата целиком. Строка без них помечена list_slim — окно «Редактировать»
по метке дочитывает полную карточку (иначе стёрло бы навыки).
"""
from datetime import datetime

import pytest

from api.models.database import Entity, EntityStatus, EntityType
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


@pytest.mark.asyncio
async def test_list_row_is_slim_card_is_full(client, db_session, organization, admin_user, org_owner):
    heavy = {
        "participations": [{"vacancy_title": "Трафик", "anketa": [{"question": "q", "answer": "a" * 500}]}],
        "resume_text": "Резюме " * 300,
        "experience_descriptions": ["опыт " * 100],
        "skills": ["Python", "SQL"],
        "education": [{"name": "МГУ"}],
        "languages": ["en"],
        "experience_summary": "лет 5",
    }
    light = {"notes": [{"id": "n1", "text": "собес ок"}], "summary": "О себе", "city": "Минск"}
    e = Entity(org_id=organization.id, name="Тяжёлый Тест", type=EntityType.candidate,
               status=EntityStatus.new, created_by=admin_user.id, created_at=datetime.utcnow(),
               extra_data={**heavy, **light})
    plain = Entity(org_id=organization.id, name="Лёгкий Тест", type=EntityType.candidate,
                   status=EntityStatus.new, created_by=admin_user.id, created_at=datetime.utcnow(),
                   extra_data={"city": "Гомель"})
    db_session.add_all([e, plain])
    await db_session.commit()

    board = (await client.get("/api/candidates/kanban", headers=_h(admin_user))).json()
    cards = {c["name"]: c for col in board["columns"] for c in col["cards"]}
    row = cards["Тяжёлый Тест"]["extra_data"]
    assert not set(heavy) & set(row)                     # тяжёлого в строке нет
    assert row["list_slim"] is True
    assert row["notes"] == light["notes"] and row["summary"] == "О себе"  # лента и шапка — сразу
    assert cards["Тяжёлый Тест"]["city"] == "Минск"
    # Строка без тяжёлых полей — как была, без метки.
    assert "list_slim" not in (cards["Лёгкий Тест"]["extra_data"] or {})

    # Открытая карточка (GET) — целиком, без метки.
    full = (await client.get(f"/api/entities/{e.id}", headers=_h(admin_user))).json()["extra_data"]
    assert full["skills"] == ["Python", "SQL"] and full["resume_text"].startswith("Резюме")
    assert "list_slim" not in full
