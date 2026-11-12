"""Пинг о комментарии в рабочий чат (12.11.2026): вместо картинки в Telegram
уходила служебная метка «[attachment:242:screenshot-….png:149845]»."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.models.database import Project, ProjectTask, TaskAttachment
from api.services import evening_report as ev

MARK = "готово\n[attachment:242:screenshot-1794474711231.png:149845]"


def test_marker_becomes_file_line():
    text, files = ev.split_attachments(MARK)
    assert text == "готово"
    assert files == [(242, "screenshot-1794474711231.png")]
    ping = ev.format_comment_ping("Super Admin", "New Hr", "NH-1", "Изменить статусы", MARK, 42, 7)
    assert "[attachment:" not in ping
    assert "📎 screenshot-1794474711231.png" in ping
    assert "готово" in ping


def test_only_attachment_and_html_is_escaped():
    ping = ev.format_comment_ping("A<b>", "P", "K", "T", "[attachment:1:a.png:10]", 1, 1)
    assert "A&lt;b&gt;" in ping and "📎 a.png" in ping
    ping = ev.format_comment_ping("A", "P", "K", "T", "if a < b && c > d", 1, 1)
    assert "a &lt; b &amp;&amp; c &gt; d" in ping


def test_digest_hides_markers():
    out = ev.format_digest("Чат", None, None, [{
        "content": MARK, "author": "A", "task_id": 7, "task_title": "T",
        "task_key": "NH-1", "project_id": 42, "project_name": "New Hr",
    }])
    assert "[attachment:" not in out and "📎 screenshot-1794474711231.png" in out


@pytest.mark.asyncio
async def test_attachments_are_sent_after_ping(db_session, organization, admin_user):
    from api import bot as botmod

    proj = Project(org_id=organization.id, name="New Hr")
    db_session.add(proj)
    await db_session.flush()
    task = ProjectTask(project_id=proj.id, title="Изменить статусы")
    other = ProjectTask(project_id=proj.id, title="Чужая")
    db_session.add_all([task, other])
    await db_session.flush()
    img = TaskAttachment(task_id=task.id, user_id=admin_user.id, filename="u_shot.png",
                         original_filename="shot.png", file_size=4, content_type="image/png", file_data=b"\x89PNG")
    doc = TaskAttachment(task_id=task.id, user_id=admin_user.id, filename="u_spec.pdf",
                         original_filename="spec.pdf", file_size=3, content_type="application/pdf", file_data=b"%PD")
    foreign = TaskAttachment(task_id=other.id, user_id=admin_user.id, filename="u_x.png",
                             original_filename="x.png", file_size=1, content_type="image/png", file_data=b"x")
    db_session.add_all([img, doc, foreign])
    await db_session.commit()

    content = f"готово\n[attachment:{img.id}:shot.png:4]\n[attachment:{doc.id}:spec.pdf:3]\n[attachment:{foreign.id}:x.png:1]"
    fake_bot = MagicMock()
    fake_bot.send_message = AsyncMock(return_value=MagicMock(message_id=555))
    fake_bot.send_photo = AsyncMock()
    fake_bot.send_document = AsyncMock()
    with patch.object(botmod, "get_bot", return_value=fake_bot), \
         patch.object(botmod, "async_session") as maker:
        maker.return_value.__aenter__ = AsyncMock(return_value=db_session)
        maker.return_value.__aexit__ = AsyncMock()
        await botmod.notify_comment_to_chat(-100, "Super Admin", "New Hr", "NH-1", "Изменить статусы",
                                            content, proj.id, task.id)

    assert "[attachment:" not in fake_bot.send_message.await_args.kwargs["text"]
    fake_bot.send_photo.assert_awaited_once()
    assert fake_bot.send_photo.await_args.kwargs["reply_to_message_id"] == 555
    fake_bot.send_document.assert_awaited_once()          # pdf — документом
    # вложение чужой задачи не отправляется
    assert fake_bot.send_photo.await_count + fake_bot.send_document.await_count == 2
