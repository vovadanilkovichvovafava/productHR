"""Таблицы HR-бота пребординга/онбординга (ТЗ «Пребординг и онбординг трафика»).

Создаются через Base.metadata.create_all в api/db/init.py — модуль импортируется там до create_all.
Все даты-время — naive UTC.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint

from api.models.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CaseStatus(str, enum.Enum):
    """Статусы из ТЗ, раздел 5."""

    practice_assigned = "practice_assigned"  # практика назначена
    practice_running = "practice_running"    # практика идёт
    transferred = "transferred"              # переведён в отдел
    failed = "failed"                        # не прошёл
    probation = "probation"                  # на испытательном
    left = "left"                            # ушёл


PRACTICE_STATUSES = (CaseStatus.practice_assigned.value, CaseStatus.practice_running.value)
DEPARTMENT_STATUSES = (CaseStatus.transferred.value, CaseStatus.probation.value)
ACTIVE_STATUSES = PRACTICE_STATUSES + DEPARTMENT_STATUSES


class OnboardingCase(Base):
    __tablename__ = "onboarding_cases"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    full_name = Column(String(200), nullable=False)
    first_name = Column(String(100), nullable=False)
    timezone = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, index=True)

    candidate_tg_username = Column(String(64), nullable=True, index=True)
    candidate_tg_id = Column(BigInteger, nullable=True, index=True)
    link_token = Column(String(64), nullable=False, unique=True)
    linked_at = Column(DateTime, nullable=True)

    practice_start_at = Column(DateTime, nullable=False)
    practice_last_day = Column(Date, nullable=False)
    practice_lead = Column(String(200), default="")
    hrd = Column(String(200), default="")
    hr_tg_id = Column(BigInteger, nullable=True)

    script_answer = Column(String(16), nullable=True)
    script_answer_at = Column(DateTime, nullable=True)
    work_chat_id = Column(BigInteger, nullable=True)
    practice_started_at = Column(DateTime, nullable=True)

    department = Column(String(200), nullable=True)
    lead_name = Column(String(200), nullable=True)
    lead_tg_id = Column(BigInteger, nullable=True)
    department_start_date = Column(Date, nullable=True)
    probation_end_date = Column(Date, nullable=True)
    # Закрытие испытательного (ТЗ 4): stays / extended; уход — статус left + причина (ТЗ 5)
    probation_decision = Column(String(16), nullable=True)
    left_at = Column(DateTime, nullable=True)
    left_reason = Column(Text, nullable=True)

    # Чего бот ждёт от кандидата текстом: "wallet" или "survey_text"
    awaiting = Column(String(32), nullable=True)
    survey_kind = Column(String(16), nullable=True)
    survey_step = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=_utcnow)


class BotJob(Base):
    """Запланированное действие бота. Отмена — status="cancelled"."""

    __tablename__ = "onboarding_jobs"
    __table_args__ = (Index("ix_onboarding_jobs_due", "status", "run_at"),)

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("onboarding_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(32), nullable=False)
    run_at = Column(DateTime, nullable=False)
    payload = Column(Text, nullable=True)
    status = Column(String(16), default="pending", nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


class SurveyResponse(Base):
    """Ответы опросов и Loom-кнопок. question=-1 — отметка «опрос пройден»."""

    __tablename__ = "onboarding_responses"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("onboarding_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    survey = Column(String(32), nullable=False)
    question = Column(Integer, nullable=False)
    answer = Column(Text, nullable=False)
    is_signal = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=_utcnow)


class Wallet(Base):
    """Данные крипто-кошелька, зашифрованные Fernet (ТЗ, вопрос 16)."""

    __tablename__ = "onboarding_wallets"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("onboarding_cases.id", ondelete="CASCADE"), nullable=False, unique=True)
    ciphertext = Column(Text, nullable=False)
    created_at = Column(DateTime, default=_utcnow)


class WalletAccess(Base):
    """Кому, кроме owner/admin, открыты кошельки — бухгалтерия (встреча 30.10.2026: «отдельное
    поле для бухгалтерии», «лид потерял кошелёк — запросил у HR»). Выдают owner/admin."""

    __tablename__ = "onboarding_wallet_access"
    __table_args__ = (UniqueConstraint("org_id", "user_id", name="uq_onboarding_wallet_access"),)

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    granted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=_utcnow)


class Signal(Base):
    """Сигналы и напоминания для HR и лида — журнал для карточки и аналитики."""

    __tablename__ = "onboarding_signals"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("onboarding_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(32), nullable=False)
    text = Column(Text, nullable=False)
    delivered_to = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


# ------------------------------------------------- передача в автоспамер / AI-селлер
# Голосовое Владимира 03.11.2026: своего бота-собеседника нет — переписку ведут HR-аккаунты
# автоспамера и AI-селлера; productHR только передаёт им, кого и когда вести (handoff.py).


class HandoffAccount(Base):
    """HR-аккаунт, которому бот передаёт людей. Перечислены в ONBOARDING_HANDOFF_ACCOUNTS;
    tg_id появляется, когда аккаунт один раз нажмёт Start у бота (иначе бот ему не напишет)."""

    __tablename__ = "onboarding_handoff_accounts"

    id = Column(Integer, primary_key=True)
    username = Column(String(64), nullable=False, unique=True)  # без @, в нижнем регистре
    tg_id = Column(BigInteger, nullable=True)
    linked_at = Column(DateTime, nullable=True)


class Handoff(Base):
    """Человек, переведённый в отдел, и где он в онбординге.

    status: baseline — был в отделе до включения моста, не трогаем; waiting — не хватает
    Telegram или даты выхода; active — ведётся, next_at — когда следующая пометка аккаунту;
    done — все этапы переданы; stopped — уволен/ушёл, аккаунту отправлен «стоп».
    """

    __tablename__ = "onboarding_handoffs"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, unique=True)
    status = Column(String(16), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("onboarding_handoff_accounts.id", ondelete="SET NULL"), nullable=True)
    first_day = Column(Date, nullable=True)
    stage_index = Column(Integer, default=0, nullable=False)
    next_at = Column(DateTime, nullable=True, index=True)
    waiting_reason = Column(String(32), nullable=True)
    notified_reason = Column(String(32), nullable=True)  # о чём HR уже сказали — не повторяем
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow)
