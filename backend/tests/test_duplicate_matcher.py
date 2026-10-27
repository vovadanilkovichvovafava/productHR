"""Единое ядро дедупа (services/duplicate_matcher) — этап 0 переделки.

Смысл этих тестов: закрепить, что «это тот же человек» решается ОДНИМ правилом.
Раньше баннер «Похожий кандидат», окно сравнения и пере-скан считали по трём
разным шкалам, и по одной паре показывали разные проценты.
"""
import pytest

from api.models.database import Entity, EntityType, EntityStatus, Organization
from api.services.duplicate_matcher import (
    compare_key_sets,
    identity_block_keys,
    keys_of_entity,
    match_entities,
    scan_org_pairs,
    best_match,
)
from api.services.similarity import (
    DupMatch, DupSignal, build_dup_keys, detect_archived_duplicate, find_duplicate_matches,
    match_level, similarity_service,
)


async def _mk(db, org_id, name, **kw):
    e = Entity(org_id=org_id, type=EntityType.candidate, name=name, status=EntityStatus.new, **kw)
    db.add(e)
    await db.flush()
    return e


# ============================================================
# compare_key_sets — единственное место, где решается «тот же человек»
# ============================================================

class TestCompareKeySets:
    def test_exact_email_is_identity_tier(self):
        a = build_dup_keys(name="Иван Иванов", email="dup@gmail.com")
        b = build_dup_keys(name="Пётр Петров", email="dup@gmail.com")
        strength, confidence, signals = compare_key_sets(a, b)
        # Одна почта — тир email, но это ОДИН признак: «возможно тот же» (60%),
        # не красный баннер (решение владельца 21.09.2026).
        assert (strength, confidence) == ("email", 60)
        assert match_level(signals) == "possible"
        assert any(s.field == "email" and s.identity for s in signals)

    def test_two_identity_fields_are_exact(self):
        a = build_dup_keys(name="Иван Иванов", email="dup@gmail.com", phone="+7 910 111-22-33")
        b = build_dup_keys(name="Пётр Петров", email="dup@gmail.com", phone="8 910 1112233")
        strength, confidence, signals = compare_key_sets(a, b)
        assert (strength, confidence) == ("email", 100)
        assert match_level(signals) == "exact"

    def test_name_alone_is_possible(self):
        a = build_dup_keys(name="Соколов Пётр")
        b = build_dup_keys(name="Соколов Пётр")
        strength, confidence, signals = compare_key_sets(a, b)
        assert (strength, confidence) == ("name", 50)
        assert match_level(signals) == "possible"

    def test_name_plus_birth_date_is_exact(self):
        a = build_dup_keys(name="Соколов Пётр", extra_data={"birth_date": "02.01.1997"})
        b = build_dup_keys(name="Соколов Пётр", extra_data={"birth_date": "1997-01-02"})
        strength, confidence, signals = compare_key_sets(a, b)
        assert (strength, confidence) == ("name", 100)
        assert match_level(signals) == "exact"

    def test_partial_phone_plus_dob_stays_possible(self):
        # 7 цифр телефона — не личность, дата рождения — одна: жёлтый, не красный.
        a = build_dup_keys(name="Сидоров Иван", phone="+7 495 000-11-22",
                           extra_data={"birth_date": "14.05.1990"})
        b = build_dup_keys(name="Петров Александр", phone="+7 916 000-11-22",
                           extra_data={"birth_date": "1990-05-14"})
        _, confidence, signals = compare_key_sets(a, b)
        assert match_level(signals) == "possible"
        assert confidence < 100

    def test_soft_component_does_not_fake_identity_tier(self):
        # Совпали ПОСЛЕДНИЕ 7 цифр (разный код города) + дата рождения. Мягкий
        # сигнал лежит в поле "phone" — но тир обязан остаться soft, а не «phone».
        a = build_dup_keys(name="Сидоров Иван", phone="+7 495 000-11-22",
                           extra_data={"birth_date": "14.05.1990"})
        b = build_dup_keys(name="Петров Александр", phone="+7 916 000-11-22",
                           extra_data={"birth_date": "1990-05-14"})
        strength, confidence, signals = compare_key_sets(a, b)
        assert strength == "soft"
        assert 65 <= confidence < 100
        assert not any(s.identity for s in signals)

    def test_signals_cover_every_matched_field(self):
        a = build_dup_keys(name="Соколов Пётр", email="p.sokolov@gmail.com",
                           phone="+7 910 555-12-34",
                           extra_data={"birth_date": "1997-01-02", "city": "Москва"})
        b = build_dup_keys(name="Cоколов Пётр Игоревич", email="p.sokolov@mail.ru",
                           phone="8 (910) 555 12 34",
                           extra_data={"birth_date": "02.01.1997", "city": "Москва"})
        strength, confidence, signals = compare_key_sets(a, b)
        assert (strength, confidence) == ("email", 100)
        fields = {s.field for s in signals}
        # Один факт — одно поле: «ФИО совпало» не должно приезжать и как name,
        # и как full_name (окно сравнения подсвечивает поле, а не имя правила).
        # Город совпал, но в причины не попадает (убран из процента 22.09.2026).
        assert fields == {"email", "name", "phone", "birth_date"}
        assert len(fields) == len(signals)

    def test_different_people_are_not_a_match(self):
        a = build_dup_keys(name="Борисов Кирилл Евгеньевич")
        b = build_dup_keys(name="Сапрыкин Кирилл Евгеньевич")
        assert compare_key_sets(a, b)[0] is None

    def test_block_keys_are_deduplicated(self):
        # «Иванов Иван» даёт одинаковый ключ от фамилии и от имени. Дубль ключа
        # клал кандидата в корзину дважды — он сравнивался сам с собой и всегда
        # «совпадал» (пере-скан из-за этого никогда не снимал устаревшие флаги).
        keys = identity_block_keys(build_dup_keys(name="Иванов Иван"))
        assert len(keys) == len(set(keys))


# ============================================================
# Одна пара — одно число в баннере и в окне сравнения
# ============================================================

@pytest.mark.asyncio
async def test_same_confidence_in_banner_and_compare_window(db_session, organization):
    old = await _mk(db_session, organization.id, "Иван Иванов", email="same@x.com")
    new = await _mk(db_session, organization.id, "Другое Имя", email="same@x.com")
    await db_session.commit()

    await detect_archived_duplicate(db_session, new)
    meta = (new.extra_data or {}).get("hidden_duplicate_meta")
    dups = await similarity_service.detect_duplicates(db=db_session, entity=new)

    card = next(d for d in dups if d.entity_id == old.id)
    # Раньше: баннер «Точное совпадение» (100), карточка — «30%».
    # Одна почта — один признак: оба места показывают одинаковые 60% и «possible».
    assert meta["confidence"] == card.confidence == 60
    assert meta["strength"] == card.strength == "email"
    assert meta["level"] == card.level == "possible"


def test_best_match_prefers_exact_over_higher_tier():
    only_email = DupMatch(entity_id=1, is_archived=False, strength="email", confidence=60,
                          reasons=[], signals=[DupSignal("email", "e", 100, True, "a", "a")])
    phone_and_name = DupMatch(entity_id=2, is_archived=False, strength="name", confidence=100,
                              reasons=[], signals=[DupSignal("name", "n", 100, True, "x", "x"),
                                                   DupSignal("phone", "p", 100, True, "1", "1")])
    assert best_match([only_email, phone_and_name]).entity_id == 2


@pytest.mark.asyncio
async def test_compare_window_exposes_signals_for_highlighting(db_session, organization):
    await _mk(db_session, organization.id, "Соколов Пётр", phone="+7 910 555-12-34",
              extra_data={"city": "Москва"})
    new = await _mk(db_session, organization.id, "Соколов Пётр Игоревич",
                    phone="8 910 5551234", extra_data={"city": "Москва"})
    await db_session.commit()

    dups = await similarity_service.detect_duplicates(db=db_session, entity=new)
    assert dups, "пара по ФИО+телефону обязана попасть в окно сравнения"
    signals = {s.field: s for s in dups[0].signals}
    assert signals["phone"].identity is True
    assert "city" not in signals  # город больше не довод «тот же человек»
    assert dups[0].matched_fields["phone"][0]


# ============================================================
# Текст резюме — подсказка, а не основание слить
# ============================================================

@pytest.mark.asyncio
async def test_text_twin_is_info_tier_only(db_session, organization):
    other = await _mk(db_session, organization.id, "Никита Первый", email="n1@x.com")
    await db_session.flush()
    new = await _mk(
        db_session, organization.id, "Никита Второй", email="n2@x.com",
        extra_data={"text_twin": {"twin_id": other.id, "similarity": 0.93}},
    )
    await db_session.commit()

    # Окно сравнения показывает пару как подсказку…
    dups = await similarity_service.detect_duplicates(db=db_session, entity=new)
    twin = next((d for d in dups if d.entity_id == other.id), None)
    assert twin is not None and twin.strength == "text"
    assert twin.confidence == 93

    # …а баннер слияния по одному тексту не поднимается: у разных людей бывают
    # анкеты по одному шаблону (реальный кейс с тремя «Никитами»).
    assert await detect_archived_duplicate(db_session, new) is None
    matches = await find_duplicate_matches(
        db_session, organization.id, keys_of_entity(new), exclude_id=new.id,
    )
    assert all(m.strength != "text" for m in matches)


# ============================================================
# Пере-скан видит то же, что детект на создании
# ============================================================

@pytest.mark.asyncio
async def test_rescan_matches_patronymic_like_detector(db_session, organization):
    # Прежний пере-скан сверял ФИО ТОЧНОЙ строкой и эту пару не находил, хотя
    # детект-на-создании считает её дублем.
    a = await _mk(db_session, organization.id, "Векленко Кирилл Дмитриевич")
    b = await _mk(db_session, organization.id, "Векленко Кирилл")
    await db_session.commit()

    _items, pairs = await scan_org_pairs(db_session, organization.id)
    assert {m.entity_id for m in pairs.get(b.id, [])} == {a.id}
    assert await detect_archived_duplicate(db_session, b) == a.id


@pytest.mark.asyncio
async def test_scan_never_pairs_entity_with_itself(db_session, organization):
    await _mk(db_session, organization.id, "Иванов Иван", email="stale-a@x.com")
    await _mk(db_session, organization.id, "Петров Пётр", email="stale-b@x.com")
    await db_session.commit()

    _items, pairs = await scan_org_pairs(db_session, organization.id)
    for owner_id, ms in pairs.items():
        assert all(m.entity_id != owner_id for m in ms)


# ============================================================
# Границы: организация, dismissed, приоритет тира
# ============================================================

@pytest.mark.asyncio
async def test_match_entities_respects_org_and_dismissed(db_session, organization, second_organization):
    await _mk(db_session, second_organization.id, "Чужой", email="cross@x.com")
    mine = await _mk(db_session, organization.id, "Свой", email="cross@x.com")
    await db_session.flush()
    probe = await _mk(db_session, organization.id, "Новый", email="cross@x.com")
    await db_session.commit()

    keys = keys_of_entity(probe)
    matches = await match_entities(db_session, organization.id, keys, exclude_id=probe.id)
    assert {m.entity_id for m in matches} == {mine.id}

    matches = await match_entities(
        db_session, organization.id, keys, exclude_id=probe.id, dismissed={mine.id},
    )
    assert matches == []


@pytest.mark.asyncio
async def test_best_match_prefers_strong_over_soft_over_phone(db_session, organization):
    # Телефон намеренно НИЖЕ мягкого тира: один номер бывает общим (родственники,
    # рабочий), а мягкий флаг — это уже несколько совпавших признаков.
    phone_only = await _mk(db_session, organization.id, "Телефонов Тимур", phone="+7 900 111-22-33")
    await db_session.flush()
    strong = await _mk(db_session, organization.id, "Сильнов Семён", email="best@x.com")
    await db_session.flush()
    probe = await _mk(db_session, organization.id, "Проверкин Пётр",
                      email="best@x.com", phone="+7 900 111-22-33")
    await db_session.commit()

    matches = await match_entities(
        db_session, organization.id, keys_of_entity(probe), exclude_id=probe.id,
    )
    assert {m.entity_id for m in matches} == {phone_only.id, strong.id}
    assert best_match(matches).entity_id == strong.id


# ============================================================
# Отчества (Эльвира, 2026-09-16): четыре однофамильца-тёзки с РАЗНЫМИ
# отчествами показывались как «точное совпадение», отличить их было нечем.
# ============================================================

class TestPatronymics:
    def test_different_patronymics_are_not_a_duplicate(self):
        a = build_dup_keys(name="Иванов Кирилл Владимирович")
        b = build_dup_keys(name="Иванов Кирилл Евгеньевич")
        assert compare_key_sets(a, b)[0] is None

    def test_missing_patronymic_on_one_side_still_matches(self):
        # «Векленко Кирилл» ↔ «Векленко Кирилл Дмитриевич» — по-прежнему дубль:
        # отсутствие отчества не противоречит ничему.
        a = build_dup_keys(name="Векленко Кирилл")
        b = build_dup_keys(name="Векленко Кирилл Дмитриевич")
        assert compare_key_sets(a, b)[0] == "name"

    def test_initial_translit_and_typo_are_not_conflicts(self):
        base = build_dup_keys(name="Иванов Кирилл Владимирович")
        for other in ("Иванов Кирилл В.", "Ivanov Kirill Vladimirovich",
                      "Иванов Кирилл Владимирвич"):
            assert compare_key_sets(base, build_dup_keys(name=other))[0] == "name", other

    def test_serbian_surname_is_not_read_as_patronymic(self):
        # «Петрович» — фамилия, а не отчество: набор отчеств пересекается по ней,
        # значит конфликта нет и пара сравнивается как обычно.
        a = build_dup_keys(name="Петрович Иван Драганович")
        b = build_dup_keys(name="Петрович Иван Мирославович")
        assert compare_key_sets(a, b)[0] == "name"

    def test_shared_contact_still_wins_over_patronymic(self):
        # Отчества разные, но почта одна — это по-прежнему дубль (контакт сильнее),
        # просто «Имя» больше не числится среди совпавших полей.
        a = build_dup_keys(name="Иванов Кирилл Владимирович", email="k@x.com")
        b = build_dup_keys(name="Иванов Кирилл Евгеньевич", email="k@x.com")
        strength, _conf, signals = compare_key_sets(a, b)
        assert strength == "email"
        assert "name" not in {s.field for s in signals}


@pytest.mark.asyncio
async def test_elvira_case_only_same_patronymic_is_offered(db_session, organization):
    """Кейс Эльвиры: у нового «Иванова Кирилла Владимировича» четыре однофамильца.
    Предлагать к слиянию можно только того, у кого отчество совпадает."""
    same = await _mk(db_session, organization.id, "Иванов Кирилл Владимирович")
    for other in ("Иванов Кирилл Евгеньевич", "Иванов Кирилл Сергеевич", "Иванов Кирилл Петрович"):
        await _mk(db_session, organization.id, other)
    new = await _mk(db_session, organization.id, "Иванов Кирилл Владимирович")
    await db_session.commit()

    dups = await similarity_service.detect_duplicates(db=db_session, entity=new)
    assert [d.entity_id for d in dups] == [same.id]
    assert await detect_archived_duplicate(db_session, new) == same.id


@pytest.mark.asyncio
async def test_merge_blocked_for_different_patronymics(db_session, organization):
    """Даже если рекрутёр дошёл до слияния руками — склеить разных людей нельзя."""
    from api.services.similarity import MergeIdentityConflict

    a = await _mk(db_session, organization.id, "Иванов Кирилл Владимирович", email="k@x.com")
    b = await _mk(db_session, organization.id, "Иванов Кирилл Евгеньевич", email="k@x.com")
    await db_session.commit()

    with pytest.raises(MergeIdentityConflict) as err:
        await similarity_service.merge_entities(db=db_session, source_entity=b, target_entity=a)
    assert "отчества" in err.value.reason


# ============================================================
# Что происходит с АНКЕТАМИ (form_dispatches/form_submissions), когда у
# нескольких похожих кандидатов они заполнены, — вопрос владельца 17.09.2026.
# ============================================================

async def _form_for(db, org_id, slug: str):
    from api.models.database import FormTemplate
    f = FormTemplate(org_id=org_id, title="Анкета кандидата", slug=slug, fields=[])
    db.add(f)
    await db.flush()
    return f


async def _fill_form(db, form, entity, answer: str, token: str):
    """Анкета, отправленная кандидату и заполненная им."""
    from api.models.database import FormDispatch, FormSubmission
    d = FormDispatch(form_id=form.id, entity_id=entity.id, token=token, status="submitted")
    db.add(d)
    await db.flush()
    sub = FormSubmission(form_id=form.id, entity_id=entity.id, data={"q": answer}, dispatch_id=d.id)
    db.add(sub)
    await db.flush()
    return d, sub


@pytest.mark.asyncio
async def test_forms_of_all_merged_duplicates_land_on_survivor(db_session, organization):
    """Три карточки одного человека, у КАЖДОЙ своя заполненная анкета. После
    попарного слияния все три анкеты должны оказаться на выжившей карточке —
    ни одна не теряется (FK у form_dispatches — CASCADE, без переноса они бы
    удалились вместе с влитой карточкой)."""
    from sqlalchemy import select as _select
    from api.models.database import FormDispatch, FormSubmission

    form = await _form_for(db_session, organization.id, "anketa-merge")
    survivor = await _mk(db_session, organization.id, "Иванов Кирилл Владимирович", email="k.ivanov@x.com")
    dup1 = await _mk(db_session, organization.id, "Кирилл Иванов", email="k.ivanov@x.com")
    dup2 = await _mk(db_session, organization.id, "Иванов К. В.", email="k.ivanov@x.com")
    await db_session.flush()
    await _fill_form(db_session, form, survivor, "ответ выжившего", "tok-survivor")
    await _fill_form(db_session, form, dup1, "ответ первого дубля", "tok-dup1")
    await _fill_form(db_session, form, dup2, "ответ второго дубля", "tok-dup2")
    await db_session.commit()

    # Рекрутёр решает пары по одной — ровно как в окне сравнения.
    await similarity_service.merge_entities(db=db_session, source_entity=dup1, target_entity=survivor)
    await similarity_service.merge_entities(db=db_session, source_entity=dup2, target_entity=survivor)
    await db_session.commit()

    dispatches = (await db_session.execute(
        _select(FormDispatch).where(FormDispatch.entity_id == survivor.id)
    )).scalars().all()
    assert len(dispatches) == 3, "все три отправленные анкеты остаются на карточке"
    assert {d.token for d in dispatches} == {"tok-survivor", "tok-dup1", "tok-dup2"}

    answers = {
        s.data["q"] for s in (await db_session.execute(
            _select(FormSubmission).where(FormSubmission.entity_id == survivor.id)
        )).scalars().all()
    }
    assert answers == {"ответ выжившего", "ответ первого дубля", "ответ второго дубля"}


@pytest.mark.asyncio
async def test_public_share_link_survives_merge(db_session, organization):
    """Публичная ссылка на кандидата (её уже отправили заказчику) после слияния
    должна вести на выжившую карточку, а не отваливаться в 404."""
    from datetime import datetime, timedelta
    from sqlalchemy import select as _select
    from api.models.database import CandidateShareLink

    survivor = await _mk(db_session, organization.id, "Жукова Ольга", email="o.zhukova@x.com")
    dup = await _mk(db_session, organization.id, "Ольга Жукова", email="o.zhukova@x.com")
    await db_session.flush()
    db_session.add(CandidateShareLink(
        org_id=organization.id, entity_id=dup.id, token="share-token-1",
        expires_at=datetime.utcnow() + timedelta(days=30),
    ))
    await db_session.commit()

    await similarity_service.merge_entities(db=db_session, source_entity=dup, target_entity=survivor)
    await db_session.commit()

    link = (await db_session.execute(
        _select(CandidateShareLink).where(CandidateShareLink.token == "share-token-1")
    )).scalar_one_or_none()
    assert link is not None, "ссылка не должна исчезать вместе с влитой карточкой"
    assert link.entity_id == survivor.id


@pytest.mark.asyncio
async def test_back_link_gets_mirrored_meta(db_session, organization):
    # Второй стороне пары ставится обратная ссылка — и та же мета: иначе баннер
    # у старого кандидата не знал уровня и показывал «0%».
    old = await _mk(db_session, organization.id, "Иван Иванов", email="mirror@x.com",
                    phone="+7 910 222-33-44")
    new = await _mk(db_session, organization.id, "Другое Имя", email="mirror@x.com",
                    phone="8 910 2223344")
    await db_session.commit()

    assert await detect_archived_duplicate(db_session, new) == old.id
    back = (old.extra_data or {}).get("hidden_duplicate_meta")
    assert old.extra_data["hidden_duplicate_id"] == new.id
    assert back["matched_id"] == new.id
    assert back["level"] == new.extra_data["hidden_duplicate_meta"]["level"] == "exact"


@pytest.mark.asyncio
async def test_weak_back_link_does_not_replace_exact_flag(db_session, organization):
    # «Кирилл Иванов» уже помечен точным дублем (имя + телефон). Однофамилец,
    # совпавший только именем, не должен перетянуть его флаг на себя.
    a = await _mk(db_session, organization.id, "Иванов Кирилл", phone="+7 917 200-40-60")
    b = await _mk(db_session, organization.id, "Кирилл Иванов", phone="8 917 2004060")
    await db_session.commit()
    assert await detect_archived_duplicate(db_session, b) == a.id
    # Флаг самой анкете ставит роут (создание / detect-duplicate) — повторяем его.
    b.extra_data = {**b.extra_data, "hidden_duplicate_id": a.id}
    assert a.extra_data["hidden_duplicate_meta"]["level"] == "exact"

    c = await _mk(db_session, organization.id, "Иванов Кирилл Евгеньевич")
    await db_session.commit()
    await detect_archived_duplicate(db_session, c)
    assert a.extra_data["hidden_duplicate_id"] == b.id
    assert b.extra_data["hidden_duplicate_id"] == a.id
