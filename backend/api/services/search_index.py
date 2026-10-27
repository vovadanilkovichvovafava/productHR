"""Умный поиск кандидатов: денормализованное search_name + матчер по pg_trgm.

Заказчица требует поиск как в Huntflow: транслитерация (Roman Fattakhov =
Роман Фаттахов), любой порядок слов, терпимость к опечаткам, одно окно без
настроек. Архитектура (согласована): вся тяжёлая работа — в PostgreSQL по
триграммному индексу; Python лишь готовит варианты запроса (несколько слов).

- build_search_name — денормализованный блоб: ФИО в ДВУХ алфавитах (через
  similarity.generate_name_variants) + должность/компания/теги. Пишется в
  entities.search_name на insert/update (event-листенеры ниже), индексируется
  GIN-триграммой (см. start.sh).
- smart_name_filter / smart_name_score — SQL-условие и ранг для запроса: каждое
  слово запроса (в любом алфавите) триграммно присутствует в search_name,
  порядок не важен, опечатки прощаются (word_similarity).
"""
import re
from typing import Optional, List
from sqlalchemy import cast, event, func, or_, and_, select, text, String
from sqlalchemy.sql.elements import ColumnElement

from ..models.database import Entity
from .similarity import (
    generate_name_variants, _name_word_variants, fold_yo,
    transliterate_ru_to_en, transliterate_en_to_ru,
)

# Доступно ли расширение pg_trgm (нужно для оператора %> и word_similarity).
# None — ещё не проверяли; True/False — установлено ли. На managed-Postgres без
# superuser расширение может не встать (см. start.sh best-effort) — тогда поиск
# ДЕГРАДИРУЕТ до старого ILIKE, а не падает 500 на несуществующем операторе.
_pg_trgm_available: Optional[bool] = None


async def ensure_pg_trgm_checked(db) -> bool:
    """Один раз (с кэшем) проверяет наличие pg_trgm по переданной сессии. Вызывать
    в поисковых эндпоинтах ДО построения запроса, чтобы smart_*-матчер знал, можно
    ли использовать триграммы."""
    global _pg_trgm_available
    if _pg_trgm_available is None:
        try:
            r = await db.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'"))
            _pg_trgm_available = r.first() is not None
        except Exception:
            _pg_trgm_available = False
    return _pg_trgm_available


def set_pg_trgm_available(value: bool) -> None:
    """Явно выставить флаг (для тестов/скриптов без ensure-проверки)."""
    global _pg_trgm_available
    _pg_trgm_available = value


# fold_yo (Ё→Е) живёт в similarity.py — один фолд на дедуп и на поиск. Здесь он
# нужен потому, что триграммам разница в Ё не по силам: «демин» vs «дёмин» дают
# word_similarity ≈0.5 при пороге 0.6. Поэтому свёрнутая форма КЛАДЁТСЯ в
# search_name, а не вычисляется на лету — иначе GIN-индекс перестал бы работать.


def build_search_name(
    name: Optional[str],
    position: Optional[str] = None,
    company: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> str:
    """Денормализованный поисковый блоб: ФИО в двух алфавитах + должность/компания/теги."""
    parts = set()
    if name:
        parts |= generate_name_variants(name)
    for f in (position, company):
        if f and str(f).strip():
            parts.add(str(f).strip().lower())
    # tags может прийти JSON-строкой (напр. из raw-SQL бэкфилла) — распарсим.
    if isinstance(tags, str):
        import json as _json
        try:
            tags = _json.loads(tags)
        except Exception:
            tags = []
    for t in (tags or []):
        if isinstance(t, str) and t.strip():
            parts.add(t.strip().lower())
    # Ё≡Е: держим в блобе ОБЕ формы, чтобы «Демин» находил «Дёмина» по индексу.
    parts |= {fold_yo(p) for p in parts}
    parts.discard("")
    return " ".join(sorted(parts))[:3000]


def _entity_search_name(target: "Entity") -> str:
    return build_search_name(
        getattr(target, "name", None),
        getattr(target, "position", None),
        getattr(target, "company", None),
        getattr(target, "tags", None),
    )


def _on_insert(mapper, connection, target):
    target.search_name = _entity_search_name(target)


def _on_update(mapper, connection, target):
    new_val = _entity_search_name(target)
    if target.search_name != new_val:
        target.search_name = new_val


def register_search_events() -> None:
    """Автосинк entities.search_name на insert/update. Идемпотентно."""
    if not event.contains(Entity, "before_insert", _on_insert):
        event.listen(Entity, "before_insert", _on_insert)
    if not event.contains(Entity, "before_update", _on_update):
        event.listen(Entity, "before_update", _on_update)


def query_tokens(q: str) -> List[str]:
    """Слова запроса (≥2 символов, lowercase)."""
    return [w for w in re.split(r"\s+", (q or "").strip().lower()) if len(w.strip("-_.,")) >= 2]


# Раскладка клавиатуры ЙЦУКЕН(RU) ↔ QWERTY(EN): один и тот же ФИЗИЧЕСКИЙ клавиш.
# «иван», набранное в EN-раскладке, выглядит как «bdfy»; перевернув раскладку —
# снова «иван». Это НЕ транслитерация (та фонетическая: ivan→иван) — тут
# соответствие клавиш. Частая жалоба: искал «иван», забыл переключить язык.
_RU_TO_EN_LAYOUT = {
    "й": "q", "ц": "w", "у": "e", "к": "r", "е": "t", "н": "y", "г": "u",
    "ш": "i", "щ": "o", "з": "p", "х": "[", "ъ": "]",
    "ф": "a", "ы": "s", "в": "d", "а": "f", "п": "g", "р": "h", "о": "j",
    "л": "k", "д": "l", "ж": ";", "э": "'",
    "я": "z", "ч": "x", "с": "c", "м": "v", "и": "b", "т": "n", "ь": "m",
    "б": ",", "ю": ".", "ё": "`",
}
_EN_TO_RU_LAYOUT = {v: k for k, v in _RU_TO_EN_LAYOUT.items()}


def switch_layout(q: str) -> str:
    """Флип раскладки RU↔EN по физическим клавишам. Латиница → трактуем как
    EN-раскладку и переводим в кириллицу («bdfy»→«иван»); кириллица → наоборот.
    Неотображаемые символы остаются как есть. Мусорные результаты (напр. «ivan»→
    «шмфт») просто ничего не находят — безвредны."""
    if not q:
        return ""
    mapping = _RU_TO_EN_LAYOUT if re.search(r"[а-яёА-ЯЁ]", q) else _EN_TO_RU_LAYOUT
    return "".join(mapping.get(ch, ch) for ch in q.lower())


def _search_word_variants(tok: str) -> set:
    """Словоформы слова для поиска: транслит-варианты (_name_word_variants) +
    вариант с перевёрнутой раскладкой и уже ЕГО транслит-варианты
    («bdfy» → «иван» → …). Отдельно от similarity._name_word_variants, чтобы НЕ
    засорять раскладкой дедуп кандидатов."""
    variants = set(_name_word_variants(tok) or {tok})
    sw = switch_layout(tok)
    if sw and sw != tok:
        variants.add(sw)
        variants |= (_name_word_variants(sw) or set())
    # Свёрнутый Ё — зеркало того, что лежит в search_name.
    variants |= {fold_yo(v) for v in variants}
    return variants


def smart_name_filter(q: str) -> Optional[ColumnElement]:
    """SQL-условие: КАЖДОЕ слово запроса (в любом алфавите, с опечатками)
    триграммно присутствует в search_name. Порядок слов не важен (AND по словам,
    OR по вариантам). None — если pg_trgm недоступен или нет значимых токенов."""
    if not _pg_trgm_available:
        return None
    tokens = query_tokens(q)
    if not tokens:
        return None
    per_token = []
    for tok in tokens:
        variants = _search_word_variants(tok)
        # search_name %> v  ==  word_similarity(v, search_name) >= threshold  (использует GIN-триграмму)
        per_token.append(or_(*[Entity.search_name.op("%>")(v) for v in variants]))
    return and_(*per_token)


def smart_name_score(q: str) -> Optional[ColumnElement]:
    """Ранг: сумма лучших пословных word_similarity (точнее совпал — выше).
    None — если pg_trgm недоступен (тогда сортировка остаётся прежней)."""
    if not _pg_trgm_available:
        return None
    tokens = query_tokens(q)
    if not tokens:
        return None
    terms = []
    for tok in tokens:
        variants = _search_word_variants(tok)
        terms.append(func.greatest(*[func.word_similarity(v, Entity.search_name) for v in variants]))
    expr = terms[0]
    for t in terms[1:]:
        expr = expr + t
    return expr


def _translit_ilike_patterns(q: str) -> List[str]:
    """ILIKE-паттерны имени с транслитерацией RU<->EN (fallback, работает без pg_trgm)."""
    q = (q or "").strip()
    terms = {q}
    # Свёрнутый Ё транслитерируем ОТДЕЛЬНО: у «Дёмин» и «Демин» разный транслит
    # («dyomin» vs «demin»), а в базе может лежать любой из двух.
    folded = fold_yo(q)
    if folded != q:
        terms.add(folded)
    for t in list(terms):
        if re.search(r"[а-яёА-ЯЁ]", t):
            terms.add(transliterate_ru_to_en(t))
        if re.search(r"[a-zA-Z]", t):
            terms.add(transliterate_en_to_ru(t))
    sw = switch_layout(q)  # раскладка: «bdfy» → «иван»
    if sw and sw != q.lower():
        terms.add(sw)
    return [f"%{t}%" for t in terms if t]


def name_search_conditions(q: str) -> List:
    """OR-условия поиска кандидата по ИМЕНИ для ЛЮБОГО окна поиска: умный
    pg_trgm-матч (транслит + любой порядок слов + опечатки, если pg_trgm доступен)
    + транслит-ILIKE как fallback. Вызывать ПОСЛЕ ensure_pg_trgm_checked(db).
    Использование: base.where(or_(*name_search_conditions(q), <прочие поля>))."""
    conds: List = []
    snf = smart_name_filter(q)
    if snf is not None:
        conds.append(snf)
    # Ё≡Е для ILIKE: сворачиваем и запрос, И колонку. Колонку — обязательно: в базе
    # лежит «Дёмин», а ищут «Демин», и никакой бэкфилл этого не покроет (search_name
    # тут не участвует). На проде pg_trgm недоступен и работает именно эта ветка,
    # так что жалоба «не находит без Ё» чинится здесь.
    yo_name = func.replace(func.replace(Entity.name, "ё", "е"), "Ё", "Е")
    seen_folded = set()  # «Дёмин» и «Демин» сворачиваются в одно — не дублируем ветку OR
    for t in _translit_ilike_patterns(q):
        conds.append(Entity.name.ilike(t))
        folded = fold_yo(t)
        if re.search(r"[а-яА-Я]", folded) and folded not in seen_folded:  # латиницу сворачивать незачем
            seen_folded.add(folded)
            conds.append(yo_name.ilike(folded))
    return conds


def _phone_digits_sql(col):
    """Портабельно (PG+SQLite) выкидывает из телефона разделители, чтобы
    «9991234567» нашёл «+7 (999) 123-45-67». Только цифры сравниваем по цифрам."""
    expr = col
    for ch in (" ", " ", "-", "(", ")", "+", ".", "/"):
        expr = func.replace(expr, ch, "")
    return expr


def _resume_contact_conditions(like: str) -> List:
    """Контакты из шапки резюме — по каждому списку отдельно (см. вызов)."""
    resume = Entity.extra_data["resume_contacts"]
    return [
        cast(resume["emails"], String).ilike(like),
        cast(resume["phones"], String).ilike(like),
        cast(resume["telegrams"], String).ilike(like),
    ]


def contact_search_conditions(q: str) -> List:
    """OR-условия поиска кандидата по КОНТАКТАМ для ЛЮБОГО окна поиска: почта
    (email + emails[]), телефон (phone + phones[], с нормализацией по цифрам:
    «9991234567» ↔ «+7 (999) 123-45-67»), telegram (telegram_usernames[], «@»
    необязателен). Ставить рядом с именем:
      where(or_(*name_search_conditions(q), *contact_search_conditions(q)))."""
    q = (q or "").strip()
    if not q:
        return []
    like = f"%{q}%"
    conds: List = [
        Entity.email.ilike(like),
        cast(Entity.emails, String).ilike(like),
        Entity.phone.ilike(like),
        cast(Entity.phones, String).ilike(like),
    ]
    # Telegram хранится без «@» и в нижнем регистре — «@» из запроса убираем.
    tg = q.lstrip("@")
    if tg:
        conds.append(cast(Entity.telegram_usernames, String).ilike(f"%{tg}%"))
    # Контакты из ШАПКИ резюме (extra_data.resume_contacts) — почта/телефон/ник,
    # которые рекрутёр в поля карточки не переносил. По КАЖДОМУ списку отдельно,
    # а не по объекту целиком: в тексте объекта есть имена ключей, и запрос «id»
    # или «mail» цеплял бы каждого, у кого эти контакты вообще посчитаны.
    conds.extend(_resume_contact_conditions(like))
    # Телефон по одним цифрам — форматы («+7 (999)…» vs «999…») не совпадают.
    digits = re.sub(r"\D", "", q)
    if len(digits) >= 4:
        conds.append(_phone_digits_sql(Entity.phone).ilike(f"%{digits}%"))
    return conds


def is_nick_query(q: str) -> bool:
    """Запрос-ник telegram: начинается с «@». Для таких ищем СТРОГО по telegram,
    без нечёткого матча имени/должности/тегов/extra_data — иначе ник цепляет кучу
    чужих карточек (жалоба рекрутёров)."""
    return (q or "").strip().startswith("@")


def nick_search_conditions(q: str) -> List:
    """Строгий поиск по telegram-нику: поле telegram_usernames + текст комментариев
    (extra_data.notes), БЕЗ нечёткого матча имени/должности/блоба. Ник уникален, так
    что имя не примешиваем; но ник, вписанный рекрутёром в комментарий, тоже находим."""
    tg = (q or "").strip().lstrip("@").lower()
    if not tg:
        return []
    return [
        cast(Entity.telegram_usernames, String).ilike(f"%{tg}%"),
        cast(Entity.extra_data["notes"], String).ilike(f"%{tg}%"),
        # Ник из ШАПКИ резюме: в поля карточки его часто не переносят (а если
        # переносят — бывает обрезанным), и по «@полный_ник» карточка не находилась.
        cast(Entity.extra_data["resume_contacts"]["telegrams"], String).ilike(f"%{tg}%"),
    ]


def broad_search_conditions(q: str, include_tags: bool = False) -> List:
    """Обычный («не-ник») поиск: имя + контакты + должность/компания + комментарии.

    Собрано в одном месте, потому что раньше три окна поиска (/search, /kanban,
    /ids) повторяли список руками и разъезжались. `include_tags` — только для
    /search: в «Все кандидаты» метки в поиск не входили, и менять это заодно не
    стали.
    """
    q = (q or "").strip()
    if not q:
        return []
    like = f"%{q.lower()}%"
    conds: List = [
        # pg_trgm (транслит + любой порядок слов + опечатки) + транслит-ILIKE + Ё≡Е
        *name_search_conditions(q),
        *contact_search_conditions(q),  # почта/телефон(норм.)/telegram + контакты из резюме
        Entity.position.ilike(like),
        Entity.company.ilike(like),
    ]
    if include_tags:
        conds.append(cast(Entity.tags, String).ilike(like))
    # Текст комментариев (extra_data.notes) — прицельно, не весь extra_data-блоб.
    conds.extend(notes_search_conditions(q))
    return conds


async def apply_text_search(db, query, q: str, include_tags: bool = False):
    """Вешает поиск на запрос. Возвращает (запрос, откатились_ли_с_ника).

    «@ник» ищется СТРОГО (telegram + комментарии + контакты из резюме): нечёткий
    матч по имени тащил на ник кучу чужих карточек. Но если по нику в этой
    выборке НЕТ НИЧЕГО, строгий режим превращался в тупик «кандидатов нет» —
    хотя тот же текст без «@» человека находил (ник в карточке сохранён другим,
    например обрезанным: `shaffer_a` вместо `shaffer_art`, 01.10.2026). Поэтому
    на пустом результате откатываемся к обычному поиску и говорим об этом окну.
    """
    q = (q or "").strip()
    if not q:
        return query, False
    await ensure_pg_trgm_checked(db)  # без superuser pg_trgm может не быть — откат на ILIKE
    if is_nick_query(q):
        strict = query.where(or_(*nick_search_conditions(q)))
        found = (await db.execute(
            select(func.count()).select_from(strict.order_by(None).subquery())
        )).scalar() or 0
        if found:
            return strict, False
        return query.where(or_(*broad_search_conditions(q, include_tags))), True
    return query.where(or_(*broad_search_conditions(q, include_tags))), False


def notes_search_conditions(q: str) -> List:
    """Поиск по тексту КОММЕНТАРИЕВ карточки (extra_data.notes) — прицельно, НЕ по
    всему extra_data-блобу (там участия/анкеты/источники = шум). Рекрутёры пишут в
    комментарии актуальный ник/почту кандидата, и это должно находиться поиском."""
    q = (q or "").strip()
    if not q:
        return []
    return [cast(Entity.extra_data["notes"], String).ilike(f"%{q}%")]


# Регистрируем автосинк при импорте модуля (роуты поиска импортируют его на
# старте — раньше любого insert/update кандидата).
register_search_events()
