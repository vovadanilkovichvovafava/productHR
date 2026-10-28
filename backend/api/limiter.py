"""Rate limiter configuration for the application."""
import os
from slowapi import Limiter
from starlette.requests import Request


# Rate limit configurations
DEFAULT_RATE_LIMIT = "100/minute"
TESTING_RATE_LIMIT = "1000/minute"  # More lenient limit for testing


# Лимиты для адресов без входа (24.10.2026). Публичная анкета кандидата,
# ссылка «Поделиться», приглашения — у них нет пользователя, по которому можно
# считать, поэтому считаем по IP. Значения с запасом для живого человека:
# кандидат с плохим интернетом жмёт «Отправить» несколько раз — это норма.
PUBLIC_PAGE_LIMIT = "60/minute"      # открыть страницу анкеты / карточку по ссылке
PUBLIC_FILE_LIMIT = "120/minute"     # фото и файлы карточки по ссылке «Поделиться»
PUBLIC_SUBMIT_LIMIT = "10/minute"    # отправить анкету
PUBLIC_REPORT_LIMIT = "20/minute"    # отчёт браузера о сбое отправки (пишет только лог)
PUBLIC_TOKEN_LIMIT = "20/minute"     # проверить / принять приглашение

RATE_LIMIT_MESSAGE = "Слишком много запросов подряд. Подождите минуту и попробуйте снова."


def client_ip(request: Request) -> str:
    """Настоящий адрес человека, а не прокси.

    Запрос приходит через nginx фронта и прокси Saturn, поэтому
    `request.client.host` — адрес прокси, ОДИН на всех: до 24.10.2026 лимит
    «20 входов в минуту» был общим на всю компанию (комментарий в auth.py
    списывал это на «общий офисный IP»). Первый адрес X-Forwarded-For — тот,
    что увидел первый прокси, так же адрес берёт `auth._get_client_ip`.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        # Первый адрес присылает сам клиент — его подделывают, чтобы обойти
        # лимит или записать чужой IP под подписью документа. Если известно,
        # сколько адресов справа дописали наши прокси (TRUSTED_PROXY_HOPS),
        # берём адрес перед ними — его клиент подделать не может.
        from .config import settings
        hops = max(0, int(getattr(settings, "trusted_proxy_hops", 0) or 0))
        if hops and len(parts) >= hops:
            return parts[-hops]
        if parts:
            return parts[0]
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def user_or_ip(request: Request) -> str:
    """Ключ «на человека»: номер пользователя из токена входа, иначе адрес.

    slowapi считает ключ ДО вызова ручки, поэтому прежний приём
    `request.state._rate_limit_user = user` внутри ручки не срабатывал никогда:
    ключом всегда оказывался адрес прокси, и лимит «5 разборов резюме в минуту
    на рекрутёра» был одним на всю компанию (найдено 24.10.2026). Токен
    проверяется подписью, без базы — подделать чужой номер нельзя, а
    отозванный токен ручка всё равно отклонит сама.
    """
    from jose import JWTError, jwt
    from .config import get_settings

    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("authorization") or ""
        if auth.startswith("Bearer "):
            token = auth[7:]
    if token:
        settings = get_settings()
        try:
            sub = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]).get("sub")
            if sub:
                return f"user:{sub}"
        except JWTError:
            pass
    return client_ip(request)


def get_key_func():
    """Ключ лимита по умолчанию — адрес человека (см. client_ip)."""
    return client_ip


def get_rate_limit() -> str:
    """Return appropriate rate limit based on environment.

    - DISABLE_RATE_LIMIT=1: Returns None (explicitly disables rate limiting)
    - TESTING=1: Returns lenient limit (1000/minute) for test performance
    - Default: Returns standard limit (100/minute)
    """
    if os.environ.get("DISABLE_RATE_LIMIT") == "1":
        # Explicit opt-out - should only be used in controlled environments
        return None
    if os.environ.get("TESTING") == "1":
        return TESTING_RATE_LIMIT
    return DEFAULT_RATE_LIMIT


def is_rate_limiting_enabled() -> bool:
    """Check if rate limiting is enabled."""
    return os.environ.get("DISABLE_RATE_LIMIT") != "1"


# Create a global limiter instance that can be imported by routes
limiter = Limiter(
    key_func=get_key_func(),
    enabled=is_rate_limiting_enabled(),
    default_limits=[get_rate_limit()] if is_rate_limiting_enabled() else []
)
