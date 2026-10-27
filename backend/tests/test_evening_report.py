"""Вечерний отчёт, пинг по комментарию и итог дня (владелец, 28.09.2026).

Боль: отчёты приходят текстом на три минуты, файлом, голосом или видео, а
картину дня приходится собирать вручную.
"""
from datetime import datetime, timedelta

import pytest

from api.models.database import (
    Chat, ChatType, EveningReport, Project, ProjectTask, TaskComment,
)
from api.services import evening_report as ev
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


@pytest.mark.parametrize("text", [
    "#вечерний_отчет сегодня доделал парсер",
    "Вечерний отчёт: закрыл три задачи",
    "вечерний отчет\nсделал ревью",
    "Отчёт за день: чинил прод",
])
def test_tag_is_recognized(text):
    assert ev.has_report_tag(text)


@pytest.mark.parametrize("text", [
    "продолжаю работу",
    "отчитаюсь вечером",
    "скинь отчёт по рекламе",
])
def test_other_messages_are_not_reports(text):
    assert not ev.has_report_tag(text)


def test_tag_is_stripped_from_body():
    body = ev.strip_tag("#вечерний_отчет  Доделал парсер, завтра тесты")
    assert body == "Доделал парсер, завтра тесты"


def test_summary_is_formatted_for_reading():
    text = ev.format_summary({
        "highlight": "Парсер заработал на боевых данных",
        "done": ["Доделал парсер резюме"],
        "in_progress": ["Тесты на крайние случаи"],
        "problems": ["Падает на сканах без текста"],
        "next": ["Добавить OCR"],
    }, "Миша")
    assert "Миша" in text
    assert "Доделал парсер резюме" in text
    assert "Падает на сканах" in text
    # разделы идут блоками, а не сплошным текстом
    assert text.count("\n") >= 6


@pytest.mark.asyncio
async def test_report_is_saved_once_per_day(db_session, organization, admin_user):
    first = await ev.save_report(
        db=db_session, org_id=organization.id, user_id=admin_user.id, chat_id=-100,
        author_name="Миша", source_type="text", text="сделал А", summary={"done": ["А"]},
    )
    second = await ev.save_report(
        db=db_session, org_id=organization.id, user_id=admin_user.id, chat_id=-100,
        author_name="Миша", source_type="voice", text="сделал А и Б", summary={"done": ["А", "Б"]},
    )
    assert first.id == second.id, "повторный отчёт за день заменяет прежний, а не плодит новый"
    assert second.source_type == "voice"
    assert await ev.report_exists_today(db_session, -100) is True
    assert await ev.report_exists_today(db_session, -999) is False


@pytest.mark.asyncio
async def test_day_comments_are_collected_by_source_chat(db_session, organization, admin_user):
    """В итог дня попадают комментарии к задачам, рождённым в этом чате."""
    project = Project(
        org_id=organization.id, name="Saturn", prefix="SAT", status="active",
        created_by=admin_user.id, created_at=datetime.utcnow(),
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    mine = ProjectTask(
        project_id=project.id, task_number=1, title="Поднять сервер", status="todo",
        sort_order=0, created_by=admin_user.id, created_by_bot=True, source_chat_id=-100,
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    alien = ProjectTask(
        project_id=project.id, task_number=2, title="Чужая задача", status="todo",
        sort_order=0, created_by=admin_user.id, source_chat_id=-200,
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    db_session.add_all([mine, alien])
    await db_session.commit()
    await db_session.refresh(mine)
    await db_session.refresh(alien)

    db_session.add_all([
        TaskComment(task_id=mine.id, user_id=admin_user.id, content="Сервер поднят, гоняю тесты",
                    created_at=datetime.utcnow()),
        TaskComment(task_id=alien.id, user_id=admin_user.id, content="Это из другого чата",
                    created_at=datetime.utcnow()),
        TaskComment(task_id=mine.id, user_id=admin_user.id, content="Вчерашний",
                    created_at=datetime.utcnow() - timedelta(days=2)),
    ])
    await db_session.commit()

    comments = await ev.comments_of_day(db_session, -100)
    assert [c["content"] for c in comments] == ["Сервер поднят, гоняю тесты"]
    assert comments[0]["task_key"] == "SAT-1"


def test_digest_mentions_report_and_comments():
    text = ev.format_digest(
        "RND — Миша",
        {"done": ["Поднял сервер"], "highlight": "Сервер в бою"},
        "Миша",
        [{"content": "Гоняю тесты", "author": "Миша", "task_id": 5, "task_title": "Поднять сервер",
          "task_key": "SAT-1", "project_id": 2, "project_name": "Saturn"}],
    )
    assert "Итог дня" in text and "RND — Миша" in text
    assert "Поднял сервер" in text
    assert "SAT-1" in text and "/projects/2/tasks/5" in text


def test_digest_says_when_nothing_happened():
    text = ev.format_digest("RND — Миша", None, None, [])
    assert "Комментариев по задачам сегодня не было" in text


def test_comment_ping_has_task_link():
    text = ev.format_comment_ping(
        "Миша", "Saturn", "SAT-1", "Поднять сервер", "Готово, проверяю", 2, 5
    )
    assert "Миша" in text and "Saturn" in text and "SAT-1" in text
    assert "/projects/2/tasks/5" in text


# ── Готовность продукта ────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("готовность Saturn 70", ("Saturn", 70)),
    ("Готовность ZavodCamp 45%", ("ZavodCamp", 45)),
    ("готовность Partner Analytics 5", ("Partner Analytics", 5)),
])
def test_readiness_is_parsed(text, expected):
    assert ev.parse_readiness(text) == expected


@pytest.mark.parametrize("text", [
    "готовность 70",                    # без проекта
    "какая готовность у Saturn?",       # вопрос
    "готовность Saturn 300",            # процент вне диапазона
    "сегодня доделал парсер",
])
def test_not_readiness(text):
    assert ev.parse_readiness(text) is None


@pytest.mark.asyncio
async def test_readiness_is_set_by_hand_and_stops_autocount(db_session, organization, admin_user):
    project = Project(
        org_id=organization.id, name="Saturn", prefix="SAT", status="active",
        progress_percent=12, progress_mode="auto",
        created_by=admin_user.id, created_at=datetime.utcnow(),
    )
    db_session.add(project)
    await db_session.commit()

    updated = await ev.set_readiness(db_session, organization.id, "сатурн", 70, admin_user.id)
    assert updated is not None and updated.progress_percent == 70
    # авто-пересчёт по задачам больше не перетрёт оценку человека
    assert updated.progress_mode == "manual"
    assert updated.progress_updated_by == admin_user.id
    assert updated.progress_updated_at is not None

    assert await ev.set_readiness(db_session, organization.id, "Несуществующий", 50, admin_user.id) is None


@pytest.mark.asyncio
async def test_stale_readiness_is_reported(db_session, organization, admin_user):
    fresh = Project(
        org_id=organization.id, name="Свежий", status="active", progress_percent=80,
        progress_updated_at=datetime.utcnow(), created_by=admin_user.id, created_at=datetime.utcnow(),
    )
    never = Project(
        org_id=organization.id, name="Забытый", status="active", progress_percent=0,
        created_by=admin_user.id, created_at=datetime.utcnow(),
    )
    db_session.add_all([fresh, never])
    await db_session.commit()
    await db_session.refresh(fresh)
    await db_session.refresh(never)

    for p in (fresh, never):
        db_session.add(ProjectTask(
            project_id=p.id, title=f"Задача {p.name}", status="todo", sort_order=0,
            source_chat_id=-100, created_by=admin_user.id,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        ))
    await db_session.commit()

    stale = await ev.stale_readiness(db_session, -100)
    names = [p["name"] for p in stale]
    assert "Забытый" in names and "Свежий" not in names

    block = ev.format_readiness_block(stale)
    assert "Забытый" in block and "не ставили ни разу" in block


# ── Редактирование отчёта ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_edited_report_updates_same_record(db_session, organization, admin_user):
    """Отчёт правят в Telegram — обновляем ту же запись и ту же выжимку."""
    first = await ev.save_report(
        db=db_session, org_id=organization.id, user_id=admin_user.id, chat_id=-100,
        author_name="Миша", source_type="text", text="сделал А",
        summary={"done": ["А"]}, tg_message_id=555, reply_message_id=556,
    )
    assert first.tg_message_id == 555 and first.reply_message_id == 556

    found = await ev.find_report_by_message(db_session, -100, 555)
    assert found is not None and found.id == first.id
    assert await ev.find_report_by_message(db_session, -100, 999) is None

    updated = await ev.save_report(
        db=db_session, org_id=organization.id, user_id=admin_user.id, chat_id=-100,
        author_name="Миша", source_type="text", text="сделал А и Б",
        summary={"done": ["А", "Б"]}, tg_message_id=555, reply_message_id=556,
    )
    assert updated.id == first.id
    assert updated.summary["done"] == ["А", "Б"]
    assert "и Б" in updated.raw_text


def test_no_report_reminder_on_weekends():
    """По выходным бот про вечерний отчёт не пишет (владелец, 25.10.2026).

    Неделя 19–25.10.2026: пн–пт — рабочие, сб 24 и вс 25 — выходные.
    """
    from datetime import date

    week = {date(2026, 10, d): d in (24, 25) for d in range(19, 26)}
    for day, off in week.items():
        assert ev.is_day_off(day) is off, day
