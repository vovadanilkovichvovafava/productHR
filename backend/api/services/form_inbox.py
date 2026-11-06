"""Все анкеты организации одним списком — страница «Анкеты → Ответы» (06.11.2026).

Владелец: «отдельная страница с анкетами — на случай, если кандидат
потеряется или анкета от него не дойдёт и не отобразится». Ответ кандидата до
этого был виден только во вкладке «Анкета» его карточки; если карточки нет,
ответа не видно нигде. На проде таких было 9 (карточку удалили — ссылка
стёрлась каскадом, а сам ответ остался с пустым кандидатом).

Строка списка — либо отправленная ссылка (`FormDispatch`), либо ответ, на
который не ссылается ни одна ссылка (`orphan`): он не виден ни в одной
карточке. Статусы: submitted (заполнена), opened (открыта, не отправлена),
sent (не открыта), orphan (без кандидата / не в карточке).

Счётчики вкладок считаются по тем же фильтрам, что и список, — бейдж и список
не расходятся (правило из CLAUDE.md).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Set

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import (
    Entity, EntityFile, FormClientError, FormDispatch, FormSubmission, FormTemplate, User,
)
from .form_answers import answer_fields, field_labels
from .hr_stages import STATUS_LABELS
from .vacancy_scope import entity_scope_filter

STATUSES = ("submitted", "opened", "sent", "orphan")

# По подписи вопроса узнаём, где кандидат вписал, кто он: у ответа без
# карточки это единственный способ понять, чей он.
_WHO_LABEL = re.compile(r"фио|имя|фамил|name|телефон|phone|номер|telegram|телеграм|ник|почт|e-?mail", re.I)


def _iso(value: Any) -> Optional[str]:
    return value.isoformat() if value is not None else None


def dispatch_status(status: Optional[str]) -> str:
    return status if status in ("submitted", "opened") else "sent"


def who_hint(data: Any, fields: Iterable[Any]) -> Optional[str]:
    """«Иванов Иван · +375 29 …» — что кандидат вписал о себе, до двух ответов."""
    if not isinstance(data, dict):
        return None
    labels = field_labels(list(fields))
    parts: List[str] = []
    for fid, value in data.items():
        label = labels.get(fid) or ""
        if not _WHO_LABEL.search(label) or not isinstance(value, (str, int)):
            continue
        text = str(value).strip()
        if text:
            parts.append(text[:60])
        if len(parts) == 2:
            break
    return " · ".join(parts) or None


def activity_at(item: Dict[str, Any]) -> str:
    """Дата последнего события строки — по ней порядок и фильтр «за N дней»."""
    return item.get("submitted_at") or item.get("opened_at") or item.get("created_at") or ""


def matches(item: Dict[str, Any], *, q: str, form_id: Optional[int], sent_by: Optional[int],
            since: Optional[str]) -> bool:
    if form_id is not None and item.get("form_id") != form_id:
        return False
    if sent_by is not None and item.get("sent_by_id") != sent_by:
        return False
    if since and activity_at(item) < since:
        return False
    if q:
        hay = " ".join(str(item.get(k) or "") for k in ("entity_name", "form_title", "hint", "sent_by_name"))
        if q not in hay.lower().replace("ё", "е"):
            return False
    return True


def summarize(items: List[Dict[str, Any]], *, status: Optional[str], q: str = "",
              form_id: Optional[int] = None, sent_by: Optional[int] = None,
              days: Optional[int] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Отфильтровать строки и посчитать вкладки. Чистая функция — под тестами."""
    q = (q or "").strip().lower().replace("ё", "е")
    since = None
    if days:
        since = ((now or datetime.utcnow()) - timedelta(days=days)).isoformat()
    picked = [i for i in items if matches(i, q=q, form_id=form_id, sent_by=sent_by, since=since)]
    counts = {s: 0 for s in STATUSES}
    for i in picked:
        counts[i["status"]] += 1
    counts["all"] = len(picked)
    if status in STATUSES:
        picked = [i for i in picked if i["status"] == status]
    picked.sort(key=activity_at, reverse=True)
    return {"items": picked, "counts": counts}


async def load_items(db: AsyncSession, org_id: Optional[int], scope_ids: Optional[Set[int]]) -> List[Dict[str, Any]]:
    """Все строки организации (org_id=None — суперадмин без организации: все)."""
    q = (
        select(FormDispatch, FormTemplate.title, Entity.name, Entity.status, User.name)
        .join(FormTemplate, FormTemplate.id == FormDispatch.form_id)
        .join(Entity, Entity.id == FormDispatch.entity_id)
        .outerjoin(User, User.id == FormDispatch.created_by)
    )
    if org_id is not None:
        q = q.where(FormTemplate.org_id == org_id, Entity.org_id == org_id)
    if scope_ids is not None:
        q = q.where(entity_scope_filter(scope_ids))
    rows = (await db.execute(q)).all()

    errors: Dict[int, Dict[str, Any]] = {}
    ids = [d.id for d, *_ in rows]
    if ids:
        for e in (await db.execute(
            select(FormClientError).where(FormClientError.dispatch_id.in_(ids))
            .order_by(FormClientError.created_at.desc(), FormClientError.id.desc())
        )).scalars().all():
            if e.dispatch_id in errors:
                errors[e.dispatch_id]["count"] += 1
                continue
            errors[e.dispatch_id] = {
                "at": _iso(e.created_at), "kind": e.kind, "status": e.status,
                "message": e.message, "online": e.online, "count": 1,
            }

    items: List[Dict[str, Any]] = []
    for d, form_title, entity_name, entity_status, sender_name in rows:
        st = getattr(entity_status, "value", entity_status)
        status = dispatch_status(d.status)
        items.append({
            "kind": "dispatch", "id": d.id, "form_id": d.form_id, "form_title": form_title,
            "entity_id": d.entity_id, "entity_name": entity_name,
            "entity_status": STATUS_LABELS.get(st, st) if st else None,
            "sent_by_id": d.created_by, "sent_by_name": sender_name,
            "created_at": _iso(d.created_at), "opened_at": _iso(d.opened_at),
            "submitted_at": _iso(d.submitted_at), "status": status,
            "token": d.token,
            # ошибка отправки важна, пока ответа нет; после ответа это история
            "error": errors.get(d.id) if status != "submitted" else None,
        })

    # Ответы, на которые не ссылается ни одна ссылка: их нет ни в одной карточке.
    # Человек со скоупом по воронкам их не видит — чей ответ, неизвестно.
    if scope_ids is None:
        oq = (
            select(FormSubmission, FormTemplate.title, FormTemplate.fields, Entity.name)
            .join(FormTemplate, FormTemplate.id == FormSubmission.form_id)
            .outerjoin(Entity, Entity.id == FormSubmission.entity_id)
            .where(~exists().where(FormDispatch.submission_id == FormSubmission.id))
        )
        if org_id is not None:
            oq = oq.where(FormTemplate.org_id == org_id)
        for sub, form_title, template_fields, entity_name in (await db.execute(oq)).all():
            items.append({
                "kind": "orphan", "id": sub.id, "form_id": sub.form_id, "form_title": form_title,
                "entity_id": sub.entity_id if entity_name else None, "entity_name": entity_name,
                "entity_status": None, "sent_by_id": None, "sent_by_name": None,
                "created_at": _iso(sub.submitted_at), "opened_at": None,
                "submitted_at": _iso(sub.submitted_at), "status": "orphan", "token": None,
                "error": None,
                "hint": who_hint(sub.data, answer_fields(template_fields or [], sub.fields_snapshot)),
            })
    return items


async def file_urls(db: AsyncSession, needed_files):
    """(entity_id, имя файла) → адрес скачивания; как во вкладке «Анкета»."""
    names = list({n for _, n in needed_files})
    eids = [e for e in {e for e, _ in needed_files} if e]
    out: Dict[Any, str] = {}
    if not names or not eids:
        return out
    for eid, file_id, fname in (await db.execute(
        select(EntityFile.entity_id, EntityFile.id, EntityFile.file_name)
        .where(EntityFile.entity_id.in_(eids), EntityFile.file_name.in_(names))
        .order_by(EntityFile.id.desc())
    )).all():
        out.setdefault((eid, fname), f"/api/entities/{eid}/files/{file_id}/download")
    return out
