"""
Сервис поиска похожих кандидатов и детекции дубликатов.

Предоставляет:
- find_similar() - поиск похожих кандидатов по навыкам, опыту, зарплате
- calculate_similarity() - расчет сходства между двумя кандидатами
- detect_duplicates() - детекция возможных дубликатов
- merge_entities() - объединение дубликатов
"""
from typing import List, Optional, Set, Dict, Any, Tuple
from dataclasses import dataclass, field
from sqlalchemy import select, or_, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
import re
import logging

from ..models.database import Entity, EntityType, Organization, User

logger = logging.getLogger("hr-analyzer.similarity")

# Таблица транслитерации русский -> английский
TRANSLIT_RU_EN = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
}

# Альтернативные варианты транслитерации
TRANSLIT_ALTERNATIVES = {
    'а': ['a'],
    'б': ['b'],
    'в': ['v', 'w'],
    'г': ['g', 'h'],
    'д': ['d'],
    'е': ['e', 'ye'],
    'ё': ['yo', 'e', 'io'],
    'ж': ['zh', 'j'],
    'з': ['z'],
    'и': ['i', 'y', 'ee'],
    'й': ['y', 'i', 'j'],
    'к': ['k', 'c'],
    'л': ['l'],
    'м': ['m'],
    'н': ['n'],
    'о': ['o'],
    'п': ['p'],
    'р': ['r'],
    'с': ['s', 'c'],
    'т': ['t'],
    'у': ['u', 'ou'],
    'ф': ['f', 'ph'],
    'х': ['kh', 'h', 'x'],
    'ц': ['ts', 'c', 'tz'],
    'ч': ['ch', 'tch'],
    'ш': ['sh'],
    'щ': ['shch', 'sch'],
    'ъ': ['', 'ie'],
    'ы': ['y', 'i'],
    'ь': ['', "'"],
    'э': ['e'],
    'ю': ['yu', 'iu', 'u'],
    'я': ['ya', 'ia', 'a']
}

# Таблица транслитерации английский -> русский (обратная)
TRANSLIT_EN_RU = {
    'a': 'а', 'b': 'б', 'c': 'к', 'd': 'д', 'e': 'е', 'f': 'ф', 'g': 'г',
    'h': 'х', 'i': 'и', 'j': 'дж', 'k': 'к', 'l': 'л', 'm': 'м', 'n': 'н',
    'o': 'о', 'p': 'п', 'q': 'к', 'r': 'р', 's': 'с', 't': 'т', 'u': 'у',
    'v': 'в', 'w': 'в', 'x': 'кс', 'y': 'й', 'z': 'з',
    # Диграфы
    'ch': 'ч', 'sh': 'ш', 'zh': 'ж', 'ts': 'ц', 'ya': 'я', 'yu': 'ю',
    'yo': 'ё', 'kh': 'х', 'shch': 'щ'
}


@dataclass
class SimilarCandidate:
    """Результат поиска похожего кандидата."""
    entity_id: int
    entity_name: str
    similarity_score: int  # 0-100
    common_skills: List[str] = field(default_factory=list)
    similar_experience: bool = False
    similar_salary: bool = False
    similar_location: bool = False
    match_reasons: List[str] = field(default_factory=list)
    # Detailed comparison data
    entity1_skills: List[str] = field(default_factory=list)
    entity2_skills: List[str] = field(default_factory=list)
    entity1_experience: Optional[int] = None
    entity2_experience: Optional[int] = None
    entity1_salary_min: Optional[int] = None
    entity1_salary_max: Optional[int] = None
    entity2_salary_min: Optional[int] = None
    entity2_salary_max: Optional[int] = None
    entity1_location: Optional[str] = None
    entity2_location: Optional[str] = None
    entity1_position: Optional[str] = None
    entity2_position: Optional[str] = None


@dataclass
class DuplicateCandidate:
    """Результат детекции дубликата."""
    entity_id: int
    entity_name: str
    confidence: int  # 0-100 (вероятность дубликата) — та же шкала, что у баннера
    match_reasons: List[str] = field(default_factory=list)
    matched_fields: Dict[str, Tuple[str, str]] = field(default_factory=dict)  # field: (value1, value2)
    strength: str = ""                 # тир совпадения (source/email/…/soft/text)
    signals: List["DupSignal"] = field(default_factory=list)
    level: str = "possible"            # exact — красный, possible — жёлтый


@dataclass
class SoftScore:
    """Результат Level-2 мягкого скоринга личности между двумя наборами ключей."""
    confidence: int          # 0-100
    components: int          # сколько независимых сигналов сработало
    reasons: List[str] = field(default_factory=list)   # причины словами (для UI)
    detail: List[str] = field(default_factory=list)    # 'first_name(+25)' — для логов/dry-run

    @property
    def is_flag(self) -> bool:
        return self.confidence >= SOFT_THRESHOLD and self.components >= SOFT_MIN_COMPONENTS


def transliterate_ru_to_en(text: str) -> str:
    """Транслитерация русского текста в английский."""
    result = []
    text_lower = text.lower()
    for char in text_lower:
        if char in TRANSLIT_RU_EN:
            result.append(TRANSLIT_RU_EN[char])
        else:
            result.append(char)
    return ''.join(result)


def transliterate_en_to_ru(text: str) -> str:
    """Транслитерация английского текста в русский."""
    result = []
    text_lower = text.lower()
    i = 0
    while i < len(text_lower):
        # Проверяем диграфы (от длинных к коротким)
        matched = False
        for length in [4, 3, 2]:  # shch, ya, ch
            if i + length <= len(text_lower):
                substr = text_lower[i:i+length]
                if substr in TRANSLIT_EN_RU:
                    result.append(TRANSLIT_EN_RU[substr])
                    i += length
                    matched = True
                    break
        if not matched:
            char = text_lower[i]
            if char in TRANSLIT_EN_RU:
                result.append(TRANSLIT_EN_RU[char])
            else:
                result.append(char)
            i += 1
    return ''.join(result)


def fold_yo(s: Optional[str]) -> str:
    """Ё → Е. Точки над Ё в русском письме факультативны, поэтому один и тот же
    человек попадает в базу и «Дёминым», и «Деминым». Для сравнения имён это одна
    буква — иначе дедуп считает две записи РАЗНЫМИ людьми и не предлагает слияние.

    Шире матч не становится: свёртка не склеивает разные буквы, а убирает разницу
    в необязательном диакритике. Тот же фолд применяется в поиске (search_index)."""
    return (s or "").replace("ё", "е").replace("Ё", "Е")


# Латинские буквы, ВИЗУАЛЬНО неотличимые от кириллических (Unicode confusables).
# Приём ухода от дедупа: в русском имени одну-две буквы подменяют латинскими
# двойниками — «Cоколов» (C латинская, U+0043) выглядит как «Соколов»
# (U+0421), но для матчера это разные строки. Держим и прописные, и строчные:
# подмена обычно копирует видимый текст, где регистр смешан, а fold применяем
# ДО .lower(), чтобы 'B'→'В' не потерялось (строчные b/в уже не двойники).
_HOMOGLYPH_LAT_TO_CYR = {
    "A": "А", "B": "В", "C": "С", "E": "Е", "H": "Н", "K": "К", "M": "М",
    "O": "О", "P": "Р", "T": "Т", "X": "Х", "Y": "У",
    "a": "а", "c": "с", "e": "е", "o": "о", "p": "р", "x": "х", "y": "у", "k": "к",
}


def fold_homoglyphs(s: Optional[str]) -> str:
    """Латинские буквы-двойники → кириллица, но ТОЛЬКО в словах, где кириллица уже
    есть. Чисто латинское имя («Sokolov») не трогаем — это законная транслитерация,
    её разбирает transliterate_en_to_ru; а вот смешанное «Cоколов» лечим в «Соколов».
    Так подмена буквы перестаёт прятать дубль, а обычные латинские имена не портятся."""
    if not s:
        return s or ""
    has_cyr = any(("а" <= ch <= "я") or ch in ("ё", "Ё") or ("А" <= ch <= "Я") for ch in s)
    if not has_cyr:
        return s
    return "".join(_HOMOGLYPH_LAT_TO_CYR.get(ch, ch) for ch in s)


def generate_name_variants(name: str) -> Set[str]:
    """
    Генерация вариантов написания имени для поиска дубликатов.

    Возвращает набор возможных написаний с учетом:
    - Регистра
    - Транслитерации rus<->eng
    - Альтернативных транслитераций
    """
    variants = set()
    # Гомоглифы лечим до lower/транслита: «Cоколов» → «соколов», иначе латинская C
    # осталась бы в блобе и поиск по «Соколов» не нашёл бы подменённую запись.
    name_lower = fold_homoglyphs(name).lower().strip()
    variants.add(name_lower)

    # Определяем язык имени
    has_cyrillic = bool(re.search(r'[а-яё]', name_lower))
    has_latin = bool(re.search(r'[a-z]', name_lower))

    if has_cyrillic:
        # Русское имя -> генерируем английские варианты
        en_variant = transliterate_ru_to_en(name_lower)
        variants.add(en_variant)

        # Генерируем альтернативные транслитерации для каждой части имени
        parts = name_lower.split()
        for part in parts:
            # Стандартная транслитерация части
            en_part = transliterate_ru_to_en(part)
            variants.add(en_part)

    if has_latin:
        # Английское имя -> генерируем русские варианты
        ru_variant = transliterate_en_to_ru(name_lower)
        variants.add(ru_variant)

        # Отдельные части имени
        parts = name_lower.split()
        for part in parts:
            ru_part = transliterate_en_to_ru(part)
            variants.add(ru_part)

    # Добавляем варианты без пробелов и с разделителями
    for v in list(variants):
        variants.add(v.replace(' ', ''))
        variants.add(v.replace(' ', '-'))
        variants.add(v.replace(' ', '_'))

    # Ё≡Е поверх готового набора: свёрнутая форма пересекается с вариантами
    # человека, записанного через Е, — включая случай «Dyomin» vs «Демин»
    # (латиница разворачивается в «дёмин», а он свернётся в «демин»).
    variants |= {fold_yo(v) for v in variants}

    return variants


def _name_word_variants(word: str) -> Set[str]:
    """Варианты ОДНОГО слова имени (само + транслитерации rus<->eng + Ё≡Е).
    Гомоглифы (латинские двойники кириллицы) лечим ПЕРВЫМ шагом — до .lower() и
    транслита, иначе «Cоколов» ушёл бы в транслит как мусор."""
    w = fold_homoglyphs(word or "").strip("-_.,").lower()
    out = {w}
    if re.search(r'[а-яё]', w):
        out.add(transliterate_ru_to_en(w))
    if re.search(r'[a-z]', w):
        out.add(transliterate_en_to_ru(w))
    # Свёртка поверх готового набора — так «дёмин»/«dyomin» и «демин»/«demin»
    # пересекаются хотя бы по одной форме, как бы ни была записана пара.
    out |= {fold_yo(v) for v in out}
    out.discard("")
    return out


def count_shared_name_words(name1: str, name2: str) -> int:
    """Сколько РАЗНЫХ слов ФИО совпадают (каждое — по raw/транслит).

    Считаем именно СЛОВА, а не варианты: общее одно имя «Семён» = 1 слово, а не 2
    из-за пары «семён»+«semyon». Это режет ложные матчи разных людей с общим
    именем («Титов Семён» vs «Кондратьев Семён») — у них совпадает 1 слово."""
    words1 = [_name_word_variants(w) for w in (name1 or "").split()
              if len(w.strip("-_.,")) >= 2]
    words2 = [_name_word_variants(w) for w in (name2 or "").split()
              if len(w.strip("-_.,")) >= 2]
    used: Set[int] = set()
    count = 0
    for v1 in words1:
        for j, v2 in enumerate(words2):
            if j in used:
                continue
            if v1 & v2:
                count += 1
                used.add(j)
                break
    return count


# Уменьшительные <-> полные (минимальный практичный набор; расширяется по мере
# калибровки). Ключи и значения — в нижнем регистре, без транслита (транслит
# добавляется через _name_word_variants на этапе сравнения).
_DIMINUTIVES = {
    "александр": {"саша", "шура", "саня"},
    "алексей": {"лёша", "леша", "алёша", "алеша"},
    "дмитрий": {"дима", "митя"},
    "евгений": {"женя"},
    "екатерина": {"катя"},
    "мария": {"маша"},
    "михаил": {"миша"},
    "владимир": {"вова", "володя"},
    "анатолий": {"толя"},
    "николай": {"коля"},
    "сергей": {"серёжа", "сережа"},
}


def _levenshtein_le1(a: str, b: str) -> bool:
    """Расстояние Левенштейна между a и b не больше 1 (равны / 1 замена / 1
    вставка-удаление / соседняя перестановка двух букв — частая опечатка).
    Дешёвая проверка без построения полной матрицы."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:  # одна замена или одна соседняя перестановка?
        diff_idx = [i for i in range(la) if a[i] != b[i]]
        if len(diff_idx) == 1:
            return True
        if len(diff_idx) == 2:
            i, j = diff_idx
            if j == i + 1 and a[i] == b[j] and a[j] == b[i]:
                return True
        return False
    # разница длины 1 — одна вставка/удаление
    short, long = (a, b) if la < lb else (b, a)
    i = j = 0
    edited = False
    while i < len(short) and j < len(long):
        if short[i] == long[j]:
            i += 1
            j += 1
        elif edited:
            return False
        else:
            edited = True
            j += 1
    return True


def _diminutive_group(word: str) -> Set[str]:
    """Все эквивалентные формы имени: полное + все уменьшительные обеих сторон.
    Словарь хранит только кириллицу, поэтому ищем совпадение не только по
    исходному слову, но и по его транслит-варианту (иначе 'Aleksandr' не
    находит уменьшительные для 'Александр')."""
    w = (word or "").strip("-_.,").lower()
    candidates = _name_word_variants(w) | {w}
    forms = {w}
    for full, dims in _DIMINUTIVES.items():
        if candidates & ({full} | dims):
            forms.add(full)
            forms.update(dims)
    return forms


def name_part_match(a: str, b: str) -> bool:
    """Совпадает ли ОДНА часть имени (имя ИЛИ фамилия) с учётом: транслита RU<->EN,
    опечатки <=1 символа, уменьшительных форм и инициала ('А.' == 'Александр').
    Пустые -> False."""
    wa = (a or "").strip("-_.,").lower()
    wb = (b or "").strip("-_.,").lower()
    if not wa or not wb:
        return False

    # Инициал: одна буква одной стороны == первая буква другой (с учётом транслита).
    def _first_letters(w: str) -> Set[str]:
        return {v[:1] for v in _name_word_variants(w) if v}
    if len(wa) == 1 or len(wb) == 1:
        return bool(_first_letters(wa) & _first_letters(wb))

    # Полный набор вариантов каждой стороны: транслит (через _name_word_variants)
    # для каждой уменьшительно-эквивалентной формы.
    def _all_variants(w: str) -> Set[str]:
        out: Set[str] = set()
        for form in _diminutive_group(w):
            out |= _name_word_variants(form)
        return out
    va, vb = _all_variants(wa), _all_variants(wb)
    if va & vb:
        return True
    # Опечатка <=1 — меряем по КАНОНИЧНОЙ кириллической форме каждого слова, а НЕ
    # по декартову произведению всех транслит-вариантов. Транслит в латиницу
    # необратимо lossy: и 'й', и 'ы' дают 'y' (см. TRANSLIT_RU_EN), поэтому в
    # латинице РАЗНЫЕ русские фамилии сходятся в один символ — «Бойков»→boykov и
    # «Быков»→bykov отличаются на 1, и старый код давал ложную «Фамилию совпала»
    # (жалоба Марии, 2026-07-23), хотя по-русски Бойков/Быков различаются на 2.
    # Канон берём от ИСХОДНОГО слова (кириллицу как есть; латиницу — обратным
    # транслитом ОДИН раз), не от va/vb: там уже лежат латинские производные
    # кириллицы (bykov), которые вернули бы то же схлопывание.
    def _canon(w: str) -> str:
        return w if re.search(r"[а-яё]", w) else transliterate_en_to_ru(w)
    ca = {_canon(f) for f in _diminutive_group(wa)}
    cb = {_canon(f) for f in _diminutive_group(wb)}
    return any(_levenshtein_le1(x, y) for x in ca for y in cb)


def _any_part_match(set_a: Set[str], set_b: Set[str]) -> bool:
    """Есть ли пара (a,b) из двух наборов, совпадающая по name_part_match."""
    return any(name_part_match(a, b) for a in set_a for b in set_b)


def _full_name_match(a: dict, b: dict) -> bool:
    """Совпала ли СВЯЗКА Фамилия+Имя — оба слова, в любом порядке. Имя и фамилия
    по ОТДЕЛЬНОСТИ дубль не поднимают (заказчик: тёзок и однофамильцев — тьма),
    поэтому здесь единственный «именной» сигнал жёлтого скоринга.

    Требуем, чтобы у обеих сторон были ОБЕ части (фамилия и имя): запись из одного
    слова («Саша», «Хабибуллин») связку не образует и в жёлтый не идёт. Порядок не
    важен (Фамилия Имя ↔ Имя Фамилия), каждое слово сверяется name_part_match'ем
    (транслит, гомоглифы, Ё, опечатка ≤1)."""
    la, fa = a.get("last_names") or set(), a.get("first_names") or set()
    lb, fb = b.get("last_names") or set(), b.get("first_names") or set()
    if not (la and fa and lb and fb):
        return False
    # Разные отчества у обеих сторон — разные люди (Эльвира, 2026-09-16:
    # четыре «Иванова Кирилла» с разными отчествами шли как точные дубли).
    pa, pb = a.get("patronymics") or set(), b.get("patronymics") or set()
    if pa and pb and not _any_part_match(pa, pb):
        return False
    straight = _any_part_match(la, lb) and _any_part_match(fa, fb)
    swapped = _any_part_match(la, fb) and _any_part_match(fa, lb)
    return straight or swapped


def score_soft_identity(a: dict, b: dict) -> SoftScore:
    """Взвешенный мягкий скоринг «тот же человек» между двумя наборами soft-ключей
    (см. build_dup_keys). НЕ использует места работы/образование (отвергнуто как
    признак личности). ДР в одиночку не флажит (требуется >=2 компонента)."""
    score = 0
    components = 0
    reasons: List[str] = []
    detail: List[str] = []

    def _hit(weight_key: str, reason: str):
        nonlocal score, components
        w = SOFT_WEIGHTS[weight_key]
        score += w
        components += 1
        reasons.append(reason)
        detail.append(f"{weight_key}(+{w})")

    if _full_name_match(a, b):
        _hit("full_name", "Фамилия и имя совпали")

    ba, bb = a.get("birth_norm"), b.get("birth_norm")
    if ba and bb and ba == bb:
        _hit("dob_exact", "Дата рождения совпала")
    else:
        aa, ab = a.get("age"), b.get("age")
        if aa is not None and ab is not None and abs(aa - ab) <= 1:
            _hit("age_pm1", "Возраст совпадает (±1 год)")

    if (a.get("phones7") or set()) & (b.get("phones7") or set()):
        _hit("phone7", "Последние 7 цифр телефона совпали")
    if (a.get("email_locals") or set()) & (b.get("email_locals") or set()):
        _hit("email_local", "Email до @ совпал")
    # Telegram в жёлтом (раньше был только в красном): общий личный @хэндл — сильный
    # сигнал «тот же человек». Мусорные ярлыки источника (hh_b2b, telegram) отсеяны
    # is_matchable_telegram ещё в tg_names.
    a_tg = {t for t in (a.get("tg_names") or set()) if is_matchable_telegram(t)}
    b_tg = {t for t in (b.get("tg_names") or set()) if is_matchable_telegram(t)}
    if a_tg & b_tg:
        _hit("telegram", "Telegram совпал")

    return SoftScore(confidence=min(score, 100), components=components,
                     reasons=reasons, detail=detail)


# Окончания отчеств — кириллица и транслит. «ич» намеренно НЕ в списке отдельно:
# по нему сербские/черногорские фамилии (Петрович, Радич) принимались бы за
# отчества. Ловим только полные формы -ович/-евич/-ьич и женские -овна/-евна/-ична.
_PATRONYMIC_SUFFIXES = (
    "ович", "евич", "ьич", "овна", "евна", "ична", "инична", "івна",
    "ovich", "evich", "ovna", "evna", "ichna",
)


def patronymics_of(name: str) -> Set[str]:
    """Слова, похожие на отчество. Пусто, если в записи меньше трёх слов.

    Порядок слов в наших источниках плавает («Кирилл Евгеньевич Борисов» ↔
    «Борисов Кирилл Евгеньевич»), поэтому ищем по окончанию в любой позиции, а не
    по третьему слову. Возвращаем НАБОР: у сербской фамилии «Петрович» под правило
    попадёт и фамилия, и отчество — тогда сравнение наборов не даст ложный
    конфликт, потому что фамилия совпадёт у обеих сторон.
    """
    words = [w.strip("-_.,").lower() for w in fold_homoglyphs(name or "").split()]
    words = [w for w in words if w]
    if len(words) < 3:
        return set()
    return {w for w in words if w.endswith(_PATRONYMIC_SUFFIXES)}


def patronymic_conflict(name1: str, name2: str) -> bool:
    """Отчества есть у ОБОИХ и НИ ОДНО не совпадает → это разные люди.

    Заказчик (Эльвира, 2026-09-16): «Иванов Кирилл Владимирович» поднимал четырёх
    однофамильцев-тёзок с РАЗНЫМИ отчествами, и все они показывались как «точное
    совпадение». Отчество — единственное, что их различает, и игнорировать его
    нельзя. Консервативно: если хотя бы у одной стороны отчества нет («Векленко
    Кирилл» ↔ «Векленко Кирилл Дмитриевич»), конфликта НЕТ — это по-прежнему дубль.
    Сравниваем через name_part_match, поэтому инициал («В.»), транслит
    («Vladimirovich») и опечатка ≤1 конфликтом не считаются.
    """
    pa, pb = patronymics_of(name1), patronymics_of(name2)
    if not pa or not pb:
        return False
    return not _any_part_match(pa, pb)


def names_match_surname_firstname(name1: str, name2: str) -> bool:
    """Совпадают ли ФИО по «Фамилия + Имя» (первые два слова, порядок МОЖЕТ быть
    обратным, каждое слово — с учётом транслитерации). Ловит «Векленко Кирилл»
    ↔ «Векленко Кирилл Дмитриевич» (с отчеством и без) И «Vlada Vertinskaya» ↔
    «Vertinskaya Vlada» (имя/фамилия в разном порядке — типично для источников
    вроде LinkedIn vs hh.ru, 2026-07-14). НЕ матчит разных однофамильцев-тёзок
    по одному лишь имени/отчеству («Борисов Кирилл Евгеньевич» ↔ «Сапрыкин
    Кирилл Евгеньевич» — фамилии разные → НЕ дубль), т.к. требуем совпадения
    ОБОИХ слов по чёткому паросочетанию (каждое слово одного имени должно
    совпасть с РАЗНЫМ словом другого — прямая ИЛИ обратная пара, не одно и то
    же слово дважды). Полное совпадение ФИО — частный случай (тоже совпадёт).

    Каждое слово сверяется через name_part_match, поэтому связка терпит ВСЕ те же
    нюансы, что и одна часть: транслит RU↔EN, смену алфавита целиком или по одной
    части, гомоглифы (латинская C в «Cоколов»), Ё≡Е и опечатку ≤1. Раньше здесь
    было ТОЧНОЕ пересечение вариантов — оно не прощало ни опечатку в связке
    («Иваноф Иван»), ни подменённую букву."""
    w1 = [w for w in (name1 or "").split() if len(w.strip("-_.,")) >= 2]
    w2 = [w for w in (name2 or "").split() if len(w.strip("-_.,")) >= 2]
    if len(w1) < 2 or len(w2) < 2:
        return False
    # Разные отчества у обеих сторон — разные люди, связка ФИО не считается.
    if patronymic_conflict(name1, name2):
        return False
    straight = name_part_match(w1[0], w2[0]) and name_part_match(w1[1], w2[1])
    swapped = name_part_match(w1[0], w2[1]) and name_part_match(w1[1], w2[0])
    return straight or swapped


def normalize_phone(phone: str) -> str:
    """Нормализация телефонного номера."""
    if not phone:
        return ""
    # Убираем все кроме цифр
    digits = re.sub(r'\D', '', phone)
    # Убираем ведущие 8 или +7 для российских номеров
    if digits.startswith('8') and len(digits) == 11:
        digits = '7' + digits[1:]
    elif digits.startswith('7') and len(digits) == 11:
        pass  # Уже нормализовано
    return digits


def normalize_email(email: str) -> str:
    """Нормализация email."""
    if not email:
        return ""
    return email.lower().strip()


# Локальные части почты, которые НЕ идентифицируют человека: служебные ящики и
# заглушки. По ним нельзя матчить — иначе «info@…» разных фирм слиплись бы.
_GENERIC_EMAIL_LOCALS = {"info", "mail", "test", "hello", "admin", "hr", "job",
                         "jobs", "work", "cv", "resume", "noreply", "no-reply"}

# Служебные ящики сайтов вакансий. Расширение сохраняло их как почту кандидата,
# когда тот свою не указал: на rabota.by в блоке контактов стоит ссылка на
# support@rabota.by — и у шести разных людей оказалась одна «почта», они
# считались похожими (прод, 22.09.2026). Такие адреса — не почта человека: в
# сравнении не участвуют и в карточку не сохраняются.
JOB_SITE_EMAIL_DOMAINS = frozenset({
    "rabota.by", "hh.ru", "hh.kz", "hh.uz", "hh.by", "headhunter.ru", "headhunter.kz",
    "superjob.ru", "rabota.ru", "zarplata.ru", "trudvsem.ru", "praca.by",
    "work.ua", "robota.ua", "rabota.ua", "djinni.co", "getmatch.ru",
})
# Локальные части, которые на ЛЮБОМ домене означают робота или поддержку.
SERVICE_EMAIL_LOCALS = frozenset({
    "support", "noreply", "no-reply", "donotreply", "do-not-reply",
    "mailer-daemon", "notifications", "notification", "robot",
})


def is_service_email(email: Optional[str]) -> bool:
    """Служебный адрес сайта/робота, а не почта кандидата."""
    e = normalize_email(email or "")
    if "@" not in e:
        return False
    local, domain = e.split("@", 1)
    if local in SERVICE_EMAIL_LOCALS:
        return True
    return domain in JOB_SITE_EMAIL_DOMAINS or any(
        domain.endswith("." + d) for d in JOB_SITE_EMAIL_DOMAINS
    )


def email_locals_of(emails) -> Set[str]:
    """Локальные части (до «@») из набора нормализованных адресов — общий ключ
    сравнения почты для КРАСНОГО и ЖЁЛТОГО (заказчик: «одинаковая система, до @»).
    Смена домена (ivan.petrov@gmail → ivan.petrov@mail) больше не уводит от дубля.
    Отсекаем generic и слишком короткие (<4) локали, чтобы не слипались чужие."""
    out: Set[str] = set()
    for e in (emails or ()):
        local = e.split("@", 1)[0] if "@" in e else ""
        if len(local) >= 4 and local not in _GENERIC_EMAIL_LOCALS:
            out.add(local)
    return out


def normalize_telegram(value: str) -> str:
    """Нормализация telegram-username: без @, нижний регистр, без пробелов."""
    return str(value or "").strip().lstrip("@").lower()


def normalize_birth_date(value) -> Optional[str]:
    """Канонизировать дату рождения в 'YYYY-MM-DD'. Принимает ISO, '14.05.1990',
    '14/05/1990'. Возвращает None для неполных/мусорных значений (год-месяц без дня,
    текст) — такие НЕ годятся как точный DOB-ключ."""
    if not value:
        return None
    s = str(value).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        y, mo, d = m.groups()
    else:
        m = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{4})$", s)
        if not m:
            return None
        d, mo, y = m.groups()
    try:
        from datetime import date
        dt = date(int(y), int(mo), int(d))
    except ValueError:
        return None
    return dt.isoformat()


def age_from_birth(value, *, today: Optional[str] = None) -> Optional[int]:
    """Возраст в полных годах из даты рождения. today (ISO) — для детерминизма в тестах;
    по умолчанию сегодняшняя дата."""
    norm = normalize_birth_date(value)
    if not norm:
        return None
    from datetime import date
    y, mo, d = (int(x) for x in norm.split("-"))
    ref = date.fromisoformat(today) if today else date.today()
    age = ref.year - y - ((ref.month, ref.day) < (mo, d))
    return age


# Значения, попадающие в telegram_usernames при импорте (HH/CSV), но НЕ являющиеся
# личными хэндлами — это ярлыки источника/площадки. Матчить дубли по ним нельзя:
# десятки разных людей с одним «telegram»/«hh_b2b» слипаются в один ложный кластер.
JUNK_TELEGRAM_USERNAMES = {
    "telegram", "tg", "telega", "hh", "hh_b2b", "hh_news", "hh_news_hr", "hhnews",
    "headhunter", "hhru", "vk", "vkontakte", "avito", "superjob", "habr", "linkedin",
    "email", "mail", "phone", "tel", "resume", "cv", "source", "none", "no",
    "n/a", "na", "null", "-", "—",
}

# Если одно и то же telegram-значение встречается у стольких кандидатов и более —
# это заведомо не личный хэндл (мусор/ярлык), а массовое совпадение. Не матчим.
TG_COMMON_THRESHOLD = 3

# --- Level-2 soft-identity scoring (anti-evasion) ------------------------------
# Веса — СТАРТОВЫЕ значения-заглушки. Калибруются dryrun_duplicate_detection.py
# на реальной активной+теневой базе ДО включения флага в проде. Меняются здесь,
# в одном месте, без правки логики скоринга.
SOFT_WEIGHTS = {
    "full_name": 50,    # СВЯЗКА Фамилия+Имя (оба слова, любой порядок). ЕДИНСТВЕННЫЙ
                        # способ учесть имя: порознь имя/фамилия НЕ считаются (заказчик:
                        # «сколько Артёмов, сколько Хабибуллиных» — одна часть не дубль).
    "dob_exact": 40,    # точная дата рождения YYYY-MM-DD
    "age_pm1": 12,      # возраст +-1 год (когда точного ДР нет)
    "phone7": 35,       # последние 7 цифр телефона совпали
    "email_local": 35,  # локальная часть email (до @) совпала
    "telegram": 35,     # общий личный @хэндл (не мусорный ярлык источника)
    # Город убран (22.09.2026, решение владельца): его вписывают любой, у всех
    # кандидатов с rabota.by это Минск — процент он только раздувал.
}
# Флаг ставим при score >= порога И >=2 независимых компонентах.
# 65 подобран так, что СВЯЗКА ФИО сама (50) НЕ флажит — полные тёзки «Иванов Иван»
# существуют, — но связка + любой сильный сигнал (ДР 90 / телефон 85 / email 85 /
# telegram 85) флажит, как и два контакта без ФИО (email+phone=70) — это ловля
# «сменил ФИО, но контакты те же». Слабый возраст (12) сам порог не берёт.
SOFT_THRESHOLD = 65
SOFT_MIN_COMPONENTS = 2


def is_junk_telegram(value: Optional[str]) -> bool:
    """Ярлык источника/канал портала (hh_b2b, telegram, hh…), а не ник человека.
    Расширение старых версий брало со страницы hh.ru ссылку t.me/hh_b2b и
    сохраняло её как Telegram кандидата (у 42 активных, 22.09.2026)."""
    return normalize_telegram(value or "") in JUNK_TELEGRAM_USERNAMES


def first_real_telegram(values) -> Optional[str]:
    """Первый НАСТОЯЩИЙ ник из списка — для показа. Карточки показывали просто
    первый, и у «hh_b2b, yrsrss» виден был hh_b2b."""
    if isinstance(values, str):
        values = [values]
    for v in values or []:
        if v and not is_junk_telegram(v):
            return v
    return None


def is_matchable_telegram(value: str, freq: Optional[dict] = None) -> bool:
    """Годен ли telegram-username как идентификатор для дедупа: не пустой,
    не из денилиста источников и (если передана частота) не «общий» (≥ порога)."""
    k = normalize_telegram(value)
    if not k or k in JUNK_TELEGRAM_USERNAMES:
        return False
    if freq is not None and freq.get(k, 0) >= TG_COMMON_THRESHOLD:
        return False
    return True


# Слова-маркеры должностей. Расширение иногда кладёт в поле «имя» должность
# («Flutter Developer, Минск, 25 лет») — по таким «именам» матчить дубли нельзя:
# все «Flutter Developer» слипаются между собой.
_POSITION_HINT_WORDS = {
    "developer", "разработчик", "разработчица", "manager", "менеджер",
    "designer", "дизайнер", "analyst", "аналитик", "engineer", "инженер",
    "specialist", "специалист", "lead", "директор", "director", "маркетолог",
    "marketer", "тестировщик", "qa", "devops", "frontend", "backend", "fullstack",
    "копирайтер", "рекрутер", "recruiter", "бухгалтер", "оператор", "sales",
    "продаж", "продажник", "smm", "программист", "администратор", "admin",
    "support", "поддержка", "продавец", "консультант", "ассистент",
}


def looks_like_person_name(name: str) -> bool:
    """Похоже ли значение на ФИО человека, а не на должность/мусор. Расширение
    иногда кладёт в имя должность («Flutter Developer, Минск, 25 лет»), а импорт —
    placeholder'ы. По таким «именам» матчить дубли нельзя. Критерии: нет цифр
    (возраст), нет запятой («Должность, Город, …»), ≥2 слов, и ни одно слово не
    является явным маркером должности."""
    n = (name or "").strip()
    if not n or any(ch.isdigit() for ch in n) or "," in n:
        return False
    nl = n.lower()
    # Плейсхолдеры импорта/расширения («Кандидат …», «Candidate …») — не ФИО:
    # по ним матчить нельзя, иначе все безымянные слипаются. Раньше этот гард
    # жил отдельной копией в magic_button.check_duplicate — теперь единый.
    if nl.startswith("кандидат") or nl.startswith("candidate"):
        return False
    words = nl.replace("-", " ").split()
    if len(words) < 2:
        return False
    if any(w.strip("().") in _POSITION_HINT_WORDS for w in words):
        return False
    return True


def normalize_source_url(url: str) -> str:
    """Стабильный ключ резюме из URL источника — БЕЗ волатильных query-параметров.

    hh.ru отдаёт ссылки вида /resume/<hash>?hhtmFrom=chat&vacancyId=..&t=<timestamp>,
    где query МЕНЯЕТСЯ при каждом открытии. Сравнение полного href ломало дедуп:
    одно и то же резюме, открытое дважды, выглядело как два разных source_url —
    и кандидат добавлялся повторно. Возвращаем канонический ключ: для hh —
    hh:resume:<hash> (стабилен), иначе host+path без query/fragment.
    """
    if not url:
        return ""
    s = str(url).strip()
    if not s:
        return ""
    m = re.search(r"/resume/([0-9a-f]{16,})", s, re.IGNORECASE)
    if m:
        return f"hh:resume:{m.group(1).lower()}"
    m = re.search(r"[?&]resumeId=(\d+)", s, re.IGNORECASE)
    if m:
        return f"hh:resumeId:{m.group(1)}"
    s = re.sub(r"#.*$", "", s)
    s = re.sub(r"\?.*$", "", s)
    s = re.sub(r"^https?://", "", s, flags=re.IGNORECASE)
    return s.rstrip("/").lower()


def extract_skills(extra_data: dict) -> Set[str]:
    """Извлечение навыков из extra_data."""
    skills = set()
    if not extra_data:
        return skills

    # Поиск skills в разных форматах
    if 'skills' in extra_data:
        if isinstance(extra_data['skills'], list):
            skills.update(s.lower().strip() for s in extra_data['skills'] if s)
        elif isinstance(extra_data['skills'], str):
            # Разделители: запятая, точка с запятой, новая строка
            for skill in re.split(r'[,;\n]', extra_data['skills']):
                skill = skill.strip().lower()
                if skill:
                    skills.add(skill)

    # Поиск в других возможных полях
    for key in ['technologies', 'tech_stack', 'stack', 'competencies']:
        if key in extra_data:
            if isinstance(extra_data[key], list):
                skills.update(s.lower().strip() for s in extra_data[key] if s)
            elif isinstance(extra_data[key], str):
                for skill in re.split(r'[,;\n]', extra_data[key]):
                    skill = skill.strip().lower()
                    if skill:
                        skills.add(skill)

    return skills


def extract_experience_years(extra_data: dict) -> Optional[int]:
    """Извлечение опыта работы в годах."""
    if not extra_data:
        return None

    for key in ['experience', 'experience_years', 'years_of_experience', 'work_experience']:
        if key in extra_data:
            value = extra_data[key]
            if isinstance(value, (int, float)):
                return int(value)
            elif isinstance(value, str):
                # Попытка извлечь число из строки
                match = re.search(r'(\d+)', value)
                if match:
                    return int(match.group(1))
    return None


def extract_location(extra_data: dict) -> Optional[str]:
    """Извлечение локации."""
    if not extra_data:
        return None

    for key in ['location', 'city', 'region', 'country', 'address']:
        if key in extra_data:
            value = extra_data[key]
            if isinstance(value, str) and value.strip():
                return value.lower().strip()
    return None


def calculate_skills_similarity(skills1: Set[str], skills2: Set[str]) -> Tuple[float, List[str]]:
    """
    Расчет сходства по навыкам с использованием коэффициента Жаккара.

    Returns:
        (similarity_score 0-1, list of common skills)
    """
    if not skills1 or not skills2:
        return 0.0, []

    # Нормализация навыков для сравнения
    normalized1 = {s.lower().strip() for s in skills1}
    normalized2 = {s.lower().strip() for s in skills2}

    common = normalized1 & normalized2
    union = normalized1 | normalized2

    if not union:
        return 0.0, []

    jaccard = len(common) / len(union)
    return jaccard, list(common)


def calculate_salary_overlap(
    min1: Optional[int], max1: Optional[int],
    min2: Optional[int], max2: Optional[int]
) -> bool:
    """Проверка пересечения зарплатных ожиданий."""
    if None in (min1, max1, min2, max2):
        # Если нет полных данных, считаем что пересечение возможно
        return True

    # Проверка пересечения диапазонов
    return max1 >= min2 and max2 >= min1


def calculate_experience_similarity(exp1: Optional[int], exp2: Optional[int]) -> bool:
    """Проверка схожести опыта (разница не более 2 лет)."""
    if exp1 is None or exp2 is None:
        return False
    return abs(exp1 - exp2) <= 2


def calculate_location_similarity(loc1: Optional[str], loc2: Optional[str]) -> bool:
    """Проверка схожести локации."""
    if not loc1 or not loc2:
        return False

    loc1_lower = loc1.lower()
    loc2_lower = loc2.lower()

    # Точное совпадение
    if loc1_lower == loc2_lower:
        return True

    # Одна локация содержит другую
    if loc1_lower in loc2_lower or loc2_lower in loc1_lower:
        return True

    return False


class MergeIdentityConflict(Exception):
    """Слияние заблокировано: у кандидатов КОНФЛИКТУЮТ сильные ключи — это заведомо
    разные люди, а не дубли. Эндпоинты ловят и отдают 409 с причиной."""
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _entity_birth_norm(e) -> Optional[str]:
    ex = e.extra_data if isinstance(getattr(e, "extra_data", None), dict) else {}
    return normalize_birth_date(ex.get("birth_date") or ex.get("date_of_birth"))


def hard_identity_conflict(a, b) -> Optional[str]:
    """Причина, если a и b — ЗАВЕДОМО РАЗНЫЕ люди: у ОБОИХ есть телефон и он различается,
    И у ОБОИХ есть дата рождения и она различается. Оба сильных ключа противоречат друг
    другу → это ошибочная склейка (реальный кейс: три разных «Никиты»). Консервативно:
    если хотя бы один ключ отсутствует или совпадает — НЕ блокируем (нормальный дубль)."""
    pa, pb = normalize_phone(getattr(a, "phone", "") or ""), normalize_phone(getattr(b, "phone", "") or "")
    phone_conflict = len(pa) >= 7 and len(pb) >= 7 and pa[-7:] != pb[-7:]
    da, dbb = _entity_birth_norm(a), _entity_birth_norm(b)
    dob_conflict = bool(da) and bool(dbb) and da != dbb
    if phone_conflict and dob_conflict:
        return f"разные телефоны (…{pa[-4:]} vs …{pb[-4:]}) и разные даты рождения ({da} vs {dbb})"
    # Отчества есть у обоих и они разные — однофамильцы-тёзки, а не дубль. Это
    # самостоятельное основание отказать: слияние необратимо стягивает историю
    # двух РАЗНЫХ людей в одну карточку.
    na, nb = getattr(a, "name", "") or "", getattr(b, "name", "") or ""
    if patronymic_conflict(na, nb):
        wa = ", ".join(sorted(patronymics_of(na)))
        wb = ", ".join(sorted(patronymics_of(nb)))
        return f"разные отчества ({wa} vs {wb})"
    return None


class SimilarityService:
    """Сервис поиска похожих кандидатов и детекции дубликатов."""

    async def find_similar(
        self,
        db: AsyncSession,
        entity: Entity,
        limit: int = 10,
        org_id: Optional[int] = None,
        user: Optional[User] = None
    ) -> List[SimilarCandidate]:
        """
        Поиск похожих кандидатов.

        Использует embeddings если доступны (быстрый поиск <100ms),
        иначе fallback на JSON-based сравнение.

        Args:
            db: Сессия БД
            entity: Исходный кандидат
            limit: Максимальное количество результатов
            org_id: ID организации (если None, ищем в той же организации)
            user: Текущий пользователь (для фильтрации по правам доступа)

        Returns:
            Список похожих кандидатов с оценкой сходства
        """
        if org_id is None:
            org_id = entity.org_id

        # Try embeddings-based search first (much faster)
        embedding_results = await self._find_similar_via_embeddings(db, entity, limit * 2, org_id)

        if embedding_results:
            logger.debug(f"Using embeddings for similarity search, found {len(embedding_results)} candidates")
            # Filter by user access if needed
            if user:
                from .permissions import PermissionService
                permissions = PermissionService(db)
                accessible_ids = await permissions.get_accessible_ids(user, "entity", org_id)
                embedding_results = [r for r in embedding_results if r.entity_id in accessible_ids]

            return embedding_results[:limit]

        # Fallback to JSON-based search
        logger.debug("Embeddings not available, using JSON-based similarity search")

        # Извлекаем данные исходного кандидата
        source_skills = extract_skills(entity.extra_data or {})
        source_experience = extract_experience_years(entity.extra_data or {})
        source_location = extract_location(entity.extra_data or {})

        # Get accessible entity IDs for security filtering
        accessible_ids: Optional[Set[int]] = None
        if user:
            from .permissions import PermissionService
            permissions = PermissionService(db)
            accessible_ids = await permissions.get_accessible_ids(user, "entity", org_id)

        # Загружаем кандидатов (фильтруем по доступу если есть user)
        query = select(Entity).where(
            and_(
                Entity.org_id == org_id,
                Entity.id != entity.id,
                Entity.type == EntityType.candidate,
                Entity.is_archived.is_not(True),  # архив не показываем в «похожих»
            )
        )
        result = await db.execute(query)
        all_candidates = result.scalars().all()

        # Filter by accessible IDs if user is provided
        if accessible_ids is not None:
            candidates = [c for c in all_candidates if c.id in accessible_ids]
        else:
            candidates = all_candidates

        similar_results: List[SimilarCandidate] = []

        for candidate in candidates:
            # Извлекаем данные кандидата для сравнения
            candidate_skills = extract_skills(candidate.extra_data or {})
            candidate_experience = extract_experience_years(candidate.extra_data or {})
            candidate_location = extract_location(candidate.extra_data or {})

            # Рассчитываем сходство по разным критериям
            skill_score, common_skills = calculate_skills_similarity(source_skills, candidate_skills)
            similar_experience = calculate_experience_similarity(source_experience, candidate_experience)
            similar_salary = calculate_salary_overlap(
                entity.expected_salary_min, entity.expected_salary_max,
                candidate.expected_salary_min, candidate.expected_salary_max
            )
            similar_location = calculate_location_similarity(source_location, candidate_location)

            # Расчет итогового балла сходства
            score = 0
            match_reasons = []

            # Навыки - 50% веса
            if skill_score > 0:
                score += int(skill_score * 50)
                if common_skills:
                    match_reasons.append(f"Общие навыки: {', '.join(common_skills[:5])}")

            # Опыт - 20% веса
            if similar_experience:
                score += 20
                match_reasons.append(f"Похожий опыт работы")

            # Зарплата - 15% веса
            if similar_salary and (entity.expected_salary_min or entity.expected_salary_max):
                score += 15
                match_reasons.append("Пересекающиеся зарплатные ожидания")

            # Локация - 15% веса
            if similar_location:
                score += 15
                match_reasons.append(f"Похожая локация")

            # Добавляем в результат если есть хоть какое-то сходство
            if score > 0:
                similar_results.append(SimilarCandidate(
                    entity_id=candidate.id,
                    entity_name=candidate.name,
                    similarity_score=min(score, 100),
                    common_skills=common_skills,
                    similar_experience=similar_experience,
                    similar_salary=similar_salary,
                    similar_location=similar_location,
                    match_reasons=match_reasons
                ))

        # Сортируем по убыванию сходства и возвращаем топ
        similar_results.sort(key=lambda x: x.similarity_score, reverse=True)
        return similar_results[:limit]

    async def _find_similar_via_embeddings(
        self,
        db: AsyncSession,
        entity: Entity,
        limit: int,
        org_id: int
    ) -> List[SimilarCandidate]:
        """
        Fast similarity search using embeddings (pgvector).

        Returns empty list if embeddings are not available.
        """
        try:
            from .similarity_search import similarity_search

            # Check if entity has embedding
            if not hasattr(entity, 'embedding') or entity.embedding is None:
                return []

            # Find similar via embeddings
            results = await similarity_search.find_similar_entities(
                db=db,
                entity_id=entity.id,
                org_id=org_id,
                limit=limit,
                min_score=0.2  # Lower threshold to get more candidates
            )

            if not results:
                return []

            # Convert to SimilarCandidate format
            similar_candidates = []
            for r in results:
                # Extract skills for match reasons
                common_skills = r.tags[:5] if r.tags else []
                match_reasons = []

                if common_skills:
                    match_reasons.append(f"Общие навыки: {', '.join(common_skills)}")
                if r.score >= 0.7:
                    match_reasons.append("Высокое AI-сходство профиля")
                elif r.score >= 0.5:
                    match_reasons.append("Среднее AI-сходство профиля")

                similar_candidates.append(SimilarCandidate(
                    entity_id=r.id,
                    entity_name=r.name,
                    similarity_score=int(r.score * 100),
                    common_skills=common_skills,
                    similar_experience=r.score >= 0.5,  # Approximate
                    similar_salary=False,  # Not calculated in embeddings
                    similar_location=False,  # Not calculated in embeddings
                    match_reasons=match_reasons
                ))

            return similar_candidates

        except ImportError:
            logger.debug("similarity_search module not available")
            return []
        except Exception as e:
            logger.warning(f"Embeddings search failed, falling back to JSON: {e}")
            return []

    def calculate_similarity(
        self,
        entity1: Entity,
        entity2: Entity
    ) -> SimilarCandidate:
        """
        Расчет сходства между двумя кандидатами.

        Args:
            entity1: Первый кандидат
            entity2: Второй кандидат

        Returns:
            Результат с оценкой сходства
        """
        # Извлекаем данные
        skills1 = extract_skills(entity1.extra_data or {})
        skills2 = extract_skills(entity2.extra_data or {})
        exp1 = extract_experience_years(entity1.extra_data or {})
        exp2 = extract_experience_years(entity2.extra_data or {})
        loc1 = extract_location(entity1.extra_data or {})
        loc2 = extract_location(entity2.extra_data or {})

        # Рассчитываем сходство
        skill_score, common_skills = calculate_skills_similarity(skills1, skills2)
        similar_experience = calculate_experience_similarity(exp1, exp2)
        similar_salary = calculate_salary_overlap(
            entity1.expected_salary_min, entity1.expected_salary_max,
            entity2.expected_salary_min, entity2.expected_salary_max
        )
        similar_location = calculate_location_similarity(loc1, loc2)

        # Расчет итогового балла
        score = 0
        match_reasons = []

        if skill_score > 0:
            score += int(skill_score * 50)
            if common_skills:
                match_reasons.append(f"Общие навыки: {', '.join(common_skills[:5])}")

        if similar_experience:
            score += 20
            match_reasons.append("Похожий опыт работы")

        if similar_salary and (entity1.expected_salary_min or entity1.expected_salary_max):
            score += 15
            match_reasons.append("Пересекающиеся зарплатные ожидания")

        if similar_location:
            score += 15
            match_reasons.append("Похожая локация")

        return SimilarCandidate(
            entity_id=entity2.id,
            entity_name=entity2.name,
            similarity_score=min(score, 100),
            common_skills=common_skills,
            similar_experience=similar_experience,
            similar_salary=similar_salary,
            similar_location=similar_location,
            match_reasons=match_reasons,
            # Detailed comparison data
            entity1_skills=skills1,
            entity2_skills=skills2,
            entity1_experience=exp1,
            entity2_experience=exp2,
            entity1_salary_min=entity1.expected_salary_min,
            entity1_salary_max=entity1.expected_salary_max,
            entity2_salary_min=entity2.expected_salary_min,
            entity2_salary_max=entity2.expected_salary_max,
            entity1_location=loc1,
            entity2_location=loc2,
            entity1_position=entity1.position,
            entity2_position=entity2.position
        )

    async def detect_duplicates(
        self,
        db: AsyncSession,
        entity: Entity,
        org_id: Optional[int] = None,
        user: Optional[User] = None,
        include_archived: bool = False,
        include_text: bool = True,
    ) -> List[DuplicateCandidate]:
        """Возможные дубликаты кандидата — для окна сравнения.

        Считает ТЕМ ЖЕ ядром, что и баннер «Похожий кандидат»
        (duplicate_matcher.compare_key_sets), поэтому процент на карточке и процент
        в баннере — одно и то же число. Раньше здесь была своя шкала (имя 40,
        email 30, телефон 30, telegram 30, компания+навыки 20, порог 30), и точное
        совпадение по email показывалось в окне как «30%».

        Args:
            db: сессия БД
            entity: исходный кандидат
            org_id: организация (по умолчанию — организация кандидата)
            user: текущий пользователь (фильтр видимости по правам)
            include_archived: включать ли архив (по умолчанию нет)
            include_text: показывать ли пары, связанные только текстом резюме
        """
        from .duplicate_matcher import match_entities, keys_of_entity
        from .duplicate_decisions import dismissed_for

        if org_id is None:
            org_id = entity.org_id

        # Фильтр видимости: кандидаты, недоступные пользователю, не должны
        # утекать через окно сравнения (SECURITY).
        accessible_ids: Optional[Set[int]] = None
        if user:
            from .permissions import PermissionService
            permissions = PermissionService(db)
            accessible_ids = await permissions.get_accessible_ids(user, "entity", org_id)

        matches = await match_entities(
            db,
            org_id,
            keys_of_entity(entity),
            exclude_id=entity.id,
            dismissed=await dismissed_for(db, entity),
            include_archived=include_archived,
            include_text=include_text,
            own_extra_data=entity.extra_data if isinstance(entity.extra_data, dict) else {},
            allowed_ids=accessible_ids,
            self_id=entity.id,
        )

        duplicates = [
            DuplicateCandidate(
                entity_id=m.entity_id,
                entity_name=m.entity_name,
                confidence=m.confidence,
                match_reasons=m.reasons,
                matched_fields=m.matched_fields,
                strength=m.strength,
                signals=m.signals,
                level=m.level,
            )
            for m in matches
        ]
        duplicates.sort(key=lambda x: (-x.confidence, -x.entity_id))
        return duplicates

    async def merge_entities(
        self,
        db: AsyncSession,
        source_entity: Entity,
        target_entity: Entity,
        keep_source_data: bool = False,
        merged_by_name=None,
        force: bool = False,
    ) -> Entity:
        """
        Объединение двух сущностей (дубликатов).

        Объединяет:
        - Контактные данные (телефоны, email, telegram)
        - Теги
        - extra_data
        - Связанные чаты и звонки переносятся на target

        Args:
            db: Сессия БД
            source_entity: Исходная сущность (будет удалена)
            target_entity: Целевая сущность (останется)
            keep_source_data: Приоритет данных source при конфликтах

        Returns:
            Обновленная целевая сущность

        Raises:
            MergeIdentityConflict: если у кандидатов конфликтуют сильные ключи
                (разные телефон И дата рождения) и force=False — защита от ошибочной
                склейки разных людей (реальный кейс: три разных «Никиты»).
        """
        # Страховка от ложного слияния: не даём слить заведомо РАЗНЫХ людей.
        if not force:
            conflict = hard_identity_conflict(source_entity, target_entity)
            if conflict:
                raise MergeIdentityConflict(conflict)

        # Объединяем телефоны
        all_phones = set(target_entity.phones or [])
        all_phones.update(source_entity.phones or [])
        if source_entity.phone:
            all_phones.add(source_entity.phone)
        if target_entity.phone:
            all_phones.add(target_entity.phone)
        target_entity.phones = list(all_phones)

        # Объединяем email
        all_emails = set(target_entity.emails or [])
        all_emails.update(source_entity.emails or [])
        if source_entity.email:
            all_emails.add(source_entity.email)
        if target_entity.email:
            all_emails.add(target_entity.email)
        target_entity.emails = list(all_emails)

        # Объединяем telegram usernames
        all_usernames = set(target_entity.telegram_usernames or [])
        all_usernames.update(source_entity.telegram_usernames or [])
        target_entity.telegram_usernames = list(all_usernames)

        # Объединяем теги
        all_tags = set(target_entity.tags or [])
        all_tags.update(source_entity.tags or [])
        target_entity.tags = list(all_tags)

        # Объединяем extra_data
        target_extra = dict(target_entity.extra_data or {})
        source_extra = dict(source_entity.extra_data or {})

        if keep_source_data:
            # Source имеет приоритет
            merged_extra = {**target_extra, **source_extra}
        else:
            # Target имеет приоритет
            merged_extra = {**source_extra, **target_extra}

        # Специальная обработка для навыков - всегда объединяем
        target_skills = extract_skills(target_extra)
        source_skills = extract_skills(source_extra)
        merged_extra['skills'] = list(target_skills | source_skills)

        # Заметки — объединяем массивы, не теряем заметки источника (дедуп по id).
        def _notes(extra):
            n = extra.get("notes")
            return n if isinstance(n, list) else []
        _t_notes = _notes(target_extra)
        _seen_ids = {n.get("id") for n in _t_notes if isinstance(n, dict) and n.get("id")}
        merged_notes = _t_notes + [
            n for n in _notes(source_extra)
            if not (isinstance(n, dict) and n.get("id") in _seen_ids) and n not in _t_notes
        ]
        if merged_notes:
            merged_extra["notes"] = merged_notes

        target_entity.extra_data = merged_extra

        # Обновляем зарплатные ожидания (берем более широкий диапазон)
        if source_entity.expected_salary_min and target_entity.expected_salary_min:
            target_entity.expected_salary_min = min(
                source_entity.expected_salary_min,
                target_entity.expected_salary_min
            )
        elif source_entity.expected_salary_min:
            target_entity.expected_salary_min = source_entity.expected_salary_min

        if source_entity.expected_salary_max and target_entity.expected_salary_max:
            target_entity.expected_salary_max = max(
                source_entity.expected_salary_max,
                target_entity.expected_salary_max
            )
        elif source_entity.expected_salary_max:
            target_entity.expected_salary_max = source_entity.expected_salary_max

        # Переносим связанные записи
        # Чаты
        from ..models.database import (
            Chat, CallRecording, AnalysisHistory,
            VacancyApplication, Vacancy, StageTransition, EntityAnalysis,
            EntityAIConversation, EntityFile, EntityTransfer,
            FormSubmission, FormDispatch, RecruiterBonus,
            EntityCriteria, PrometheusReviewCache,
            Employee, ParseJob, SharedAccess, CandidateShareLink,
        )
        from sqlalchemy import text as _sql_text

        await db.execute(
            Chat.__table__.update()
            .where(Chat.entity_id == source_entity.id)
            .values(entity_id=target_entity.id)
        )

        # Звонки
        await db.execute(
            CallRecording.__table__.update()
            .where(CallRecording.entity_id == source_entity.id)
            .values(entity_id=target_entity.id)
        )

        # Анализы
        await db.execute(
            AnalysisHistory.__table__.update()
            .where(AnalysisHistory.entity_id == source_entity.id)
            .values(entity_id=target_entity.id)
        )

        # --- Заявки на вакансии: сливаем БЕЗ потери истории ---
        # UNIQUE(vacancy_id, entity_id): две заявки на одну вакансию нельзя.
        # Карта vacancy_id -> ORM-объект выжившего (target).
        target_app_objs = (await db.execute(
            select(VacancyApplication)
            .where(VacancyApplication.entity_id == target_entity.id)
        )).scalars().all()
        target_app_by_vacancy = {a.vacancy_id: a for a in target_app_objs}

        source_apps = (await db.execute(
            select(VacancyApplication)
            .where(VacancyApplication.entity_id == source_entity.id)
        )).scalars().all()

        # Honest vacancy-маппинг контейнера источника: берём самую свежую заявку
        # источника (если есть). Нет заявок → vacancy остаётся null.
        _src_vacancy_id = None
        _src_vacancy_title = None
        if source_apps:
            _primary_app = sorted(source_apps, key=lambda a: a.id, reverse=True)[0]
            _src_vacancy_id = _primary_app.vacancy_id
            _vac_row = (await db.execute(
                select(Vacancy.title).where(Vacancy.id == _src_vacancy_id)
            )).first()
            _src_vacancy_title = _vac_row[0] if _vac_row else None

        for s_app in source_apps:
            t_app = target_app_by_vacancy.get(s_app.vacancy_id)
            if t_app is None:
                # Нет коллизии — переносим заявку на target отдельным блоком.
                s_app.entity_id = target_entity.id
                # Явно перепривязываем переходы этой заявки на target.
                await db.execute(
                    StageTransition.__table__.update()
                    .where(StageTransition.application_id == s_app.id)
                    .values(entity_id=target_entity.id)
                )
                continue
            # Коллизия по вакансии: историю источника перепривязываем к заявке
            # target ДО удаления заявки (иначе FK CASCADE снесёт StageTransition).
            await db.execute(
                StageTransition.__table__.update()
                .where(StageTransition.application_id == s_app.id)
                .values(application_id=t_app.id, entity_id=target_entity.id)
            )
            # Скалярные поля переносим только если у target пусто (не затираем).
            for _field in ("notes", "rating", "interview_summary", "rejection_reason", "source"):
                if getattr(t_app, _field, None) is None and getattr(s_app, _field, None) is not None:
                    setattr(t_app, _field, getattr(s_app, _field))
            await db.delete(s_app)

        # Файлы источника фиксируем ДО перепривязки — чтобы исторический контейнер
        # (merged_from) знал СВОИ файлы/резюме: после merge все EntityFile висят на
        # target, и без этого списка не отличить, чьё это резюме/файл.
        _src_file_ids = [
            r[0] for r in (await db.execute(
                select(EntityFile.id).where(EntityFile.entity_id == source_entity.id)
            )).all()
        ]
        # То же для анкет (FormDispatch): фиксируем id ДО перепривязки, чтобы
        # исторический контейнер знал СВОИ диспатчи. Без этого: FormDispatch.entity_id
        # имеет FK ondelete=CASCADE → при удалении source его анкеты УДАЛЯЛИСЬ из БД
        # (после слияния показывалась только анкета survivor'а). Перепривязываем на
        # target (переживают удаление), а различаем по id (а не entity_id, который
        # у всех станет target).
        _src_dispatch_ids = [
            r[0] for r in (await db.execute(
                select(FormDispatch.id).where(FormDispatch.entity_id == source_entity.id)
            )).all()
        ]

        # Остальную историю переносим на target. VacancyApplication уже обработан
        # выше — здесь его НЕ трогаем. StageTransition тоже обработан явно в цикле
        # source_apps (каждый переход принадлежит конкретной заявке, application_id
        # NOT NULL), поэтому здесь его НЕ включаем.
        for _hist_model in (
            EntityAnalysis,
            EntityAIConversation, EntityFile, EntityTransfer,
            FormSubmission, FormDispatch, RecruiterBonus,
            # Публичные ссылки предпросмотра: FK CASCADE, и без переноса ссылка,
            # уже отправленная заказчику, после слияния отдавала бы 404 (владелец
            # 17.09.2026 — вопрос «что ещё объединяется вместе с анкетами»).
            CandidateShareLink,
            # SET NULL FK на entities.id — без перепривязки осиротеют после удаления source.
            Employee, ParseJob,
        ):
            await db.execute(
                _hist_model.__table__.update()
                .where(_hist_model.entity_id == source_entity.id)
                .values(entity_id=target_entity.id)
            )

        # One-to-one записи (unique entity_id): приоритет у target, копии source удаляем
        for _uniq_model in (EntityCriteria, PrometheusReviewCache):
            await db.execute(
                _uniq_model.__table__.delete().where(
                    _uniq_model.entity_id == source_entity.id
                )
            )

        # M2M-теги: связи source удаляем (теги уже слиты в target.tags выше)
        await db.execute(
            _sql_text("DELETE FROM entity_tags WHERE entity_id = :sid"),
            {"sid": source_entity.id},
        )

        # SharedAccess (доступ коллег к кандидату) на source: FK ondelete=CASCADE —
        # при удалении source эти строки ПРОПАДУТ, и кандидат «исчезнет» из воронок
        # тех, кому он был расшарен. Перевешиваем доступы на target (entity_id+resource_id),
        # но уникальный ключ (resource_type, resource_id, shared_with, shared_by) столкнётся,
        # если у target уже есть доступ той же пары — такой дубль удаляем, не перевешиваем.
        _src_shares = (await db.execute(
            select(SharedAccess).where(SharedAccess.entity_id == source_entity.id)
        )).scalars().all()
        if _src_shares:
            _tgt_share_pairs = {
                (sa.shared_with_id, sa.shared_by_id)
                for sa in (await db.execute(
                    select(SharedAccess).where(SharedAccess.entity_id == target_entity.id)
                )).scalars().all()
            }
            for _sa in _src_shares:
                if (_sa.shared_with_id, _sa.shared_by_id) in _tgt_share_pairs:
                    await db.delete(_sa)  # у target уже есть такой доступ — дубль убираем
                else:
                    _sa.entity_id = target_entity.id
                    _sa.resource_id = target_entity.id
                    _tgt_share_pairs.add((_sa.shared_with_id, _sa.shared_by_id))

        # Survivor: сохраняем ОБА резюме (своё + источника) — после объединения
        # рядом со старым резюме появляется новое. Плюс снимаем флаг теневого дубля.
        _te = dict(target_entity.extra_data) if isinstance(target_entity.extra_data, dict) else {}
        _se = source_entity.extra_data if isinstance(source_entity.extra_data, dict) else {}

        def _resumes(extra):
            rs = extra.get("resume_demos")
            if isinstance(rs, list) and rs:
                return [r for r in rs if r]
            r = extra.get("resume_demo")
            return [r] if r else []

        combined = _resumes(_te) + _resumes(_se)
        if combined:
            seen = set()
            uniq = []
            for r in combined:
                key = (
                    (r.get("title"), r.get("saved_at")) if isinstance(r, dict) else (str(r), None)
                )
                if key in seen:
                    continue
                seen.add(key)
                uniq.append(r)
            _te["resume_demos"] = uniq

        # Сохраняем резюме/анкету источника отдельным блоком (merged_from), чтобы
        # показать его «вторым резюме» рядом с основным — особенно импортированную
        # анкету (cf:*), которую плоское объединение extra_data затирает.
        # Исторический контейнер источника (плашка): статус-снапшот (read-only),
        # дата добавления, лог+резюме (extra_data БЕЗ своего merged_from), файлы,
        # honest vacancy. FLATTEN: если источник сам был результатом слияния — его
        # контейнеры поднимаем в КОРЕНЬ массива (без матрёшки), чтобы фронт ходил
        # .map() по одномерному списку.
        from datetime import datetime as _dt
        _src_mf = _se.get("merged_from") if isinstance(_se.get("merged_from"), list) else []
        _se_clean = {k: v for k, v in _se.items() if k != "merged_from"}
        _b_container = {
            "entity_id": source_entity.id,
            "name": source_entity.name,
            "status": source_entity.status.value if source_entity.status else None,
            "added_at": source_entity.created_at.isoformat() if source_entity.created_at else None,
            "vacancy_id": _src_vacancy_id,
            "vacancy_title": _src_vacancy_title,
            "merged_at": _dt.utcnow().isoformat(),
            "merged_by_name": merged_by_name,
            "extra_data": _se_clean,
            "file_ids": _src_file_ids,
            "form_dispatch_ids": _src_dispatch_ids,
        }
        _target_mf = target_extra.get("merged_from") if isinstance(target_extra.get("merged_from"), list) else []
        _te["merged_from"] = list(_target_mf) + [_b_container] + list(_src_mf)

        # Импортные прохождения (ClickUp-архив) ОБЪЕДИНЯЕМ в корень (а не только
        # прячем в merged_from-контейнер) — иначе survivor показал бы лишь свои
        # анкеты, а прохождения источника пропали бы с виду. Дедуп по
        # (воронка+рекрутёр+статус). Так склейка разъехавшихся карточек одного
        # человека даёт одну карточку со ВСЕМИ его анкетами.
        _t_parts = _te.get("participations") if isinstance(_te.get("participations"), list) else []
        _s_parts = _se.get("participations") if isinstance(_se.get("participations"), list) else []
        if _s_parts or _t_parts:
            from .clickup_import import merge_participations as _merge_parts
            _te["participations"] = _merge_parts(_t_parts, _s_parts)
        _t_tids = _te.get("clickup_task_ids") if isinstance(_te.get("clickup_task_ids"), list) else []
        _s_tids = _se.get("clickup_task_ids") if isinstance(_se.get("clickup_task_ids"), list) else []
        if _s_tids or _t_tids:
            _te["clickup_task_ids"] = sorted(set(_t_tids) | set(_s_tids))

        _te.pop("hidden_duplicate_id", None)
        target_entity.extra_data = _te

        # Решения «разные люди» влитой анкеты переезжают на выжившую — ДО удаления,
        # иначе каскад по внешнему ключу снесёт их, и пары всплывут снова.
        from .duplicate_decisions import repoint_on_merge
        await repoint_on_merge(db, source_entity.id, target_entity.id)
        # Пометки дубля у других карточек, смотревшие на влитую, — на выжившую
        # (иначе после удаления они вели в никуда, services/duplicate_flags.py).
        from .duplicate_flags import repoint_on_merge as repoint_flags_on_merge
        await repoint_flags_on_merge(db, source_entity.id, target_entity.id, target_entity.org_id)

        # Удаляем исходную сущность
        await db.delete(source_entity)

        # Сохраняем изменения
        await db.commit()
        await db.refresh(target_entity)

        logger.info(f"Merged entity {source_entity.id} into {target_entity.id}")

        return target_entity


# Singleton instance
similarity_service = SimilarityService()


@dataclass
class DupSignal:
    """Один факт, из-за которого пара считается дублем.

    Общий «язык» бэка и окна сравнения: карточка подсвечивает ровно те поля, что
    перечислены здесь, вместо того чтобы заново сравнивать значения на фронте.
    """
    field: str       # 'source'|'email'|'telegram'|'name'|'phone'|'birth_date'|…
    label: str       # человекочитаемая причина (RU)
    weight: int = 0  # 100 — идентификатор; 0 — контекстный/мягкий сигнал
    identity: bool = False
    left: str = ""   # значение у проверяемого кандидата
    right: str = ""  # значение у совпавшего

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field, "label": self.label, "weight": self.weight,
            "identity": self.identity, "left": self.left, "right": self.right,
        }


# --- Уровень совпадения: «точно он» / «возможно он» ---------------------------
# Решение владельца 21.09.2026: красный баннер «Точное совпадение» — ТОЛЬКО когда
# совпало несколько признаков личности. Одна совпавшая почта или одно «Фамилия
# Имя» — это «возможно тот же человек» (жёлтый): тёзки и общие почты бывают.
# Город и возраст признаком личности не считаются, 7 цифр телефона — тоже.
STRONG_EVIDENCE_FIELDS = frozenset(
    {"source", "email", "telegram", "name", "phone", "birth_date", "resume_text"}
)
# Сколько процентов даёт каждое совпавшее поле, пока признак один. Ни одно поле
# в одиночку не дотягивает до 100 — сотня только у «точного» уровня.
EVIDENCE_WEIGHTS = {
    "source": 60, "email": 60, "telegram": 60, "phone": 60, "name": 50,
    "birth_date": 40, "resume_text": 40, "age": 12,
}
PARTIAL_PHONE_WEIGHT = 35  # совпали только последние 7 цифр
FUZZY_NAME_WEIGHT = 20     # имя похоже лишь нечётко (инициал, мягкий скоринг)
# Потолок «возможного» уровня: одиночный признак не должен выглядеть как 99%.
POSSIBLE_CONFIDENCE_CAP = 90


def strong_evidence_fields(signals) -> Set[str]:
    """Поля, совпадение которых — самостоятельный признак личности. Частичное
    совпадение телефона (7 цифр) признаком не считается."""
    out: Set[str] = set()
    for sig in signals or []:
        if sig.field not in STRONG_EVIDENCE_FIELDS:
            continue
        if sig.identity or sig.field in ("birth_date", "resume_text"):
            out.add(sig.field)
    return out


def match_level(signals) -> str:
    """«exact» — совпало ≥2 признака личности (красный баннер), иначе «possible»."""
    return "exact" if len(strong_evidence_fields(signals)) >= 2 else "possible"


def evidence_confidence(signals) -> int:
    """Процент для «возможного» совпадения: сумма весов совпавших полей (по
    максимуму на поле), не выше POSSIBLE_CONFIDENCE_CAP. «Точному» — всегда 100."""
    if match_level(signals) == "exact":
        return 100
    per_field: Dict[str, int] = {}
    for sig in signals or []:
        if sig.field == "phone" and not sig.identity:
            w = PARTIAL_PHONE_WEIGHT
        elif sig.field == "name" and not sig.identity:
            w = FUZZY_NAME_WEIGHT
        else:
            w = EVIDENCE_WEIGHTS.get(sig.field, 0)
        per_field[sig.field] = max(per_field.get(sig.field, 0), w)
    return min(POSSIBLE_CONFIDENCE_CAP, sum(per_field.values()))


@dataclass
class DupMatch:
    """Одно совпадение единого матчера дублей."""
    entity_id: int
    is_archived: bool
    strength: str  # 'source'|'email'|'telegram'|'name'|'phone'|'soft'|'text'
    confidence: int = 100          # Level-1 = 100; Level-2 (soft) = вычисленный балл
    reasons: List[str] = field(default_factory=list)  # причины словами (soft-тир, для UI)
    entity_name: str = ""
    # Все сработавшие сигналы пары — источник подсветки полей в окне сравнения.
    signals: List["DupSignal"] = field(default_factory=list)

    @property
    def matched_fields(self) -> Dict[str, Tuple[str, str]]:
        """{поле: (значение слева, значение справа)} — формат окна сравнения."""
        return {s.field: (s.left, s.right) for s in self.signals}

    @property
    def level(self) -> str:
        """«exact» (красный) — совпало ≥2 признака личности, иначе «possible»."""
        return match_level(self.signals)


def build_dup_keys(
    *,
    name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    telegram: Optional[str] = None,
    source_url: Optional[str] = None,
    emails: Optional[list] = None,
    phones: Optional[list] = None,
    telegram_usernames: Optional[list] = None,
    extra_data: Optional[dict] = None,
    company: Optional[str] = None,
) -> dict:
    """Нормализованные ключи дедупа из полей кандидата ИЛИ запроса расширения.
    Единый вход для find_duplicate_matches — чтобы веб/парсер и расширение
    сравнивали дубли по ОДНИМ правилам (email/телефон E.164/telegram/ФИО/URL)."""
    ek: Set[str] = set()
    pe = normalize_email(email or "")
    if pe and not is_service_email(pe):
        ek.add(pe)
    for e in (emails or []):
        ne = normalize_email(e or "")
        if ne and not is_service_email(ne):
            ek.add(ne)

    # Телефоны — в международном формате с кодом страны (+ старый ключ «10 цифр»),
    # см. services/phone_keys.py: иначе «+998 90…» и «90 …» не совпадали.
    from .phone_keys import phone_match_keys, phone_tails7
    raw_phones = [phone, *(phones or [])]
    ph: Set[str] = phone_match_keys(raw_phones)

    tg: Set[str] = set()
    nt = normalize_telegram(telegram or "")
    if nt:
        tg.add(nt)
    for t in (telegram_usernames or []):
        n2 = normalize_telegram(t)
        if n2:
            tg.add(n2)

    ed = extra_data if isinstance(extra_data, dict) else {}
    skey = normalize_source_url(source_url or ed.get("source_url") or ed.get("source_key") or "")

    # Контакты из ШАПКИ текста резюме (services/resume_contacts.py) — отдельными
    # наборами: совпадение по ним полноценное, но в окне сравнения подписывается
    # «из резюме», иначе рекрутёр видел бы «совпал телефон» при разных телефонах
    # в карточках.
    rc = ed.get("resume_contacts") if isinstance(ed.get("resume_contacts"), dict) else {}
    resume_emails: Set[str] = {
        normalize_email(e) for e in (rc.get("emails") or [])
        if e and not is_service_email(e)
    }
    resume_phone_keys: Set[str] = phone_match_keys(rc.get("phones") or [])
    resume_tg: Set[str] = {
        normalize_telegram(t) for t in (rc.get("telegrams") or [])
        if t and not is_junk_telegram(t)
    }

    # --- Level-2 мягкие ключи (anti-evasion) ---------------------------------
    # Имя/фамилия раздельно, только если значение похоже на ФИО (та же защита от
    # должностей/мусора, что и name_ok). Первое слово трактуем как фамилию, второе
    # как имя (порядок в наших источниках чаще «Фамилия Имя»); скоринг всё равно
    # сверяет наборами, так что перестановка не критична для флага.
    # Гомоглифы лечим до разбора на слова: «Cоколов Пётр» (латинская C) → кириллица,
    # иначе first/last-ключи разъехались бы с честной записью.
    folded_name = fold_homoglyphs(name or "")
    first_names: Set[str] = set()
    last_names: Set[str] = set()
    if looks_like_person_name(folded_name):
        parts = [w for w in folded_name.split() if len(w.strip("-_.,")) >= 1]
        if len(parts) >= 2:
            last_names.add(parts[0].strip("-_.,").lower())
            first_names.add(parts[1].strip("-_.,").lower())
    else:
        # looks_like_person_name requires >=2 words, so a bare single-word name
        # ("Саша") never passes it even though it's clearly a first-name-only
        # value. Apply the same digit/comma/placeholder/position-hint guards
        # without the word-count requirement for that one-word case only.
        parts = folded_name.split()
        if len(parts) == 1:
            w = parts[0].strip("-_.,")
            wl = w.lower()
            if (w and not any(ch.isdigit() for ch in w) and "," not in w
                    and not wl.startswith("кандидат") and not wl.startswith("candidate")
                    and wl not in _POSITION_HINT_WORDS):
                first_names.add(wl)
    first_names.discard("")
    last_names.discard("")

    phones7: Set[str] = phone_tails7(raw_phones)

    email_locals: Set[str] = email_locals_of(ek)

    birth_norm = normalize_birth_date(ed.get("birth_date"))
    age = ed.get("age")
    if not isinstance(age, int):
        age = age_from_birth(ed.get("birth_date")) if birth_norm else None

    cities: Set[str] = set()
    for cval in (ed.get("location"), ed.get("city")):
        if isinstance(cval, str) and cval.strip():
            cities.add(cval.strip().lower())

    return {
        "emails": ek,
        "phone_keys": ph,
        "resume_emails": resume_emails,
        "resume_phone_keys": resume_phone_keys,
        "resume_tg": resume_tg,
        "tg_names": tg,
        "name": " ".join((name or "").strip().lower().split()),
        "name_ok": looks_like_person_name(name or ""),
        "source_key": skey,
        # Level-2 soft keys
        "first_names": first_names,
        "last_names": last_names,
        "birth_norm": birth_norm,
        "age": age,
        "phones7": phones7,
        "email_locals": email_locals,
        "cities": cities,
        # Отчества (разные у обеих сторон — признак РАЗНЫХ людей, см.
        # patronymic_conflict). Берём из вылеченного гомоглифами имени.
        "patronymics": patronymics_of(folded_name),
        # Контекст (сам дубль не поднимает, но объясняет пару в окне сравнения).
        "company": (company or "").strip().lower(),
        "skills": extract_skills(ed),
    }


async def find_duplicate_matches(
    db: AsyncSession,
    org_id: Optional[int],
    keys: dict,
    *,
    exclude_id: Optional[int] = None,
    dismissed: Optional[Set[int]] = None,
) -> List[DupMatch]:
    """ЕДИНЫЙ матчер дублей для всей платформы: активные + архив, нормализованное
    сравнение в Python (портируемо Postgres+SQLite). Возвращает ВСЕ совпадения в
    порядке id-desc с флагом is_archived и типом (strength). Общий источник для
    расширения (check-duplicate, до добавления) и detect_archived_duplicate
    (веб/парсер, флаг после добавления).

    Сама логика сравнения живёт в services/duplicate_matcher.compare_key_sets —
    одно правило на весь продукт (баннер, окно сравнения, пере-скан, расширение).
    Импорт ленивый: duplicate_matcher импортирует этот модуль на уровне модуля.
    """
    if not (
        keys.get("emails") or keys.get("phone_keys") or keys.get("tg_names")
        or keys.get("name_ok") or keys.get("source_key")
        or keys.get("birth_norm") or keys.get("phones7") or keys.get("email_locals")
    ):
        return []
    from .duplicate_matcher import match_entities

    return await match_entities(
        db, org_id, keys, exclude_id=exclude_id, dismissed=dismissed,
    )


async def detect_archived_duplicate(db: AsyncSession, entity: Entity) -> Optional[int]:
    """Найти дубликат среди кандидатов организации — активные И архив (кроме self),
    совпадение по нормализованному email, телефону (последние 10 цифр) или
    telegram-username. (Раньше сверял только с архивом — теперь и активных между собой.)

    Вызывается на путях создания АКТИВНОГО кандидата (ручное добавление,
    расширение, загрузка резюме), чтобы пометить новый профиль флагом
    extra_data.hidden_duplicate_id. Возвращает id архивного совпадения или None.
    Исключает self и пары, признанные «разными людьми» (duplicate_pair_decisions).
    """
    # Единый матчер (build_dup_keys + find_duplicate_matches) — те же правила,
    # что теперь использует расширение (check-duplicate). Приоритет: сильное
    # совпадение (source/email/telegram/name) в порядке id-desc, иначе первое по
    # телефону — как было в прежней прямой реализации.
    from .duplicate_matcher import best_match, keys_of_entity
    from .duplicate_decisions import dismissed_for

    keys = keys_of_entity(entity)
    dismissed: Set[int] = await dismissed_for(db, entity)

    matches = await find_duplicate_matches(
        db, entity.org_id, keys, exclude_id=entity.id, dismissed=dismissed
    )
    # Приоритет выбора: сильное совпадение (source/email/telegram/name) → soft →
    # phone. Телефон НИЖЕ мягкого намеренно: один номер бывает общим (родственники,
    # рабочий), а мягкий флаг уже означает совпадение нескольких признаков.
    chosen = best_match(matches)
    match_id = chosen.entity_id if chosen is not None else None
    if chosen is not None and getattr(entity, "id", None):
        ne = dict(entity.extra_data) if isinstance(entity.extra_data, dict) else {}
        ne["hidden_duplicate_meta"] = {
            "strength": chosen.strength,
            "confidence": chosen.confidence,
            "reasons": chosen.reasons,
            "matched_id": chosen.entity_id,
            "level": chosen.level,
        }
        entity.extra_data = ne

    # Помечаем найденного дубля ОБРАТНОЙ ссылкой (его hidden_duplicate_id → наш id),
    # чтобы баннер «Похожий кандидат» появлялся у ОБОИХ профилей пары.
    if match_id is not None and getattr(entity, "id", None):
        dup = (await db.execute(select(Entity).where(Entity.id == match_id))).scalar_one_or_none()
        if dup is not None:
            de = dup.extra_data if isinstance(dup.extra_data, dict) else {}
            # Решения пары симметричны (одна строка на пару), и найденный дубль уже
            # прошёл фильтр dismissed — здесь остаётся только старый список у него.
            from .duplicate_decisions import legacy_dismissed
            ddis = legacy_dismissed(de)
            # Слабая пара не вытесняет сильную: «Кирилл Иванов» с точным флагом (имя +
            # телефон) не должен переключаться на однофамильца, совпавшего лишь именем.
            cur_meta = de.get("hidden_duplicate_meta") or {}
            cur_rank = (cur_meta.get("level") == "exact", cur_meta.get("confidence") or 0)
            new_rank = (chosen.level == "exact", chosen.confidence)
            keeps_better = bool(de.get("hidden_duplicate_id")) and cur_rank > new_rank
            if (
                entity.id not in ddis
                and de.get("hidden_duplicate_id") != entity.id
                and not keeps_better
            ):
                nde = dict(de)
                nde["hidden_duplicate_id"] = entity.id
                # Признаки пары симметричны — второй стороне та же мета. Без неё
                # баннер у старого кандидата не знал уровня и процента («0%»).
                nde["hidden_duplicate_meta"] = {
                    **ne["hidden_duplicate_meta"], "matched_id": entity.id,
                }
                dup.extra_data = nde
    return match_id


# Поля ключей, от которых зависит «тот же ли это человек». Правка остального
# (этап, комментарии, зарплата) пересчёта дублей не запускает.
_IDENTITY_KEY_FIELDS = (
    "emails", "email_locals", "phone_keys", "tg_names", "name", "source_key",
    "birth_norm", "patronymics", "resume_emails", "resume_phone_keys", "resume_tg",
)


def identity_fingerprint(entity: Entity) -> tuple:
    """Снимок ключей личности кандидата — сравнить «до» и «после» правки."""
    from .duplicate_matcher import keys_of_entity
    keys = keys_of_entity(entity)
    out = []
    for f in _IDENTITY_KEY_FIELDS:
        v = keys.get(f)
        out.append(tuple(sorted(v)) if isinstance(v, (set, frozenset, list)) else v)
    return tuple(out)


async def refresh_duplicate_flag(db: AsyncSession, entity: Entity) -> Optional[int]:
    """Пересчитать флаг «похожий кандидат» у одной анкеты по её ТЕКУЩИМ данным.

    Нашлось совпадение — флаг и мета указывают на него (и вторая сторона получает
    обратную ссылку). Не нашлось — флаг снимается. Исключение — совпадение по
    тексту резюме: оно не зависит от ФИО/контактов и правкой карточки не
    отменяется, если пару не признали «разными людьми». Не коммитит.
    """
    from .duplicate_decisions import dismissed_for

    before = dict(entity.extra_data) if isinstance(entity.extra_data, dict) else {}
    old_meta = before.get("hidden_duplicate_meta") or {}
    old_id = before.get("hidden_duplicate_id")

    new_id = await detect_archived_duplicate(db, entity)
    extra = dict(entity.extra_data) if isinstance(entity.extra_data, dict) else {}
    if new_id:
        extra["hidden_duplicate_id"] = new_id
    elif (
        old_id
        and old_meta.get("strength") == "text"
        and old_id not in await dismissed_for(db, entity)
    ):
        new_id = old_id  # текстовый дубль остаётся как был
    else:
        extra.pop("hidden_duplicate_id", None)
        extra.pop("hidden_duplicate_meta", None)
    entity.extra_data = extra
    return new_id


async def recheck_duplicates_after_edit(db: AsyncSession, entity: Entity) -> Set[int]:
    """Правка ФИО/контактов/даты рождения: пересчитать совпадения сразу.

    1. Сама анкета: новое совпадение — плашка появляется, причина исчезла —
       снимается.
    2. Анкеты, чья плашка смотрела на эту: пересчитываются тоже — иначе после
       исправленной опечатки в телефоне у второй стороны висела бы старая
       плашка.
    Возвращает id затронутых ДРУГИХ анкет. Не коммитит.
    """
    touched: Set[int] = set()
    old_id = (entity.extra_data or {}).get("hidden_duplicate_id") if isinstance(entity.extra_data, dict) else None
    new_id = await refresh_duplicate_flag(db, entity)
    if new_id:
        touched.add(new_id)  # получил обратную ссылку

    partners = (await db.execute(
        select(Entity).where(
            Entity.org_id == entity.org_id,
            Entity.type == EntityType.candidate,
            Entity.id != entity.id,
            Entity.extra_data["hidden_duplicate_id"].as_integer() == entity.id,
        )
    )).scalars().all()
    for other in partners:
        prev = (other.extra_data or {}).get("hidden_duplicate_id")
        now = await refresh_duplicate_flag(db, other)
        if now != prev:
            touched.add(other.id)

    logger.info(
        f"DUP_RECHECK entity {entity.id}: flag {old_id}->{new_id}, "
        f"partners rechecked={[o.id for o in partners]} touched={sorted(touched)}"
    )
    return touched

