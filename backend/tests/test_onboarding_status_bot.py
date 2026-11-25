"""Мит 19.11.2026: ИИ-агентов на HR-аккаунтах отложили — события по статусу АТС (handoff.py)
получает НАШ бот (OnboardingService) при ONBOARDING_HANDOFF_TO_BOT."""

from dataclasses import dataclass, field
import json
from datetime import date, datetime
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.models.database import Entity, EntityStatus, EntityType
from api.onboarding import schedule as sch
from api.onboarding.config import Settings
from api.onboarding.handoff import HandoffService
from api.onboarding.models import BotJob, CaseStatus, Handoff, OnboardingCase
from api.onboarding.service import OnboardingService, first_name_of

HR_TG = 7001


@dataclass
class FakeMessenger:
    sent: list = field(default_factory=list)

    async def send(self, chat_id, text, buttons=None, html=False):
        self.sent.append(SimpleNamespace(chat_id=chat_id, text=text, buttons=buttons))
        return len(self.sent)

    async def delete(self, chat_id, message_id):
        pass

    def to(self, chat_id):
        return [m.text for m in self.sent if m.chat_id == chat_id]


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


SETTINGS = Settings(handoff_to_bot=True, bot_username="Staffwise_bot", practice_days=4, hrd="Настя")


@pytest_asyncio.fixture
async def setup(async_engine, db_session, admin_user):
    admin_user.telegram_id = HR_TG
    await db_session.commit()
    sessions = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    messenger, clock = FakeMessenger(), Clock(datetime(2026, 11, 18, 9, 0))  # среда, 12:00 МСК
    bot = OnboardingService(sessions, messenger, SETTINGS, None, clock)

    async def sink():
        return bot

    handoff = HandoffService(sessions, messenger, SETTINGS, clock, bot_sink=sink)
    await handoff.tick()  # baseline: пустая база
    return SimpleNamespace(bot=bot, handoff=handoff, messenger=messenger, clock=clock, sessions=sessions)


async def _person(db, org, user, name="Петров Иван Сергеевич", *, status=EntityStatus.probation,
                  practice="2026-11-19", tg="ivan_p"):
    extra = {"manager_name": "Егор"}
    if practice:
        extra["practice_start_date"] = practice
    entity = Entity(org_id=org.id, created_by=user.id, name=name, type=EntityType.candidate, status=status,
                    telegram_usernames=[tg] if tg else [], extra_data=extra, created_at=datetime.utcnow())
    db.add(entity)
    await db.commit()
    return entity


async def _cases(setup, entity_id):
    async with setup.sessions() as s:
        return list(await s.scalars(select(OnboardingCase).where(OnboardingCase.entity_id == entity_id)))


async def _jobs(setup, case_id, status="pending"):
    async with setup.sessions() as s:
        return sorted(j.kind for j in await s.scalars(
            select(BotJob).where(BotJob.case_id == case_id, BotJob.status == status)))


def test_first_name_of():
    assert first_name_of("Петров Иван Сергеевич") == "Иван"
    assert first_name_of("Владимир Шинкаренко") == "Владимир"
    assert first_name_of("Захаров Илья") == "Илья"
    assert first_name_of("Яковлева Злата") == "Злата"
    assert first_name_of("тест") == "тест"
    assert first_name_of("") == ""


async def test_practice_status_creates_case_for_own_bot(setup, db_session, organization, admin_user):
    entity = await _person(db_session, organization, admin_user)
    assert await setup.handoff.tick() == 1

    [case] = await _cases(setup, entity.id)
    assert case.status == CaseStatus.practice_assigned.value
    assert (case.first_name, case.candidate_tg_username, case.hr_tg_id) == ("Иван", "ivan_p", HR_TG)
    assert case.practice_lead == "Егор" and case.created_by == admin_user.id
    assert sch.utc_to_local(case.practice_start_at, case.timezone).replace(tzinfo=None) == datetime(2026, 11, 19, 10, 0)
    assert case.practice_last_day == date(2026, 11, 24)  # 4 рабочих дня: чт, пт, пн, вт
    # в личку кандидату бот не пишет: ни «открыл ли ссылку», ни «завтра старт»
    jobs = await _jobs(setup, case.id)
    assert "invite_check" not in jobs and "day_before" not in jobs and "loom" not in jobs
    assert jobs.count("loom_chat") == 4 and "practice_deadline" in jobs and "hr_practice_start" in jobs

    # схема Маши: на статус «практика» бот HR не пишет — «создай чат» придёт за час до старта
    assert setup.messenger.to(HR_TG) == []
    async with setup.sessions() as s:
        row = await s.scalar(select(Handoff).where(Handoff.entity_id == entity.id))
    assert row.practice_sent_at is not None and row.account_id is None

    assert await setup.handoff.tick() == 0  # повтор прохода ничего не дублирует
    assert len(await _cases(setup, entity.id)) == 1


async def test_practice_date_moved_reschedules(setup, db_session, organization, admin_user):
    entity = await _person(db_session, organization, admin_user)
    await setup.handoff.tick()
    [case] = await _cases(setup, entity.id)

    entity.extra_data = {**entity.extra_data, "practice_start_date": "2026-11-23"}
    await db_session.commit()
    assert await setup.handoff.tick() == 1

    [case] = await _cases(setup, entity.id)
    assert sch.utc_to_local(case.practice_start_at, case.timezone).date() == date(2026, 11, 23)
    assert case.practice_last_day == date(2026, 11, 26)
    async with setup.sessions() as s:
        looms = sorted(json_day(j) for j in await s.scalars(
            select(BotJob).where(BotJob.case_id == case.id, BotJob.status == "pending", BotJob.kind == "loom_chat")))
    assert looms == ["2026-11-23", "2026-11-24", "2026-11-25", "2026-11-26"]
    assert "invite_check" not in await _jobs(setup, case.id, "cancelled")
    # прод 20.11.2026: в режиме бота HR-профиля нет — не «HR-профилю передано»
    moved = setup.messenger.to(HR_TG)[-1]
    assert "дата практики изменена" in moved and "напоминания бота перенесены" in moved
    assert "HR-профил" not in moved


async def test_practice_without_date_text_in_bot_mode(setup, db_session, organization, admin_user):
    """Прод 20.11.2026: «поправьте дату: HR-профиль получит новую» — в режиме бота профиля нет."""
    await _person(db_session, organization, admin_user, "Без Даты", practice=None)
    await setup.handoff.tick()
    [note] = setup.messenger.to(HR_TG)
    assert "поставлена следующим рабочим днём" in note and "бот перенесёт напоминания" in note
    assert "HR-профил" not in note


def json_day(job):
    import json
    return json.loads(job.payload)["day"]


async def test_transfer_and_stop(setup, db_session, organization, admin_user):
    entity = await _person(db_session, organization, admin_user)
    await setup.handoff.tick()

    entity.status = EntityStatus.transferred
    entity.extra_data = {**entity.extra_data, "department_transfer_date": "2026-11-24", "manager_name": "Марк"}
    await db_session.commit()
    assert await setup.handoff.tick() == 1
    [case] = await _cases(setup, entity.id)
    assert case.status == CaseStatus.transferred.value
    assert (case.department_start_date, case.probation_end_date, case.lead_name) == (
        date(2026, 11, 24), date(2027, 2, 24), "Марк")
    pending = await _jobs(setup, case.id)
    assert "loom_chat" not in pending and "first_day_welcome" not in pending and "survey" not in pending
    assert pending.count("staff_reminder") == 25  # 8–21 и Л4–Л12 схемы Маши
    hr = setup.messenger.to(HR_TG)
    assert [t for t in hr if "переведён" in t or "передан" in t] == [  # без дубля «передано»
        f"Петров Иван Сергеевич переведён в отдел, выход 24.11.2026. Поздравь, отправь опрос о практике, "
        f"передай кошелёк в бухгалтерию\nКарточка: https://staffwise.club/all-candidates?entity={entity.id}"]

    entity.status = EntityStatus.dismissed
    await db_session.commit()
    assert await setup.handoff.tick() == 1
    [case] = await _cases(setup, entity.id)
    assert case.status == CaseStatus.left.value
    assert await _jobs(setup, case.id) == []
    assert setup.messenger.to(HR_TG)[-1].startswith("Петров Иван Сергеевич уходит")
    assert "exit-интервью" in setup.messenger.to(HR_TG)[-1]


async def test_rejected_during_practice_stops_reminders(setup, db_session, organization, admin_user):
    entity = await _person(db_session, organization, admin_user)
    await setup.handoff.tick()
    entity.status = EntityStatus.rejected
    await db_session.commit()
    await setup.handoff.tick()
    [case] = await _cases(setup, entity.id)
    assert case.status == CaseStatus.failed.value
    pending = await _jobs(setup, case.id)
    assert "loom_chat" not in pending and "practice_deadline" not in pending
    assert [t.split("\n")[0] for t in setup.messenger.to(HR_TG)] == [
        "Петров Иван Сергеевич: не прошёл. Сообщи кандидату лично"]


async def test_transfer_without_practice_case(setup, db_session, organization, admin_user):
    """Практику вели до включения бота — переход в отдел всё равно заводит онбординг."""
    entity = await _person(db_session, organization, admin_user, status=EntityStatus.transferred, practice=None)
    entity.extra_data = {**entity.extra_data, "department_transfer_date": "2026-11-20"}
    await db_session.commit()
    await setup.handoff.tick()
    [case] = await _cases(setup, entity.id)
    assert case.status == CaseStatus.transferred.value and case.department_start_date == date(2026, 11, 20)


async def test_bot_off_postpones(async_engine, db_session, organization, admin_user):
    sessions = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    async def no_bot():
        return None

    handoff = HandoffService(sessions, FakeMessenger(), SETTINGS, Clock(datetime(2026, 11, 18, 9, 0)),
                             bot_sink=no_bot)
    await handoff.tick()
    entity = await _person(db_session, organization, admin_user)
    assert await handoff.tick() == 0
    async with sessions() as s:
        row = await s.scalar(select(Handoff).where(Handoff.entity_id == entity.id))
    assert row.practice_sent_at is None and row.waiting_reason == "no_bot" and row.next_at is not None


async def test_wallet_not_requested_without_key(setup, db_session, organization, admin_user):
    """Кошелёк отложили: без ключа бот его не просит и текст кандидата не забирает."""
    entity = await _person(db_session, organization, admin_user)
    await setup.handoff.tick()
    [case] = await _cases(setup, entity.id)
    async with setup.sessions() as s:
        fresh = await s.get(OnboardingCase, case.id)
        fresh.candidate_tg_id, fresh.awaiting = 555, "wallet"
        await s.commit()
    assert await setup.bot.handle_text(555, "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t") == (False, None)


@pytest.mark.parametrize("raw,expected", [("", False), ("x", True)])
def test_runtime_enabled_with_to_bot(monkeypatch, raw, expected):
    from api.onboarding import runtime

    monkeypatch.setattr("api.config.settings.telegram_bot_token", "123:abc")
    monkeypatch.setattr("api.config.settings.onboarding_wallet_key", "")
    monkeypatch.setattr("api.config.settings.onboarding_handoff_to_bot", bool(raw))
    assert runtime.enabled() is expected
    assert runtime.handoff_enabled() is expected


async def test_sheet_onboarding_schedule_and_texts(setup, db_session, organization, admin_user):
    """Схема Маши «пре:онборд»: переход в пятницу 20.11 — первый день сразу, «за день» в прошлом не шлём,
    понедельник: 2-й день; сроки ИС от даты выхода; каждое сообщение со ссылкой на карточку."""
    entity = await _person(db_session, organization, admin_user)
    await setup.handoff.tick()
    setup.clock.now = datetime(2026, 11, 20, 6, 0)  # пятница, 09:00 МСК
    entity.status = EntityStatus.transferred
    entity.extra_data = {**entity.extra_data, "department_transfer_date": "2026-11-20", "manager_name": "Марк"}
    await db_session.commit()
    await setup.handoff.tick()
    [case] = await _cases(setup, entity.id)
    async with setup.sessions() as s:
        jobs = {json.loads(j.payload)["kind"]: sch.utc_to_local(j.run_at, case.timezone).strftime("%d.%m.%Y %H:%M")
                for j in await s.scalars(select(BotJob).where(BotJob.case_id == case.id, BotJob.status == "pending"))}
    assert "s_hr_day_before" not in jobs  # 19.11 уже прошло
    assert jobs["s_hr_first_day"] == "20.11.2026 09:30" and jobs["s_lead_first_day"] == "20.11.2026 09:00"
    assert jobs["s_lead_call_done"] == "20.11.2026 15:00" and jobs["s_hr_first_day_survey"] == "20.11.2026 17:00"
    assert jobs["s_hr_check_first_day"] == "23.11.2026 10:00"  # день 2 — суббота → понедельник
    assert jobs["s_hr_week_survey"] == "25.11.2026 10:00" and jobs["s_hr_week_meeting"] == "26.11.2026 09:30"
    assert jobs["s_hr_m1_soon"] == "17.12.2026 10:00" and jobs["s_hr_m1"] == "21.12.2026 10:00"
    assert jobs["s_hr_m3_two_weeks"] == "08.02.2027 10:00" and jobs["s_hr_probation_close"] == "22.02.2027 10:00"
    assert jobs["s_hr_6m"] == "20.05.2027 10:00"

    setup.clock.now = datetime(2026, 11, 20, 6, 31)  # 09:31 — HR: первый день
    await setup.bot.run_due_jobs()
    link = f"Карточка: https://staffwise.club/all-candidates?entity={entity.id}"
    assert setup.messenger.to(HR_TG)[-1] == (
        f"Сегодня первый день Петров Иван Сергеевич. Спроси у лида (Марк) про звонок, отправь приветствие и "
        f"материалы\n{link}")
    # день 7 от 20.11 — четверг 26.11; встреча недели в тексте 11 и в 13 — один день
    assert env_day7(setup, case) == "26.11"

    # решение по ИС внесено — 18 и Л11 не приходят
    await setup.bot.decide_probation(case.id, "stays")
    setup.clock.now = datetime(2027, 2, 19, 7, 1)
    await setup.bot.run_due_jobs()
    assert not any("Нет решения лида" in t for t in setup.messenger.to(HR_TG))



async def test_practice_lead_from_mentor_tag(setup, db_session, organization, admin_user):
    """Прод 23.11.2026: ментора ставят тегом у ФИО (окно перевода, строка «Ментор»), а старое
    manager_name при этом стирается — бот не видел руководителя практики и не тегал ментора."""
    from api.services.practice_mentor import set_entity_mentor

    entity = await _person(db_session, organization, admin_user, status=EntityStatus.new)
    await set_entity_mentor(db_session, entity, "Влад", user_id=admin_user.id)
    entity.status = EntityStatus.probation
    await db_session.commit()
    assert "manager_name" not in entity.extra_data
    await setup.handoff.tick()
    [case] = await _cases(setup, entity.id)
    assert case.practice_lead == "Влад"


def env_day7(setup, case):
    return setup.bot._sheet_ctx(case)["day7"]


def test_day7_weekend_goes_to_monday():
    bot = OnboardingService(None, None, Settings(handoff_to_bot=True), None, lambda: datetime(2026, 11, 23))
    assert bot._day7(date(2026, 11, 23)).isoformat() == "2026-11-30"  # 29.11 — воскресенье
    assert bot._day7(date(2026, 11, 20)).isoformat() == "2026-11-26"
