"""Юнит-тесты чистых функций ClickUp-combine импорта."""
from api.services.clickup_import import (
    normalize_phone,
    normalize_hh_url,
    clean_recruiter,
    row_strong_keys,
    group_rows_by_person,
    build_participation,
    assemble_person,
    extract_hh_from_row,
    extract_email_from_row,
    merge_participations,
    extract_birthdate,
    extract_location,
    distill_person_fields,
    birthdate_from_cf,
)
from datetime import date


# ── Task 1: ключи и нормализация ──

def test_normalize_phone_last10():
    assert normalize_phone("+7 915 167 29 74") == "9151672974"
    assert normalize_phone("8(915)167-29-74") == "9151672974"
    assert normalize_phone("123") == ""  # слишком коротко → не ключ


def test_normalize_hh_url_strips_query():
    a = normalize_hh_url("https://hh.ru/resume/ABC123?from=share&t=1")
    assert a == "hh.ru/resume/abc123"
    assert normalize_hh_url("нет ссылки") is None


def test_clean_recruiter_strips_prefix():
    assert clean_recruiter("Sandbox - Мария") == "Мария"
    assert clean_recruiter("Эльвира") == "Эльвира"
    assert clean_recruiter("") == ""


def test_row_strong_keys():
    keys = row_strong_keys("IVAN@x.io", "+7 915 167 29 74", "https://hh.ru/resume/ABC?x=1")
    assert "email:ivan@x.io" in keys
    assert "phone:9151672974" in keys
    assert "hh:hh.ru/resume/abc" in keys


def test_row_strong_keys_telegram():
    # Годный личный хэндл → tg-ключ (ловит людей без телефона/почты/hh).
    keys = row_strong_keys("", "", None, telegram="@hier_sonne")
    assert keys == {"tg:hier_sonne"}
    # С @ и регистром — нормализуется.
    assert row_strong_keys("", "", None, telegram="HIER_SONNE") == {"tg:hier_sonne"}


def test_row_strong_keys_junk_telegram_ignored():
    # Мусорный тег-источник в telegram → НЕ ключ (иначе слипнутся разные люди).
    assert row_strong_keys("", "", None, telegram="hh_b2b") == set()
    assert row_strong_keys("", "", None, telegram="@telegram") == set()


def test_group_by_telegram_only_no_phone_email():
    # Реальный кейс Пройдакова: 3 строки, нет телефона/почты/hh, один @hier_sonne
    # → одна группа (склеиваются по telegram).
    rows = [
        {"name": "Пройдаков Владимир", "telegram": "@hier_sonne", "funnel_list": "Android dev"},
        {"name": "Пройдаков Владимир", "telegram": "@hier_sonne", "funnel_list": "Unity"},
        {"name": "Пройдаков Владимир", "telegram": "@hier_sonne", "funnel_list": "Unity dev"},
    ]
    key_fn = lambda r: row_strong_keys("", "", None, telegram=r.get("telegram"))
    groups = group_rows_by_person(rows, key_fn)
    assert len(groups) == 1
    assert len(groups[0]) == 3


def test_assemble_telegram_only_person_one_card_many_passes():
    rows = [
        {"name": "Пройдаков Владимир Дмитриевич", "telegram": "@hier_sonne",
         "funnel_list": "Android dev", "funnel_folder": "Sandbox - Мария", "status": "собес"},
        {"name": "Пройдаков Владимир Дмитриевич", "telegram": "@hier_sonne",
         "funnel_list": "Unity", "funnel_folder": "Sandbox - Мария", "status": "собес"},
        {"name": "Пройдаков Владимир Дмитриевич", "telegram": "@hier_sonne",
         "funnel_list": "Unity dev", "funnel_folder": "Sandbox - Эльвира", "status": "собес"},
    ]
    person = assemble_person(rows, cf_headers=[])
    assert person["telegram_usernames"] == ["hier_sonne"]
    parts = person["extra_data"]["participations"]
    assert {p["vacancy_title"] for p in parts} == {"Android dev", "Unity", "Unity dev"}


def test_row_strong_keys_name_only_is_empty():
    assert row_strong_keys("", "", None) == set()


# ── Task 2: группировка ──

def _key_fn(row):
    return row_strong_keys(row.get("email", ""), row.get("phone", ""), row.get("hh"))


def test_group_merges_by_shared_phone():
    rows = [
        {"name": "Панасик", "phone": "+375 25 918 24 41", "funnel_list": "Android dev"},
        {"name": "Панасик", "phone": "+375 25 918 24 41", "funnel_list": "Unity"},
        {"name": "Другой", "phone": "+7 900 000 00 00", "funnel_list": "Unity dev"},
    ]
    groups = group_rows_by_person(rows, _key_fn)
    sizes = sorted(len(g) for g in groups)
    assert sizes == [1, 2]


def test_group_transitive_email_then_phone():
    rows = [
        {"name": "A", "email": "x@x.io"},
        {"name": "B", "email": "x@x.io", "phone": "+7 915 167 29 74"},
        {"name": "C", "phone": "89151672974"},
    ]
    groups = group_rows_by_person(rows, _key_fn)
    assert len(groups) == 1 and len(groups[0]) == 3


def test_group_name_only_rows_stay_separate():
    rows = [
        {"name": "Ким Евгений"},
        {"name": "Ким Евгений"},
    ]
    groups = group_rows_by_person(rows, _key_fn)
    assert len(groups) == 2


# ── Task 3: сборка прохождения и человека ──

def test_build_participation():
    row = {
        "funnel_list": "Android dev", "funnel_folder": "Sandbox - Мария",
        "status": "собес (1): нет", "date_created": "2026-07-08 19:17:06",
        "task_id": "86camy7yj", "url": "https://app.clickup.com/t/86camy7yj",
        "cf:Telegram": "@itegin", "cf:Источник": "hh", "cf:Пусто": "",
    }
    cf_headers = ["cf:Telegram", "cf:Источник", "cf:Пусто"]
    p = build_participation(row, cf_headers)
    assert p["vacancy_title"] == "Android dev"
    assert p["recruiter"] == "Мария"
    assert p["status"] == "собес (1): нет"
    assert p["task_id"] == "86camy7yj"
    assert {"question": "Telegram", "answer": "@itegin"} in p["anketa"]
    assert all(a["answer"] for a in p["anketa"])


def test_assemble_person_dedups_twin_passes():
    group = [
        {"name": "Панасик Т", "phone": "+375259182441", "funnel_list": "Android dev",
         "funnel_folder": "Sandbox - Мария", "status": "анкета: нет", "cf:A": "1"},
        {"name": "Панасик Т", "phone": "+375259182441", "funnel_list": "Android dev",
         "funnel_folder": "Sandbox - Мария", "status": "анкета: нет", "cf:B": "2"},
        {"name": "Панасик Т", "phone": "+375259182441", "funnel_list": "Unity",
         "funnel_folder": "Sandbox - Эльвира", "status": "анкета: нет", "cf:A": "3"},
    ]
    person = assemble_person(group, cf_headers=["cf:A", "cf:B"])
    parts = person["extra_data"]["participations"]
    assert len(parts) == 2
    android = next(p for p in parts if p["vacancy_title"] == "Android dev")
    qs = {a["question"] for a in android["anketa"]}
    assert qs == {"A", "B"}
    assert person["phone"] == "+375259182441"
    assert person["name"] == "Панасик Т"


def test_assemble_person_collects_all_task_ids():
    # Все task_id человека сохраняются — якорь идемпотентности при переимпорте.
    group = [
        {"name": "X", "phone": "+79000000000", "funnel_list": "A",
         "funnel_folder": "Sandbox - М", "task_id": "T2"},
        {"name": "X", "phone": "+79000000000", "funnel_list": "B",
         "funnel_folder": "Sandbox - М", "task_id": "T1"},
    ]
    person = assemble_person(group, cf_headers=[])
    assert person["extra_data"]["clickup_task_ids"] == ["T1", "T2"]


# ── Task 4/5: hh-экстрактор + идемпотентное слияние участий ──

def test_extract_hh_from_row():
    row = {"cf:Резюме hh": "https://hh.ru/resume/ABC?x=1", "name": "X"}
    assert extract_hh_from_row(row) == "hh.ru/resume/abc"
    assert extract_hh_from_row({"description": "смотри https://hh.ru/resume/ZZZ"}) == "hh.ru/resume/zzz"
    assert extract_hh_from_row({"name": "нет"}) is None


def test_extract_telegram_from_row():
    from api.services.clickup_import import extract_telegram_from_row
    assert extract_telegram_from_row({"cf:Telegram": "@hier_sonne", "name": "X"}) == "@hier_sonne"
    assert extract_telegram_from_row({"cf:Твой tg": "  @user  "}) == "@user"
    assert extract_telegram_from_row({"name": "нет тг"}) is None


def test_extract_email_from_row():
    row = {"cf:Укажи, пожалуйста, актуальную почту": "IVAN@X.io", "name": "X"}
    assert extract_email_from_row(row) == "ivan@x.io"
    assert extract_email_from_row({"description": "почта a.b@mail.ru тут"}) == "a.b@mail.ru"
    assert extract_email_from_row({"name": "нет почты"}) is None


def test_merge_participations_idempotent():
    existing = [{"vacancy_title": "Android dev", "recruiter": "Мария", "status": "x",
                 "anketa": [], "date": None, "task_id": "T1", "url": None}]
    incoming = [
        {"vacancy_title": "Android dev", "recruiter": "Мария", "status": "x",
         "anketa": [], "date": None, "task_id": "T1", "url": None},
        {"vacancy_title": "Unity", "recruiter": "Эльвира", "status": "y",
         "anketa": [], "date": None, "task_id": "T2", "url": None},
    ]
    merged = merge_participations(existing, incoming)
    assert len(merged) == 2
    assert {p["task_id"] for p in merged} == {"T1", "T2"}


def test_merge_participations_task_id_not_in_key():
    # Та же связка (воронка + рекрутёр + статус), но ДРУГОЙ task_id → один проход.
    existing = [{"vacancy_title": "Media Buyer", "recruiter": "Эльвира", "status": "собес",
                 "anketa": [], "date": None, "task_id": "T1", "url": None}]
    incoming = [{"vacancy_title": "Media Buyer", "recruiter": "Эльвира", "status": "собес",
                 "anketa": [], "date": None, "task_id": "T99", "url": None}]
    merged = merge_participations(existing, incoming)
    assert len(merged) == 1  # task_id в ключ не идёт — связка+статус совпали


def test_merge_participations_different_status_is_separate_pass():
    # Та же воронка+рекрутёр, но РАЗНЫЙ статус (этап) → разные прохождения.
    existing = [{"vacancy_title": "Android dev", "recruiter": "Мария", "status": "выполняет ТЗ",
                 "anketa": [], "date": None, "task_id": "T1", "url": None}]
    incoming = [{"vacancy_title": "Android dev", "recruiter": "Мария", "status": "вышел на ИС",
                 "anketa": [], "date": None, "task_id": "T2", "url": None}]
    merged = merge_participations(existing, incoming)
    assert len(merged) == 2  # разные этапы = отдельные анкеты


# ── Дистилляция структурных полей карточки (дата рождения / локация) ──

def test_extract_birthdate_from_description_iso():
    desc = "Что-то\nДата рождения: 1995-03-12T00:00:00+03:00\nещё"
    assert extract_birthdate(desc, today=date(2026, 7, 14)) == "1995-03-12"


def test_extract_birthdate_rejects_junk_year():
    # Год-мусор (форм-сабмит 2026 / слишком старый) отсекается.
    assert extract_birthdate("Дата рождения: 2026-01-01T00:00:00Z", today=date(2026, 7, 14)) is None
    assert extract_birthdate("Дата рождения: 1900-01-01T00:00:00Z", today=date(2026, 7, 14)) is None
    assert extract_birthdate("нет даты") is None


def test_birthdate_from_cf_column():
    # Реальный формат cf-колонки ClickUp: '2002-08-21 21:00:00' (без T, UTC).
    assert birthdate_from_cf("2002-08-21 21:00:00", today=date(2026, 7, 14)) == "2002-08-21"
    assert birthdate_from_cf("2026-01-01 00:00:00", today=date(2026, 7, 14)) is None  # мусор-год
    assert birthdate_from_cf("") is None


def test_distill_falls_back_to_cf_birthdate_when_no_description():
    # Реальный кейс: description пуст, дата рождения только в cf-колонке (UTC).
    group = [
        {"cf:Дата рождения": "2002-08-21 21:00:00",
         "cf:Местонахождение": '{"formatted_address": "Новокузнецк, Россия"}'},
    ]
    out = distill_person_fields(group)
    assert out["birth_date"] == "2002-08-21"
    assert out["location"] == "Новокузнецк, Россия"


def test_extract_location_formatted_address():
    raw = '{"location": {"lat": 55.7}, "formatted_address": "Москва, Россия"}'
    assert extract_location(raw) == "Москва, Россия"
    assert extract_location("не json") is None
    assert extract_location("") is None


def test_distill_person_fields_first_nonempty():
    group = [
        {"description": "нет полей", "cf:Местонахождение": ""},
        {"description": "Дата рождения: 1990-06-01T00:00:00+03:00",
         "cf:Местонахождение": '{"formatted_address": "Минск, Беларусь"}'},
    ]
    out = distill_person_fields(group)
    assert out["birth_date"] == "1990-06-01"
    assert out["location"] == "Минск, Беларусь"


def test_assemble_person_distills_structured_fields():
    group = [
        {"name": "Марк", "phone": "+375259182441", "funnel_list": "Android dev",
         "funnel_folder": "Sandbox - Мария", "status": "вышел ис",
         "description": "Дата рождения: 1993-09-20T00:00:00+03:00",
         "cf:Местонахождение": '{"formatted_address": "Гомель, Беларусь"}', "cf:A": "1"},
    ]
    person = assemble_person(group, cf_headers=["cf:A"])
    assert person["extra_data"]["birth_date"] == "1993-09-20"
    assert person["extra_data"]["location"] == "Гомель, Беларусь"


def test_assemble_person_different_status_same_funnel_are_separate():
    # Один человек, одна воронка, РАЗНЫЕ этапы (статусы) → две анкеты.
    group = [
        {"name": "Марк", "phone": "+375259182441", "funnel_list": "Unity",
         "funnel_folder": "Sandbox - Мария", "status": "выполняет ТЗ", "cf:A": "1"},
        {"name": "Марк", "phone": "+375259182441", "funnel_list": "Unity",
         "funnel_folder": "Sandbox - Мария", "status": "вышел на ИС", "cf:B": "2"},
    ]
    person = assemble_person(group, cf_headers=["cf:A", "cf:B"])
    parts = person["extra_data"]["participations"]
    assert len(parts) == 2
    assert {p["status"] for p in parts} == {"выполняет ТЗ", "вышел на ИС"}


# ── Комментарии ClickUp → плашки таймлайна (extra_data.participations[].notes) ──

def test_parse_comments_single():
    from api.services.clickup_import import parse_comments
    raw = "[2025-06-19 10:16:09 · Инна HR] по софтам не подходит"
    notes = parse_comments(raw, task_id="86c41wx9n")
    assert len(notes) == 1
    assert notes[0]["author_name"] == "Инна HR"
    assert notes[0]["date"] == "2025-06-19T10:16:09"
    assert notes[0]["text"] == "по софтам не подходит"
    assert notes[0]["id"] == "clickup:86c41wx9n:0"


def test_parse_comments_multiple_split_by_dashes():
    from api.services.clickup_import import parse_comments
    raw = (
        "[2025-06-17 12:41:00 · Инна HR] https://att.clickup.com/rec.webm\n"
        "---\n"
        "[2025-06-18 08:13:06 · Инна HR] фин собес 19.06 11:00 по мск"
    )
    notes = parse_comments(raw, task_id="T1")
    assert len(notes) == 2
    # URL записи собеседования → кликабельная ссылка с подписью-именем файла.
    assert notes[0]["text"] == '<a href="https://att.clickup.com/rec.webm">rec.webm</a>'
    assert notes[1]["text"] == "фин собес 19.06 11:00 по мск"
    assert [n["id"] for n in notes] == ["clickup:T1:0", "clickup:T1:1"]


def test_linkify_escapes_and_preserves_text():
    from api.services.clickup_import import _linkify_html
    # обычный текст со спецсимволами HTML — экранируется, тегов не появляется
    assert _linkify_html("a < b & c") == "a &lt; b &amp; c"
    # текст + ссылка: текст экранён, ссылка кликабельна
    got = _linkify_html("смотри https://x.io/f.webm тут")
    assert got == 'смотри <a href="https://x.io/f.webm">f.webm</a> тут'


def test_parse_comments_empty_and_no_markers():
    from api.services.clickup_import import parse_comments
    assert parse_comments("", task_id="T") == []
    assert parse_comments("   ", task_id="T") == []
    # текст без разметки [дата · автор] → один безымянный комментарий
    plain = parse_comments("просто заметка", task_id="T")
    assert len(plain) == 1
    assert plain[0]["text"] == "просто заметка"
    assert "author_name" not in plain[0]


def test_build_participation_carries_comments_as_notes():
    row = {
        "funnel_list": "CMO", "funnel_folder": "Найм - Анастасия",
        "status": "собес 1: нет", "task_id": "86c41wx9n",
        "comments": "[2025-06-19 10:16:09 · Инна HR] сильный кандидат",
        "cf:Уровень ЗП": "от 3000$",
    }
    p = build_participation(row, cf_headers=["cf:Уровень ЗП"])
    assert p["notes"][0]["text"] == "сильный кандидат"
    assert p["notes"][0]["author_name"] == "Инна HR"


def test_twin_participations_merge_notes_by_id():
    # Один человек, одна воронка+рекрутёр+статус, но две строки-задачи с разными
    # комментариями (зеркала в разных списках) → одно прохождение, заметки слиты.
    group = [
        {"name": "Марк", "phone": "+375259182441", "funnel_list": "Unity",
         "funnel_folder": "Sandbox - Мария", "status": "собес", "task_id": "A",
         "comments": "[2025-06-19 10:00:00 · Инна HR] запись есть"},
        {"name": "Марк", "phone": "+375259182441", "funnel_list": "Unity",
         "funnel_folder": "Sandbox - Мария", "status": "собес", "task_id": "B",
         "comments": "[2025-06-20 11:00:00 · Мария HR] берём"},
    ]
    person = assemble_person(group, cf_headers=[])
    parts = person["extra_data"]["participations"]
    assert len(parts) == 1
    texts = {n["text"] for n in parts[0]["notes"]}
    assert texts == {"запись есть", "берём"}


def test_merge_participations_backfills_notes_idempotently():
    # Старое прохождение без комментариев + повторный импорт с комментариями →
    # заметки додокладываются; ещё один такой же импорт ничего не двоит.
    existing = [{"vacancy_title": "CMO", "recruiter": "Анастасия", "status": "собес", "notes": []}]
    incoming = [{"vacancy_title": "CMO", "recruiter": "Анастасия", "status": "собес",
                 "notes": [{"id": "clickup:X:0", "text": "берём", "author_name": "Инна HR"}]}]
    merged = merge_participations(existing, incoming)
    assert len(merged) == 1
    assert len(merged[0]["notes"]) == 1
    # повторный прогон с тем же id — без дублей
    merged2 = merge_participations(merged, incoming)
    assert len(merged2[0]["notes"]) == 1


def test_merge_participations_upserts_edited_note_text():
    # Тот же комментарий (тот же id), но текст отредактирован → мердж обновляет
    # содержимое на актуальное, не задваивая заметку.
    existing = [{"vacancy_title": "CMO", "recruiter": "Инна", "status": "собес",
                 "notes": [{"id": "clickup:X:0", "text": "старый текст", "author_name": "Инна HR"}]}]
    incoming = [{"vacancy_title": "CMO", "recruiter": "Инна", "status": "собес",
                 "notes": [
                     {"id": "clickup:X:0", "text": "исправленный текст", "author_name": "Инна HR"},
                     {"id": "clickup:X:1", "text": "новый комментарий", "author_name": "Инна HR"},
                 ]}]
    merged = merge_participations(existing, incoming)
    notes = merged[0]["notes"]
    assert len(notes) == 2, notes
    by_id = {n["id"]: n for n in notes}
    assert by_id["clickup:X:0"]["text"] == "исправленный текст"   # обновился
    assert by_id["clickup:X:1"]["text"] == "новый комментарий"    # добавился
