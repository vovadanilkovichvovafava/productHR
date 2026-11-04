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
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from . import texts
from .messenger import Buttons, SendError
from .runtime import get_handoff, get_service
from .service import TOKEN_PREFIX

logger = logging.getLogger("hr-analyzer.onboarding")


class AiogramMessenger:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def send(self, chat_id: int, text: str, buttons: Buttons | None = None) -> None:
        markup = None
        if buttons:
            markup = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in buttons]
            )
        try:
            await self.bot.send_message(chat_id, text, reply_markup=markup, disable_web_page_preview=True)
        except TelegramAPIError as exc:
            raise SendError(str(exc)) from exc


# --------------------------------------------------------------- хуки для api/bot.py


def is_onboarding_token(payload: str) -> bool:
    return payload.startswith(TOKEN_PREFIX)


async def on_start(message: Message, payload: str) -> None:
    """`/start ob_…` — кандидат открыл ссылку-приглашение на практику."""
    service = await get_service()
    if service is None or message.from_user is None:
        await message.answer(texts.START_UNKNOWN)
        return
    if not await service.handle_start(message.from_user.id, payload):
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
    """Новые участники группы: кандидат пришёл в рабочий чат → приветствие с «Старт».

    Зовётся первой строкой сбора переписки, поэтому ничего не бросает: сбой здесь
    не должен стоить сообщения в базе.
    """
    members = getattr(message, "new_chat_members", None)
    if not members:
        return
    try:
        service = await get_service()
        if service is None:
            return
        me = await service.messenger.bot.me()
        joined = [(u.id, u.username) for u in members if u.id != me.id and not u.is_bot]
        if joined:
            await service.handle_members_joined(message.chat.id, joined)
    except Exception:
        logger.exception("ONBOARDING new members")


async def on_bot_added(chat_id: int, adder_tg_id: int | None) -> None:
    try:
        service = await get_service()
        if service is not None and await service.handle_bot_added(chat_id, adder_tg_id):
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
