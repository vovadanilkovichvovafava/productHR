"""Анкеты кандидата для вкладки «Анкета»: ответы, вопросы, файлы, чей профиль.

Одна сборка на двоих (06.11.2026): живая карточка
(`GET /forms/entity/{id}/all-dispatches`) и удалённая из корзины
(`GET /entities/trash/{id}/card`). Владелец: удалённая карточка — «1 в 1 как
обычная», поэтому и анкета в ней та же. Разница только в том, откуда взяты
строки анкет (база или слепок корзины) и куда ведут ссылки на файлы.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import FormSubmission, FormTemplate
from .form_answers import answer_fields, field_labels

# (entity_id, имя файла) → адрес скачивания
FileUrls = Callable[[List[Tuple[Any, str]]], Awaitable[Dict[Tuple[Any, str], str]]]


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _get(row: Any, key: str) -> Any:
    return row.get(key) if isinstance(row, dict) else getattr(row, key, None)


async def build_dispatch_list(
    db: AsyncSession,
    rows: Iterable[Any],
    *,
    entity_id: int,
    merged_from: Any,
    file_urls: FileUrls,
) -> List[Dict[str, Any]]:
    """Ответ вкладки «Анкета». rows — FormDispatch или строки слепка (dict)."""
    rows = list(rows)

    # Названия и вопросы анкет. Вопросы ответа — его снимок на момент
    # отправки (fields_snapshot), у старых ответов — текущие поля шаблона.
    form_ids = {_get(d, "form_id") for d in rows}
    titles: Dict[int, str] = {}
    template_fields: Dict[int, list] = {}
    if form_ids:
        for fid, title, fields in (await db.execute(
            select(FormTemplate.id, FormTemplate.title, FormTemplate.fields).where(FormTemplate.id.in_(form_ids))
        )).all():
            titles[fid] = title
            template_fields[fid] = fields or []

    # Ответ анкеты при удалении кандидата не стирается (ссылка обнуляется),
    # поэтому и у удалённого он берётся из базы по номеру.
    subs: Dict[int, FormSubmission] = {}
    sub_ids = [_get(d, "submission_id") for d in rows if _get(d, "submission_id")]
    if sub_ids:
        for sub in (await db.execute(select(FormSubmission).where(FormSubmission.id.in_(sub_ids)))).scalars().all():
            subs[sub.id] = sub

    def fields_of(d) -> list:
        sub = subs.get(_get(d, "submission_id"))
        return answer_fields(template_fields.get(_get(d, "form_id")), sub.fields_snapshot if sub else None)

    def file_field_ids(d) -> list:
        return [f["id"] for f in fields_of(d) if isinstance(f, dict) and f.get("type") == "file" and f.get("id")]

    def data_of(d) -> dict:
        sub = subs.get(_get(d, "submission_id"))
        return (sub.data if sub else None) or {}

    # Резолв файлов анкеты: (entity_id, имя файла) → URL скачивания, чтобы поле
    # типа «файл» в ответах было кликабельным (а не просто именем).
    needed_files = []
    for d in rows:
        data = data_of(d)
        for ffid in file_field_ids(d):
            val = data.get(ffid)
            if isinstance(val, str) and val.strip():
                needed_files.append((_get(d, "entity_id"), val.strip()))
    file_url_map = await file_urls(needed_files) if needed_files else {}

    # Карта: id диспатча → имя профиля-источника. После merge ВСЕ диспатчи висят на
    # target (FormDispatch перепривязан, иначе CASCADE-delete стирал бы анкеты влитого
    # профиля), поэтому различаем по id (захвачен в merged_from[].form_dispatch_ids),
    # а не по entity_id.
    _mf_list = merged_from if isinstance(merged_from, list) else []
    dispatch_source: Dict[int, str] = {}
    for m in _mf_list:
        if not isinstance(m, dict):
            continue
        nm = m.get("name") or (f"Профиль #{m.get('entity_id')}" if m.get("entity_id") else "Объединённый профиль")
        for did in (m.get("form_dispatch_ids") or []):
            dispatch_source[did] = nm

    result = []
    for d in rows:
        d_id = _get(d, "id")
        d_entity = _get(d, "entity_id")
        source_name = dispatch_source.get(d_id)
        if source_name is None:
            # Легаси-путь: диспатч ещё висит на влитом профиле по entity_id
            # (слияния до фикса form_dispatch_ids).
            if d_entity != entity_id:
                for m in _mf_list:
                    if isinstance(m, dict) and m.get("entity_id") == d_entity:
                        source_name = m.get("name") or f"Профиль #{d_entity}"
                        break
            if source_name is None:
                source_name = "Текущий профиль"

        d_sub = subs.get(_get(d, "submission_id"))
        d_data = data_of(d)
        d_file_links = {}
        for ffid in file_field_ids(d):
            val = d_data.get(ffid)
            if isinstance(val, str) and val.strip():
                url = file_url_map.get((d_entity, val.strip()))
                if url:
                    d_file_links[ffid] = url

        result.append({
            "id": d_id, "form_id": _get(d, "form_id"), "form_title": titles.get(_get(d, "form_id")),
            "token": _get(d, "token"), "status": _get(d, "status"),
            "seen_by_recruiter": _get(d, "seen_by_recruiter"),
            "submission_id": _get(d, "submission_id"), "answers": d_sub.data if d_sub else None,
            "field_labels": field_labels(fields_of(d)),
            "file_links": d_file_links,  # field_id → URL скачивания файла
            "created_at": _iso(_get(d, "created_at")),
            "submitted_at": _iso(_get(d, "submitted_at")),
            "source_entity_id": d_entity,
            "source_name": source_name,  # Какой профиль заполнил
        })
    return result
