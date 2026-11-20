"""Telegram-часть HR-бота практики и испытательного срока.

Кнопки (scr:, pstart, loom:, survey:, sv:) — свой Router, подключается к `dp` в api/bot.py:
у существующих обработчиков таких callback_data нет, конфликтов нет.

Сообщения — НЕ роутером: обработчики самого `dp` срабатывают раньше подключённых роутеров,
а в api/bot.py есть ловушки на всё (`/start` с аргументом — привязка аккаунта, любой текст
в личке — AI-сводка, любое сообщение группы — сбор переписки). Поэтому они зовут хуки
отсюда первыми строками: on_start / on_private_text / on_group_message / on_bot_added.
"""

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from . import texts
from .messenger import Buttons, SendError
from .runtime import get_handoff, get_service
from .chat_flow import SURVEY_LINK_PREFIX
from .service import TOKEN_PREFIX

logger = logging.getLogger("hr-analyzer.onboarding")


class AiogramMessenger:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def send(self, chat_id: int, text: str, buttons: Buttons | None = None, html: bool = False) -> int:
        markup = None
        if buttons:
            # Ссылка (опрос в личке из рабочего чата) — url-кнопка, остальное — callback
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t, url=d) if d.startswith("https://") else
                 InlineKeyboardButton(text=t, callback_data=d) for t, d in row]
                for row in buttons
            ])
        try:
            message = await self.bot.send_message(chat_id, text, reply_markup=markup, disable_web_page_preview=True,
                                                  parse_mode="HTML" if html else None)
        except TelegramAPIError as exc:
            raise SendError(str(exc)) from exc
        return message.message_id

    async def delete(self, chat_id: int, message_id: int) -> None:
        try:
            await self.bot.delete_message(chat_id, message_id)
        except TelegramAPIError as exc:
            raise SendError(str(exc)) from exc


# --------------------------------------------------------------- хуки для api/bot.py


def is_onboarding_token(payload: str) -> bool:
    return payload.startswith((TOKEN_PREFIX, SURVEY_LINK_PREFIX))


async def on_start(message: Message, payload: str) -> None:
    """`/start ob_…` — кандидат открыл ссылку-приглашение на практику."""
    service = await get_service()
    if service is None or message.from_user is None:
        await message.answer(texts.START_UNKNOWN)
        return
    if payload.startswith(SURVEY_LINK_PREFIX):  # «Пройти опрос» из рабочего чата
        ok = await service.handle_survey_link(message.from_user.id, payload)
    else:
        ok = await service.handle_start(message.from_user.id, payload)
    if not ok:
        await message.answer(texts.START_UNKNOWN)


async def on_plain_start(message: Message) -> bool:
    """`/start` без ссылки от HR-аккаунта из ONBOARDING_HANDOFF_ACCOUNTS — подключаем его к передаче."""
    try:
        handoff = await get_handoff()
        if handoff is None or message.from_user is None:
            return False
        if not await handoff.register_account(message.from_user.id, message.from_user.username):
            return False
    except Exception:
        logger.exception("ONBOARDING handoff register")
        return False
    await message.answer(
        "Аккаунт подключён: сюда будут приходить кандидаты на практику (#onboarding_practice), "
        "переводы в отдел (#onboarding_transfer) и остановки (#onboarding_stop)."
    )
    return True


async def on_stranger(message: Message, via: str) -> None:
    """Боту написал НЕ сотрудник (Telegram не привязан к productHR): /start или любое сообщение.

    HR-аккаунт из ONBOARDING_HANDOFF_ACCOUNTS — подключаем (любым сообщением, не только /start).
    Остальным — временный ответ Staffwise, а ID и ник — в лог STAFFWISE_CONTACT: по нему HR-аккаунт
    вписывают в список (04.11.2026, просьба Ильнара).
    """
    if await on_plain_start(message):
        return
    await message.answer(texts.STAFFWISE_START_TEMP)


def log_contact(message: Message, via: str) -> None:
    """ID, ник и имя любого, кто пишет боту в личку (сотрудник, HR-аккаунт, кандидат) — без текста
    сообщения. По строке STAFFWISE_CONTACT HR-аккаунт вписывают в ONBOARDING_HANDOFF_ACCOUNTS."""
    user = getattr(message, "from_user", None)
    logger.info(
        "STAFFWISE_CONTACT via=%s user_id=%s @%s name=%s",
        via, getattr(user, "id", None), getattr(user, "username", None) or "—",
        getattr(user, "full_name", None) or "",
    )


async def on_private_text(message: Message) -> bool:
    """True — сообщение забрал бот практики (ждал кошелёк или ответ опроса)."""
    try:
        service = await get_service()
        if service is None or message.from_user is None or not message.text:
            return False
        handled, reply = await service.handle_text(message.from_user.id, message.text)
    except Exception:
        logger.exception("ONBOARDING private text")
        return False
    if reply:
        await message.answer(reply)
    return handled


async def on_group_message(message: Message) -> None:
    """Группа: кандидат пришёл в рабочий чат → приветствие с «Старт»; текст — вечерний отчёт
    (#вечерний_отчёт) и #блокер. Текст бот видит, только если в BotFather выключен режим
    приватности (/setprivacy → Disable) или он админ чата.

    Зовётся первой строкой сбора переписки, поэтому ничего не бросает: сбой здесь
    не должен стоить сообщения в базе.
    """
    members = getattr(message, "new_chat_members", None)
    try:
        service = await get_service()
        if service is None:
            return
        if members:
            me = await service.messenger.bot.me()
            joined = [(u.id, u.username) for u in members if u.id != me.id and not u.is_bot]
            if joined:
                await service.handle_members_joined(message.chat.id, joined)
            return
        user = getattr(message, "from_user", None)
        text = getattr(message, "text", None) or getattr(message, "caption", None)
        if user is None or user.is_bot or not text:
            return
        reply = await service.handle_group_text(message.chat.id, user.id, user.username,
                                                user.full_name or user.username or str(user.id), text)
        if reply:
            await message.reply(reply)
    except Exception:
        logger.exception("ONBOARDING group message")


async def on_bot_added(chat_id: int, adder_tg_id: int | None, title: str = "") -> None:
    try:
        service = await get_service()
        if service is not None and await service.handle_bot_added(chat_id, adder_tg_id, title or ""):
            logger.info("ONBOARDING work chat welcome chat=%s adder=%s", chat_id, adder_tg_id)
    except Exception:
        logger.exception("ONBOARDING bot added chat=%s", chat_id)


# ------------------------------------------------------------------------- кнопки

router = Router(name="onboarding")


async def _drop_buttons(callback: CallbackQuery) -> None:
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramAPIError:
            pass


async def _reply(callback: CallbackQuery, text: str | None) -> None:
    await callback.answer()
    if text and isinstance(callback.message, Message):
        await callback.message.answer(text)


@router.message(F.chat.type == "private", ~F.text)
async def private_non_text(message: Message) -> None:
    """Стикер, фото, голосовое в личку — тоже засчитываем: ID в лог; не-сотруднику — как на текст.
    Своих обработчиков такого в личке у api/bot.py нет, поэтому сюда они доходят."""
    log_contact(message, "media")
    if message.from_user is None:
        return
    try:
        from api.bot import _get_user_access, async_session

        async with async_session() as session:
            access = await _get_user_access(session, message.from_user.id)
    except Exception:
        logger.exception("ONBOARDING media access check")
        return
    if not access:
        await on_stranger(message, "media")


@router.callback_query(F.data.startswith("scr:"))
async def script_answer(callback: CallbackQuery) -> None:
    service = await get_service()
    if service is None:
        await callback.answer()
        return
    reply = await service.handle_script_answer(callback.from_user.id, callback.data.removeprefix("scr:"))
    if reply:
        await _drop_buttons(callback)
    await _reply(callback, reply)


@router.callback_query(F.data == "pstart")
async def practice_start(callback: CallbackQuery) -> None:
    service = await get_service()
    if service is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    alert = await service.handle_practice_start(
        callback.message.chat.id, callback.from_user.id, callback.from_user.username
    )
    if alert:
        await callback.answer(alert, show_alert=True)
    else:
        await _drop_buttons(callback)
        await callback.answer()


@router.callback_query(F.data.startswith("pchat:"))
async def pick_chat_case(callback: CallbackQuery) -> None:
    """«Для кого этот чат?» — сотрудник выбрал кандидата."""
    service = await get_service()
    case_id = callback.data.removeprefix("pchat:")
    if service is None or not case_id.isdigit() or not isinstance(callback.message, Message):
        await callback.answer()
        return
    reply = await service.bind_chat(callback.message.chat.id, int(case_id), callback.from_user.id)
    if reply.startswith("Готово"):
        await _drop_buttons(callback)
        await callback.answer(reply)
    else:
        await callback.answer(reply, show_alert=True)


@router.message(Command("lead", "lid"), F.chat.type == "private")
async def lead_command(message: Message) -> None:
    """Лид отдела: выбирает свой отдел, владелец/админ HR подтверждает (мит 19.11.2026)."""
    service = await get_service()
    if service is None:
        return
    departments = await service.lead_departments()
    if not departments:
        await message.answer(texts.LEAD_NO_DEPARTMENTS)
        return
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=d.name, callback_data=f"leaddept:{d.id}")] for d in departments[:40]
    ])
    await message.answer(texts.LEAD_PICK_DEPARTMENT, reply_markup=markup)


@router.callback_query(F.data.startswith("leaddept:"))
async def lead_department(callback: CallbackQuery) -> None:
    service = await get_service()
    dept_id = callback.data.removeprefix("leaddept:")
    if service is None or not dept_id.isdigit():
        await callback.answer()
        return
    user = callback.from_user
    reply = await service.request_lead(user.id, user.username, user.full_name or "", int(dept_id))
    await _drop_buttons(callback)
    await _reply(callback, reply)


@router.callback_query(F.data.startswith(("leadok:", "leadno:")))
async def lead_decision(callback: CallbackQuery) -> None:
    service = await get_service()
    action, _, lead_id = callback.data.partition(":")
    if service is None or not lead_id.isdigit():
        await callback.answer()
        return
    reply = await service.decide_lead(int(lead_id), callback.from_user.id, action == "leadok")
    if reply not in (texts.LEAD_NOT_ADMIN,):
        await _drop_buttons(callback)
    await _reply(callback, reply)


@router.callback_query(F.data.startswith("loom:"))
async def loom(callback: CallbackQuery) -> None:
    service = await get_service()
    parts = callback.data.split(":", 2)
    if service is None or len(parts) != 3:
        await callback.answer()
        return
    reply = await service.handle_loom(callback.from_user.id, parts[1], parts[2])
    if reply:
        await _drop_buttons(callback)
    await _reply(callback, reply)


@router.callback_query(F.data.startswith("survey:"))
async def survey_start(callback: CallbackQuery) -> None:
    service = await get_service()
    if service is None:
        await callback.answer()
        return
    await _drop_buttons(callback)
    await _reply(callback, await service.start_survey(callback.from_user.id, callback.data.removeprefix("survey:")))


@router.callback_query(F.data.startswith("sv:"))
async def survey_answer(callback: CallbackQuery) -> None:
    service = await get_service()
    parts = callback.data.split(":")
    if service is None or len(parts) != 4 or not parts[2].isdigit() or not parts[3].isdigit():
        await callback.answer()
        return
    reply = await service.answer_survey(callback.from_user.id, parts[1], int(parts[2]), int(parts[3]))
    if reply is None:
        await _drop_buttons(callback)
    await _reply(callback, reply)
