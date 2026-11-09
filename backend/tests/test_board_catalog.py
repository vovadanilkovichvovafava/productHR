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
