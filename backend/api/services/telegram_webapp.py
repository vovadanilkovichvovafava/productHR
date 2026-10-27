"""Проверка Telegram WebApp initData (авторизация Mini App).

Telegram подписывает данные запуска Mini App HMAC-ом на производном ключе от
токена бота. Схема из документации Telegram:

    secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)
    hash       = HMAC_SHA256(key=secret_key, msg=data_check_string)

где data_check_string — все поля initData кроме `hash`, отсортированные по
имени и склеенные через \\n как "key=value".

Важно: проверка подписи — единственное, что отличает настоящий запуск из
Telegram от подделанного запроса. Поэтому здесь нет «мягких» веток: любая
неудача — отказ.
"""
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl

logger = logging.getLogger("hr-analyzer.telegram-webapp")

# Сколько живёт initData. Telegram не ограничивает, но старый initData —
# признак переигранного запроса, поэтому режем сами.
MAX_AUTH_AGE_SECONDS = 24 * 60 * 60


class InitDataError(Exception):
    """initData не прошёл проверку."""


def parse_and_verify(init_data: str, bot_token: str,
                     max_age: int = MAX_AUTH_AGE_SECONDS) -> Dict[str, Any]:
    """Разбирает и проверяет initData. Возвращает поля, либо бросает InitDataError."""
    if not bot_token:
        raise InitDataError("Бот не настроен на сервере")
    if not init_data:
        raise InitDataError("Пустой initData")

    # strict_parsing=False: Telegram может добавлять новые поля, ронять на них нельзя
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    except ValueError as exc:
        raise InitDataError("Некорректный формат initData") from exc

    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise InitDataError("В initData нет подписи")

    data_check_string = "\n".join(
        f"{k}={pairs[k]}" for k in sorted(pairs)
    )
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    # Сравнение в постоянном времени — иначе подпись можно подобрать по таймингам
    if not hmac.compare_digest(expected, received_hash):
        raise InitDataError("Подпись initData неверна")

    # Свежесть
    auth_date = pairs.get("auth_date")
    if not auth_date or not auth_date.isdigit():
        raise InitDataError("Нет корректного auth_date")
    age = time.time() - int(auth_date)
    if age > max_age:
        raise InitDataError("initData устарел, переоткройте приложение")
    if age < -300:  # часы клиента ушли вперёд больше чем на 5 минут
        raise InitDataError("Некорректный auth_date")

    # user приходит JSON-строкой внутри параметра
    user_raw = pairs.get("user")
    if user_raw:
        try:
            pairs["user"] = json.loads(user_raw)
        except json.JSONDecodeError as exc:
            raise InitDataError("Некорректные данные пользователя") from exc

    return pairs


def extract_telegram_id(parsed: Dict[str, Any]) -> Optional[int]:
    user = parsed.get("user")
    if isinstance(user, dict):
        tg_id = user.get("id")
        if isinstance(tg_id, int):
            return tg_id
    return None
