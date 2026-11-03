"""Дозаливка изменений из Энцеладуса в базу productHR (30.10.2026, маркер HR_DELTA).

Базу productHR залили дампом Энцеладуса от 27.10 11:06 UTC, а рекрутёры ещё три
дня работали в Энцеладусе: новые кандидаты, переводы, комментарии, файлы,
анкеты. Полный дамп заново залить нельзя — в productHR за эти дни своя жизнь
(приглашения, документы, пароли в «Управлении»), pg_restore --clean её сотрёт.
Скачать бэкап Энцеладуса может только админ команды Saturn.

Поэтому разница собирается на компьютере из того, что можно прочитать
(просмотр таблиц Saturn и API Энцеладуса), и приходит сюда пакетом шагов:

    {"version": 1, "steps": [
        {"op": "upsert", "table": "vacancy_applications", "rows": [{...}, ...]},
        {"op": "delete", "table": "entities", "keys": [{"id": 9308}, ...]},
    ]}

update — то же, но только для существующих строк (пропавшие — в отчёт).
insert (03.11.2026) — только новые строки, номер выдаёт сама база. С 30.10 в
productHR работают рекрутёры, и номера новых кандидатов, заявок, записей
истории разошлись с Энцеладусом: 9595 там и 9595 здесь — разные люди.
Поэтому строка, пришедшая из Энцеладуса, несёт вместо номера
`"$new": "entities:9595"` (номер в Энцеладусе), база даёт ей свой, а все
ссылки на неё в следующих строках записаны как `{"$ref": "entities:9595"}`
(или `{"$ref": …, "$fmt": "prefix{}"}` — строкой) — и подменяются здесь, в том
числе внутри JSON. `"$match"` у строки — найти уже перенесённую по метке в
JSON-колонке (`extra_data.enceladus_id`) и не вставлять второй раз.
`"$expect"` у строки update/upsert/delete — значения колонок, которые строка
должна иметь СЕЙЧАС (как на момент сборки пакета). Не совпало — значит, её
успели поменять в productHR, строку не трогаем, в отчёт — conflict.
append_notes — дописать в `entities.extra_data.notes` комментарии, которых там
ещё нет (по id записи), не трогая остальное в карточке.
Ответ на анкету, вставленный пакетом, сам уведомляет рекрутёров (04.11.2026):
кандидат заполнил анкету по старой ссылке Энцеладуса — ответ лёг там, приехал
сюда дозаливкой, и «Ответ на анкету» не получил никто (Губич, 31.10). Правило
то же, что у `notify_form_submitted`: отправителю ссылки и текущему рекрутёру
кандидата, по одному на человека. notify_form_answers (`rows`: `{"token"}` или
`{"submission_id"}`) — то же для ответов, перенесённых раньше; уведомление,
которое уже есть, второй раз не создаётся.
upsert — строка вставляется с ТЕМ ЖЕ первичным ключом, а если такая есть —
перезаписываются только те колонки, что пришли в строке (остальные не
трогаются). Значения — как их отдаёт просмотр таблиц (строки): тип каждой
колонки приводит сама база через json_populate_record. Колонки json/jsonb,
пришедшие строкой, разбираются здесь — иначе база сохранила бы JSON-строку.
Байты файла — отдельным полем `file_data_b64`.

Всё — одной транзакцией: упал любой шаг — не применилось ничего. dry_run
выполняет всё и откатывает, отчёт тот же. В конце счётчики id подтягиваются к
максимуму, иначе следующая вставка споткнётся о перенесённые номера.
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Any, Iterable

logger = logging.getLogger("hr-analyzer.hr-delta")

JSON_TYPES = {"json", "jsonb"}


def _table_meta(cur, table: str) -> tuple[dict[str, str], list[str]]:
    cur.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s",
        (table,),
    )
    cols = {name: dtype for name, dtype in cur.fetchall()}
    if not cols:
        raise ValueError(f"нет таблицы {table}")
    cur.execute(
        "SELECT a.attname FROM pg_index i "
        "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
        "WHERE i.indrelid = %s::regclass AND i.indisprimary ORDER BY a.attnum",
        (f"public.{table}",),
    )
    pk = [r[0] for r in cur.fetchall()]
    if not pk:
        raise ValueError(f"у таблицы {table} нет первичного ключа")
    return cols, pk


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _resolve(value, idmap: dict):
    """{"$ref": "table:old"} → новый номер (с "$fmt" — строкой), в том числе внутри JSON."""
    if isinstance(value, dict):
        if "$ref" in value and set(value) <= {"$ref", "$fmt"}:
            ref = value["$ref"]
            if ref not in idmap:
                raise ValueError(f"ссылка на {ref}, которой нет в пакете")
            new = idmap[ref]
            return value["$fmt"].format(new) if "$fmt" in value else new
        return {k: _resolve(v, idmap) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v, idmap) for v in value]
    return value


def _expect_ok(cur, table: str, row_pk: dict, expect: dict, meta) -> bool | None:
    """True — строка есть и колонки совпали; False — изменена; None — строки нет."""
    cols, pk = meta
    where = " AND ".join(f"x.{_q(k)} = r.{_q(k)}" for k in pk)
    checks = []
    for c in expect:
        if c not in cols:
            raise ValueError(f"{table}: в $expect колонка {c}, которой нет")
        if cols[c] in JSON_TYPES:
            checks.append(f"x.{_q(c)}::jsonb IS NOT DISTINCT FROM e.{_q(c)}::jsonb")
        else:
            checks.append(f"x.{_q(c)} IS NOT DISTINCT FROM e.{_q(c)}")
    rec = f"json_populate_record(NULL::public.{_q(table)}, %s::json)"
    cur.execute(
        f"SELECT {' AND '.join(checks) or 'TRUE'} FROM public.{_q(table)} AS x, {rec} AS r, {rec} AS e "
        f"WHERE {where} FOR UPDATE OF x",
        (json.dumps(row_pk, ensure_ascii=False), json.dumps(_normalize(expect, cols), ensure_ascii=False)),
    )
    got = cur.fetchone()
    return None if got is None else bool(got[0])


def _normalize(row: dict, cols: dict[str, str]) -> dict:
    out = {}
    for k, v in row.items():
        if k not in cols:
            continue
        if cols[k] in JSON_TYPES and isinstance(v, str):
            try:
                v = json.loads(v)
            except ValueError:
                pass
        out[k] = v
    return out


def _write_file(cur, table: str, pk: list[str], row: dict, file_b64) -> None:
    if file_b64 is None:
        return
    import psycopg2

    where = " AND ".join(f"{_q(k)} = %s" for k in pk)
    cur.execute(
        f"UPDATE public.{_q(table)} SET file_data = %s WHERE {where}",
        [psycopg2.Binary(base64.b64decode(file_b64))] + [row[k] for k in pk],
    )


def _upsert(cur, table: str, rows: Iterable[dict], meta, insert: bool = True, idmap: dict | None = None) -> dict:
    """insert=False — шаг "update": только существующие строки, пропавшие — в отчёт."""
    cols, pk = meta
    idmap = {} if idmap is None else idmap
    stats = {"inserted": 0, "updated": 0, "absent": 0, "conflict": 0}
    for raw in rows:
        raw = _resolve(dict(raw), idmap)
        file_b64 = raw.pop("file_data_b64", None)
        expect = raw.pop("$expect", None)
        row = _normalize(raw, cols)
        missing_pk = [k for k in pk if row.get(k) in (None, "")]
        if missing_pk:
            raise ValueError(f"{table}: в строке нет ключа {missing_pk}")
        if expect is not None:
            ok = _expect_ok(cur, table, {k: row[k] for k in pk}, expect, meta)
            if not ok:
                stats["conflict"] += 1
                continue
        names = list(row)
        payload = json.dumps(row, ensure_ascii=False)
        rec = f"json_populate_record(NULL::public.{_q(table)}, %s::json) AS r"
        match = " AND ".join(f"x.{_q(k)} = r.{_q(k)}" for k in pk)
        updates = [c for c in names if c not in pk]
        # Сначала UPDATE: NOT NULL Postgres проверяет у вставляемой строки ДО
        # ON CONFLICT, поэтому частичная строка (только изменённые колонки)
        # через INSERT … ON CONFLICT не прошла бы.
        if updates:
            cur.execute(
                f"UPDATE public.{_q(table)} AS x SET "
                + ", ".join(f"{_q(c)} = r.{_q(c)}" for c in updates)
                + f" FROM {rec} WHERE {match}",
                (payload,),
            )
        else:
            cur.execute(f"SELECT 1 FROM public.{_q(table)} AS x, {rec} WHERE {match}", (payload,))
        if cur.rowcount:
            stats["updated"] += 1
        elif not insert:
            stats["absent"] += 1
            continue
        else:
            col_list = ", ".join(_q(c) for c in names)
            cur.execute(
                f"INSERT INTO public.{_q(table)} ({col_list}) SELECT {col_list} FROM {rec}",
                (payload,),
            )
            stats["inserted"] += 1
        _write_file(cur, table, pk, row, file_b64)
    return stats


def _insert(cur, table: str, rows: Iterable[dict], meta, idmap: dict) -> dict:
    """Только новые строки; "$new" — номер выдаёт база, старый → новый в idmap."""
    cols, pk = meta
    stats = {"inserted": 0, "matched": 0}
    for raw in rows:
        raw = dict(raw)
        new_key = raw.pop("$new", None)
        match = raw.pop("$match", None)
        raw = _resolve(raw, idmap)
        file_b64 = raw.pop("file_data_b64", None)
        row = _normalize(raw, cols)
        if new_key is not None:
            if pk != ["id"]:
                raise ValueError(f"{table}: $new только для таблиц с ключом id")
            if new_key in idmap:
                raise ValueError(f"{table}: {new_key} в пакете дважды")
            row.pop("id", None)
        if match is not None:
            cur.execute(
                f"SELECT id FROM public.{_q(table)} WHERE {_q(match['column'])}::jsonb ->> %s = %s ORDER BY id LIMIT 1",
                (match["key"], str(match["value"])),
            )
            found = cur.fetchone()
            if found:
                if new_key is not None:
                    idmap[new_key] = found[0]
                stats["matched"] += 1
                continue
        names = list(row)
        col_list = ", ".join(_q(c) for c in names)
        returning = " RETURNING id" if new_key is not None else ""
        cur.execute(
            f"INSERT INTO public.{_q(table)} ({col_list}) SELECT {col_list} "
            f"FROM json_populate_record(NULL::public.{_q(table)}, %s::json){returning}",
            (json.dumps(row, ensure_ascii=False),),
        )
        if new_key is not None:
            row["id"] = idmap[new_key] = cur.fetchone()[0]
        stats["inserted"] += 1
        _write_file(cur, table, pk, row, file_b64)
    return stats


def _append_notes(cur, rows: Iterable[dict], idmap: dict) -> dict:
    """Дописать в extra_data.notes карточки комментарии, которых там нет (по id)."""
    stats = {"appended": 0, "already": 0, "absent": 0}
    for raw in rows:
        raw = _resolve(dict(raw), idmap)
        cur.execute("SELECT extra_data FROM public.entities WHERE id = %s FOR UPDATE", (raw["id"],))
        got = cur.fetchone()
        if got is None:
            stats["absent"] += 1
            continue
        extra = got[0] if isinstance(got[0], dict) else json.loads(got[0] or "{}")
        notes = list(extra.get("notes") or [])
        have = {n.get("id") for n in notes if isinstance(n, dict)}
        add = [n for n in raw["notes"] if n.get("id") not in have]
        stats["already"] += len(raw["notes"]) - len(add)
        if not add:
            continue
        notes = sorted(notes + add, key=lambda n: str(n.get("date") or ""))
        extra["notes"] = notes
        cur.execute(
            "UPDATE public.entities SET extra_data = %s::json WHERE id = %s",
            (json.dumps(extra, ensure_ascii=False), raw["id"]),
        )
        stats["appended"] += len(add)
    return stats


def _form_answer_recipients(cur, dispatch_by, entity_id, entity_created_by) -> list[int]:
    """То же правило, что `hr_notifications.form_answer_recipients` (там — async ORM):
    отправитель ссылки, затем текущие рекрутёры по правилу метки «HR: …»
    (`hr_tags.compute_hr_tags`: автор живой заявки, без автора — владелец воронки,
    плюс со-рекрутёры; порядок — по (hr_id, vacancy_id)); нет живых заявок — тот,
    за кем карточка. Удалённых пользователей нет в выборке — им некуда писать."""
    recipients: list[int] = []

    def add(user_id) -> None:
        if user_id and user_id not in recipients:
            recipients.append(user_id)

    if dispatch_by:
        cur.execute("SELECT id FROM public.users WHERE id = %s", (dispatch_by,))
        if cur.fetchone():
            add(dispatch_by)
    cur.execute(
        "SELECT hr_id FROM ("
        " SELECT COALESCE(a.created_by, v.created_by) AS hr_id, v.id AS vid"
        " FROM public.vacancy_applications a JOIN public.vacancies v ON v.id = a.vacancy_id"
        " WHERE a.entity_id = %(e)s AND a.stage::text NOT IN ('rejected', 'withdrawn')"
        " AND v.deleted_at IS NULL"
        " UNION"
        " SELECT c.user_id, v.id FROM public.application_co_recruiters c"
        " JOIN public.vacancy_applications a ON a.id = c.application_id"
        " JOIN public.vacancies v ON v.id = a.vacancy_id"
        " WHERE a.entity_id = %(e)s AND a.stage::text NOT IN ('rejected', 'withdrawn')"
        " AND v.deleted_at IS NULL"
        ") t JOIN public.users u ON u.id = t.hr_id ORDER BY hr_id, vid",
        {"e": entity_id},
    )
    current = [r[0] for r in cur.fetchall()]
    for hr_id in current:
        add(hr_id)
    if not current and entity_created_by:
        cur.execute("SELECT id FROM public.users WHERE id = %s", (entity_created_by,))
        if cur.fetchone():
            add(entity_created_by)
    return recipients


def _notify_form_answers(cur, submission_ids: Iterable[int]) -> dict:
    """Уведомление «Ответ на анкету» по ответам, пришедшим пакетом (см. docstring
    модуля). Текст и ссылка — как у `notify_form_submitted`. Если такое же
    уведомление этому человеку уже создано не раньше ответа — не дублируем
    (повторный пакет, notify_form_answers по уже уведомлённому ответу)."""
    stats = {"answers": 0, "created": 0, "already": 0, "nobody": 0, "absent": 0}
    for sid in submission_ids:
        cur.execute(
            "SELECT COALESCE(d.entity_id, s.entity_id), d.id, d.created_by, s.submitted_at,"
            " e.name, e.created_by, t.title"
            " FROM public.form_submissions s"
            " LEFT JOIN public.form_dispatches d ON d.id = s.dispatch_id"
            " LEFT JOIN public.entities e ON e.id = COALESCE(d.entity_id, s.entity_id)"
            " LEFT JOIN public.form_templates t ON t.id = s.form_id"
            " WHERE s.id = %s",
            (sid,),
        )
        got = cur.fetchone()
        if got is None or got[0] is None:
            stats["absent"] += 1
            continue
        entity_id, dispatch_id, dispatch_by, submitted_at, name, entity_by, form_title = got
        stats["answers"] += 1
        recipients = _form_answer_recipients(cur, dispatch_by, entity_id, entity_by)
        if not recipients:
            stats["nobody"] += 1
            logger.warning("FORM_ANSWER_NOTIFY via=hr_delta submission=%s — некому", sid)
            continue
        message = f"{name or 'Кандидат'} заполнил(а) анкету «{form_title}»"
        link = f"/all-candidates?entity={entity_id}&tab=anketa"
        sent = []
        for user_id in recipients:
            cur.execute(
                "SELECT 1 FROM public.notifications WHERE user_id = %s AND type = 'form_submitted'"
                " AND link = %s AND message = %s AND created_at >= COALESCE(%s, created_at)",
                (user_id, link, message, submitted_at),
            )
            if cur.fetchone():
                stats["already"] += 1
                continue
            cur.execute(
                "INSERT INTO public.notifications (user_id, type, title, message, link, is_read, created_at)"
                " VALUES (%s, 'form_submitted', 'Ответ на анкету', %s, %s, false, now())",
                (user_id, message, link),
            )
            stats["created"] += 1
            sent.append(user_id)
        logger.warning(
            "FORM_ANSWER_NOTIFY via=hr_delta submission=%s dispatch=%s entity=%s to=%s",
            sid, dispatch_id, entity_id, sent,
        )
    return stats


def _submission_ids(cur, rows: Iterable[dict], idmap: dict) -> list[int]:
    """notify_form_answers: строки `{"submission_id"}` (можно $ref) или `{"token"}` ссылки."""
    ids = []
    for raw in rows:
        raw = _resolve(dict(raw), idmap)
        if raw.get("submission_id"):
            ids.append(int(raw["submission_id"]))
            continue
        cur.execute(
            "SELECT COALESCE(d.submission_id, (SELECT max(s.id) FROM public.form_submissions s"
            " WHERE s.dispatch_id = d.id)) FROM public.form_dispatches d WHERE d.token = %s",
            (raw["token"],),
        )
        got = cur.fetchone()
        ids.append(got[0] if got and got[0] else -1)
    return ids


def _delete(cur, table: str, keys: Iterable[dict], meta, idmap: dict | None = None) -> dict:
    cols, pk = meta
    stats = {"deleted": 0, "absent": 0, "conflict": 0}
    for key in keys:
        key = _resolve(dict(key), idmap or {})
        expect = key.pop("$expect", None)
        if set(key) != set(pk):
            raise ValueError(f"{table}: ключ удаления {sorted(key)} не совпадает с {pk}")
        if expect is not None:
            ok = _expect_ok(cur, table, key, expect, meta)
            if ok is None:
                stats["absent"] += 1
                continue
            if not ok:
                stats["conflict"] += 1
                continue
        where = " AND ".join(f"{_q(k)} = %s" for k in pk)
        cur.execute(f"DELETE FROM public.{_q(table)} WHERE {where}", [key[k] for k in pk])
        stats["deleted" if cur.rowcount else "absent"] += 1
    return stats


def _sync_sequences(cur, tables: Iterable[str], dry_run: bool) -> dict:
    """setval не откатывается вместе с транзакцией — при dry_run только отчёт."""
    moved = {}
    for table in sorted(set(tables)):
        cur.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s AND column_name = 'id'",
            (table,),
        )
        if not cur.fetchone():
            continue
        cur.execute("SELECT pg_get_serial_sequence(%s, 'id')", (f"public.{table}",))
        row = cur.fetchone()
        if not row or not row[0]:
            continue
        seq = row[0]
        cur.execute(f"SELECT COALESCE(MAX(id), 0) FROM public.{_q(table)}")
        max_id = cur.fetchone()[0]
        cur.execute(f"SELECT last_value FROM {seq}")
        last = cur.fetchone()[0]
        if max_id > last:
            if not dry_run:
                cur.execute("SELECT setval(%s, %s)", (seq, max_id))
            moved[table] = [last, max_id]
    return moved


def apply_delta(dsn: str, bundle: dict, dry_run: bool) -> dict[str, Any]:
    """Применить пакет одной транзакцией. Возвращает отчёт по шагам."""
    import psycopg2

    if bundle.get("version") != 1 or not isinstance(bundle.get("steps"), list):
        raise ValueError("пакет не того формата")
    report: dict[str, Any] = {"dry_run": dry_run, "steps": []}
    conn = psycopg2.connect(dsn)
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout = '15s'")
            metas: dict[str, tuple] = {}
            touched: list[str] = []
            idmap: dict[str, int] = {}
            for i, step in enumerate(bundle["steps"]):
                table, op = step["table"], step["op"]
                if table not in metas:
                    metas[table] = _table_meta(cur, table)
                if op == "upsert":
                    stats = _upsert(cur, table, step["rows"], metas[table], idmap=idmap)
                    touched.append(table)
                elif op == "update":
                    stats = _upsert(cur, table, step["rows"], metas[table], insert=False, idmap=idmap)
                    touched.append(table)
                elif op == "insert":
                    stats = _insert(cur, table, step["rows"], metas[table], idmap)
                    touched.append(table)
                elif op == "append_notes":
                    stats = _append_notes(cur, step["rows"], idmap)
                elif op == "notify_form_answers":
                    stats = _notify_form_answers(cur, _submission_ids(cur, step["rows"], idmap))
                elif op == "delete":
                    stats = _delete(cur, table, step["keys"], metas[table], idmap)
                else:
                    raise ValueError(f"шаг {i}: неизвестная операция {op}")
                report["steps"].append({"op": op, "table": table, **stats})
                logger.warning("HR_DELTA %s %s %s%s", op, table, stats, " (dry_run)" if dry_run else "")
            # Ответы на анкеты, вставленные этим пакетом, — уведомить, когда на
            # месте и ссылки, и заявки (от них зависит «текущий рекрутёр»).
            new_answers = [v for k, v in idmap.items() if k.startswith("form_submissions:")]
            if new_answers:
                report["form_answer_notifications"] = _notify_form_answers(cur, new_answers)
            report["sequences"] = _sync_sequences(cur, touched, dry_run)
            report["new_ids"] = {k: v for k, v in idmap.items() if k.startswith("entities:")}
        if dry_run:
            conn.rollback()
        else:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return report
