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


def _upsert(cur, table: str, rows: Iterable[dict], meta, insert: bool = True) -> dict:
    """insert=False — шаг "update": только существующие строки, пропавшие — в отчёт."""
    cols, pk = meta
    stats = {"inserted": 0, "updated": 0, "absent": 0}
    for raw in rows:
        raw = dict(raw)
        file_b64 = raw.pop("file_data_b64", None)
        row = _normalize(raw, cols)
        missing_pk = [k for k in pk if row.get(k) in (None, "")]
        if missing_pk:
            raise ValueError(f"{table}: в строке нет ключа {missing_pk}")
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
        if file_b64 is not None:
            import psycopg2

            where = " AND ".join(f"{_q(k)} = %s" for k in pk)
            cur.execute(
                f"UPDATE public.{_q(table)} SET file_data = %s WHERE {where}",
                [psycopg2.Binary(base64.b64decode(file_b64))] + [row[k] for k in pk],
            )
    return stats


def _delete(cur, table: str, keys: Iterable[dict], meta) -> dict:
    _cols, pk = meta
    stats = {"deleted": 0, "absent": 0}
    for key in keys:
        if set(key) != set(pk):
            raise ValueError(f"{table}: ключ удаления {sorted(key)} не совпадает с {pk}")
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
            for i, step in enumerate(bundle["steps"]):
                table, op = step["table"], step["op"]
                if table not in metas:
                    metas[table] = _table_meta(cur, table)
                if op == "upsert":
                    stats = _upsert(cur, table, step["rows"], metas[table])
                    touched.append(table)
                elif op == "update":
                    stats = _upsert(cur, table, step["rows"], metas[table], insert=False)
                    touched.append(table)
                elif op == "delete":
                    stats = _delete(cur, table, step["keys"], metas[table])
                else:
                    raise ValueError(f"шаг {i}: неизвестная операция {op}")
                report["steps"].append({"op": op, "table": table, **stats})
                logger.warning("HR_DELTA %s %s %s%s", op, table, stats, " (dry_run)" if dry_run else "")
            report["sequences"] = _sync_sequences(cur, touched, dry_run)
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
