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

import logging
import re
from datetime import date, datetime, timedelta

from sqlalchemy import func, or_, select

from api.models.database import (
    BoardDepartment,
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
            await self.messenger.send(chat_id, texts.WHICH_CHAT_DEPT if dept_only else texts.WHICH_CHAT, buttons)
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
            if case.status != CaseStatus.practice_assigned.value:
                continue
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
        tpl = texts.HR_PRACTICE_START_CHAT_READY if case.work_chat_id else texts.HR_PRACTICE_START
        await self._deliver(case, "hr_practice_start", tpl.format(full=case.full_name, bot=bot))

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
        if case.work_chat_id:
            try:
                await self.messenger.send(case.work_chat_id, texts.PRACTICE_DONE.format(**ctx))
            except SendError as exc:
                log.warning("рабочий чат %s: %s", case.work_chat_id, exc)
        if not self.settings.handoff_to_bot:
            return
        first_day = _ddmm(case.department_start_date)
        leads = self.lead_ids(case)
        for tg_id in leads:
            try:
                await self.messenger.send(tg_id, texts.LEAD_NEW_HIRE.format(
                    **ctx, first_day=first_day, probation_end_full=_ddmm(case.probation_end_date)))
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
        link = f"{self.settings.app_url}/all-candidates?entity={entity.id}"
        sent = 0
        if new and new.telegram_id and rec.get("by") != new.id:
            prev_txt = f" (было у {prev.name})" if prev and prev.name else ""
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
        name = (case.practice_lead or "").strip()
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
