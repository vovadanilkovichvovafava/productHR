"""Бот в рабочих чатах (мит 19.11.2026): чат практики, вечерний отчёт, ментор, переход в отдел,
лиды, чат отдела, блокер, смена HR. Логика — api/onboarding/chat_flow.py."""

from dataclasses import dataclass, field
from datetime import date, datetime
from types import SimpleNamespace

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.models.database import BoardDepartment, Entity, EntityStatus, EntityType, User, UserRole
from api.onboarding.config import Settings
from api.onboarding.messenger import SendError
from api.onboarding.models import BotJob, CaseStatus, DepartmentLead, OnboardingCase, Signal
from api.onboarding.service import OnboardingService, first_name_of
from api.services.auth import hash_password

HR_TG, MENTOR_TG, LEAD_TG, CANDIDATE_TG, STRANGER_TG = 7001, 7002, 7003, 7100, 7999
WORK_CHAT, DEPT_CHAT, EVENTS_CHAT = -1001, -1002, -1009


@dataclass
class FakeMessenger:
    sent: list = field(default_factory=list)
    failing: set = field(default_factory=set)

    async def send(self, chat_id, text, buttons=None, html=False):
        if chat_id in self.failing:
            raise SendError("Forbidden: bot can't initiate conversation with a user")
        self.sent.append(SimpleNamespace(chat_id=chat_id, text=text, buttons=buttons))
        return len(self.sent)

    async def delete(self, chat_id, message_id):
        pass

    def to(self, chat_id):
        return [m for m in self.sent if m.chat_id == chat_id]

    def texts(self, chat_id):
        return [m.text for m in self.to(chat_id)]


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


@pytest_asyncio.fixture
async def env(async_engine, db_session, admin_user, organization, org_owner):
    admin_user.telegram_id = HR_TG
    db_session.add(User(email="egor@test.com", password_hash=hash_password("x"), name="Егор Смирнов",
                        role=UserRole.admin, is_active=True, telegram_id=MENTOR_TG, telegram_username="egor_s"))
    await db_session.commit()
    sessions = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    messenger = FakeMessenger()
    clock = Clock(datetime(2026, 11, 18, 9, 0))  # среда, 12:00 МСК
    settings = Settings(handoff_to_bot=True, bot_username="Staffwise_bot", practice_days=4,
                        hr_events_chat_id=EVENTS_CHAT, hrd="Настя")
    bot = OnboardingService(sessions, messenger, settings, None, clock)
    return SimpleNamespace(bot=bot, messenger=messenger, clock=clock, sessions=sessions, db=db_session,
                           org=organization, user=admin_user, entities={})


async def _entity_id(env, n, name):
    """Карточка в АТС под номером n теста (у onboarding_cases — внешний ключ на entities)."""
    if n not in env.entities:
        entity = Entity(org_id=env.org.id, created_by=env.user.id, name=name, type=EntityType.candidate,
                        status=EntityStatus.probation, extra_data={}, created_at=datetime.utcnow())
        env.db.add(entity)
        await env.db.commit()
        env.entities[n] = entity.id
    return env.entities[n]


def _event(entity_id, kind="practice", name="Петров Иван Сергеевич", tg="ivan_p", **extra):
    base = {"event": kind, "id": entity_id, "full_name": name, "telegram": f"@{tg}" if tg else None,
            "timezone": "Europe/Moscow"}
    if kind == "practice":
        base.update(practice_start="19.11.2026 10:00", practice_start_iso="2026-11-19T10:00",
                    practice_lead="Егор", hrd="Настя")
    if kind == "transfer":
        base.update(department="Push team", lead=None, first_day="24.11.2026", first_day_iso="2026-11-24",
                    probation_end="24.02.2027")
    base.update(extra)
    return base


async def _practice(env, n=1, **kw):
    entity_id = await _entity_id(env, n, kw.get("name", "Петров Иван Сергеевич"))
    return await env.bot.apply_handoff_event(_event(entity_id, **kw), org_id=env.org.id,
                                             created_by=env.user.id, hr_tg_id=HR_TG)


async def _transfer(env, n=1):
    return await env.bot.apply_handoff_event(_event(env.entities[n], "transfer"), org_id=env.org.id,
                                             hr_tg_id=HR_TG)


async def _fresh(env, case_id):
    async with env.sessions() as s:
        return await s.get(OnboardingCase, case_id)


async def _jobs(env, case_id, kind=None, status="pending"):
    async with env.sessions() as s:
        q = select(BotJob).where(BotJob.case_id == case_id, BotJob.status == status)
        if kind:
            q = q.where(BotJob.kind == kind)
        return list(await s.scalars(q))


# ------------------------------------------------------------------ рабочий чат практики


async def test_hr_adds_bot_chat_is_bound_and_candidate_greeted(env):
    case = await _practice(env)
    assert not await env.bot.handle_bot_added(WORK_CHAT, STRANGER_TG)  # не сотрудник — бот молчит
    assert await env.bot.handle_bot_added(WORK_CHAT, HR_TG, "Практика Петров")

    [hello] = env.messenger.to(WORK_CHAT)
    assert "рабочий чат практики Петров Иван Сергеевич" in hello.text and "@ivan_p" in hello.text
    assert hello.buttons == [[("Старт", "pstart")]]
    assert (await _fresh(env, case.id)).work_chat_id == WORK_CHAT
    assert not await env.bot.handle_bot_added(WORK_CHAT, HR_TG)  # повторно — уже привязан


async def test_two_candidates_asks_whose_chat_title_decides(env):
    first = await _practice(env, 1)
    second = await _practice(env, 2, name="Сидорова Анна", tg="anna_s")
    assert await env.bot.handle_bot_added(WORK_CHAT, HR_TG, "рабочий чат")
    [ask] = env.messenger.to(WORK_CHAT)
    assert ask.buttons == [[("Петров Иван Сергеевич", f"pchat:{first.id}")], [("Сидорова Анна", f"pchat:{second.id}")]]
    assert await env.bot.bind_chat(WORK_CHAT, second.id, STRANGER_TG) == "Выбрать кандидата может только сотрудник компании."
    assert (await env.bot.bind_chat(WORK_CHAT, second.id, MENTOR_TG)).startswith("Готово")
    assert (await _fresh(env, second.id)).work_chat_id == WORK_CHAT

    # по названию чата — без вопроса
    assert await env.bot.handle_bot_added(-2002, HR_TG, "Практика — Петров")
    assert (await _fresh(env, first.id)).work_chat_id == -2002


async def test_start_with_wrong_nick_and_rules(env):
    case = await _practice(env, tg="wrong_nick")
    await env.bot.handle_bot_added(WORK_CHAT, HR_TG)
    assert await env.bot.handle_practice_start(WORK_CHAT, MENTOR_TG, "egor_s") == "Эта кнопка — для кандидата на практику."
    assert await env.bot.handle_practice_start(WORK_CHAT, CANDIDATE_TG, "ivan_real") is None
    fresh = await _fresh(env, case.id)
    assert fresh.status == CaseStatus.practice_running.value and fresh.candidate_tg_id == CANDIDATE_TG
    rules = env.messenger.texts(WORK_CHAT)[-1]
    assert rules.startswith("Старт практики!") and "#вечерний_отчёт" in rules
    assert "Приглашение на платформу пришлёт HR" in rules and "руководителем практики Егор" in rules


async def test_evening_report_reminder_and_mentor_tag(env):
    case = await _practice(env)
    await env.bot.handle_bot_added(WORK_CHAT, HR_TG)
    await env.bot.handle_practice_start(WORK_CHAT, CANDIDATE_TG, "ivan_p")

    # день 1 (19.11): отчёт прислан — вечером тишина
    reply = await env.bot.handle_group_text(WORK_CHAT, CANDIDATE_TG, "ivan_p", "Иван", "Сделал парсер #вечерний_отчёт")
    assert reply == "Отчёт принят 👍"
    assert await env.bot.handle_group_text(WORK_CHAT, MENTOR_TG, "egor_s", "Егор", "#отчёт") is None  # не кандидат
    env.clock.now = datetime(2026, 11, 19, 7, 0)
    await env.bot.handle_group_text(WORK_CHAT, CANDIDATE_TG, "ivan_p", "Иван", "loom.com/share/abc")
    env.clock.now = datetime(2026, 11, 19, 15, 1)  # 18:01 МСК
    before = len(env.messenger.to(WORK_CHAT))
    await env.bot.run_due_jobs()
    assert len(env.messenger.to(WORK_CHAT)) == before

    # день 2 (20.11): отчёта нет — напоминание в 18:00, через час — тег ментора
    env.clock.now = datetime(2026, 11, 20, 15, 1)
    await env.bot.run_due_jobs()
    assert env.messenger.texts(WORK_CHAT)[-1].startswith("@ivan_p, напоминаю про вечерний отчёт")
    env.clock.now = datetime(2026, 11, 20, 16, 2)
    await env.bot.run_due_jobs()
    late = "@egor_s, Петров Иван Сергеевич не прислал(а) вечерний отчёт за 20.11.2026."
    assert env.messenger.texts(WORK_CHAT)[-1] == late
    assert late in env.messenger.texts(EVENTS_CHAT)
    assert [j.payload for j in await _jobs(env, case.id, "report_check")]  # остальные дни ещё впереди


async def test_no_work_chat_hr_told_once(env):
    case = await _practice(env)
    env.clock.now = datetime(2026, 11, 19, 6, 31)  # 09:31 МСК — HR: «сегодня старт»
    await env.bot.run_due_jobs()
    assert env.messenger.texts(HR_TG)[-1].startswith("Сегодня у Петров Иван Сергеевич старт практики")
    env.clock.now = datetime(2026, 11, 20, 15, 1)
    await env.bot.run_due_jobs()  # отчёты 19 и 20 — чата нет
    async with env.sessions() as s:
        told = list(await s.scalars(select(Signal).where(Signal.case_id == case.id, Signal.kind == "no_work_chat")))
    assert len(told) == 1 and "не видит рабочий чат" in told[0].text


# ------------------------------------------------------------------ лиды и переход в отдел


async def _department(env, name="Push team"):
    dept = BoardDepartment(org_id=env.org.id, name=name, kind="team")
    env.db.add(dept)
    await env.db.commit()
    return dept


async def test_lead_registers_and_gets_new_hire(env):
    dept = await _department(env)
    assert [d.name for d in await env.bot.lead_departments()] == ["Push team"]
    assert await env.bot.request_lead(LEAD_TG, "mark_lead", "Марк", dept.id) == "Запрос отправлен HR. Как подтвердят — напишу."
    [request] = env.messenger.to(HR_TG)
    assert "Марк (@mark_lead) пишет, что он(а) лид отдела Push team" in request.text
    lead_id = int(request.buttons[0][0][1].split(":")[1])
    assert await env.bot.decide_lead(lead_id, MENTOR_TG, True) == "Подтверждать лидов могут только владелец и админы HR."
    assert (await env.bot.decide_lead(lead_id, HR_TG, True)).startswith("Подтверждено")
    assert env.messenger.texts(LEAD_TG)[-1].startswith("Подтверждено: ты лид отдела Push team")
    assert await env.bot.decide_lead(lead_id, HR_TG, False) == "Запрос уже обработан."

    case = await _practice(env)
    await env.bot.handle_bot_added(WORK_CHAT, HR_TG)
    await env.bot.handle_practice_start(WORK_CHAT, CANDIDATE_TG, "ivan_p")
    env.messenger.failing.add(CANDIDATE_TG)  # бот кандидату в личку не может — поздравление в чат
    await _transfer(env)

    fresh = await _fresh(env, case.id)
    assert fresh.status == CaseStatus.transferred.value and fresh.lead_tg_id == LEAD_TG and fresh.lead_name == "Марк"
    chat = env.messenger.to(WORK_CHAT)
    congrats = next(m for m in chat if "поздравляем! Ты прошёл(ла) практику" in m.text)
    [[(label, link)]] = congrats.buttons
    assert label == "Пройти опрос" and link.startswith("https://t.me/Staffwise_bot?start=obs_p")
    assert chat[-1].text.startswith("Иван, практика закончена — поздравляем, ты переходишь в отдел Push team")
    assert env.messenger.texts(LEAD_TG)[-1].startswith("К тебе в отдел Push team переходит Петров Иван Сергеевич")

    # кандидат открыл опрос по ссылке — дальше в личке
    env.messenger.failing.discard(CANDIDATE_TG)
    assert await env.bot.handle_survey_link(CANDIDATE_TG, link.split("start=")[1])
    assert env.messenger.texts(CANDIDATE_TG)[-1].startswith("1. Насколько тебе было понятно")
    assert not await env.bot.handle_survey_link(STRANGER_TG, link.split("start=")[1])  # чужой не откроет

    # лид создал чат отдела и добавил бота — поздравление со сроками
    assert await env.bot.handle_bot_added(DEPT_CHAT, LEAD_TG)
    welcome = env.messenger.texts(DEPT_CHAT)[-1]
    assert "ты в отделе Push team" in welcome and "24.11.2026" in welcome and "24.02" in welcome
    assert (await _fresh(env, case.id)).dept_chat_id == DEPT_CHAT


async def test_transfer_without_lead_tells_hr(env):
    await _practice(env)
    await _transfer(env)
    assert any("лид отдела не подключён к боту" in t for t in env.messenger.texts(HR_TG))


async def test_lead_without_approvers(env, db_session):
    env.user.telegram_id = None
    await db_session.commit()
    dept = await _department(env)
    assert "Некому подтвердить" in await env.bot.request_lead(LEAD_TG, None, "Марк", dept.id)
    async with env.sessions() as s:
        assert (await s.scalars(select(DepartmentLead))).all() == []


# ------------------------------------------------------------------ блокер и смена HR


async def test_blocker_goes_to_hr_and_mentor(env):
    await _practice(env)
    await env.bot.handle_bot_added(WORK_CHAT, HR_TG)
    reply = await env.bot.handle_group_text(WORK_CHAT, CANDIDATE_TG, "ivan_p", "Иван",
                                            "#блокер не приходит инвайт на платформу")
    assert reply == "Передал HR и ментору @egor_s. Скоро с тобой свяжутся."
    to_hr = env.messenger.texts(HR_TG)[-1]
    assert to_hr.startswith("🚧 Блокер у Петров Иван Сергеевич (рабочий чат практики) от Иван")
    assert "не приходит инвайт" in to_hr and to_hr in env.messenger.texts(EVENTS_CHAT)
    assert await env.bot.handle_group_text(-555, CANDIDATE_TG, "ivan_p", "Иван", "#блокер") is None  # чужой чат


async def test_hr_change_pings_new_and_previous(env, db_session):
    new_hr = User(email="vlada@test.com", password_hash=hash_password("x"), name="Влада", role=UserRole.admin,
                  is_active=True, telegram_id=7300)
    db_session.add(new_hr)
    entity = Entity(org_id=env.org.id, created_by=env.user.id, name="Захаров Илья", type=EntityType.candidate,
                    status=EntityStatus.probation, extra_data={}, created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow())
    db_session.add(entity)
    await db_session.commit()
    assert await env.bot.ping_hr_changes() == 0  # первый проход — только отметка «с этого момента»

    env.clock.now = datetime(2026, 11, 18, 9, 5)
    entity.extra_data = {"hr_changes": [{"id": "abc", "at": "2026-11-18T09:03:00", "by": env.user.id,
                                         "prev": env.user.id, "new": new_hr.id}]}
    entity.updated_at = datetime(2026, 11, 18, 9, 3)
    await db_session.commit()
    assert await env.bot.ping_hr_changes() == 1  # новому HR; прежний сам и передал — ему не пишем
    msg = env.messenger.texts(7300)[-1]
    assert msg.startswith("Тебе передали кандидата Захаров Илья (было у Admin User)")
    assert msg.endswith(f"https://staffwise.club/all-candidates?entity={entity.id}")
    assert await env.bot.ping_hr_changes() == 0  # повторно не шлём


# ------------------------------------------------------------------ Telegram-обвязка


async def test_telegram_glue_group_text_lead_and_url_buttons(env, monkeypatch):
    from unittest.mock import AsyncMock

    from api.onboarding import runtime
    from api.onboarding import telegram as tg

    runtime.set_service(env.bot)
    try:
        await _practice(env)
        await env.bot.handle_bot_added(WORK_CHAT, HR_TG)
        # сообщение кандидата в группе → ответ бота реплаем
        message = SimpleNamespace(
            new_chat_members=None, chat=SimpleNamespace(id=WORK_CHAT), text="#вечерний_отчёт готово", caption=None,
            from_user=SimpleNamespace(id=CANDIDATE_TG, username="ivan_p", full_name="Иван", is_bot=False),
            reply=AsyncMock(),
        )
        await tg.on_group_message(message)
        message.reply.assert_awaited_once_with("Отчёт принят 👍")

        # /lead без отделов — подсказка
        answer = AsyncMock()
        await tg.lead_command(SimpleNamespace(answer=answer))
        answer.assert_awaited_once_with("Отделов пока нет — попроси HR завести их на «Штате».")
        assert tg.is_onboarding_token("obs_pabc") and tg.is_onboarding_token("ob_abc")
    finally:
        runtime.set_service(None)

    # url-кнопка (опрос ссылкой) и callback-кнопка в одной клавиатуре
    bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=5)))
    await tg.AiogramMessenger(bot).send(1, "x", [[("Пройти опрос", "https://t.me/b?start=obs_p1")], [("Старт", "pstart")]])
    markup = bot.send_message.await_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].url == "https://t.me/b?start=obs_p1"
    assert markup.inline_keyboard[1][0].callback_data == "pstart"


# ------------------------------------------------------------------ найдено на проде 20.11.2026


def test_texts_without_mentor_and_lead():
    from api.onboarding import texts

    rules = texts.practice_start({"practice_lead": "", "hrd": "", "platform_invite_url": ""})
    assert "руководителем практики руководитель" not in rules and "Контакты" not in rules
    assert "Это чат для связи с руководителем практики." in rules
    with_lead = texts.practice_start({"practice_lead": "Егор", "hrd": "Настя", "platform_invite_url": ""})
    assert "Контакты: руководитель практики Егор (направление и фидбек), HRD Настя (орг. вопросы)." in with_lead
    welcome = texts.dept_welcome("@ivan", "HR team", "20.11.2026", "20.02.2027", "")
    assert "лид —" not in welcome and "до 20.02.2027." in welcome
    assert "Твой лид — Марк." in texts.dept_welcome("@ivan", "SEO", "20.11.2026", "20.02.2027", "Марк")


async def test_candidate_unreachable_hr_told_once(env):
    """Не нажимал «Старт», бота нет в его чате — поздравление некуда; HR узнаёт один раз."""
    case = await _practice(env)
    await _transfer(env)
    env.clock.now = datetime(2026, 11, 24, 7, 1)  # первый день в отделе: приветствие 10:00
    await env.bot.run_due_jobs()
    async with env.sessions() as s:
        told = list(await s.scalars(select(Signal).where(Signal.case_id == case.id, Signal.kind == "no_contact")))
    assert len(told) == 1 and "Добавь бота в рабочий чат" in told[0].text


async def test_bot_mode_no_duplicate_hr_first_day(async_engine, db_session, organization, admin_user):
    from api.onboarding.handoff import HandoffService
    from api.onboarding.models import Handoff

    admin_user.telegram_id = HR_TG
    await db_session.commit()
    sessions = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    messenger, clock = FakeMessenger(), Clock(datetime(2026, 11, 18, 6, 0))
    settings = Settings(handoff_to_bot=True, bot_username="Staffwise_bot")
    bot = OnboardingService(sessions, messenger, settings, None, clock)

    async def sink():
        return bot

    handoff = HandoffService(sessions, messenger, settings, clock, bot_sink=sink)
    await handoff.tick()  # baseline по пустой базе
    entity = Entity(org_id=organization.id, created_by=admin_user.id, name="Петров Иван", type=EntityType.candidate,
                    status=EntityStatus.transferred, telegram_usernames=["ivan_p"], created_at=datetime.utcnow(),
                    extra_data={"department_transfer_date": "2026-11-18", "practice_start_date": "2026-11-17"})
    db_session.add(entity)
    await db_session.commit()
    await handoff.tick()
    async with sessions() as s:
        row = await s.scalar(select(Handoff).where(Handoff.entity_id == entity.id))
    assert row.transfer_sent_at is not None  # переход ушёл боту
    clock.now = datetime(2026, 11, 18, 7, 30)  # 10:30 МСК, первый день — передача шла бы с «day1»
    for _ in range(3):
        await handoff.tick()
    first_day = [t for t in messenger.texts(HR_TG) if "Спроси лида: установлена ли связь" in t]
    assert first_day == []  # в режиме бота «первый рабочий день» шлёт только бот, без дубля


async def test_title_picks_most_matching_name(env):
    """Прод 20.11.2026: общее слово у двух кандидатов — выбираем того, у кого совпало больше слов."""
    first = await _practice(env, 1, name="Тестбот Повтор", tg="a1")
    await _practice(env, 2, name="Тестбот Безчата", tg="a2")
    assert await env.bot.handle_bot_added(WORK_CHAT, HR_TG, "Практика Тестбот Повтор")
    assert (await _fresh(env, first.id)).work_chat_id == WORK_CHAT
    assert not any(m.buttons and m.buttons[0][0][1].startswith("pchat:") for m in env.messenger.to(WORK_CHAT))


async def test_legacy_evening_report_silent_in_onboarding_chat(env, monkeypatch):
    """Прод 20.11.2026: на #вечерний_отчёт в чате практики отвечал и старый «вечерний отчёт»."""
    from unittest.mock import AsyncMock

    import api.bot as bot_module
    from api.onboarding import runtime

    await _practice(env)
    await env.bot.handle_bot_added(WORK_CHAT, HR_TG)
    runtime.set_service(env.bot)
    try:
        summarize = AsyncMock()
        monkeypatch.setattr("api.services.evening_report.summarize_report", summarize)
        message = SimpleNamespace(chat=SimpleNamespace(id=WORK_CHAT), reply=AsyncMock(),
                                  from_user=SimpleNamespace(id=CANDIDATE_TG))
        handled = await bot_module._handle_evening_report(
            None, message, "text", "#вечерний_отчёт сделал парсер и разобрал задачу", env.org.id)
        assert handled is True
        message.reply.assert_not_called()
        summarize.assert_not_called()
    finally:
        runtime.set_service(None)


async def test_start_in_bound_chat_goes_to_its_candidate(env):
    """Прод 20.11.2026: у двух карточек один ник — «Старт» в чате первой засчитывался второй."""
    first = await _practice(env, 1, name="Тестбот Повтор", tg="same_nick")
    second = await _practice(env, 2, name="Тестбот Безчата", tg="same_nick")
    assert (await env.bot.bind_chat(WORK_CHAT, first.id, HR_TG)).startswith("Готово")
    assert await env.bot.handle_practice_start(WORK_CHAT, CANDIDATE_TG, "same_nick") is None
    assert (await _fresh(env, first.id)).candidate_tg_id == CANDIDATE_TG
    assert (await _fresh(env, second.id)).candidate_tg_id is None
    assert (await _fresh(env, second.id)).work_chat_id is None


def test_first_name_form_order():
    assert first_name_of("Тестбот Повтор") == "Повтор"
    assert first_name_of("Захаров Илья") == "Илья"
    assert first_name_of("Владимир Шинкаренко") == "Владимир"
    assert first_name_of("Яковлева Злата") == "Злата"


async def test_no_wallet_request_in_bot_mode(async_engine, db_session, admin_user, organization, org_owner):
    from cryptography.fernet import Fernet

    from api.onboarding.crypto import WalletCipher

    sessions = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    messenger, clock = FakeMessenger(), Clock(datetime(2026, 11, 18, 9, 0))
    bot = OnboardingService(sessions, messenger, Settings(handoff_to_bot=True, bot_username="b", practice_days=4),
                            WalletCipher(Fernet.generate_key().decode()), clock)
    env = SimpleNamespace(bot=bot, org=organization, user=admin_user, db=db_session, entities={},
                          sessions=sessions)
    case = await _practice(env)
    async with sessions() as s:
        fresh = await s.get(OnboardingCase, case.id)
        fresh.candidate_tg_id = CANDIDATE_TG
        await s.commit()
    await _transfer(env)
    clock.now = datetime(2026, 11, 24, 7, 1)
    await bot.run_due_jobs()
    welcome = [t for t in messenger.texts(CANDIDATE_TG) if "добро пожаловать в команду" in t]
    assert welcome and "кошел" not in welcome[0] and "  " not in welcome[0]
