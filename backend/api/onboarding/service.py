"""Сценарии ТЗ: пребординг (практика), переход в отдел, онбординг, сигналы HR.

АТС (productHR) вызывает create_case() и set_status(); Telegram-хендлеры — handle_*();
воркер — run_due_jobs(). Сообщения уходят через Messenger, поэтому логика тестируется без Telegram.
"""

from __future__ import annotations

import json
import logging
import secrets
from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from . import schedule as sch
from . import texts
from .chat_flow import ChatFlowMixin
from .config import Settings
from .crypto import WalletCipher
from .messenger import Buttons, Messenger, SendError
from .models import (
    ACTIVE_STATUSES,
    DEPARTMENT_STATUSES,
    PRACTICE_STATUSES,
    BotJob,
    CaseStatus,
    OnboardingCase,
    Signal,
    SurveyResponse,
    Wallet,
)
from .surveys import SURVEYS

log = logging.getLogger(__name__)

PREBOARDING_JOBS = {
    "report_check",
    "report_escalate",
    "hr_practice_start",
    "invite_check",
    "first_retry",
    "first_no_answer",
    "day_before",
    "loom",
    "loom_morning",
    "practice_deadline",
}
DONE_MARK = -1  # SurveyResponse.question для отметки «опрос пройден»
# Префикс ссылки кандидата: /start с ним — наш, без него — привязка аккаунта сотрудника (api/bot.py)
TOKEN_PREFIX = "ob_"
# Карточка из статуса АТС (мит 19.11.2026): кандидат не открывал ссылку бота, в личку бот ему
# писать не может — задачи «открыл ли ссылку» и «завтра старт» не ставим. Остальное — в рабочем чате.
DM_ONLY_JOBS = {"invite_check", "day_before"}
# Окончания фамилий: «Шинкаренко Владимир» и «Владимир Шинкаренко» — имя то, что не фамилия
_SURNAME_ENDINGS = ("ова", "ева", "ина", "ына", "ская", "цкая", "ов", "ев", "ёв", "ин", "ын", "ский",
                    "цкий", "енко", "ко", "ук", "юк", "ич", "ян", "дзе", "швили", "их", "ых")


def first_name_of(full_name: str) -> str:
    """Имя для обращения из ФИО карточки. В АТС порядок «Фамилия Имя Отчество», но бывает и
    «Имя Фамилия»: из двух слов берём то, что не похоже на фамилию."""
    words = (full_name or "").split()
    if not words:
        return ""
    if len(words) >= 3:
        return words[1]
    if len(words) == 2:
        first, second = words
        if first.lower().endswith(_SURNAME_ENDINGS) and not second.lower().endswith(_SURNAME_ENDINGS):
            return second
    return words[0]


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class OnboardingService(ChatFlowMixin):
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        messenger: Messenger,
        settings: Settings,
        cipher: WalletCipher | None,
        clock: Callable[[], datetime] = utcnow,
    ):
        self.sessions = sessions
        self.messenger = messenger
        self.settings = settings
        self.cipher = cipher
        self.clock = clock

    # ------------------------------------------------------------------ АТС

    async def create_case(
        self,
        *,
        full_name: str,
        first_name: str,
        practice_start: datetime,
        candidate_tg_username: str | None = None,
        tz: str | None = None,
        practice_lead: str = "",
        hrd: str = "",
        hr_tg_id: int | None = None,
        entity_id: int | None = None,
        org_id: int | None = None,
        created_by: int | None = None,
        from_status: bool = False,
    ) -> OnboardingCase:
        """Статус «практика назначена» (ТЗ 3.1). practice_start без tzinfo — местное время кандидата.
        from_status — карточку завёл статус АТС, а не HR ссылкой: без задач для лички (DM_ONLY_JOBS)."""
        tz = tz or self.settings.default_tz
        start_utc = sch.local_to_utc(practice_start, tz)
        now = self.clock()
        case = OnboardingCase(
            org_id=org_id,
            entity_id=entity_id,
            created_by=created_by,
            full_name=full_name,
            first_name=first_name,
            timezone=tz,
            status=CaseStatus.practice_assigned.value,
            candidate_tg_username=_norm_username(candidate_tg_username),
            link_token=TOKEN_PREFIX + secrets.token_urlsafe(16),
            practice_start_at=start_utc,
            practice_last_day=self._last_day(sch.utc_to_local(start_utc, tz), from_status),
            practice_lead=practice_lead,
            hrd=hrd,
            hr_tg_id=hr_tg_id,
        )
        async with self.sessions() as s:
            s.add(case)
            await s.flush()
            self._add_jobs(s, case.id, self._preboarding(now, start_utc, tz, from_status))
            await s.commit()
        return case

    def _preboarding(self, now: datetime, start_utc: datetime, tz: str, from_status: bool) -> list[sch.Job]:
        if not from_status:
            return sch.preboarding_jobs(now, start_utc, tz, self.settings.practice_days, self.settings.skip_weekends)
        # Мит 19.11.2026: в личку кандидату бот не пишет — каждый рабочий день практики проверка
        # вечернего отчёта в рабочем чате, утром в день старта — HR «подготовь документы и чат»,
        # в последний день без решения — сигнал HR.
        days = self.practice_days(sch.utc_to_local(start_utc, tz).date())
        jobs: list[sch.Job] = [
            ("report_check", sch.at_local(d, self.settings.report_hour, tz), {"day": d.isoformat()}) for d in days
        ]
        jobs.append(("practice_deadline", sch.at_local(days[-1], sch.NO_DECISION_HOUR, tz), {}))
        hr_at = sch.at_local(days[0], 9, tz) + timedelta(minutes=30)
        if hr_at > now:
            jobs.append(("hr_practice_start", hr_at, {}))
        return jobs

    def _last_day(self, start_local: datetime, from_status: bool) -> date:
        if from_status:
            return self.practice_days(start_local.date())[-1]
        return sch.practice_last_day(start_local.date(), self.settings.practice_days)

    # ------------------------------------------------- события по статусу АТС (мит 19.11.2026)

    async def apply_handoff_event(
        self, event: dict, *, org_id: int | None = None, created_by: int | None = None,
        hr_tg_id: int | None = None,
    ) -> OnboardingCase | None:
        """Событие из handoff.py (смена статуса в АТС): practice / transfer / stop.

        practice — новая карточка, а если практика ещё не началась и дату перенесли — перенос;
        transfer — переход в отдел (карточки не было — заводим и сразу переводим); stop —
        практика: «не прошёл», отдел: «ушёл». Повтор того же события ничего не дублирует.
        """
        kind, entity_id = event["event"], event["id"]
        async with self.sessions() as s:
            case = await s.scalar(
                select(OnboardingCase)
                .where(OnboardingCase.entity_id == entity_id, OnboardingCase.status.in_(ACTIVE_STATUSES))
                .order_by(OnboardingCase.id.desc())
                .limit(1)
            )
        full_name = event.get("full_name") or ""
        common = dict(
            full_name=full_name, first_name=first_name_of(full_name),
            candidate_tg_username=event.get("telegram"), tz=event.get("timezone") or None,
            hr_tg_id=hr_tg_id, entity_id=entity_id, org_id=org_id, created_by=created_by, from_status=True,
        )
        if kind == "practice":
            start = datetime.fromisoformat(event["practice_start_iso"])
            if case is not None and case.status in PRACTICE_STATUSES:
                return await self.reschedule_practice(case.id, start)
            case = await self.create_case(practice_start=start, practice_lead=event.get("practice_lead") or "",
                                          hrd=event.get("hrd") or "", **common)
            log.info("ONBOARDING case=%s from status entity=%s practice=%s", case.id, entity_id, start.date())
            return case
        if kind == "transfer":
            first_day = date.fromisoformat(event["first_day_iso"])
            if case is not None and case.status in DEPARTMENT_STATUSES:
                return case  # уже в отделе — повтор события
            if case is None:  # практику вели не мы (до включения бота) — заводим карточку задним числом
                start = datetime.combine(first_day, datetime.strptime(self.settings.practice_start_time, "%H:%M").time())
                case = await self.create_case(practice_start=start, **common)
            lead = await self.department_lead(org_id, event.get("department"))
            case = await self.set_status(
                case.id, CaseStatus.transferred, department=event.get("department"),
                lead_name=event.get("lead") or (lead.full_name if lead else None),
                lead_tg_id=lead.tg_id if lead else None, department_start_date=first_day)
            log.info("ONBOARDING case=%s transfer entity=%s first_day=%s", case.id, entity_id, first_day)
            return case
        if kind == "stop":
            if case is None:
                return None
            if case.status in PRACTICE_STATUSES:
                case = await self.set_status(case.id, CaseStatus.failed)
            else:
                case = await self.set_status(case.id, CaseStatus.left, reason=event.get("reason"))
            log.info("ONBOARDING case=%s stop entity=%s status=%s", case.id, entity_id, case.status)
            return case
        return case

    async def reschedule_practice(self, case_id: int, practice_start: datetime) -> OnboardingCase:
        """HR перенёс дату практики, пока она не началась: новые Loom и срок, старые задачи — отмена."""
        async with self.sessions() as s:
            case = await s.get(OnboardingCase, case_id)
            start_utc = sch.local_to_utc(practice_start, case.timezone)
            if case.status != CaseStatus.practice_assigned.value or case.practice_start_at == start_utc:
                return case
            case.practice_start_at = start_utc
            case.practice_last_day = self._last_day(practice_start, True)
            await self._cancel(s, case.id, PREBOARDING_JOBS)
            self._add_jobs(s, case.id, self._preboarding(self.clock(), start_utc, case.timezone, True))
            await s.commit()
        log.info("ONBOARDING case=%s practice moved to %s", case_id, practice_start.date())
        return case

    def invite_link(self, case: OnboardingCase) -> str:
        return f"https://t.me/{self.settings.bot_username}?start={case.link_token}"

    async def set_status(
        self,
        case_id: int,
        status: CaseStatus,
        *,
        department: str | None = None,
        lead_name: str | None = None,
        lead_tg_id: int | None = None,
        department_start_date: date | None = None,
        reason: str | None = None,
    ) -> OnboardingCase:
        async with self.sessions() as s:
            case = await s.get(OnboardingCase, case_id)
            if case is None:
                raise LookupError(f"нет карточки {case_id}")
            case.status = status.value

            if status is CaseStatus.transferred:
                case.department = department or case.department
                case.lead_name = lead_name or case.lead_name
                case.lead_tg_id = lead_tg_id or case.lead_tg_id
                start = department_start_date or self._local_now(case).date()
                case.department_start_date = start
                case.probation_end_date = sch.add_months(start, 3)
                case.awaiting = None
                await self._cancel(s, case.id, PREBOARDING_JOBS)
                reminder = self._work_time(self.clock() + timedelta(hours=24), case)
                self._add_jobs(s, case.id, [("survey_reminder", reminder, {"kind": "practice"})])
                self._add_jobs(s, case.id, sch.onboarding_jobs(start, case.timezone, self.settings.skip_weekends))
            elif status is CaseStatus.failed:
                case.awaiting = None
                await self._cancel(s, case.id, PREBOARDING_JOBS)
            elif status is CaseStatus.left:
                case.awaiting = None
                case.left_at = self.clock()
                case.left_reason = (reason or "").strip() or case.left_reason
                await self._cancel(s, case.id)
            await s.commit()

        if status is CaseStatus.transferred:
            await self._send_candidate(
                case, texts.CONGRATS.format(**self._ctx(case)), texts.survey_button("practice"), "поздравление"
            )
            await self._after_transfer(case)
        elif status is CaseStatus.failed and self.settings.send_thanks_on_fail:
            await self._send_candidate(case, texts.THANKS_ON_FAIL.format(**self._ctx(case)), None, "благодарность")
        elif status is CaseStatus.left:
            # ТЗ 4: при уходе — напоминание про exit-интервью и причину
            if case.left_reason:
                await self._signal(case, "left_with_reason", reason=case.left_reason)
            else:
                await self._signal(case, "left")
        return case

    async def decide_probation(
        self, case_id: int, decision: str, *, new_end: date | None = None, reason: str | None = None
    ) -> OnboardingCase:
        """Закрытие испытательного (ТЗ 4): остаётся / продлевается / уходит."""
        if decision == "leaves":
            return await self.set_status(case_id, CaseStatus.left, reason=reason)
        if decision not in ("stays", "extended"):
            raise ValueError(f"неизвестное решение {decision!r}")
        async with self.sessions() as s:
            case = await s.get(OnboardingCase, case_id)
            if case is None:
                raise LookupError(f"нет карточки {case_id}")
            if case.status not in DEPARTMENT_STATUSES:
                raise ValueError("испытательный срок идёт только у переведённых в отдел")
            if decision == "stays":
                case.probation_decision = "stays"
                await self._cancel_onboarding_kinds(s, case.id, {"probation_close"})
            else:
                if new_end is None or (case.probation_end_date and new_end <= case.probation_end_date):
                    raise ValueError("новая дата конца срока должна быть позже текущей")
                case.probation_decision = "extended"
                case.probation_end_date = new_end
                await self._cancel_onboarding_kinds(s, case.id, {"month3", "checkpoint_m3", "probation_close"})
                before_end = new_end - timedelta(days=14)
                if self.settings.skip_weekends:
                    before_end, new_end_day = sch.next_workday(before_end), sch.next_workday(new_end)
                else:
                    new_end_day = new_end
                jobs: list[sch.Job] = [
                    ("staff_reminder", sch.at_local(before_end, sch.STAFF_HOUR, case.timezone), {"kind": "checkpoint_m3"}),
                    ("staff_reminder", sch.at_local(new_end_day, sch.STAFF_HOUR, case.timezone), {"kind": "probation_close"}),
                ]
                if not await self._survey_done(s, case.id, "month3"):
                    jobs.append(("survey", sch.at_local(before_end, sch.SURVEY_HOUR, case.timezone), {"kind": "month3"}))
                self._add_jobs(s, case.id, jobs)
            await s.commit()
        if decision == "extended":
            await self._deliver(case, "probation_extended",
                                texts.STAFF_REMINDER["probation_extended"].format(**self._ctx(case)))
        return case

    async def _cancel_onboarding_kinds(self, s: AsyncSession, case_id: int, kinds: set[str]) -> None:
        """Отменить запланированные опросы/напоминания онбординга по их payload["kind"]."""
        jobs = await s.scalars(
            select(BotJob).where(
                BotJob.case_id == case_id,
                BotJob.status == "pending",
                BotJob.kind.in_(("survey", "staff_reminder", "survey_reminder")),
            )
        )
        for job in jobs:
            if json.loads(job.payload or "{}").get("kind") in kinds:
                job.status = "cancelled"

    # ------------------------------------------------------------ Telegram

    async def handle_start(self, tg_user_id: int, token: str) -> bool:
        """Кандидат открыл персональную ссылку: привязываем и шлём первое сообщение (ТЗ 3.3)."""
        async with self.sessions() as s:
            case = await s.scalar(select(OnboardingCase).where(OnboardingCase.link_token == token))
            if case is None or case.status not in PRACTICE_STATUSES:
                return False
            if case.candidate_tg_id is not None:
                return True  # повторный Start — первое сообщение уже было
            now = self.clock()
            case.candidate_tg_id = tg_user_id
            case.linked_at = now
            case.awaiting = "wallet"
            await self._cancel(s, case.id, {"invite_check"})
            interval = sch.retry_interval(now, case.practice_start_at, case.timezone)
            self._add_jobs(s, case.id, [("first_retry", self._work_time(now + interval, case), {"attempt": 1})])
            await s.commit()
        await self._send_candidate(
            case, texts.FIRST_MESSAGE.format(**self._ctx(case)), texts.SCRIPT_BUTTONS, "первое сообщение"
        )
        return True

    async def handle_script_answer(self, tg_user_id: int, answer: str) -> str | None:
        if answer not in texts.SCRIPT_REPLY:
            return None
        async with self.sessions() as s:
            case = await self._case_by_tg(s, tg_user_id)
            if case is None or case.script_answer is not None:
                return None
            case.script_answer = answer
            case.script_answer_at = self.clock()
            await self._cancel(s, case.id, {"first_retry", "first_no_answer"})
            await s.commit()
        if answer == "questions":
            await self._signal(case, "questions")
        elif answer == "decline":
            await self._signal(case, "declined")
        return texts.SCRIPT_REPLY[answer].format(**self._ctx(case))

    async def handle_text(self, tg_user_id: int, text: str) -> tuple[bool, str | None]:
        """(забрали ли сообщение, ответ). Не ждём от человека текста — сообщение идёт дальше
        по обычным обработчикам бота (AI-сводка и т. п.)."""
        async with self.sessions() as s:
            case = await self._case_by_tg(s, tg_user_id)
            if case is None or case.awaiting is None:
                return False, None
            if case.awaiting == "survey_text" and case.survey_kind is not None and case.survey_step is not None:
                question = SURVEYS[case.survey_kind].questions[case.survey_step]
                is_signal = question.follow_up is not None and question.follow_up in question.signal
                s.add(SurveyResponse(case_id=case.id, survey=case.survey_kind, question=case.survey_step,
                                     answer=text, is_signal=is_signal))
                kind, step = case.survey_kind, case.survey_step
                next_step = await self._advance_survey(s, case)
                await s.commit()
                if is_signal:
                    await self._signal_survey(case, kind, step, f"{question.options[question.follow_up]}: {text}")
                await self._after_advance(case, kind, next_step)
                return True, None
            if case.awaiting == "wallet" and self.cipher is None:
                case.awaiting = None  # кошельки отложены (мит 19.11.2026), ключа нет — не собираем
                await s.commit()
                return False, None
            if case.awaiting == "wallet":
                existing = await s.scalar(select(Wallet).where(Wallet.case_id == case.id))
                if existing is None:
                    s.add(Wallet(case_id=case.id, ciphertext=self.cipher.encrypt(text.strip())))
                else:
                    existing.ciphertext = self.cipher.encrypt(text.strip())
                case.awaiting = None
                await s.commit()
                return True, texts.WALLET_SAVED
        return False, None

    async def handle_loom(self, tg_user_id: int, day: str, choice: str) -> str | None:
        if choice not in texts.LOOM_REPLY:
            return None
        async with self.sessions() as s:
            case = await self._case_by_tg(s, tg_user_id)
            if case is None:
                return None
            s.add(SurveyResponse(case_id=case.id, survey="loom", question=0, answer=f"{day}:{choice}"))
            await s.commit()
        return texts.LOOM_REPLY[choice]

    async def start_survey(self, tg_user_id: int, kind: str) -> str | None:
        if kind not in SURVEYS:
            return None
        async with self.sessions() as s:
            case = await self._case_by_tg(s, tg_user_id)
            if case is None:
                return None
            if await self._survey_done(s, case.id, kind):
                return texts.SURVEY_ALREADY_DONE
            if case.survey_kind != kind or case.survey_step is None:
                case.survey_kind, case.survey_step = kind, 0
            step = case.survey_step
            case.awaiting = self._awaiting_for(kind, step)
            await s.commit()
        if kind == "practice" and step == 0:
            await self._send_candidate(case, texts.SURVEY_INTRO["practice"], None, "опрос")
        await self._ask(case, kind, step)
        return None

    async def answer_survey(self, tg_user_id: int, kind: str, step: int, option: int) -> str | None:
        async with self.sessions() as s:
            case = await self._case_by_tg(s, tg_user_id)
            if case is None:
                return None
            if case.survey_kind != kind or case.survey_step != step or case.awaiting == "survey_text":
                return texts.SURVEY_STALE
            question = SURVEYS[kind].questions[step]
            if not 0 <= option < len(question.options):
                return None
            answer = question.options[option]
            if option == question.follow_up:
                # сигнал (если положен) — когда придёт текст, вместе с ним
                s.add(SurveyResponse(case_id=case.id, survey=kind, question=step, answer=answer))
                case.awaiting = "survey_text"
                await s.commit()
                await self._send_candidate(case, texts.TELL_ONE_MESSAGE, None, "опрос")
                return None
            is_signal = option in question.signal
            s.add(SurveyResponse(case_id=case.id, survey=kind, question=step, answer=answer, is_signal=is_signal))
            next_step = await self._advance_survey(s, case)
            await s.commit()
        if is_signal:
            await self._signal_survey(case, kind, step, answer)
        await self._after_advance(case, kind, next_step)
        return None

    # --------------------------------------------------------------- воркер

    async def run_due_jobs(self, limit: int = 100) -> int:
        now = self.clock()
        async with self.sessions() as s:
            jobs = list(
                await s.scalars(
                    select(BotJob)
                    .where(BotJob.status == "pending", BotJob.run_at <= now)
                    .order_by(BotJob.run_at, BotJob.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            for job in jobs:
                job.status = "running"
                job.attempts += 1
            await s.commit()

        for job in jobs:
            status, error = "done", None
            try:
                await self._execute(job)
            except Exception as exc:  # одна сломанная задача не должна останавливать остальные
                log.exception("задача %s (%s) упала", job.id, job.kind)
                status, error = "failed", repr(exc)
            async with self.sessions() as s:
                await s.execute(
                    update(BotJob).where(BotJob.id == job.id).values(status=status, last_error=error)
                )
                await s.commit()
        return len(jobs)

    async def _execute(self, job: BotJob) -> None:
        async with self.sessions() as s:
            case = await s.get(OnboardingCase, job.case_id)
        if case is None:
            return
        payload = json.loads(job.payload) if job.payload else {}
        await getattr(self, f"_job_{job.kind}")(case, payload)

    async def _job_invite_check(self, case: OnboardingCase, payload: dict) -> None:
        if case.candidate_tg_id is None and case.status in PRACTICE_STATUSES:
            await self._signal(case, "not_opened")

    async def _job_first_retry(self, case: OnboardingCase, payload: dict) -> None:
        if case.script_answer is not None or case.status not in PRACTICE_STATUSES:
            return
        await self._send_candidate(case, texts.FIRST_RETRY.format(**self._ctx(case)), texts.SCRIPT_BUTTONS, "повтор")
        now = self.clock()
        interval = sch.retry_interval(now, case.practice_start_at, case.timezone)
        attempt = payload.get("attempt", 1)
        if attempt < self.settings.first_retry_count:
            next_job = ("first_retry", self._work_time(now + interval, case), {"attempt": attempt + 1})
        else:
            next_job = ("first_no_answer", self._work_time(now + interval, case), {})
        async with self.sessions() as s:
            self._add_jobs(s, case.id, [next_job])
            await s.commit()

    async def _job_first_no_answer(self, case: OnboardingCase, payload: dict) -> None:
        if case.script_answer is None and case.status in PRACTICE_STATUSES:
            await self._signal(case, "no_answer")

    async def _job_day_before(self, case: OnboardingCase, payload: dict) -> None:
        if case.status == CaseStatus.practice_assigned.value and case.candidate_tg_id:
            await self._send_candidate(case, texts.DAY_BEFORE.format(**self._ctx(case)), None, "напоминание за день")

    async def _job_loom(self, case: OnboardingCase, payload: dict) -> None:
        if case.status not in PRACTICE_STATUSES or case.candidate_tg_id is None:
            return
        day = payload["day"]
        await self._send_candidate(case, texts.LOOM.format(**self._ctx(case)), texts.loom_buttons(day), "напоминание о Loom")
        morning = sch.at_local(date.fromisoformat(day) + timedelta(days=1), sch.LOOM_MORNING_HOUR, case.timezone)
        async with self.sessions() as s:
            self._add_jobs(s, case.id, [("loom_morning", morning, {"day": day})])
            await s.commit()

    async def _job_loom_morning(self, case: OnboardingCase, payload: dict) -> None:
        if case.status not in PRACTICE_STATUSES:
            return
        day = payload["day"]
        async with self.sessions() as s:
            answered = await s.scalar(
                select(SurveyResponse.id).where(
                    SurveyResponse.case_id == case.id,
                    SurveyResponse.survey == "loom",
                    SurveyResponse.answer.startswith(f"{day}:"),
                )
            )
        if answered is None:  # без сигнала HR (ТЗ 3.4)
            await self._send_candidate(
                case, texts.LOOM_MORNING.format(**self._ctx(case)), texts.loom_buttons(day), "напоминание о Loom"
            )

    async def _job_practice_deadline(self, case: OnboardingCase, payload: dict) -> None:
        if case.status in PRACTICE_STATUSES:
            await self._signal(case, "no_decision")

    async def _job_survey(self, case: OnboardingCase, payload: dict) -> None:
        kind = payload["kind"]
        if case.status not in DEPARTMENT_STATUSES:
            return
        await self._send_candidate(
            case, texts.SURVEY_INTRO[kind].format(**self._ctx(case)), texts.survey_button(kind), "опрос"
        )
        async with self.sessions() as s:
            reminder = self._work_time(self.clock() + timedelta(hours=24), case)
            self._add_jobs(s, case.id, [("survey_reminder", reminder, {"kind": kind})])
            await s.commit()

    async def _job_survey_reminder(self, case: OnboardingCase, payload: dict) -> None:
        kind = payload["kind"]
        if case.status not in DEPARTMENT_STATUSES:
            return
        async with self.sessions() as s:
            if await self._survey_done(s, case.id, kind):
                return
        await self._send_candidate(  # один раз, без сигнала HR (ТЗ 3.5, 4)
            case, texts.SURVEY_REMINDER.format(**self._ctx(case)), texts.survey_button(kind), "напоминание об опросе"
        )

    async def _job_first_day_welcome(self, case: OnboardingCase, payload: dict) -> None:
        """Чек-лист первого дня, п. 1: приветствие и организационная информация около 10:00."""
        if case.status not in DEPARTMENT_STATUSES:
            return
        async with self.sessions() as s:
            no_wallet = (self.cipher is not None
                         and await s.scalar(select(Wallet.id).where(Wallet.case_id == case.id)) is None)
            if no_wallet:
                fresh = await s.get(OnboardingCase, case.id)
                if fresh.awaiting is None:
                    fresh.awaiting = "wallet"
                await s.commit()
        text = texts.FIRST_DAY_WELCOME.format(**self._ctx(case))
        if no_wallet:
            text += "\n\n" + texts.FIRST_DAY_WALLET.format(**self._ctx(case))
        await self._send_candidate(case, text, None, "приветствие первого дня")

    async def _job_staff_reminder(self, case: OnboardingCase, payload: dict) -> None:
        kind = payload["kind"]
        if case.status not in DEPARTMENT_STATUSES:
            return
        if kind == "probation_close" and case.probation_decision == "stays":
            return
        text = texts.STAFF_REMINDER[kind].format(**self._ctx(case))
        targets = texts.STAFF_TARGETS[kind]
        for who in targets:
            if who == "hr":
                await self._deliver(case, kind, text)
            elif case.lead_tg_id:
                await self._deliver(case, kind, text, [case.lead_tg_id])
            elif "hr" not in targets:
                # напоминание только для лида, а его Telegram не знаем — не теряем, отдаём HR
                await self._deliver(case, kind, f"Лиду не доставлено (не привязан Telegram):\n{text}")

    # ------------------------------------------------------------- опросы

    async def _advance_survey(self, s: AsyncSession, case: OnboardingCase) -> int | None:
        """Следующий шаг или None, если опрос пройден. Меняет case, не коммитит."""
        kind = case.survey_kind
        assert kind is not None and case.survey_step is not None
        next_step = case.survey_step + 1
        if next_step >= len(SURVEYS[kind].questions):
            s.add(SurveyResponse(case_id=case.id, survey=kind, question=DONE_MARK, answer="done"))
            case.survey_kind = case.survey_step = case.awaiting = None
            return None
        case.survey_step = next_step
        case.awaiting = self._awaiting_for(kind, next_step)
        return next_step

    async def _after_advance(self, case: OnboardingCase, kind: str, next_step: int | None) -> None:
        if next_step is None:
            await self._send_candidate(case, texts.SURVEY_DONE, None, "опрос")
        else:
            await self._ask(case, kind, next_step)

    async def _ask(self, case: OnboardingCase, kind: str, step: int) -> None:
        question = SURVEYS[kind].questions[step]
        buttons: Buttons | None = None
        if question.options:
            buttons = [[(opt, f"sv:{kind}:{step}:{i}")] for i, opt in enumerate(question.options)]
        await self._send_candidate(case, f"{step + 1}. {question.text}", buttons, "опрос")

    @staticmethod
    def _awaiting_for(kind: str, step: int) -> str | None:
        return None if SURVEYS[kind].questions[step].options else "survey_text"

    @staticmethod
    async def _survey_done(s: AsyncSession, case_id: int, kind: str) -> bool:
        found = await s.scalar(
            select(SurveyResponse.id).where(
                SurveyResponse.case_id == case_id,
                SurveyResponse.survey == kind,
                SurveyResponse.question == DONE_MARK,
            )
        )
        return found is not None

    # ------------------------------------------------- отправка и сигналы

    async def _send_candidate(self, case: OnboardingCase, text: str, buttons: Buttons | None, what: str) -> bool:
        error: SendError | None = None
        if case.candidate_tg_id is not None:
            try:
                await self.messenger.send(case.candidate_tg_id, text, buttons)
                return True
            except SendError as exc:
                error = exc
        # Мит 19.11.2026: кандидат мог ни разу не открыть бота — тогда в личку нельзя, пишем в его
        # рабочий чат, а опрос даём ссылкой в личку (отвечать при всех незачем).
        chat_id = self._candidate_chat(case)
        if chat_id is not None:
            try:
                await self.messenger.send(chat_id, text, self._chat_buttons(case, buttons))
                return True
            except SendError as exc:
                error = exc
        if error is not None:  # ТЗ, вопрос 3: HR должна видеть ошибку, а не тихий сбой
            await self._signal(case, "send_failed", what=what, error=str(error))
        return False

    async def _signal(self, case: OnboardingCase, kind: str, **extra: str) -> None:
        text = texts.SIGNAL[kind].format(**self._ctx(case), **extra)
        await self._deliver(case, kind, text)

    async def _signal_survey(self, case: OnboardingCase, kind: str, step: int, answer: str) -> None:
        survey = SURVEYS[kind]
        await self._signal(
            case, "survey", survey=survey.title, question=survey.questions[step].text, answer=answer
        )

    async def _deliver(
        self, case: OnboardingCase, kind: str, text: str, targets: list[int | None] | None = None
    ) -> None:
        """Лично HR из карточки; не вышло — в запасной HR-чат. Всё пишется в журнал."""
        if targets is None:
            targets = [case.hr_tg_id, self.settings.hr_fallback_chat_id]
        delivered_to = None
        for chat_id in targets:
            if not chat_id:
                continue
            try:
                await self.messenger.send(chat_id, text)
                delivered_to = chat_id
                break
            except SendError as exc:
                log.warning("сигнал %s в %s не доставлен: %s", kind, chat_id, exc)
        async with self.sessions() as s:
            s.add(Signal(case_id=case.id, kind=kind, text=text, delivered_to=delivered_to))
            await s.commit()
        if self.settings.hr_events_chat_id not in targets:
            await self._events(text)

    # ------------------------------------------------------------ helpers

    def _add_jobs(self, s: AsyncSession, case_id: int, jobs: Iterable[sch.Job]) -> None:
        for kind, run_at, payload in jobs:
            s.add(BotJob(case_id=case_id, kind=kind, run_at=run_at, payload=json.dumps(payload) if payload else None))

    @staticmethod
    async def _cancel(s: AsyncSession, case_id: int, kinds: set[str] | None = None) -> None:
        stmt = update(BotJob).where(BotJob.case_id == case_id, BotJob.status == "pending")
        if kinds is not None:
            stmt = stmt.where(BotJob.kind.in_(kinds))
        await s.execute(stmt.values(status="cancelled"))

    @staticmethod
    async def _case_by_tg(s: AsyncSession, tg_user_id: int) -> OnboardingCase | None:
        return await s.scalar(
            select(OnboardingCase)
            .where(OnboardingCase.candidate_tg_id == tg_user_id, OnboardingCase.status != CaseStatus.left.value)
            .order_by(OnboardingCase.id.desc())
            .limit(1)
        )

    @staticmethod
    async def _practice_case(s: AsyncSession, user_id: int, username: str | None) -> OnboardingCase | None:
        by_id = OnboardingCase.candidate_tg_id == user_id
        cond = by_id
        if username:
            cond = by_id | (OnboardingCase.candidate_tg_username == _norm_username(username))
        return await s.scalar(
            select(OnboardingCase)
            .where(cond, OnboardingCase.status.in_(PRACTICE_STATUSES))
            .order_by(OnboardingCase.id.desc())
            .limit(1)
        )

    def _work_time(self, run_at: datetime, case: OnboardingCase) -> datetime:
        return sch.within_working_hours(run_at, case.timezone, self.settings.skip_weekends)

    def _local_now(self, case: OnboardingCase) -> datetime:
        return sch.utc_to_local(self.clock(), case.timezone)

    def _ctx(self, case: OnboardingCase) -> dict[str, str]:
        start = sch.utc_to_local(case.practice_start_at, case.timezone)
        return {
            "name": case.first_name,
            "full": case.full_name,
            "date": start.strftime("%d.%m"),
            "time": start.strftime("%H:%M"),
            "last_day": case.practice_last_day.strftime("%d.%m"),
            "landing_url": self.settings.landing_url,
            "materials_url": self.settings.materials_url,
            "wallet_guide_url": self.settings.wallet_guide_url,
            "platform_invite_url": self.settings.platform_invite_url,
            "practice_lead": case.practice_lead,
            "hrd": case.hrd,
            "department": case.department or "",
            "lead": case.lead_name or "",
            "probation_end": case.probation_end_date.strftime("%d.%m") if case.probation_end_date else "",
        }


def _norm_username(username: str | None) -> str | None:
    return username.lstrip("@").lower() if username else None
