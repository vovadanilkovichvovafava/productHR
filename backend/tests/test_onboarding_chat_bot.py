"""Бот в рабочих чатах (мит 19.11.2026): чат практики, вечерний отчёт, ментор, переход в отдел,
лиды, чат отдела, блокер, смена HR. Логика — api/onboarding/chat_flow.py."""

import dataclasses
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.models.database import (
    BoardDepartment,
    Department,
    DepartmentMember,
    DeptRole,
    Entity,
    EntityStatus,
    EntityType,
    Organization,
    OrgMember,
    OrgRole,
    User,
    UserRole,
)
from api.onboarding.config import Settings
from api.onboarding.messenger import SendError
from api.onboarding.models import BotJob, CaseStatus, DepartmentLead, OnboardingCase, Signal
from api.onboarding import texts as texts_mod
from api.onboarding.service import OnboardingService, first_name_of
from api.services.auth import hash_password

HR_TG, MENTOR_TG, LEAD_TG, CANDIDATE_TG, STRANGER_TG = 7001, 7002, 7003, 7100, 7999
WORK_CHAT, DEPT_CHAT, EVENTS_CHAT = -1001, -1002, -1009


@dataclass
class FakeMessenger:
    sent: list = field(default_factory=list)
    failing: set = field(default_factory=set)
    members: set = field(default_factory=set)  # (чат, человек) — для /demo

    async def is_member(self, chat_id, user_id):
        return (chat_id, user_id) in self.members

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


async def _member(env, tg, role=OrgRole.member, name="Сотрудник", org_id=None, **user):
    """Учётка staffwise с Telegram и участием в организации (role — роль в организации)."""
    found = await env.db.scalar(select(User).where(User.telegram_id == tg))
    if found is None:
        found = User(email=f"u{tg}@test.com", password_hash=hash_password("x"), name=name, role=UserRole.admin,
                     telegram_id=tg, **{"is_active": True, **user})
        env.db.add(found)
        await env.db.flush()
    env.db.add(OrgMember(org_id=org_id or env.org.id, user_id=found.id, role=role, created_at=datetime.utcnow()))
    await env.db.commit()
    return found


def _legacy(env):
    """Старый режим (ТЗ 03.11, ссылка HR): блокер, смена HR, «Для кого этот чат?» живут только в нём."""
    env.bot.settings = dataclasses.replace(env.bot.settings, handoff_to_bot=False)


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


async def test_hr_adds_bot_chat_is_bound_quietly(env):
    """Схема Маши: правила и инвайт шлёт HR — бот только говорит, что подключён, без «Старт»."""
    case = await _practice(env)
    assert not await env.bot.handle_bot_added(WORK_CHAT, STRANGER_TG)  # не сотрудник — бот молчит
    assert await env.bot.handle_bot_added(WORK_CHAT, HR_TG, "Практика Петров")

    assert env.messenger.to(WORK_CHAT) == []  # по листу бот при подключении в чат ничего не пишет
    assert (await _fresh(env, case.id)).work_chat_id == WORK_CHAT
    assert not await env.bot.handle_bot_added(WORK_CHAT, HR_TG)  # повторно — уже привязан
    await env.bot.handle_members_joined(WORK_CHAT, [(CANDIDATE_TG, "ivan_p")])
    assert env.messenger.to(WORK_CHAT) == []  # кандидата приветствует HR, не бот


async def test_two_candidates_sheet_silent_binds_by_candidate_message(env):
    """Лист Маши (Ильнар 26.11.2026: «убери лишнее»): «Для кого этот чат?» бот не спрашивает. Чат
    привязывается молча — по названию или когда в нём пишет кандидат."""
    first = await _practice(env, 1)
    second = await _practice(env, 2, name="Сидорова Анна", tg="anna_s")
    assert await env.bot.handle_bot_added(WORK_CHAT, HR_TG, "рабочий чат") is False
    assert env.messenger.to(WORK_CHAT) == []
    assert await env.bot.handle_group_text(WORK_CHAT, MENTOR_TG, "egor_s", "Егор", "привет") is None
    assert (await _fresh(env, first.id)).work_chat_id is None and (await _fresh(env, second.id)).work_chat_id is None
    assert await env.bot.handle_group_text(WORK_CHAT, 7700, "anna_s", "Анна", "Привет всем") is None
    fresh = await _fresh(env, second.id)
    assert fresh.work_chat_id == WORK_CHAT and fresh.candidate_tg_id == 7700
    assert env.messenger.to(WORK_CHAT) == []

    # по названию чата — без вопроса
    assert await env.bot.handle_bot_added(-2002, HR_TG, "Практика — Петров")
    assert (await _fresh(env, first.id)).work_chat_id == -2002


async def test_two_candidates_asks_whose_chat_title_decides(env):
    _legacy(env)
    first = await _practice(env, 1)
    second = await _practice(env, 2, name="Сидорова Анна", tg="anna_s")
    assert await env.bot.handle_bot_added(WORK_CHAT, HR_TG, "рабочий чат")
    ask = env.messenger.to(WORK_CHAT)[-1]
    assert ask.text == texts_mod.WHICH_CHAT
    assert ask.buttons == [[("Петров Иван Сергеевич", f"pchat:{first.id}")], [("Сидорова Анна", f"pchat:{second.id}")]]
    assert await env.bot.bind_chat(WORK_CHAT, second.id, STRANGER_TG) == "Выбрать кандидата может только сотрудник компании."
    # аудит 26.11.2026: сотрудник без HR-раздела чат к кандидату не привязывает
    assert await env.bot.bind_chat(WORK_CHAT, second.id, MENTOR_TG) == "Выбрать кандидата может только сотрудник компании."
    assert (await env.bot.bind_chat(WORK_CHAT, second.id, HR_TG)).startswith("Готово")
    assert (await _fresh(env, second.id)).work_chat_id == WORK_CHAT

    # по названию чата — без вопроса
    assert await env.bot.handle_bot_added(-2002, HR_TG, "Практика — Петров")
    assert (await _fresh(env, first.id)).work_chat_id == -2002


async def test_start_with_wrong_nick_and_rules(env):
    case = await _practice(env, tg="wrong_nick")
    await env.bot.handle_bot_added(WORK_CHAT, HR_TG)
    assert await env.bot.handle_practice_start(WORK_CHAT, MENTOR_TG, "egor_s") == "Эта кнопка для кандидата на практику."
    assert await env.bot.handle_practice_start(WORK_CHAT, CANDIDATE_TG, "ivan_real") is None
    fresh = await _fresh(env, case.id)
    assert fresh.status == CaseStatus.practice_running.value and fresh.candidate_tg_id == CANDIDATE_TG
    rules = env.messenger.texts(WORK_CHAT)[-1]
    assert rules.startswith("Старт практики!") and "#вечерний_отчёт" in rules
    assert "Приглашение на платформу HR пришлёт" in rules and "руководителем практики Егор" in rules


async def test_loom_reminder_at_20_with_buttons(env):
    """Схема Маши, уведомление 4: каждый день практики в 20:00 — Loom в рабочий чат с кнопками,
    HR не уведомляется, ментора не тегаем."""
    case = await _practice(env)
    await env.bot.handle_bot_added(WORK_CHAT, HR_TG)

    # отчёт с хэштегом — в листе его нет: бот молчит, Loom в 20:00 придёт всё равно
    assert await env.bot.handle_group_text(WORK_CHAT, CANDIDATE_TG, "ivan_p", "Иван", "Сделал #вечерний_отчёт") is None
    env.clock.now = datetime(2026, 11, 19, 17, 1)  # 20:01 МСК
    await env.bot.run_due_jobs()
    assert env.messenger.texts(WORK_CHAT)[-1] == "Время для вечернего Loom: до 5 минут, экран и голос."

    # день 2 (20.11): отчёта нет — 20:00 Loom с кнопками
    hr_before = len(env.messenger.to(HR_TG))
    env.clock.now = datetime(2026, 11, 20, 17, 1)
    await env.bot.run_due_jobs()
    loom = env.messenger.to(WORK_CHAT)[-1]
    assert loom.text == "Время для вечернего Loom: до 5 минут, экран и голос."
    assert loom.buttons == [[("Отправил(а)", "lmc:2026-11-20:sent"), ("Ещё в работе", "lmc:2026-11-20:later")]]
    assert await env.bot.handle_loom_chat(WORK_CHAT, MENTOR_TG, "egor_s", "2026-11-20", "sent") is False
    assert await env.bot.handle_loom_chat(WORK_CHAT, CANDIDATE_TG, "ivan_p", "2026-11-20", "sent") is True
    assert env.messenger.to(WORK_CHAT)[-1] is loom  # в листе только кнопки: ни «Спасибо!», ни «ждём»
    env.clock.now = datetime(2026, 11, 20, 18, 30)
    await env.bot.run_due_jobs()
    assert env.messenger.to(WORK_CHAT)[-1] is loom  # никаких тегов ментора
    assert len(env.messenger.to(HR_TG)) == hr_before  # HR про Loom не пишем
    assert len(await _jobs(env, case.id, "loom_chat")) == 2  # 21 и 24.11 ещё впереди
    assert await _jobs(env, case.id, "report_check") == []


async def test_no_work_chat_hr_told_once(env):
    case = await _practice(env)
    env.clock.now = datetime(2026, 11, 19, 6, 1)  # 09:01 МСК — за час до старта HR: «создай чат»
    await env.bot.run_due_jobs()
    assert env.messenger.texts(HR_TG)[-1] == (
        "Сегодня старт Петров Иван Сергеевич в 10:00: создай рабочий чат, добавь бота, "
        f"отправь инвайт и правила\nКарточка: https://staffwise.club/all-candidates?entity={case.entity_id}")
    env.clock.now = datetime(2026, 11, 20, 17, 1)
    await env.bot.run_due_jobs()  # Loom 19 и 20 — чата нет
    async with env.sessions() as s:
        told = list(await s.scalars(select(Signal).where(Signal.case_id == case.id, Signal.kind == "no_work_chat")))
    assert len(told) == 1 and "не видит рабочий чат" in told[0].text
    env.clock.now = datetime(2026, 11, 24, 15, 1)  # последний день практики, 18:01 — уведомление 5
    await env.bot.run_due_jobs()
    assert env.messenger.texts(HR_TG)[-1].startswith(
        "Решение по Петров Иван Сергеевич: уточни дату старта и переведи в отдел. В АТС откроется модальное "
        "окно с отделом (Telegram лида подтягивается)")


# ------------------------------------------------------------------ лиды и переход в отдел


async def _department(env, name="Push team"):
    dept = BoardDepartment(org_id=env.org.id, name=name, kind="team")
    env.db.add(dept)
    await env.db.commit()
    return dept


async def test_lead_registers_and_gets_new_hire(env):
    dept = await _department(env)
    await _member(env, LEAD_TG, name="Марк")  # лид — сотрудник без HR-раздела
    assert [d.name for d in await env.bot.lead_departments(LEAD_TG)] == ["Push team"]
    assert await env.bot.request_lead(LEAD_TG, "mark_lead", "Марк", dept.id) == "Запрос ушёл HR. Как подтвердят, напишу."
    assert await env.bot.request_lead(LEAD_TG, "mark_lead", "Марк", dept.id) == texts_mod.LEAD_PENDING  # без повторов
    [request] = env.messenger.to(HR_TG)
    assert "Марк (@mark_lead) называет себя лидом отдела Push team" in request.text
    lead_id = int(request.buttons[0][0][1].split(":")[1])
    assert await env.bot.decide_lead(lead_id, MENTOR_TG, True) == "Подтверждать лидов могут только владелец и админы HR."
    assert (await env.bot.decide_lead(lead_id, HR_TG, True)).startswith("Подтверждено")
    assert env.messenger.texts(LEAD_TG)[-1].startswith("Подтверждено, ты лид отдела Push team")
    assert await env.bot.decide_lead(lead_id, HR_TG, False) == "Запрос уже обработан."

    case = await _practice(env)
    await env.bot.handle_bot_added(WORK_CHAT, HR_TG)
    await env.bot.handle_group_text(WORK_CHAT, CANDIDATE_TG, "ivan_p", "Иван", "привет")
    chat_before = len(env.messenger.to(WORK_CHAT))
    await _transfer(env)

    fresh = await _fresh(env, case.id)
    assert fresh.status == CaseStatus.transferred.value and fresh.lead_tg_id == LEAD_TG and fresh.lead_name == "Марк"
    # схема Маши: кандидату и в чат практики бот ничего не пишет — поздравляет HR
    assert len(env.messenger.to(WORK_CHAT)) == chat_before and env.messenger.to(CANDIDATE_TG) == []
    link = f"https://staffwise.club/all-candidates?entity={case.entity_id}"
    assert (f"Петров Иван Сергеевич переведён в Push team, выход 24.11.2026. Поздравь, отправь опрос "
            f"о практике, передай кошелёк в бухгалтерию\nКарточка: {link}") in env.messenger.texts(HR_TG)
    assert env.messenger.texts(LEAD_TG)[-1] == (
        "Петров Иван Сергеевич выходит к тебе в Push team 24.11.2026. Проведи онбординг: создай чат отдела, "
        f"свяжись с сотрудником, назначь онбординг-звонок на первый день\nКарточка: {link}")

    # лид создал чат отдела и добавил бота — бот там не нужен, молчит
    assert not await env.bot.handle_bot_added(DEPT_CHAT, LEAD_TG)
    assert env.messenger.to(DEPT_CHAT) == []


async def test_transfer_without_lead_tells_hr(env):
    await _practice(env)
    await _transfer(env)
    assert any("бот не знает, кто лид отдела" in t for t in env.messenger.texts(HR_TG))


async def _org_dept_with_leads(env, *leads):
    """«Управление → Отделы»: отдел с лидами [(имя, telegram_id)]."""
    org_dept = Department(org_id=env.org.id, name="RND отдел")
    env.db.add(org_dept)
    await env.db.flush()
    for i, (name, tg) in enumerate(leads):
        user = User(email=f"lead{i}@test.com", password_hash=hash_password("x"), name=name,
                    role=UserRole.admin, is_active=True, telegram_id=tg)
        env.db.add(user)
        await env.db.flush()
        env.db.add(DepartmentMember(department_id=org_dept.id, user_id=user.id, role=DeptRole.lead))
    await env.db.commit()
    return org_dept


async def test_leads_come_from_org_department_without_lead_command(env):
    """Ильнар, 23.11.2026: «там же всё через базу берётся» — лиды из «Управление → Отделы»,
    связь у песочницы, команда наследует; оба лида получают нового сотрудника, /lead не нужен."""
    org_dept = await _org_dept_with_leads(env, ("Владимир", LEAD_TG), ("Ильнар", 7004))
    sandbox = BoardDepartment(org_id=env.org.id, name="SANDBOX R&D", kind="sandbox", org_department_id=org_dept.id)
    env.db.add(sandbox)
    await env.db.flush()
    env.db.add(BoardDepartment(org_id=env.org.id, name="Push team", kind="team", parent_id=sandbox.id))
    await env.db.commit()

    case = await _practice(env)
    await _transfer(env)
    fresh = await _fresh(env, case.id)
    assert fresh.lead_name == "Владимир, Ильнар" and fresh.lead_tg_ids == [LEAD_TG, 7004]
    for tg in (LEAD_TG, 7004):
        assert env.messenger.texts(tg)[-1].startswith("Петров Иван Сергеевич выходит к тебе в Push team")
    assert not any("бот не знает, кто лид" in t for t in env.messenger.texts(HR_TG))
    # кандидату — обоих в нужном числе (прод 23.11.2026: «Руководитель Владимир, Ильнар свяжется»)
    ctx = env.bot._ctx(fresh)
    assert "Руководители Владимир и Ильнар свяжутся с тобой." in texts_mod.CONGRATS.format(**ctx)
    assert "руководители Владимир и Ильнар познакомят" in texts_mod.FIRST_DAY_WELCOME.format(**ctx)
    reminders = await _jobs(env, case.id, "staff_reminder")
    assert any(j.payload == '{"kind": "s_hr_day_before"}' for j in reminders)  # «в нужном числе»: Лиды: …
    assert env.bot._sheet_ctx(fresh)["lid"] == "Владимир и Ильнар"  # {лид} листа как есть


async def test_org_lead_unreachable_tells_hr_to_rebind(env):
    """Прод 23.11.2026: у Владимира к staffwise привязан старый Telegram — «chat not found».
    HR должен понять, что перепривязать Telegram надо лиду, а не править карточку кандидата."""
    org_dept = await _org_dept_with_leads(env, ("Владимир", LEAD_TG), ("Ильнар", 7004))
    env.db.add(BoardDepartment(org_id=env.org.id, name="Push team", kind="team", org_department_id=org_dept.id))
    await env.db.commit()
    env.messenger.failing.add(LEAD_TG)
    await _practice(env)
    await _transfer(env)
    warn = [t for t in env.messenger.texts(HR_TG) if "не получил сообщение о новом сотруднике" in t]
    assert len(warn) == 1 and "Лид Владимир не получил" in warn[0] and "Пусть Владимир откроет staffwise" in warn[0]
    assert "карточке" not in warn[0]
    assert env.messenger.texts(7004)[-1].startswith("Петров Иван Сергеевич выходит к тебе в Push team")


async def test_org_lead_without_telegram_tells_hr(env):
    org_dept = await _org_dept_with_leads(env, ("Николай", None))
    env.db.add(BoardDepartment(org_id=env.org.id, name="Push team", kind="team", org_department_id=org_dept.id))
    await env.db.commit()
    await _practice(env)
    await _transfer(env)
    assert any("Лид Николай не привязал Telegram к staffwise" in t for t in env.messenger.texts(HR_TG))


async def test_lead_without_approvers(env, db_session):
    env.user.telegram_id = None
    await db_session.commit()
    dept = await _department(env)
    await _member(env, LEAD_TG, name="Марк")
    assert "Подтвердить некому" in await env.bot.request_lead(LEAD_TG, None, "Марк", dept.id)
    async with env.sessions() as s:
        assert (await s.scalars(select(DepartmentLead))).all() == []


# ------------------------------------------------------------------ блокер и смена HR


async def test_sheet_no_blocker(env):
    """Лист Маши: блокера в нём нет — #блокер и /blocker бот не пересылает и в чат не отвечает."""
    await _practice(env)
    await env.bot.handle_bot_added(WORK_CHAT, HR_TG)
    hr_before = len(env.messenger.to(HR_TG))
    for text in ("#блокер не приходит инвайт", "/blocker нет доступа", "/blocker"):
        assert await env.bot.handle_group_text(WORK_CHAT, CANDIDATE_TG, "ivan_p", "Иван", text) is None
    assert len(env.messenger.to(HR_TG)) == hr_before and env.messenger.to(WORK_CHAT) == []


async def test_blocker_goes_to_hr_and_mentor(env):
    _legacy(env)
    await _practice(env)
    await env.bot.handle_bot_added(WORK_CHAT, HR_TG)
    reply = await env.bot.handle_group_text(WORK_CHAT, CANDIDATE_TG, "ivan_p", "Иван",
                                            "#блокер не приходит инвайт на платформу")
    assert reply == "Передал HR и ментору @egor_s. Скоро с тобой свяжутся."
    to_hr = env.messenger.texts(HR_TG)[-1]
    assert to_hr.startswith("🚧 Блокер у Петров Иван Сергеевич (рабочий чат практики) от Иван")
    assert "не приходит инвайт" in to_hr and to_hr in env.messenger.texts(EVENTS_CHAT)
    assert await env.bot.handle_group_text(-555, CANDIDATE_TG, "ivan_p", "Иван", "#блокер") is None  # чужой чат


async def test_blocker_command(env):
    """Мит 24.11.2026: блокер — командой /blocker. С текстом — сразу HR; без текста — бот спрашивает,
    следующее сообщение того же человека уходит HR. Старый режим: в листе Маши блокера нет."""
    _legacy(env)
    await _practice(env)
    await env.bot.handle_bot_added(WORK_CHAT, HR_TG)
    reply = await env.bot.handle_group_text(WORK_CHAT, CANDIDATE_TG, "ivan_p", "Иван",
                                            "/blocker@Staffwise_bot нет доступа к кабинету")
    assert reply.startswith("Передал HR")
    assert env.messenger.texts(HR_TG)[-1].endswith("от Иван:\nнет доступа к кабинету")

    sent = len(env.messenger.texts(HR_TG))
    assert await env.bot.handle_group_text(WORK_CHAT, CANDIDATE_TG, "ivan_p", "Иван", "/blocker") == texts_mod.BLOCKER_ASK
    assert len(env.messenger.texts(HR_TG)) == sent  # пустой блокер HR не уходит
    assert await env.bot.handle_group_text(WORK_CHAT, MENTOR_TG, "egor_s", "Егор", "сейчас гляну") is None  # другой человек
    reply = await env.bot.handle_group_text(WORK_CHAT, CANDIDATE_TG, "ivan_p", "Иван", "не открывается Loom")
    assert reply.startswith("Передал HR") and env.messenger.texts(HR_TG)[-1].endswith("\nне открывается Loom")
    assert await env.bot.handle_group_text(WORK_CHAT, CANDIDATE_TG, "ivan_p", "Иван", "спасибо") is None  # уже не блокер

    await env.bot.handle_group_text(WORK_CHAT, CANDIDATE_TG, "ivan_p", "Иван", "/blocker")
    env.clock.now += timedelta(minutes=20)  # описание пришло слишком поздно — это обычное сообщение
    assert await env.bot.handle_group_text(WORK_CHAT, CANDIDATE_TG, "ivan_p", "Иван", "всё, разобрался") is None


async def test_sheet_no_hr_change_ping(env, db_session):
    """Лист Маши: уведомления о смене HR в нём нет."""
    entity = Entity(org_id=env.org.id, created_by=env.user.id, name="Захаров Илья", type=EntityType.candidate,
                    status=EntityStatus.probation, extra_data={}, created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow())
    db_session.add(entity)
    await db_session.commit()
    assert await env.bot.ping_hr_changes() == 0
    env.clock.now = datetime(2026, 11, 18, 9, 5)
    entity.extra_data = {"hr_changes": [{"id": "abc", "at": "2026-11-18T09:03:00", "by": env.user.id,
                                         "prev": env.user.id, "new": env.user.id}]}
    entity.updated_at = datetime(2026, 11, 18, 9, 3)
    await db_session.commit()
    assert await env.bot.ping_hr_changes() == 0
    assert env.messenger.sent == []


async def test_hr_change_pings_new_and_previous(env, db_session):
    _legacy(env)
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
    assert msg.startswith("Тебе передали кандидата Захаров Илья (прежний HR: Admin User)")
    assert msg.endswith(f"https://staffwise.club/all-candidates?entity={entity.id}")
    assert await env.bot.ping_hr_changes() == 0  # повторно не шлём


async def test_hr_change_moves_bot_signals_to_new_hr(env, db_session):
    """Прод 24.11.2026: после «Сменить HR» блокер и сигналы перехода уходили прежнему HR. Старый режим."""
    _legacy(env)
    new_hr = User(email="masha@test.com", password_hash=hash_password("x"), name="Мария", role=UserRole.admin,
                  is_active=True, telegram_id=7400)
    db_session.add(new_hr)
    await db_session.commit()
    case = await _practice(env)
    await env.bot.handle_bot_added(WORK_CHAT, HR_TG)
    assert await env.bot.ping_hr_changes() == 0
    entity = await db_session.get(Entity, case.entity_id)
    env.clock.now += timedelta(minutes=5)
    entity.extra_data = {"hr_changes": [{"id": "x1", "at": env.clock.now.isoformat(), "by": env.user.id,
                                         "prev": env.user.id, "new": new_hr.id}]}
    entity.updated_at = env.clock.now
    await db_session.commit()
    await env.bot.ping_hr_changes()
    assert (await _fresh(env, case.id)).hr_tg_id == 7400
    await env.bot.handle_group_text(WORK_CHAT, CANDIDATE_TG, "ivan_p", "Иван", "#блокер нет доступа")
    assert env.messenger.texts(7400)[-1].startswith("🚧 Блокер у")
    assert not any(t.startswith("🚧") for t in env.messenger.texts(HR_TG))


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
        message.reply.assert_not_awaited()  # по листу на отчёт бот не отвечает
        message.text = "/blocker нет доступа"
        await tg.on_group_message(message)
        message.reply.assert_not_awaited()  # в листе Маши блокера нет

        # /lead без отделов — подсказка
        answer = AsyncMock()
        await tg.lead_command(SimpleNamespace(answer=answer, from_user=SimpleNamespace(id=HR_TG)))
        answer.assert_awaited_once_with("Отделов пока нет. Попроси HR завести их на Штате.")
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
    assert "ты на связи с руководителем практики. " in rules
    with_lead = texts.practice_start({"practice_lead": "Егор", "hrd": "Настя", "platform_invite_url": ""})
    assert "Контакты: руководитель практики Егор, по задачам и обратной связи; HRD Настя, по организационным вопросам." in with_lead
    welcome = texts.dept_welcome("@ivan", "HR team", "20.11.2026", "20.02.2027", "")
    assert "лид —" not in welcome and "до 20.02.2027." in welcome
    assert "Твой лид: Марк." in texts.dept_welcome("@ivan", "SEO", "20.11.2026", "20.02.2027", "Марк")
    assert "Твои лиды: Владимир и Ильнар." in texts.dept_welcome("@ivan", "SEO", "20.11.2026", "20.02.2027",
                                                               "Владимир, Ильнар")
    assert texts.lead_phrases("")["lead_contact"] == "Руководитель свяжется с тобой."
    assert texts.lead_phrases("Марк")["lead_intro"] == "руководитель Марк познакомит"
    assert texts.join_names(["Мария", "Анастасия", "Егор"]) == "Мария, Анастасия и Егор"


async def test_candidate_unreachable_nothing_to_tell(env):
    """Схема Маши: кандидату бот после перевода не пишет — и «бот не может написать кандидату» HR не шлёт."""
    case = await _practice(env)
    await _transfer(env)
    env.clock.now = datetime(2026, 11, 24, 7, 1)
    await env.bot.run_due_jobs()
    async with env.sessions() as s:
        told = list(await s.scalars(select(Signal).where(Signal.case_id == case.id, Signal.kind == "no_contact")))
    assert told == []


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


async def test_full_name_in_title_beats_adders_own_cases(env):
    """Прод 24.11.2026: лид R&D добавил бота в «Практика Тестбот Владимир» — кандидат не его (HR другой),
    а у самого лида в отделе «Тестбот Практика». Бот привязал чат к отделу и поздравил не того."""
    await _member(env, MENTOR_TG, role=OrgRole.hr)  # лид R&D с HR-разделом (на проде — суперадмин)
    own = await _practice(env, 1, name="Тестбот Практика", tg="a1")
    await _transfer(env, 1)
    async with env.sessions() as s:
        case = await s.get(OnboardingCase, own.id)
        case.lead_tg_ids = [MENTOR_TG]  # добавляет лид отдела, он же сотрудник
        await s.commit()
    entity_id = await _entity_id(env, 2, "Тестбот Владимир")
    other = await env.bot.apply_handoff_event(_event(entity_id, name="Тестбот Владимир", tg="a2"), org_id=env.org.id,
                                              created_by=env.user.id, hr_tg_id=LEAD_TG)
    assert await env.bot.handle_bot_added(WORK_CHAT, MENTOR_TG, "Практика Тестбот Владимир")
    assert (await _fresh(env, other.id)).work_chat_id == WORK_CHAT
    assert (await _fresh(env, own.id)).dept_chat_id is None
    assert not any("ты в отделе" in m.text for m in env.messenger.to(WORK_CHAT))


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
    assert messenger.to(CANDIDATE_TG) == []  # схема Маши: приветствие и материалы отправляет HR

async def test_preview_sends_every_sheet_message(env):
    """/preview: все уведомления схемы Маши по очереди в чат, где попросили; только сотруднику."""
    import asyncio

    case = await _practice(env)
    env.bot.preview_pause = 0
    assert await env.bot.preview_sheet(-777, STRANGER_TG) is None
    reply = await env.bot.preview_sheet(-777, HR_TG)
    assert reply.startswith("Предпросмотр по листу «пре:онборд» на примере Петров Иван Сергеевич: 32 сообщения")
    await asyncio.gather(*env.bot._preview_tasks)
    sent = env.messenger.to(-777)
    assert len(sent) == 32
    labels = [m.text.split("]")[0] + "]" for m in sent]
    assert labels[:6] == ["[3]", "[4]", "[5]", "[6]", "[Л2]", "[7]"] and labels[-1] == "[Л12]"
    assert sent[1].buttons[0][0][1].startswith("lmc:2026-11-19:")
    link = f"https://staffwise.club/all-candidates?entity={case.entity_id}"
    for m in sent:
        assert "{" not in m.text and "  " not in m.text
        assert m.text.endswith(link) or m.text.startswith("[4]")
    assert all("отдел ," not in m.text and "отделе ." not in m.text for m in sent)  # отдела ещё нет
    assert "выход 25.11.2026" in sent[3].text  # практика до 24.11 — выход на следующий рабочий день


async def test_demo_is_a_natural_run(env):
    """/demo: ход кандидата как в жизни, быстро — заголовки разделов листа, Loom в беседу, HR и лиду в личку
    все уведомления листа тем же текстом; только тем, кто в беседе."""
    import asyncio

    org_dept = await _org_dept_with_leads(env, ("Владимир", LEAD_TG), ("Ильнар", 7004))
    env.db.add(DepartmentMember(department_id=org_dept.id, user_id=env.user.id, role=DeptRole.lead))
    await env.db.commit()  # HR кандидата — ещё и лид своего отдела: в демо он только HR
    case = await _practice(env, tg="admin_tg")  # тестовая карточка: кандидат — сам HR на своём Telegram
    await env.bot.handle_bot_added(WORK_CHAT, HR_TG)
    env.messenger.members = {(WORK_CHAT, HR_TG), (WORK_CHAT, LEAD_TG)}  # Ильнара в беседе нет
    env.bot.preview_pause = 0
    assert await env.bot.demo_sheet(WORK_CHAT, STRANGER_TG) is None
    before = len(env.messenger.to(WORK_CHAT))
    assert await env.bot.demo_sheet(WORK_CHAT, HR_TG, "admin_tg") is None  # в беседу — ни слова от себя
    await asyncio.gather(*env.bot._preview_tasks)

    chat = env.messenger.to(WORK_CHAT)[before:]
    texts_in_chat = [m.text for m in chat]
    assert texts_in_chat[0].startswith(f"Демо: путь кандидата {case.full_name}")
    assert "В личку получат: HR — Admin User; лид — Владимир." in texts_in_chat[0]
    # сначала раздел листа его словами, потом действия
    assert texts_in_chat[1] == "Сценарий 1 из 8 — Практика (пребординг)"
    assert texts_in_chat[2] == "Время для вечернего Loom: до 5 минут, экран и голос." and chat[2].buttons
    assert texts_in_chat[3].startswith("Сценарий 2 из 8 — Переход в отдел\n\nРешение лид пишет в рабочем чате")
    assert texts_in_chat[-2] == "Сценарий 8 из 8 — Статус «мы уволили» и “сам уволился”(в любой момент)"
    assert texts_in_chat[-1] == "Демо закончено."
    assert len(chat) == 11  # вступление, 8 разделов, Loom, конец
    hr, lead = env.messenger.texts(HR_TG), env.messenger.texts(LEAD_TG)
    assert len(hr) == 19 and len(lead) == 12  # все уведомления листа: 3, 5–21 и Л2–Л12
    assert not any(t.startswith("[") for t in hr + lead)
    link = f"https://staffwise.club/all-candidates?entity={case.entity_id}"
    assert all(t.endswith(link) for t in hr + lead)
    assert hr[0].startswith("Сегодня старт Петров Иван Сергеевич в 10:00")
    assert hr[-1].startswith("Петров Иван Сергеевич уходит: проведи exit-интервью и заполни причину")
    assert env.messenger.texts(7004) == []


async def test_demo_in_unbound_chat_uses_own_case(env):
    """Проверочный чат без кандидата: пример — своя карточка, в личку только тем, кто в беседе."""
    import asyncio

    await _practice(env)
    env.messenger.members = {(-555, HR_TG)}
    env.bot.preview_pause = 0
    assert await env.bot.demo_sheet(-555, HR_TG, "admin_tg") is None
    await asyncio.gather(*env.bot._preview_tasks)
    assert len(env.messenger.texts(HR_TG)) == 31  # проверочная беседа: запустивший — и HR, и лид
    assert "В личку получат: HR — Admin User; лид — Admin User." in env.messenger.texts(-555)[0]



async def test_demo_and_preview_refused_where_candidate_sits(env):
    """Прод 25.11.2026: служебные строки демо видел бы кандидат — в его беседе /demo и /preview не идут."""
    await _practice(env)
    await env.bot.handle_bot_added(WORK_CHAT, HR_TG)
    env.bot.preview_pause = 0
    refused = texts_mod.DEMO_CANDIDATE_HERE.format(cmd="/demo")
    assert await env.bot.demo_sheet(WORK_CHAT, HR_TG, "admin_tg") == refused  # кандидат @ivan_p, мог прочесть
    await env.bot.handle_group_text(WORK_CHAT, CANDIDATE_TG, "ivan_p", "Иван", "привет")  # бот узнал его id
    env.messenger.members = {(WORK_CHAT, HR_TG), (WORK_CHAT, CANDIDATE_TG)}
    assert await env.bot.preview_sheet(WORK_CHAT, HR_TG, "admin_tg") == texts_mod.DEMO_CANDIDATE_HERE.format(cmd="/preview")
    env.messenger.members = {(WORK_CHAT, HR_TG)}  # кандидат вышел из беседы
    assert await env.bot.demo_sheet(WORK_CHAT, HR_TG, "admin_tg") is None  # запустилось


async def test_legacy_jobs_switch_to_sheet(env):
    """Прод 25.11.2026: у кандидата, переведённого утром по старой схеме, остались её задачи — Маше ушло
    старое «всё ли понятно». В режиме листа старая задача ничего не шлёт: снимает старые, ставит задачи листа."""
    import json

    case = await _practice(env)
    await _transfer(env)  # выход 24.11
    async with env.sessions() as s:
        for job in await s.scalars(select(BotJob).where(BotJob.case_id == case.id, BotJob.status == "pending")):
            job.status = "cancelled"
        s.add_all([
            BotJob(case_id=case.id, kind="survey", run_at=datetime(2026, 11, 24, 15, 0), payload='{"kind": "first_day"}'),
            BotJob(case_id=case.id, kind="staff_reminder", run_at=datetime(2026, 11, 24, 9, 0),
                   payload='{"kind": "hr_first_day"}'),
            BotJob(case_id=case.id, kind="staff_reminder", run_at=datetime(2026, 11, 30, 7, 0),
                   payload='{"kind": "hr_call_week"}'),
        ])
        await s.commit()
    sent = len(env.messenger.sent)
    env.clock.now = datetime(2026, 11, 24, 15, 1)  # 18:01 МСК в первый день
    await env.bot.run_due_jobs()
    assert len(env.messenger.sent) == sent  # ни старого опроса кандидату, ни «всё ли понятно» HR
    kinds = [json.loads(j.payload)["kind"] for j in await _jobs(env, case.id)]
    assert "hr_call_week" not in kinds and "s_hr_check_first_day" in kinds and "s_hr_first_day" not in kinds


# Итоговая таблица листа Маши «пре:онборд» (Google Doc, 25.11.2026), как есть — с подстановками листа.
SHEET_TABLE = [
    "Сегодня старт {Имя} в 10:00: создай рабочий чат, добавь бота, отправь инвайт и правила",  # 3
    "Время для вечернего Loom: до 5 минут, экран и голос.",  # 4
    "Решение по {Имя}: уточни дату старта и переведи в отдел. В АТС откроется модальное окно с отделом "
    "(Telegram лида подтягивается)",  # 5
    "{Имя} переведён в {отдел}, выход {дата}. Поздравь, отправь опрос о практике, передай кошелёк в бухгалтерию",  # 6
    "{Имя} выходит к тебе в {отдел} {дата}. Проведи онбординг: создай чат отдела, свяжись с сотрудником, назначь "
    "онбординг-звонок на первый день",  # Л2
    "{Имя}: не прошёл. Сообщи кандидату лично",  # 7
    "Завтра {Имя} выходит в {отдел}. Уточни у {лид}: чат, связь, онбординг-звонок",  # 8
    "Завтра в 10:00 к тебе выходит {Имя}. Не забудь связаться и начать онбординг: чат, доступы, онбординг-звонок",  # Л4
    "Сегодня в 10:00 старт {Имя}. Онбординг-звонок: продукт, задачи, цели на ИС, KPI, как устроена работа, "
    "наставник, доступы",  # Л5
    "Сегодня первый день {Имя}. Спроси у {лид} про звонок, отправь приветствие и материалы",  # 9
    "Онбординг-звонок с {Имя} состоялся? Проверь доступы и первую задачу",  # Л6
    "Отправь {Имя} опрос первого дня",  # 10
    "Проверь ответы опроса первого дня и запланируй встречу недели на {дата дня 7}",  # 11
    "Цели и KPI на ИС с {Имя} обсудили? Если нет — назначь встречу до конца недели",  # Л7
    "Отправь {Имя} опрос недели",  # 12
    "Сегодня встреча недели с {Имя}. Посмотри ответы опроса",  # 13
    "Через 3 дня точка 1 месяца у {Имя}: опрос, обратная связь {лид}, one-to-one",  # 14
    "Через 3 дня 1 месяц работы {Имя}. Подготовь обратную связь по шкале и передай HR",  # Л8
    "Сегодня one-to-one с {Имя}. Оценка лида внесена?",  # 15
    "Нужна твоя оценка за 1 месяц {Имя}, передай HR сегодня",  # Л9
    "Через 3 дня точка 2 месяца у {Имя}: опрос, обратная связь {лид}, one-to-one",  # 16 «как 14, для 2-го месяца»
    "Через 3 дня 2 месяц работы {Имя}. Подготовь обратную связь по шкале и передай HR",  # Л8
    "Сегодня one-to-one с {Имя}. Оценка лида внесена?",  # 16 «как 15»
    "Нужна твоя оценка за 2 месяц {Имя}, передай HR сегодня",  # Л9
    "До конца ИС {Имя} 2 недели: опрос месяца 3, оценка и решение {лид}, встреча втроём, договор и NDA",  # 17
    "До конца ИС {Имя} 2 недели. Подготовь итоговую оценку и решение, HR назначит встречу втроём",  # Л10
    "Нет решения лида по {Имя}, ИС заканчивается {конец ИС}",  # 18
    "Нужно твоё решение по ИС {Имя} до {конец ИС}",  # Л11
    "Сегодня закрытие ИС {Имя}. Внеси решение в АТС",  # 19
    "{Имя} уходит: проведи exit-интервью и заполни причину",  # 20
    "6 месяцев у {Имя}: запроси оценку у {лид}",  # 21
    "6 месяцев работы {Имя}: оцени результат и передай HR",  # Л12
]


async def test_sheet_texts_match_doc_word_for_word(env):
    """Ильнар 25.11.2026: «всё должно быть 1 в 1 … слово в слово сверяйся по этому тз от Маши»."""
    org_dept = await _org_dept_with_leads(env, ("Владимир", LEAD_TG))
    env.db.add(BoardDepartment(org_id=env.org.id, name="Push team", kind="team", org_department_id=org_dept.id))
    await env.db.commit()
    case = await _practice(env)
    await _transfer(env)  # выход 24.11.2026 (вт), ИС до 24.02.2027
    case = await _fresh(env, case.id)
    fill = {"{Имя}": "Петров Иван Сергеевич", "{отдел}": "Push team", "{дата}": "24.11.2026",
            "{лид}": "Владимир", "{дата дня 7}": "30.11", "{конец ИС}": "24.02.2027"}
    link = f"\nКарточка: https://staffwise.club/all-candidates?entity={case.entity_id}"
    expected = []
    for i, line in enumerate(SHEET_TABLE):
        for key, value in fill.items():
            line = line.replace(key, value)
        expected.append(line if i == 1 else line + link)  # 4 — кандидату в чат, без ссылки
    got = [text for _, _, _, text, _ in env.bot.sheet_plan(case)]
    assert got == expected


# ------------------------------------------------------------------ аудит безопасности 26.11.2026


async def test_audit_preview_demo_only_for_hr_of_the_org(env):
    """«Сотрудником» бот считал любого с привязанным Telegram: сотрудник без HR-раздела, человек из другой
    организации или с закрытым входом через /preview и /demo получал ФИО, даты и ссылки карточек."""
    await _practice(env)
    await _member(env, MENTOR_TG)  # обычный сотрудник (member)
    other_org = Organization(name="Other", slug="other", created_at=datetime.utcnow())
    env.db.add(other_org)
    await env.db.commit()
    await _member(env, 7500, role=OrgRole.owner, org_id=other_org.id)  # HR чужой организации
    await _member(env, 7501, role=OrgRole.hr, is_active=False)  # отключённая учётка
    for tg in (MENTOR_TG, 7500, 7501, STRANGER_TG):
        assert await env.bot.preview_sheet(-3001, tg) in (None, texts_mod.PREVIEW_NO_CASE)
        assert await env.bot.demo_sheet(-3001, tg) in (None, texts_mod.DEMO_NO_CASE)
    assert env.messenger.sent == []
    assert env.messenger.to(7500) == [] and env.messenger.to(MENTOR_TG) == []
    assert (await env.bot.preview_sheet(-3001, HR_TG)).startswith("Предпросмотр")  # своя HR — можно


async def test_audit_member_cannot_hijack_candidate_chat(env):
    """Сотрудник без HR-раздела назвал свою группу именем кандидата и добавил бота — чат не привязывается."""
    case = await _practice(env)
    await _member(env, MENTOR_TG)
    assert not await env.bot.handle_bot_added(-3002, MENTOR_TG, "Практика Петров Иван Сергеевич")
    assert (await _fresh(env, case.id)).work_chat_id is None
    assert await env.bot.handle_bot_added(WORK_CHAT, HR_TG, "Практика Петров Иван Сергеевич")
    assert (await _fresh(env, case.id)).work_chat_id == WORK_CHAT


async def test_audit_lead_command_only_for_staff(env):
    """/lead мог нажать посторонний: видел отделы всех организаций и засыпал админов запросами."""
    dept = await _department(env)
    assert await env.bot.lead_departments(STRANGER_TG) is None
    assert await env.bot.request_lead(STRANGER_TG, "x", "Владимир", dept.id) == texts_mod.LEAD_NOT_STAFF
    other_org = Organization(name="Other", slug="other", created_at=datetime.utcnow())
    env.db.add(other_org)
    await env.db.commit()
    await _member(env, 7500, org_id=other_org.id)
    assert await env.bot.lead_departments(7500) == []  # отделы чужой организации не видны
    assert await env.bot.request_lead(7500, "x", "Икс", dept.id) == texts_mod.LEAD_NO_DEPARTMENTS
    assert env.messenger.sent == []
    async with env.sessions() as s:
        assert (await s.scalars(select(DepartmentLead))).all() == []


def test_audit_wallet_masked_in_audit_log():
    """Кошелёк и ответы опросов из /api/onboarding/inbound лежали в журнале действий открытым текстом."""
    from api.services.audit import _clean

    cleaned = _clean({"id": 5, "wallet": "TQ3xyz", "answers": [{"answer": "всё ок"}]})
    assert cleaned["id"] == 5 and cleaned["wallet"] == "***" and cleaned["answers"] == "***"
