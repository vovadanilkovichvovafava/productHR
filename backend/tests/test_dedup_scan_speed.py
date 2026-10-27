"""Сверка всей базы не должна вешать сервер (прод, 22.09.2026).

Корзины пере-скана строились по КАЖДОМУ слову ФИО: в «алек» падали все
Александры, Александровичи и Александровны — ~7,5 млн пар на 8 тыс. анкет,
~8 минут, в которые сервер не отвечал никому.
"""
import random
import time

from api.services.duplicate_matcher import (
    MAX_BUCKET_SIZE, CandidateKeys, _scan_pairs, identity_block_keys,
)
from api.services.similarity import build_dup_keys


def _names(n, seed=7):
    rnd = random.Random(seed)
    first = ["Александр", "Дмитрий", "Сергей", "Андрей", "Алексей", "Кирилл", "Иван",
             "Владимир", "Анна", "Мария", "Елена", "Ольга", "Александра"]
    roots = ["Бел", "Вол", "Гон", "Дуб", "Жук", "Зай", "Кар", "Лап", "Мор", "Нос",
             "Орл", "Пав", "Рыж", "Сав", "Тар", "Фил", "Хом", "Чер", "Шил", "Яков"]
    ends = ["ков", "ин", "ов", "ев", "ский", "енко", "ук", "ан"]
    pats = ["Александрович", "Сергеевич", "Андреевич", "Владимирович",
            "Александровна", "Сергеевна", ""]
    return [f"{rnd.choice(roots)}{rnd.choice(ends)} {rnd.choice(first)} {rnd.choice(pats)}".strip()
            for _ in range(n)]


def test_name_key_is_surname_and_first_name_pair():
    k = identity_block_keys(build_dup_keys(name="Иванов Кирилл Владимирович"))
    assert [x for x in k if x.startswith("n:")] == ["n:иван|кири"]
    # Транслит и перестановка — та же корзина.
    assert "n:иван|кири" in identity_block_keys(build_dup_keys(name="Kirill Ivanov"))
    # Одно имя или одно отчество ключом больше не бывают.
    assert not any(x in k for x in ("n:кири", "n:влад", "n:иван"))


def test_patronymic_like_surname_is_kept():
    # Фамилия «Петрович» похожа на отчество — её нельзя выкинуть из ключа.
    k = identity_block_keys(build_dup_keys(name="Петрович Иван Сергеевич"))
    assert "n:иван|петр" in k


def test_scan_of_8000_candidates_is_fast():
    items = [
        CandidateKeys(entity_id=i + 1, name=n, is_archived=True,
                      keys=build_dup_keys(name=n, phone=f"+7 916 {1000000 + i}"))
        for i, n in enumerate(_names(8000))
    ]
    started = time.perf_counter()
    _scan_pairs(items)
    # Было ~8 минут. Порог щедрый — чтобы тест не мигал на медленной машине.
    assert time.perf_counter() - started < 15


def test_real_pair_still_found():
    items = [
        CandidateKeys(1, "Иванов Кирилл Владимирович", False,
                      build_dup_keys(name="Иванов Кирилл Владимирович", phone="+7 917 200-40-60")),
        CandidateKeys(2, "Kirill Ivanov", True,
                      build_dup_keys(name="Kirill Ivanov", phone="8 917 2004060")),
    ]
    matches = _scan_pairs(items)
    assert [m.entity_id for m in matches[1]] == [2]
    assert matches[1][0].level == "exact"


def test_huge_bucket_is_skipped():
    # 300 разных людей с одним «телефоном»-заглушкой — не один человек.
    items = [
        CandidateKeys(i + 1, f"Человек{i}", True, build_dup_keys(name="", phone="+7 800 000-00-00"))
        for i in range(MAX_BUCKET_SIZE + 100)
    ]
    assert _scan_pairs(items) == {}
