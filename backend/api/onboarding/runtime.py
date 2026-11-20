"""Один OnboardingService на процесс и воркер расписания.

Модуль выключен (get_service() → None), если нет TELEGRAM_BOT_TOKEN или нет ни
ONBOARDING_WALLET_KEY, ни ONBOARDING_HANDOFF_TO_BOT (события по статусу без кошельков, мит 19.11.2026).
"""

import asyncio
import logging
from typing import Optional

from .config import Settings
from .crypto import WalletCipher
from .service import OnboardingService

logger = logging.getLogger("hr-analyzer.onboarding")

_service: Optional[OnboardingService] = None
_handoff = None  # HandoffService — передача людей HR-аккаунтам автоспамера/AI-селлера
_lock = asyncio.Lock()


def enabled() -> bool:
    from api.config import settings

    return bool(settings.telegram_bot_token
                and (settings.onboarding_wallet_key or settings.onboarding_handoff_to_bot))


def handoff_enabled() -> bool:
    from api.config import settings

    return bool(
        (settings.telegram_bot_token and settings.onboarding_handoff_to_bot)
        or settings.onboarding_handoff_webhook_url.strip()
        or (settings.telegram_bot_token and any(v.strip() for v in (
            settings.onboarding_handoff_accounts, settings.onboarding_handoff_preboarding_accounts,
            settings.onboarding_handoff_onboarding_accounts)))
    )


async def get_handoff():
    """HandoffService или None: нужен ONBOARDING_HANDOFF_WEBHOOK_URL либо бот + ONBOARDING_HANDOFF_ACCOUNTS."""
    global _handoff
    if _handoff is not None or not handoff_enabled():
        return _handoff
    async with _lock:
        if _handoff is None:
            from api.config import settings as app
            from api.database import AsyncSessionLocal

            from .handoff import HandoffService, NullMessenger
            from .service import utcnow

            messenger = NullMessenger()
            if app.telegram_bot_token:
                from api.bot import get_bot

                from .telegram import AiogramMessenger

                messenger = AiogramMessenger(get_bot())
            _handoff = HandoffService(AsyncSessionLocal, messenger, Settings.from_app(), utcnow,
                                      bot_sink=get_service)
    return _handoff


def set_handoff(handoff) -> None:
    """Для тестов."""
    global _handoff
    _handoff = handoff


async def get_service() -> Optional[OnboardingService]:
    global _service
    if _service is not None or not enabled():
        return _service
    async with _lock:
        if _service is None:
            from api.bot import get_bot
            from api.database import AsyncSessionLocal

            from .telegram import AiogramMessenger

            bot = get_bot()
            settings = Settings.from_app()
            if not settings.bot_username:
                me = await bot.me()
                settings = Settings.from_app(bot_username=me.username or "")
            cipher = WalletCipher(settings.wallet_enc_key) if settings.wallet_enc_key else None
            _service = OnboardingService(AsyncSessionLocal, AiogramMessenger(bot), settings, cipher)
    return _service


def set_service(service: Optional[OnboardingService]) -> None:
    """Для тестов: подставить сервис с фейковым мессенджером."""
    global _service
    _service = service


async def run_worker(interval_seconds: float = 30) -> None:
    """Раз в interval_seconds выполняет созревшие задачи (повторы, Loom, опросы, напоминания)."""
    if not enabled() and not handoff_enabled():
        logger.info("ONBOARDING выключен: нет TELEGRAM_BOT_TOKEN или ONBOARDING_WALLET_KEY / "
                    "ONBOARDING_HANDOFF_TO_BOT / ONBOARDING_HANDOFF_ACCOUNTS")
        return
    logger.info("ONBOARDING воркер запущен (бот: %s, передача аккаунтам: %s)", enabled(), handoff_enabled())
    while True:
        try:
            service = await get_service()
            if service is not None:
                done = await service.run_due_jobs()
                if done:
                    logger.info("ONBOARDING jobs done=%s", done)
                await service.ping_hr_changes()  # смена HR у кандидата — в Telegram (мит 19.11.2026)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("ONBOARDING воркер")
        try:
            handoff = await get_handoff()
            if handoff is not None:
                sent = await handoff.tick()
                if sent:
                    logger.info("ONBOARDING handoff sent=%s", sent)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("ONBOARDING передача")
        await asyncio.sleep(interval_seconds)
