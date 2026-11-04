"""Ручки HR-бота практики и испытательного срока (ТЗ «Пребординг и онбординг трафика»).

HR назначает практику в карточке кандидата → бот получает дату и время старта, а HR —
персональную ссылку, которую отправляет кандидату. Дальше сценарии идут сами
(api/onboarding/service.py); статусы «переведён в отдел» / «не прошёл» / «ушёл» HR
ставит здесь же.

Доступ — рекрутёры организации (owner/admin/hr), чужой или вне скоупа кандидат — 404.
Данные кошелька — владелец, админы и бухгалтерия, которой они выдали доступ; чтение пишется в лог.
"""

import logging
from datetime import date, datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.database import Entity, OrgRole, User, UserRole
from ..onboarding.models import (
    ACTIVE_STATUSES, CaseStatus, Handoff, HandoffAccount, OnboardingCase, Signal, SurveyResponse, Wallet,
    WalletAccess,
)
from ..onboarding.runtime import enabled, get_service
from ..onboarding.surveys import SURVEYS
from ..services.auth import get_current_user, get_user_org, get_user_org_role
from ..services.similarity import first_real_telegram
from ..services.vacancy_scope import ensure_entity_visible

logger = logging.getLogger("hr-analyzer.onboarding")

router = APIRouter()

RECRUITER_ROLES = (OrgRole.owner, OrgRole.admin, OrgRole.hr)
STATUS_LABELS = {
    "practice_assigned": "Практика назначена",
    "practice_running": "Практика идёт",
    "transferred": "Переведён в отдел",
    "failed": "Не прошёл",
    "probation": "На испытательном",
    "left": "Ушёл",
}


class CaseCreate(BaseModel):
    practice_start: datetime = Field(description="Старт практики, местное время кандидата")
    first_name: Optional[str] = Field(None, max_length=100, description="Как обращаться; по умолчанию — ФИО")
    timezone: Optional[str] = Field(None, max_length=64)
    practice_lead: str = Field("", max_length=200, description="Руководитель практики: имя и контакт")
    hrd: str = Field("", max_length=200, description="HRD: имя и контакт")
    hr_user_id: Optional[int] = Field(None, description="Ответственный HR; по умолчанию — кто назначает")


class StatusChange(BaseModel):
    status: CaseStatus
    department: Optional[str] = Field(None, max_length=200)
    lead_user_id: Optional[int] = None
    lead_name: Optional[str] = Field(None, max_length=200)
    department_start_date: Optional[date] = None
    reason: Optional[str] = Field(None, max_length=2000, description="Причина ухода (для статуса «Ушёл»)")


class ProbationDecision(BaseModel):
    decision: Literal["stays", "extended", "leaves"]
    new_end_date: Optional[date] = Field(None, description="Новая дата конца срока — для «продлевается»")
    reason: Optional[str] = Field(None, max_length=2000, description="Причина ухода — для «уходит»")


async def _org_and_role(user: User, db: AsyncSession):
    org = await get_user_org(user, db)
    if org is None:
        raise HTTPException(403, "Нет организации")
    role = None if user.role == UserRole.superadmin else await get_user_org_role(user, org.id, db)
    if user.role != UserRole.superadmin and role not in RECRUITER_ROLES:
        raise HTTPException(403, "Бот практики доступен рекрутёрам")
    return org, role


async def _entity(entity_id: int, org_id: int, user: User, db: AsyncSession) -> Entity:
    entity = await db.get(Entity, entity_id)
    if entity is None or entity.org_id != org_id:
        raise HTTPException(404, "Кандидат не найден")
    await ensure_entity_visible(entity_id, user, db)
    return entity


async def _case(case_id: int, org_id: int, user: User, db: AsyncSession) -> OnboardingCase:
    case = await db.get(OnboardingCase, case_id)
    if case is None or case.org_id != org_id:
        raise HTTPException(404, "Карточка бота не найдена")
    if case.entity_id is not None:
        await ensure_entity_visible(case.entity_id, user, db)
    return case


async def _service_or_503():
    service = await get_service() if enabled() else None
    if service is None:
        raise HTTPException(503, "Бот практики выключен: не задан TELEGRAM_BOT_TOKEN или ONBOARDING_WALLET_KEY")
    return service


async def _case_view(case: OnboardingCase, db: AsyncSession) -> dict:
    signals = (await db.execute(
        select(Signal).where(Signal.case_id == case.id).order_by(Signal.id.desc()).limit(100)
    )).scalars().all()
    responses = (await db.execute(
        select(SurveyResponse).where(SurveyResponse.case_id == case.id).order_by(SurveyResponse.id)
    )).scalars().all()
    has_wallet = await db.scalar(select(Wallet.id).where(Wallet.case_id == case.id)) is not None

    surveys: dict[str, dict] = {}
    for r in responses:
        if r.survey not in SURVEYS:
            continue
        block = surveys.setdefault(r.survey, {"title": SURVEYS[r.survey].title, "done": False, "answers": []})
        if r.question < 0:
            block["done"] = True
            continue
        block["answers"].append({
            "question": SURVEYS[r.survey].questions[r.question].text,
            "answer": r.answer,
            "is_signal": r.is_signal,
            "at": r.created_at,
        })
    loom = [r.answer for r in responses if r.survey == "loom"]

    service = await get_service() if enabled() else None
    return {
        "id": case.id,
        "entity_id": case.entity_id,
        "status": case.status,
        "status_label": STATUS_LABELS.get(case.status, case.status),
        "full_name": case.full_name,
        "first_name": case.first_name,
        "timezone": case.timezone,
        "invite_link": service.invite_link(case) if service else None,
        "candidate_opened_bot": case.candidate_tg_id is not None,
        "linked_at": case.linked_at,
        "practice_start_at_utc": case.practice_start_at,
        "practice_last_day": case.practice_last_day,
        "practice_lead": case.practice_lead,
        "hrd": case.hrd,
        "hr_telegram_missing": case.hr_tg_id is None,
        "script_answer": case.script_answer,
        "script_answer_at": case.script_answer_at,
        "work_chat_id": case.work_chat_id,
        "practice_started_at": case.practice_started_at,
        "has_wallet": has_wallet,
        "department": case.department,
        "lead_name": case.lead_name,
        "department_start_date": case.department_start_date,
        "probation_end_date": case.probation_end_date,
        "probation_decision": case.probation_decision,
        "left_at": case.left_at,
        "left_reason": case.left_reason,
        "loom": loom,
        "surveys": surveys,
        "signals": [{"kind": s.kind, "text": s.text, "delivered": s.delivered_to is not None, "at": s.created_at}
                    for s in signals],
    }


@router.get("/status")
async def onboarding_status(current_user: User = Depends(get_current_user)):
    return {"enabled": enabled()}


@router.get("/entities/{entity_id}/case")
async def get_entity_case(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user = await db.merge(current_user)
    org, _ = await _org_and_role(current_user, db)
    await _entity(entity_id, org.id, current_user, db)
    case = await db.scalar(
        select(OnboardingCase)
        .where(OnboardingCase.entity_id == entity_id, OnboardingCase.org_id == org.id)
        .order_by(OnboardingCase.id.desc())
        .limit(1)
    )
    return {"enabled": enabled(), "case": await _case_view(case, db) if case else None}


@router.post("/entities/{entity_id}/case", status_code=201)
async def create_entity_case(
    entity_id: int,
    body: CaseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """«Практика назначена» (ТЗ 3.1): бот ставит расписание, HR получает ссылку для кандидата."""
    current_user = await db.merge(current_user)
    org, _ = await _org_and_role(current_user, db)
    entity = await _entity(entity_id, org.id, current_user, db)
    service = await _service_or_503()

    active = await db.scalar(
        select(OnboardingCase.id).where(
            OnboardingCase.entity_id == entity_id, OnboardingCase.status.in_(ACTIVE_STATUSES)
        )
    )
    if active is not None:
        raise HTTPException(409, "У кандидата уже идёт сценарий бота — сначала завершите его")

    hr_user = current_user
    if body.hr_user_id is not None and body.hr_user_id != current_user.id:
        hr_user = await db.get(User, body.hr_user_id)
        if hr_user is None or await get_user_org_role(hr_user, org.id, db) not in RECRUITER_ROLES:
            raise HTTPException(400, "Ответственный HR должен быть рекрутёром этой организации")

    practice_start = body.practice_start.replace(tzinfo=None) if body.practice_start.tzinfo else body.practice_start
    try:
        case = await service.create_case(
            full_name=entity.name,
            first_name=(body.first_name or entity.name).strip(),
            practice_start=practice_start,
            candidate_tg_username=first_real_telegram(entity.telegram_usernames or []),
            tz=body.timezone,
            practice_lead=body.practice_lead,
            hrd=body.hrd,
            hr_tg_id=hr_user.telegram_id,
            entity_id=entity.id,
            org_id=org.id,
            created_by=current_user.id,
        )
    except KeyError as exc:  # неизвестный часовой пояс
        raise HTTPException(400, f"Неизвестный часовой пояс: {exc}")
    logger.info("ONBOARDING case=%s entity=%s start=%s by=%s", case.id, entity.id, practice_start, current_user.id)
    case = await db.get(OnboardingCase, case.id)
    return await _case_view(case, db)


@router.post("/cases/{case_id}/status")
async def change_case_status(
    case_id: int,
    body: StatusChange,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """«Переведён в отдел» (поздравление, опрос, онбординг), «Не прошёл», «Ушёл» и т. п."""
    current_user = await db.merge(current_user)
    org, _ = await _org_and_role(current_user, db)
    case = await _case(case_id, org.id, current_user, db)
    service = await _service_or_503()

    if body.status is CaseStatus.transferred and not (body.department or case.department):
        raise HTTPException(400, "Укажите отдел — он подставляется в поздравление")
    lead_tg_id, lead_name = None, body.lead_name
    if body.lead_user_id is not None:
        lead = await db.get(User, body.lead_user_id)
        if lead is None or await get_user_org_role(lead, org.id, db) is None:
            raise HTTPException(400, "Лид должен быть участником этой организации")
        lead_tg_id, lead_name = lead.telegram_id, lead_name or lead.name

    await service.set_status(
        case.id,
        body.status,
        department=body.department,
        lead_name=lead_name,
        lead_tg_id=lead_tg_id,
        department_start_date=body.department_start_date,
        reason=body.reason,
    )
    logger.info("ONBOARDING case=%s status=%s by=%s", case.id, body.status.value, current_user.id)
    await db.refresh(case)  # сервис писал своей сессией
    return await _case_view(case, db)


@router.post("/cases/{case_id}/probation")
async def decide_probation(
    case_id: int,
    body: ProbationDecision,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Закрытие испытательного (ТЗ 4): остаётся / продлевается (новая дата) / уходит (причина)."""
    current_user = await db.merge(current_user)
    org, _ = await _org_and_role(current_user, db)
    case = await _case(case_id, org.id, current_user, db)
    service = await _service_or_503()
    try:
        await service.decide_probation(case.id, body.decision, new_end=body.new_end_date, reason=body.reason)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    logger.info("ONBOARDING case=%s probation=%s by=%s", case.id, body.decision, current_user.id)
    await db.refresh(case)
    return await _case_view(case, db)


# --------------------------------------------------------------- кошельки


class WalletAccessGrant(BaseModel):
    user_id: int


async def _wallet_reader(user: User, db: AsyncSession):
    """Кошельки видят owner/admin и те, кому они выдали доступ (бухгалтерия)."""
    org = await get_user_org(user, db)
    if org is None:
        raise HTTPException(403, "Нет организации")
    if user.role == UserRole.superadmin:
        return org
    if await get_user_org_role(user, org.id, db) in (OrgRole.owner, OrgRole.admin):
        return org
    granted = await db.scalar(
        select(WalletAccess.id).where(WalletAccess.org_id == org.id, WalletAccess.user_id == user.id)
    )
    if granted is None:
        raise HTTPException(403, "Данные кошельков видят владелец, админы и бухгалтерия")
    return org


async def _wallet_admin(user: User, db: AsyncSession):
    org = await get_user_org(user, db)
    if org is None:
        raise HTTPException(403, "Нет организации")
    if user.role != UserRole.superadmin and await get_user_org_role(user, org.id, db) not in (OrgRole.owner, OrgRole.admin):
        raise HTTPException(403, "Доступ к кошелькам выдают владелец и админы")
    return org


@router.get("/cases/{case_id}/wallet")
async def read_wallet(
    case_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user = await db.merge(current_user)
    org = await _wallet_reader(current_user, db)
    case = await db.get(OnboardingCase, case_id)
    if case is None or case.org_id != org.id:
        raise HTTPException(404, "Карточка бота не найдена")
    service = await _service_or_503()
    wallet = await db.scalar(select(Wallet).where(Wallet.case_id == case.id))
    if wallet is None:
        raise HTTPException(404, "Кандидат ещё не прислал кошелёк")
    logger.info("PII_ACCESS onboarding_wallet case=%s entity=%s by=%s", case.id, case.entity_id, current_user.id)
    return {"wallet": service.cipher.decrypt(wallet.ciphertext), "saved_at": wallet.created_at}


@router.get("/wallets")
async def list_wallets(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Список для бухгалтерии: кто, какой отдел, кошелёк. Без остальных данных кандидата."""
    current_user = await db.merge(current_user)
    org = await _wallet_reader(current_user, db)
    service = await _service_or_503()
    rows = (await db.execute(
        select(OnboardingCase, Wallet)
        .join(Wallet, Wallet.case_id == OnboardingCase.id)
        .where(OnboardingCase.org_id == org.id)
        .order_by(OnboardingCase.full_name)
    )).all()
    logger.info("PII_ACCESS onboarding_wallets list=%s by=%s", len(rows), current_user.id)
    return [
        {
            "case_id": case.id,
            "entity_id": case.entity_id,
            "full_name": case.full_name,
            "department": case.department,
            "lead_name": case.lead_name,
            "status": case.status,
            "status_label": STATUS_LABELS.get(case.status, case.status),
            "wallet": service.cipher.decrypt(wallet.ciphertext),
            "saved_at": wallet.created_at,
        }
        for case, wallet in rows
    ]


@router.get("/wallet-access")
async def list_wallet_access(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user = await db.merge(current_user)
    org = await _wallet_admin(current_user, db)
    rows = (await db.execute(
        select(User).join(WalletAccess, WalletAccess.user_id == User.id).where(WalletAccess.org_id == org.id)
    )).scalars().all()
    return [{"user_id": u.id, "name": u.name, "email": u.email} for u in rows]


@router.post("/wallet-access", status_code=201)
async def grant_wallet_access(
    body: WalletAccessGrant,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user = await db.merge(current_user)
    org = await _wallet_admin(current_user, db)
    target = await db.get(User, body.user_id)
    if target is None or await get_user_org_role(target, org.id, db) is None:
        raise HTTPException(400, "Доступ выдаётся только участнику этой организации")
    exists = await db.scalar(
        select(WalletAccess.id).where(WalletAccess.org_id == org.id, WalletAccess.user_id == target.id)
    )
    if exists is None:
        db.add(WalletAccess(org_id=org.id, user_id=target.id, granted_by=current_user.id))
        await db.commit()
    logger.info("ONBOARDING wallet_access grant user=%s by=%s", target.id, current_user.id)
    return {"user_id": target.id, "name": target.name, "email": target.email}


@router.delete("/wallet-access/{user_id}", status_code=204)
async def revoke_wallet_access(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user = await db.merge(current_user)
    org = await _wallet_admin(current_user, db)
    row = await db.scalar(
        select(WalletAccess).where(WalletAccess.org_id == org.id, WalletAccess.user_id == user_id)
    )
    if row is not None:
        await db.delete(row)
        await db.commit()
    logger.info("ONBOARDING wallet_access revoke user=%s by=%s", user_id, current_user.id)


# ------------------------------------------- передача HR-аккаунтам автоспамера / AI-селлера

HANDOFF_STATUS_LABELS = {
    "active": "Ведётся",
    "stopped": "Остановлено",
}
HANDOFF_REASON_LABELS = {
    "no_telegram": "нет Telegram и телефона в карточке",
    "no_practice_date": "не указана дата выхода на практику",
    "no_first_day": "не указана дата выхода в отдел",
    "no_account": "ни один HR-аккаунт не нажал Start у бота",
    "send_failed": "Telegram не принял сообщение аккаунту — повтор через 10 минут",
}


@router.get("/handoffs")
async def list_handoffs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Кого передали HR-профилю, кто ждёт данных и почему (baseline — до включения — не показываем)."""
    from ..config import settings as app_settings
    from ..onboarding.config import parse_accounts

    current_user = await db.merge(current_user)
    org, _ = await _org_and_role(current_user, db)
    rows = (await db.execute(
        select(Handoff, Entity, HandoffAccount)
        .join(Entity, Entity.id == Handoff.entity_id)
        .outerjoin(HandoffAccount, HandoffAccount.id == Handoff.account_id)
        .where(Entity.org_id == org.id, Handoff.status != "baseline")
        .order_by(Handoff.id.desc())
        .limit(500)
    )).all()
    configured = parse_accounts(app_settings.onboarding_handoff_accounts)
    linked = {a.username: a for a in (await db.execute(select(HandoffAccount))).scalars().all()}
    return {
        "accounts": [
            {"username": name if name.isdigit() else f"@{name}", "linked": bool(linked.get(name) and linked[name].tg_id)}
            for name in configured
        ],
        "delivery": "webhook" if app_settings.onboarding_handoff_webhook_url.strip() else "telegram",
        "handoffs": [
            {
                "entity_id": entity.id,
                "full_name": entity.name,
                "status": row.status,
                "status_label": HANDOFF_STATUS_LABELS.get(row.status, row.status),
                "waiting_reason": HANDOFF_REASON_LABELS.get(row.waiting_reason) if row.waiting_reason else None,
                "practice_sent_at": row.practice_sent_at,
                "practice_date": row.practice_date,
                "transfer_sent_at": row.transfer_sent_at,
                "first_day": row.first_day,
                "stop_sent_at": row.stop_sent_at,
                "account": f"@{account.username}" if account else None,
            }
            for row, entity, account in rows
        ],
    }
