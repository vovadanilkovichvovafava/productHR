from __future__ import annotations

from typing import Protocol

# Ряды inline-кнопок: [[(текст, callback_data), ...], ...]
Buttons = list[list[tuple[str, str]]]


class SendError(Exception):
    """Telegram не принял сообщение: бот заблокирован, чат не найден и т. п."""


class Messenger(Protocol):
    async def send(self, chat_id: int, text: str, buttons: Buttons | None = None, html: bool = False) -> int | None:
        """html=True — text в HTML-разметке Telegram (ссылки), спецсимволы экранирует вызывающий.
        Возвращает номер сообщения (если мессенджер его знает) — чтобы потом удалить."""

    async def delete(self, chat_id: int, message_id: int) -> None:
        """Удалить своё сообщение. Не вышло (старше 48 ч, уже удалено) — SendError."""
