"""Окно «Редактировать» стирает поле, которое очистили (05.11.2026).

Пустое поле раньше не присылалось вовсе, а PUT /entities дописывает правку к
старому — «стираю текст резюме целиком, пишет „обновлён“, а текст на месте».
Теперь очищенное поле приходит как null: в extra_data ключ убирается, обычное
поле карточки становится пустым. Не присланное по-прежнему не трогается.
"""
import pytest


@pytest.mark.asyncio
async def test_null_clears_fields_and_missing_keys_stay(
    client, admin_token, organization, department, get_auth_headers, org_owner
):
    h = get_auth_headers(admin_token)
    created = await client.post(
        "/api/entities",
        json={
            "type": "candidate",
            "name": "Пищ Павел Сергеевич",
            "phone": "+375333769944",
            "position": "Маркетолог",
            "extra_data": {
                "resume_text": "РЕЗЮМЕ | РЕЗЮМЕ | РЕЗЮМЕ",
                "city": "Минск",
                "skills": ["Маркетинг"],
            },
        },
        headers=h,
    )
    assert created.status_code == 201, created.text
    eid = created.json()["id"]

    r = await client.put(
        f"/api/entities/{eid}",
        json={
            "position": None,
            "extra_data": {"resume_text": None, "city": "Гродно"},
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    extra = body["extra_data"]
    assert "resume_text" not in extra  # стёрто
    assert extra["city"] == "Гродно"  # поправлено
    assert extra["skills"] == ["Маркетинг"]  # не присылали — осталось
    assert body["position"] is None
    assert body["phone"] == "+375333769944"

    again = (await client.get(f"/api/entities/{eid}", headers=h)).json()
    assert "resume_text" not in again["extra_data"]
