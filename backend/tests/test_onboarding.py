"""HR-бот практики и испытательного срока (api/onboarding, ТЗ «Пребординг и онбординг трафика»).

Сценарии — на тестовой базе с фейковым мессенджером и подменённым временем; плюс
встраивание в api/bot.py (ловушки /start, лички, групп) и ручки /api/onboarding.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.models.database import Entity, EntityStatus, EntityType, Organization
from api.onboarding import runtime
from api.onboarding import schedule as sch
from api.onboarding.config import Settings
from api.onboarding.crypto import WalletCipher
from api.onboarding.messenger import SendError
from api.onboarding.models import BotJob, CaseStatus, OnboardingCase, Signal, Wallet
from api.onboarding.service import OnboardingService
from tests.conftest import auth_headers

HR_TG = 1001
LEAD_TG = 2002
FALLBACK = -3003
CANDIDATE_TG = 4004
WORK_CHAT = -5005
TZ = "Europe/Moscow"


@dataclass
class FakeMessenger:
    sent: list = field(default_factory=list)
    failing: set = field(default_factory=set)

    async def send(self, chat_id, text, buttons=None):
        if chat_id in self.failing:
            raise SendError("Forbidden: bot was blocked by the user")
        self.sent.append(SimpleNamespace(chat_id=chat_id, text=text, buttons=buttons))

    def to(self, chat_id):
        return [m for m in self.sent if m.chat_id == chat_id]


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


@pytest.fixture
def messenger():
    return FakeMessenger()


@pytest.fixture
def clock():
    return Clock(datetime(2026, 11, 3, 9, 0))  # 12:00 МСК


@pytest_asyncio.fixture
async def service(async_engine, messenger, clock, monkeypatch):
    settings = Settings(
        bot_username="test_bot",
        wallet_enc_key=Fernet.generate_key().decode(),
        landing_url="https://example.com/start",
        wallet_guide_url="https://example.com/wallet",
        platform_invite_url="https://example.com/invite",
        materials_url="https://example.com/materials",
        hr_fallback_chat_id=FALLBACK,
    )
    svc = OnboardingService(
        async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False),
        messenger, settings, WalletCipher(settings.wallet_enc_key), clock,
    )
    monkeypatch.setattr(runtime, "enabled", lambda: True)
    monkeypatch.setattr("api.routes.onboarding.enabled", lambda: True)
    runtime.set_service(svc)
    yield svc
    runtime.set_service(None)


async def _case(service, start=datetime(2026, 11, 5, 10, 0), **kw):
    params = dict(full_name="Иван Петров", first_name="Иван", practice_start=start,
                  candidate_tg_username="@Ivan_P", practice_lead="Анна @anna", hrd="Олег @oleg", hr_tg_id=HR_TG)
    params.update(kw)
    return await service.create_case(**params)


async def _pending(service, case_id):
    async with service.sessions() as s:
        return {j.kind for j in await s.scalars(select(BotJob).where(BotJob.case_id == case_id, BotJob.status == "pending"))}


# ------------------------------------------------------------------ расписание


def test_schedule_practice_and_onboarding_dates():
    now = datetime(2026, 11, 3, 9, 0)
    start = sch.local_to_utc(datetime(2026, 11, 5, 10, 0), TZ)
    jobs = sch.preboarding_jobs(now, start, TZ, 7)
    looms = [run_at for kind, run_at, _ in jobs if kind == "loom"]
    assert len(looms) == 7 and looms[0] == datetime(2026, 11, 5, 17, 0)  # 20:00 МСК
    assert sch.retry_interval(now, start, TZ) == timedelta(hours=24)
    assert sch.retry_interval(now, sch.local_to_utc(datetime(2026, 11, 4, 10, 0), TZ), TZ) == timedelta(hours=2)
    by_kind = {p.get("kind", k): run_at.date() for k, run_at, p in sch.onboarding_jobs(date(2026, 11, 12), TZ)}
    assert by_kind["first_day_welcome"] == by_kind["first_day"] == date(2026, 11, 12)
    assert by_kind["week"] == date(2026, 11, 17)
    assert by_kind["month3"] == date(2027, 1, 29)
    assert sch.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert by_kind["month1"] == date(2026, 12, 14)  # 12.12 — суббота → понедельник


def test_working_hours_window():
    def local(dt):
        return sch.utc_to_local(dt, TZ).replace(tzinfo=None)

    def shift(y, m, d, hh, mm=0):
        return local(sch.within_working_hours(sch.local_to_utc(datetime(y, m, d, hh, mm), TZ), TZ))

    assert shift(2026, 11, 4, 12) == datetime(2026, 11, 4, 12)    # среда, день — как есть
    assert shift(2026, 11, 4, 18) == datetime(2026, 11, 4, 18)    # ровно 18:00 — ещё можно
    assert shift(2026, 11, 4, 18, 1) == datetime(2026, 11, 5, 10)  # вечер → утро
    assert shift(2026, 11, 4, 7) == datetime(2026, 11, 4, 10)     # рано → 10:00
    assert shift(2026, 11, 6, 23) == datetime(2026, 11, 9, 10)    # пятница ночь → понедельник
    assert shift(2026, 11, 7, 12) == datetime(2026, 11, 9, 10)    # суббота → понедельник
    utc = sch.local_to_utc(datetime(2026, 11, 7, 12), TZ)
    assert sch.within_working_hours(utc, TZ, skip_weekends=False) == utc


# -------------------------------------------------------------------- сценарии


async def test_first_message_after_start(service, messenger):
    case = await _case(service)
    assert case.link_token.startswith("ob_")
    assert service.invite_link(case) == f"https://t.me/test_bot?start={case.link_token}"
    assert await service.handle_start(CANDIDATE_TG, case.link_token)
    [msg] = messenger.to(CANDIDATE_TG)
    assert msg.text.startswith("Привет, Иван! Практика стартует 05.11 в 10:00.")
    assert [row[0][1] for row in msg.buttons] == ["scr:ok", "scr:questions", "scr:decline"]
    assert "invite_check" not in await _pending(service, case.id)


async def test_retries_then_hr_signal(service, messenger, clock):
    case = await _case(service, start=datetime(2026, 11, 4, 10, 0))
    await service.handle_start(CANDIDATE_TG, case.link_token)
    for _ in range(3):
        clock.advance(hours=2, minutes=1)
        await service.run_due_jobs()
    assert len(messenger.to(CANDIDATE_TG)) == 3  # первое + 2 повтора (14:01, 16:02 МСК)
    assert messenger.to(HR_TG) == []  # сигнал выпал на 18:03 — после окна 10–18, ждёт утра
    clock.now = datetime(2026, 11, 4, 7, 1)  # 04.11 10:01 МСК
    await service.run_due_jobs()
    [signal] = messenger.to(HR_TG)
    assert "не ответил(а) по практике на 04.11" in signal.text


async def test_questions_signal_falls_back_to_hr_chat(service, messenger):
    messenger.failing.add(HR_TG)
    case = await _case(service)
    await service.handle_start(CANDIDATE_TG, case.link_token)
    await service.handle_script_answer(CANDIDATE_TG, "questions")
    [signal] = messenger.to(FALLBACK)
    assert "задал(а) вопрос" in signal.text


async def test_wallet_encrypted_and_text_passthrough(service):
    case = await _case(service)
    await service.handle_start(CANDIDATE_TG, case.link_token)
    handled, reply = await service.handle_text(CANDIDATE_TG, "TRC20: TXyz")
    assert handled and "сохранены" in reply
    async with service.sessions() as s:
        wallet = await s.scalar(select(Wallet).where(Wallet.case_id == case.id))
    assert "TXyz" not in wallet.ciphertext and service.cipher.decrypt(wallet.ciphertext) == "TRC20: TXyz"
    # дальше бот текста не ждёт — сообщение уходит обычным обработчикам
    assert await service.handle_text(CANDIDATE_TG, "вопрос") == (False, None)
    assert await service.handle_text(999, "кто-то другой") == (False, None)


async def test_work_chat_start_and_loom(service, messenger, clock):
    case = await _case(service)
    await service.handle_start(CANDIDATE_TG, case.link_token)
    await service.handle_members_joined(WORK_CHAT, [(CANDIDATE_TG, "ivan_p")])
    assert messenger.to(WORK_CHAT)[0].buttons == [[("Старт", "pstart")]]
    assert await service.handle_practice_start(WORK_CHAT, 777, "stranger") == "Эта кнопка — для кандидата на практику."
    assert await service.handle_practice_start(WORK_CHAT, CANDIDATE_TG, "ivan_p") is None
    assert messenger.to(WORK_CHAT)[-1].text.startswith("Старт практики!")

    clock.now = datetime(2026, 11, 5, 17, 1)  # 20:01 МСК
    await service.run_due_jobs()
    assert messenger.to(CANDIDATE_TG)[-1].text.startswith("Иван, время для вечернего Loom")


async def test_bot_added_welcome_only_for_hr_with_practice_now(service, messenger):
    await _case(service, start=datetime(2026, 11, 4, 10, 0))
    assert not await service.handle_bot_added(WORK_CHAT, 555)          # не HR кандидата
    assert not await service.handle_bot_added(WORK_CHAT, None)
    assert await service.handle_bot_added(WORK_CHAT, HR_TG)
    assert messenger.to(WORK_CHAT)[0].buttons == [[("Старт", "pstart")]]
    far = await _case(service, start=datetime(2026, 12, 20, 10, 0), hr_tg_id=6006)
    assert far and not await service.handle_bot_added(-1, 6006)       # практика не в эти дни


async def test_transfer_survey_and_onboarding(service, messenger, clock):
    case = await _case(service)
    await service.handle_start(CANDIDATE_TG, case.link_token)
    await service.set_status(case.id, CaseStatus.transferred, department="SEO", lead_name="Мария",
                             lead_tg_id=LEAD_TG, department_start_date=date(2026, 11, 12))
    assert messenger.to(CANDIDATE_TG)[-1].text.startswith("Иван, поздравляем!")
    pending = await _pending(service, case.id)
    assert "loom" not in pending and {"survey", "staff_reminder"} <= pending

    await service.start_survey(CANDIDATE_TG, "practice")
    await service.answer_survey(CANDIDATE_TG, "practice", 0, 2)  # «Многое осталось непонятным»
    assert "Многое осталось непонятным" in messenger.to(HR_TG)[-1].text

    clock.now = datetime(2026, 12, 12, 7, 1)  # месяц 1 — суббота 12.12: в выходной бот молчит
    await service.run_due_jobs()
    assert not any("Контрольная точка" in m.text for m in messenger.to(LEAD_TG))
    clock.now = datetime(2026, 12, 14, 7, 1)  # понедельник 14.12, 10:01 МСК
    await service.run_due_jobs()
    assert "Контрольная точка: месяц Иван Петров" in messenger.to(LEAD_TG)[-1].text


async def test_left_cancels_jobs(service, messenger):
    case = await _case(service)
    await service.set_status(case.id, CaseStatus.left)
    assert "exit-интервью" in messenger.to(HR_TG)[-1].text
    assert await _pending(service, case.id) == set()


async def _transferred(service, lead_tg_id=LEAD_TG):
    case = await _case(service)
    await service.handle_start(CANDIDATE_TG, case.link_token)
    await service.set_status(case.id, CaseStatus.transferred, department="SEO", lead_name="Мария",
                             lead_tg_id=lead_tg_id, department_start_date=date(2026, 11, 12))
    return case


async def test_first_working_day_checklist(service, messenger, clock):
    case = await _transferred(service)
    clock.now = datetime(2026, 11, 12, 7, 1)  # 12.11 10:01 МСК — первый день в отделе
    await service.run_due_jobs()
    welcome = messenger.to(CANDIDATE_TG)[-1].text
    assert welcome.startswith("Иван, добро пожаловать в команду! Сегодня твой первый день в отделе SEO.")
    assert "https://example.com/materials" in welcome and "реферальная программа" in welcome
    assert "крипто-кошелька" in welcome  # кошелёк ещё не присылал
    assert messenger.to(LEAD_TG)[-1].text.startswith("Сегодня первый день Иван Петров в отделе SEO. Назначь")

    clock.now = datetime(2026, 11, 12, 9, 1)  # 12:01 — HR
    await service.run_due_jobs()
    assert "всё ли понятно, нет ли организационных вопросов" in messenger.to(HR_TG)[-1].text

    assert (await service.handle_text(CANDIDATE_TG, "TRC20: TFirst"))[0]  # бот ждал кошелёк

    clock.now = datetime(2026, 11, 12, 15, 1)  # 18:01 — опрос конца дня
    await service.run_due_jobs()
    invite = messenger.to(CANDIDATE_TG)[-1]
    assert invite.buttons == [[("Пройти опрос", "survey:first_day")]]
    await service.start_survey(CANDIDATE_TG, "first_day")
    await service.answer_survey(CANDIDATE_TG, "first_day", 0, 1)  # встречи с руководителем не было
    assert "Состоялась ли встреча с руководителем?" in messenger.to(HR_TG)[-1].text


async def test_first_day_wallet_not_requested_twice(service, messenger, clock):
    case = await _case(service)
    await service.handle_start(CANDIDATE_TG, case.link_token)
    await service.handle_text(CANDIDATE_TG, "TRC20: TOld")
    await service.set_status(case.id, CaseStatus.transferred, department="SEO", department_start_date=date(2026, 11, 12))
    clock.now = datetime(2026, 11, 12, 7, 1)
    await service.run_due_jobs()
    assert "крипто-кошелька" not in messenger.to(CANDIDATE_TG)[-1].text


async def test_lead_only_reminder_goes_to_hr_without_lead_telegram(service, messenger, clock):
    await _transferred(service, lead_tg_id=None)
    clock.now = datetime(2026, 11, 12, 7, 1)
    await service.run_due_jobs()
    assert messenger.to(HR_TG)[-1].text.startswith("Лиду не доставлено (не привязан Telegram):")


async def test_probation_extended_reschedules_close(service, messenger):
    case = await _transferred(service)
    with pytest.raises(ValueError):
        await service.decide_probation(case.id, "extended", new_end=date(2027, 2, 1))  # раньше текущей
    await service.decide_probation(case.id, "extended", new_end=date(2027, 3, 12))
    assert "продлён до 12.03" in messenger.to(HR_TG)[-1].text
    async with service.sessions() as s:
        jobs = list(await s.scalars(select(BotJob).where(BotJob.case_id == case.id, BotJob.status == "pending")))
        saved = await s.get(OnboardingCase, case.id)
    closes = [j.run_at for j in jobs if j.payload and "probation_close" in j.payload]
    assert closes == [datetime(2027, 3, 12, 7, 0)]  # 10:00 МСК в новый последний день
    month3 = [j.run_at.date() for j in jobs if j.payload and '"month3"' in j.payload]
    assert month3 == [date(2027, 2, 26)]  # за 14 дней до нового конца
    assert saved.probation_end_date == date(2027, 3, 12) and saved.probation_decision == "extended"


async def test_probation_stays_cancels_close_reminder(service, messenger, clock):
    case = await _transferred(service)
    await service.decide_probation(case.id, "stays")
    clock.now = datetime(2027, 2, 12, 7, 1)
    await service.run_due_jobs()
    assert not any("заканчивается испытательный срок" in m.text for m in messenger.to(HR_TG))


async def test_left_reason_saved_and_in_signal(service, messenger):
    case = await _transferred(service)
    await service.decide_probation(case.id, "leaves", reason="Переезд в другой город")
    assert messenger.to(HR_TG)[-1].text == (
        "Иван Петров уходит. Причина: Переезд в другой город. Не забудь про exit-интервью."
    )
    async with service.sessions() as s:
        saved = await s.get(OnboardingCase, case.id)
    assert saved.status == "left" and saved.left_reason == "Переезд в другой город" and saved.left_at


# ---------------------------------------------------------- встраивание в api/bot.py


def _private_message(text, user_id=CANDIDATE_TG):
    return SimpleNamespace(
        text=text, chat=SimpleNamespace(type="private", id=user_id),
        from_user=SimpleNamespace(id=user_id, username=None), answer=AsyncMock(),
    )


async def test_bot_start_with_onboarding_link_is_not_account_bind(service, messenger, monkeypatch):
    import api.bot as bot_module

    bind = AsyncMock()
    monkeypatch.setattr(bot_module, "handle_bind_token", bind)
    case = await _case(service)
    await bot_module.cmd_start(_private_message(f"/start {case.link_token}"))
    bind.assert_not_called()
    assert messenger.to(CANDIDATE_TG)[0].text.startswith("Привет, Иван!")


async def test_bot_group_join_shows_start_and_still_collects(service, messenger, monkeypatch):
    import api.bot as bot_module

    messenger.bot = SimpleNamespace(me=AsyncMock(return_value=SimpleNamespace(id=1)))
    case = await _case(service)
    await service.handle_start(CANDIDATE_TG, case.link_token)
    candidate = SimpleNamespace(id=CANDIDATE_TG, username="ivan_p", is_bot=False)
    message = SimpleNamespace(new_chat_members=[candidate], chat=SimpleNamespace(id=WORK_CHAT), from_user=None)
    await bot_module.collect_group_message(message)  # from_user=None — сбор сам выходит после хука
    assert messenger.to(WORK_CHAT)[0].buttons == [[("Старт", "pstart")]]

    # сломанный бот практики не мешает сбору переписки
    monkeypatch.setattr(runtime, "get_service", AsyncMock(side_effect=RuntimeError("boom")))
    await bot_module.collect_group_message(message)


async def test_bot_private_text_wallet_not_sent_to_ai_digest(service, monkeypatch):
    import api.bot as bot_module

    case = await _case(service)
    await service.handle_start(CANDIDATE_TG, case.link_token)
    monkeypatch.setattr(bot_module, "_handle_access_chat_reply", AsyncMock(return_value=False))
    access = AsyncMock()
    monkeypatch.setattr(bot_module, "_get_user_access", access)
    message = _private_message("TRC20: TXyz")
    await bot_module.cmd_ai_digest(message)
    access.assert_not_called()
    message.answer.assert_awaited_once()
    assert "сохранены" in message.answer.await_args.args[0]


# ------------------------------------------------------------------------ API


@pytest_asyncio.fixture
async def practice_entity(db_session, organization, admin_user):
    entity = Entity(org_id=organization.id, created_by=admin_user.id, name="Пётр Иванов",
                    type=EntityType.candidate, status=EntityStatus.new, telegram_usernames=["petr_i"],
                    created_at=datetime.utcnow())
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)
    return entity


async def test_api_assign_practice(client, service, org_owner, admin_token, practice_entity):
    url = f"/api/onboarding/entities/{practice_entity.id}/case"
    body = {"practice_start": "2026-11-05T10:00", "first_name": "Пётр", "practice_lead": "Анна", "hrd": "Олег"}
    r = await client.post(url, json=body, headers=auth_headers(admin_token))
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["status"] == "practice_assigned"
    assert data["invite_link"].startswith("https://t.me/test_bot?start=ob_")
    assert data["hr_telegram_missing"] is True  # у HR не привязан Telegram — сигналы уйдут в запасной чат
    assert (await client.post(url, json=body, headers=auth_headers(admin_token))).status_code == 409

    r = await client.get(url, headers=auth_headers(admin_token))
    assert r.json()["case"]["id"] == data["id"]


async def test_api_member_without_hr_role_forbidden(client, service, org_member, second_user_token, practice_entity):
    r = await client.get(f"/api/onboarding/entities/{practice_entity.id}/case", headers=auth_headers(second_user_token))
    assert r.status_code == 403


async def test_api_other_org_candidate_is_404(client, service, db_session, org_owner, admin_token, second_organization):
    other = Entity(org_id=second_organization.id, name="Чужой", type=EntityType.candidate,
                   status=EntityStatus.new, created_at=datetime.utcnow())
    db_session.add(other)
    await db_session.commit()
    r = await client.post(f"/api/onboarding/entities/{other.id}/case",
                          json={"practice_start": "2026-11-05T10:00"}, headers=auth_headers(admin_token))
    assert r.status_code == 404


async def test_api_transfer_and_wallet(client, service, messenger, org_owner, admin_token, practice_entity):
    r = await client.post(f"/api/onboarding/entities/{practice_entity.id}/case",
                          json={"practice_start": "2026-11-05T10:00", "first_name": "Пётр"},
                          headers=auth_headers(admin_token))
    case_id = r.json()["id"]
    async with service.sessions() as s:
        token = (await s.get(OnboardingCase, case_id)).link_token
    await service.handle_start(CANDIDATE_TG, token)
    await service.handle_text(CANDIDATE_TG, "BEP20: 0xabc")

    wallet = await client.get(f"/api/onboarding/cases/{case_id}/wallet", headers=auth_headers(admin_token))
    assert wallet.status_code == 200 and wallet.json()["wallet"] == "BEP20: 0xabc"

    status_url = f"/api/onboarding/cases/{case_id}/status"
    r = await client.post(status_url, json={"status": "transferred"}, headers=auth_headers(admin_token))
    assert r.status_code == 400  # без отдела поздравление не собрать
    r = await client.post(status_url, json={"status": "transferred", "department": "SEO", "lead_name": "Мария",
                                            "department_start_date": "2026-11-12"}, headers=auth_headers(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "transferred" and r.json()["probation_end_date"] == "2027-02-12"
    assert messenger.to(CANDIDATE_TG)[-1].text.startswith("Пётр, поздравляем! Ты прошёл(ла) практику и переходишь в отдел SEO.")


async def test_api_probation_decision(client, service, org_owner, admin_token, practice_entity):
    r = await client.post(f"/api/onboarding/entities/{practice_entity.id}/case",
                          json={"practice_start": "2026-11-05T10:00"}, headers=auth_headers(admin_token))
    case_id = r.json()["id"]
    url = f"/api/onboarding/cases/{case_id}/probation"
    r = await client.post(url, json={"decision": "stays"}, headers=auth_headers(admin_token))
    assert r.status_code == 400  # ещё на практике
    await client.post(f"/api/onboarding/cases/{case_id}/status",
                      json={"status": "transferred", "department": "SEO", "department_start_date": "2026-11-12"},
                      headers=auth_headers(admin_token))
    r = await client.post(url, json={"decision": "extended", "new_end_date": "2027-03-12"}, headers=auth_headers(admin_token))
    assert r.status_code == 200 and r.json()["probation_end_date"] == "2027-03-12"
    r = await client.post(url, json={"decision": "leaves", "reason": "Не подошёл темп"}, headers=auth_headers(admin_token))
    assert r.json()["status"] == "left" and r.json()["left_reason"] == "Не подошёл темп"


async def test_api_wallets_for_accounting(client, service, org_owner, org_member, admin_token,
                                          second_user, second_user_token, practice_entity):
    r = await client.post(f"/api/onboarding/entities/{practice_entity.id}/case",
                          json={"practice_start": "2026-11-05T10:00", "first_name": "Пётр"},
                          headers=auth_headers(admin_token))
    case_id = r.json()["id"]
    async with service.sessions() as s:
        token = (await s.get(OnboardingCase, case_id)).link_token
    await service.handle_start(CANDIDATE_TG, token)
    await service.handle_text(CANDIDATE_TG, "TRC20: TAccounting")
    await service.set_status(case_id, CaseStatus.transferred, department="SEO", lead_name="Мария",
                             department_start_date=date(2026, 11, 12))

    accountant = auth_headers(second_user_token)  # участник орга без HR-роли
    assert (await client.get("/api/onboarding/wallets", headers=accountant)).status_code == 403
    assert (await client.post("/api/onboarding/wallet-access", json={"user_id": second_user.id},
                              headers=accountant)).status_code == 403  # сам себе не выдаст

    r = await client.post("/api/onboarding/wallet-access", json={"user_id": second_user.id},
                          headers=auth_headers(admin_token))
    assert r.status_code == 201
    r = await client.get("/api/onboarding/wallets", headers=accountant)
    assert r.status_code == 200
    [row] = r.json()
    assert row["full_name"] == "Пётр Иванов" and row["department"] == "SEO" and row["wallet"] == "TRC20: TAccounting"
    assert set(row) == {"case_id", "entity_id", "full_name", "department", "lead_name", "status",
                        "status_label", "wallet", "saved_at"}  # остальных данных кандидата бухгалтерии не видно
    assert (await client.get(f"/api/onboarding/cases/{case_id}/wallet", headers=accountant)).status_code == 200
    # карточка бота с опросами и сигналами бухгалтерии по-прежнему закрыта
    assert (await client.get(f"/api/onboarding/entities/{practice_entity.id}/case", headers=accountant)).status_code == 403

    listed = await client.get("/api/onboarding/wallet-access", headers=auth_headers(admin_token))
    assert [u["user_id"] for u in listed.json()] == [second_user.id]
    assert (await client.delete(f"/api/onboarding/wallet-access/{second_user.id}",
                                headers=auth_headers(admin_token))).status_code == 204
    assert (await client.get("/api/onboarding/wallets", headers=accountant)).status_code == 403


async def test_api_disabled_is_503(client, org_owner, admin_token, practice_entity, monkeypatch):
    monkeypatch.setattr("api.routes.onboarding.enabled", lambda: False)
    r = await client.post(f"/api/onboarding/entities/{practice_entity.id}/case",
                          json={"practice_start": "2026-11-05T10:00"}, headers=auth_headers(admin_token))
    assert r.status_code == 503
    r = await client.get(f"/api/onboarding/entities/{practice_entity.id}/case", headers=auth_headers(admin_token))
    assert r.status_code == 200 and r.json() == {"enabled": False, "case": None}
