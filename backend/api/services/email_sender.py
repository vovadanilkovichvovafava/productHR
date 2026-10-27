"""Исходящая почта кандидатам через SMTP (B5).

Включается только если заданы SMTP_HOST и SMTP_FROM. Иначе ``send_email_smtp()``
возвращает ``False`` (письмо НЕ отправлено) — чтобы UI показывал честный статус
«в очереди», а не ложное «отправлено».
"""
import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

from ..config import settings

logger = logging.getLogger("hr-analyzer.email_sender")


def is_smtp_configured() -> bool:
    """SMTP считается настроенным, если задан хост и адрес отправителя."""
    return bool(settings.smtp_host and settings.smtp_from)


def _send_sync(to: str, subject: str, html: str) -> None:
    """Блокирующая отправка через smtplib (вызывается в отдельном потоке)."""
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content("Для просмотра письма нужен HTML-совместимый почтовый клиент.")
    msg.add_alternative(html or "", subtype="html")

    with smtplib.SMTP(settings.smtp_host, int(settings.smtp_port or 587), timeout=20) as server:
        if settings.smtp_use_tls:
            server.starttls(context=ssl.create_default_context())
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)


async def send_email_smtp(to: str, subject: str, html: str) -> bool:
    """Отправить письмо.

    Returns:
        True  — письмо реально отправлено;
        False — SMTP не настроен (ничего не отправлено).

    Raises:
        Exception — если SMTP настроен, но отправка не удалась. Вызывающий код
        сам решает, как пометить статус (например, ``pending``/``bounced``).
    """
    if not is_smtp_configured():
        logger.warning("SMTP не настроен (SMTP_HOST/SMTP_FROM) — письмо для %s НЕ отправлено", to)
        return False

    await asyncio.to_thread(_send_sync, to, subject, html)
    logger.info("SMTP: письмо отправлено на %s", to)
    return True
