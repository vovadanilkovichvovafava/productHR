"""Проект чата по умолчанию (владелец, 12.11.2026): «привязать чат „Новая ATS -
Тест“ к проекту New Hr, чтобы не писать название проекта, а бот понимал, что
из этого чата задачи — для New Hr». Ставится командой /chatproject в чате."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from api.models.database import Chat, ChatType, OrgMember, OrgRole, Project
from api.services import task_trigger as tt

TG_CHAT = -1009990001


def test_find_projects_by_name():
    ps = [SimpleNamespace(id=1, name="New Hr"), SimpleNamespace(id=2, name="Saturn"),
          SimpleNamespace(id=3, name="Saturn Ads")]
    assert [p.id for p in tt.find_projects_by_name("new hr", ps)] == [1]
    assert [p.id for p in tt.find_projects_by_name("NewHR", ps)] == [1]
    assert [p.id for p in tt.find_projects_by_name("Hew Hr", ps)] == [1]      # опечатка
    assert [p.id for p in tt.find_projects_by_name("saturn", ps)] == [2]      # целиком — один
    assert {p.id for p in tt.find_projects_by_name("satur", ps)} == {2, 3}    # часть — переспросить
    assert tt.find_projects_by_name("Марс", ps) == []


async def _setup(db, org, user, project_name="New Hr"):
    user.telegram_id = 555_000_111
    proj = Project(org_id=org.id, name=project_name)
    other = Project(org_id=org.id, name="Saturn")
    db.add_all([proj, other])
    chat = Chat(telegram_chat_id=TG_CHAT, title="Новая ATS - Тест", chat_type=ChatType.work,
                owner_id=user.id, org_id=org.id, is_active=True)
    db.add(chat)
    await db.commit()
    return proj, other, chat


def _patch_ai(monkeypatch):
    async def yes(_t):
        return True

    async def parsed(_t, _u, _e):
        return [{"title": "Поменять подписи статусов", "assignee_name": None}]

    monkeypatch.setattr(tt, "should_trigger_ai", yes)
    monkeypatch.setattr(tt, "parse_message_to_tasks", parsed)


@pytest.mark.asyncio
async def test_message_without_project_goes_to_chat_project(db_session, organization, admin_user, org_owner, monkeypatch):
    proj, other, chat = await _setup(db_session, organization, admin_user)
    _patch_ai(monkeypatch)
    kw = dict(db=db_session, user_name=admin_user.name, telegram_user_id=555_000_111, chat_id=TG_CHAT, dry_run=True)

    text = "изменить статусы на странице Штат с уволен на Мы уволили"
    assert await tt.create_tasks_from_message(message_text=text, **kw) == []   # проекта у чата нет

    chat.project_id = proj.id
    await db_session.commit()
    preview = await tt.create_tasks_from_message(message_text=text, **kw)
    assert preview and preview[0]["project"] == "New Hr"

    # Названный в сообщении проект главнее проекта чата
    preview = await tt.create_tasks_from_message(message_text="на проекте Saturn " + text, **kw)
    assert preview and preview[0]["project"] == "Saturn"


def _msg(text, chat_type="supergroup"):
    m = MagicMock()
    m.text = text
    m.chat = SimpleNamespace(id=TG_CHAT, type=chat_type)
    m.from_user = SimpleNamespace(id=555_000_111)
    m.answer = AsyncMock()
    return m


@pytest.mark.asyncio
async def test_chatproject_command(db_session, organization, admin_user, org_owner):
    from api.bot import cmd_chat_project

    proj, other, chat = await _setup(db_session, organization, admin_user)
    if not (await db_session.execute(select(OrgMember).where(OrgMember.user_id == admin_user.id))).first():
        db_session.add(OrgMember(org_id=organization.id, user_id=admin_user.id, role=OrgRole.admin))
        await db_session.commit()

    with patch("api.bot.async_session") as maker:
        maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
        maker.return_value.__aexit__ = AsyncMock()

        m = _msg("/chatproject")
        await cmd_chat_project(m)
        assert "нет проекта" in m.answer.await_args.args[0]

        m = _msg("/chatproject hew hr")
        await cmd_chat_project(m)
        assert "«New Hr»" in m.answer.await_args.args[0]
        await db_session.refresh(chat)
        assert chat.project_id == proj.id

        m = _msg("/chatproject Марс")
        await cmd_chat_project(m)
        assert "не нашёл" in m.answer.await_args.args[0]
        await db_session.refresh(chat)
        assert chat.project_id == proj.id          # неудачная попытка не сбрасывает

        m = _msg("/chatproject -")
        await cmd_chat_project(m)
        await db_session.refresh(chat)
        assert chat.project_id is None

        m = _msg("/chatproject New Hr", chat_type="private")
        await cmd_chat_project(m)
        assert "рабочем чате" in m.answer.await_args.args[0]
