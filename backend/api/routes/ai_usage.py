"""«Расход ИИ» — сводка по вызовам Claude (21.10.2026, services/ai_usage.py).

Только владельцу, админам организации и суперадмину: это деньги компании.
Расход общий на всё приложение (бот, созвоны, HR), поэтому без деления по
организациям.
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.database import AiUsageEvent, OrgMember, OrgRole, User, UserRole
from ..services.ai_usage import label_of
from ..services.auth import get_current_user

router = APIRouter()


async def _ensure_admin(db: AsyncSession, user: User) -> None:
    if user.role == UserRole.superadmin:
        return
    role = (await db.execute(
        select(OrgMember.role).where(OrgMember.user_id == user.id)
    )).scalars().first()
    if role not in (OrgRole.owner, OrgRole.admin):
        raise HTTPException(403, "Расход ИИ доступен только владельцу и админам")


@router.get("")
async def ai_usage_summary(
    days: int = Query(7, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user = await db.merge(current_user)
    await _ensure_admin(db, current_user)
    since = datetime.utcnow() - timedelta(days=days)
    where = AiUsageEvent.at >= since

    by_caller = (await db.execute(
        select(
            AiUsageEvent.caller, AiUsageEvent.model,
            func.count(AiUsageEvent.id),
            func.sum(AiUsageEvent.input_tokens), func.sum(AiUsageEvent.output_tokens),
            func.sum(AiUsageEvent.cache_read_tokens), func.sum(AiUsageEvent.cost_usd),
            func.sum(case((AiUsageEvent.ok.is_(False), 1), else_=0)),
        ).where(where).group_by(AiUsageEvent.caller, AiUsageEvent.model)
    )).all()
    rows = [
        {
            "caller": caller, "label": label_of(caller or ""), "model": model,
            "calls": calls, "input_tokens": int(inp or 0), "output_tokens": int(out or 0),
            "cache_read_tokens": int(cr or 0), "cost_usd": round(float(cost or 0), 4),
            "errors": int(errs or 0),
        }
        for caller, model, calls, inp, out, cr, cost, errs in by_caller
    ]
    rows.sort(key=lambda r: -r["cost_usd"])

    day = func.date(AiUsageEvent.at)
    by_day = (await db.execute(
        select(day, func.count(AiUsageEvent.id), func.sum(AiUsageEvent.cost_usd))
        .where(where).group_by(day).order_by(day)
    )).all()

    last_errors = (await db.execute(
        select(AiUsageEvent).where(where, AiUsageEvent.ok.is_(False))
        .order_by(AiUsageEvent.id.desc()).limit(5)
    )).scalars().all()

    return {
        "days": days,
        "total_cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
        "total_calls": sum(r["calls"] for r in rows),
        "by_caller": rows,
        "by_day": [{"day": str(d), "calls": c, "cost_usd": round(float(cost or 0), 4)} for d, c, cost in by_day],
        "last_errors": [
            {"at": e.at.isoformat() if e.at else None, "label": label_of(e.caller or ""), "error": e.error}
            for e in last_errors
        ],
    }
