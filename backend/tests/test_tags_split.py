"""Теги у ФИО отдельно от меток; метки — только сорсеры (21.09.2026).

Данные — копия прод-меток на 21.09: имена (Валя, Влад, Егор…), слова
(перформер, продуктивный, опечатки), часть висит «у имени» (show_at_name).
"""
from datetime import datetime

import pytest
from sqlalchemy import select

from api.models.database import (
    DataMigrationMark, Entity, EntityStatus, EntityTag, EntityType, NameTag,
    entity_name_tag_association, entity_tag_association,
)
from api.services.auth import create_access_token
from api.services.tags_split import WORDS_MARK, split_tags_and_labels


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _cand(db, org, name):
    e = Entity(org_id=org.id, name=name, type=EntityType.candidate,
               status=EntityStatus.new, created_at=datetime.utcnow())
    db.add(e)
    await db.flush()
    return e


async def _label(db, org, name, kind="general", archived=False):
    t = EntityTag(org_id=org.id, name=name, color="var(--hf-red-500)", kind=kind,
                  archived_at=datetime.utcnow() if archived else None)
    db.add(t)
    await db.flush()
    return t


async def _link(db, entity, tag, at_name=False):
    await db.execute(entity_tag_association.insert().values(
        entity_id=entity.id, tag_id=tag.id, show_at_name=at_name))


async def _labels_of(db, entity):
    return set((await db.execute(
        select(EntityTag.name)
        .join(entity_tag_association, EntityTag.id == entity_tag_association.c.tag_id)
        .where(entity_tag_association.c.entity_id == entity.id)
    )).scalars().all())


async def _name_tags_of(db, entity):
    return set((await db.execute(
        select(NameTag.name)
        .join(entity_name_tag_association, NameTag.id == entity_name_tag_association.c.tag_id)
        .where(entity_name_tag_association.c.entity_id == entity.id)
    )).scalars().all())


@pytest.fixture
async def prod_like(db_session, organization):
    db = db_session
    ruslan = await _cand(db, organization, "Руслан")      # перформер у имени
    anna = await _cand(db, organization, "Анна")          # перформер в «Метках» + Валя
    boris = await _cand(db, organization, "Борис")        # Влад у имени, продуктивный
    lena = await _cand(db, organization, "Лена")          # опечатка у имени, Лиза

    valya = await _label(db, organization, "Валя")
    vlad = await _label(db, organization, "Влад")
    liza = await _label(db, organization, "Лиза")
    await _label(db, organization, "Иван", archived=True)
    await _label(db, organization, "Тест", archived=True)
    await _label(db, organization, "12", archived=True)
    egor = await _label(db, organization, "Егор", kind="sourcer")
    performer = await _label(db, organization, "перформер")
    typo = await _label(db, organization, "перфомер", archived=True)
    productive = await _label(db, organization, "продуктивный")

    await _link(db, ruslan, performer, at_name=True)
    await _link(db, ruslan, egor, at_name=True)
    await _link(db, anna, performer)
    await _link(db, anna, valya)
    await _link(db, boris, vlad, at_name=True)
    await _link(db, boris, productive)
    await _link(db, lena, typo, at_name=True)
    await _link(db, lena, liza)
    await db.commit()
    return {"ruslan": ruslan, "anna": anna, "boris": boris, "lena": lena}


@pytest.mark.asyncio
async def test_split_moves_name_tags_and_keeps_them_visible(db_session, prod_like):
    await split_tags_and_labels(db_session)
    p = prod_like
    assert await _name_tags_of(db_session, p["ruslan"]) == {"перформер", "Егор"}
    assert await _name_tags_of(db_session, p["boris"]) == {"Влад"}
    assert await _name_tags_of(db_session, p["lena"]) == {"перфомер"}
    # у имени больше не метки
    assert await _labels_of(db_session, p["ruslan"]) == set()
    assert await _labels_of(db_session, p["boris"]) == set()
    # никаких show_at_name в метках не осталось
    left = (await db_session.execute(
        select(entity_tag_association).where(entity_tag_association.c.show_at_name.is_(True))
    )).all()
    assert left == []


@pytest.mark.asyncio
async def test_split_removes_word_labels_even_assigned(db_session, prod_like):
    await split_tags_and_labels(db_session)
    p = prod_like
    names = set((await db_session.execute(select(EntityTag.name))).scalars().all())
    assert names == {"Валя", "Влад", "Лиза", "Иван", "Егор"}
    # слово в «Метках» снято, имя осталось
    assert await _labels_of(db_session, p["anna"]) == {"Валя"}
    assert await _labels_of(db_session, p["boris"]) == set()
    assert await _labels_of(db_session, p["lena"]) == {"Лиза"}


@pytest.mark.asyncio
async def test_split_makes_all_labels_sourcers(db_session, prod_like):
    await split_tags_and_labels(db_session)
    kinds = set((await db_session.execute(select(EntityTag.kind))).scalars().all())
    assert kinds == {"sourcer"}
    ivan = (await db_session.execute(select(EntityTag).where(EntityTag.name == "Иван"))).scalar_one()
    assert ivan.archived_at is not None  # архив сохранён


@pytest.mark.asyncio
async def test_split_is_idempotent_and_words_removed_only_once(db_session, organization, prod_like):
    first = await split_tags_and_labels(db_session)
    assert first["word_labels_removed"] == 5
    assert await db_session.get(DataMigrationMark, WORDS_MARK) is not None

    # Позже кто-то осознанно заводит метку «перформер» — рестарт её не трогает.
    await _label(db_session, organization, "перформер", kind="sourcer")
    await db_session.commit()
    second = await split_tags_and_labels(db_session)
    assert second == {
        "name_tags_created": 0, "name_tag_links_moved": 0,
        "word_labels_removed": 0, "labels_made_sourcers": 0,
    }
    names = set((await db_session.execute(select(EntityTag.name))).scalars().all())
    assert "перформер" in names


# ---------------- API ----------------

@pytest.mark.asyncio
async def test_new_label_is_always_sourcer(client, admin_user, org_owner):
    r = await client.post("/api/tags", json={"name": "Маша", "color": "red", "kind": "general"},
                          headers=_h(admin_user))
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "sourcer"

    r2 = await client.patch(f"/api/tags/{r.json()['id']}", json={"kind": "general"},
                            headers=_h(admin_user))
    assert r2.status_code == 422


@pytest.mark.asyncio
async def test_name_tags_live_separately_from_labels(
    client, db_session, organization, admin_user, org_owner,
):
    e = await _cand(db_session, organization, "Кандидат")
    await db_session.commit()

    r = await client.post("/api/tags/name-tags", json={"name": "перформер"}, headers=_h(admin_user))
    assert r.status_code == 200, r.text
    tag_id = r.json()["id"]

    r = await client.post(f"/api/tags/entities/{e.id}/name-tags/{tag_id}", headers=_h(admin_user))
    assert r.status_code == 200, r.text
    got = await client.get(f"/api/tags/entities/{e.id}/name-tags", headers=_h(admin_user))
    assert [t["name"] for t in got.json()] == ["перформер"]

    # не метка: нет ни в справочнике меток, ни в метках кандидата
    labels = await client.get("/api/tags", headers=_h(admin_user))
    assert "перформер" not in {t["name"] for t in labels.json()}
    ent_labels = await client.get(f"/api/tags/entities/{e.id}/tags", headers=_h(admin_user))
    assert ent_labels.json() == []

    # скрыть из списка — у кандидата остаётся
    await client.post(f"/api/tags/name-tags/{tag_id}/archive", headers=_h(admin_user))
    listed = await client.get("/api/tags/name-tags", headers=_h(admin_user))
    assert listed.json() == []
    got = await client.get(f"/api/tags/entities/{e.id}/name-tags", headers=_h(admin_user))
    assert [t["name"] for t in got.json()] == ["перформер"]

    # снять
    r = await client.delete(f"/api/tags/entities/{e.id}/name-tags/{tag_id}", headers=_h(admin_user))
    assert r.status_code == 200
    got = await client.get(f"/api/tags/entities/{e.id}/name-tags", headers=_h(admin_user))
    assert got.json() == []


@pytest.mark.asyncio
async def test_board_card_shows_name_tags_from_new_catalog(
    client, db_session, organization, admin_user, org_owner, prod_like,
):
    await split_tags_and_labels(db_session)
    r = await client.get("/api/candidates/kanban?per_column=500", headers=_h(admin_user))
    assert r.status_code == 200, r.text
    cards = {c["name"]: c for col in r.json()["columns"] for c in col["cards"]}
    assert {t["name"] for t in cards["Руслан"]["headline_tags"]} == {"перформер", "Егор"}
    assert cards["Анна"]["headline_tags"] == []
