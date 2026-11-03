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
_lock = asyncio.Lock()


def enabled() -> bool:
    from api.config import settings

    return bool(settings.telegram_bot_token and settings.onboarding_wallet_key)


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
    if not enabled():
        logger.info("ONBOARDING выключен: нет TELEGRAM_BOT_TOKEN или ONBOARDING_WALLET_KEY")
        return
    logger.info("ONBOARDING воркер запущен")
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
        await asyncio.sleep(interval_seconds)
