"""
Тесты теневой дедупликации кандидатов:
- detect_archived_duplicate: матчинг по email/телефону, скоуп архива/org, dismissed
- merge_entities: перенос истории на survivor, удаление source, снятие флага, UNIQUE-конфликт заявок
- эндпоинты: archive / unarchive / archive-list (superadmin-гейт), dismiss, merge-shadow
- фильтрация: архивные не попадают в активный список
"""
import pytest
from sqlalchemy import select

from api.models.database import (
    Entity, EntityType, EntityStatus, Organization, User,
    Vacancy, VacancyApplication, StageTransition,
)
from api.services.similarity import (
    detect_archived_duplicate, similarity_service, looks_like_person_name,
)
from api.services.auth import create_access_token


async def _mk(db, org_id, name, **kw):
    e = Entity(org_id=org_id, type=EntityType.candidate, name=name, status=EntityStatus.new, **kw)
    db.add(e)
    await db.flush()
    return e


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ============================================================
# Архив в поиске «Все кандидаты» (найти можно, листать — нет)
# ============================================================

@pytest.mark.asyncio
async def test_search_finds_archived_only_with_query(
    client, db_session, organization, admin_user, org_owner, admin_token,
):
    """Архивный НЕ виден в пустой выдаче (доска не тонет в теневой базе),
    но находится ПОИСКОМ и помечен флагом is_archived."""
    await _mk(db_session, organization.id, "Архивный Пётр Сергеевич", is_archived=True)
    await _mk(db_session, organization.id, "Активный Иван Петрович")
    await db_session.commit()

    # без запроса — архива нет
    r = await client.get("/api/candidates/search", headers=_h(admin_token))
    assert r.status_code == 200, r.text
    names = [i["name"] for i in r.json()["items"]]
    assert "Архивный Пётр Сергеевич" not in names, names

    # с запросом — находится и помечен
    r = await client.get("/api/candidates/search?q=Архивный", headers=_h(admin_token))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    found = [i for i in items if i["name"] == "Архивный Пётр Сергеевич"]
    assert len(found) == 1, items
    assert found[0]["is_archived"] is True, found[0]


@pytest.mark.asyncio
async def test_search_archived_does_not_leak_across_orgs(
    client, db_session, organization, second_organization, admin_user, org_owner, admin_token,
):
    """Поиск с архивом НЕ должен пробивать границу организации."""
    await _mk(db_session, second_organization.id, "Чужой Архивный Пётр", is_archived=True)
    await db_session.commit()

    r = await client.get("/api/candidates/search?q=Чужой", headers=_h(admin_token))
    assert r.status_code == 200, r.text
    names = [i["name"] for i in r.json()["items"]]
    assert "Чужой Архивный Пётр" not in names, names


# ============================================================
# Авто-склейка «разъехавшегося» человека прямо во время импорта
# ============================================================

@pytest.mark.asyncio
async def test_import_auto_merges_split_person(
    client, db_session, organization, admin_user, org_owner, admin_token,
):
    """Кейс Пройдакова: человек без телефона/почты, только @хэндл, из-за старых
    заливок разъехался на 3 архивные карточки. Новый импорт должен склеить их
    в ОДНУ автоматически — без ручной кнопки «Найти дубликаты»."""
    for f in ("Android dev", "Unity", "Unity dev"):
        await _mk(
            db_session, organization.id, "Разъехался Тест Иванович",
            telegram_usernames=["splituser"], is_archived=True,
            extra_data={
                "import_source": "clickup",
                "clickup_task_ids": [f"T-{f}"],
                "participations": [{
                    "vacancy_title": f, "recruiter": "Мария",
                    "status": "собес", "anketa": [],
                }],
            },
        )
    await db_session.commit()

    csv_text = (
        "task_id,funnel_list,funnel_folder,status,name,cf:Telegram\n"
        "N1,Android dev,Sandbox - Мария,собес,Разъехался Тест Иванович,@splituser\n"
    )
    r = await client.post(
        "/api/import/execute",
        files={"file": ("clickup.csv", csv_text.encode("utf-8"), "text/csv")},
        data={"column_mapping": '{"name":"name"}', "skip_duplicates": "true"},
        headers=_h(admin_token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # две лишние карточки влиты в первую
    assert body["auto_merged"] == 2, body

    db_session.expire_all()
    rows = (await db_session.execute(
        select(Entity).where(Entity.name == "Разъехался Тест Иванович")
    )).scalars().all()
    assert len(rows) == 1, [(e.id, e.name) for e in rows]
    # все прохождения собрались в выжившую карточку
    parts = (rows[0].extra_data or {}).get("participations") or []
    assert {p["vacancy_title"] for p in parts} == {"Android dev", "Unity", "Unity dev"}, parts


# ============================================================
# detect_archived_duplicate (unit)
# ============================================================

@pytest.mark.asyncio
async def test_detect_email_match_case_insensitive(db_session, organization):
    archived = await _mk(db_session, organization.id, "Иван архив", email="ivan@x.com", is_archived=True)
    newc = await _mk(db_session, organization.id, "Иван новый", email="IVAN@x.com")
    await db_session.commit()
    assert await detect_archived_duplicate(db_session, newc) == archived.id


@pytest.mark.asyncio
async def test_detect_phone_match_ignores_formatting(db_session, organization):
    archived = await _mk(db_session, organization.id, "Пётр архив", phone="8 (912) 345-67-89", is_archived=True)
    newc = await _mk(db_session, organization.id, "Пётр новый", phone="+7 912 3456789")
    await db_session.commit()
    assert await detect_archived_duplicate(db_session, newc) == archived.id


@pytest.mark.asyncio
async def test_detect_telegram_match_normalizes_at_and_case(db_session, organization):
    archived = await _mk(db_session, organization.id, "ТГ архив",
                         telegram_usernames=["ivan_hr"], is_archived=True)
    newc = await _mk(db_session, organization.id, "ТГ новый",
                     telegram_usernames=["@Ivan_HR"])  # @ + другой регистр
    await db_session.commit()
    assert await detect_archived_duplicate(db_session, newc) == archived.id


@pytest.mark.asyncio
async def test_detect_matches_by_full_name(db_session, organization):
    # одинаковое полное ФИО (≥2 слов) без общих контактов → дубль
    existing = await _mk(db_session, organization.id, "Хисамов Вадим Ринатович")
    newc = await _mk(db_session, organization.id, "Хисамов Вадим Ринатович")
    await db_session.commit()
    assert await detect_archived_duplicate(db_session, newc) == existing.id


@pytest.mark.asyncio
async def test_detect_single_word_name_not_matched(db_session, organization):
    # одно слово («Владимир») — по имени НЕ матчим (слишком общо)
    await _mk(db_session, organization.id, "Владимир")
    newc = await _mk(db_session, organization.id, "Владимир")
    await db_session.commit()
    assert await detect_archived_duplicate(db_session, newc) is None


@pytest.mark.asyncio
async def test_detect_matches_surname_firstname_ignoring_patronymic(db_session, organization):
    # «Векленко Кирилл» ↔ «Векленко Кирилл Дмитриевич» (с отчеством/без) → дубль
    existing = await _mk(db_session, organization.id, "Векленко Кирилл Дмитриевич")
    newc = await _mk(db_session, organization.id, "Векленко Кирилл")
    await db_session.commit()
    assert await detect_archived_duplicate(db_session, newc) == existing.id


@pytest.mark.asyncio
async def test_detect_same_firstname_patronymic_diff_surname_not_matched(db_session, organization):
    # разные фамилии, общий Имя+Отчество («Кирилл Евгеньевич») → НЕ дубль
    await _mk(db_session, organization.id, "Борисов Кирилл Евгеньевич")
    newc = await _mk(db_session, organization.id, "Сапрыкин Кирилл Евгеньевич")
    await db_session.commit()
    assert await detect_archived_duplicate(db_session, newc) is None


def test_names_match_surname_firstname_unit():
    from api.services.similarity import names_match_surname_firstname as m
    assert m("Векленко Кирилл", "Векленко Кирилл Дмитриевич") is True
    assert m("Векленко Кирилл Дмитриевич", "Векленко Кирилл") is True
    assert m("Борисов Кирилл Евгеньевич", "Сапрыкин Кирилл Евгеньевич") is False
    assert m("Иванов Иван", "Иванов Иван") is True   # тёзки-однофамильцы — да (предупреждение)
    assert m("Иванов", "Иванов Иван") is False        # одно слово → нет
    assert m("Иванов Пётр", "Иванов Иван") is False   # разное имя → нет
    # Фамилия/Имя в обратном порядке (LinkedIn "Имя Фамилия" vs hh.ru
    # "Фамилия Имя") — 2026-07-14: должно матчиться как дубль.
    assert m("Vlada Vertinskaya", "Vertinskaya Vlada") is True
    assert m("Кирилл Векленко", "Векленко Кирилл Дмитриевич") is True
    # Обратный порядок НЕ должен обходить защиту от однофамильцев-тёзок:
    # переставляем слова местами — фамилии всё равно разные.
    assert m("Кирилл Евгеньевич Борисов", "Сапрыкин Кирилл Евгеньевич") is False


@pytest.mark.asyncio
async def test_detect_no_match_returns_none(db_session, organization):
    await _mk(db_session, organization.id, "Архив", email="someone@x.com", is_archived=True)
    newc = await _mk(db_session, organization.id, "Новый", email="other@x.com", phone="+7 999 0000000")
    await db_session.commit()
    assert await detect_archived_duplicate(db_session, newc) is None


@pytest.mark.asyncio
async def test_detect_matches_active_candidates(db_session, organization):
    # детект теперь ловит дубль и среди АКТИВНЫХ (не только архив)
    active = await _mk(db_session, organization.id, "Актив", email="dup@x.com", is_archived=False)
    newc = await _mk(db_session, organization.id, "Новый", email="dup@x.com")
    await db_session.commit()
    assert await detect_archived_duplicate(db_session, newc) == active.id


@pytest.mark.asyncio
async def test_detect_respects_dismissed(db_session, organization):
    archived = await _mk(db_session, organization.id, "Архив", email="d@x.com", is_archived=True)
    await db_session.flush()
    newc = await _mk(
        db_session, organization.id, "Новый", email="d@x.com",
        extra_data={"dismissed_duplicate_ids": [archived.id]},
    )
    await db_session.commit()
    assert await detect_archived_duplicate(db_session, newc) is None


@pytest.mark.asyncio
async def test_detect_cross_org_isolated(db_session, organization, second_organization):
    await _mk(db_session, second_organization.id, "Чужой архив", email="x@x.com", is_archived=True)
    newc = await _mk(db_session, organization.id, "Новый", email="x@x.com")
    await db_session.commit()
    assert await detect_archived_duplicate(db_session, newc) is None


# ============================================================
# merge_entities (unit) — единый таймлайн
# ============================================================

@pytest.mark.asyncio
async def test_merge_moves_history_and_deletes_source(db_session, organization):
    vac = Vacancy(org_id=organization.id, title="Dev")
    db_session.add(vac)
    await db_session.flush()

    source = await _mk(db_session, organization.id, "Архив", email="s@x.com", is_archived=True)
    target = await _mk(db_session, organization.id, "Новый", email="t@x.com")
    target.extra_data = {"hidden_duplicate_id": source.id}

    app = VacancyApplication(vacancy_id=vac.id, entity_id=source.id)
    db_session.add(app)
    await db_session.flush()
    db_session.add(StageTransition(application_id=app.id, entity_id=source.id, to_stage="new"))
    await db_session.commit()

    merged = await similarity_service.merge_entities(
        db=db_session, source_entity=source, target_entity=target
    )

    # вся история перецеплена на survivor
    apps = (await db_session.execute(
        select(VacancyApplication).where(VacancyApplication.entity_id == target.id)
    )).scalars().all()
    assert len(apps) == 1
    trs = (await db_session.execute(
        select(StageTransition).where(StageTransition.entity_id == target.id)
    )).scalars().all()
    assert len(trs) == 1
    # source удалён
    assert await db_session.get(Entity, source.id) is None
    # флаг теневого дубля снят
    assert "hidden_duplicate_id" not in (merged.extra_data or {})


@pytest.mark.asyncio
async def test_merge_resolves_duplicate_application_conflict(db_session, organization):
    # обе сущности подавались на ОДНУ вакансию → UNIQUE(vacancy_id, entity_id);
    # merge не должен падать, заявка target остаётся, заявка source удаляется.
    vac = Vacancy(org_id=organization.id, title="Dev")
    db_session.add(vac)
    await db_session.flush()

    source = await _mk(db_session, organization.id, "Архив", email="s2@x.com", is_archived=True)
    target = await _mk(db_session, organization.id, "Новый", email="t2@x.com")
    db_session.add_all([
        VacancyApplication(vacancy_id=vac.id, entity_id=target.id),
        VacancyApplication(vacancy_id=vac.id, entity_id=source.id),
    ])
    await db_session.commit()

    await similarity_service.merge_entities(
        db=db_session, source_entity=source, target_entity=target
    )

    apps = (await db_session.execute(
        select(VacancyApplication).where(VacancyApplication.entity_id == target.id)
    )).scalars().all()
    assert len(apps) == 1
    assert await db_session.get(Entity, source.id) is None


# ============================================================
# Эндпоинты
# ============================================================

@pytest.mark.asyncio
async def test_archive_endpoint_hides_from_list(client, db_session, organization, admin_user, org_owner, admin_token):
    active = await _mk(db_session, organization.id, "Актив", email="act@x.com", created_by=admin_user.id)
    target = await _mk(db_session, organization.id, "Уберём", email="arc@x.com", created_by=admin_user.id)
    await db_session.commit()

    # до архивации — оба в списке
    r = await client.get("/api/entities/", headers=_h(admin_token))
    assert r.status_code == 200, r.text
    ids_before = {e["id"] for e in r.json()}
    assert {active.id, target.id} <= ids_before

    # архивируем
    r = await client.post(f"/api/entities/{target.id}/archive", headers=_h(admin_token))
    assert r.status_code == 200, r.text
    fresh = await db_session.get(Entity, target.id)
    await db_session.refresh(fresh)
    assert fresh.is_archived is True

    # после — архивный исчез из активного списка, активный остался
    r = await client.get("/api/entities/", headers=_h(admin_token))
    ids_after = {e["id"] for e in r.json()}
    assert active.id in ids_after
    assert target.id not in ids_after


@pytest.mark.asyncio
async def test_archive_list_superadmin_only(
    client, db_session, organization, admin_user, org_owner,
    superadmin_user, admin_token, superadmin_token,
):
    await _mk(db_session, organization.id, "Арх1", email="a1@x.com", is_archived=True)
    await db_session.commit()

    # обычный админ → 403
    r = await client.get("/api/entities/archive/list", headers=_h(admin_token))
    assert r.status_code == 403

    # суперадмин → 200 + видит архив
    r = await client.get("/api/entities/archive/list", headers=_h(superadmin_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] >= 1
    assert any(it["name"] == "Арх1" for it in body["items"])


@pytest.mark.asyncio
async def test_unarchive_superadmin_only(
    client, db_session, organization, admin_user, org_owner,
    superadmin_user, admin_token, superadmin_token,
):
    e = await _mk(db_session, organization.id, "ВАрхиве", email="u@x.com",
                  created_by=admin_user.id, is_archived=True)
    await db_session.commit()

    # обычный админ не может вернуть из архива
    r = await client.post(f"/api/entities/{e.id}/unarchive", headers=_h(admin_token))
    assert r.status_code == 403

    # суперадмин может
    r = await client.post(f"/api/entities/{e.id}/unarchive", headers=_h(superadmin_token))
    assert r.status_code == 200, r.text
    fresh = await db_session.get(Entity, e.id)
    await db_session.refresh(fresh)
    assert fresh.is_archived is False


@pytest.mark.asyncio
async def test_dismiss_clears_flag_and_records_id(
    client, db_session, organization, admin_user, org_owner, admin_token,
):
    archived = await _mk(db_session, organization.id, "Арх", email="dd@x.com", is_archived=True)
    await db_session.flush()
    newc = await _mk(
        db_session, organization.id, "Новый", email="dd2@x.com", created_by=admin_user.id,
        extra_data={"hidden_duplicate_id": archived.id},
    )
    await db_session.commit()

    r = await client.post(
        f"/api/entities/{newc.id}/dismiss-duplicate",
        json={"duplicate_id": archived.id}, headers=_h(admin_token),
    )
    assert r.status_code == 200, r.text

    fresh = await db_session.get(Entity, newc.id)
    await db_session.refresh(fresh)
    extra = fresh.extra_data or {}
    assert "hidden_duplicate_id" not in extra
    # Решение — в таблице пар (с 22.09.2026), а не в extra_data анкеты.
    from api.services.duplicate_decisions import dismissed_for
    assert archived.id in await dismissed_for(db_session, fresh)
    # повторный детект уже не поднимает этот дубль
    assert await detect_archived_duplicate(db_session, fresh) is None


@pytest.mark.asyncio
async def test_merge_shadow_endpoint(
    client, db_session, organization, admin_user, org_owner, admin_token,
):
    source = await _mk(db_session, organization.id, "Арх", email="ms@x.com", is_archived=True)
    await db_session.flush()
    target = await _mk(
        db_session, organization.id, "Новый", email="ms2@x.com", created_by=admin_user.id,
        extra_data={"hidden_duplicate_id": source.id},
    )
    await db_session.commit()

    r = await client.post(
        f"/api/entities/{target.id}/merge-shadow",
        json={"duplicate_id": source.id}, headers=_h(admin_token),
    )
    assert r.status_code == 200, r.text
    # архивный удалён, флаг снят
    assert await db_session.get(Entity, source.id) is None
    fresh = await db_session.get(Entity, target.id)
    await db_session.refresh(fresh)
    assert "hidden_duplicate_id" not in (fresh.extra_data or {})


@pytest.mark.asyncio
async def test_merge_shadow_merges_active_duplicate(
    client, db_session, organization, admin_user, org_owner, admin_token,
):
    # merge-shadow теперь объединяет и АКТИВНЫЙ дубль (не только архивный)
    source = await _mk(db_session, organization.id, "Активный дубль", email="na@x.com", is_archived=False)
    await db_session.flush()
    target = await _mk(db_session, organization.id, "Новый", email="na2@x.com", created_by=admin_user.id)
    await db_session.commit()

    r = await client.post(
        f"/api/entities/{target.id}/merge-shadow",
        json={"duplicate_id": source.id}, headers=_h(admin_token),
    )
    assert r.status_code == 200, r.text
    # источник-дубль удалён, survivor остался
    assert await db_session.get(Entity, source.id) is None
    assert await db_session.get(Entity, target.id) is not None


@pytest.mark.asyncio
async def test_detect_duplicate_endpoint_flags_both_sides(
    client, db_session, organization, admin_user, org_owner, admin_token,
):
    # Сценарий «Хисамовых»: два идентичных активных кандидата, созданных ДО детекта,
    # без флагов. Открытие карточки одного (detect-duplicate при открытии) должно
    # найти второго и пометить ОБЕ стороны → баннер появляется у обоих.
    a = await _mk(db_session, organization.id, "Хисамов Вадим Ринатович",
                  email="dnsvadim6@gmail.com", phone="+7 999 203 8926",
                  created_by=admin_user.id)
    b = await _mk(db_session, organization.id, "Хисамов Вадим Ринатович",
                  email="dnsvadim6@gmail.com", phone="+7 999 203 8926",
                  created_by=admin_user.id)
    await db_session.commit()

    r = await client.post(f"/api/entities/{a.id}/detect-duplicate", headers=_h(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["duplicate_id"] == b.id

    fresh_a = await db_session.get(Entity, a.id)
    await db_session.refresh(fresh_a)
    assert (fresh_a.extra_data or {}).get("hidden_duplicate_id") == b.id
    fresh_b = await db_session.get(Entity, b.id)
    await db_session.refresh(fresh_b)
    assert (fresh_b.extra_data or {}).get("hidden_duplicate_id") == a.id


@pytest.mark.asyncio
async def test_detect_duplicate_endpoint_no_match_returns_null(
    client, db_session, organization, admin_user, org_owner, admin_token,
):
    a = await _mk(db_session, organization.id, "Уникальный Кандидат",
                  email="uniq-detect@x.com", created_by=admin_user.id)
    await db_session.commit()
    r = await client.post(f"/api/entities/{a.id}/detect-duplicate", headers=_h(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["duplicate_id"] is None


# ============================================================
# Мусорные / общие telegram-значения (ярлыки источника из импорта)
# ============================================================

@pytest.mark.asyncio
async def test_detect_junk_telegram_not_matched(db_session, organization):
    # «telegram» — ярлык источника, а не личный хэндл → по нему НЕ матчим
    await _mk(db_session, organization.id, "Иванов Иван", telegram_usernames=["telegram"])
    newc = await _mk(db_session, organization.id, "Петров Пётр", telegram_usernames=["telegram"])
    await db_session.commit()
    assert await detect_archived_duplicate(db_session, newc) is None


@pytest.mark.asyncio
async def test_detect_common_telegram_not_matched(db_session, organization):
    # одно и то же tg-значение у ≥3 кандидатов → это не хэндл, а мусор; не матчим
    for nm in ("Иванов Иван", "Петров Пётр", "Сидоров Сидор"):
        await _mk(db_session, organization.id, nm, telegram_usernames=["sharedtag"])
    newc = await _mk(db_session, organization.id, "Кузнецов Кузьма", telegram_usernames=["sharedtag"])
    await db_session.commit()
    assert await detect_archived_duplicate(db_session, newc) is None


@pytest.mark.asyncio
async def test_detect_real_unique_telegram_still_matched(db_session, organization):
    # настоящий уникальный telegram-хэндл по-прежнему ловит дубль (регрессия)
    existing = await _mk(db_session, organization.id, "Анна Анина",
                         telegram_usernames=["anna_unique_hr"])
    newc = await _mk(db_session, organization.id, "Совсем Другая",
                     telegram_usernames=["@Anna_Unique_HR"])  # @ + регистр
    await db_session.commit()
    assert await detect_archived_duplicate(db_session, newc) == existing.id


@pytest.mark.asyncio
async def test_detect_same_person_split_cards_same_telegram_matched(db_session, organization):
    # ОДИН человек (одно ФИО), разъехавшийся на неск. карточек с ОДНИМ хэндлом,
    # ловится по telegram, хотя карточек ≥3. Гвард частоты — по РАЗНЫМ ИМЕНАМ, а
    # не по числу карточек (кейс Пройдакова: 3 воронки без телефона/почты).
    existing = await _mk(db_session, organization.id, "Пройдаков Владимир Дмитриевич",
                         telegram_usernames=["hier_sonne"])
    await _mk(db_session, organization.id, "Пройдаков Владимир Дмитриевич",
              telegram_usernames=["hier_sonne"])
    newc = await _mk(db_session, organization.id, "Пройдаков Владимир Дмитриевич",
                     telegram_usernames=["hier_sonne"])
    await db_session.commit()
    assert await detect_archived_duplicate(db_session, newc) is not None


@pytest.mark.asyncio
async def test_rescan_clears_stale_flag_from_junk_telegram(
    client, db_session, organization, admin_user, org_owner,
    superadmin_user, superadmin_token,
):
    # Двое РАЗНЫХ людей, ранее склеенных по мусорному telegram («telegram»):
    # стоит hidden_duplicate_id, но реального совпадения нет. Rescan снимает флаг.
    a = await _mk(db_session, organization.id, "Иванов Иван", email="stale-a@x.com",
                  telegram_usernames=["telegram"])
    b = await _mk(db_session, organization.id, "Петров Пётр", email="stale-b@x.com",
                  telegram_usernames=["telegram"])
    await db_session.flush()
    a.extra_data = {"hidden_duplicate_id": b.id}
    b.extra_data = {"hidden_duplicate_id": a.id}
    await db_session.commit()

    r = await client.post("/api/entities/archive/rescan", headers=_h(superadmin_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cleared"] >= 2

    for e in (a, b):
        fresh = await db_session.get(Entity, e.id)
        await db_session.refresh(fresh)
        assert "hidden_duplicate_id" not in (fresh.extra_data or {})


# ============================================================
# Имя-должность не должно матчить (баг расширения: имя = «Flutter Developer …»)
# ============================================================

def test_looks_like_person_name_rejects_positions():
    # настоящие ФИО
    assert looks_like_person_name("Хисамов Вадим Ринатович")
    assert looks_like_person_name("Александра Симонова")
    assert looks_like_person_name("Иван Петров")
    # должность/мусор/placeholder — не ФИО
    assert not looks_like_person_name("Flutter Developer, Минск, 25 лет")  # запятая+цифры
    assert not looks_like_person_name("Flutter Developer")                  # слово-должность
    assert not looks_like_person_name("Flutter-developer")                  # должность через дефис
    assert not looks_like_person_name("Backend разработчик")
    assert not looks_like_person_name("Владимир")                          # одно слово
    assert not looks_like_person_name("")


@pytest.mark.asyncio
async def test_detect_position_name_not_matched(db_session, organization):
    # имя-должность без общих контактов НЕ считаем дублем (иначе все «Flutter
    # Developer» слипаются), в отличие от настоящего ФИО (см. matches_by_full_name)
    await _mk(db_session, organization.id, "Flutter Developer, Минск, 26 лет")
    newc = await _mk(db_session, organization.id, "Flutter Developer, Москва, 29 лет")
    await db_session.commit()
    assert await detect_archived_duplicate(db_session, newc) is None


@pytest.mark.asyncio
async def test_check_duplicate_ignores_position_name_and_junk_telegram(
    client, db_session, organization, admin_user, org_owner, admin_token,
):
    # Баг расширения: имя = должность, telegram = ярлык источника «hh_b2b».
    # Разные люди (разные email/телефон) НЕ должны попадать в «Уже в базе».
    await _mk(db_session, organization.id, "Flutter Developer, Минск, 26 лет",
              email="evgeniy@x.com", phone="+375 29 271-14-25",
              telegram_usernames=["hh_b2b"], created_by=admin_user.id)
    await _mk(db_session, organization.id, "Flutter-developer, Москва, 29 лет",
              email="anatoliy@x.com", phone="+7 919 836-45-14",
              telegram_usernames=["hh_b2b"], created_by=admin_user.id)
    await db_session.commit()

    r = await client.post(
        "/api/magic-button/check-duplicate",
        json={"full_name": "Flutter Developer, Минск, 25 лет",
              "telegram": "hh_b2b", "phone": "+375 29 521 00 00"},
        headers=_h(admin_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["is_duplicate"] is False


@pytest.mark.asyncio
async def test_check_duplicate_real_identifier_still_flags(
    client, db_session, organization, admin_user, org_owner, admin_token,
):
    # настоящий идентификатор (email) по-прежнему ловит дубль
    await _mk(db_session, organization.id, "Хисамов Вадим Ринатович",
              email="dnsvadim6@gmail.com", phone="+7 999 203-89-26",
              created_by=admin_user.id)
    await db_session.commit()
    r = await client.post(
        "/api/magic-button/check-duplicate",
        json={"full_name": "Хисамов Вадим Ринатович", "email": "dnsvadim6@gmail.com"},
        headers=_h(admin_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["is_duplicate"] is True


# ============================================================
# source_url дедуп (резюме hh — стабильный ключ, без query-параметров)
# ============================================================

def test_normalize_source_url_strips_volatile_query():
    # hh даёт один и тот же /resume/<hash> с РАЗНЫМИ query (?t=…&vacancyId=…) при
    # каждом открытии — ключ должен быть одинаковым, иначе дедуп по URL не работает.
    from api.services.similarity import normalize_source_url
    a = normalize_source_url("https://hh.ru/resume/7f3d95b2000d88ec4300b539db6b4f67504341?hhtmFrom=chat&vacancyId=133912255&t=537111")
    b = normalize_source_url("https://hh.ru/resume/7f3d95b2000d88ec4300b539db6b4f67504341?hhtmFrom=chat&vacancyId=999&t=537999")
    assert a == b == "hh:resume:7f3d95b2000d88ec4300b539db6b4f67504341"


def test_normalize_source_url_different_resumes_differ():
    from api.services.similarity import normalize_source_url
    a = normalize_source_url("https://hh.ru/resume/aaaa0000bbbb1111cccc2222?t=1")
    b = normalize_source_url("https://hh.ru/resume/dddd3333eeee4444ffff5555?t=2")
    assert a and b and a != b


@pytest.mark.asyncio
async def test_detect_same_resume_url_matched_despite_query(db_session, organization):
    # Одно и то же резюме hh, открытое дважды с разными query-параметрами, без
    # контактов и с именем-заглушкой (должность). Раньше дедуп пропускал → дубль.
    url1 = "https://hh.ru/resume/7f3d95b2000d88ec4300b539db6b4f67504341?hhtmFrom=chat&vacancyId=1&t=100"
    url2 = "https://hh.ru/resume/7f3d95b2000d88ec4300b539db6b4f67504341?hhtmFrom=chat&vacancyId=2&t=200"
    existing = await _mk(db_session, organization.id, "специалист, Баку, 32 года",
                         telegram_usernames=["hh_b2b"], extra_data={"source_url": url1})
    newc = await _mk(db_session, organization.id, "специалист, Баку, 32 года",
                     telegram_usernames=["hh_b2b"], extra_data={"source_url": url2})
    await db_session.commit()
    assert await detect_archived_duplicate(db_session, newc) == existing.id


@pytest.mark.asyncio
async def test_detect_different_resume_url_not_matched(db_session, organization):
    # Разные резюме (разный hash) — НЕ дубль, даже при одинаковом мусорном telegram
    # и имени-должности.
    await _mk(db_session, organization.id, "специалист, Баку, 32 года",
              telegram_usernames=["hh_b2b"],
              extra_data={"source_url": "https://hh.ru/resume/aaaa0000bbbb1111cccc2222dddd3333eeee4444?t=1"})
    newc = await _mk(db_session, organization.id, "специалист, Минск, 28 лет",
                     telegram_usernames=["hh_b2b"],
                     extra_data={"source_url": "https://hh.ru/resume/9999000088887777666655554444333322221111?t=2"})
    await db_session.commit()
    assert await detect_archived_duplicate(db_session, newc) is None


@pytest.mark.asyncio
async def test_rescan_flags_same_resume_url(
    client, db_session, organization, admin_user, org_owner,
    superadmin_user, superadmin_token,
):
    # «Сверить»: один и тот же резюме hh, добавленный дважды (разные query), без
    # контактов и с именем-заглушкой — раньше rescan не находил, теперь флагует оба.
    url1 = "https://hh.ru/resume/abcdef0123456789abcdef0123456789abcdef01?vacancyId=1&t=1"
    url2 = "https://hh.ru/resume/abcdef0123456789abcdef0123456789abcdef01?vacancyId=2&t=2"
    a = await _mk(db_session, organization.id, "специалист, Баку, 32 года",
                  telegram_usernames=["hh_b2b"], extra_data={"source_url": url1})
    b = await _mk(db_session, organization.id, "специалист, Баку, 32 года",
                  telegram_usernames=["hh_b2b"], extra_data={"source_url": url2})
    await db_session.commit()

    r = await client.post("/api/entities/archive/rescan", headers=_h(superadmin_token))
    assert r.status_code == 200, r.text
    assert r.json()["flagged"] >= 2

    for e in (a, b):
        fresh = await db_session.get(Entity, e.id)
        await db_session.refresh(fresh)
        assert (fresh.extra_data or {}).get("hidden_duplicate_id") is not None


# ============================================================
# Пакетный импорт CSV (/import/execute-bulk)
# ============================================================

@pytest.mark.asyncio
async def test_bulk_import_merges_person_across_files(
    client, db_session, organization, admin_user, org_owner, admin_token,
):
    """Пачка: человек в двух файлах (разные воронки) → ОДНА карточка со всеми
    прохождениями. Не-ClickUp файл пропускается с причиной в files[]."""
    file_a = (
        "task_id,funnel_list,funnel_folder,status,name,cf:Telegram\n"
        "A1,Android dev,Sandbox - Мария,собес,Пётр Тестов Иванович,@petrtest\n"
    )
    file_b = (
        "task_id,funnel_list,funnel_folder,status,name,cf:Telegram\n"
        "B1,Unity,Sandbox - Мария,собес,Пётр Тестов Иванович,@petrtest\n"
    )
    not_clickup = "name,email\nКто-то,x@y.z\n"
    r = await client.post(
        "/api/import/execute-bulk",
        files=[
            ("files", ("android.csv", file_a.encode("utf-8"), "text/csv")),
            ("files", ("unity.csv", file_b.encode("utf-8"), "text/csv")),
            ("files", ("other.csv", not_clickup.encode("utf-8"), "text/csv")),
        ],
        data={"replace_existing": "false"},
        headers=_h(admin_token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["imported"] == 1, body      # один человек создан
    assert body["total"] == 2, body         # 2 ClickUp-строки (не-ClickUp не в счёт)
    accepted = [f for f in body["files"] if f["accepted"]]
    skipped_files = [f for f in body["files"] if not f["accepted"]]
    assert len(accepted) == 2, body["files"]
    assert len(skipped_files) == 1, body["files"]
    assert "ClickUp" in (skipped_files[0]["reason"] or ""), skipped_files

    db_session.expire_all()
    rows = (await db_session.execute(
        select(Entity).where(Entity.name == "Пётр Тестов Иванович")
    )).scalars().all()
    assert len(rows) == 1, [(e.id, e.name) for e in rows]
    parts = (rows[0].extra_data or {}).get("participations") or []
    assert {p["vacancy_title"] for p in parts} == {"Android dev", "Unity"}, parts


@pytest.mark.asyncio
async def test_bulk_import_idempotent(
    client, db_session, organization, admin_user, org_owner, admin_token,
):
    """Повторная пачка тех же файлов не плодит карточки — до-кладывает (skipped)."""
    file_a = (
        "task_id,funnel_list,funnel_folder,status,name,cf:Telegram\n"
        "A1,Android dev,Sandbox - Мария,собес,Идемпотент Тестов,@idemtest\n"
    )
    def _post():
        return client.post(
            "/api/import/execute-bulk",
            files=[("files", ("a.csv", file_a.encode("utf-8"), "text/csv"))],
            data={"replace_existing": "false"},
            headers=_h(admin_token),
        )
    r1 = await _post()
    assert r1.status_code == 200, r1.text
    assert r1.json()["imported"] == 1, r1.json()
    r2 = await _post()
    assert r2.status_code == 200, r2.text
    b2 = r2.json()
    assert b2["imported"] == 0 and b2["skipped"] == 1, b2

    db_session.expire_all()
    rows = (await db_session.execute(
        select(Entity).where(Entity.name == "Идемпотент Тестов")
    )).scalars().all()
    assert len(rows) == 1, [(e.id, e.name) for e in rows]


@pytest.mark.asyncio
async def test_bulk_backfills_comments_into_existing_card(
    client, db_session, organization, admin_user, org_owner, admin_token,
):
    """Регресс: комментарии должны домерживаться в УЖЕ существующую карточку
    (совпал → merge). Раньше терялись — shallow copy + мутация общих dict'ов
    делали значение равным старому, и SQLAlchemy не сохранял JSON-колонку."""
    await _mk(
        db_session, organization.id, "Якубов Тест",
        email="yak@x.io", telegram_usernames=["yaktest"], is_archived=True,
        extra_data={
            "import_source": "clickup",
            "clickup_task_ids": ["T-mb"],
            "participations": [{
                "vacancy_title": "Media Buyer", "recruiter": "Эльвира",
                "status": "анкета: нет", "anketa": [], "notes": [],
            }],
        },
    )
    await db_session.commit()

    csv_text = (
        "task_id,funnel_list,funnel_folder,status,name,cf:Telegram,comments\n"
        'T-mb,Media Buyer,Sandbox - Эльвира,анкета: нет,Якубов Тест,@yaktest,'
        '"[2026-07-07 15:01:42 · Эльвира HR] ответы копипастом и с ошибками"\n'
    )
    r = await client.post(
        "/api/import/execute-bulk",
        files=[("files", ("mb.csv", csv_text.encode("utf-8"), "text/csv"))],
        data={"replace_existing": "false"},
        headers=_h(admin_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["skipped"] == 1, r.json()  # совпал с существующей → merge

    db_session.expire_all()
    ents = (await db_session.execute(
        select(Entity).where(Entity.name == "Якубов Тест")
    )).scalars().all()
    assert len(ents) == 1
    parts = (ents[0].extra_data or {}).get("participations") or []
    notes = parts[0].get("notes") or []
    assert len(notes) == 1, f"комментарий не домержился: {parts}"
    assert "копипастом" in notes[0]["text"]
