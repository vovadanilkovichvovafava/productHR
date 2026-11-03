"""Один OnboardingService на процесс и воркер расписания.

Модуль выключен (get_service() → None), если нет TELEGRAM_BOT_TOKEN или ONBOARDING_WALLET_KEY.
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

    return bool(settings.telegram_bot_token and settings.onboarding_wallet_key)


def handoff_enabled() -> bool:
    from api.config import settings

    return bool(settings.telegram_bot_token and settings.onboarding_handoff_accounts.strip())


async def get_handoff():
    """HandoffService или None, если не задан TELEGRAM_BOT_TOKEN или ONBOARDING_HANDOFF_ACCOUNTS."""
    global _handoff
    if _handoff is not None or not handoff_enabled():
        return _handoff
    async with _lock:
        if _handoff is None:
            from api.bot import get_bot
            from api.database import AsyncSessionLocal

            from .handoff import HandoffService
            from .service import utcnow
            from .telegram import AiogramMessenger

            _handoff = HandoffService(AsyncSessionLocal, AiogramMessenger(get_bot()), Settings.from_app(), utcnow)
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
            _service = OnboardingService(
                AsyncSessionLocal, AiogramMessenger(bot), settings, WalletCipher(settings.wallet_enc_key)
            )
    return _service


def set_service(service: Optional[OnboardingService]) -> None:
    """Для тестов: подставить сервис с фейковым мессенджером."""
    global _service
    _service = service


async def run_worker(interval_seconds: float = 30) -> None:
    """Раз в interval_seconds выполняет созревшие задачи (повторы, Loom, опросы, напоминания)."""
    if not enabled() and not handoff_enabled():
        logger.info("ONBOARDING выключен: нет TELEGRAM_BOT_TOKEN или ONBOARDING_WALLET_KEY / ONBOARDING_HANDOFF_ACCOUNTS")
        return
    logger.info("ONBOARDING воркер запущен (бот: %s, передача аккаунтам: %s)", enabled(), handoff_enabled())
    while True:
        try:
            service = await get_service()
            if service is not None:
                done = await service.run_due_jobs()
                if done:
                    logger.info("ONBOARDING jobs done=%s", done)
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
