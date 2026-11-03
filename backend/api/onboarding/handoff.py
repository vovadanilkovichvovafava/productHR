"""Передача новых сотрудников HR-аккаунтам автоспамера / AI-селлера.

Голосовое Владимира 03.11.2026: «у нас не будет бота как такового… сделать бота, который будет
забирать данные, когда человек попадает в онбординг после практики, и посылать это тг-аккаунтам,
которые мы добавили. Всё остальное делает другая часть команды». Встреча Маши и Вовы 30.10:
первое сообщение — в 10:00 первого рабочего дня, «100% гарантия».

Как работает (раз в 30 с из runtime.run_worker):
1. первый запуск — все, кто УЖЕ «Перешёл в отдел», помечаются baseline: истории не пишем;
2. новый «Перешёл в отдел» → проверяем Telegram/телефон и дату выхода в отдел; чего-то нет —
   один раз говорим HR, ждём;
3. в 10:00 первого рабочего дня — карточка #onboarding_new аккаунту (у кого меньше людей),
   дальше тому же аккаунту пометки этапов #onboarding_stage; выходные пропускаем;
4. человек больше не «Перешёл в отдел» (уволен, ушёл…) — #onboarding_stop.

Формат сообщений — docs: ~/Desktop/Rabota/spam/HANDOFF_FORMAT.md. Кошелёк и прочие данные
карточки не передаются.
"""

import logging
from collections.abc import Callable
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

BASELINE_MARK = "onboarding_handoff_baseline_2026_11"
RETRY_AFTER = timedelta(minutes=10)
# Ключи карточки, которые ведёт доска «Штат» (routes/staff_board.py): наш и запасной из ClickUp
DEPT_START_KEYS = ("department_transfer_date", "cf:Выход в отдел")
MANAGER_KEYS = ("manager_name", "cf:Рук-ль")


@dataclass(frozen=True)
class Stage:
    key: str
    title: str
    hour: int


# Этапы онбординга из ТЗ (раздел 4) — для AI-селлера: когда что делать с человеком
STAGES = (
    Stage("first_day", "первый рабочий день", sch.FIRST_DAY_HOUR),
    Stage("week", "неделя в отделе — опрос недели", sch.SURVEY_HOUR),
    Stage("month1", "месяц работы — опрос месяца 1", sch.SURVEY_HOUR),
    Stage("month2", "два месяца — опрос месяца 2", sch.SURVEY_HOUR),
    Stage("month3", "за 2 недели до конца испытательного — опрос месяца 3", sch.SURVEY_HOUR),
    Stage("probation_end", "последний день испытательного срока", sch.STAFF_HOUR),
)


def stage_day(stage: Stage, first_day: date) -> date:
    return {
        "first_day": first_day,
        "week": first_day + timedelta(days=5),
        "month1": sch.add_months(first_day, 1),
        "month2": sch.add_months(first_day, 2),
        "month3": sch.add_months(first_day, 3) - timedelta(days=14),
        "probation_end": sch.add_months(first_day, 3),
    }[stage.key]


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


class HandoffService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        messenger: Messenger,
        settings: Settings,
        clock: Callable[[], datetime],
    ):
        self.sessions = sessions
        self.messenger = messenger
        self.settings = settings
        self.clock = clock

    # ------------------------------------------------------------------ вход

    async def register_account(self, tg_id: int, username: Optional[str]) -> bool:
        """/start от HR-аккаунта из списка — запоминаем, куда ему писать."""
        name = (username or "").lstrip("@").lower()
        if not name or name not in self.settings.handoff_accounts:
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
        """Один проход воркера. Возвращает, сколько сообщений ушло аккаунтам."""
        if not self.settings.handoff_accounts:
            return 0
        await self._baseline_once()
        await self._pick_up_new()
        await self._check_waiting()
        return await self._send_due()

    # ------------------------------------------------------------- этапы прохода

    async def _baseline_once(self) -> None:
        async with self.sessions() as s:
            if await s.get(DataMigrationMark, BASELINE_MARK) is not None:
                return
            ids = (await s.scalars(
                select(Entity.id).where(Entity.status == EntityStatus.transferred)
            )).all()
            known = set((await s.scalars(select(Handoff.entity_id))).all())
            for entity_id in ids:
                if entity_id not in known:
                    s.add(Handoff(entity_id=entity_id, status="baseline"))
            s.add(DataMigrationMark(key=BASELINE_MARK))
            await s.commit()
        logger.info("ONBOARDING handoff baseline: %s человек уже в отделе — им не пишем", len(ids))

    async def _pick_up_new(self) -> None:
        async with self.sessions() as s:
            fresh = (await s.execute(
                select(Entity.id, Entity.org_id)
                .outerjoin(Handoff, Handoff.entity_id == Entity.id)
                .where(Entity.status == EntityStatus.transferred, Handoff.id.is_(None))
            )).all()
            for entity_id, org_id in fresh:
                s.add(Handoff(entity_id=entity_id, org_id=org_id, status="waiting", updated_at=self.clock()))
            # вернулся в отдел после ухода — ведём заново
            returned = (await s.scalars(
                select(Handoff)
                .join(Entity, Entity.id == Handoff.entity_id)
                .where(Handoff.status == "stopped", Entity.status == EntityStatus.transferred)
            )).all()
            for row in returned:
                row.status, row.stage_index, row.next_at = "waiting", 0, None
                row.waiting_reason = row.notified_reason = None
                row.updated_at = self.clock()
            await s.commit()
        for entity_id, _ in fresh:
            logger.info("ONBOARDING handoff new entity=%s", entity_id)

    async def _check_waiting(self) -> None:
        """waiting → active, когда есть Telegram/телефон и дата выхода. До первой карточки
        следим за датой: HR мог её поправить."""
        async with self.sessions() as s:
            rows = (await s.execute(
                select(Handoff, Entity)
                .join(Entity, Entity.id == Handoff.entity_id)
                .where(
                    (Handoff.status == "waiting")
                    | ((Handoff.status == "active") & (Handoff.stage_index == 0))
                )
            )).all()
        for row, entity in rows:
            if entity.status != EntityStatus.transferred:
                continue  # остановку сделает _send_due
            extra = entity.extra_data or {}
            contact = self._contact(entity)
            first_day = _parse_date(_pick(extra, DEPT_START_KEYS))
            reason = None if contact else "no_telegram"
            reason = reason or (None if first_day else "no_first_day")
            async with self.sessions() as s:
                fresh = await s.get(Handoff, row.id)
                if reason:
                    fresh.status, fresh.waiting_reason = "waiting", reason
                    notify = fresh.notified_reason != reason
                    fresh.notified_reason = reason
                    await s.commit()
                    if notify:
                        await self._tell_hr(entity, reason)
                    continue
                if fresh.status == "active" and fresh.first_day == first_day:
                    continue
                fresh.status, fresh.waiting_reason = "active", None
                fresh.first_day = first_day
                fresh.stage_index = 0
                fresh.next_at = self._stage_time(STAGES[0], first_day)
                fresh.updated_at = self.clock()
                await s.commit()
                logger.info("ONBOARDING handoff scheduled entity=%s first_day=%s at=%s",
                            entity.id, first_day, fresh.next_at)

    async def _send_due(self) -> int:
        now = self.clock()
        async with self.sessions() as s:
            rows = (await s.execute(
                select(Handoff, Entity)
                .join(Entity, Entity.id == Handoff.entity_id)
                .where(Handoff.status == "active", Handoff.next_at <= now)
            )).all()
            # активные, у кого статус уже не «Перешёл в отдел», — стоп, не дожидаясь этапа
            gone = (await s.execute(
                select(Handoff, Entity)
                .join(Entity, Entity.id == Handoff.entity_id)
                .where(Handoff.status.in_(("active", "waiting")), Entity.status != EntityStatus.transferred)
            )).all()
        sent = 0
        for row, entity in gone:
            await self._stop(row, entity)
        stopped = {row.id for row, _ in gone}
        for row, entity in rows:
            if row.id in stopped:
                continue
            if await self._send_stage(row, entity):
                sent += 1
        return sent

    # ------------------------------------------------------------------ отправка

    async def _send_stage(self, row: Handoff, entity: Entity) -> bool:
        stage = STAGES[row.stage_index]
        account = await self._account_for(row)
        if account is None:
            await self._postpone(row, "no_account")
            return False
        text = await self._card(entity, row, stage)
        try:
            await self.messenger.send(account.tg_id, text)
        except SendError as exc:
            logger.warning("ONBOARDING handoff send failed entity=%s @%s: %s", entity.id, account.username, exc)
            await self._postpone(row, "send_failed")
            return False
        async with self.sessions() as s:
            fresh = await s.get(Handoff, row.id)
            fresh.account_id = account.id
            fresh.stage_index += 1
            fresh.waiting_reason = fresh.notified_reason = None
            fresh.updated_at = self.clock()
            if fresh.stage_index >= len(STAGES):
                fresh.status, fresh.next_at = "done", None
            else:
                fresh.next_at = self._stage_time(STAGES[fresh.stage_index], fresh.first_day)
            await s.commit()
        logger.info("ONBOARDING handoff %s entity=%s → @%s", stage.key, entity.id, account.username)
        return True

    async def _stop(self, row: Handoff, entity: Entity) -> None:
        async with self.sessions() as s:
            fresh = await s.get(Handoff, row.id)
            account = await s.get(HandoffAccount, fresh.account_id) if fresh.account_id else None
            fresh.status, fresh.next_at = "stopped", None
            fresh.updated_at = self.clock()
            await s.commit()
        if account is not None and account.tg_id:  # аккаунт уже вёл человека — пусть перестанет
            status = getattr(entity.status, "value", entity.status)
            text = "\n".join([
                "#onboarding_stop",
                f"id: {entity.id}",
                f"ФИО: {entity.name}",
                f"Telegram: {self._contact(entity) or '—'}",
                f"Причина: статус «{status}» — больше не пишем",
            ])
            try:
                await self.messenger.send(account.tg_id, text)
            except SendError as exc:
                logger.warning("ONBOARDING handoff stop not delivered entity=%s: %s", entity.id, exc)
        logger.info("ONBOARDING handoff stopped entity=%s status=%s", entity.id, entity.status)

    async def _postpone(self, row: Handoff, reason: str) -> None:
        async with self.sessions() as s:
            fresh = await s.get(Handoff, row.id)
            fresh.next_at = self.clock() + RETRY_AFTER
            notify = fresh.notified_reason != reason
            fresh.waiting_reason = fresh.notified_reason = reason
            await s.commit()
        if notify and reason == "no_account":
            await self._tell_fallback(
                "Некому передать нового сотрудника: ни один HR-аккаунт из ONBOARDING_HANDOFF_ACCOUNTS "
                "не нажал Start у бота. Передача ждёт."
            )

    async def _account_for(self, row: Handoff) -> Optional[HandoffAccount]:
        """Свой аккаунт, если человек уже закреплён; иначе подключённый, у кого меньше людей."""
        async with self.sessions() as s:
            if row.account_id:
                account = await s.get(HandoffAccount, row.account_id)
                if account and account.tg_id and account.username in self.settings.handoff_accounts:
                    return account
            load = (
                select(Handoff.account_id, func.count(Handoff.id).label("n"))
                .where(Handoff.status.in_(("active", "done")), Handoff.account_id.is_not(None))
                .group_by(Handoff.account_id)
                .subquery()
            )
            return await s.scalar(
                select(HandoffAccount)
                .outerjoin(load, load.c.account_id == HandoffAccount.id)
                .where(
                    HandoffAccount.tg_id.is_not(None),
                    HandoffAccount.username.in_(self.settings.handoff_accounts),
                )
                .order_by(func.coalesce(load.c.n, 0), HandoffAccount.id)
                .limit(1)
            )

    async def _card(self, entity: Entity, row: Handoff, stage: Stage) -> str:
        extra = entity.extra_data or {}
        department, hr = await self._department_and_hr(entity)
        lines = ["#onboarding_new" if stage.key == "first_day" else "#onboarding_stage", f"id: {entity.id}"]
        if stage.key != "first_day":
            lines.append(f"Этап: {stage.key} — {stage.title}")
        lines += [
            f"ФИО: {entity.name}",
            f"Telegram: {self._telegram(entity) or '—'}",
        ]
        phone = (entity.phone or "").strip()
        if phone:
            lines.append(f"Телефон: {phone}")
        lines += [
            f"Отдел: {department or '—'}",
            f"Лид: {_pick(extra, MANAGER_KEYS) or '—'}",
            f"Первый рабочий день: {row.first_day.strftime('%d.%m.%Y')}",
            f"Часовой пояс: {self.settings.default_tz}",
        ]
        if hr:
            lines.append(f"HR: {hr}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ помощники

    def _stage_time(self, stage: Stage, first_day: date) -> datetime:
        day = stage_day(stage, first_day)
        if self.settings.skip_weekends:
            day = sch.next_workday(day)
        at = sch.at_local(day, stage.hour, self.settings.default_tz)
        # дату выхода поставили задним числом или сегодня после 10:00 — передаём сразу, в рабочее время
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

    async def _tell_hr(self, entity: Entity, reason: str) -> None:
        text = {
            "no_telegram": (
                f"{entity.name} переведён(а) в отдел, но в карточке нет Telegram и телефона — "
                "допишите, иначе HR-аккаунт не сможет написать в первый рабочий день."
            ),
            "no_first_day": (
                f"{entity.name} переведён(а) в отдел, но не указана дата выхода в отдел — "
                "проставьте её на «Штате», от неё считаются первое сообщение и этапы онбординга."
            ),
        }[reason]
        targets = []
        if entity.created_by:
            async with self.sessions() as s:
                user = await s.get(User, entity.created_by)
            if user and user.telegram_id:
                targets.append(user.telegram_id)
        if self.settings.hr_fallback_chat_id:
            targets.append(self.settings.hr_fallback_chat_id)
        for chat_id in targets:
            try:
                await self.messenger.send(chat_id, text)
                break
            except SendError as exc:
                logger.warning("ONBOARDING handoff HR notice to %s failed: %s", chat_id, exc)
        logger.info("ONBOARDING handoff waiting entity=%s reason=%s", entity.id, reason)

    async def _tell_fallback(self, text: str) -> None:
        if not self.settings.hr_fallback_chat_id:
            logger.warning("ONBOARDING handoff: %s", text)
            return
        try:
            await self.messenger.send(self.settings.hr_fallback_chat_id, text)
        except SendError as exc:
            logger.warning("ONBOARDING handoff fallback notice failed: %s", exc)
