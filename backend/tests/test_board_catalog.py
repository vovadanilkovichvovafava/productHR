"""Справочник отделов и должностей доски «Штат» (владелец, 09.11.2026).

Отделы и должности — только из списка владельца. Похожие старые отделы
переименовываются (люди остаются на месте), непохожие остаются, но в списке
перевода их нет.
"""
import pytest
from sqlalchemy import select

from api.models.database import BoardDepartment, BoardPlacement, Entity, EntityStatus, EntityType
from api.services import board_catalog as bc
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


@pytest.mark.parametrize("name, canon", [
    ("Facebook", "Facebook team"),
    ("FB", "Facebook team"),
    ("facebook team", "Facebook team"),
    ("SEO", "SEO team"),
    ("Google", "Google Ads team"),
    ("Google Ads", "Google Ads team"),
    ("Продукт", "Product Studio"),
    ("BizDev", "BizDev team"),
    ("HR", "HR team"),
    ("Product Studio (Марк)", "Product Studio"),
    ("SEO team (старый)", "SEO team"),
])
def test_similar_names_map_to_canon(name, canon):
    assert bc.CANON_TEAMS[bc.canon_index(name)][0] == canon


@pytest.mark.parametrize("name", ["iOS Product", "ASA", "TikTok", "SANDBOX", ""])
def test_other_names_are_not_canon(name):
    assert bc.canon_index(name) is None
    assert bc.positions_for(name) == []


def test_positions_belong_to_their_team():
    assert bc.positions_for("Push team") == ["Push Media Buyer Team Lead", "Push Media Buyer"]
    assert "Talent Sourcer" in bc.positions_for("HR")


@pytest.mark.asyncio
async def test_canon_migration_renames_creates_and_keeps(db_session, organization, admin_user):
    sandbox = BoardDepartment(org_id=organization.id, name="SANDBOX", kind="sandbox")
    fb = BoardDepartment(org_id=organization.id, name="Facebook", kind="team")
    fb2 = BoardDepartment(org_id=organization.id, name="FB", kind="team")
    ios = BoardDepartment(org_id=organization.id, name="iOS Product", kind="team")
    db_session.add_all([sandbox, fb, fb2, ios])
    await db_session.commit()
    e = Entity(org_id=organization.id, name="Ротный Иван", type=EntityType.candidate,
               status=EntityStatus.transferred, created_by=admin_user.id, extra_data={})
    db_session.add(e)
    await db_session.commit()
    db_session.add(BoardPlacement(org_id=organization.id, entity_id=e.id, department_id=fb.id, extra={}))
    await db_session.commit()

    await bc.canonize_board_departments_once(db_session)
    await bc.canonize_board_departments_once(db_session)   # второй раз — ничего

    names = {d.id: d.name for d in (await db_session.execute(
        select(BoardDepartment).where(BoardDepartment.org_id == organization.id)
    )).scalars().all()}
    # Похожий — переименован, человек остался в нём же
    assert names[fb.id] == "Facebook team"
    # Второй похожий не тронут — людей из него переносят руками
    assert names[fb2.id] == "FB"
    # Непохожий и песочница — как были
    assert names[ios.id] == "iOS Product" and names[sandbox.id] == "SANDBOX"
    # Недостающие из списка созданы, и ровно по одному
    for canon, _a, _p in bc.CANON_TEAMS:
        assert list(names.values()).count(canon) == 1, canon
    pl = (await db_session.execute(select(BoardPlacement))).scalars().one()
    assert pl.department_id == fb.id


@pytest.mark.asyncio
async def test_departments_carry_positions(client, admin_user, organization, org_owner):
    for name, kind in [("SEO team", "team"), ("ASA", "team"), ("SANDBOX", "sandbox")]:
        r = await client.post("/api/staff-board/departments", json={"name": name, "kind": kind},
                              headers=_h(admin_user))
        assert r.status_code == 201, r.text
    r = await client.get("/api/staff-board/departments", headers=_h(admin_user))
    by = {d["name"]: d for d in r.json()}
    assert by["SEO team"]["canonical"] is True and by["SEO team"]["canon_order"] == 0
    assert by["SEO team"]["positions"][0] == "SEO Buyer Team Lead"
    assert by["ASA"]["canonical"] is False and by["ASA"]["positions"] == []
    assert by["SANDBOX"]["canonical"] is False


@pytest.mark.asyncio
async def test_own_department_is_offered_editable_and_deletable_when_empty(
    client, db_session, admin_user, organization, org_owner
):
    """Свой отдел из окна выбора (клиент, 11.11.2026): предлагается, правится,
    удаляется только пустым. С единой логикой списков то же и у отделов из
    основного списка; песочница не удаляется."""
    h = _h(admin_user)
    own = (await client.post("/api/staff-board/departments", json={"name": "Фин отдел"}, headers=h)).json()
    canon = (await client.post("/api/staff-board/departments", json={"name": "SEO team"}, headers=h)).json()
    old = BoardDepartment(org_id=organization.id, name="Фарм отдел", kind="team")
    db_session.add(old)
    await db_session.commit()

    by = {d["name"]: d for d in (await client.get("/api/staff-board/departments", headers=h)).json()}
    assert by["Фин отдел"]["offered"] is True and by["Фин отдел"]["canonical"] is False
    assert by["SEO team"]["offered"] is True
    assert by["Фарм отдел"]["offered"] is False   # старый — не предлагается

    # Старый отдел добавили заново через окно — теперь свой, предлагается
    again = (await client.post("/api/staff-board/departments", json={"name": "фарм отдел"}, headers=h)).json()
    assert again["id"] == old.id and again["offered"] is True

    r = await client.patch(f"/api/staff-board/departments/{own['id']}", json={"name": "Финансы"}, headers=h)
    assert r.status_code == 200 and r.json()["name"] == "Финансы" and r.json()["offered"] is True
    r = await client.patch(f"/api/staff-board/departments/{canon['id']}", json={"name": "Сеошники"}, headers=h)
    assert r.status_code == 200 and r.json()["offered"] is True   # по id, не по названию

    e = Entity(org_id=organization.id, name="Финансист", type=EntityType.candidate,
               status=EntityStatus.transferred, created_by=admin_user.id, extra_data={})
    db_session.add(e)
    await db_session.commit()
    db_session.add(BoardPlacement(org_id=organization.id, entity_id=e.id, department_id=own["id"], extra={}))
    await db_session.commit()
    assert (await client.delete(f"/api/staff-board/departments/{own['id']}", headers=h)).status_code == 409
    sandbox = (await client.post("/api/staff-board/departments", json={"name": "SANDBOX", "kind": "sandbox"}, headers=h)).json()
    assert (await client.delete(f"/api/staff-board/departments/{sandbox['id']}", headers=h)).status_code == 409
    assert (await client.delete(f"/api/staff-board/departments/{canon['id']}", headers=h)).status_code == 200

    empty = (await client.post("/api/staff-board/departments", json={"name": "Support отдел"}, headers=h)).json()
    assert (await client.delete(f"/api/staff-board/departments/{empty['id']}", headers=h)).status_code == 200
    names = {d["name"] for d in (await client.get("/api/staff-board/departments", headers=h)).json()}
    assert "Support отдел" not in names


@pytest.mark.asyncio
async def test_position_catalog_add_rename_delete(client, db_session, admin_user, organization, org_owner):
    """Один общий список должностей: из списка владельца + свои (11.11.2026)."""
    h = _h(admin_user)
    cat = (await client.get("/api/staff-board/catalog/positions", headers=h)).json()
    # основа засеяна в список организации и правится как своё (11.11.2026)
    assert cat[0] == {"name": "SEO Buyer Team Lead", "locked": False, "count": 0}

    cat = (await client.post("/api/staff-board/catalog/positions", json={"name": "  Финансист "}, headers=h)).json()
    assert {"name": "Финансист", "locked": False, "count": 0} in cat
    # повтор без учёта регистра — не дублируется
    cat = (await client.post("/api/staff-board/catalog/positions", json={"name": "финансист"}, headers=h)).json()
    assert [p["name"] for p in cat].count("Финансист") == 1

    e = Entity(org_id=organization.id, name="Сотрудник Фин", type=EntityType.candidate,
               status=EntityStatus.transferred, created_by=admin_user.id, extra_data={},
               position="Финансист")
    db_session.add(e)
    await db_session.commit()

    r = await client.request("DELETE", "/api/staff-board/catalog/positions", params={"name": "Финансист"}, headers=h)
    assert r.status_code == 409   # стоит у человека
    r = await client.patch("/api/staff-board/catalog/positions",
                           json={"name": "Финансист", "new_name": "Финансовый аналитик"}, headers=h)
    assert r.status_code == 200
    await db_session.refresh(e)
    assert e.position == "Финансовый аналитик"   # переименование доходит до людей
    r = await client.patch("/api/staff-board/catalog/positions",
                           json={"name": "SEO Buyer", "new_name": "Сеошник"}, headers=h)
    assert r.status_code == 200 and "Сеошник" in [p["name"] for p in r.json()]

    await client.post("/api/staff-board/catalog/positions", json={"name": "Курьер"}, headers=h)
    r = await client.request("DELETE", "/api/staff-board/catalog/positions", params={"name": "Курьер"}, headers=h)
    assert r.status_code == 200 and "Курьер" not in [p["name"] for p in r.json()]


@pytest.mark.asyncio
async def test_manager_and_marks_catalogs(client, db_session, admin_user, organization, org_owner):
    """«Рук-ль» и отметки у вех — те же окна (клиент, 11.11.2026: «логика у всех
    дропдаунов одна»). Уже вписанное у людей тоже в списке — его можно выбрать
    снова и переименовать у всех разом."""
    h = _h(admin_user)
    e = Entity(org_id=organization.id, name="Практикант Рук", type=EntityType.candidate,
               status=EntityStatus.probation, created_by=admin_user.id,
               extra_data={"manager_name": "Влад", "m1_done": "Сентябрь"})
    db_session.add(e)
    await db_session.commit()

    managers = (await client.get("/api/staff-board/catalog/managers", headers=h)).json()
    assert {"name": "Влад", "locked": False, "count": 1} in managers
    managers = (await client.post("/api/staff-board/catalog/managers", json={"name": "Вова"}, headers=h)).json()
    assert "Вова" in [m["name"] for m in managers]

    # Выбор в ячейке главнее тега и сохраняется даже пустым
    r = await client.patch(f"/api/staff-board/rows/{e.id}", json={"manager": "Вова"}, headers=h)
    assert r.json()["manager"] == "Вова"
    r = await client.patch(f"/api/staff-board/rows/{e.id}", json={"manager": None}, headers=h)
    assert r.json()["manager"] is None

    r = await client.patch(f"/api/staff-board/rows/{e.id}", json={"manager": "Влад"}, headers=h)
    r = await client.patch("/api/staff-board/catalog/managers",
                           json={"name": "Влад", "new_name": "Владислав"}, headers=h)
    assert r.status_code == 200
    await db_session.refresh(e)
    assert e.extra_data["board_manager"] == "Владислав" and e.extra_data["manager_name"] == "Владислав"

    marks = (await client.get("/api/staff-board/catalog/marks", headers=h)).json()
    assert marks[0] == {"name": "✓", "locked": True, "count": 0}
    assert {"name": "Сентябрь", "locked": False, "count": 1} in marks
    marks = (await client.post("/api/staff-board/catalog/marks", json={"name": "Премия"}, headers=h)).json()
    r = await client.patch(f"/api/staff-board/rows/{e.id}", json={"m3_done": "Премия"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["m3_done"] == "Премия"
    r = await client.request("DELETE", "/api/staff-board/catalog/marks", params={"name": "Премия"}, headers=h)
    assert r.status_code == 409
    assert (await client.get("/api/staff-board/catalog/nope", headers=h)).status_code == 404



@pytest.mark.asyncio
async def test_dropdown_meta_colors_order_and_rename(client, db_session, admin_user, organization, org_owner):
    """Цвет и порядок пунктов — одно хранилище на все списки; переименование
    переносит цвет."""
    h = _h(admin_user)
    r = await client.put("/api/staff-board/dropdown-meta/positions",
                         json={"order": ["SEO Buyer", "UA Manager"], "colors": {"SEO Buyer": "#22c55e"}}, headers=h)
    assert r.status_code == 200
    assert r.json()["positions"] == {"order": ["SEO Buyer", "UA Manager"], "colors": {"SEO Buyer": "#22c55e"}}
    assert (await client.put("/api/staff-board/dropdown-meta/positions", json={"colors": {"x": "red"}}, headers=h)).status_code == 400
    assert (await client.put("/api/staff-board/dropdown-meta/nope", json={"order": []}, headers=h)).status_code == 404
    await client.patch("/api/staff-board/catalog/positions", json={"name": "SEO Buyer", "new_name": "SEO Баер"}, headers=h)
    meta = (await client.get("/api/staff-board/dropdown-meta", headers=h)).json()
    assert meta["positions"]["colors"] == {"SEO Баер": "#22c55e"}
    assert meta["positions"]["order"][0] == "SEO Баер"
    r = await client.put("/api/staff-board/dropdown-meta/positions", json={"colors": {"SEO Баер": None}}, headers=h)
    assert r.json()["positions"]["colors"] == {}


@pytest.mark.asyncio
async def test_deleted_item_forgets_color_and_place(client, db_session, admin_user, organization, org_owner):
    """Удалили пункт — его цвет и место тоже уходят: добавленный заново с тем
    же названием начинает с чистого листа."""
    h = _h(admin_user)
    assert (await client.post("/api/staff-board/catalog/managers", json={"name": "Олег"}, headers=h)).status_code in (200, 201)
    await client.put("/api/staff-board/dropdown-meta/managers",
                     json={"order": ["Олег"], "colors": {"Олег": "#22c55e"}}, headers=h)
    r = await client.delete("/api/staff-board/catalog/managers", params={"name": "Олег"}, headers=h)
    assert r.status_code == 200
    meta = (await client.get("/api/staff-board/dropdown-meta", headers=h)).json()
    assert meta["managers"] == {"order": [], "colors": {}}

    fields = (await client.post("/api/staff-board/custom-fields", json={"name": "Грейд", "type": "select"}, headers=h)).json()
    fid = next(f["id"] for f in fields if f["name"] == "Грейд")
    await client.patch(f"/api/staff-board/custom-fields/{fid}", json={"options": ["Junior", "Senior"]}, headers=h)
    await client.put(f"/api/staff-board/dropdown-meta/cf:{fid}",
                     json={"order": ["Senior", "Junior"], "colors": {"Junior": "#2563eb"}}, headers=h)
    await client.patch(f"/api/staff-board/custom-fields/{fid}", json={"options": ["Senior"]}, headers=h)
    meta = (await client.get("/api/staff-board/dropdown-meta", headers=h)).json()
    assert meta[f"cf:{fid}"] == {"order": ["Senior"], "colors": {}}
    await client.delete(f"/api/staff-board/custom-fields/{fid}", headers=h)
    meta = (await client.get("/api/staff-board/dropdown-meta", headers=h)).json()
    assert f"cf:{fid}" not in meta


@pytest.mark.asyncio
async def test_sourcer_tag_can_be_renamed(client, db_session, admin_user, organization, org_owner):
    h = _h(admin_user)
    a = (await client.post("/api/tags", json={"name": "Лиза", "color": "#ef4444"}, headers=h)).json()
    await client.post("/api/tags", json={"name": "Катя", "color": "#f59e0b"}, headers=h)
    r = await client.patch(f"/api/tags/{a['id']}", json={"name": "Елизавета"}, headers=h)
    assert r.status_code == 200 and r.json()["name"] == "Елизавета"
    assert (await client.patch(f"/api/tags/{a['id']}", json={"name": "катя"}, headers=h)).status_code == 409
