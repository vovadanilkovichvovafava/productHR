"""Передача кандидатов и сотрудников HR-профилю автоспамера / AI-селлера.

Голосовое Владимира 03.11.2026: своего бота-собеседника нет — переписку ведут HR-аккаунты
автоспамера и AI-селлера. Отчёт админа в тот же день: HR-профиль ведёт человека сам, от
практики до конца испытательного (напоминания, Loom, поздравление, опросы, кошелёк,
сигналы HR), «осталось понять, как АТС будет их нам передавать». Поэтому productHR передаёт
только СОБЫТИЯ, расписание — на их стороне:

- practice  — статус «Практика» (probation): дата старта, руководитель практики, HRD;
- transfer  — «Перешёл в отдел» (transferred): отдел, лид, первый рабочий день;
- stop      — отказ / отозван / резерв / уволен / уволился после переданного события.

Как работает (раз в 30 с из runtime.run_worker): смотрит на entities.status, а не встраивается
в пути смены статуса — воронка, карточка и «Штат» ловятся одинаково. Первый запуск помечает
всех, кто УЖЕ на практике или в отделе (baseline): то же событие им не шлём, следующее — да.
Нет Telegram/телефона или нужной даты — один раз говорим HR и ждём.

Доставка: JSON на ONBOARDING_HANDOFF_WEBHOOK_URL (подпись HMAC-SHA256), иначе — сообщение
HR-аккаунту из ONBOARDING_HANDOFF_ACCOUNTS (с наименьшей нагрузкой; человек закрепляется за
ним). Формат — ~/Desktop/Rabota/spam/HANDOFF_FORMAT.md. Кошелёк и прочее не передаётся.
Пометки этапов (неделя, месяцы) — только при ONBOARDING_HANDOFF_STAGES.
"""

import hashlib
import hmac
import html
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.models.database import (
    BoardDepartment,
    BoardPlacement,
    DataMigrationMark,
    Entity,
    EntityStatus,
    User,
)
from api.services.similarity import first_real_telegram

from . import schedule as sch
from .config import Settings
from .messenger import Messenger, SendError
from .models import Handoff, HandoffAccount

logger = logging.getLogger("hr-analyzer.onboarding")

BASELINE_MARK = "onboarding_handoff_baseline_v2_2026_11"
RETRY_AFTER = timedelta(minutes=10)
# Напоминания HR после перехода в отдел — новая версия ТЗ Маши (06.11.2026), чек-лист первого
# дня: «АТС — напоминание эйчару о старте работы (!!!!)» и «за 6 дней бот приходит к HR,
# напоминает о звонке». (ключ, день от первого рабочего, флаг в onboarding_handoffs)
HR_REMINDERS = (("day1", 0, "hr_day1_done"), ("week", 5, "hr_week_done"))
REMINDER_STALE = timedelta(days=1)  # перевели задним числом — старое напоминание не шлём
PRACTICE = EntityStatus.probation       # «Практика»
TRANSFER = EntityStatus.transferred     # «Перешёл в отдел»
TRACKED = (PRACTICE, TRANSFER)
STOP_REASONS = {
    EntityStatus.rejected: "не прошёл (Отказ)",
    EntityStatus.withdrawn: "отозвал отклик",
    EntityStatus.reserve: "отложен в резерв",
    EntityStatus.dismissed: "уволен",
    EntityStatus.quit: "уволился",
}
# Ключи карточки, которые ведёт доска «Штат» (routes/staff_board.py): наш и запасной из ClickUp
PRACTICE_START_KEYS = ("practice_start_date", "cf:Выход на практику")
DEPT_START_KEYS = ("department_transfer_date", "cf:Выход в отдел")
MANAGER_KEYS = ("manager_name", "cf:Рук-ль")


@dataclass(frozen=True)
class Stage:
    key: str
    title: str
    hour: int


STAGES = (
    Stage("week", "неделя в отделе — опрос недели", sch.SURVEY_HOUR),
    Stage("month1", "месяц работы — опрос месяца 1", sch.SURVEY_HOUR),
    Stage("month2", "два месяца — опрос месяца 2", sch.SURVEY_HOUR),
    Stage("month3", "за 2 недели до конца испытательного — опрос месяца 3", sch.SURVEY_HOUR),
    Stage("probation_end", "последний день испытательного срока", sch.STAFF_HOUR),
)


def stage_day(stage: Stage, first_day: date) -> date:
    return {
        "week": first_day + timedelta(days=5),
        "month1": sch.add_months(first_day, 1),
        "month2": sch.add_months(first_day, 2),
        "month3": sch.add_months(first_day, 3) - timedelta(days=14),
        "probation_end": sch.add_months(first_day, 3),
    }[stage.key]


TAGS = {"practice": "#onboarding_practice", "transfer": "#onboarding_transfer",
        "stop": "#onboarding_stop", "stage": "#onboarding_stage"}
# Ключ события → подпись строки в Telegram-сообщении (порядок = порядок строк)
LABELS = (
    ("id", "id"), ("stage_title", "Этап"), ("full_name", "ФИО"), ("telegram", "Telegram"),
    ("phone", "Телефон"), ("practice_start", "Старт практики"), ("practice_lead", "Руководитель практики"),
    ("hrd", "HRD"), ("department", "Отдел"), ("lead", "Лид"), ("first_day", "Первый рабочий день"),
    ("probation_end", "Испытательный срок до"), ("materials", "Материалы"), ("reason", "Причина"), ("timezone", "Часовой пояс"), ("hr", "HR"),
)


class NullMessenger:
    """Без бота (только вебхук) — Telegram не нужен."""

    async def send(self, chat_id, text, buttons=None, html=False):
        raise SendError("Telegram-бот не настроен")

    async def delete(self, chat_id, message_id):
        raise SendError("Telegram-бот не настроен")


def _parse_date(value) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _pick(extra: dict, keys) -> Optional[str]:
    for key in keys:
        value = extra.get(key)
        if value not in (None, ""):
            return value
    return None


def _ids(raw: Optional[str]) -> list[int]:
    return [int(x) for x in (raw or "").split(",") if x.strip().isdigit()]


def event_text(event: dict) -> str:
    lines = [TAGS[event["event"]]]
    for key, label in LABELS:
        value = event.get(key)
        if value not in (None, ""):
            lines.append(f"{label}: {value}")
    return "\n".join(lines)


async def _http_post(url: str, body: bytes, headers: dict) -> None:
    import httpx

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(url, content=body, headers=headers)
    if response.status_code >= 400:
        raise SendError(f"вебхук ответил {response.status_code}")


class HandoffService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        messenger: Messenger,
        settings: Settings,
        clock: Callable[[], datetime],
        poster: Callable[[str, bytes, dict], Awaitable[None]] = _http_post,
    ):
        self.sessions = sessions
        self.messenger = messenger
        self.settings = settings
        self.clock = clock
        self.poster = poster

    @property
    def via_webhook(self) -> bool:
        return bool(self.settings.handoff_webhook_url)

    # ------------------------------------------------------------------ вход

    async def register_account(self, tg_id: int, username: Optional[str]) -> bool:
        """/start от HR-аккаунта из списка (по @нику или по Telegram ID) — запоминаем, куда писать."""
        name = (username or "").lstrip("@").lower()
        listed = self.settings.all_handoff_accounts
        if name and name in listed:
            pass
        elif str(tg_id) in listed:
            name = str(tg_id)  # у купленных аккаунтов часто нет @ника — тогда в списке их ID
        else:
            return False
        async with self.sessions() as s:
            account = await s.scalar(select(HandoffAccount).where(HandoffAccount.username == name))
            if account is None:
                account = HandoffAccount(username=name)
                s.add(account)
            account.tg_id = tg_id
            account.linked_at = self.clock()
            await s.commit()
        logger.info("ONBOARDING handoff account linked @%s tg=%s", name, tg_id)
        return True

    async def tick(self) -> int:
        """Один проход воркера. Возвращает, сколько событий передано."""
        if not (self.via_webhook or self.settings.all_handoff_accounts):
            return 0
        await self._sync_id_accounts()
        await self._baseline_once()
        await self._pick_up()
        sent = await self._process()
        await self._hr_reminders()
        return sent

    # ------------------------------------------------------------- этапы прохода

    async def _sync_id_accounts(self) -> None:
        """Аккаунты, указанные числовым Telegram ID, подключены сразу: ID берут из того, что они
        уже написали боту, — значит Telegram даст боту им ответить."""
        ids = [key for key in self.settings.all_handoff_accounts if key.isdigit()]
        if not ids:
            return
        async with self.sessions() as s:
            known = {a.username: a for a in (await s.scalars(
                select(HandoffAccount).where(HandoffAccount.username.in_(ids))
            )).all()}
            changed = False
            for key in ids:
                account = known.get(key)
                if account is None:
                    s.add(HandoffAccount(username=key, tg_id=int(key), linked_at=self.clock()))
                    changed = True
                elif account.tg_id is None:
                    account.tg_id, account.linked_at = int(key), self.clock()
                    changed = True
            if changed:
                await s.commit()

    async def _baseline_once(self) -> None:
        async with self.sessions() as s:
            if await s.get(DataMigrationMark, BASELINE_MARK) is not None:
                return
            people = (await s.execute(
                select(Entity.id, Entity.org_id, Entity.status).where(Entity.status.in_(TRACKED))
            )).all()
            known = set((await s.scalars(select(Handoff.entity_id))).all())
            for entity_id, org_id, status in people:
                if entity_id not in known:
                    s.add(Handoff(entity_id=entity_id, org_id=org_id, status="baseline",
                                  baseline_status=status.value, updated_at=self.clock()))
            s.add(DataMigrationMark(key=BASELINE_MARK))
            await s.commit()
        logger.info("ONBOARDING handoff baseline: %s человек уже на практике/в отделе", len(people))

    async def _pick_up(self) -> None:
        async with self.sessions() as s:
            fresh = (await s.execute(
                select(Entity.id, Entity.org_id)
                .outerjoin(Handoff, Handoff.entity_id == Entity.id)
                .where(Entity.status.in_(TRACKED), Handoff.id.is_(None))
            )).all()
            for entity_id, org_id in fresh:
                s.add(Handoff(entity_id=entity_id, org_id=org_id, status="active", updated_at=self.clock()))
            # вернулся на практику/в отдел после стопа — ведём заново
            returned = (await s.scalars(
                select(Handoff)
                .join(Entity, Entity.id == Handoff.entity_id)
                .where(Handoff.status == "stopped", Entity.status.in_(TRACKED))
            )).all()
            for row in returned:
                row.status, row.baseline_status = "active", None
                row.hr_day1_done = row.hr_week_done = False
                row.delivered = None
                row.practice_sent_at = row.transfer_sent_at = row.stop_sent_at = None
                row.stage_index, row.next_at = 0, None
                row.waiting_reason = row.notified_reason = None
                row.updated_at = self.clock()
            await s.commit()
        for entity_id, _ in fresh:
            logger.info("ONBOARDING handoff new entity=%s", entity_id)

    async def _process(self) -> int:
        now = self.clock()
        async with self.sessions() as s:
            rows = (await s.execute(
                select(Handoff, Entity)
                .join(Entity, Entity.id == Handoff.entity_id)
                .where(
                    Handoff.status.in_(("baseline", "active")),
                    (Handoff.next_at.is_(None)) | (Handoff.next_at <= now),
                )
            )).all()
        sent = 0
        for row, entity in rows:
            status = entity.status
            if status == PRACTICE and row.practice_sent_at is None and row.baseline_status != PRACTICE.value:
                sent += await self._send_event(row, entity, "practice")
            elif status == TRANSFER and row.transfer_sent_at is None and row.baseline_status != TRANSFER.value:
                sent += await self._send_event(row, entity, "transfer")
            elif status in STOP_REASONS:
                sent += await self._stop(row, entity)
            elif (status == TRANSFER and row.transfer_sent_at and self.settings.handoff_stages
                  and row.next_at is not None and row.stage_index < len(STAGES)):
                sent += await self._send_event(row, entity, "stage")
        return sent

    # ------------------------------------------------------------------ события

    async def _send_event(self, row: Handoff, entity: Entity, kind: str) -> int:
        extra = entity.extra_data or {}
        practice_date = _parse_date(_pick(extra, PRACTICE_START_KEYS))
        first_day = _parse_date(_pick(extra, DEPT_START_KEYS))
        reason = None if self._contact(entity) else "no_telegram"
        if not reason and kind == "practice" and not practice_date:
            reason = "no_practice_date"
        if not reason and kind in ("transfer", "stage") and not first_day:
            reason = "no_first_day"
        if reason:
            await self._wait(row, entity, reason)
            return 0

        event = await self._event(entity, kind)
        if kind == "practice":
            event["practice_start"] = f"{practice_date.strftime('%d.%m.%Y')} {self.settings.practice_start_time}"
            event["practice_start_iso"] = f"{practice_date.isoformat()}T{self.settings.practice_start_time}"
            event["practice_lead"] = _pick(extra, MANAGER_KEYS)
            event["hrd"] = self.settings.hrd or None
        else:
            department, _ = await self._department_and_hr(entity)
            event["department"] = department
            event["lead"] = _pick(extra, MANAGER_KEYS)
            event["first_day"] = first_day.strftime("%d.%m.%Y")
            event["first_day_iso"] = first_day.isoformat()
            # С перехода в отдел идёт испытательный срок (3 месяца, ТЗ раздел 4) — Владимир
            # 06.11.2026: «не практика, а испытательный срок»
            probation_end = sch.add_months(first_day, 3)
            event["probation_end"] = probation_end.strftime("%d.%m.%Y")
            event["probation_end_iso"] = probation_end.isoformat()
            event["materials"] = self.settings.materials_url or None  # ДНК компании, staffwise.club/dna/
        if kind == "stage":
            stage = STAGES[row.stage_index]
            event["stage"] = stage.key
            event["stage_title"] = f"{stage.key} — {stage.title}"

        got = await self._deliver(row, entity, event, await self._targets(row, kind))
        if got is False:
            return 0
        async with self.sessions() as s:
            fresh = await s.get(Handoff, row.id)
            fresh.status = "active"
            self._pin(fresh, got)
            fresh.delivered = None
            fresh.waiting_reason = fresh.notified_reason = None
            fresh.next_at = None
            if kind == "practice":
                fresh.practice_sent_at, fresh.practice_date = self.clock(), practice_date
            elif kind == "transfer":
                fresh.transfer_sent_at, fresh.first_day = self.clock(), first_day
                fresh.stage_index = 0
                if self.settings.handoff_stages:
                    fresh.next_at = self._stage_time(STAGES[0], first_day)
            else:
                fresh.stage_index += 1
                if fresh.stage_index < len(STAGES):
                    fresh.next_at = self._stage_time(STAGES[fresh.stage_index], fresh.first_day or first_day)
            fresh.updated_at = self.clock()
            await s.commit()
        logger.info("ONBOARDING handoff %s entity=%s → %s", event.get("stage") or kind, entity.id,
                    ", ".join(f"@{a.username}" for _, a in got) or "webhook")
        if kind in ("practice", "transfer"):
            # HR видит, что передача прошла (Ильнар 06.11.2026: «бот тихо принимает»). Было
            # «допишите …» — оно удаляется, «передан» приходит в тот же чат.
            chat_id = await self._drop_notice(row) if row.notice_message_id else None
            await self._confirm_hr(entity, self._confirm_text(entity, event), chat_id)
        return 1

    async def _hr_reminders(self) -> int:
        """HR — в первый рабочий день и на 6-й день в отделе, в 10:00 (выходные — на понедельник)."""
        now = self.clock()
        async with self.sessions() as s:
            rows = (await s.execute(
                select(Handoff, Entity)
                .join(Entity, Entity.id == Handoff.entity_id)
                .where(
                    Handoff.status == "active", Handoff.transfer_sent_at.is_not(None),
                    Handoff.first_day.is_not(None), Entity.status == TRANSFER,
                    Handoff.hr_day1_done.is_(False) | Handoff.hr_week_done.is_(False),
                )
            )).all()
        sent = 0
        for row, entity in rows:
            for key, offset, flag in HR_REMINDERS:
                if getattr(row, flag):
                    continue
                day = row.first_day + timedelta(days=offset)
                if self.settings.skip_weekends:
                    day = sch.next_workday(day)
                due = sch.at_local(day, sch.STAFF_HOUR, self.settings.default_tz)
                if now < due:
                    continue
                if now - due < REMINDER_STALE:
                    await self._confirm_hr(entity, await self._reminder_text(entity, key))
                    logger.info("ONBOARDING handoff HR reminder %s entity=%s", key, entity.id)
                    sent += 1
                async with self.sessions() as s:
                    fresh = await s.get(Handoff, row.id)
                    setattr(fresh, flag, True)
                    await s.commit()
        return sent

    async def _reminder_text(self, entity: Entity, key: str) -> str:
        name = self._name_html(entity)
        department, _ = await self._department_and_hr(entity)
        lead = _pick(entity.extra_data or {}, MANAGER_KEYS)
        where = f" в отделе {html.escape(department)}" if department else " в отделе"
        if key == "day1":
            who = f"лида ({html.escape(str(lead))})" if lead else "лида"
            return (f"Сегодня у {name} первый рабочий день{where}. Спроси {who}: установлена ли связь "
                    "с новичком и назначен ли онбординг-звонок.")
        return (f"У {name} шестой день{where}. В первую неделю HR проводит с новичком отдельную встречу — "
                "запланируй созвон: пройтись по ответам опроса недели и по ДНК с демонстрацией экрана.")

    async def _stop(self, row: Handoff, entity: Entity) -> int:
        """Отказ/уход. Если ни одно событие не передавали — молча закрываем."""
        told = row.practice_sent_at or row.transfer_sent_at
        if told:
            event = await self._event(entity, "stop")
            event["reason"] = STOP_REASONS[entity.status]
            event["status"] = entity.status.value
            if await self._deliver(row, entity, event, await self._targets(row, "stop")) is False:
                return 0
        async with self.sessions() as s:
            fresh = await s.get(Handoff, row.id)
            fresh.status, fresh.next_at = "stopped", None
            fresh.stop_sent_at = self.clock() if told else None
            fresh.delivered = None
            fresh.updated_at = self.clock()
            await s.commit()
        if row.notice_message_id:
            await self._drop_notice(row)  # отказ, пока ждали данные: «допишите» уже не актуально
        if told:
            await self._confirm_hr(entity, self._confirm_text(entity, event))
        logger.info("ONBOARDING handoff stop entity=%s status=%s told=%s", entity.id, entity.status, bool(told))
        return 1 if told else 0

    async def _event(self, entity: Entity, kind: str) -> dict:
        _, hr = await self._department_and_hr(entity)
        return {
            "event": kind,
            "id": entity.id,
            "full_name": entity.name,
            "telegram": self._telegram(entity),
            "phone": (entity.phone or "").strip() or None,
            "timezone": self.settings.default_tz,
            "hr": hr,
        }

    # ------------------------------------------------------------- аккаунты по этапам
    # Админ 10.11.2026: пребординг (практика) — свои аккаунты, нагрузка делится; онбординг —
    # два аккаунта (онбординг и испытательный срок), переход в отдел нужен КАЖДОМУ из них
    # (испытательный поздравляет с новым этапом). Без списков по этапам — один аккаунт на всё.

    async def _targets(self, row: Handoff, kind: str) -> list[tuple[str, Optional[HandoffAccount]]]:
        """[(ключ, аккаунт)] — кому отправить событие; ключ — для `delivered`."""
        onboarding = self.settings.handoff_onboarding_accounts
        if kind in ("transfer", "stage") and onboarding:
            async with self.sessions() as s:
                linked = {a.username: a for a in (await s.scalars(
                    select(HandoffAccount).where(HandoffAccount.username.in_(onboarding),
                                                 HandoffAccount.tg_id.is_not(None))
                )).all()}
            return [(name, linked.get(name)) for name in onboarding]
        if kind == "stop":
            return await self._stop_targets(row)
        return [("main", await self._main_account(row))]

    async def _stop_targets(self, row: Handoff) -> list[tuple[str, Optional[HandoffAccount]]]:
        """Стоп — каждому аккаунту, который уже вёл человека, по одному разу."""
        ids = ([row.account_id] if row.account_id else []) + _ids(row.onboarding_account_ids)
        async with self.sessions() as s:
            accounts = [await s.get(HandoffAccount, i) for i in dict.fromkeys(ids)]
        targets = [(f"id{a.id}", a) for a in accounts if a and a.tg_id]
        return targets or [("main", await self._main_account(row))]

    async def _deliver(self, row: Handoff, entity: Entity, event: dict,
                       targets: list[tuple[str, Optional[HandoffAccount]]]):
        """[(ключ, аккаунт)] доставленных ([] при вебхуке) или False — не доставлено, повтор позже.
        Аккаунты, которым событие уже ушло (`delivered`), при повторе пропускаются."""
        if self.via_webhook:
            body = json.dumps({**event, "sent_at": self.clock().isoformat() + "Z"}, ensure_ascii=False).encode()
            headers = {"Content-Type": "application/json", "X-Onboarding-Event": event["event"]}
            if self.settings.handoff_webhook_secret:
                digest = hmac.new(self.settings.handoff_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
                headers["X-Onboarding-Signature"] = f"sha256={digest}"
            try:
                await self.poster(self.settings.handoff_webhook_url, body, headers)
            except Exception as exc:  # сеть, 5xx — повторим
                logger.warning("ONBOARDING handoff webhook failed entity=%s: %s", entity.id, exc)
                await self._postpone(row, "send_failed")
                return False
            return []
        done = set(filter(None, (row.delivered or "").split(",")))
        got: list[tuple[str, HandoffAccount]] = []
        what = event.get("stage") or event["event"]
        for key, account in targets:
            mark = f"{what}:{key}"
            if mark in done:
                if account is not None:
                    got.append((key, account))
                continue
            if account is None:
                await self._save_progress(row, done, got)
                await self._postpone(row, "no_account")
                return False
            try:
                await self.messenger.send(account.tg_id, event_text(event))
            except SendError as exc:
                logger.warning("ONBOARDING handoff send failed entity=%s @%s: %s", entity.id, account.username, exc)
                await self._save_progress(row, done, got)
                await self._postpone(row, "send_failed")
                return False
            done.add(mark)
            got.append((key, account))
        return got

    @staticmethod
    def _pin(fresh: Handoff, got: list[tuple[str, HandoffAccount]]) -> None:
        """Запоминает, кто ведёт человека: «main» — практика (или всё), остальные — онбординг."""
        ids = _ids(fresh.onboarding_account_ids)
        for key, account in got:
            if key == "main":
                fresh.account_id = account.id
            elif not key.startswith("id") and account.id not in ids:
                ids.append(account.id)
        fresh.onboarding_account_ids = ",".join(map(str, ids)) or None

    async def _save_progress(self, row: Handoff, done: set, got: list) -> None:
        async with self.sessions() as s:
            fresh = await s.get(Handoff, row.id)
            fresh.delivered = ",".join(sorted(done)) or None
            self._pin(fresh, got)
            await s.commit()

    async def _main_account(self, row: Handoff) -> Optional[HandoffAccount]:
        """Закреплённый за человеком аккаунт практики, если он в списке и подключён; иначе —
        подключённый из списка с наименьшей нагрузкой."""
        pool = self.settings.handoff_pool("practice")
        async with self.sessions() as s:
            if row.account_id:
                account = await s.get(HandoffAccount, row.account_id)
                if account and account.tg_id and account.username in pool:
                    return account
            load = (
                select(Handoff.account_id, func.count(Handoff.id).label("n"))
                .where(Handoff.status == "active", Handoff.account_id.is_not(None))
                .group_by(Handoff.account_id)
                .subquery()
            )
            return await s.scalar(
                select(HandoffAccount)
                .outerjoin(load, load.c.account_id == HandoffAccount.id)
                .where(HandoffAccount.tg_id.is_not(None), HandoffAccount.username.in_(pool))
                .order_by(func.coalesce(load.c.n, 0), HandoffAccount.id)
                .limit(1)
            )

    async def _wait(self, row: Handoff, entity: Entity, reason: str) -> None:
        async with self.sessions() as s:
            fresh = await s.get(Handoff, row.id)
            notify = fresh.notified_reason != reason
            fresh.waiting_reason = fresh.notified_reason = reason
            await s.commit()
        if notify:
            await self._tell_hr(row, entity, reason)

    async def _postpone(self, row: Handoff, reason: str) -> None:
        async with self.sessions() as s:
            fresh = await s.get(Handoff, row.id)
            fresh.next_at = self.clock() + RETRY_AFTER
            notify = fresh.notified_reason != reason
            fresh.waiting_reason = fresh.notified_reason = reason
            await s.commit()
        if notify and reason == "no_account":
            await self._tell_fallback(
                "Некому передать кандидата: нужный HR-аккаунт ещё не написал боту (или его нет в "
                "списках ONBOARDING_HANDOFF_*). Передача ждёт."
            )

    # ------------------------------------------------------------------ помощники

    def _stage_time(self, stage: Stage, first_day: date) -> datetime:
        day = stage_day(stage, first_day)
        if self.settings.skip_weekends:
            day = sch.next_workday(day)
        at = sch.at_local(day, stage.hour, self.settings.default_tz)
        return max(at, sch.within_working_hours(self.clock(), self.settings.default_tz, self.settings.skip_weekends))

    @staticmethod
    def _telegram(entity: Entity) -> Optional[str]:
        nick = first_real_telegram(entity.telegram_usernames or [])
        return f"@{nick.lstrip('@')}" if nick else None

    def _contact(self, entity: Entity) -> Optional[str]:
        return self._telegram(entity) or ((entity.phone or "").strip() or None)

    async def _department_and_hr(self, entity: Entity):
        async with self.sessions() as s:
            department = await s.scalar(
                select(BoardDepartment.name)
                .join(BoardPlacement, BoardPlacement.department_id == BoardDepartment.id)
                .where(
                    BoardPlacement.entity_id == entity.id,
                    func.coalesce(BoardDepartment.kind, "team") != "sandbox",
                )
                .order_by(BoardPlacement.id.desc())
                .limit(1)
            )
            hr = await s.get(User, entity.created_by) if entity.created_by else None
        return department, (hr.name if hr else None)

    def _name_html(self, entity: Entity) -> str:
        # ФИО — ссылка на Telegram кандидата, когда ник есть (просьба Ильнара 04.11.2026)
        nick = self._telegram(entity)
        name = html.escape(entity.name or "")
        if nick:
            name = f'<a href="https://t.me/{html.escape(nick.lstrip("@"), quote=True)}">{name}</a>'
        return name

    async def _save_notice(self, row_id: int, chat_id: Optional[int], message_id: Optional[int]) -> None:
        async with self.sessions() as s:
            fresh = await s.get(Handoff, row_id)
            fresh.notice_chat_id, fresh.notice_message_id = chat_id, message_id
            await s.commit()

    async def _drop_notice(self, row: Handoff) -> Optional[int]:
        """Удаляет прежнее «допишите …» у HR. Возвращает чат, где оно было."""
        try:
            await self.messenger.delete(row.notice_chat_id, row.notice_message_id)
        except SendError as exc:  # старше 48 ч или HR удалил сам — не страшно
            logger.info("ONBOARDING handoff HR notice not deleted entity=%s: %s", row.entity_id, exc)
        await self._save_notice(row.id, None, None)
        return row.notice_chat_id

    def _confirm_text(self, entity: Entity, event: dict) -> str:
        name = self._name_html(entity)
        kind = event["event"]
        if kind == "practice":
            return f"{name} передан(а) HR-профилю: практика с {event['practice_start']}. Он напишет кандидату первым."
        if kind == "transfer":
            parts = [f"переход в отдел {html.escape(event['department'])}" if event.get("department")
                     else "переход в отдел", f"первый рабочий день {event['first_day']}",
                     f"испытательный срок до {event['probation_end']}"]
            return f"{name} передан(а) HR-профилю: " + ", ".join(parts) + "."
        return f"{name}: HR-профилю передан стоп — {html.escape(event.get('reason') or '')}."

    async def _hr_targets(self, entity: Entity) -> list[int]:
        """Кому из HR писать: тот, кто завёл карточку, иначе запасной чат."""
        targets = []
        if entity.created_by:
            async with self.sessions() as s:
                user = await s.get(User, entity.created_by)
            if user and user.telegram_id:
                targets.append(user.telegram_id)
        if self.settings.hr_fallback_chat_id:
            targets.append(self.settings.hr_fallback_chat_id)
        return targets

    async def _confirm_hr(self, entity: Entity, text: str, chat_id: Optional[int] = None) -> None:
        for target in ([chat_id] if chat_id else await self._hr_targets(entity)):
            try:
                await self.messenger.send(target, text, html=True)
                return
            except SendError as exc:
                logger.warning("ONBOARDING handoff HR confirm to %s failed: %s", target, exc)

    async def _tell_hr(self, row: Handoff, entity: Entity, reason: str) -> None:
        name = self._name_html(entity)
        text = {
            "no_telegram": (
                f"{name}: в карточке нет Telegram и телефона — допишите, иначе HR-бот "
                "не сможет написать кандидату первым."
            ),
            "no_practice_date": (
                f"{name} на практике, но не указана дата выхода на практику — проставьте её "
                "на «Штате», иначе HR-бот не напишет кандидату."
            ),
            "no_first_day": (
                f"{name} переведён(а) в отдел, но не указана дата выхода в отдел — проставьте её "
                "на «Штате», от неё считаются первый рабочий день и этапы онбординга."
            ),
        }[reason]
        targets = await self._hr_targets(entity)
        if row.notice_message_id:
            await self._drop_notice(row)  # причина сменилась (дописали Telegram, нет даты) — одно сообщение
        for chat_id in targets:
            try:
                message_id = await self.messenger.send(chat_id, text, html=True)
            except SendError as exc:
                logger.warning("ONBOARDING handoff HR notice to %s failed: %s", chat_id, exc)
                continue
            if message_id is not None:
                await self._save_notice(row.id, chat_id, message_id)
            break
        logger.info("ONBOARDING handoff waiting entity=%s reason=%s", entity.id, reason)

    async def _tell_fallback(self, text: str) -> None:
        if not self.settings.hr_fallback_chat_id:
            logger.warning("ONBOARDING handoff: %s", text)
            return
        try:
            await self.messenger.send(self.settings.hr_fallback_chat_id, text)
        except SendError as exc:
            logger.warning("ONBOARDING handoff fallback notice failed: %s", exc)
