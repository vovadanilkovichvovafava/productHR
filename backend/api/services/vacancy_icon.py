"""Значок вакансии в левой панели — подбирает ИИ (12.11.2026).

Владелец: «я думал, он просто будет под все значки подбирать». Словарь
направлений (frontend/src/utils/vacancyDirection.ts) узнаёт только названия
профессий: «Car», «SuperJet», «Суперкар» получали серую папку. Теперь Haiku
читает название и выбирает одну иконку из ~200 предметных
(`vacancy_icon_names.txt`, тот же список — во фронте, vacancyIcons.ts).

- Значок считается ОДИН раз на название и лежит в вакансии:
  `extra_data.icon` (имя иконки, "" — модель не выбрала ничего из списка) и
  `extra_data.icon_for` (название, под которое он подобран). Сменили название
  — `icon_for` разошёлся, значок пересчитается. Список вакансий модель не
  зовёт, открывается так же быстро.
- Считает фоновый обходчик (`icon_worker`): после создания/переименования его
  будит `kick_icon_worker()`, плюс раз в 5 минут — так ловятся и вакансии из
  других путей (клон заявки, бот). Ошибка API (например, кончился баланс) —
  пауза на час, без долбёжки.
- Цена: ~1,5 тыс. токенов на вход (список кэшируется), десяток на выход —
  сотые доли цента за вакансию. Строка «Значок вакансии» на «Расходе ИИ».
- Ключи `icon`/`icon_for` — серверные (`SERVER_MANAGED_EXTRA`): форма,
  открытая до подбора значка, их не сотрёт.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Awaitable, Callable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models.database import Vacancy, VacancyStatus

logger = logging.getLogger("hr-analyzer.vacancy_icon")
settings = get_settings()

ICON_NAMES: list[str] = [
    line.strip()
    for line in Path(__file__).with_name("vacancy_icon_names.txt").read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.startswith("#")
]
_ICON_SET = frozenset(ICON_NAMES)

_SYSTEM = (
    "Ты подбираешь иконку к названию вакансии для списка вакансий в HR-системе. "
    "Выбери ОДНО имя иконки из списка — то, что лучше всего передаёт смысл названия: "
    "профессию, предмет, тему или бренд. Если название — просто слово или имя "
    "собственное (например, «SuperJet», «Машина»), бери иконку его смысла "
    "(самолёт, машина). Ответь только именем иконки из списка, без пояснений.\n\n"
    "Список иконок:\n" + ", ".join(ICON_NAMES)
)

_NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

Picker = Callable[[str, Optional[str]], Awaitable[Optional[str]]]


def parse_icon_answer(text: str) -> Optional[str]:
    """Первое имя из списка в ответе модели; ничего подходящего — None."""
    for token in _NAME_RE.findall((text or "").lower()):
        if token in _ICON_SET:
            return token
    return None


async def pick_icon(title: str, department: Optional[str] = None) -> Optional[str]:
    """Спросить модель. Ошибка API — исключение (обходчик уйдёт на паузу)."""
    from anthropic import AsyncAnthropic

    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
    client = AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=30, max_retries=1)
    model = settings.vacancy_icon_model
    kwargs = {}
    if model.startswith("claude-haiku-5"):
        # Думать тут не о чем — низкое усилие (SDK 0.76 не знает output_config).
        kwargs["extra_body"] = {"output_config": {"effort": "low"}}
    user_text = f"Вакансия: {title.strip()}"
    if department and str(department).strip():
        user_text += f"\nОтдел: {str(department).strip()}"
    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        system=[{"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_text}],
        **kwargs,
    )
    if response.stop_reason == "refusal":
        return None
    text = "".join(
        b.text for b in response.content
        if getattr(b, "type", None) not in ("thinking", "redacted_thinking")
        and isinstance(getattr(b, "text", None), str)
    )
    return parse_icon_answer(text)


def needs_icon(v: Vacancy) -> bool:
    return (v.extra_data or {}).get("icon_for") != v.title


async def apply_icons(db: AsyncSession, picker: Picker, limit: int = 20) -> int:
    """Подобрать значки вакансиям, у которых их нет или название сменилось.
    Ошибка picker'а пробрасывается — следующий раз продолжим с того же места."""
    candidates = (await db.execute(
        select(Vacancy)
        .where(Vacancy.deleted_at.is_(None), Vacancy.status != VacancyStatus.closed)
        .order_by(Vacancy.id.desc())
        .limit(1000)
    )).scalars().all()
    todo = [v.id for v in candidates if needs_icon(v)][:limit]
    done = 0
    for vid in todo:
        vacancy = await db.get(Vacancy, vid)
        if vacancy is None or not needs_icon(vacancy):
            continue
        title = vacancy.title
        icon = await picker(title, (vacancy.extra_data or {}).get("department"))
        # Перечитать под замком: пока модель думала, вакансию могли сохранить.
        fresh = (await db.execute(
            select(Vacancy).where(Vacancy.id == vid).with_for_update().execution_options(populate_existing=True)
        )).scalar_one_or_none()
        if fresh is None or fresh.title != title:
            await db.rollback()
            continue
        fresh.extra_data = {**(fresh.extra_data or {}), "icon": icon or "", "icon_for": title}
        await db.commit()
        done += 1
        logger.info("VACANCY_ICON: vacancy=%s icon=%s", vid, icon or "-")
    return done


_wake = asyncio.Event()


def kick_icon_worker() -> None:
    """Разбудить обходчик сразу (после создания или переименования вакансии)."""
    _wake.set()


async def icon_worker() -> None:
    if os.getenv("TESTING"):
        return
    from ..database import AsyncSessionLocal

    await asyncio.sleep(20)
    while True:
        delay = 300
        try:
            async with AsyncSessionLocal() as db:
                await apply_icons(db, pick_icon)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning("VACANCY_ICON paused for 1h: %s: %s", type(e).__name__, str(e)[:200])
            delay = 3600
        _wake.clear()
        try:
            await asyncio.wait_for(_wake.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass
