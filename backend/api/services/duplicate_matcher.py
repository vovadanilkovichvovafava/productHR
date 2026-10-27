"""ЕДИНОЕ ядро сравнения кандидатов на дубль.

Зачем модуль появился (этап 0 переделки дедупа). До него решение «это тот же
человек» принимали ПЯТЬ независимых кусков кода с разошедшимися правилами:

1. ``similarity.find_duplicate_matches`` — тиры source/email/telegram/name/phone +
   мягкий скоринг; питает баннер «Похожий кандидат» и расширение hh.ru;
2. ``similarity.detect_duplicates`` — своя шкала (имя 40, email 30, телефон 30,
   telegram 30, компания+навыки 20, порог 30); питает окно сравнения;
3. ``services/duplicates.py`` — третья шкала (0.5/0.35/0.15), мёртвый код;
4. ``routes/entities/crud.rescan_active_duplicates`` — свой индекс ключей, ФИО
   сверялось ТОЧНОЙ строкой (без транслита и отчеств);
5. ``routes/entities/crud.find_archive_duplicates`` — union-find вообще без ФИО.

Из-за этого баннер и карточка сравнения показывали РАЗНЫЕ проценты по одной паре,
а пере-скан находил не то же самое, что детект на создании.

Теперь правило одно: :func:`compare_key_sets` — чистая функция над двумя наборами
ключей ``build_dup_keys``. Всё остальное (обход БД, блокировка-индекс, обёртки для
роутов) построено вокруг неё.

Уровни (``strength``), в порядке приоритета:
    source  — тот же канонический URL резюме;
    email   — полный адрес ИЛИ локальная часть до «@»;
    telegram— личный @хэндл (мусорные ярлыки источника отсеяны);
    name    — связка Фамилия+Имя (транслит, отчества, гомоглифы, опечатка ≤1);
    phone   — тот же номер с кодом страны (E.164) или те же последние 10 цифр;
    soft    — мягкий скоринг личности (``score_soft_identity`` ≥ порога);
    text    — совпал ТЕКСТ резюме (инфо-сигнал, слияние по нему не предлагаем).

``confidence`` — ОДНО число на пару. 100 — только «точный» уровень (``level``
exact: совпало ≥2 признака личности, красный баннер). Одиночный признак —
«возможно тот же» (possible, жёлтый): сумма весов ``EVIDENCE_WEIGHTS``, для
``soft`` — балл мягкого скоринга, для ``text`` — процент Жаккара. Раньше окно сравнения считало своё,
поэтому «точное совпадение» в баннере превращалось в «30%» на карточке.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import Entity, EntityType
# similarity импортирует ЭТОТ модуль внутри тел функций (ленивo), поэтому обратный
# импорт на уровне модуля цикла не создаёт.
from .similarity import (
    DupMatch,
    DupSignal,
    POSSIBLE_CONFIDENCE_CAP,
    evidence_confidence,
    match_level,
    build_dup_keys,
    email_locals_of,
    is_matchable_telegram,
    names_match_surname_firstname,
    normalize_telegram,
    score_soft_identity,
    transliterate_en_to_ru,
    fold_yo,
    fold_homoglyphs,
    TG_COMMON_THRESHOLD,
)

logger = logging.getLogger("hr-analyzer.duplicate_matcher")

# Уровни-идентификаторы в порядке убывания приоритета. Совпадение любого из них
# задаёт тир пары; «точным» (100%) пара становится только при ≥2 признаках.
IDENTITY_ORDER: Tuple[str, ...] = ("source", "email", "telegram", "name", "phone")

# Человекочитаемые причины (идут в баннер и в чипы карточки сравнения).
SIGNAL_LABELS: Dict[str, str] = {
    "source": "Та же ссылка на резюме",
    "email": "Совпадение email",
    "telegram": "Совпадение Telegram",
    "name": "Совпадение имени (с учётом транслитерации)",
    "phone": "Совпадение телефона",
    "company": "Та же компания + похожие навыки",
    "resume_text": "Текст резюме совпадает",
    # Совпало с контактом из шапки текста резюме (не из полей карточки).
    "email_resume": "Совпадение email (из текста резюме)",
    "phone_resume": "Совпадение телефона (из текста резюме)",
    "telegram_resume": "Совпадение Telegram (из текста резюме)",
}


@dataclass
class CandidateKeys:
    """Кандидат, разобранный в ключи дедупа (одна строка выборки из БД)."""
    entity_id: int
    name: str
    is_archived: bool
    keys: dict
    extra_data: dict = field(default_factory=dict)


def _first(values: Sequence[str], fallback: str = "") -> str:
    for v in values:
        if v:
            return v
    return fallback


def compare_key_sets(a: dict, b: dict) -> Tuple[Optional[str], int, List[DupSignal]]:
    """ЕДИНСТВЕННОЕ место, где решается «это один человек».

    Принимает два набора ключей :func:`build_dup_keys` и возвращает
    ``(strength, confidence, signals)``. ``strength`` = None, если пара не дубль.

    Сигналы собираются ВСЕ (и сильные, и мягкие) — они нужны окну сравнения, чтобы
    подсветить ровно те поля, из-за которых пара считается дублем. ``strength`` же
    берётся по приоритету :data:`IDENTITY_ORDER`, а мягкий скоринг поднимает флаг
    только когда сильных сигналов нет (иначе «возможно тот же человек» перебивало
    бы «точное совпадение»).
    """
    signals: List[DupSignal] = []

    # --- Level-1: идентификаторы ------------------------------------------------
    a_src, b_src = a.get("source_key") or "", b.get("source_key") or ""
    if a_src and a_src == b_src:
        signals.append(DupSignal("source", SIGNAL_LABELS["source"], 100, True, a_src, b_src))

    a_emails: Set[str] = a.get("emails") or set()
    b_emails: Set[str] = b.get("emails") or set()
    card_email_hit = a_emails & b_emails
    # С контактами из шапки резюме (у одной или обеих сторон).
    full_hit = (a_emails | (a.get("resume_emails") or set())) & (
        b_emails | (b.get("resume_emails") or set())
    )
    local_hit = (a.get("email_locals") or email_locals_of(a_emails)) & (
        b.get("email_locals") or email_locals_of(b_emails)
    )
    if full_hit or local_hit:
        # Почта сверяется и по полному адресу, и по локали до «@»: смена домена
        # gmail→mail не уводит от дубля (служебные локали отсеяны email_locals_of).
        from_resume = not card_email_hit and not local_hit
        signals.append(DupSignal(
            "email", SIGNAL_LABELS["email_resume" if from_resume else "email"], 100, True,
            _first(sorted(full_hit) or sorted(a_emails)),
            _first(sorted(full_hit) or sorted(b_emails)),
        ))

    a_tg, b_tg = a.get("tg_names") or set(), b.get("tg_names") or set()
    tg_hit = (a_tg | (a.get("resume_tg") or set())) & (b_tg | (b.get("resume_tg") or set()))
    tg_hit = {t for t in tg_hit if is_matchable_telegram(t)}
    if tg_hit:
        from_resume = not (a_tg & b_tg & tg_hit)
        signals.append(DupSignal(
            "telegram", SIGNAL_LABELS["telegram_resume" if from_resume else "telegram"], 100, True,
            "@" + _first(sorted(tg_hit)), "@" + _first(sorted(tg_hit)),
        ))

    a_name, b_name = a.get("name") or "", b.get("name") or ""
    if (
        a.get("name_ok") and b.get("name_ok")
        and names_match_surname_firstname(a_name, b_name)
    ):
        signals.append(DupSignal("name", SIGNAL_LABELS["name"], 100, True, a_name, b_name))

    a_ph, b_ph = a.get("phone_keys") or set(), b.get("phone_keys") or set()
    phone_hit = (a_ph | (a.get("resume_phone_keys") or set())) & (
        b_ph | (b.get("resume_phone_keys") or set())
    )
    if phone_hit:
        from_resume = not (a_ph & b_ph)
        p = _first(sorted(phone_hit))
        signals.append(DupSignal(
            "phone", SIGNAL_LABELS["phone_resume" if from_resume else "phone"], 100, True, p, p,
        ))

    # --- Level-2: мягкий скоринг личности --------------------------------------
    # Считаем ВСЕГДА (не только при отсутствии сильных): его компоненты — ФИО, дата
    # рождения, 7 цифр телефона, город — это подсказки для окна сравнения.
    soft = score_soft_identity(a, b)
    # Мягкие компоненты кладём в ТЕ ЖЕ поля, что и сильные сигналы (ФИО → name,
    # 7 цифр → phone, локаль почты → email): окно сравнения подсвечивает поле, а не
    # внутреннее имя правила, и один факт не дублируется двумя строками.
    soft_fields = {
        "Фамилия и имя совпали": ("name", a_name, b_name),
        "Дата рождения совпала": ("birth_date", a.get("birth_norm") or "", b.get("birth_norm") or ""),
        "Возраст совпадает (±1 год)": ("age", str(a.get("age") or ""), str(b.get("age") or "")),
        "Последние 7 цифр телефона совпали": (
            "phone",
            _first(sorted((a.get("phones7") or set()) & (b.get("phones7") or set()))),
            _first(sorted((a.get("phones7") or set()) & (b.get("phones7") or set()))),
        ),
        "Email до @ совпал": (
            "email",
            _first(sorted(local_hit)), _first(sorted(local_hit)),
        ),
        "Telegram совпал": ("telegram", _first(sorted(tg_hit)), _first(sorted(tg_hit))),
    }
    seen_fields = {s.field for s in signals}
    for reason in soft.reasons:
        fname, left, right = soft_fields.get(reason, (reason, "", ""))
        if fname in seen_fields:
            continue  # тот же факт уже описан сильным сигналом
        signals.append(DupSignal(fname, reason, 0, False, left, right))

    # --- Компания + навыки (слабый контекстный сигнал, сам дубль не поднимает) ---
    a_company, b_company = a.get("company") or "", b.get("company") or ""
    if a_company and a_company == b_company:
        a_skills: Set[str] = a.get("skills") or set()
        b_skills: Set[str] = b.get("skills") or set()
        if a_skills and b_skills:
            common = a_skills & b_skills
            if len(common) / len(a_skills | b_skills) > 0.5:
                signals.append(DupSignal(
                    "company", SIGNAL_LABELS["company"], 0, False, a_company, b_company,
                ))

    # Тир — ТОЛЬКО по сильным сигналам. Мягкие компоненты лежат в тех же полях
    # (phone7 → "phone", email-локаль → "email"), поэтому фильтр по identity
    # обязателен: иначе «совпали последние 7 цифр» выдавало бы себя за точный
    # телефон и давало 100%.
    identity_fields = {x.field for x in signals if x.identity}
    strength = next((s for s in IDENTITY_ORDER if s in identity_fields), None)
    # Процент — от ЧИСЛА совпавших признаков: 100 только при ≥2 (красный баннер),
    # одиночное совпадение — «возможно тот же человек» (решение владельца 21.09).
    if strength is not None:
        return strength, evidence_confidence(signals), signals
    if soft.is_flag:
        conf = 100 if match_level(signals) == "exact" else min(POSSIBLE_CONFIDENCE_CAP, soft.confidence)
        return "soft", conf, signals
    return None, 0, signals


def identity_block_keys(keys: dict) -> List[str]:
    """Ключи «блокировки» для пере-скана: по ним пара попадает на полное сравнение.

    Имя даёт ключ по ПАРЕ слов ФИО (канонические первые 4 буквы обоих, без учёта
    порядка): «Иванов Кирилл», «Кирилл Иванов» и «Иванов Кирилл Владимирович»
    встречаются в корзине «иван|кири». Отчества, перестановка и опечатка в хвосте
    слова пару не разводят. Точность всё равно решает :func:`compare_key_sets` —
    здесь только отбор пар-кандидатов.

    Раньше ключом было КАЖДОЕ слово отдельно, и в корзину «алек» падали все
    Александры, Александровичи и Александровны: на проде (8 тыс. анкет) это
    ~7,5 млн пар и ~8 минут сверки, во время которых сервер не отвечал никому
    (22.09.2026). Совпадение ФИО по правилам и так требует фамилию И имя вместе.
    """
    out: List[str] = []
    if keys.get("source_key"):
        out.append("s:" + keys["source_key"])
    for e in (keys.get("emails") or set()) | (keys.get("resume_emails") or set()):
        out.append("e:" + e)
    for loc in (keys.get("email_locals") or set()):
        out.append("el:" + loc)
    for p in (keys.get("phone_keys") or set()) | (keys.get("resume_phone_keys") or set()):
        out.append("p:" + p)
    for t in (keys.get("tg_names") or set()) | (keys.get("resume_tg") or set()):
        if is_matchable_telegram(t):
            out.append("t:" + t)
    if keys.get("name_ok"):
        words = (keys.get("name") or "").split()
        # Отчество в совпадении ФИО не участвует (нужны фамилия и имя), а корзины
        # «имя|отчество» (Владимир Александрович) — самые большие. Убираем его,
        # если без него остаётся хотя бы два слова: у фамилии «Петрович» под
        # правило отчества попадает и сама фамилия.
        pats = keys.get("patronymics") or set()
        plain = [w for w in words if w.strip("-_.,") not in pats]
        if len(plain) >= 2:
            words = plain
        stems: List[str] = []
        for word in words:
            w = fold_yo(fold_homoglyphs(word).lower().strip("-_.,"))
            if len(w) < 2:
                continue
            canon = w if any("а" <= ch <= "я" or ch == "ё" for ch in w) else transliterate_en_to_ru(w)
            stems.append(fold_yo(canon)[:4])
        for x, y in combinations(sorted(set(stems)), 2):
            out.append(f"n:{x}|{y}")
    # Дедуп обязателен: «Иванов Иван» даёт ключ n:иван дважды, и кандидат попадал в
    # одну корзину два раза — то есть сравнивался сам с собой и всегда «совпадал».
    return sorted(set(out))


def keys_of_entity(entity: Entity) -> dict:
    """Ключи дедупа для ORM-сущности (обёртка над build_dup_keys)."""
    return build_dup_keys(
        name=entity.name,
        email=entity.email,
        phone=entity.phone,
        emails=entity.emails,
        phones=entity.phones,
        telegram_usernames=entity.telegram_usernames,
        extra_data=entity.extra_data,
        company=getattr(entity, "company", None),
    )


def _keys_of_row(m) -> dict:
    """Ключи из строки укороченной выборки (см. _CANDIDATE_COLUMNS)."""
    extra = m.get(Entity.extra_data)
    return build_dup_keys(
        name=m[Entity.name],
        email=m[Entity.email],
        phone=m[Entity.phone],
        emails=m.get(Entity.emails),
        phones=m.get(Entity.phones),
        telegram_usernames=m[Entity.telegram_usernames],
        extra_data=extra if isinstance(extra, dict) else {},
        company=m.get(Entity.company),
    )


_CANDIDATE_COLUMNS = [
    Entity.id, Entity.name, Entity.email, Entity.phone, Entity.emails, Entity.phones,
    Entity.telegram_usernames, Entity.is_archived, Entity.company, Entity.extra_data,
]

# Что из extra_data нужно ПОСЛЕ разбора в ключи: сигнал «текст резюме совпадает»
# (_text_twin_signal) и должность в отчёте сверки архива. Остальное (опыт,
# комментарии, текст резюме) в памяти не держим.
_EXTRA_KEEP = ("position", "text_twin", "hidden_duplicate_meta")

# Разобранные ключи по id кандидата: (отпечаток, CandidateKeys). Расширение
# проверяет дубли на КАЖДОМ открытии попапа, и каждая проверка заново тянула всех
# кандидатов орга с полным extra_data и разбирала их телефоны/ФИО — на проде
# 8 250 карточек (7 149 в архиве), 2–5 с на запрос (22.10.2026). Отпечаток — md5
# полей, из которых строятся ключи, считается в базе (наружу уходит 32 символа
# вместо всего extra_data): поменялась карточка — её ключи пересчитываются,
# остальные берутся отсюда. updated_at для этого не годится: две правки в одной
# транзакции получают одно now(). extra_data берётся целиком (json хранится
# текстом, md5 по нему дешевле, чем разбирать поля), поэтому лишний пересчёт
# бывает и после нового комментария — это одна карточка. Кэш свой у каждого
# процесса и пуст после перезапуска; только Postgres (в SQLite-тестах md5 нет —
# там каждый раз полный разбор, как раньше).
_KEYS_CACHE: Dict[int, Tuple[str, CandidateKeys]] = {}


def _fingerprint():
    from sqlalchemy import Text, cast, func
    parts = [
        Entity.name, Entity.email, Entity.phone, cast(Entity.emails, Text),
        cast(Entity.phones, Text), cast(Entity.telegram_usernames, Text),
        cast(Entity.is_archived, Text), Entity.company, cast(Entity.extra_data, Text),
    ]
    # coalesce: пустое поле и NULL дают разный отпечаток.
    return func.md5(func.concat_ws("|", *[func.coalesce(p, "\x01") for p in parts]))


async def load_candidate_keys(
    db: AsyncSession,
    org_id: Optional[int],
    *,
    exclude_id: Optional[int] = None,
    include_archived: bool = True,
    archived_only: bool = False,
) -> List[CandidateKeys]:
    """Выборка кандидатов организации, разобранная в ключи дедупа.

    Полный проход по кандидатам org, но в два шага: сначала лёгкий список
    «id + отпечаток», затем полные строки — только у тех, кого нет в _KEYS_CACHE
    или у кого отпечаток сменился.
    """
    if db.get_bind().dialect.name != "postgresql":
        return await _load_candidate_keys_full(
            db, org_id, exclude_id=exclude_id,
            include_archived=include_archived, archived_only=archived_only,
        )
    q = select(Entity.id, _fingerprint()).where(Entity.type == EntityType.candidate)
    if org_id is not None:
        q = q.where(Entity.org_id == org_id)
    if exclude_id is not None:
        q = q.where(Entity.id != exclude_id)
    if archived_only:
        q = q.where(Entity.is_archived.is_(True))
    elif not include_archived:
        q = q.where(Entity.is_archived.is_not(True))
    stamps = (await db.execute(q.order_by(Entity.id.desc()))).all()

    stale = [
        eid for eid, fp in stamps
        if eid not in _KEYS_CACHE or _KEYS_CACHE[eid][0] != fp
    ]
    for i in range(0, len(stale), 1000):
        chunk = stale[i:i + 1000]
        rows = (await db.execute(
            select(_fingerprint().label("fp"), *_CANDIDATE_COLUMNS).where(Entity.id.in_(chunk))
        )).all()
        for r in rows:
            m = r._mapping
            extra = m[Entity.extra_data] if isinstance(m[Entity.extra_data], dict) else {}
            _KEYS_CACHE[m[Entity.id]] = (m["fp"], CandidateKeys(
                entity_id=m[Entity.id],
                name=m[Entity.name] or "",
                is_archived=bool(m[Entity.is_archived]),
                keys=_keys_of_row(m),
                extra_data={k: extra[k] for k in _EXTRA_KEEP if k in extra},
            ))

    # Новый объект на каждый вызов: _scan_pairs переприсваивает it.keys, и это не
    # должно протекать в кэш.
    items: List[CandidateKeys] = []
    for eid, _ in stamps:
        cached = _KEYS_CACHE.get(eid)
        if cached is None:
            continue  # удалили между двумя шагами
        c = cached[1]
        items.append(CandidateKeys(
            entity_id=c.entity_id, name=c.name, is_archived=c.is_archived,
            keys=c.keys, extra_data=c.extra_data,
        ))
    return items


async def _load_candidate_keys_full(
    db: AsyncSession,
    org_id: Optional[int],
    *,
    exclude_id: Optional[int] = None,
    include_archived: bool = True,
    archived_only: bool = False,
) -> List[CandidateKeys]:
    """Прежний полный разбор без кэша (не-Postgres)."""
    q = select(*_CANDIDATE_COLUMNS).where(Entity.type == EntityType.candidate)
    if org_id is not None:
        q = q.where(Entity.org_id == org_id)
    if exclude_id is not None:
        q = q.where(Entity.id != exclude_id)
    if archived_only:
        q = q.where(Entity.is_archived.is_(True))
    elif not include_archived:
        q = q.where(Entity.is_archived.is_not(True))
    rows = (await db.execute(q.order_by(Entity.id.desc()))).all()

    items: List[CandidateKeys] = []
    for r in rows:
        m = r._mapping
        extra = m[Entity.extra_data]
        items.append(CandidateKeys(
            entity_id=m[Entity.id],
            name=m[Entity.name] or "",
            is_archived=bool(m[Entity.is_archived]),
            keys=_keys_of_row(m),
            extra_data=extra if isinstance(extra, dict) else {},
        ))
    return items


def telegram_name_frequency(items: Sequence[CandidateKeys], extra_names: Optional[Dict[str, str]] = None) -> Dict[str, Set[str]]:
    """Сколько РАЗНЫХ имён стоит за каждым @хэндлом.

    Один человек, разъехавшийся на несколько карточек с одним хэндлом, даёт одно
    имя — матчим. Мусорный ярлык источника («telegram», «hh_b2b») сидит у многих
    разных имён — не идентификатор.
    """
    freq: Dict[str, Set[str]] = {}
    for it in items:
        nm = (it.name or "").strip().lower()
        for t in (it.keys.get("tg_names") or set()):
            freq.setdefault(t, set()).add(nm)
    for t, nm in (extra_names or {}).items():
        freq.setdefault(t, set()).add(nm)
    return freq


def filter_common_telegram(keys: dict, freq: Dict[str, Set[str]]) -> dict:
    """Убрать из ключей «общие» @хэндлы (у ≥ TG_COMMON_THRESHOLD разных имён)."""
    tg = {
        t for t in (keys.get("tg_names") or set())
        if is_matchable_telegram(t) and len(freq.get(t, ())) < TG_COMMON_THRESHOLD
    }
    if tg == (keys.get("tg_names") or set()):
        return keys
    out = dict(keys)
    out["tg_names"] = tg
    return out


def _text_twin_signal(
    my_extra: dict, other_id: int, other_extra: dict, self_id: Optional[int] = None,
) -> Optional[Tuple[int, DupSignal]]:
    """Инфо-сигнал «текст резюме совпадает» из УЖЕ сохранённого text_twin.

    Считается не здесь, а detect_resume_text_twin при создании кандидата (Жаккар по
    шинглам — дорого на каждую пару). Сознательно НЕ поднимает слияние: у разных
    людей бывают анкеты по одному шаблону. Читаем обе стороны связи — инициатор
    хранит extra_data.text_twin, у цели остаётся только backreference в мете.
    """
    tw = my_extra.get("text_twin")
    if isinstance(tw, dict) and tw.get("twin_id") == other_id:
        pct = round((tw.get("similarity") or 0) * 100)
        return pct, DupSignal("resume_text", f"Текст резюме совпадает ({pct}%)", 0, False, "", "")
    tw_other = other_extra.get("text_twin")
    if isinstance(tw_other, dict) and self_id is not None and tw_other.get("twin_id") == self_id:
        pct = round((tw_other.get("similarity") or 0) * 100)
        return pct, DupSignal("resume_text", f"Текст резюме совпадает ({pct}%)", 0, False, "", "")
    meta = my_extra.get("hidden_duplicate_meta")
    if isinstance(meta, dict) and meta.get("strength") == "text" and meta.get("matched_id") == other_id:
        pct = int(meta.get("confidence") or 0)
        return pct, DupSignal("resume_text", f"Текст резюме совпадает ({pct}%)", 0, False, "", "")
    return None


# Старый список «разные люди» из extra_data. Основное хранилище решений теперь
# таблица duplicate_pair_decisions — см. services/duplicate_decisions.py.
from .duplicate_decisions import legacy_dismissed as _dismissed_ids  # noqa: E402


async def match_entities(
    db: AsyncSession,
    org_id: Optional[int],
    keys: dict,
    *,
    exclude_id: Optional[int] = None,
    dismissed: Optional[Set[int]] = None,
    include_archived: bool = True,
    include_text: bool = False,
    own_extra_data: Optional[dict] = None,
    allowed_ids: Optional[Set[int]] = None,
    self_id: Optional[int] = None,
) -> List[DupMatch]:
    """Все совпадения для одного набора ключей. Порядок — id DESC (как раньше).

    ``include_text`` добавляет пары, связанные только совпадением ТЕКСТА резюме
    (окно сравнения показывает их отдельным тиром; баннер слияния — нет).
    ``allowed_ids`` — фильтр видимости (права доступа), применяется до сравнения.
    """
    dismissed = set(dismissed or set())
    items = await load_candidate_keys(
        db, org_id, exclude_id=exclude_id, include_archived=include_archived,
    )
    if allowed_ids is not None:
        items = [it for it in items if it.entity_id in allowed_ids]

    freq = telegram_name_frequency(
        items, {t: (keys.get("name") or "").strip().lower() for t in (keys.get("tg_names") or set())}
    )
    my_keys = filter_common_telegram(keys, freq)
    my_extra = own_extra_data if isinstance(own_extra_data, dict) else {}

    out: List[DupMatch] = []
    for it in items:
        if it.entity_id in dismissed:
            continue
        strength, confidence, signals = compare_key_sets(
            my_keys, filter_common_telegram(it.keys, freq)
        )
        text_hit = _text_twin_signal(
            my_extra, it.entity_id, it.extra_data, self_id if self_id is not None else exclude_id,
        ) if include_text else None
        if text_hit is not None:
            pct, sig = text_hit
            signals.append(sig)
            if strength is None:
                strength, confidence = "text", pct
            elif match_level(signals) == "exact":
                # Текст резюме + ещё один признак личности — это уже «точно он».
                confidence = 100
        if strength is None:
            continue
        out.append(DupMatch(
            entity_id=it.entity_id,
            entity_name=it.name,
            is_archived=it.is_archived,
            strength=strength,
            confidence=confidence,
            reasons=[s.label for s in signals if not s.identity] if strength in ("soft", "text")
            else [s.label for s in signals],
            signals=signals,
        ))
    return out


async def scan_org_pairs(
    db: AsyncSession,
    org_id: Optional[int],
    *,
    archived_only: bool = False,
) -> Tuple[List[CandidateKeys], Dict[int, List[DupMatch]]]:
    """Пере-скан всей организации: для каждого кандидата — его совпадения.

    Пары отбираются по общим ключам-блокировкам (:func:`identity_block_keys`), а
    решение по каждой паре принимает :func:`compare_key_sets` — то же правило, что
    у детекта на создании. Раньше пере-скан сверял ФИО точной строкой и поэтому
    находил не то же, что баннер.
    """
    items = await load_candidate_keys(db, org_id, archived_only=archived_only)
    # Перебор пар — чистый CPU. В основном потоке он держал бы весь сервер: пока
    # считаются пары, сайт не отвечает никому (прод, 22.09.2026 — ~8 минут).
    # В отдельном потоке цикл событий продолжает обслуживать запросы.
    matches = await asyncio.to_thread(_scan_pairs, items)
    return items, matches


# Корзина больше этого — общее мусорное значение, а не один человек (см. _scan_pairs).
MAX_BUCKET_SIZE = 200


def _scan_pairs(items: List[CandidateKeys]) -> Dict[int, List[DupMatch]]:
    """Все пары-совпадения среди items (синхронно; вызывается в отдельном потоке)."""
    started = time.perf_counter()
    freq = telegram_name_frequency(items)
    by_id = {it.entity_id: it for it in items}

    buckets: Dict[str, List[int]] = {}
    for it in items:
        it.keys = filter_common_telegram(it.keys, freq)
        for k in identity_block_keys(it.keys):
            buckets.setdefault(k, []).append(it.entity_id)

    checked: Set[Tuple[int, int]] = set()
    matches: Dict[int, List[DupMatch]] = {}
    skipped: List[Tuple[str, int]] = []
    for bkey, ids in buckets.items():
        if len(ids) < 2:
            continue
        if len(ids) > MAX_BUCKET_SIZE:
            # Сотни анкет с одним «ключом» — это не один человек, а мусорное общее
            # значение (служебный телефон, заглушка). Перебор такой корзины — это
            # десятки тысяч пар ради ложных совпадений.
            skipped.append((bkey, len(ids)))
            continue
        for i, a_id in enumerate(ids):
            for b_id in ids[i + 1:]:
                if a_id == b_id:
                    continue
                pair = (a_id, b_id) if a_id < b_id else (b_id, a_id)
                if pair in checked:
                    continue
                checked.add(pair)
                a, b = by_id[a_id], by_id[b_id]
                strength, confidence, signals = compare_key_sets(a.keys, b.keys)
                if strength is None:
                    continue
                matches.setdefault(a_id, []).append(DupMatch(
                    entity_id=b_id, entity_name=b.name, is_archived=b.is_archived,
                    strength=strength, confidence=confidence,
                    reasons=[s.label for s in signals], signals=signals,
                ))
                matches.setdefault(b_id, []).append(DupMatch(
                    entity_id=a_id, entity_name=a.name, is_archived=a.is_archived,
                    strength=strength, confidence=confidence,
                    reasons=[s.label for s in signals], signals=signals,
                ))
    for lst in matches.values():
        lst.sort(key=lambda m: (-m.confidence, -m.entity_id))
    logger.info(
        f"DUP_SCAN items={len(items)} buckets={len(buckets)} pairs={len(checked)} "
        f"with_matches={len(matches)} took={time.perf_counter() - started:.1f}s"
        + (f" skipped_buckets={skipped[:10]}" if skipped else "")
    )
    return matches


# Порядок выбора «того самого» совпадения для флага на карточке. Телефон стоит
# НИЖЕ мягкого тира сознательно (так было и в прежнем detect_archived_duplicate):
# один номер бывает общим — родственники, рабочий телефон, — а мягкий флаг уже
# означает совпадение нескольких независимых признаков.
BEST_MATCH_ORDER: Tuple[str, ...] = ("source", "email", "telegram", "name", "soft", "phone", "text")


def best_match(
    matches: Sequence[DupMatch], order: Sequence[str] = BEST_MATCH_ORDER,
) -> Optional[DupMatch]:
    """Лучшее совпадение: по тиру (см. :data:`BEST_MATCH_ORDER`), внутри тира —
    первое в порядке выдачи (id DESC)."""
    # Сначала «точные» (совпало ≥2 признака), и только потом по тиру: иначе
    # баннер мог показать одиночное совпадение почты, когда рядом есть анкета,
    # совпавшая и по почте, и по телефону.
    for pool in ([m for m in matches if m.level == "exact"], list(matches)):
        for s in order:
            hit = next((m for m in pool if m.strength == s), None)
            if hit is not None:
                return hit
    return None


__all__ = [
    "CandidateKeys", "IDENTITY_ORDER", "SIGNAL_LABELS",
    "compare_key_sets", "identity_block_keys", "keys_of_entity",
    "load_candidate_keys", "telegram_name_frequency", "filter_common_telegram",
    "match_entities", "scan_org_pairs", "best_match", "_dismissed_ids",
]
