"""Чистые функции сборки ClickUp-импорта: ключи, группировка, прохождения.

Один реальный человек в ClickUp-выгрузке лежит в нескольких строках (разные
вакансии/рекрутёры/анкеты). Эти функции группируют строки по человеку (по
сильному ключу: hh-URL / email / телефон / telegram) и собирают из каждой строки
«прохождение». Без I/O и без БД — всё юнит-тестируется (tests/test_clickup_import.py).
"""
import html as _html
import json
import re
from datetime import date
from typing import Optional, Set, List, Dict, Any
from urllib.parse import unquote
from collections import defaultdict

# Telegram как идентификатор: нормализация + денилист источников/ярлыков —
# единый источник правды с дедупом (similarity), чтобы «hh_b2b»/«telegram» и т.п.
# не слепляли разных людей.
from .similarity import normalize_telegram, is_matchable_telegram


def normalize_phone(value: str) -> str:
    """Телефон → последние 10 цифр (сравнимый ключ). Короче 10 → пусто (не ключ)."""
    digits = re.sub(r"\D", "", value or "")
    return digits[-10:] if len(digits) >= 10 else ""


_HH_RE = re.compile(r"(hh\.ru|rabota\.by)/resume/([0-9a-z]+)", re.IGNORECASE)


def normalize_hh_url(value: str) -> Optional[str]:
    """hh/rabota резюме-URL → канон 'host/resume/id' (без query, lowercase)."""
    if not value:
        return None
    m = _HH_RE.search(value)
    if not m:
        return None
    return f"{m.group(1).lower()}/resume/{m.group(2).lower()}"


def clean_recruiter(folder: str) -> str:
    """'Sandbox - Мария' → 'Мария'. Без префикса — как есть."""
    folder = (folder or "").strip()
    if " - " in folder:
        folder = folder.split(" - ", 1)[1].strip()
    return folder


# ── Дистилляция структурных полей карточки (дата рождения / локация) ──
# ВАЖНО: карточка кандидата (KanbanCard) читает extra_data.birth_date → возраст и
# extra_data.location → город. Раньше combine-путь клал только participations и
# карточка выглядела пустой («мало инфы»). Эти чистые экстракторы позволяют
# вытащить те же поля, что и построчный путь (_clickup_postprocess), — единый
# источник правды: csv_import импортирует их отсюда.

_BIRTHDATE_RE = re.compile(r"Дата рождения:\s*(\d{4}-\d{2}-\d{2})T")


def extract_birthdate(description: str, today: Optional[date] = None) -> Optional[str]:
    """Дата рождения как локальная дата (YYYY-MM-DD) из ISO в description.

    cf-колонка «Дата рождения» хранит значение в UTC (может сместить день на ±1),
    а описание задачи держит исходный timezone-aware ISO — берём дату оттуда.
    Мусорные значения (даты форм-сабмита / тестовые) отсекаем по диапазону года.
    """
    if not description:
        return None
    m = _BIRTHDATE_RE.search(description)
    if not m:
        return None
    value = m.group(1)
    year = int(value[:4])
    today = today or date.today()
    if year < 1940 or year > today.year - 14:
        return None
    return value


_CF_DATE_RE = re.compile(r"^\s*(\d{4}-\d{2}-\d{2})")


def birthdate_from_cf(raw: str, today: Optional[date] = None) -> Optional[str]:
    """Фолбэк: дата рождения из cf-колонки «Дата рождения» (формат '2002-08-21 …').

    Колонка в UTC (может сместить день на ±1) — поэтому предпочтение у
    extract_birthdate из описания. Но когда описания нет, дата из cf лучше, чем
    пусто: для ВОЗРАСТА расхождение в один день практически не важно.
    """
    if not raw:
        return None
    m = _CF_DATE_RE.match(raw)
    if not m:
        return None
    year = int(m.group(1)[:4])
    today = today or date.today()
    if year < 1940 or year > today.year - 14:
        return None
    return m.group(1)


def extract_location(raw: str) -> Optional[str]:
    """Читаемый адрес из geo-JSON ClickUp (custom field «Местонахождение»)."""
    if not raw:
        return None
    try:
        data = json.loads(raw)
        addr = data.get("formatted_address")
        return addr or None
    except (json.JSONDecodeError, AttributeError, TypeError):
        return None


def distill_person_fields(group: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Структурные поля карточки из строк человека (первое непустое по группе).

    Кладёт те же ключи, что читает карточка: `birth_date` (→ возраст) и `location`
    (→ город). Строки одного человека личные поля обычно повторяют, но не всегда
    заполнены во всех — поэтому берём первое непустое.
    """
    out: Dict[str, Any] = {}
    for r in group:
        if "birth_date" not in out:
            # Приоритет — timezone-aware ISO из описания; иначе cf-колонка (UTC).
            bd = extract_birthdate(r.get("description", "") or "") or birthdate_from_cf(
                r.get("cf:Дата рождения", "") or ""
            )
            if bd:
                out["birth_date"] = bd
        if "location" not in out:
            loc = extract_location(r.get("cf:Местонахождение", "") or "")
            if loc:
                out["location"] = loc
        if "birth_date" in out and "location" in out:
            break
    return out


def row_strong_keys(
    email: str, phone: str, hh: Optional[str], telegram: Optional[str] = None
) -> Set[str]:
    """Сильные ключи строки (может быть несколько). Пусто → только ФИО (не склеиваем).

    telegram — опциональный: добавляем `tg:<handle>` ТОЛЬКО для годного личного
    хэндла (не из денилиста источников). Частотный гвард (один хэндл на много
    РАЗНЫХ людей = мусор) применяет вызывающий — здесь его нет, т.к. он требует
    статистики по всей выгрузке. Ловит людей без телефона/почты/hh (только tg)."""
    keys: Set[str] = set()
    e = (email or "").strip().lower()
    if e:
        keys.add(f"email:{e}")
    p = normalize_phone(phone)
    if p:
        keys.add(f"phone:{p}")
    h = normalize_hh_url(hh or "")
    if h:
        keys.add(f"hh:{h}")
    if telegram:
        tg = normalize_telegram(telegram)
        if tg and is_matchable_telegram(tg):
            keys.add(f"tg:{tg}")
    return keys


def group_rows_by_person(rows: List[Dict[str, Any]], key_fn) -> List[List[Dict[str, Any]]]:
    """Union-find по сильным ключам. Строки без ключей → каждая своей группой."""
    parent: Dict[str, str] = {}

    def find(k: str) -> str:
        parent.setdefault(k, k)
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    row_keys = [key_fn(r) for r in rows]
    for keys in row_keys:
        kl = list(keys)
        for k in kl[1:]:
            union(kl[0], k)

    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    singleton = 0
    for row, keys in zip(rows, row_keys):
        if keys:
            gid = find(next(iter(sorted(keys))))
        else:
            gid = f"__single_{singleton}"
            singleton += 1
        groups[gid].append(row)
    return list(groups.values())


# Комментарий ClickUp в CSV-колонке `comments`: записи вида
# `[YYYY-MM-DD HH:MM:SS · Автор] текст`, разделённые строкой `---`.
_COMMENT_MARK_RE = re.compile(r"\[(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) · ([^\]]+)\]")
_URL_RE = re.compile(r"https?://[^\s<]+")


def _linkify_html(text: str) -> str:
    """Текст комментария → безопасный HTML: URL'ы — кликабельными ссылками.

    Родные комментарии в таймлайне и так хранятся как HTML (rich-редактор,
    рендер через sanitizeHtml, где `<a href>` разрешён). Поэтому запись
    собеседования (ссылка на .webm и т.п.) в импортированном комментарии тоже
    делаем ссылкой — с читаемой подписью (имя файла), а не голым URL. Весь
    текст экранируется: на выходе только наши `<a>` вокруг http(s)-ссылок.
    """
    out: List[str] = []
    last = 0
    for m in _URL_RE.finditer(text):
        out.append(_html.escape(text[last:m.start()]))
        url = m.group(0)
        label = url
        try:
            fname = unquote(url.split("?")[0]).rstrip("/").split("/")[-1]
            if fname:
                label = fname
        except Exception:  # noqa: BLE001 — подпись не критична, падать нельзя
            pass
        out.append(f'<a href="{_html.escape(url, quote=True)}">{_html.escape(label)}</a>')
        last = m.end()
    out.append(_html.escape(text[last:]))
    return "".join(out)


def parse_comments(raw: str, task_id: str = "") -> List[Dict[str, Any]]:
    """Колонка `comments` → список заметок для родного таймлайна карточки.

    Каждая запись → плашка комментария: {id, text, date, author_name}. Дата в
    ISO (таймлайн сортирует через `new Date`). id детерминированный
    (task_id + номер записи) — переимпорт не двоит существующие плашки.
    Текст без разметки автор/дата сохраняем как один безымянный комментарий.
    """
    raw = (raw or "").strip()
    if not raw:
        return []
    marks = list(_COMMENT_MARK_RE.finditer(raw))
    if not marks:
        return [{"id": f"clickup:{task_id}:0", "text": _linkify_html(raw)}]
    notes: List[Dict[str, Any]] = []
    for i, m in enumerate(marks):
        start = m.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(raw)
        body = raw[start:end].strip()
        body = re.sub(r"\s*-{3,}\s*$", "", body).strip()  # хвостовой разделитель '---'
        if not body:
            continue
        notes.append({
            "id": f"clickup:{task_id}:{i}",
            "text": _linkify_html(body),
            "date": f"{m.group(1)}T{m.group(2)}",
            "author_name": m.group(3).strip(),
        })
    return notes


def _merge_notes(target: List[Dict[str, Any]], incoming: List[Dict[str, Any]]) -> None:
    """Upsert заметок по id (стабильному на переимпорте): тот же id → обновляем
    содержимое (текст/дата/автор) на актуальное из файла, новый id → добавляем.

    Так повторная заливка свежего экспорта приводит комментарии к актуальному
    состоянию (в т.ч. отредактированные), не задваивая и ничего не теряя.
    Заметки, которых больше нет в файле (удалённые в ClickUp), не трогаем."""
    pos_by_id = {n.get("id"): i for i, n in enumerate(target)}
    for n in incoming or []:
        nid = n.get("id")
        if nid in pos_by_id:
            target[pos_by_id[nid]] = n   # актуальная версия побеждает
        else:
            pos_by_id[nid] = len(target)
            target.append(n)


def build_participation(row: Dict[str, Any], cf_headers: List[str]) -> Dict[str, Any]:
    """Одна строка ClickUp → одно прохождение (вакансия/рекрутёр/статус/анкета)."""
    anketa: List[Dict[str, str]] = []
    for h in cf_headers:
        val = (row.get(h) or "").strip()
        if not val:
            continue
        q = h[3:].strip() if h.lower().startswith("cf:") else h
        anketa.append({"question": q, "answer": val})
    recruiter = clean_recruiter(row.get("funnel_folder", "")) or (row.get("assignees", "") or "").strip()
    task_id = (row.get("task_id", "") or "").strip()
    return {
        "vacancy_title": (row.get("funnel_list", "") or "").strip(),
        "recruiter": recruiter,
        "status": (row.get("status", "") or "").strip(),
        "anketa": anketa,
        # Комментарии рекрутёра/HR (заметки собеседований, ссылки на записи) —
        # родными плашками в таймлайне прохождения (см. model.ts participations).
        "notes": parse_comments(row.get("comments", "") or "", task_id),
        "date": (row.get("date_created", "") or "").strip() or None,
        "task_id": task_id or None,
        "url": (row.get("url", "") or "").strip() or None,
    }


def _dedup_twin_participations(parts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Истинные близнецы → одно прохождение, анкеты объединены.

    Идентичность прохождения = (вакансия + рекрутёр + статус). Статус в ключе
    ВАЖЕН: разные этапы одной воронки (напр. «выполняет ТЗ» и «вышел на ИС») —
    это РАЗНЫЕ прохождения и должны показываться отдельными анкетами. Схлопываем
    лишь дословные дубли одной задачи (та же воронка+рекрутёр+статус)."""
    by_key: Dict[tuple, Dict[str, Any]] = {}
    for p in parts:
        key = (
            p["vacancy_title"].lower(),
            p["recruiter"].lower(),
            (p.get("status") or "").strip().lower(),
        )
        if key not in by_key:
            by_key[key] = {**p, "anketa": list(p["anketa"]), "notes": list(p.get("notes") or [])}
            continue
        existing = by_key[key]
        seen_q = {a["question"] for a in existing["anketa"]}
        for a in p["anketa"]:
            if a["question"] not in seen_q:
                existing["anketa"].append(a)
                seen_q.add(a["question"])
        # Строки-близнецы (зеркала в разных списках) несут свои комментарии —
        # сливаем их заметки в одно прохождение (дедуп по id).
        _merge_notes(existing["notes"], p.get("notes") or [])
    return list(by_key.values())


def _longest(values: List[str]) -> str:
    vals = [v for v in values if v]
    return max(vals, key=len) if vals else ""


def assemble_person(group: List[Dict[str, Any]], cf_headers: List[str]) -> Dict[str, Any]:
    """Группа строк одного человека → payload одной архивной карточки с участиями."""
    names = [(r.get("name", "") or "").strip() for r in group]
    emails = {(r.get("email", "") or "").strip().lower() for r in group if (r.get("email") or "").strip()}
    phones = {(r.get("phone", "") or "").strip() for r in group if (r.get("phone") or "").strip()}
    tgs = {(r.get("telegram", "") or "").strip().lstrip("@").lower()
           for r in group if (r.get("telegram") or "").strip()}
    participations = _dedup_twin_participations([build_participation(r, cf_headers) for r in group])
    primary = participations[0] if participations else {}
    # ВСЕ ClickUp task_id человека — надёжный якорь идемпотентности при переимпорте.
    # Часть людей без телефона/почты (только hh-ссылка или только ФИО) — их иначе
    # не узнать при повторном импорте, и они дублировались бы каждый раз.
    task_ids = sorted(
        {(r.get("task_id") or "").strip() for r in group if (r.get("task_id") or "").strip()}
    )
    extra_data: Dict[str, Any] = {
        "participations": participations,
        "import_source": "clickup",
        "clickup_task_ids": task_ids,
    }
    # Структурные поля карточки (дата рождения → возраст, локация → город) —
    # иначе шапка архивной карточки пустая, вся инфа сидит только в анкетах.
    extra_data.update(distill_person_fields(group))
    return {
        "name": _longest(names),
        "email": (sorted(emails)[0] if emails else None),
        "emails": sorted(emails),
        "phone": (sorted(phones)[0] if phones else None),
        "phones": sorted(phones),
        "telegram_usernames": sorted(tgs),
        "position": primary.get("vacancy_title") or None,
        "extra_data": extra_data,
    }


_HH_COL_HINTS = ("резюме hh", "ссылку на свое резюме", "резюме из hh")


def extract_hh_from_row(row: Dict[str, Any]) -> Optional[str]:
    """Ищет hh/rabota резюме-URL в известных cf:-колонках и в description."""
    for col, val in row.items():
        cl = col.lower()
        if any(h in cl for h in _HH_COL_HINTS) or cl == "cf:резюме":
            got = normalize_hh_url(val or "")
            if got:
                return got
    return normalize_hh_url(row.get("description", "") or "")


_EMAIL_RE = re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", re.IGNORECASE)
_EMAIL_COL_HINTS = ("почт", "email", "e-mail", "mail")


def extract_email_from_row(row: Dict[str, Any]) -> Optional[str]:
    """Почта из cf:-колонок с намёком на почту (произвольные имена), иначе из description."""
    for col, val in row.items():
        if any(h in col.lower() for h in _EMAIL_COL_HINTS) and isinstance(val, str):
            m = _EMAIL_RE.search(val)
            if m:
                return m.group(0).lower()
    m = _EMAIL_RE.search(row.get("description", "") or "")
    return m.group(0).lower() if m else None


_TG_COL_HINTS = ("telegram", "телеграм", "телеграмм", "tg")


def extract_telegram_from_row(row: Dict[str, Any]) -> Optional[str]:
    """Telegram из cf:-колонки с намёком на телеграм — независимо от того,
    смапил ли пользователь эту колонку на поле «telegram». Нужно для группировки
    по telegram у людей без телефона/почты/hh (иначе зависели бы от маппинга)."""
    for col, val in row.items():
        if any(h in col.lower() for h in _TG_COL_HINTS) and isinstance(val, str) and val.strip():
            return val.strip()
    return None


def merge_participations(
    existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """До-кладываем участия. Идентичность прохождения = (воронка + рекрутёр +
    статус): разные этапы одной воронки — разные прохождения (отдельные анкеты).
    task_id в ключ НЕ идёт, иначе один и тот же проход задваивался бы при
    переимпорте; статус же стабилен между выгрузками, поэтому идемпотентность
    сохраняется."""
    def sig(p: Dict[str, Any]):
        return (
            (p.get("vacancy_title") or "").strip().lower(),
            (p.get("recruiter") or "").strip().lower(),
            (p.get("status") or "").strip().lower(),
        )

    by_sig: Dict[tuple, Dict[str, Any]] = {sig(p): p for p in existing}
    out = list(existing)
    for p in incoming:
        s = sig(p)
        if s not in by_sig:
            out.append(p)
            by_sig[s] = p
        else:
            # Прохождение уже есть — но у него могли появиться новые комментарии
            # (напр. старый импорт был без колонки comments). До-кладываем заметки,
            # дедуп по id → повторный импорт идемпотентен.
            tgt = by_sig[s]
            tgt.setdefault("notes", [])
            _merge_notes(tgt["notes"], p.get("notes") or [])
    return out
