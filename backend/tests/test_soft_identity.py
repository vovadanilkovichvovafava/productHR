"""Unit tests for the Level-2 soft-identity duplicate scorer (pure functions)."""
from api.services.similarity import (
    normalize_birth_date,
    age_from_birth,
    SOFT_WEIGHTS,
    SOFT_THRESHOLD,
)


class TestNormalizeBirthDate:
    def test_iso_passthrough(self):
        assert normalize_birth_date("1990-05-14") == "1990-05-14"

    def test_dotted_ru_format(self):
        assert normalize_birth_date("14.05.1990") == "1990-05-14"

    def test_slashed_format(self):
        assert normalize_birth_date("14/05/1990") == "1990-05-14"

    def test_year_month_only_returns_none(self):
        # Not a full date -> not usable as an exact-DOB key.
        assert normalize_birth_date("1990-05") is None

    def test_garbage_returns_none(self):
        assert normalize_birth_date("не указано") is None
        assert normalize_birth_date("") is None
        assert normalize_birth_date(None) is None


class TestAgeFromBirth:
    def test_age_from_iso(self):
        # Reference date passed explicitly to keep the test deterministic.
        assert age_from_birth("1990-05-14", today="2026-07-17") == 36

    def test_age_before_birthday_this_year(self):
        assert age_from_birth("1990-12-31", today="2026-07-17") == 35

    def test_invalid_returns_none(self):
        assert age_from_birth("garbage", today="2026-07-17") is None


class TestConstants:
    def test_weights_present(self):
        # Новая модель: имя/фамилия — единой связкой full_name (не порознь), +telegram.
        for key in ("full_name", "dob_exact", "age_pm1",
                    "phone7", "email_local", "telegram"):
            assert key in SOFT_WEIGHTS
        # Город убран из процента 22.09.2026: его вписывают любой.
        assert "city" not in SOFT_WEIGHTS

    def test_name_parts_are_not_scored_separately(self):
        # Заказчик: имя/фамилия НИКОГДА не считаются по отдельности.
        assert "last_name" not in SOFT_WEIGHTS
        assert "first_name" not in SOFT_WEIGHTS

    def test_full_name_alone_below_threshold(self):
        # Связка ФИО сама не должна флажить (полные тёзки существуют).
        assert SOFT_WEIGHTS["full_name"] < SOFT_THRESHOLD

    def test_threshold_is_int(self):
        assert isinstance(SOFT_THRESHOLD, int)


from api.services.similarity import name_part_match


class TestNamePartMatch:
    def test_exact_ru(self):
        assert name_part_match("Александр", "Александр") is True

    def test_translit(self):
        assert name_part_match("Александр", "Aleksandr") is True

    def test_one_typo(self):
        # Deliberate single-char typo still matches.
        assert name_part_match("Петров", "Петорв") is True
        assert name_part_match("Aleksandr", "Alexsandr") is True

    def test_diminutive(self):
        assert name_part_match("Александр", "Саша") is True
        assert name_part_match("Aleksandr", "Sasha") is True

    def test_initial_abbreviation(self):
        # "А." abbreviates "Александр".
        assert name_part_match("Александр", "А.") is True

    def test_different_names_do_not_match(self):
        assert name_part_match("Александр", "Дмитрий") is False
        assert name_part_match("Петров", "Сидоров") is False

    def test_translit_does_not_collapse_distinct_surnames(self):
        # Жалоба Марии (2026-07-23): «Бойков» и «Быков» помечались как одна
        # фамилия. В латинице они схлопываются (boykov/bykov = 1 символ), т.к.
        # и 'й', и 'ы' транслитерируются в 'y'. По-русски различаются на 2 буквы
        # ('ой' vs 'ы') — опечатку меряем в кириллице, поэтому НЕ матч.
        assert name_part_match("Бойков", "Быков") is False
        # настоящая кириллическая опечатка на 1 символ — по-прежнему матч:
        assert name_part_match("Быков", "Быкав") is True
        # и кросс-алфавитное точное совпадение не сломалось:
        assert name_part_match("Быков", "Bykov") is True

    def test_homoglyph_latin_letter_still_matches(self):
        # Подмена буквы латинским двойником (уход от дедупа): русская С (U+0421)
        # заменена латинской C (U+0043). Визуально одно слово — матчер тоже.
        assert name_part_match("Соколов", "Cоколов") is True   # C латинская
        assert name_part_match("Марина", "Mарина") is True     # M латинская
        # чисто латинское имя при этом не ломается (законная транслитерация):
        assert name_part_match("Соколов", "Sokolov") is True

    def test_empty_is_false(self):
        assert name_part_match("", "Александр") is False
        assert name_part_match("Александр", "") is False


from api.services.similarity import score_soft_identity, SoftScore


def _keys(**kw):
    """Build a soft-key dict matching build_dup_keys' soft-key contract."""
    base = {
        "first_names": set(), "last_names": set(),
        "birth_norm": None, "age": None,
        "phones7": set(), "email_locals": set(), "tg_names": set(), "cities": set(),
    }
    base.update(kw)
    return base


# Новая модель (заказчик, 2026-07-27): имя/фамилия учитываются ТОЛЬКО жёсткой
# связкой full_name(50); связка сама не флажит (тёзки), но +сильный сигнал — да.
class TestScoreSoftIdentity:
    def test_full_name_alone_below_threshold(self):
        # Полные тёзки «Иванов Иван» существуют — связка сама флаг не поднимает.
        a = _keys(first_names={"иван"}, last_names={"иванов"})
        b = _keys(first_names={"иван"}, last_names={"ivanov"})
        r = score_soft_identity(a, b)
        assert r.confidence == 50          # full_name
        assert r.components == 1
        assert r.is_flag is False

    def test_full_name_plus_phone_flags(self):
        a = _keys(first_names={"александр"}, last_names={"петров"}, phones7={"1234567"})
        b = _keys(first_names={"саша"}, last_names={"petrov"}, phones7={"1234567"})
        r = score_soft_identity(a, b)
        assert r.confidence == 85          # 50 + 35
        assert r.components >= 2
        assert r.is_flag is True

    def test_full_name_plus_dob_flags(self):
        a = _keys(first_names={"александр"}, last_names={"петров"}, birth_norm="1990-05-14")
        b = _keys(first_names={"aleksandr"}, last_names={"petrov"}, birth_norm="1990-05-14")
        r = score_soft_identity(a, b)
        assert r.confidence == 90          # 50 + 40
        assert r.is_flag is True

    def test_full_name_plus_weak_below_threshold(self):
        # Связка + один лишь возраст(12) = 62 < 65: тёзки одного возраста — не дубль.
        a = _keys(first_names={"иван"}, last_names={"петров"}, age=30)
        b = _keys(first_names={"иван"}, last_names={"petrov"}, age=30)
        r = score_soft_identity(a, b)
        assert r.confidence == 62          # 50 + 12
        assert r.is_flag is False

    def test_lone_name_part_is_not_scored(self):
        # Одна фамилия (без имени) или одно имя (без фамилии) — 0 баллов, 0 сигналов.
        only_last = score_soft_identity(
            _keys(last_names={"петров"}), _keys(last_names={"петров"}))
        assert only_last.confidence == 0 and only_last.components == 0
        only_first = score_soft_identity(
            _keys(first_names={"александр"}), _keys(first_names={"александр"}))
        assert only_first.confidence == 0 and only_first.components == 0

    def test_two_contacts_flag_without_name(self):
        # Смена личины: ФИО разное, но почта(до @)+телефон те же → 35+35=70 флажит.
        a = _keys(last_names={"иванов"}, first_names={"иван"},
                  phones7={"1234567"}, email_locals={"ivan.petrov"})
        b = _keys(last_names={"сидоров"}, first_names={"пётр"},
                  phones7={"1234567"}, email_locals={"ivan.petrov"})
        r = score_soft_identity(a, b)
        assert r.confidence == 70          # phone7 + email_local (связки нет)
        assert r.is_flag is True

    def test_one_contact_alone_never_flags(self):
        a = _keys(phones7={"1234567"})
        b = _keys(phones7={"1234567"})
        r = score_soft_identity(a, b)
        assert r.components == 1
        assert r.is_flag is False

    def test_dob_alone_never_flags(self):
        a = _keys(birth_norm="1990-05-14")
        b = _keys(birth_norm="1990-05-14")
        r = score_soft_identity(a, b)
        assert r.components == 1
        assert r.is_flag is False

    def test_telegram_in_soft_scoring(self):
        # Telegram теперь и в жёлтом: связка(50) + telegram(35) = 85 флажит.
        a = _keys(first_names={"иван"}, last_names={"иванов"}, tg_names={"ivan_hr"})
        b = _keys(first_names={"иван"}, last_names={"ivanov"}, tg_names={"ivan_hr"})
        r = score_soft_identity(a, b)
        assert r.confidence == 85
        assert any("telegram" in reason.lower() for reason in r.reasons)
        assert r.is_flag is True

    def test_junk_telegram_not_scored(self):
        # Мусорный ярлык источника (hh_b2b) — не личный хэндл, в счёт не идёт.
        a = _keys(first_names={"иван"}, last_names={"иванов"}, tg_names={"hh_b2b"})
        b = _keys(first_names={"иван"}, last_names={"ivanov"}, tg_names={"hh_b2b"})
        r = score_soft_identity(a, b)
        assert r.confidence == 50          # только связка, telegram отсеян
        assert r.is_flag is False

    def test_phone7_plus_dob_flags(self):
        # phone7(35)+dob(40)=75 >= 65 → флажит (телефон сменил код страны, ДР то же).
        a = _keys(phones7={"1234567"}, birth_norm="1990-05-14")
        b = _keys(phones7={"1234567"}, birth_norm="1990-05-14")
        r = score_soft_identity(a, b)
        assert r.confidence == 75
        assert r.is_flag is True

    def test_email_local_plus_dob_flags(self):
        a = _keys(email_locals={"ivan.petrov"}, birth_norm="1988-01-02")
        b = _keys(email_locals={"ivan.petrov"}, birth_norm="1988-01-02")
        r = score_soft_identity(a, b)
        assert r.confidence == 75
        assert r.is_flag is True

    def test_reasons_are_human_readable(self):
        a = _keys(first_names={"александр"}, last_names={"петров"}, phones7={"1234567"})
        b = _keys(first_names={"саша"}, last_names={"petrov"}, phones7={"1234567"})
        r = score_soft_identity(a, b)
        assert any("фамилия и имя" in reason.lower() for reason in r.reasons)

    def test_confidence_capped_at_100(self):
        a = _keys(first_names={"иван"}, last_names={"петров"},
                  birth_norm="1990-05-14", phones7={"1234567"},
                  email_locals={"ivan.petrov"}, tg_names={"ivan_hr"}, cities={"минск"})
        r = score_soft_identity(a, a)  # identical keys both sides -> all signals hit
        assert r.confidence == 100  # 50+40+35+35+35+8 = 203, capped at 100


from api.services.similarity import build_dup_keys


class TestBuildDupKeysSoft:
    def test_soft_keys_present(self):
        keys = build_dup_keys(
            name="Петров Александр",
            email="ivan.petrov@gmail.com",
            phone="+7 916 123-45-67",
            telegram="@petrov_a",
            extra_data={"birth_date": "14.05.1990", "location": "Минск"},
        )
        assert keys["last_names"] == {"петров"}
        assert keys["first_names"] == {"александр"}
        assert keys["birth_norm"] == "1990-05-14"
        assert keys["age"] is not None
        assert "1234567" in keys["phones7"]
        assert "ivan.petrov" in keys["email_locals"]
        assert "petrov_a" in keys["tg_names"]
        assert "минск" in keys["cities"]

    def test_homoglyph_name_normalized_in_keys(self):
        # «Cоколов» (латинская C) должен дать те же ключи, что честный «Соколов».
        spoofed = build_dup_keys(name="Cоколов Пётр")
        honest = build_dup_keys(name="Соколов Пётр")
        assert spoofed["last_names"] == honest["last_names"] == {"соколов"}

    def test_single_word_name_goes_to_first_only(self):
        keys = build_dup_keys(name="Саша")
        assert keys["first_names"] == {"саша"}
        assert keys["last_names"] == set()

    def test_position_junk_name_excluded_from_soft(self):
        # looks_like_person_name already gates name_ok; soft name keys must respect it.
        keys = build_dup_keys(name="Flutter Developer, Минск")
        assert keys["last_names"] == set()
        assert keys["first_names"] == set()


class TestNameOrderIndependence:
    def test_swapped_order_full_name_matches(self):
        # Связка ловит перестановку (Фамилия Имя ↔ Имя Фамилия); +телефон → флаг.
        a = _keys(last_names={"петров"}, first_names={"александр"}, phones7={"1234567"})
        b = _keys(last_names={"sasha"}, first_names={"petrov"}, phones7={"1234567"})  # western order
        r = score_soft_identity(a, b)
        assert r.confidence == 85          # full_name(50) + phone7(35)
        assert r.is_flag is True

    def test_partial_name_overlap_is_not_a_full_name(self):
        # Совпала только фамилия (имена разные) → связки НЕТ, даже с ДР не хватает
        # именной части: 40(dob) < 65, один сигнал. Однофамильцы не слипаются.
        a = _keys(last_names={"петров"}, first_names={"дмитрий"}, birth_norm="1990-01-01")
        b = _keys(last_names={"petrov"}, first_names={"сергей"}, birth_norm="1990-01-01")
        r = score_soft_identity(a, b)
        assert r.confidence == 40          # только dob_exact, связки нет
        assert r.is_flag is False

    def test_swap_does_not_invent_matches(self):
        a = _keys(last_names={"иванов"}, first_names={"пётр"})
        b = _keys(last_names={"сидоров"}, first_names={"павел"})
        r = score_soft_identity(a, b)
        assert r.components == 0
