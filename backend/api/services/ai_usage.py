"""Учёт расхода Claude (21.10.2026).

Владелец: «разбор резюме ест очень много». Посчитать было нечем: ни один вызов
Claude не записывал, сколько токенов ушло и откуда он пришёл, — расход видно
было только итогом в консоли Anthropic. Клиентов в коде два десятка (у каждого
сервиса свой), поэтому учёт ставится в ОДНУ точку — на методы SDK
`messages.create` и `messages.stream` (install() при старте приложения). Новые
вызовы попадают в учёт сами.

На каждый вызов: строка `AI_USAGE` в лог и запись `ai_usage_events` в базу
(лог Saturn живёт до перезапуска контейнера, база — нет): модель, откуда
вызван (файл:функция), токены входа/выхода/кэша, примерная цена, время, ошибка.
Ошибки тоже пишутся — так видно и «кончился баланс».

Цена — примерная, по прайсу на 21.10.2026 (`PRICES`, $ за 1 млн токенов).
Точный счёт — в консоли Anthropic.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("hr-analyzer.ai_usage")

# $ за 1 млн токенов: (вход, выход). Ищется по началу имени модели.
PRICES: Tuple[Tuple[str, float, float], ...] = (
    ("claude-fable-5", 10.0, 50.0),
    ("claude-opus-5-5", 4.0, 20.0),
    ("claude-opus-5", 5.0, 25.0),
    ("claude-opus-4", 5.0, 25.0),
    ("claude-sonnet-5", 2.0, 10.0),
    ("claude-sonnet-4", 3.0, 15.0),
    ("claude-haiku-5-5", 0.10, 0.50),
    ("claude-haiku-4", 1.0, 5.0),
    ("claude-3-5-haiku", 0.8, 4.0),
    ("claude-3-haiku", 0.25, 1.25),
)

# Откуда вызван → подпись по-русски для страницы «Расход ИИ».
CALLER_LABELS: Tuple[Tuple[str, str], ...] = (
    ("services/parser.py:parse_with_ai", "Разбор резюме / вакансии (окно «Загрузка из файла»)"),
    ("services/parser.py:split_vacancy_description", "Разбивка описания вакансии"),
    ("services/documents.py", "Распознавание картинок и сканов (Vision)"),
    ("services/resume_parser.py", "Разбор резюме (массовый, «PDF → Резюме»)"),
    ("services/resume_autopromote.py", "Проверка: не резюме ли загруженный PDF"),
    ("services/call_processor.py", "Созвоны: расшифровка и разбор"),
    ("services/task_trigger.py", "Автозадачи из чатов"),
    ("services/participants.py", "Участники чатов"),
    ("services/evening_report.py", "Вечерний отчёт"),
    ("services/prometheus_review.py", "Практика: ревью"),
    ("services/entity_ai.py", "ИИ в карточке кандидата"),
    ("services/entity_profile.py", "ИИ-профиль кандидата"),
    ("services/entity_memory.py", "Память по кандидату"),
    ("services/red_flags.py", "Красные флаги"),
    ("services/smart_search.py", "Умный поиск"),
    ("services/skills_normalizer.py", "Нормализация навыков"),
    ("services/vacancy_recommender.py", "Рекомендации вакансий"),
    ("services/ai_scoring.py", "Оценка соответствия"),
    ("services/comparison_ai.py", "Сравнение кандидатов"),
    ("services/resume_generator.py", "Генерация резюме"),
    ("services/ai.py", "Чаты: ИИ-анализ"),
    ("routes/forms.py", "Анкеты: ИИ-чат"),
    ("routes/projects/ai_tasks.py", "Проекты: ИИ-задачи"),
    ("bot.py", "Telegram-бот"),
)

_installed = False


def price_of(model: str) -> Optional[Tuple[float, float]]:
    for prefix, inp, out in PRICES:
        if (model or "").startswith(prefix):
            return inp, out
    return None


def estimate_cost(model: str, inp: int, out: int, cache_read: int = 0, cache_write: int = 0) -> Optional[float]:
    """Примерная цена вызова в $: кэш-чтение ~0,1 входа, запись в кэш ~1,25."""
    p = price_of(model)
    if p is None:
        return None
    pin, pout = p
    return round((inp * pin + cache_read * pin * 0.1 + cache_write * pin * 1.25 + out * pout) / 1_000_000, 6)


def label_of(caller: str) -> str:
    for key, label in CALLER_LABELS:
        if key in caller:
            return label
    return caller


def _caller() -> str:
    """Первый кадр из нашего кода (api/…) выше этого модуля: «services/x.py:func»."""
    f = sys._getframe(2)
    while f is not None:
        path = f.f_code.co_filename.replace("\\", "/")
        if "/api/" in path and not path.endswith("ai_usage.py") and "/site-packages/" not in path:
            return f"{path.split('/api/', 1)[1]}:{f.f_code.co_name}"
        f = f.f_back
    return "unknown"


def _usage_fields(usage: Any) -> Dict[str, int]:
    def g(name: str) -> int:
        v = getattr(usage, name, None) if usage is not None else None
        return int(v) if isinstance(v, (int, float)) else 0
    return {
        "input_tokens": g("input_tokens"),
        "output_tokens": g("output_tokens"),
        "cache_read_tokens": g("cache_read_input_tokens"),
        "cache_write_tokens": g("cache_creation_input_tokens"),
    }


def _record(model: str, caller: str, started: float, usage: Any = None, error: Optional[BaseException] = None) -> None:
    fields = _usage_fields(usage)
    cost = estimate_cost(model, fields["input_tokens"], fields["output_tokens"],
                         fields["cache_read_tokens"], fields["cache_write_tokens"])
    duration_ms = int((time.perf_counter() - started) * 1000)
    err = f"{type(error).__name__}: {str(error)[:300]}" if error is not None else None
    logger.info(
        "AI_USAGE model=%s caller=%s in=%s out=%s cache_read=%s cache_write=%s cost=$%s ms=%s%s",
        model, caller, fields["input_tokens"], fields["output_tokens"], fields["cache_read_tokens"],
        fields["cache_write_tokens"], cost if cost is not None else "?", duration_ms,
        f" error={err}" if err else "",
    )
    if os.environ.get("TESTING") == "1" and not os.environ.get("AI_USAGE_DB_IN_TESTS"):
        return
    event = dict(at=datetime.utcnow(), model=(model or "")[:100], caller=caller[:200], cost_usd=cost,
                 duration_ms=duration_ms, ok=error is None, error=err, **fields)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # вызов из потока без цикла событий — только строка в логе
    loop.create_task(_write(event))


async def _write(event: Dict[str, Any]) -> None:
    try:
        from ..database import AsyncSessionLocal
        from ..models.database import AiUsageEvent
        async with AsyncSessionLocal() as db:
            db.add(AiUsageEvent(**event))
            await db.commit()
    except Exception as e:  # noqa: BLE001 — учёт не должен ломать работу
        logger.warning("AI_USAGE write failed: %s", e)


class _AsyncStreamManagerProxy:
    """`async with client.messages.stream(...)` — расход берём из итогового
    сообщения при выходе из блока."""

    def __init__(self, manager, model: str, caller: str, started: float):
        self._manager, self._model, self._caller, self._started = manager, model, caller, started
        self._stream = None

    async def __aenter__(self):
        self._stream = await self._manager.__aenter__()
        return self._stream

    async def __aexit__(self, exc_type, exc, tb):
        try:
            snapshot = getattr(self._stream, "current_message_snapshot", None) if self._stream else None
            _record(self._model, self._caller, self._started,
                    getattr(snapshot, "usage", None), exc if exc_type else None)
        except Exception:  # noqa: BLE001
            pass
        return await self._manager.__aexit__(exc_type, exc, tb)


def install() -> None:
    """Обернуть методы SDK один раз при старте приложения."""
    global _installed
    if _installed:
        return
    try:
        from anthropic.resources.messages import messages as m
    except Exception as e:  # noqa: BLE001
        logger.warning("AI_USAGE: SDK не найден, учёт выключен: %s", e)
        return

    orig_async_create = m.AsyncMessages.create
    orig_sync_create = m.Messages.create
    orig_async_stream = m.AsyncMessages.stream

    async def async_create(self, *args, **kwargs):
        caller, started, model = _caller(), time.perf_counter(), str(kwargs.get("model", ""))
        try:
            response = await orig_async_create(self, *args, **kwargs)
        except BaseException as e:
            _record(model, caller, started, error=e)
            raise
        if kwargs.get("stream"):
            return response  # сырой поток событий: расхода в ответе нет
        _record(getattr(response, "model", None) or model, caller, started, getattr(response, "usage", None))
        return response

    def sync_create(self, *args, **kwargs):
        caller, started, model = _caller(), time.perf_counter(), str(kwargs.get("model", ""))
        try:
            response = orig_sync_create(self, *args, **kwargs)
        except BaseException as e:
            _record(model, caller, started, error=e)
            raise
        if kwargs.get("stream"):
            return response
        _record(getattr(response, "model", None) or model, caller, started, getattr(response, "usage", None))
        return response

    def async_stream(self, *args, **kwargs):
        caller, started, model = _caller(), time.perf_counter(), str(kwargs.get("model", ""))
        return _AsyncStreamManagerProxy(orig_async_stream(self, *args, **kwargs), model, caller, started)

    m.AsyncMessages.create = async_create
    m.Messages.create = sync_create
    m.AsyncMessages.stream = async_stream
    _installed = True
    logger.info("AI_USAGE: учёт вызовов Claude включён")
