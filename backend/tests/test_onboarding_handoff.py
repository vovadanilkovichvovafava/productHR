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
from api.onboarding.handoff import RETRY_AFTER, HandoffService
from api.onboarding.messenger import SendError
from api.onboarding.models import Handoff, HandoffAccount
from tests.conftest import auth_headers

ACC_ONE, ACC_TWO = 501, 502
FALLBACK = -3003
SETTINGS = dict(handoff_accounts=("hr_one", "hr_two"), hr_fallback_chat_id=FALLBACK, hrd="Настя @nastya")


@dataclass
class FakeMessenger:
    sent: list = field(default_factory=list)
    deleted: list = field(default_factory=list)
    failing: set = field(default_factory=set)

    async def send(self, chat_id, text, buttons=None, html=False):
        if chat_id in self.failing:
            raise SendError("Forbidden: bot was blocked by the user")
        self.sent.append(SimpleNamespace(chat_id=chat_id, text=text, html=html, id=len(self.sent) + 1))
        return len(self.sent)

    async def delete(self, chat_id, message_id):
        self.deleted.append((chat_id, message_id))

    def to(self, chat_id):
        return [m.text for m in self.sent if m.chat_id == chat_id]

    def visible(self, chat_id):
        """Что осталось в чате после удалений — то, что видит HR."""
        gone = {mid for cid, mid in self.deleted if cid == chat_id}
        return [m.text for m in self.sent if m.chat_id == chat_id and m.id not in gone]


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
    for line in ("Отдел: SEO", "Лид: Мария", "Первый рабочий день: 12.11.2026",
                 "Испытательный срок до: 12.02.2027"):
        assert line in transfer
    assert "кошел" not in transfer.lower()

    ivan.status = EntityStatus.dismissed
    await db_session.commit()
    await handoff.tick()
    stop = messenger.to(ACC_ONE)[-1]
    assert stop.startswith("#onboarding_stop") and "Причина: уволен" in stop
    assert messenger.to(ACC_TWO) == []
    # HR получает «передан» на каждое событие (Ильнар 06.11.2026)
    assert messenger.to(FALLBACK) == [
        '<a href="https://t.me/ivan_p">Иван Петров</a> передан(а) HR-профилю: практика с 05.11.2026 10:00. '
        "Он напишет кандидату первым.",
        '<a href="https://t.me/ivan_p">Иван Петров</a> передан(а) HR-профилю: переход в отдел SEO, '
        "первый рабочий день 12.11.2026, испытательный срок до 12.02.2027.",
        '<a href="https://t.me/ivan_p">Иван Петров</a>: HR-профилю передан стоп — уволен.',
    ]


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
    assert "Без Ника: в карточке нет Telegram и телефона" in notices[0]  # ника нет — имя без ссылки
    # ФИО — ссылка на Telegram кандидата, уведомление уходит HTML-разметкой
    assert notices[1].startswith('<a href="https://t.me/no_date">Без Даты</a> на практике, но не указана дата')
    assert all(m.html for m in messenger.sent if m.chat_id == FALLBACK)

    no_nick.telegram_usernames = ["found_nick"]
    await db_session.commit()
    await handoff.tick()
    assert "Telegram: @found_nick" in messenger.to(ACC_ONE)[0]


async def test_hr_notice_replaced_when_data_added(handoff, messenger, db_session, organization, admin_user):
    """Ильнар 06.11.2026: дописал Telegram — бот молчал. Теперь «допишите» удаляется,
    вместо него — «передан»; сменилась причина — у HR одно актуальное сообщение."""
    await _link(handoff)
    await handoff.tick()
    person = await _person(db_session, organization, admin_user, "Третий Тест", tg=None, practice=None)
    await handoff.tick()
    [notice] = messenger.visible(FALLBACK)
    assert "нет Telegram и телефона" in notice

    person.telegram_usernames = ["third"]
    await db_session.commit()
    await handoff.tick()
    [notice] = messenger.visible(FALLBACK)  # прежнее удалено, осталось одно — про дату
    assert "не указана дата выхода на практику" in notice

    person.extra_data = {**person.extra_data, "practice_start_date": "2026-11-06"}
    await db_session.commit()
    await handoff.tick()
    assert messenger.visible(FALLBACK) == [
        '<a href="https://t.me/third">Третий Тест</a> передан(а) HR-профилю: практика с 06.11.2026 10:00. '
        "Он напишет кандидату первым."
    ]
    assert "Telegram: @third" in messenger.to(ACC_ONE)[0]
    async with handoff.sessions() as s:
        row = await s.scalar(select(Handoff).where(Handoff.entity_id == person.id))
    assert row.notice_message_id is None

    await handoff.tick()  # дальше тишина: подтверждение одно
    assert len(messenger.visible(FALLBACK)) == 1


async def test_hr_reminders_first_day_and_week(handoff, messenger, clock, db_session, organization, admin_user):
    """Новая версия ТЗ Маши (06.11.2026): «АТС — напоминание эйчару о старте работы» и через
    6 дней — запланировать встречу с новичком. 10:00 МСК, выходные — на понедельник."""
    await _link(handoff)
    await handoff.tick()
    person = await _person(db_session, organization, admin_user, "Иван Петров", dept="SEO")
    await handoff.tick()
    await _transfer(db_session, person, first_day="2026-11-05")  # четверг
    await handoff.tick()
    before = len(messenger.to(FALLBACK))  # «передан» за практику и перевод

    clock.now = datetime(2026, 11, 5, 6, 59)  # 09:59 МСК — рано
    await handoff.tick()
    assert len(messenger.to(FALLBACK)) == before
    clock.now = datetime(2026, 11, 5, 7, 0)  # 10:00 МСК
    await handoff.tick()
    await handoff.tick()  # второй раз не шлём
    [day1] = messenger.to(FALLBACK)[before:]
    assert day1 == ('Сегодня у <a href="https://t.me/ivan_p">Иван Петров</a> первый рабочий день в отделе SEO. '
                    "Спроси лида (Мария): установлена ли связь с новичком и назначен ли онбординг-звонок.")

    clock.now = datetime(2026, 11, 10, 7, 0)  # 5 дней спустя — вторник 10.11, 10:00 МСК
    await handoff.tick()
    [week] = messenger.to(FALLBACK)[before + 1:]
    assert week.startswith('У <a href="https://t.me/ivan_p">Иван Петров</a> шестой день в отделе SEO.')
    assert "запланируй созвон" in week


async def test_hr_reminders_skipped_when_transfer_is_late(handoff, messenger, db_session, organization,
                                                         admin_user):
    await _link(handoff)
    await handoff.tick()
    person = await _person(db_session, organization, admin_user, "Иван Петров")
    await handoff.tick()
    await _transfer(db_session, person, first_day="2026-10-01")  # перевели задним числом
    await handoff.tick()
    texts = " ".join(messenger.to(FALLBACK))
    assert "первый рабочий день в отделе." not in texts and "шестой день" not in texts
    async with handoff.sessions() as s:
        row = await s.scalar(select(Handoff).where(Handoff.entity_id == person.id))
    assert row.hr_day1_done and row.hr_week_done


STAGED = dict(handoff_accounts=(), handoff_practice_accounts=("p_one", "p_two"),
              handoff_onboarding_accounts=("onb", "prob"), hr_fallback_chat_id=FALLBACK)
P_ONE, P_TWO, ONB, PROB = 601, 602, 603, 604


async def _link_staged(svc):
    for tg, name in ((P_ONE, "p_one"), (P_TWO, "p_two"), (ONB, "onb"), (PROB, "prob")):
        assert await svc.register_account(tg, name)


async def test_staged_accounts_route_events_by_stage(async_engine, messenger, clock, db_session,
                                                     organization, admin_user):
    """Админ 10.11.2026: пребординг — два аккаунта практики (нагрузка делится), онбординг — два
    аккаунта (онбординг и испытательный), переход в отдел получает каждый."""
    svc = _service(async_engine, messenger, clock, **STAGED)
    await _link_staged(svc)
    await svc.tick()
    ivan = await _person(db_session, organization, admin_user, "Иван Петров", dept="SEO")
    await svc.tick()
    await _person(db_session, organization, admin_user, "Анна Смирнова", tg="anna")
    await svc.tick()
    assert [m.splitlines()[0] for m in messenger.to(P_ONE)] == ["#onboarding_practice"]
    assert [m.splitlines()[0] for m in messenger.to(P_TWO)] == ["#onboarding_practice"]
    assert messenger.to(ONB) == [] and messenger.to(PROB) == []

    await _transfer(db_session, ivan)
    await svc.tick()
    assert messenger.to(ONB)[-1].startswith("#onboarding_transfer")
    assert messenger.to(PROB)[-1].startswith("#onboarding_transfer")
    assert len(messenger.to(P_ONE)) == 1  # аккаунту практики перехода нет

    ivan.status = EntityStatus.dismissed
    await db_session.commit()
    await svc.tick()
    # стоп — каждому, кто вёл Ивана, по одному разу; Анну вёл другой аккаунт практики
    for chat in (P_ONE, ONB, PROB):
        assert [m.splitlines()[0] for m in messenger.to(chat)].count("#onboarding_stop") == 1
    assert all(not m.startswith("#onboarding_stop") for m in messenger.to(P_TWO))


async def test_staged_retry_does_not_duplicate(async_engine, messenger, clock, db_session, organization,
                                               admin_user):
    svc = _service(async_engine, messenger, clock, **STAGED)
    await _link_staged(svc)
    await svc.tick()
    ivan = await _person(db_session, organization, admin_user, "Иван Петров")
    await svc.tick()
    await _transfer(db_session, ivan)
    messenger.failing.add(PROB)  # аккаунт испытательного недоступен
    await svc.tick()
    assert len(messenger.to(ONB)) == 1 and messenger.to(PROB) == []
    messenger.failing.clear()
    clock.now += RETRY_AFTER
    await svc.tick()
    assert len(messenger.to(ONB)) == 1  # онбордингу второй раз не шлём
    assert messenger.to(PROB)[0].startswith("#onboarding_transfer")
    async with svc.sessions() as s:
        row = await s.scalar(select(Handoff).where(Handoff.entity_id == ivan.id))
        names = {a.id: a.username for a in (await s.scalars(select(HandoffAccount))).all()}
    assert row.transfer_sent_at and row.delivered is None
    assert sorted(names[int(i)] for i in row.onboarding_account_ids.split(",")) == ["onb", "prob"]


async def test_hr_notice_removed_on_stop_while_waiting(handoff, messenger, db_session, organization, admin_user):
    await _link(handoff)
    await handoff.tick()
    person = await _person(db_session, organization, admin_user, "Без Ника", tg=None)
    await handoff.tick()
    person.status = EntityStatus.rejected
    await db_session.commit()
    await handoff.tick()
    assert messenger.visible(FALLBACK) == []  # отказали, пока ждали: «допишите» убрано, нового нет


async def test_transfer_without_first_day_waits(handoff, messenger, db_session, organization, admin_user):
    await _link(handoff)
    await handoff.tick()
    person = await _person(db_session, organization, admin_user, "Иван Петров")
    await handoff.tick()
    person.status = EntityStatus.transferred  # дату выхода не поставили
    await db_session.commit()
    await handoff.tick()
    practice_ok, waiting = messenger.to(FALLBACK)
    assert "передан(а) HR-профилю: практика с 05.11.2026 10:00" in practice_ok
    assert "не указана дата выхода в отдел" in waiting
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
    assert messenger.to(ACC_ONE) == [] and messenger.to(ACC_TWO) == []  # аккаунтам — ничего
    assert "передан(а) HR-профилю" in messenger.to(FALLBACK)[0]  # HR видит, что передали


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
    assert len(messenger.to(FALLBACK)) == 1 and "HR-аккаунт ещё не написал боту" in messenger.to(FALLBACK)[0]
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
    assert data["accounts"] == [{"username": "@hr_one", "linked": True, "stages": []},
                                {"username": "@hr_two", "linked": False, "stages": []}]
    by_name = {row["full_name"]: row for row in data["handoffs"]}
    assert "Уже На Практике" not in by_name  # baseline не показываем
    assert by_name["Без Ника"]["waiting_reason"] == "нет Telegram и телефона в карточке"
    assert by_name["Передан"]["practice_sent_at"] and by_name["Передан"]["account"] == "@hr_one"
    assert sent.id == by_name["Передан"]["entity_id"]


async def test_accounts_by_telegram_id(async_engine, messenger, clock, db_session, organization, admin_user):
    """У купленных аккаунтов часто нет @ника — в списке их числовой ID, подключены без /start."""
    svc = _service(async_engine, messenger, clock, handoff_accounts=("777001",))
    await svc.tick()
    await _person(db_session, organization, admin_user, "Иван Петров")
    assert await svc.tick() == 1
    assert messenger.to(777001)[0].startswith("#onboarding_practice")
    # /start с этого аккаунта без ника тоже узнаётся по ID
    assert await svc.register_account(777001, None)
    assert not await svc.register_account(777002, None)


async def test_start_from_stranger_gets_staffwise_reply(monkeypatch, caplog):
    """Не сотрудник на /start — временный ответ Staffwise, а не меню «Энцеладуса»; ID и ник — в лог."""
    import api.bot as bot_module
    from api.onboarding import texts

    monkeypatch.setattr(bot_module, "_get_user_access", AsyncMock(return_value=None))
    message = SimpleNamespace(
        text="/start", chat=SimpleNamespace(type="private", id=4242),
        from_user=SimpleNamespace(id=4242, username="someone"), answer=AsyncMock(),
    )
    with caplog.at_level("INFO", logger="hr-analyzer.onboarding"):
        await bot_module.cmd_start(message)
    assert message.answer.await_args.args[0] == texts.STAFFWISE_START_TEMP
    assert "STAFFWISE_CONTACT via=start user_id=4242 @someone" in caplog.text


async def test_start_from_employee_keeps_menu(monkeypatch):
    import api.bot as bot_module

    monkeypatch.setattr(bot_module, "_get_user_access", AsyncMock(return_value={"org_id": 1, "is_admin": False}))
    monkeypatch.setattr(bot_module, "main_menu_kb", lambda access: None)
    message = SimpleNamespace(
        text="/start", chat=SimpleNamespace(type="private", id=4243),
        from_user=SimpleNamespace(id=4243, username="employee"), answer=AsyncMock(),
    )
    await bot_module.cmd_start(message)
    assert "Добро пожаловать" in message.answer.await_args.args[0]


def _text_message(user_id, username, text="привет"):
    return SimpleNamespace(
        text=text, chat=SimpleNamespace(type="private", id=user_id),
        from_user=SimpleNamespace(id=user_id, username=username, full_name="Кто-то"), answer=AsyncMock(),
    )


async def test_any_text_from_stranger_logs_id_and_replies(monkeypatch, caplog):
    """Не сотрудник пишет любой текст — временный ответ и ID в лог, без AI-сводки и без «привяжите аккаунт»."""
    import api.bot as bot_module
    from api.onboarding import texts

    monkeypatch.setattr(bot_module, "_handle_access_chat_reply", AsyncMock(return_value=False))
    monkeypatch.setattr(bot_module, "_get_user_access", AsyncMock(return_value=None))
    message = _text_message(5151, "hr_acc_x")
    with caplog.at_level("INFO", logger="hr-analyzer.onboarding"):
        await bot_module.cmd_ai_digest(message)
    assert message.answer.await_args.args[0] == texts.STAFFWISE_START_TEMP
    assert "STAFFWISE_CONTACT via=text user_id=5151 @hr_acc_x" in caplog.text


async def test_any_text_from_listed_account_links_it(handoff, monkeypatch):
    """HR-аккаунт из списка подключается любым сообщением, не только /start."""
    import api.bot as bot_module

    monkeypatch.setattr(bot_module, "_handle_access_chat_reply", AsyncMock(return_value=False))
    monkeypatch.setattr(bot_module, "_get_user_access", AsyncMock(return_value=None))
    message = _text_message(ACC_ONE, "HR_one", "здравствуйте")
    await bot_module.cmd_ai_digest(message)
    assert "Аккаунт подключён" in message.answer.await_args.args[0]
    async with handoff.sessions() as s:
        account = await s.scalar(select(HandoffAccount).where(HandoffAccount.username == "hr_one"))
    assert account.tg_id == ACC_ONE


async def test_employee_start_is_logged_too(monkeypatch, caplog):
    """ID в лог пишется у ЛЮБОГО, кто пишет боту, — сотрудник тоже (а меню у него как было)."""
    import api.bot as bot_module

    monkeypatch.setattr(bot_module, "_get_user_access", AsyncMock(return_value={"org_id": 1, "is_admin": False}))
    monkeypatch.setattr(bot_module, "main_menu_kb", lambda access: None)
    message = SimpleNamespace(
        text="/start", chat=SimpleNamespace(type="private", id=6161),
        from_user=SimpleNamespace(id=6161, username="staff_guy", full_name="Сотрудник"), answer=AsyncMock(),
    )
    with caplog.at_level("INFO", logger="hr-analyzer.onboarding"):
        await bot_module.cmd_start(message)
    assert "STAFFWISE_CONTACT via=start user_id=6161 @staff_guy" in caplog.text
    assert "Добро пожаловать" in message.answer.await_args.args[0]


async def test_sticker_from_stranger_counts(monkeypatch, caplog):
    """Стикер/фото/голосовое от не-сотрудника — ID в лог и тот же ответ, что на текст."""
    import api.bot as bot_module
    from api.onboarding import telegram as onboarding_tg
    from api.onboarding import texts

    monkeypatch.setattr(bot_module, "_get_user_access", AsyncMock(return_value=None))
    message = SimpleNamespace(
        text=None, chat=SimpleNamespace(type="private", id=7171),
        from_user=SimpleNamespace(id=7171, username="hr_sticker", full_name="HR"), answer=AsyncMock(),
    )
    with caplog.at_level("INFO", logger="hr-analyzer.onboarding"):
        await onboarding_tg.private_non_text(message)
    assert "STAFFWISE_CONTACT via=media user_id=7171 @hr_sticker" in caplog.text
    assert message.answer.await_args.args[0] == texts.STAFFWISE_START_TEMP


async def test_sticker_from_employee_only_logged(monkeypatch, caplog):
    import api.bot as bot_module
    from api.onboarding import telegram as onboarding_tg

    monkeypatch.setattr(bot_module, "_get_user_access", AsyncMock(return_value={"org_id": 1}))
    message = SimpleNamespace(
        text=None, chat=SimpleNamespace(type="private", id=8181),
        from_user=SimpleNamespace(id=8181, username="staff_s", full_name="S"), answer=AsyncMock(),
    )
    with caplog.at_level("INFO", logger="hr-analyzer.onboarding"):
        await onboarding_tg.private_non_text(message)
    assert "user_id=8181" in caplog.text
    message.answer.assert_not_called()


# ------------------------------------------- обратно от HR-профиля: кошелёк и ответы

INBOUND_SECRET = "inbound-test-secret"


@pytest.fixture
def inbound_on(monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setattr("api.config.settings.onboarding_inbound_secret", INBOUND_SECRET)
    monkeypatch.setattr("api.config.settings.onboarding_wallet_key", Fernet.generate_key().decode())


async def _handed_over(handoff, db, org, user, name="Иван Петров"):
    await _link(handoff)
    await handoff.tick()
    entity = await _person(db, org, user, name)
    assert await handoff.tick() == 1
    return entity


def _signed(payload: dict) -> tuple[bytes, dict]:
    body = json.dumps(payload, ensure_ascii=False).encode()
    digest = hmac.new(INBOUND_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return body, {"Content-Type": "application/json", "X-Onboarding-Signature": f"sha256={digest}"}


async def test_inbound_saves_wallet_and_answers(client, handoff, inbound_on, db_session, org_owner,
                                                admin_token, organization, admin_user):
    entity = await _handed_over(handoff, db_session, organization, admin_user)
    body, headers = _signed({
        "id": entity.id,
        "wallet": "TRC20: TReturned",
        "answers": [
            {"survey": "week", "question": "Как прошла первая неделя?", "answer": "Норм",
             "answered_at": "2026-11-12T15:00:00+03:00"},
            {"survey": "week", "question": "Что мешает?", "answer": "Нет доступа к ПП", "signal": True},
        ],
    })
    r = await client.post("/api/onboarding/inbound", content=body, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "id": entity.id, "wallet": True, "answers": 2}

    # повтор того же вопроса — перезапись, а не дубль; Bearer тоже принимается
    r = await client.post("/api/onboarding/inbound", headers={"Authorization": f"Bearer {INBOUND_SECRET}"}, json={
        "id": entity.id, "answers": [{"survey": "week", "question": "Что мешает?", "answer": "Уже всё ок"}],
    })
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/onboarding/entities/{entity.id}/answers", headers=auth_headers(admin_token))
    data = r.json()
    assert data["has_wallet"] is True
    assert [(a["question"], a["answer"], a["is_signal"]) for a in data["answers"]] == [
        ("Как прошла первая неделя?", "Норм", False), ("Что мешает?", "Уже всё ок", False),
    ]
    assert data["answers"][0]["answered_at"].startswith("2026-11-12T12:00")  # в UTC

    r = await client.get("/api/onboarding/wallets", headers=auth_headers(admin_token))
    assert r.status_code == 200, r.text
    [row] = r.json()
    assert row["entity_id"] == entity.id and row["wallet"] == "TRC20: TReturned" and row["lead_name"] == "Анна"


async def test_inbound_rejects_bad_secret_and_unknown_id(client, handoff, inbound_on, db_session,
                                                         organization, admin_user):
    entity = await _handed_over(handoff, db_session, organization, admin_user)
    body, headers = _signed({"id": entity.id, "wallet": "x"})
    bad = {**headers, "X-Onboarding-Signature": "sha256=" + "0" * 64}
    assert (await client.post("/api/onboarding/inbound", content=body, headers=bad)).status_code == 401
    assert (await client.post("/api/onboarding/inbound", json={"id": entity.id, "wallet": "x"},
                              headers={"Authorization": "Bearer wrong"})).status_code == 401

    stranger = await _person(db_session, organization, admin_user, "Не Передавали", status=EntityStatus.new)
    body, headers = _signed({"id": stranger.id, "wallet": "x"})
    assert (await client.post("/api/onboarding/inbound", content=body, headers=headers)).status_code == 404

    body, headers = _signed({"id": entity.id})
    assert (await client.post("/api/onboarding/inbound", content=body, headers=headers)).status_code == 422


async def test_inbound_off_without_secret(client, monkeypatch):
    monkeypatch.setattr("api.config.settings.onboarding_inbound_secret", "")
    r = await client.post("/api/onboarding/inbound", json={"id": 1, "wallet": "x"},
                          headers={"Authorization": "Bearer "})
    assert r.status_code == 503
