import os
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from functools import lru_cache


class Settings(BaseSettings):
    # Database URL - Railway provides this as DATABASE_URL
    database_url: str = Field(
        default="postgresql://localhost/hr_bot",
        alias="DATABASE_URL"
    )

    # JWT Settings - Railway uses SECRET_KEY
    jwt_secret: str = Field(
        alias="SECRET_KEY"
    )
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # Legacy fallback - actual auth uses ACCESS_TOKEN_EXPIRE_MINUTES (15 min)

    # Telegram Bot Token and Username
    telegram_bot_token: str = Field(
        default="",
        alias="TELEGRAM_BOT_TOKEN"
    )
    # Адрес Telegram Mini App. Telegram требует HTTPS, поэтому локально кнопка
    # просто не показывается — вместо неё остаются обычные команды бота.
    miniapp_url: str = Field(
        default="",
        alias="MINIAPP_URL"
    )
    telegram_bot_username: str = Field(
        default="",
        alias="TELEGRAM_BOT_USERNAME",
        description="Bot username for deep links (e.g., 'my_hr_bot' without @)"
    )

    # AI API Keys
    anthropic_api_key: str = Field(
        default="",
        alias="ANTHROPIC_API_KEY"
    )
    # Separate key for AI form generation (falls back to anthropic_api_key if not set)
    anthropic_api_key_forms: str = Field(
        default="",
        alias="ANTHROPIC_API_KEY_FORMS"
    )
    openai_api_key: str = Field(
        default="",
        alias="OPENAI_API_KEY"
    )

    # Claude model name
    claude_model: str = Field(
        default="claude-sonnet-4-6",
        alias="CLAUDE_MODEL"
    )

    # Redis (optional, for future use)
    redis_url: str = Field(
        default="redis://localhost:6379",
        alias="REDIS_URL"
    )

    # Fireflies.ai API for call recording & transcription
    fireflies_api_key: str = Field(
        default="",
        alias="FIREFLIES_API_KEY"
    )

    # SMTP — исходящая почта кандидатам (B5). Если SMTP_HOST/SMTP_FROM пусты,
    # письмо не отправляется (помечается pending), а не врёт "отправлено".
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from: str = Field(default="", alias="SMTP_FROM")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")

    # Superadmin credentials - MUST be set in Railway Variables
    superadmin_email: str = Field(
        alias="SUPERADMIN_EMAIL"
    )
    superadmin_password: str = Field(
        alias="SUPERADMIN_PASSWORD"
    )

    # Prometheus integration (server-only, for interns data)
    prometheus_base_url: str = Field(
        default="",
        alias="PROMETHEUS_BASE_URL"
    )
    communication_api_key: str = Field(
        default="",
        alias="COMMUNICATION_API_KEY"
    )

    @field_validator("prometheus_base_url")
    @classmethod
    def _ensure_prometheus_scheme(cls, v: str) -> str:
        # Если PROMETHEUS_BASE_URL задан без схемы (напр. "host.example" вместо
        # "https://host.example") — httpx падает «Request URL is missing an
        # 'http://' or 'https://' protocol», и фоновый auto-export практикантов
        # сыпал ERROR каждые 5 мин (прод 2026-08-27). Нормализуем один раз здесь,
        # чтобы все консюмеры prometheus_base_url получали валидный URL.
        v = (v or "").strip()
        if v and not v.startswith(("http://", "https://")):
            v = "https://" + v
        return v

    # Call recordings settings
    upload_dir: str = Field(
        default="/app/uploads/calls",
        alias="UPLOAD_DIR"
    )
    default_bot_name: str = Field(
        default="HR Recorder",
        alias="DEFAULT_BOT_NAME"
    )

    # CORS allowed origins - comma-separated list
    allowed_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        alias="ALLOWED_ORIGINS"
    )

    # Cookie settings
    cookie_secure: bool = Field(
        default=True,
        alias="COOKIE_SECURE"
    )

    # Cache TTL settings (in seconds)
    cache_ttl_default: int = Field(
        default=3600,  # 1 hour
        alias="CACHE_TTL_DEFAULT"
    )
    cache_ttl_scoring: int = Field(
        default=3600,  # 1 hour
        alias="CACHE_TTL_SCORING"
    )

    def get_allowed_origins_list(self) -> list[str]:
        """Parse comma-separated origins into a list.

        SECURITY: Rejects wildcard (*) origins in production to prevent CORS attacks.
        Only specific domains should be allowed in production.
        """
        origins = [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

        # Security check: reject wildcards
        if "*" in origins:
            import logging
            logger = logging.getLogger("hr-analyzer.config")
            logger.warning("SECURITY WARNING: Wildcard (*) CORS origin detected! Removing for security.")
            origins = [o for o in origins if o != "*"]

        # Ensure at least localhost for development if no valid origins
        if not origins:
            return ["http://localhost:3000", "http://localhost:5173"]

        return origins

    class Config:
        env_file = (".env", ".env.local")  # .env.local overrides .env for local dev
        extra = "ignore"
        populate_by_name = True  # Allow both alias and field name

    def validate_required_secrets(self) -> None:
        """Validate that required secrets are set (no default fallback)"""
        if not self.jwt_secret or self.jwt_secret == "":
            raise ValueError("SECRET_KEY environment variable must be set")
        if not self.superadmin_email or self.superadmin_email == "":
            raise ValueError("SUPERADMIN_EMAIL environment variable must be set")
        if not self.superadmin_password or self.superadmin_password == "":
            raise ValueError("SUPERADMIN_PASSWORD environment variable must be set")


# Global settings instance (for bot.py compatibility)
settings = Settings()
# Validate required secrets at startup
settings.validate_required_secrets()


@lru_cache()
def get_settings() -> Settings:
    return settings
