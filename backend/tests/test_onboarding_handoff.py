"""Передача кандидатов и сотрудников HR-профилю автоспамера / AI-селлера (api/onboarding/handoff.py):
события «практика», «перевод в отдел», «стоп»."""

import hashlib
import hmac
import json
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
SETTINGS = dict(handoff_accounts=("hr_one", "hr_two"), hr_fallback_chat_id=FALLBACK, hrd="Настя @nastya")


@dataclass
class FakeMessenger:
    sent: list = field(default_factory=list)

    async def send(self, chat_id, text, buttons=None):
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


def _service(async_engine, messenger, clock, poster=None, **overrides):
    sessions = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    return HandoffService(sessions, messenger, Settings(**{**SETTINGS, **overrides}), clock,
                          poster=poster or AsyncMock())


@pytest_asyncio.fixture
async def handoff(async_engine, messenger, clock):
    svc = _service(async_engine, messenger, clock)
    runtime.set_handoff(svc)
    yield svc
    runtime.set_handoff(None)


async def _person(db, org, user, name, *, status=EntityStatus.probation, tg="ivan_p",
                  practice="2026-11-05", first_day=None, dept=None):
    extra = {"manager_name": "Анна"}
    if practice:
        extra["practice_start_date"] = practice
    if first_day:
        extra["department_transfer_date"] = first_day
    entity = Entity(org_id=org.id, created_by=user.id, name=name, type=EntityType.candidate, status=status,
                    telegram_usernames=[tg] if tg else [], extra_data=extra, created_at=datetime.utcnow())
    db.add(entity)
    await db.commit()
    if dept:
        await _place(db, org, entity, dept)
    return entity


async def _place(db, org, entity, dept):
    department = BoardDepartment(org_id=org.id, name=dept, kind="team")
    db.add(department)
    await db.commit()
    db.add(BoardPlacement(org_id=org.id, entity_id=entity.id, department_id=department.id, extra={}))
    await db.commit()


async def _transfer(db, entity, first_day="2026-11-12", lead="Мария"):
    entity.status = EntityStatus.transferred
    entity.extra_data = {**entity.extra_data, "department_transfer_date": first_day, "manager_name": lead}
    await db.commit()


async def _link(handoff):
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


async def test_practice_transfer_stop_go_to_one_account(handoff, messenger, db_session, organization, admin_user):
    await _link(handoff)
    await handoff.tick()  # baseline — пусто
    ivan = await _person(db_session, organization, admin_user, "Иван Петров")
    assert await handoff.tick() == 1  # практика — сразу, расписание у них
    [practice] = messenger.to(ACC_ONE)
    assert practice.splitlines()[:2] == ["#onboarding_practice", f"id: {ivan.id}"]
    for line in ("ФИО: Иван Петров", "Telegram: @ivan_p", "Старт практики: 05.11.2026 10:00",
                 "Руководитель практики: Анна", "HRD: Настя @nastya", "HR: Admin User"):
        assert line in practice
    assert await handoff.tick() == 0  # второй раз не шлём

    await _place(db_session, organization, ivan, "SEO")
    await _transfer(db_session, ivan)
    await handoff.tick()
    transfer = messenger.to(ACC_ONE)[-1]  # тот же аккаунт, что вёл практику
    assert transfer.startswith("#onboarding_transfer")
    for line in ("Отдел: SEO", "Лид: Мария", "Первый рабочий день: 12.11.2026"):
        assert line in transfer
    assert "кошел" not in transfer.lower()

    ivan.status = EntityStatus.dismissed
    await db_session.commit()
    await handoff.tick()
    stop = messenger.to(ACC_ONE)[-1]
    assert stop.startswith("#onboarding_stop") and "Причина: уволен" in stop
    assert messenger.to(ACC_TWO) == []


async def test_accounts_share_the_load(handoff, messenger, db_session, organization, admin_user):
    await _link(handoff)
    await handoff.tick()
    await _person(db_session, organization, admin_user, "Первый")
    await handoff.tick()
    await _person(db_session, organization, admin_user, "Второй", tg="second")
    await handoff.tick()
    assert len(messenger.to(ACC_ONE)) == 1 and len(messenger.to(ACC_TWO)) == 1


async def test_baseline_skips_same_event_but_not_next(handoff, messenger, db_session, organization, admin_user):
    await _link(handoff)
    old = await _person(db_session, organization, admin_user, "Уже На Практике")
    await _person(db_session, organization, admin_user, "Уже В Отделе", status=EntityStatus.transferred,
                  first_day="2026-10-01")
    await handoff.tick()
    await handoff.tick()
    assert messenger.sent == []  # истории не пишем
    await _transfer(db_session, old)
    await handoff.tick()
    [transfer] = messenger.to(ACC_ONE)
    assert transfer.startswith("#onboarding_transfer") and f"id: {old.id}" in transfer


async def test_missing_data_asks_hr_once(handoff, messenger, db_session, organization, admin_user):
    await _link(handoff)
    await handoff.tick()
    no_nick = await _person(db_session, organization, admin_user, "Без Ника", tg=None)
    await _person(db_session, organization, admin_user, "Без Даты", tg="no_date", practice=None)
    await handoff.tick()
    await handoff.tick()
    notices = messenger.to(FALLBACK)
    assert len(notices) == 2
    assert any("нет Telegram и телефона" in n for n in notices)
    assert any("не указана дата выхода на практику" in n for n in notices)

    no_nick.telegram_usernames = ["found_nick"]
    await db_session.commit()
    await handoff.tick()
    assert "Telegram: @found_nick" in messenger.to(ACC_ONE)[0]


async def test_transfer_without_first_day_waits(handoff, messenger, db_session, organization, admin_user):
    await _link(handoff)
    await handoff.tick()
    person = await _person(db_session, organization, admin_user, "Иван Петров")
    await handoff.tick()
    person.status = EntityStatus.transferred  # дату выхода не поставили
    await db_session.commit()
    await handoff.tick()
    assert "не указана дата выхода в отдел" in messenger.to(FALLBACK)[0]
    assert len(messenger.to(ACC_ONE)) == 1  # только практика


async def test_rejected_before_any_event_is_silent(handoff, messenger, db_session, organization, admin_user):
    await _link(handoff)
    await handoff.tick()
    person = await _person(db_session, organization, admin_user, "Без Ника", tg=None)
    await handoff.tick()
    person.status = EntityStatus.rejected
    await db_session.commit()
    await handoff.tick()
    assert messenger.to(ACC_ONE) == [] and messenger.to(ACC_TWO) == []
    async with handoff.sessions() as s:
        row = await s.scalar(select(Handoff).where(Handoff.entity_id == person.id))
    assert row.status == "stopped" and row.stop_sent_at is None


async def test_intermediate_stage_sends_nothing(handoff, messenger, db_session, organization, admin_user):
    await _link(handoff)
    await handoff.tick()
    person = await _person(db_session, organization, admin_user, "Иван Петров")
    await handoff.tick()
    person.status = EntityStatus.offer  # после практики — оффер: не стоп, ждём перевода
    await db_session.commit()
    await handoff.tick()
    assert len(messenger.to(ACC_ONE)) == 1


async def test_stages_off_by_default_and_on_when_enabled(async_engine, messenger, clock, db_session,
                                                         organization, admin_user):
    for stages, expected in ((False, 0), (True, 1)):
        messenger.sent.clear()
        svc = _service(async_engine, messenger, clock, handoff_stages=stages)
        await _link(svc)
        await svc.tick()
        person = await _person(db_session, organization, admin_user, f"Сотрудник {stages}",
                               status=EntityStatus.transferred, first_day="2026-11-12", tg=f"t{stages}")
        clock.now = datetime(2026, 11, 3, 9, 0)
        await svc.tick()
        clock.now = datetime(2026, 11, 17, 9, 1)  # день 6, 12:01 МСК
        await svc.tick()
        weeks = [t for t in messenger.sent if "Этап: week" in t.text]
        assert len(weeks) == expected, stages
        person.status = EntityStatus.dismissed  # чтобы второй проход начинал с чистого листа
        await db_session.commit()
        await svc.tick()


async def test_webhook_delivery_signed(async_engine, messenger, clock, db_session, organization, admin_user):
    posted = []

    async def poster(url, body, headers):
        posted.append((url, body, headers))

    svc = _service(async_engine, messenger, clock, handoff_accounts=(),
                   handoff_webhook_url="https://seller.example/hr", handoff_webhook_secret="s3cret", poster=poster)
    await svc.tick()
    person = await _person(db_session, organization, admin_user, "Иван Петров")
    assert await svc.tick() == 1
    [(url, body, headers)] = posted
    assert url == "https://seller.example/hr" and headers["X-Onboarding-Event"] == "practice"
    expected = hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    assert headers["X-Onboarding-Signature"] == f"sha256={expected}"
    data = json.loads(body)
    assert data["event"] == "practice" and data["id"] == person.id
    assert data["practice_start_iso"] == "2026-11-05T10:00" and data["telegram"] == "@ivan_p"
    assert messenger.sent == []  # в Telegram ничего


async def test_webhook_failure_retries_later(async_engine, messenger, clock, db_session, organization, admin_user):
    poster = AsyncMock(side_effect=[SendError("вебхук ответил 502"), None])
    svc = _service(async_engine, messenger, clock, handoff_accounts=(),
                   handoff_webhook_url="https://seller.example/hr", poster=poster)
    await svc.tick()
    await _person(db_session, organization, admin_user, "Иван Петров")
    assert await svc.tick() == 0
    assert await svc.tick() == 0  # пауза 10 минут — не долбим
    clock.now = datetime(2026, 11, 3, 9, 11)
    assert await svc.tick() == 1
    assert poster.await_count == 2


async def test_no_linked_account_waits(handoff, messenger, clock, db_session, organization, admin_user):
    await handoff.tick()
    await _person(db_session, organization, admin_user, "Иван Петров")
    await handoff.tick()
    await handoff.tick()
    assert len(messenger.to(FALLBACK)) == 1 and "ни один HR-аккаунт" in messenger.to(FALLBACK)[0]
    await handoff.register_account(ACC_ONE, "hr_one")
    clock.now = datetime(2026, 11, 3, 9, 11)
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
    monkeypatch.setattr(app_settings, "onboarding_handoff_webhook_url", "")
    await handoff.register_account(ACC_ONE, "hr_one")
    await _person(db_session, organization, admin_user, "Уже На Практике")
    await handoff.tick()
    await _person(db_session, organization, admin_user, "Без Ника", tg=None)
    sent = await _person(db_session, organization, admin_user, "Передан", tg="sent_nick")
    await handoff.tick()
    r = await client.get("/api/onboarding/handoffs", headers=auth_headers(admin_token))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["delivery"] == "telegram"
    assert data["accounts"] == [{"username": "@hr_one", "linked": True}, {"username": "@hr_two", "linked": False}]
    by_name = {row["full_name"]: row for row in data["handoffs"]}
    assert "Уже На Практике" not in by_name  # baseline не показываем
    assert by_name["Без Ника"]["waiting_reason"] == "нет Telegram и телефона в карточке"
    assert by_name["Передан"]["practice_sent_at"] and by_name["Передан"]["account"] == "@hr_one"
    assert sent.id == by_name["Передан"]["entity_id"]
