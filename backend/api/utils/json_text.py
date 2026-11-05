"""JSON в базе — с русскими буквами как есть, а не кодами `\\u0437`.

У SQLAlchemy по умолчанию `json.dumps` с ensure_ascii=True: всё, что сайт писал
в JSON-колонки (комментарии, метки, резюме в extra_data), ложилось в базу
кодами. Колонки у нас типа JSON (не JSONB) — Postgres хранит текст как есть,
и поиск `ILIKE '%слово%'` по комментариям не находил ничего, что написано на
сайте; находилось только перенесённое дампом (05.11.2026, карточка 9876).
Накопленное перекодирует `services/json_unescape.py`.
"""
import json


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)
