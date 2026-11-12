"""Значок вакансии в левой панели подбирает ИИ (12.11.2026).

Владелец: «я думал, он просто будет под все значки подбирать» — «Car»,
«SuperJet», «Суперкар» получали серую папку. Правила:
- значок — одно имя из списка vacancy_icon_names.txt (тот же — во фронте);
- считается один раз на название (`icon_for`), смена названия — пересчёт;
- форма, открытая до подбора, значок не стирает (серверные ключи);
- ошибка ИИ не портит вакансию, обходчик продолжит позже.
"""
from datetime import datetime

import pytest
from sqlalchemy import select

from api.models.database import Vacancy, VacancyStatus
from api.services import vacancy_icon as VI
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _vac(db, org, user, title, status=VacancyStatus.open, extra=None):
    now = datetime.utcnow()
    v = Vacancy(org_id=org.id, created_by=user.id, title=title, status=status, salary_currency="RUB",
                created_at=now, updated_at=now, visible_to_all=True, extra_data=extra or {})
    db.add(v)
    await db.commit()
    return v


async def _fresh(db, vid):
    return (await db.execute(
        select(Vacancy).where(Vacancy.id == vid).execution_options(populate_existing=True)
    )).scalar_one()


def test_list_is_loaded_and_answers_are_parsed():
    assert len(VI.ICON_NAMES) > 150
    assert {"car", "plane", "clapperboard", "target"} <= set(VI.ICON_NAMES)
    assert VI.parse_icon_answer("plane") == "plane"
    assert VI.parse_icon_answer("`car-front`.") == "car-front"
    assert VI.parse_icon_answer("Иконка: Plane") == "plane"
    assert VI.parse_icon_answer("нет подходящей") is None
    assert VI.parse_icon_answer("some-unknown-icon") is None


@pytest.mark.asyncio
async def test_apply_icons_fills_once_per_title(db_session, organization, admin_user):
    car = await _vac(db_session, organization, admin_user, "Car")
    jet = await _vac(db_session, organization, admin_user, "SuperJet")
    closed = await _vac(db_session, organization, admin_user, "Закрытая", status=VacancyStatus.closed)
    ids = (car.id, jet.id, closed.id)
    asked = []

    async def picker(title, dept):
        asked.append(title)
        return {"Car": "car", "SuperJet": "plane"}.get(title)

    assert await VI.apply_icons(db_session, picker) == 2
    assert sorted(asked) == ["Car", "SuperJet"]  # закрытые не трогаем
    car, jet, closed = [await _fresh(db_session, i) for i in ids]
    assert car.extra_data["icon"] == "car" and car.extra_data["icon_for"] == "Car"
    assert jet.extra_data["icon"] == "plane"
    assert "icon" not in (closed.extra_data or {})

    # Второй проход модель не зовёт — всё уже подобрано.
    asked.clear()
    assert await VI.apply_icons(db_session, picker) == 0 and asked == []

    # Переименовали — пересчёт.
    car.title = "SuperJet"
    await db_session.commit()
    assert await VI.apply_icons(db_session, picker) == 1 and asked == ["SuperJet"]
    assert (await _fresh(db_session, ids[0])).extra_data["icon"] == "plane"


@pytest.mark.asyncio
async def test_nothing_suitable_is_remembered_and_error_leaves_vacancy(db_session, organization, admin_user):
    v1 = await _vac(db_session, organization, admin_user, "Абракадабра")
    v1_id = v1.id

    async def none_picker(title, dept):
        return None

    assert await VI.apply_icons(db_session, none_picker) == 1
    fresh = await _fresh(db_session, v1_id)
    assert fresh.extra_data["icon"] == "" and fresh.extra_data["icon_for"] == "Абракадабра"

    v2 = await _vac(db_session, organization, admin_user, "Кондитер")
    v2_id = v2.id

    async def broken(title, dept):
        raise RuntimeError("credit balance is too low")

    with pytest.raises(RuntimeError):
        await VI.apply_icons(db_session, broken)
    assert "icon_for" not in ((await _fresh(db_session, v2_id)).extra_data or {})


@pytest.mark.asyncio
async def test_form_save_keeps_icon(client, db_session, organization, admin_user, org_owner):
    v = await _vac(db_session, organization, admin_user, "Car",
                   extra={"icon": "car", "icon_for": "Car", "positions_count": 1})
    # Форма открыта до подбора значка — шлёт extra_data без него.
    r = await client.put(f"/api/vacancies/{v.id}", json={"extra_data": {"positions_count": 2}},
                         headers=_h(admin_user))
    assert r.status_code == 200, r.text
    fresh = await _fresh(db_session, v.id)
    assert fresh.extra_data["icon"] == "car" and fresh.extra_data["positions_count"] == 2
