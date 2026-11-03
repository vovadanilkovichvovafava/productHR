from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Settings:
    bot_username: str = ""
    wallet_enc_key: str = ""
    default_tz: str = "Europe/Moscow"
    landing_url: str = ""
    wallet_guide_url: str = ""
    platform_invite_url: str = ""
    materials_url: str = ""
    hr_fallback_chat_id: Optional[int] = None
    practice_days: int = 7
    first_retry_count: int = 2
    send_thanks_on_fail: bool = False

    @classmethod
    def from_app(cls, bot_username: str = "") -> "Settings":
        from api.config import settings as app

        return cls(
            bot_username=bot_username or app.telegram_bot_username,
            wallet_enc_key=app.onboarding_wallet_key,
            default_tz=app.onboarding_default_tz,
            landing_url=app.onboarding_landing_url,
            wallet_guide_url=app.onboarding_wallet_guide_url,
            platform_invite_url=app.onboarding_platform_invite_url,
            materials_url=app.onboarding_materials_url,
            hr_fallback_chat_id=app.onboarding_hr_fallback_chat_id or None,
            practice_days=app.onboarding_practice_days,
            send_thanks_on_fail=app.onboarding_send_thanks_on_fail,
        )
