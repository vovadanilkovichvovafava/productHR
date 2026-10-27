"""«Был отказ» — прошлые отказы человека (владелец, 22.10.2026).

Задача: рекрутёр должен видеть, что кандидат уже получал у нас отказ, ДО того
как снова тратить на него время. Матчер дублей (duplicate_matcher) находит «тот
же человек» только по личным данным и про отказы не знает ничего; плашка дубля
говорила «Возможно тот же человек · 64%» без слова о том, что тогда случилось.
На проде (22.10.2026): из 6 пар «одна карточка в Отказе, другая живая» все шесть
были помечены дублями — и ни одну не разобрали.

Решение владельца: ПРЕДУПРЕЖДАТЬ, не запрещать; показывать в списке, воронке,
карточке, расширении и в окне добавления в воронку; отказы считать и в
Enceladus, и в архиве ClickUp.

Откуда берётся отказ (`rejections_by_entity`):
- заявка на этапе «Отказ» (живая воронка): дата, воронка, кто отклонил, с
  какого этапа, комментарий к переводу, причина отказа заявки;
- кандидат вне воронок: запись ленты со `stage == "rejected"`;
- архив ClickUp: прохождение со статусом «…: нет» («собес (1): нет» — отказ на
  этом этапе) или «неявка» / «не отвечают» (вид `no_show` — не пришёл);
- общий статус «Отказ» без всего этого — запись без подробностей.

Чей отказ показываем (`prior_rejections`): связанных карточек того же человека
(`hidden_duplicate_id` в обе стороны) и — где просят — своих ДРУГИХ воронок.
Своя воронка, в которой человек сейчас стоит в «Отказе», — не «прошлый» отказ.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import (
    ApplicationStage, Entity, EntityStatus, StageTransition, User, Vacancy, VacancyApplication,
)
from .hr_stages import stage_label

# Статус прохождения ClickUp. «Собес (1): нет» — кандидат не прошёл этап (это
# наш отказ); «неявка (1)», «не отвечают» — пропал сам.
ARCHIVE_REJECTED_RE = re.compile(r":\s*нет\b|отказ|reject", re.I)
ARCHIVE_NO_SHOW_RE = re.compile(r"неявк|не\s*отвеча|не\s*приш[её]л", re.I)


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    # ClickUp: «2025-03-12 10:41:00» → ISO
    return text.replace(" ", "T", 1) if re.match(r"^\d{4}-\d{2}-\d{2} ", text) else text


def sort_key(r: Dict[str, Any]):
    return (r.get("date") is not None, r.get("date") or "")


def linked_ids(entities: Iterable[Any]) -> Dict[int, Set[int]]:
    """Связанные карточки того же человека по пометке дубля, в обе стороны.

    Пометка (`extra_data.hidden_duplicate_id`) ставится детектором дублей на
    новую карточку и обратной ссылкой на найденную. Берём обе стороны среди
    переданных карточек: у старой копии пометка может указывать на третью.
    """
    out: Dict[int, Set[int]] = {}
    for e in entities:
        ed = e.extra_data if isinstance(getattr(e, "extra_data", None), dict) else {}
        other = ed.get("hidden_duplicate_id")
        try:
            other = int(other) if other is not None else None
        except (TypeError, ValueError):
            other = None
        if other and other != e.id:
            out.setdefault(e.id, set()).add(other)
            out.setdefault(other, set()).add(e.id)
    return out


async def rejections_by_entity(
    db: AsyncSession,
    entity_ids: Iterable[int],
    *,
    scope_ids: Optional[Iterable[int]] = None,
) -> Dict[int, List[Dict[str, Any]]]:
    """Все отказы по каждой карточке, свежие первыми."""
    ids = sorted({int(i) for i in entity_ids if i})
    out: Dict[int, List[Dict[str, Any]]] = {i: [] for i in ids}
    if not ids:
        return out
    scope = set(scope_ids) if scope_ids else None

    # 1) Заявки на этапе «Отказ» в живых (не удалённых) воронках.
    app_rows = (await db.execute(
        select(
            VacancyApplication.id, VacancyApplication.entity_id, VacancyApplication.vacancy_id,
            VacancyApplication.rejection_reason, VacancyApplication.last_stage_change_at,
            Vacancy.title,
        )
        .join(Vacancy, Vacancy.id == VacancyApplication.vacancy_id)
        .where(
            VacancyApplication.entity_id.in_(ids),
            VacancyApplication.stage == ApplicationStage.rejected,
            Vacancy.deleted_at.is_(None),
        )
    )).all()
    if scope is not None:
        app_rows = [r for r in app_rows if r.vacancy_id in scope]
    by_app: Dict[int, Dict[str, Any]] = {}
    for r in app_rows:
        rec = {
            "kind": "rejected", "source": "funnel", "entity_id": r.entity_id,
            "application_id": r.id, "vacancy_id": r.vacancy_id, "vacancy_title": r.title,
            "date": _iso(r.last_stage_change_at), "reason": r.rejection_reason or None,
            "recruiter_name": None, "from_stage": None, "comment": None,
        }
        by_app[r.id] = rec
        out[r.entity_id].append(rec)
    if by_app:
        # Последний перевод в «Отказ» по каждой заявке: кто, откуда, с каким текстом.
        tr_rows = (await db.execute(
            select(
                StageTransition.application_id, StageTransition.from_stage,
                StageTransition.comment, StageTransition.created_at, User.name,
            )
            .outerjoin(User, User.id == StageTransition.changed_by)
            .where(
                StageTransition.application_id.in_(list(by_app)),
                StageTransition.to_stage == ApplicationStage.rejected.value,
            )
            .order_by(StageTransition.created_at.desc(), StageTransition.id.desc())
        )).all()
        seen: Set[int] = set()
        for t in tr_rows:
            if t.application_id in seen:
                continue
            seen.add(t.application_id)
            rec = by_app[t.application_id]
            rec["recruiter_name"] = t.name
            rec["from_stage"] = stage_label(t.from_stage) if t.from_stage else None
            rec["comment"] = (t.comment or "").strip() or None
            rec["date"] = _iso(t.created_at) or rec["date"]

    # 2) Карточки: отказ вне воронок, архив ClickUp, общий статус.
    ent_rows = (await db.execute(
        select(Entity.id, Entity.status, Entity.is_archived, Entity.extra_data).where(Entity.id.in_(ids))
    )).all()
    for r in ent_rows:
        ed = r.extra_data if isinstance(r.extra_data, dict) else {}
        found = bool(out[r.id])
        for n in ed.get("notes") or []:
            if not isinstance(n, dict) or n.get("stage") != EntityStatus.rejected.value:
                continue
            found = True
            out[r.id].append({
                "kind": "rejected", "source": "card", "entity_id": r.id,
                "vacancy_id": None, "vacancy_title": None, "date": _iso(n.get("date")),
                "recruiter_name": n.get("author_name"), "comment": (n.get("text") or "").strip() or None,
                "from_stage": None, "reason": None,
            })
        for p in ed.get("participations") or []:
            if not isinstance(p, dict):
                continue
            status = (p.get("status") or "").strip()
            kind = ("rejected" if ARCHIVE_REJECTED_RE.search(status)
                    else "no_show" if ARCHIVE_NO_SHOW_RE.search(status) else None)
            if not kind:
                continue
            found = True
            out[r.id].append({
                "kind": kind, "source": "archive", "entity_id": r.id,
                "vacancy_id": None, "vacancy_title": (p.get("vacancy_title") or "").strip() or None,
                "date": _iso(p.get("date")), "recruiter_name": (p.get("recruiter") or "").strip() or None,
                "from_stage": status, "comment": None, "reason": None,
            })
        status_val = r.status.value if hasattr(r.status, "value") else r.status
        if not found and status_val == EntityStatus.rejected.value:
            out[r.id].append({
                "kind": "rejected", "source": "card", "entity_id": r.id,
                "vacancy_id": None, "vacancy_title": None, "date": None,
                "recruiter_name": None, "comment": None, "from_stage": None, "reason": None,
            })
        for rec in out[r.id]:
            rec["archived"] = bool(r.is_archived)

    for lst in out.values():
        lst.sort(key=sort_key, reverse=True)
    return out


async def prior_rejections(
    db: AsyncSession,
    entities: List[Any],
    *,
    own_except_vacancy: Optional[Dict[int, Optional[int]]] = None,
    scope_ids: Optional[Iterable[int]] = None,
    extra_links: Optional[Dict[int, Set[int]]] = None,
) -> Dict[int, List[Dict[str, Any]]]:
    """Прошлые отказы человека для каждой карточки из `entities`.

    Всегда — отказы СВЯЗАННЫХ карточек (дубли того же человека). Свои — только
    если карточка есть в `own_except_vacancy` (воронка: отказы в других
    воронках, кроме указанной). На «Все кандидаты» свои не берём: чипы этапов по
    воронкам уже видны в строке.
    """
    links = linked_ids(entities)
    for k, v in (extra_links or {}).items():
        links.setdefault(k, set()).update(v)
    own = own_except_vacancy or {}
    wanted: Set[int] = set(own)
    for e in entities:
        wanted |= links.get(e.id, set())
    if not wanted:
        return {}
    rej = await rejections_by_entity(db, wanted, scope_ids=scope_ids)
    out: Dict[int, List[Dict[str, Any]]] = {}
    for e in entities:
        items: List[Dict[str, Any]] = []
        for other in links.get(e.id, set()):
            if other != e.id:
                items.extend(rej.get(other, []))
        if e.id in own:
            skip = own[e.id]
            # Свои: другие воронки, отказ вне воронок (запись ленты) и прохождения
            # архива. Голый общий статус «Отказ» без записи — нет: он описывает
            # текущее положение, а не прошлое.
            items.extend(
                r for r in rej.get(e.id, [])
                if (r["source"] == "funnel" and r.get("vacancy_id") != skip)
                or r["source"] == "archive"
                or (r["source"] == "card" and r.get("date"))
            )
        if items:
            out[e.id] = sorted(items, key=sort_key, reverse=True)
    return out


def summary(items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Короткая метка для строки списка: последний отказ + сколько всего."""
    if not items:
        return None
    top = dict(items[0])
    top["count"] = len(items)
    return top
