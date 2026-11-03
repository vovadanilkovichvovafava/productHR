from __future__ import annotations

from typing import Protocol

# Ряды inline-кнопок: [[(текст, callback_data), ...], ...]
Buttons = list[list[tuple[str, str]]]


class SendError(Exception):
    """Telegram не принял сообщение: бот заблокирован, чат не найден и т. п."""


class Messenger(Protocol):
    async def send(self, chat_id: int, text: str, buttons: Buttons | None = None) -> None: ...
