"""Передача новых сотрудников HR-аккаунтам автоспамера / AI-селлера (api/onboarding/handoff.py)."""

from dataclasses import dataclass, field
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.models.database import BoardDepartment, BoardPlacement, Entity, EntityStatus, EntityType
from api.onboarding import runtime
from api.onboarding.config import Settings, parse_accounts
from api.onboarding.handoff import HandoffService
from api.onboarding.messenger import SendError
from api.onboarding.models import Handoff, HandoffAccount
from tests.conftest import auth_headers

ACC_ONE, ACC_TWO = 501, 502
FALLBACK = -3003


@dataclass
class FakeMessenger:
    sent: list = field(default_factory=list)
    failing: set = field(default_factory=set)

    async def send(self, chat_id, text, buttons=None):
        if chat_id in self.failing:
            raise SendError("Forbidden: bot was blocked by the user")
        self.sent.append(SimpleNamespace(chat_id=chat_id, text=text))

    def to(self, chat_id):
        return [m.text for m in self.sent if m.chat_id == chat_id]


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def messenger():
    return FakeMessenger()


@pytest.fixture
def clock():
    return Clock(datetime(2026, 11, 3, 9, 0))  # вторник, 12:00 МСК


@pytest_asyncio.fixture
async def handoff(async_engine, messenger, clock):
    sessions = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    svc = HandoffService(
        sessions, messenger,
        Settings(handoff_accounts=("hr_one", "hr_two"), hr_fallback_chat_id=FALLBACK),
        clock,
    )
    runtime.set_handoff(svc)
    yield svc
    runtime.set_handoff(None)


async def _person(db, org, user, name, *, status=EntityStatus.transferred, tg="ivan_p",
                  first_day="2026-11-12", dept="SEO"):
    extra = {"manager_name": "Мария"}
    if first_day:
        extra["department_transfer_date"] = first_day
    entity = Entity(org_id=org.id, created_by=user.id, name=name, type=EntityType.candidate, status=status,
                    telegram_usernames=[tg] if tg else [], extra_data=extra, created_at=datetime.utcnow())
    db.add(entity)
    await db.commit()
    if dept:
        department = BoardDepartment(org_id=org.id, name=dept, kind="team")
        db.add(department)
        await db.commit()
        db.add(BoardPlacement(org_id=org.id, entity_id=entity.id, department_id=department.id, extra={}))
        await db.commit()
    return entity


async def _link_accounts(handoff):
    assert await handoff.register_account(ACC_ONE, "@HR_one")
    assert await handoff.register_account(ACC_TWO, "hr_two")


def test_parse_accounts():
    assert parse_accounts(" @HR_one, hr_two ,, @hr_one") == ("hr_one", "hr_two")
    assert parse_accounts("") == ()


async def test_register_only_listed_accounts(handoff):
    assert not await handoff.register_account(999, "stranger")
    assert not await handoff.register_account(999, None)
    assert await handoff.register_account(ACC_ONE, "@HR_ONE")
    async with handoff.sessions() as s:
        account = await s.scalar(select(HandoffAccount))
    assert account.username == "hr_one" and account.tg_id == ACC_ONE


async def test_people_already_in_department_are_not_messaged(handoff, messenger, clock, db_session,
                                                             organization, admin_user):
    await _link_accounts(handoff)
    await _person(db_session, organization, admin_user, "Старый Сотрудник", first_day="2026-11-12")
    await handoff.tick()  # первое включение — baseline
    newbie = await _person(db_session, organization, admin_user, "Иван Петров", first_day="2026-11-12")
    await handoff.tick()
    clock.now = datetime(2026, 11, 12, 7, 1)  # 10:01 МСК первого рабочего дня
    await handoff.tick()
    sent = messenger.to(ACC_ONE) + messenger.to(ACC_TWO)
    assert len(sent) == 1 and f"id: {newbie.id}" in sent[0]


async def test_first_day_card_and_stages(handoff, messenger, clock, db_session, organization, admin_user):
    await _link_accounts(handoff)
    await handoff.tick()  # baseline — пусто
    ivan = await _person(db_session, organization, admin_user, "Иван Петров")
    await handoff.tick()
    assert messenger.sent == []  # ждём 10:00 первого рабочего дня

    clock.now = datetime(2026, 11, 12, 6, 59)
    await handoff.tick()
    assert messenger.sent == []
    clock.now = datetime(2026, 11, 12, 7, 1)
    assert await handoff.tick() == 1
    [card] = messenger.to(ACC_ONE)
    assert card.splitlines()[:2] == ["#onboarding_new", f"id: {ivan.id}"]
    for line in ("ФИО: Иван Петров", "Telegram: @ivan_p", "Отдел: SEO", "Лид: Мария",
                 "Первый рабочий день: 12.11.2026", "Часовой пояс: Europe/Moscow", "HR: Admin User"):
        assert line in card
    assert "кошел" not in card.lower()

    # второй человек — второму аккаунту (у первого уже один)
    anna = await _person(db_session, organization, admin_user, "Анна Смирнова", tg="anna_s", first_day="2026-11-12")
    await handoff.tick()
    assert f"id: {anna.id}" in messenger.to(ACC_TWO)[0]

    clock.now = datetime(2026, 11, 17, 9, 1)  # день 6, 12:01 МСК — неделя
    await handoff.tick()
    week = messenger.to(ACC_ONE)[-1]
    assert week.startswith("#onboarding_stage") and "Этап: week" in week

    clock.now = datetime(2026, 12, 12, 9, 1)  # месяц — суббота: молчим
    await handoff.tick()
    assert not any("Этап: month1" in t for t in messenger.to(ACC_ONE))
    clock.now = datetime(2026, 12, 14, 9, 1)  # понедельник
    await handoff.tick()
    assert "Этап: month1" in messenger.to(ACC_ONE)[-1]


async def test_missing_telegram_asks_hr_once_then_continues(handoff, messenger, clock, db_session,
                                                            organization, admin_user):
    await _link_accounts(handoff)
    await handoff.tick()
    person = await _person(db_session, organization, admin_user, "Без Ника", tg=None)
    await handoff.tick()
    await handoff.tick()
    notices = messenger.to(FALLBACK)
    assert len(notices) == 1 and "нет Telegram и телефона" in notices[0]

    person.telegram_usernames = ["found_nick"]
    await db_session.commit()
    clock.now = datetime(2026, 11, 12, 7, 1)
    await handoff.tick()
    assert "Telegram: @found_nick" in (messenger.to(ACC_ONE) + messenger.to(ACC_TWO))[0]


async def test_missing_first_day_asks_hr(handoff, messenger, db_session, organization, admin_user):
    await _link_accounts(handoff)
    await handoff.tick()
    await _person(db_session, organization, admin_user, "Без Даты", first_day=None)
    await handoff.tick()
    assert "не указана дата выхода в отдел" in messenger.to(FALLBACK)[0]


async def test_late_first_day_is_sent_right_away(handoff, messenger, db_session, organization, admin_user):
    await _link_accounts(handoff)
    await handoff.tick()
    await _person(db_session, organization, admin_user, "Поздно Внесли", first_day="2026-11-02")
    await handoff.tick()  # дата уже прошла — передаём сейчас (вторник, 12:00 МСК)
    assert len(messenger.to(ACC_ONE)) == 1


async def test_dismissed_gets_stop(handoff, messenger, clock, db_session, organization, admin_user):
    await _link_accounts(handoff)
    await handoff.tick()
    person = await _person(db_session, organization, admin_user, "Иван Петров")
    await handoff.tick()
    clock.now = datetime(2026, 11, 12, 7, 1)
    await handoff.tick()
    person.status = EntityStatus.dismissed
    await db_session.commit()
    await handoff.tick()
    stop = messenger.to(ACC_ONE)[-1]
    assert stop.startswith("#onboarding_stop") and f"id: {person.id}" in stop
    async with handoff.sessions() as s:
        row = await s.scalar(select(Handoff).where(Handoff.entity_id == person.id))
    assert row.status == "stopped"


async def test_no_linked_account_waits(handoff, messenger, db_session, organization, admin_user):
    await handoff.tick()
    await _person(db_session, organization, admin_user, "Иван Петров", first_day="2026-11-02")
    await handoff.tick()
    await handoff.tick()
    assert len(messenger.to(FALLBACK)) == 1 and "ни один HR-аккаунт" in messenger.to(FALLBACK)[0]
    await handoff.register_account(ACC_ONE, "hr_one")
    handoff.clock.now = datetime(2026, 11, 3, 9, 11)  # после паузы 10 минут
    await handoff.tick()
    assert len(messenger.to(ACC_ONE)) == 1


async def test_bot_start_links_account(handoff):
    import api.bot as bot_module

    message = SimpleNamespace(
        text="/start", chat=SimpleNamespace(type="private", id=ACC_ONE),
        from_user=SimpleNamespace(id=ACC_ONE, username="HR_one"), answer=AsyncMock(),
    )
    await bot_module.cmd_start(message)
    assert "Аккаунт подключён" in message.answer.await_args.args[0]


async def test_api_handoffs_overview(client, handoff, monkeypatch, db_session, org_owner, admin_token,
                                     organization, admin_user):
    from api.config import settings as app_settings

    monkeypatch.setattr(app_settings, "onboarding_handoff_accounts", "@hr_one, @hr_two")
    await handoff.register_account(ACC_ONE, "hr_one")
    await _person(db_session, organization, admin_user, "Старый Сотрудник")
    await handoff.tick()
    await _person(db_session, organization, admin_user, "Без Ника", tg=None)
    await handoff.tick()
    r = await client.get("/api/onboarding/handoffs", headers=auth_headers(admin_token))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["accounts"] == [{"username": "@hr_one", "linked": True}, {"username": "@hr_two", "linked": False}]
    [row] = data["handoffs"]  # baseline не показываем
    assert row["full_name"] == "Без Ника" and row["waiting_reason"] == "нет Telegram и телефона в карточке"
