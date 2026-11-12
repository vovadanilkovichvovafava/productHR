"""Сообщения владельца, из которых бот не завёл задачу (12.11.2026).

1. «на проекте New Hr изменить статусы на странице Штат…» — регулярка-отбор
   не знала глагола «изменить» и ловила глаголы только в начале строки, так что
   до модели сообщение не дошло.
2. «Ильнар Задача на проекте Hew Hr …» — опечатка в названии из двух слов: по
   одному слову «Hew»/«Hr» с «New HR» не сравнить.
"""
import pytest

from api.models.database import Project
from api.services import task_trigger as tt

STATUS_TEXT = "на проекте New Hr изменить статуты на странице Штат с уволен / уволился на Мы уволили / Сам уволился"
LIST_TEXT = ("Ильнар Задача на проекте Hew Hr нужно улучшить этот список чтобы он не был монотонным "
             "каждая воронка крупнее у нее есть заливка небольшая и она как блок должна выглядеть")


@pytest.mark.parametrize("text", [STATUS_TEXT, STATUS_TEXT.replace("New", "Hew"), LIST_TEXT])
def test_owner_messages_pass_prefilter(text):
    assert tt.should_trigger(text)


@pytest.mark.parametrize("text", ["в проекте всё хорошо, спасибо", "что за ссылка?", "вот что что должно быть"])
def test_project_word_alone_is_not_a_trigger(text):
    assert not tt.should_trigger(text)


@pytest.mark.asyncio
@pytest.mark.parametrize("text", [STATUS_TEXT, LIST_TEXT])
async def test_typo_in_two_word_project_name_still_matches(text, db_session, organization, admin_user, org_owner, monkeypatch):
    admin_user.telegram_id = 777_000_123
    db_session.add(Project(org_id=organization.id, name="New HR"))
    db_session.add(Project(org_id=organization.id, name="Saturn"))
    await db_session.commit()

    async def yes(_text):
        return True

    async def parsed(_text, _user, _existing):
        return [{"title": "Сделать список воронок блоками", "assignee_name": None}]

    monkeypatch.setattr(tt, "should_trigger_ai", yes)
    monkeypatch.setattr(tt, "parse_message_to_tasks", parsed)
    preview = await tt.create_tasks_from_message(
        db=db_session, message_text=text, user_name=admin_user.name,
        telegram_user_id=777_000_123, chat_id=None, dry_run=True,
    )
    assert preview and preview[0]["project"] == "New HR"
