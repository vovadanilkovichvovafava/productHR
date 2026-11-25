"""Бот в рабочих чатах, лиды отделов, блокер, смены HR — мит 19.11.2026 (Маша, Владимир).

ИИ-агентов на HR-аккаунтах отложили: бот сам пишет в рабочие чаты, куда его добавляет HR
(чаты бот создавать не может — Bot API 10.4 такого метода не даёт). Порядок:

- HR создаёт рабочий чат практики и добавляет бота. Бот понимает, чей чат: по тому, кто добавил
  (HR кандидата, ментор, лид), и по названию чата; не понял — спрашивает кнопками «для кого».
- Кандидата в чате бот узнаёт по нику из карточки, по номеру из «Старт» или по сообщению.
  Список участников бот получить не может — поэтому «Старт» в приветствии.
- Вечерний отчёт — сообщение кандидата с #вечерний_отчёт (или ссылкой на Loom). Не прислал к
  report_hour — напоминание в чат, ещё через report_grace_minutes — тег ментора.
- Переход в отдел: прощание в чате практики, лиду в личку «создай чат отдела», бот в чате
  отдела поздравляет. Лиды — /lead в личке, подтверждает владелец/админ HR.
- #блокер в рабочем чате — HR кандидата (и ментору в чате) + общий чат HR.
- Смена HR у кандидата — новому и прежнему HR в Telegram со ссылкой на карточку.

Миксин к OnboardingService: пользуется его sessions/messenger/settings/clock и _deliver.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, timedelta

from sqlalchemy import func, or_, select

from api.models.database import (
    BoardDepartment,
    Department,
    DepartmentMember,
    DeptRole,
    Entity,
    OrgMember,
    OrgRole,
    User,
)

from . import schedule as sch
from . import texts
from .messenger import Buttons, SendError
from .models import (
    DEPARTMENT_STATUSES,
    PRACTICE_STATUSES,
    CaseStatus,
    DepartmentLead,
    OnboardingCase,
    Signal,
    SurveyResponse,
)

log = logging.getLogger(__name__)

REPORT_SURVEY = "report"  # SurveyResponse.survey: answer = день практики (ISO), по которому пришёл отчёт
BLOCKER_CMD_RE = re.compile(r"^/blocker(?:@\w+)?(?:\s+(.*))?$", re.IGNORECASE | re.DOTALL)
BLOCKER_WAIT = timedelta(minutes=15)  # сколько ждём описание после /blocker без текста
REPORT_RE = re.compile(r"#\s*(вечерн\w*_?отч[её]т|отч[её]т)|loom\.com/", re.IGNORECASE)
# Код опроса в ссылке t.me/<бот>?start=obs_<код><токен> (у start ≤ 64 знаков, только [A-Za-z0-9_-])
SURVEY_CODES = {"practice": "p", "first_day": "f", "week": "w", "month1": "1", "month2": "2", "month3": "3"}
SURVEY_BY_CODE = {v: k for k, v in SURVEY_CODES.items()}
SURVEY_LINK_PREFIX = "obs_"
HR_CHANGE_SEEN_MAX = 2000
BIND_WINDOW_BEFORE, BIND_WINDOW_AFTER = timedelta(days=1), timedelta(days=4)
DEPT_BIND_WINDOW = timedelta(days=10)


def _norm(username: str | None) -> str | None:
    return username.lstrip("@").lower() if username else None


class ChatFlowMixin:
    # ------------------------------------------------------------------ рабочий чат

    async def handle_bot_added(self, chat_id: int, adder_tg_id: int | None, title: str = "") -> bool:
        """Бота добавили в группу. True — бот понял, что это чат практики/отдела, и написал в него."""
        if adder_tg_id is None:
            return False
        async with self.sessions() as s:
            if await self._case_for_chat(s, chat_id) is not None:
                return False  # бота добавили повторно — чат уже привязан
            practice = await self._unbound_practice_cases(s)
            dept = await self._unbound_dept_cases(s)
            staff = await self._is_staff(s, adder_tg_id)
        # Кто добавил: HR кандидата / лид отдела — его люди; иначе — все (только если добавил сотрудник:
        # бот сидит и в других чатах компании, писать туда «для кого чат» незачем).
        if staff and title:
            # Прод 24.11.2026: лид R&D создал «Практика Тестбот Владимир» для кандидата, у которого он не HR, —
            # бот выбирал только из «своих» карточек и привязал чат к чужому отделу. Полное имя в названии
            # главнее того, кто добавил.
            named = _named_in_title(practice + dept, title)
            if len(named) == 1:
                await self._bind(chat_id, named[0].id)
                return True
        mine_p = [c for c in practice if c.hr_tg_id == adder_tg_id]
        mine_d = [c for c in dept if adder_tg_id in self.lead_ids(c) or c.hr_tg_id == adder_tg_id]
        options = mine_p + mine_d
        if not options:
            if not staff:
                return False
            options = practice + dept
        if not options:
            return False
        if len(options) > 1 and title:
            # Прод 20.11.2026: «Практика Тестбот Повтор» при кандидатах «Тестбот Повтор» и «Тестбот
            # Безчата» — общее слово есть у обоих, решает число совпавших слов
            scores = {c.id: _title_score(c, title) for c in options}
            best = max(scores.values())
            by_title = [c for c in options if best and scores[c.id] == best]
            if len(by_title) == 1:
                options = by_title
        if len(options) == 1:
            await self._bind(chat_id, options[0].id)
            return True
        dept_only = all(c.status in DEPARTMENT_STATUSES for c in options)
        buttons: Buttons = [[(c.full_name, f"pchat:{c.id}")] for c in options[:10]]
        try:
            ask = texts.WHICH_CHAT_DEPT if dept_only else (texts.SHEET_WHICH_CHAT if self.sheet else texts.WHICH_CHAT)
            await self.messenger.send(chat_id, ask, buttons)
        except SendError as exc:
            log.warning("чат %s: %s", chat_id, exc)
        return True

    async def bind_chat(self, chat_id: int, case_id: int, by_tg_id: int) -> str:
        """Кнопка «для кого этот чат». Возвращает текст ответа на нажатие."""
        async with self.sessions() as s:
            if not await self._is_staff(s, by_tg_id):
                return texts.CHAT_BIND_NOT_STAFF
            case = await s.get(OnboardingCase, case_id)
        if case is None:
            return texts.LEAD_ALREADY
        await self._bind(chat_id, case_id)
        return texts.CHAT_BOUND.format(full=case.full_name)

    async def _bind(self, chat_id: int, case_id: int) -> None:
        async with self.sessions() as s:
            case = await s.get(OnboardingCase, case_id)
            dept = case.status in DEPARTMENT_STATUSES
            if dept:
                case.dept_chat_id = chat_id
            else:
                case.work_chat_id = chat_id
            await s.commit()
        log.info("ONBOARDING chat bound case=%s chat=%s %s", case_id, chat_id, "dept" if dept else "practice")
        ctx = self._ctx(case)
        if dept:
            text = texts.dept_welcome(self._mention(case), case.department or "", _ddmm(case.department_start_date),
                                      _ddmm(case.probation_end_date), case.lead_name or "")
            buttons = None
        elif self.sheet:  # схема Маши: правила и инвайт шлёт HR, бот только говорит, что подключён
            text, buttons = texts.SHEET_CHAT_CONNECTED.format(**ctx), None
        else:
            text, buttons = texts.WORK_CHAT_HELLO.format(**ctx, mention=self._mention(case)), texts.START_BUTTON
            if case.status == CaseStatus.practice_running.value:
                buttons = None  # «Старт» уже нажат в другом чате
        text = re.sub(r" {2,}", " ", text)  # нет руководителя практики в карточке — без двойного пробела
        try:
            await self.messenger.send(chat_id, text, buttons)
        except SendError as exc:
            log.warning("чат %s: %s", chat_id, exc)

    async def handle_members_joined(self, chat_id: int, members) -> None:
        """В группу пришли люди. Кандидат из карточки — приветствие с «Старт» (и привязка чата)."""
        for user_id, username in members:
            async with self.sessions() as s:
                case = await self._case_for_chat(s, chat_id)
                if case is not None:
                    if not _is_candidate(case, user_id, username):
                        continue
                    if case.candidate_tg_id is None:
                        case.candidate_tg_id = user_id
                        await s.commit()
                else:
                    case = await self._practice_case(s, user_id, username)
                    if case is None or case.status != CaseStatus.practice_assigned.value:
                        continue
                    if case.work_chat_id is None:
                        case.work_chat_id = chat_id
                        await s.commit()
            if case.status in DEPARTMENT_STATUSES:
                continue  # чат отдела: поздравление ушло при привязке
            if case.status != CaseStatus.practice_assigned.value or self.sheet:
                continue  # схема Маши: кандидата приветствует HR
            try:
                await self.messenger.send(chat_id, texts.WORK_CHAT_WELCOME.format(**self._ctx(case)),
                                          texts.START_BUTTON)
            except SendError as exc:
                log.warning("рабочий чат %s: %s", chat_id, exc)

    async def handle_practice_start(self, chat_id: int, user_id: int, username: str | None) -> str | None:
        """Кандидат нажал «Старт» в рабочем чате → правила и инвайт (ТЗ 3.1). Возвращает текст алерта."""
        async with self.sessions() as s:
            bound = await self._case_for_chat(s, chat_id)
            if bound is not None:
                # Чат уже привязан — «Старт» относится к его кандидату. Прод 20.11.2026: у двух карточек
                # один ник, и «Старт» в чате одной засчитывался другой (более новой).
                case = None
                if bound.status in PRACTICE_STATUSES:
                    if _is_candidate(bound, user_id, username):
                        case = bound
                    elif bound.candidate_tg_id is None and not await self._is_staff(s, user_id):
                        case = bound  # ник в карточке с ошибкой: нажал не сотрудник — это кандидат
            else:
                case = await self._practice_case(s, user_id, username)
            if case is None:
                return texts.START_NOT_CANDIDATE
            if case.status != CaseStatus.practice_assigned.value:
                return None  # уже стартовал
            case.candidate_tg_id = case.candidate_tg_id or user_id
            case.candidate_tg_username = case.candidate_tg_username or _norm(username)
            case.status = CaseStatus.practice_running.value
            case.work_chat_id = case.work_chat_id or chat_id
            case.practice_started_at = self.clock()
            await s.commit()
        try:
            await self.messenger.send(chat_id, texts.practice_start(self._ctx(case)))
        except SendError as exc:
            await self._signal(case, "send_failed", what="правила практики", error=str(exc))
        log.info("ONBOARDING practice started case=%s chat=%s", case.id, chat_id)
        return None

    async def handle_group_text(
        self, chat_id: int, user_id: int, username: str | None, author: str, text: str,
    ) -> str | None:
        """Сообщение в группе. Ответ бота в чат или None. Ловит #блокер и вечерний отчёт кандидата."""
        if not text:
            return None
        async with self.sessions() as s:
            case = await self._case_for_chat(s, chat_id)
            if case is None:
                return None
            candidate = _is_candidate(case, user_id, username)
            if candidate and case.candidate_tg_id is None:
                case.candidate_tg_id = user_id
                await s.commit()
        # Мит 24.11.2026: блокер — командой /blocker (её видно в меню команд), #блокер тоже работает.
        command = BLOCKER_CMD_RE.match(text.strip())
        if command:
            body = (command.group(1) or "").strip()
            if not body:
                self._pending_blockers[(chat_id, user_id)] = self.clock()
                return texts.BLOCKER_ASK
            return await self._blocker(case, chat_id, author, body)
        asked = self._pending_blockers.pop((chat_id, user_id), None)
        if asked is not None and self.clock() - asked <= BLOCKER_WAIT:
            return await self._blocker(case, chat_id, author, text)
        low = text.lower()
        if any(tag in low for tag in texts.BLOCKER_TAGS):
            return await self._blocker(case, chat_id, author, text)
        if candidate and case.status in PRACTICE_STATUSES and REPORT_RE.search(text):
            day = self._local_now(case).date().isoformat()
            async with self.sessions() as s:
                if not await self._reported(s, case.id, day):
                    s.add(SurveyResponse(case_id=case.id, survey=REPORT_SURVEY, question=0, answer=day))
                    await s.commit()
            log.info("ONBOARDING report case=%s day=%s", case.id, day)
            return texts.REPORT_ACCEPTED
        return None

    async def _blocker(self, case: OnboardingCase, chat_id: int, author: str, text: str) -> str:
        where = "чат отдела" if chat_id == case.dept_chat_id else "рабочий чат практики"
        await self._deliver(case, "blocker", texts.BLOCKER_TO_HR.format(
            full=case.full_name, where=where, author=author, text=text.strip()))
        mentor = ""
        if chat_id == case.work_chat_id and case.status in PRACTICE_STATUSES:
            tag = await self._mentor_tag(case)
            if tag:
                mentor = f" и ментору {tag}"
        log.info("ONBOARDING blocker case=%s chat=%s", case.id, chat_id)
        return texts.BLOCKER_FORWARDED.format(mentor=mentor)

    # ------------------------------------------------------------- вечерний отчёт

    async def _job_report_check(self, case: OnboardingCase, payload: dict) -> None:
        if case.status not in PRACTICE_STATUSES:
            return
        day = payload["day"]
        async with self.sessions() as s:
            if await self._reported(s, case.id, day):
                return
            no_chat_told = await s.scalar(select(Signal.id).where(
                Signal.case_id == case.id, Signal.kind == "no_work_chat").limit(1))
        if case.work_chat_id is None:
            if no_chat_told is None:
                await self._signal(case, "no_work_chat")
            return
        try:
            await self.messenger.send(case.work_chat_id, texts.REPORT_REMINDER.format(mention=self._mention(case)))
        except SendError as exc:
            await self._signal(case, "send_failed", what="напоминание про вечерний отчёт", error=str(exc))
            return
        later = self.clock() + timedelta(minutes=self.settings.report_grace_minutes)
        async with self.sessions() as s:
            self._add_jobs(s, case.id, [("report_escalate", later, {"day": day})])
            await s.commit()

    async def _job_report_escalate(self, case: OnboardingCase, payload: dict) -> None:
        if case.status not in PRACTICE_STATUSES or case.work_chat_id is None:
            return
        day = payload["day"]
        async with self.sessions() as s:
            if await self._reported(s, case.id, day):
                return
        mentor = await self._mentor_tag(case) or "Руководитель практики"
        text = texts.REPORT_LATE.format(mentor=mentor, full=case.full_name, day=_ddmm(date.fromisoformat(day)))
        try:
            await self.messenger.send(case.work_chat_id, text)
        except SendError as exc:
            log.warning("рабочий чат %s: %s", case.work_chat_id, exc)
        await self._events(text)

    async def _job_hr_practice_start(self, case: OnboardingCase, payload: dict) -> None:
        if case.status not in PRACTICE_STATUSES:
            return
        bot = f"@{self.settings.bot_username}" if self.settings.bot_username else "бота"
        if self.sheet:  # уведомление 3, за час до старта
            tpl = texts.SHEET_PRACTICE_START_CHAT_READY if case.work_chat_id else texts.SHEET_PRACTICE_START
            await self._deliver(case, "hr_practice_start", tpl.format(**self._ctx(case)))
            return
        tpl = texts.HR_PRACTICE_START_CHAT_READY if case.work_chat_id else texts.HR_PRACTICE_START
        await self._deliver(case, "hr_practice_start", tpl.format(full=case.full_name, bot=bot))

    async def _job_loom_chat(self, case: OnboardingCase, payload: dict) -> None:
        """Схема Маши, уведомление 4: каждый день практики в 20:00 — Loom в рабочий чат. HR не уведомляется."""
        if case.status not in PRACTICE_STATUSES:
            return
        day = payload["day"]
        async with self.sessions() as s:
            if await self._reported(s, case.id, day):
                return  # отчёт за день уже прислали — напоминать незачем
            no_chat_told = await s.scalar(select(Signal.id).where(
                Signal.case_id == case.id, Signal.kind == "no_work_chat").limit(1))
        if case.work_chat_id is None:
            if no_chat_told is None:
                await self._signal(case, "no_work_chat")
            return
        try:
            await self.messenger.send(case.work_chat_id, texts.SHEET_LOOM.format(mention=self._mention(case)),
                                      texts.sheet_loom_buttons(day))
        except SendError as exc:
            await self._signal(case, "send_failed", what="напоминание про Loom", error=str(exc))

    async def handle_loom_chat(self, chat_id: int, user_id: int, username: str | None,
                               day: str, choice: str) -> tuple[str | None, str | None]:
        """Кнопка под Loom в рабочем чате. (ответ в чат, всплывающее предупреждение)."""
        if choice not in texts.SHEET_LOOM_REPLY:
            return None, None
        async with self.sessions() as s:
            case = await self._case_for_chat(s, chat_id)
            if case is None:
                return None, None
            if not _is_candidate(case, user_id, username):
                if case.candidate_tg_id is not None or await self._is_staff(s, user_id):
                    return None, texts.SHEET_LOOM_NOT_CANDIDATE
                case.candidate_tg_id = user_id  # ник в карточке с ошибкой: нажал не сотрудник — кандидат
            elif case.candidate_tg_id is None:
                case.candidate_tg_id = user_id
            s.add(SurveyResponse(case_id=case.id, survey="loom", question=0, answer=f"{day}:{choice}"))
            if choice == "sent" and not await self._reported(s, case.id, day):
                s.add(SurveyResponse(case_id=case.id, survey=REPORT_SURVEY, question=0, answer=day))
            await s.commit()
        log.info("ONBOARDING loom case=%s day=%s %s", case.id, day, choice)
        return texts.SHEET_LOOM_REPLY[choice], None

    @staticmethod
    async def _reported(s, case_id: int, day: str) -> bool:
        return await s.scalar(select(SurveyResponse.id).where(
            SurveyResponse.case_id == case_id, SurveyResponse.survey == REPORT_SURVEY,
            SurveyResponse.answer == day).limit(1)) is not None

    def practice_days(self, start_day: date) -> list[date]:
        """Дни практики: practice_days рабочих дней (выходные пропускаем, если skip_weekends)."""
        days, day = [], start_day
        while len(days) < max(self.settings.practice_days, 1):
            if not (self.settings.skip_weekends and day.weekday() >= 5):
                days.append(day)
            day += timedelta(days=1)
        return days

    # ---------------------------------------------------------- переход в отдел и лиды

    async def department_lead(self, org_id: int | None, department: str | None) -> DepartmentLead | None:
        if not department:
            return None
        async with self.sessions() as s:
            q = select(DepartmentLead).where(DepartmentLead.status == "confirmed")
            if org_id is not None:
                q = q.where(or_(DepartmentLead.org_id == org_id, DepartmentLead.org_id.is_(None)))
            leads = (await s.scalars(q.order_by(DepartmentLead.id.desc()))).all()
        want = department.strip().lower()  # сравнение в Python: lower() в SQLite не знает кириллицы
        return next((lead for lead in leads if lead.department.strip().lower() == want), None)

    async def org_department_leads(self, org_id: int | None, department: str | None) -> list[tuple[str, int | None]]:
        """Лиды отдела «Штата» из оргструктуры: [(имя, telegram_id или None)].

        Отдел доски связан с отделом «Управление → Отделы» (`org_department_id`); у команды
        без своей связи берётся связь её песочницы. Связи нет или лидов нет — пусто, тогда
        бот ищет лида, подтверждённого через /lead.
        """
        if not department:
            return []
        want = department.strip().lower()
        async with self.sessions() as s:
            q = select(BoardDepartment)
            if org_id is not None:
                q = q.where(BoardDepartment.org_id == org_id)
            depts = (await s.scalars(q)).all()
            by_id = {d.id: d for d in depts}
            board = next((d for d in depts if (d.name or "").strip().lower() == want), None)
            if board is None:
                return []
            link = board.org_department_id
            if link is None and board.parent_id in by_id:
                link = by_id[board.parent_id].org_department_id
            if link is None:
                return []
            rows = (await s.execute(
                select(User.name, User.telegram_id)
                .join(DepartmentMember, DepartmentMember.user_id == User.id)
                .where(DepartmentMember.department_id == link, DepartmentMember.role == DeptRole.lead)
                .order_by(DepartmentMember.id)
            )).all()
        return [(name or "", tg) for name, tg in rows]

    async def transfer_leads(
        self, org_id: int | None, department: str | None,
    ) -> tuple[str | None, list[int] | None]:
        """Кто лид отдела для бота: (имена через запятую, telegram_id).

        Сначала оргструктура: тогда список есть всегда, пустой — лиды есть, но без Telegram.
        Связи с оргструктурой нет — лид, подтверждённый через /lead, или (None, None).
        """
        from_org = await self.org_department_leads(org_id, department)
        if from_org:
            names = ", ".join(n for n, _ in from_org if n) or None
            return names, list(dict.fromkeys(tg for _, tg in from_org if tg))
        lead = await self.department_lead(org_id, department)
        if lead is None:
            return None, None
        return lead.full_name, [lead.tg_id]

    async def _lead_name_by_tg(self, tg_id: int) -> str:
        async with self.sessions() as s:
            name = (await s.scalars(select(User.name).where(User.telegram_id == tg_id))).first()
        return name or ""

    @staticmethod
    def lead_ids(case: OnboardingCase) -> list[int]:
        ids = list(case.lead_tg_ids or [])
        if case.lead_tg_id and case.lead_tg_id not in ids:
            ids.insert(0, case.lead_tg_id)
        return ids

    async def _after_transfer(self, case: OnboardingCase) -> None:
        """Чат практики — прощание; лиду — «создай чат отдела»; лида нет — сигнал HR."""
        ctx = self._ctx(case)
        if case.work_chat_id and not self.sheet:  # схема Маши: решение в чате пишет руководитель практики
            try:
                await self.messenger.send(case.work_chat_id, texts.PRACTICE_DONE.format(**ctx))
            except SendError as exc:
                log.warning("рабочий чат %s: %s", case.work_chat_id, exc)
        if not self.settings.handoff_to_bot:
            return
        await self._signal(case, "transferred")  # 6: HR поздравляет, шлёт опрос, передаёт кошелёк
        link = self.card_link(case)
        lead_text = texts.SHEET_LEAD_TRANSFER.format(**ctx)  # Л2
        if link:
            lead_text += "\n" + texts.CARD_LINK.format(link=link)
        leads = self.lead_ids(case)
        for tg_id in leads:
            try:
                await self.messenger.send(tg_id, lead_text)
            except SendError as exc:
                # Прод 23.11.2026: у Владимира к staffwise привязан старый Telegram, «chat not found»,
                # а HR читал «проверь Telegram в карточке» — в карточке кандидата всё было верно.
                log.warning("лиду %s о новом сотруднике case=%s: %s", tg_id, case.id, exc)
                name = await self._lead_name_by_tg(tg_id)  # имена только в именительном падеже
                await self._signal(case, "lead_send_failed", lead_who=f"Лид {name}" if name else "Лид отдела",
                                   lead_short=name or "лид")
        if not leads:
            # лиды в оргструктуре есть, но без Telegram — иначе бот вообще не знает лида
            await self._signal(case, "lead_no_tg" if case.lead_tg_ids == [] and case.lead_name else "no_lead")

    async def lead_departments(self) -> list[BoardDepartment]:
        async with self.sessions() as s:
            rows = (await s.scalars(
                select(BoardDepartment).where(
                    func.coalesce(BoardDepartment.kind, "team") != "sandbox",
                    BoardDepartment.hidden_at.is_(None),
                ).order_by(BoardDepartment.name)
            )).all()
        return list(rows)

    async def request_lead(self, tg_id: int, username: str | None, full_name: str, department_id: int) -> str:
        """Лид выбрал отдел → запрос владельцам/админам HR с кнопками. Возвращает ответ лиду."""
        async with self.sessions() as s:
            dept = await s.get(BoardDepartment, department_id)
            if dept is None:
                return texts.LEAD_NO_DEPARTMENTS
            approvers = await self._approvers(s, dept.org_id)
            if not approvers:
                return texts.LEAD_NO_APPROVERS
            lead = DepartmentLead(org_id=dept.org_id, department=dept.name, tg_id=tg_id,
                                  username=_norm(username), full_name=full_name, status="pending")
            s.add(lead)
            await s.commit()
        who = full_name + (f" (@{_norm(username)})" if username else "")
        text = texts.LEAD_REQUEST.format(who=who, department=dept.name)
        buttons: Buttons = [[("Да, лид", f"leadok:{lead.id}"), ("Нет", f"leadno:{lead.id}")]]
        for chat_id in approvers:
            try:
                await self.messenger.send(chat_id, text, buttons)
            except SendError as exc:
                log.warning("запрос лида %s → %s: %s", lead.id, chat_id, exc)
        log.info("ONBOARDING lead request id=%s dept=%s tg=%s", lead.id, dept.name, tg_id)
        return texts.LEAD_REQUEST_SENT

    async def decide_lead(self, lead_id: int, approver_tg_id: int, ok: bool) -> str:
        async with self.sessions() as s:
            lead = await s.get(DepartmentLead, lead_id)
            if lead is None or lead.status != "pending":
                return texts.LEAD_ALREADY
            if approver_tg_id not in await self._approvers(s, lead.org_id):
                return texts.LEAD_NOT_ADMIN
            lead.status = "confirmed" if ok else "rejected"
            lead.decided_by_tg, lead.decided_at = approver_tg_id, self.clock()
            if ok:
                others = (await s.scalars(select(DepartmentLead).where(
                    DepartmentLead.id != lead.id, DepartmentLead.status == "confirmed"))).all()
                for other in others:
                    if other.department.strip().lower() == lead.department.strip().lower():
                        other.status = "replaced"
            await s.commit()
        try:
            await self.messenger.send(lead.tg_id, (texts.LEAD_CONFIRMED if ok else texts.LEAD_REJECTED)
                                      .format(department=lead.department))
        except SendError as exc:
            log.warning("лиду %s: %s", lead.tg_id, exc)
        who = lead.full_name or f"@{lead.username}"
        log.info("ONBOARDING lead %s id=%s dept=%s", "confirmed" if ok else "rejected", lead.id, lead.department)
        decided = texts.LEAD_DECIDED["ok" if ok else "no"].format(who=who, department=lead.department)
        await self._events(decided)
        return decided

    @staticmethod
    async def _approvers(s, org_id: int | None) -> list[int]:
        """Telegram владельцев и админов HR организации (кто подтверждает лида)."""
        q = (select(User.telegram_id).join(OrgMember, OrgMember.user_id == User.id)
             .where(OrgMember.role.in_([OrgRole.owner, OrgRole.admin]), User.telegram_id.is_not(None)))
        if org_id is not None:
            q = q.where(OrgMember.org_id == org_id)
        return list(dict.fromkeys((await s.scalars(q)).all()))

    # ------------------------------------------------------------- опрос по ссылке

    def survey_link(self, case: OnboardingCase, kind: str) -> str | None:
        code = SURVEY_CODES.get(kind)
        if not code or not self.settings.bot_username:
            return None
        token = case.link_token.removeprefix("ob_")
        return f"https://t.me/{self.settings.bot_username}?start={SURVEY_LINK_PREFIX}{code}{token}"

    async def handle_survey_link(self, tg_user_id: int, payload: str) -> bool:
        """`/start obs_<код><токен>` — кандидат открыл опрос из рабочего чата: дальше в личке."""
        body = payload.removeprefix(SURVEY_LINK_PREFIX)
        kind = SURVEY_BY_CODE.get(body[:1])
        if kind is None:
            return False
        async with self.sessions() as s:
            case = await s.scalar(select(OnboardingCase).where(OnboardingCase.link_token == "ob_" + body[1:]))
            if case is None or (case.candidate_tg_id not in (None, tg_user_id)):
                return False
            if case.candidate_tg_id is None:
                case.candidate_tg_id = tg_user_id
                await s.commit()
        await self.start_survey(tg_user_id, kind)
        return True

    def _chat_buttons(self, case: OnboardingCase, buttons: Buttons | None) -> Buttons | None:
        """Кнопки для сообщения кандидату в группе: опрос — ссылкой в личку (отвечать при всех не надо),
        остальные кнопки в группе не имеют смысла."""
        out: Buttons = []
        for row in buttons or []:
            for label, data in row:
                if data.startswith("survey:"):
                    link = self.survey_link(case, data.removeprefix("survey:"))
                    if link:
                        out.append([(label, link)])
        return out or None

    def _candidate_chat(self, case: OnboardingCase) -> int | None:
        if case.status in DEPARTMENT_STATUSES and case.dept_chat_id:
            return case.dept_chat_id
        return case.work_chat_id or case.dept_chat_id

    # ------------------------------------------------------------- предпросмотр схемы

    preview_pause = 3.1  # Bot API: в одну группу не больше 20 сообщений в минуту

    async def preview_sheet(self, chat_id: int, user_id: int, username: str | None = None) -> str | None:
        """/preview в группе: все уведомления схемы Маши по очереди в этот чат, на примере последней
        карточки бота (своей, если ты её HR). Только сотрудникам. Ответ в чат или None."""
        async with self.sessions() as s:
            if not await self._is_staff(s, user_id):
                return None
            bound = await self._case_for_chat(s, chat_id)
            case = await self._example_case(s, user_id)
        if bound is not None and await self._candidate_in_chat(chat_id, bound, user_id, username):
            return texts.DEMO_CANDIDATE_HERE.format(cmd="/preview")
        if case is None:
            return texts.PREVIEW_NO_CASE
        items = self.sheet_preview_messages(case)
        task = asyncio.create_task(self._send_preview(chat_id, items))
        self._preview_tasks = getattr(self, "_preview_tasks", set())
        self._preview_tasks.add(task)
        task.add_done_callback(self._preview_tasks.discard)
        log.info("ONBOARDING preview chat=%s case=%s n=%s", chat_id, case.id, len(items))
        return texts.PREVIEW_START.format(full=case.full_name, n=texts.messages_count(len(items)))

    @staticmethod
    async def _example_case(s, user_id: int) -> OnboardingCase | None:
        """Карточка для примера. Прод 25.11.2026: пример взялся с удалённой тестовой карточки — без
        ссылки на карточку. Берём живую: с карточкой в АТС и в работе; своя (ты HR) — раньше чужой."""
        live = select(OnboardingCase).where(OnboardingCase.entity_id.is_not(None),
                                            OnboardingCase.status.in_(PRACTICE_STATUSES + DEPARTMENT_STATUSES))
        for q in (live.where(OnboardingCase.hr_tg_id == user_id), live, select(OnboardingCase)):
            case = await s.scalar(q.order_by(OnboardingCase.id.desc()).limit(1))
            if case is not None:
                return case
        return None

    def sheet_preview_messages(self, case: OnboardingCase) -> list[tuple[str, Buttons | None]]:
        """Тексты схемы Маши в порядке листа: «[номер] кому, когда» + сообщение, как его получит адресат."""
        return [(f"[{num}] {who}\n\n{text}", buttons) for num, who, _, text, buttons in self.sheet_plan(case)]

    def sheet_plan(self, case: OnboardingCase) -> list[tuple[str, str, str, str, Buttons | None]]:
        """(номер, кому и когда, роль hr/lead/chat, текст, кнопки) — все уведомления схемы по порядку."""
        demo = OnboardingCase(**{c.name: getattr(case, c.name) for c in OnboardingCase.__table__.columns})
        if demo.department_start_date is None:  # практика ещё идёт — выход «на следующий рабочий день»
            demo.department_start_date = sch.next_workday(demo.practice_last_day + timedelta(days=1))
        if demo.probation_end_date is None:
            demo.probation_end_date = sch.add_months(demo.department_start_date, 3)
        ctx = self._ctx(demo)
        link = self.card_link(demo)
        day = sch.utc_to_local(demo.practice_start_at, demo.timezone).date().isoformat()

        def staff(text: str) -> str:
            return f"{text}\n{texts.CARD_LINK.format(link=link)}" if link else text

        r = texts.SHEET_REMINDER
        sig = texts.SHEET_SIGNAL
        start = (texts.SHEET_PRACTICE_START_CHAT_READY if demo.work_chat_id else texts.SHEET_PRACTICE_START)
        plan: list[tuple[str, str, str, Buttons | None]] = [
            ("3", "HR, за час до старта практики", staff(start.format(**ctx)), None),
            ("4", "в рабочий чат кандидату, каждый день практики в 20:00",
             texts.SHEET_LOOM.format(mention=self._mention(demo)), texts.sheet_loom_buttons(day)),
            ("5", "HR, последний день практики в 18:00", staff(sig["no_decision"].format(**ctx)), None),
            ("6", "HR, сразу при переводе в отдел", staff(sig["transferred"].format(**ctx)), None),
            ("Л2", "лиду, сразу при переводе в отдел", staff(texts.SHEET_LEAD_TRANSFER.format(**ctx)), None),
            ("7", "HR, статус «не прошёл»", staff(sig["failed"].format(**ctx)), None),
            ("8", "HR, за день до выхода в 12:00", staff(r["s_hr_day_before"].format(**ctx)), None),
            ("Л4", "лиду, за день до выхода в 12:00", staff(r["s_lead_day_before"].format(**ctx)), None),
            ("Л5", "лиду, первый день в 09:00", staff(r["s_lead_first_day"].format(**ctx)), None),
            ("9", "HR, первый день в 09:30", staff(r["s_hr_first_day"].format(**ctx)), None),
            ("Л6", "лиду, первый день в 15:00", staff(r["s_lead_call_done"].format(**ctx)), None),
            ("10", "HR, первый день в 17:00", staff(r["s_hr_first_day_survey"].format(**ctx)), None),
            ("11", "HR, день 2 в 10:00", staff(r["s_hr_check_first_day"].format(**ctx)), None),
            ("Л7", "лиду, день 3 в 10:00", staff(r["s_lead_goals"].format(**ctx)), None),
            ("12", "HR, день 6 в 10:00", staff(r["s_hr_week_survey"].format(**ctx)), None),
            ("13", "HR, день 7 в 09:30", staff(r["s_hr_week_meeting"].format(**ctx)), None),
            ("14", "HR, за 3 дня до 1 месяца", staff(r["s_hr_m1_soon"].format(**ctx)), None),
            ("Л8", "лиду, за 3 дня до 1 месяца", staff(r["s_lead_m1_soon"].format(**ctx)), None),
            ("15", "HR, 1 месяц", staff(r["s_hr_m1"].format(**ctx)), None),
            ("Л9", "лиду, 1 месяц", staff(r["s_lead_m1"].format(**ctx)), None),
            ("16", "HR, за 3 дня до 2 месяцев", staff(r["s_hr_m2_soon"].format(**ctx)), None),
            ("Л8", "лиду, за 3 дня до 2 месяцев", staff(r["s_lead_m2_soon"].format(**ctx)), None),
            ("16", "HR, 2 месяца", staff(r["s_hr_m2"].format(**ctx)), None),
            ("Л9", "лиду, 2 месяца", staff(r["s_lead_m2"].format(**ctx)), None),
            ("17", "HR, за 2 недели до конца испытательного", staff(r["s_hr_m3_two_weeks"].format(**ctx)), None),
            ("Л10", "лиду, за 2 недели до конца испытательного", staff(r["s_lead_m3_two_weeks"].format(**ctx)), None),
            ("18", "HR, за 3 дня до конца испытательного, если решения нет",
             staff(r["s_hr_no_decision"].format(**ctx)), None),
            ("Л11", "лиду, за 3 дня до конца испытательного, если решения нет",
             staff(r["s_lead_no_decision"].format(**ctx)), None),
            ("19", "HR, день закрытия испытательного", staff(r["s_hr_probation_close"].format(**ctx)), None),
            ("20", "HR, статус «Мы уволили» / «Сам уволился»", staff(sig["left"].format(**ctx)), None),
            ("21", "HR, 6 месяцев", staff(r["s_hr_6m"].format(**ctx)), None),
            ("Л12", "лиду, 6 месяцев", staff(r["s_lead_6m"].format(**ctx)), None),
        ]
        return [(num, who, "chat" if num == "4" else ("lead" if num.startswith("Л") else "hr"), text, buttons)
                for num, who, text, buttons in plan]

    async def demo_sheet(self, chat_id: int, user_id: int, username: str | None = None) -> str | None:
        """/demo: путь одного кандидата по схеме Маши в ускоренном виде, по сценам (Ильнар 25.11.2026:
        «имитировать естественный процесс работы, но в ускоренном виде»; «сначала писал, что за сценарий,
        а потом действия»). В беседу — заголовок сцены и то, что бот пишет в чат (Loom); HR и лиду —
        в личку тем же текстом, что в жизни; получают те, кто указан по ролям и есть в этой беседе.
        Ветки «не прошёл»/уход, второй месяц и «если решения нет» не показываем."""
        async with self.sessions() as s:
            if not await self._is_staff(s, user_id):
                return None
            bound = await self._case_for_chat(s, chat_id)
            # беседа не привязана (проверочный чат) — пример, как у /preview
            case = bound or await self._example_case(s, user_id)
        if case is None:
            return texts.DEMO_NO_CASE
        if bound is not None and await self._candidate_in_chat(chat_id, bound, user_id, username):
            return texts.DEMO_CANDIDATE_HERE.format(cmd="/demo")
        hr_all = [case.hr_tg_id] if case.hr_tg_id else []
        # Отдела ещё нет — лиды организации из беседы, кроме HR кандидата (прод 25.11.2026: Мария —
        # и HR, и лид своего отдела в «Управлении», и получала в демо обе части)
        leads = self.lead_ids(case) or [tg for tg in await self._known_leads(case.org_id) if tg not in hr_all]
        present = {"hr": [tg for tg in hr_all if await self._in_chat(chat_id, tg)],
                   "lead": [tg for tg in leads if await self._in_chat(chat_id, tg)]}
        names = {tg: await self._staff_name(tg) for tg in set(present["hr"] + present["lead"])}
        steps = {num: (role, text, buttons) for num, when, role, text, buttons in self.sheet_plan(case)
                 if "2 месяц" not in when}
        ctx = self._ctx(case)

        def who(role: str) -> str:
            return ", ".join(names[tg] for tg in present[role]) or "никто, в беседе нет"
        intro = texts.DEMO_INTRO.format(full=case.full_name, hr=who("hr"), lead=who("lead"))
        scenes = [(texts.DEMO_SCENE.format(n=i, total=len(texts.DEMO_SCENES), title=title, text=text.format(**ctx)),
                   [steps[num] for num in nums]) for i, (title, text, nums) in enumerate(texts.DEMO_SCENES, 1)]
        task = asyncio.create_task(self._run_demo(chat_id, user_id, intro, scenes, present))
        self._preview_tasks = getattr(self, "_preview_tasks", set())
        self._preview_tasks.add(task)
        task.add_done_callback(self._preview_tasks.discard)
        log.info("ONBOARDING demo chat=%s case=%s hr=%s leads=%s", chat_id, case.id, present["hr"], present["lead"])
        return None

    async def _run_demo(self, chat_id: int, owner: int, intro: str, scenes, present: dict[str, list[int]]) -> None:
        failed: set[int] = set()
        pause = self.preview_pause
        try:
            await self.messenger.send(chat_id, intro)
        except SendError as exc:
            log.warning("ONBOARDING demo chat=%s: %s", chat_id, exc)
            return
        for header, messages in scenes:
            if pause:
                await asyncio.sleep(pause * 2)  # прочитать, что было, — и дальше
            try:
                await self.messenger.send(chat_id, header)
            except SendError as exc:
                log.warning("ONBOARDING demo chat=%s: %s", chat_id, exc)
                return
            for role, text, buttons in messages:
                if pause:
                    await asyncio.sleep(pause)
                targets = [chat_id] if role == "chat" else [tg for tg in present[role] if tg not in failed]
                for target in targets:
                    try:
                        await self.messenger.send(target, text, buttons if role == "chat" else None)
                    except SendError as exc:
                        log.warning("ONBOARDING demo %s: %s", target, exc)
                        if target == chat_id:
                            return
                        failed.add(target)
                        try:  # кто не открывал бота — тихо сказать запустившему
                            await self.messenger.send(owner, texts.DEMO_DM_FAILED.format(
                                name=await self._staff_name(target)))
                        except SendError:
                            pass
        if pause:
            await asyncio.sleep(pause)
        try:
            await self.messenger.send(chat_id, texts.DEMO_DONE)
        except SendError:
            pass

    async def _candidate_in_chat(self, chat_id: int, case: OnboardingCase, user_id: int,
                                 username: str | None) -> bool:
        """Кандидат этой беседы может её читать (а не тот, кто тестирует на своём Telegram)."""
        if _is_candidate(case, user_id, username):
            return False
        if case.candidate_tg_id is not None:
            return await self._in_chat(chat_id, case.candidate_tg_id)
        return True  # чат кандидата, а есть ли он в нём — бот узнать не может

    async def _in_chat(self, chat_id: int, tg_id: int) -> bool:
        check = getattr(self.messenger, "is_member", None)
        return bool(check) and await check(chat_id, tg_id)

    async def _known_leads(self, org_id: int | None) -> list[int]:
        """Все лиды организации с Telegram: из оргструктуры и подтверждённые через /lead."""
        async with self.sessions() as s:
            q = (select(User.telegram_id).join(DepartmentMember, DepartmentMember.user_id == User.id)
                 .join(Department, Department.id == DepartmentMember.department_id)
                 .where(DepartmentMember.role == DeptRole.lead, User.telegram_id.is_not(None)))
            if org_id is not None:
                q = q.where(Department.org_id == org_id)
            org = list(await s.scalars(q))
            q = select(DepartmentLead.tg_id).where(DepartmentLead.status == "confirmed")
            if org_id is not None:
                q = q.where(or_(DepartmentLead.org_id == org_id, DepartmentLead.org_id.is_(None)))
            confirmed = list(await s.scalars(q))
        return list(dict.fromkeys(org + confirmed))

    async def _staff_name(self, tg_id: int) -> str:
        async with self.sessions() as s:
            name = await s.scalar(select(User.name).where(User.telegram_id == tg_id).limit(1))
            if not name:
                name = await s.scalar(select(DepartmentLead.full_name).where(DepartmentLead.tg_id == tg_id).limit(1))
        return name or str(tg_id)

    async def _send_preview(self, chat_id: int, items: list[tuple[str, Buttons | None]]) -> None:
        for i, (text, buttons) in enumerate(items):
            if i and self.preview_pause:
                await asyncio.sleep(self.preview_pause)
            try:
                await self.messenger.send(chat_id, text, buttons)
            except SendError as exc:
                log.warning("ONBOARDING preview chat=%s stopped at %s: %s", chat_id, i, exc)
                return

    # ------------------------------------------------------------- смена HR

    async def ping_hr_changes(self) -> int:
        """Смена HR у кандидата (services/candidate_hr.py пишет её в extra_data.hr_changes) —
        новому и прежнему HR в Telegram со ссылкой на карточку. Смотрит только свежие записи."""
        now = self.clock()
        watermark = getattr(self, "_hr_watermark", None)
        if watermark is None:
            self._hr_watermark, self._hr_seen = now, set()  # история до запуска — не шлём
            return 0
        async with self.sessions() as s:
            entities = (await s.scalars(select(Entity).where(Entity.updated_at >= watermark - timedelta(minutes=5)))).all()
        sent = 0
        for entity in entities:
            for rec in (entity.extra_data or {}).get("hr_changes") or []:
                rid, at = rec.get("id"), _parse_dt(rec.get("at"))
                if not rid or rid in self._hr_seen or at is None or at < watermark:
                    continue
                self._hr_seen.add(rid)
                sent += await self._ping_hr_change(entity, rec)
        if len(self._hr_seen) > HR_CHANGE_SEEN_MAX:
            self._hr_seen = set(list(self._hr_seen)[-HR_CHANGE_SEEN_MAX // 2:])
        self._hr_watermark = now
        return sent

    async def _ping_hr_change(self, entity: Entity, rec: dict) -> int:
        ids = [i for i in (rec.get("prev"), rec.get("new"), rec.get("by")) if i]
        async with self.sessions() as s:
            rows = (await s.scalars(select(User).where(User.id.in_(ids)))).all()
        users = {u.id: u for u in rows}
        new, prev = users.get(rec.get("new")), users.get(rec.get("prev"))
        if new and new.telegram_id:
            # Прод 24.11.2026: после «Сменить HR» сигналы бота (блокер, переход, первый день) уходили
            # прежнему HR — карточка бота помнила Telegram того, кто был HR при старте практики.
            async with self.sessions() as s:
                for case in (await s.scalars(select(OnboardingCase).where(
                        OnboardingCase.entity_id == entity.id))).all():
                    case.hr_tg_id = new.telegram_id
                await s.commit()
        link = f"{self.settings.app_url}/all-candidates?entity={entity.id}"
        sent = 0
        if new and new.telegram_id and rec.get("by") != new.id:
            prev_txt = f" (прежний HR: {prev.name})" if prev and prev.name else ""
            sent += await self._safe_send(new.telegram_id, texts.HR_CHANGE_NEW.format(
                name=entity.name, prev=prev_txt, link=link))
        if prev and prev.telegram_id and rec.get("by") != prev.id:
            sent += await self._safe_send(prev.telegram_id, texts.HR_CHANGE_PREV.format(
                name=entity.name, new=(new.name if new else "другой HR"), link=link))
        await self._events(f"Смена HR: {entity.name}, было {prev.name if prev else 'без HR'}, "
                           f"стало {new.name if new else 'без HR'}. {link}")
        log.info("ONBOARDING hr change ping entity=%s rec=%s sent=%s", entity.id, rec.get("id"), sent)
        return sent

    # ------------------------------------------------------------- помощники

    async def _safe_send(self, chat_id: int, text: str) -> int:
        try:
            await self.messenger.send(chat_id, text)
            return 1
        except SendError as exc:
            log.warning("сообщение в %s не доставлено: %s", chat_id, exc)
            return 0

    async def _events(self, text: str) -> None:
        """Копия в общий чат HR (ONBOARDING_HR_EVENTS_CHAT_ID), если он задан."""
        if self.settings.hr_events_chat_id:
            await self._safe_send(self.settings.hr_events_chat_id, text)

    @staticmethod
    async def _is_staff(s, tg_id: int | None) -> bool:
        if tg_id is None:
            return False
        return await s.scalar(select(User.id).where(User.telegram_id == tg_id).limit(1)) is not None

    async def _mentor_tag(self, case: OnboardingCase) -> str | None:
        """«@ник» ментора (руководителя практики) по имени из карточки, иначе само имя."""
        name = (await self._current_mentor(case) or case.practice_lead or "").strip()
        if not name:
            return None
        if "@" in name:
            return "@" + name.split("@", 1)[1].split()[0]
        first = name.split()[0].lower()
        async with self.sessions() as s:
            with_tg = (await s.scalars(select(User).where(User.telegram_username.is_not(None)))).all()
        # Сравнение в Python: lower() в SQLite не знает кириллицы
        users = [u for u in with_tg if (u.name or "").lower().split()[:1] == [first]]
        if len(users) == 1:
            return f"@{users[0].telegram_username.lstrip('@')}"
        return name

    async def _current_mentor(self, case: OnboardingCase) -> str | None:
        """Ментор, который стоит в карточке СЕЙЧАС. Прод 24.11.2026: ментора поставили после старта
        практики, а бот помнил пустое имя со старта и тегал «Руководитель практики»."""
        if case.entity_id is None:
            return None
        from api.services.practice_mentor import load_mentors

        async with self.sessions() as s:
            entity = await s.get(Entity, case.entity_id)
            if entity is None:
                return None
            tags = (await load_mentors(s, entity.org_id, [entity.id])).get(entity.id)
        return tags[0] if tags else None

    @staticmethod
    def _mention(case: OnboardingCase) -> str:
        return f"@{case.candidate_tg_username}" if case.candidate_tg_username else case.first_name

    async def _case_for_chat(self, s, chat_id: int) -> OnboardingCase | None:
        return await s.scalar(
            select(OnboardingCase)
            .where(or_(OnboardingCase.work_chat_id == chat_id, OnboardingCase.dept_chat_id == chat_id),
                   OnboardingCase.status.in_(PRACTICE_STATUSES + DEPARTMENT_STATUSES))
            .order_by(OnboardingCase.id.desc()).limit(1)
        )

    async def _unbound_practice_cases(self, s) -> list[OnboardingCase]:
        today = sch.utc_to_local(self.clock(), self.settings.default_tz).date()
        start = sch.local_to_utc(datetime.combine(today - BIND_WINDOW_BEFORE, datetime.min.time()), self.settings.default_tz)
        end = sch.local_to_utc(datetime.combine(today + BIND_WINDOW_AFTER, datetime.min.time()), self.settings.default_tz)
        return list((await s.scalars(select(OnboardingCase).where(
            OnboardingCase.status.in_(PRACTICE_STATUSES), OnboardingCase.work_chat_id.is_(None),
            OnboardingCase.practice_start_at >= start, OnboardingCase.practice_start_at < end,
        ).order_by(OnboardingCase.practice_start_at))).all())

    async def _unbound_dept_cases(self, s) -> list[OnboardingCase]:
        if self.sheet:  # схема Маши: чат отдела ведёт лид, бот туда не нужен
            return []
        today = sch.utc_to_local(self.clock(), self.settings.default_tz).date()
        return list((await s.scalars(select(OnboardingCase).where(
            OnboardingCase.status.in_(DEPARTMENT_STATUSES), OnboardingCase.dept_chat_id.is_(None),
            OnboardingCase.department_start_date >= today - DEPT_BIND_WINDOW,
            OnboardingCase.department_start_date <= today + DEPT_BIND_WINDOW,
        ).order_by(OnboardingCase.department_start_date))).all())


def _is_candidate(case: OnboardingCase, user_id: int, username: str | None) -> bool:
    if case.candidate_tg_id is not None:
        return case.candidate_tg_id == user_id
    return bool(username) and _norm(username) == case.candidate_tg_username


def _title_score(case: OnboardingCase, title: str) -> int:
    """Сколько слов ФИО кандидата есть в названии чата."""
    low = title.lower()
    return sum(1 for w in (case.full_name or "").split() if len(w) > 2 and w.lower() in low)


def _named_in_title(cases: list[OnboardingCase], title: str) -> list[OnboardingCase]:
    """Карточки, ВСЁ ФИО которых есть в названии чата. Несколько — решает слово «практика»/«отдел»
    в названии: «Практика Тестбот Владимир» подходит и «Тестбот Практика», но это чат практики."""
    named = []
    for c in cases:
        words = [w for w in (c.full_name or "").split() if len(w) > 2]
        if words and _title_score(c, title) == len(words):
            named.append(c)
    if len(named) > 1:
        low = title.lower()
        if "практик" in low:
            named = [c for c in named if c.status in PRACTICE_STATUSES] or named
        elif "отдел" in low:
            named = [c for c in named if c.status in DEPARTMENT_STATUSES] or named
    return named


def _ddmm(day: date | None) -> str:
    return day.strftime("%d.%m.%Y") if day else ""


def _parse_dt(value) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None
