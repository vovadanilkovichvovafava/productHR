"""
Auto-creates project tasks from Telegram chat messages.
Triggers on planning-related keywords and uses Claude AI to parse.
Also detects status reports and updates project progress.
"""
import re
import os
import logging
import json
import difflib
from typing import Optional
from datetime import datetime

# Кириллица → латиница для матчинга проекта в блокерах/тасках.
# «Saturn» в БД должен матчиться на «Сатурн» и наоборот.
_CYR_TO_LAT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
}
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("hr-analyzer.task_trigger")

# Trigger words (Russian)
# ── Модальные слова (intent) ──────────────────────────────────────
_MODALS = [
    r'надо', r'нужно', r'необходимо', r'требуется', r'следует',
    r'нужн[аоы]',                          # нужна/нужно/нужны
    r'должн?[аеоы]?',                      # должен/должна/должно/должны
    r'обязан[аоы]?',                        # обязан/обязана
    r'стоит',                               # "стоит проверить"
    r'пора',                                # "пора делать"
    r'важно',                               # "важно сделать"
    r'хочу', r'хочет', r'хотим',
    r'буду', r'будет', r'будем', r'будут',
    r'планиру[юет]',                        # планирую/планирует
    r'собираюсь', r'собирается',
    r'предлагаю',
    r'попрошу', r'прошу', r'просьба',
    r'поручаю', r'поручи',
    r'давай', r'давайте',  # + "давайте добавим" через самостоятельные глаголы ниже
    r'начн[уиёе]',                          # начну/начни/начнём/начнёт
]

# ── Глаголы действия ─────────────────────────────────────────────
_ACTIONS = [
    r'сделать', r'делать', r'доделать',
    r'провести', r'проводить',
    r'проверить', r'проверять',
    r'написать', r'писать', r'дописать', r'переписать',
    r'настроить', r'настраивать', r'перенастроить',
    r'подготовить', r'готовить',
    r'исправить', r'исправлять', r'починить', r'пофиксить', r'фиксить',
    r'обновить', r'обновлять',
    r'добавить', r'добавлять',
    r'удалить', r'убрать',
    r'создать', r'создавать',
    r'реализовать', r'имплементировать', r'заимплементить',
    r'протестировать', r'протестить', r'тестировать', r'потестить', r'стестить',
    r'откалибровать', r'калибровать', r'перекалибровать',
    r'замерить', r'измерить', r'измерять',
    r'собрать', r'пересобрать', r'разобрать',
    r'снять', r'снимать',
    r'загрузить', r'загружать', r'выгрузить', r'выгружать',
    r'задеплоить', r'деплоить', r'выкатить', r'выкатывать',
    r'отрефакторить', r'рефакторить', r'рефакторинг',
    r'оптимизировать',
    r'интегрировать',
    r'мигрировать', r'мигрировать',
    r'разработать', r'разрабатывать',
    r'запустить', r'запускать',
    r'завершить', r'закончить',
    r'ревьюить', r'отревьюить',
    r'замержить', r'мержить',
    r'закоммитить', r'коммитить', r'запушить',
    r'поднять', r'развернуть',
    r'перевести', r'переводить',             # "перевести на новый API"
    r'переделать', r'переработать',
    r'внедрить', r'внедрять',
    r'подключить', r'подключать',
    r'документировать', r'задокументировать',
    r'согласовать',
    r'спроектировать', r'проектировать',
    r'автоматизировать',
    r'продвинуть(?:ся)?', r'продвинутся',  # "продвинуться в генерации"
    r'выпустить', r'выпускать',             # "выпустить в пользование"
    r'улучшить', r'улучшать', r'улучшить',
    r'развить', r'развивать',
    r'закрыть',                              # "закрыть таску"
    r'доработать', r'дорабатывать',
]

# Комбинаторные паттерны: модальное_слово .* действие
_MODAL_ACTION_PATTERNS = [
    rf'{modal}.*{action}'
    for modal in _MODALS
    for action in _ACTIONS
]

# Строка-задача без модального слова: «1. Проверить качество поиска по API»,
# «- Добавить фильтр», «Проверить прод». Раньше такие сообщения не проходили
# даже предварительный отбор: глаголы в неопределённой форме учитывались только
# в связке «надо … проверить», а список из ОДНОГО пункта за список не считался
# (жалоба владельца 28.09.2026 — сообщение по ZavodCamp бот пропустил).
_LIST_MARK = r'(?:\d+[.)]|[-–—•*])\s*'
_ACTION_LINE_PATTERNS = [
    rf'^\s*(?:{_LIST_MARK})?{action}\b'
    for action in _ACTIONS
]

TRIGGER_PATTERNS = [
    # Пункт списка — сам по себе заявка на задачу; в том числе в одну строку
    # после названия проекта: «Saturn: 1. Поднять сервер»
    rf'^\s*{_LIST_MARK}\S',
    rf':\s*{_LIST_MARK}\S',
    *_ACTION_LINE_PATTERNS,

    # ── Прямая постановка задачи ──────────────────────────────────
    r'задач[уаие]',                         # задача, задачу, задачи, задаче
    r'ставлю задач', r'поставь задач',
    r'создай задач', r'создать задач',
    r'новая задач', r'новый таск',
    r'таск[:\s]', r'тикет[:\s]',
    r'todo[:\s]',

    # ── Самостоятельные глаголы (1-е лицо, без модального) ─────────
    r'сделаю',  r'доделаю', r'переделаю',
    r'займусь', r'возьмусь',
    r'пофикш', r'починю', r'исправлю',
    r'напишу', r'допишу', r'перепишу',
    r'проверю', r'протестирую', r'потестирую',
    r'настрою', r'перенастрою',
    r'обновлю', r'добавлю', r'уберу', r'удалю',
    r'создам', r'реализую',
    r'задеплою', r'выкачу',
    r'отрефакторю',
    r'оптимизирую',
    r'интегрирую',
    r'запущу', r'подниму', r'разверну',
    r'подготовлю',
    r'закончу', r'завершу', r'доработаю',
    r'замержу', r'запушу', r'закоммичу',
    r'отревьюю',
    r'подключу',
    r'внедрю',
    r'спроектирую',
    r'продвинусь', r'продвинемся',
    r'улучшу', r'улучшим',
    r'выпущу', r'выпустим',
    r'закрою', r'закроем',
    r'доработаю', r'доработаем',
    # Формы "мы" (1-е лицо мн.ч.)
    r'добавим', r'сделаем', r'проверим', r'напишем', r'создадим',
    r'настроим', r'обновим', r'исправим', r'запустим', r'завершим',
    r'подготовим', r'протестируем', r'задеплоим', r'отрефакторим',
    r'интегрируем', r'оптимизируем', r'внедрим', r'переделаем',

    # ── Планирование ──────────────────────────────────────────────
    r'план на', r'по плану', r'планы', r'в планах', r'планы на',
    r'начну делать', r'начну работать',
    r'начинаю работать', r'начинаю делать',
    r'приступаю', r'приступлю',
    r'сегодня:', r'сегодня буду', r'сегодня планирую',
    r'сегодня надо', r'сегодня нужно',
    r'сегодня в планах', r'сегодня хочу',
    r'продолжаю работу', r'продолжаю работать',
    r'продолжаю развивать', r'продолжаю делать',
    r'с утра', r'утром буду',
    r'утренний план',
    r'доброе утро.*план', r'доброе утро.*работ',
    r'good morning', r'гуд морнинг',

    # ── Нумерованные/маркированные списки (стендап-паттерн) ─────────
    r'1[\.\)]\s*.+\n\s*2[\.\)]',               # "1. ... \n 2. ..." — numbered list
    r'[-•]\s*.+\n\s*[-•]\s',                    # "- ...\n- ..." — bullet list

    # ── План на день ─────────────────────────────────────────────────
    r'план на день',                            # "План на день для FB Analitic"
    r'план работ',
    r'тестирование\s', r'исправление\s',       # noun forms of actions
    r'разработка\s', r'настройка\s', r'интеграция\s',
    r'рефакторинг\s', r'оптимизация\s',

    # ── Английские триггеры ───────────────────────────────────────
    r'i will', r"i'll",
    r'need to', r'have to', r'got to', r'gotta',
    r'going to', r'gonna',
    r'should', r'must',
    r'let me', r"let's",
    r'working on', r'work on',
    r'implement', r'deploy', r'fix', r'refactor',

    # ── Комбинаторные: модальное + действие ───────────────────────
    *_MODAL_ACTION_PATTERNS,
]

TRIGGER_REGEX = re.compile('|'.join(TRIGGER_PATTERNS), re.IGNORECASE | re.MULTILINE)

# ── Блокеры: явно сигнализируют о срочной задаче разработчику ──────
BLOCKER_REGEX = re.compile(r'\bблокер\w*|\bblock(?:er|ing)?\b|\bне\s+работает\b|\bсломал\w*\b|\bпадает\b|\bкрит(?:ично|ичный)?\b', re.IGNORECASE)


def is_blocker(text: str) -> bool:
    """Сообщение упоминает блокер/критическую проблему."""
    return bool(BLOCKER_REGEX.search(text))

# ── Негативные паттерны: НЕ создавать задачу ────────────────────────
# Прошедшее время, вопросы, предположения — не являются постановкой задач
_NEGATIVE_PATTERNS = [
    r'должн\w*\s+был[аоиь]?\b',    # "должны были", "должен был" — past tense
    r'надо\s+было\b',               # "надо было сделать" — past tense
    r'нужно\s+было\b',              # "нужно было" — past tense
    r'следовало\b',                  # "следовало бы"
    r'стоило\b',                     # "стоило бы"
    r'\bмб\b',                       # "мб сделать" — speculation (может быть)
    r'может\s+быть',                 # "может быть сделать"
    r'может\s+стоит',               # "может стоит"
    r'а\s+что\s+если',              # "а что если сделать"
    r'что\s+если\b',                # "что если"
    r'не\s+кажется\s+ли',           # rhetorical
    r'интересно\s*,?\s*(?:а\s+)?(?:можно|стоит|надо)',  # "интересно, а можно..."
]
NEGATIVE_REGEX = re.compile('|'.join(_NEGATIVE_PATTERNS), re.IGNORECASE)

# ── Отчёт о работе, а не постановка задачи ─────────────────────────
# Самые частые промахи на проде (выгрузка 3600 сообщений из RND-чатов,
# 25.09.2026): «продолжаю работу», «отчет за сегодня», «вчера сделал».
# «Отчёт за …» — отчёт любой длины. А «продолжаю работу» часто идёт просто
# приветствием, после которого следует план дня («продолжаю работу. По
# планам: 1. Доделать кнопку…») — поэтому такие режем только в КОРОТКИХ
# сообщениях, где кроме этой фразы ничего нет.
_REPORT_ANY_LEN = re.compile(r'^\s*отч[её]т\s+за\b|напишу\s+отч[её]т', re.IGNORECASE)
_REPORT_PHRASE = re.compile(
    r'продолжаю\s+работ(?:у|ать)(?:\s+над\s+\w+)?'
    r'|^\s*(?:вчера|сегодня)\s+(?:сделал|доделал|закончил|завершил|починил|залил|выкатил)'
    r'|^\s*(?:готово|сделано|залил|выкатил|задеплоил)\b',
    re.IGNORECASE,
)
_GREETING = re.compile(
    r'^\s*(?:доброе утро|добрый день|добрый вечер|доброго времени|привет(?:ы|ики)?(?: всем)?|хай(?:юшки)?|здравствуйте|так,? если что|пока|всем привет)[\s,!)(-]*',
    re.IGNORECASE,
)
# Сколько «своего» текста должно остаться после приветствия и дежурной фразы,
# чтобы считать сообщение планом, а не докладом о ходе дел.
REPORT_REST_MAX = 40


def is_work_report(text: str) -> bool:
    """Сообщение рассказывает о ходе работы, а не ставит задачу.

    «Продолжаю работу» — чаще всего дежурная фраза: у одних это всё сообщение
    (доклад), у других — приветствие перед планом дня («продолжаю работу. По
    планам: 1. Доделать кнопку…»). Поэтому смотрим, что осталось в сообщении
    после приветствия и самой фразы: почти ничего — доклад, есть содержание —
    отдаём модели.
    """
    t = text.strip()
    if _REPORT_ANY_LEN.search(t):
        return True
    if not _REPORT_PHRASE.search(t):
        return False
    rest = _REPORT_PHRASE.sub(' ', _GREETING.sub('', t))
    rest = re.sub(r'[\s,.!)(–—-]+', ' ', rest).strip()
    return len(rest) <= REPORT_REST_MAX


# Короткие реплики в диалоге («принял, ща займусь», «да, сейчас переделаю»)
# задачами не считаем: это ответ собеседнику, а не план работ.
_CHATTER_PREFIX = re.compile(
    r'^\s*(?:да|нет|ок|окей|хорошо|принял|понял|ага|угу|спасибо|щас|ща|сейчас)\b',
    re.IGNORECASE,
)
CHATTER_MAX_LEN = 60


def is_chatter(text: str) -> bool:
    """Короткая реплика в диалоге — не постановка задачи."""
    t = text.strip()
    return len(t) <= CHATTER_MAX_LEN and bool(_CHATTER_PREFIX.match(t))


def _is_question(text: str) -> bool:
    """Check if message is a question (ends with ? or starts with question words)."""
    stripped = text.strip()
    if stripped.endswith('?'):
        return True
    # Question words at start of sentence
    if re.match(r'^(а |как |зачем |почему |можно ли |нет ли |разве )', stripped, re.IGNORECASE):
        return True
    return False


def should_trigger(text: str) -> bool:
    """Check if message contains trigger words (fast regex pre-filter)."""
    if not TRIGGER_REGEX.search(text):
        return False
    # Reject if negative patterns match (past tense, speculation, questions)
    if NEGATIVE_REGEX.search(text):
        logger.debug(f"🚫 Negative pattern matched, skipping: {text[:80]}...")
        return False
    # Reject short questions — they are discussions, not task assignments
    if _is_question(text) and len(text.strip()) < 120:
        logger.debug(f"🚫 Short question rejected: {text[:80]}...")
        return False
    return True


# Порог уверенности модели: ниже — не беспокоим чат.
AI_CONFIDENCE_MIN = 0.7

_AI_DECIDE_PROMPT = """Ты разбираешь сообщения из рабочего чата разработчиков.

Реши, ставит ли автор КОНКРЕТНУЮ задачу или описывает план работ, который
имеет смысл завести в трекер.

НЕ задача:
- отчёт о сделанном: «вчера доделал», «отчёт за сегодня», «продолжаю работу»
- короткая реплика в диалоге: «принял, ща займусь», «да, сейчас переделаю»
- обсуждение, оценка, размышление: «надо наверное развернуть ещё сервак»,
  «может уже микро тест запустим», «и ещё мало людей будут писать текстом»
- анализ, сравнение, пересказ («конкуренты и их минусы: 1… 2…»)
- вопрос или предложение обсудить

Задача:
- «сегодня по плану разобраться, почему адс павер умирает, плюс пофиксить размер картинок»
- «Сегодня займусь двумя вещами: умной буферизацией сообщений и …»
- «Твоя задача пинговать этого баера»
- «Нужно переписать браузер для обхода клоаки»

Ответь ТОЛЬКО JSON: {"is_task": true|false, "confidence": 0.0-1.0, "reason": "коротко"}

Сообщение:
"""


async def ai_decide(text: str) -> dict:
    """Спросить модель, есть ли в сообщении задача. Возвращает решение и причину."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"is_task": None, "confidence": 0.0, "reason": "no api key"}
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=120,
            messages=[{"role": "user", "content": _AI_DECIDE_PROMPT + text}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw.strip())
        return {
            "is_task": bool(data.get("is_task")),
            "confidence": float(data.get("confidence") or 0),
            "reason": str(data.get("reason") or "")[:200],
        }
    except Exception as e:
        logger.error(f"AI decide failed: {e}")
        return {"is_task": None, "confidence": 0.0, "reason": f"error: {e}"}


async def should_trigger_ai(text: str) -> bool:
    """Есть ли в сообщении задача.

    Раньше решала регулярка: совпало — задача, модель даже не спрашивалась.
    Регулярка же ловит любые «надо … проверить», «сегодня:», списки «1. 2.» —
    на проде срабатывала на 14% ВСЕХ сообщений рабочих чатов, из-за чего
    трекер зарастал мусором. Теперь регулярка — только дешёвый предварительный
    отбор, а решает модель (владелец, 25.09.2026).
    """
    stripped = text.strip()
    if len(stripped) < 10:
        return False
    if is_work_report(stripped):
        logger.info(f"🚫 Отчёт о работе, не задача: {stripped[:60]}...")
        return False
    if is_chatter(stripped):
        logger.info(f"🚫 Короткая реплика, не задача: {stripped[:60]}...")
        return False
    if NEGATIVE_REGEX.search(stripped):
        logger.info(f"🚫 Прошедшее время/предположение: {stripped[:60]}...")
        return False
    if _is_question(stripped) and len(stripped) < 120:
        logger.info(f"🚫 Короткий вопрос: {stripped[:60]}...")
        return False

    # Предварительный отбор: без единого признака задачи модель не зовём
    if not TRIGGER_REGEX.search(stripped) and not BLOCKER_REGEX.search(stripped):
        return False

    decision = await ai_decide(stripped)
    if decision["is_task"] is None:
        # Модель недоступна — старое поведение регулярки, но об этом видно в логах
        logger.warning("⚠️ Модель недоступна, решает регулярка")
        return bool(TRIGGER_REGEX.search(stripped))

    ok = decision["is_task"] and decision["confidence"] >= AI_CONFIDENCE_MIN
    logger.info(
        f"🤖 Решение модели: is_task={decision['is_task']} "
        f"conf={decision['confidence']:.2f} ({decision['reason']}) → {ok}"
    )
    return ok


def _extract_project_hint(text: str) -> Optional[str]:
    """Try to extract a project name from the message.

    Heuristics:
    - First line if it's short (< 40 chars) and not a sentence (likely a project title)
    - Text after "на проекте", "проект:", "для" etc.
    """
    lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
    if not lines:
        return None

    # Check first line — if short and not a numbered item, treat as project name
    first = lines[0]
    if len(first) < 50 and not re.match(r'^\d+[\.\)]', first) and not re.search(r'(план|сегодня|доброе|привет)', first, re.IGNORECASE):
        # If first line is short and second line looks like a list, first line is project name
        if len(lines) > 1 and re.match(r'^(\d+[\.\)]|[-•])', lines[1]):
            return first

    # Look for "на проекте X", "проект: X", "для X -", "План на день для X"
    patterns = [
        r'(?:на проекте|по проекту|проект[:\s])\s*[«"]?([A-Za-zА-Яа-яёЁ0-9_ -]+)',
        r'для\s+([A-Za-zА-Яа-яёЁ0-9_ ]+?)(?:\s*[-–—:]|\s+тестирование|\s+разработка|\s+исправление)',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            if len(name) > 2 and len(name) < 60:
                return name

    return None


# ---------------------------------------------------------------------------
# Status report detection & parsing
# ---------------------------------------------------------------------------

STATUS_PATTERNS = [
    r'статус.*проект',           # "статус по проектам"
    r'готовность\s*\d+',         # "готовность 90%"
    r'статус[:\s]',              # "статус:"
    r'\d+%\s*(готов|готовность)', # "90% готово"
    r'статус.?отч[её]т',        # "статус-отчёт" / "статус отчет"
    r'status\s*report',
]
STATUS_REGEX = re.compile('|'.join(STATUS_PATTERNS), re.IGNORECASE)


def is_status_report(text: str) -> bool:
    """Check if message is a status report (not a task).

    A status report typically lists several projects with progress percentages
    or completion markers. We require the pattern match plus at least one
    line that looks like a project-progress entry (contains ``%`` or a
    completion keyword).
    """
    if not STATUS_REGEX.search(text):
        return False
    # Extra heuristic: message should contain at least one percentage or
    # a completion keyword on a separate line to avoid false positives.
    pct_or_done = re.compile(r'\d+\s*%|завершён|завершен|done|готов[оа]?\b', re.IGNORECASE)
    return bool(pct_or_done.search(text))


async def parse_status_report(text: str) -> list[dict]:
    """Use Claude AI to extract project names and progress from a status report."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set, cannot parse status report")
        return []

    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed, cannot parse status report")
        return []

    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)

        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[{"role": "user", "content": f"""Разбери статус-отчёт по проектам. Извлеки название проекта и процент готовности.

ТЕКСТ:
{text}

Для каждого проекта верни JSON:
{{
  "project_name": "название проекта",
  "progress_percent": число 0-100 (если указан диапазон — среднее),
  "status_text": "текст статуса если есть" или null,
  "is_completed": true/false (если написано "завершён/готов/done")
}}

Верни ТОЛЬКО JSON массив, без markdown."""}],
        )

        ai_text = response.content[0].text.strip()
        if ai_text.startswith("```"):
            ai_text = ai_text.split("```")[1]
            if ai_text.startswith("json"):
                ai_text = ai_text[4:]
            ai_text = ai_text.strip()

        return json.loads(ai_text)
    except Exception as e:
        logger.error(f"AI status report parse error: {e}")
        return []


async def update_projects_from_status(
    db: AsyncSession,
    message_text: str,
    user_name: str,
    telegram_user_id: Optional[int],
    chat_id: Optional[int] = None,
) -> list[dict]:
    """Parse status report and update project progress in the database.

    Returns a list of dicts describing which projects were updated, or an
    empty list if the message is not a status report or nothing matched.
    """
    from ..models.database import Project, User, OrgMember, Chat

    if not is_status_report(message_text):
        return []

    logger.info(f"Status report detected from {user_name}")

    # Find user by telegram_id
    user = None
    if telegram_user_id:
        result = await db.execute(select(User).where(User.telegram_id == telegram_user_id))
        user = result.scalar_one_or_none()

    if not user and user_name:
        result = await db.execute(select(User).where(User.name.ilike(f"%{user_name}%")))
        user = result.scalar_one_or_none()

    # Find org — from user or from chat
    org_id = None
    if user:
        org_result = await db.execute(select(OrgMember.org_id).where(OrgMember.user_id == user.id).limit(1))
        org_id = org_result.scalar_one_or_none()

    # Fallback: get org from the chat
    if not org_id and chat_id:
        chat_result = await db.execute(select(Chat).where(Chat.telegram_chat_id == chat_id))
        chat_obj = chat_result.scalar_one_or_none()
        if chat_obj and chat_obj.org_id:
            org_id = chat_obj.org_id

    if not org_id:
        logger.warning(f"Status report: no org found for {user_name} (tg_id={telegram_user_id})")
        return []

    # Get all projects in the organisation
    projects_result = await db.execute(
        select(Project).where(Project.org_id == org_id)
    )
    all_projects = list(projects_result.scalars().all())

    if not all_projects:
        logger.warning(f"Status report: no projects in org for user {user_name}")
        return []

    # Parse status report with AI
    parsed = await parse_status_report(message_text)
    if not parsed:
        return []

    updated: list[dict] = []
    for item in parsed:
        project_name = item.get("project_name", "")
        progress = item.get("progress_percent")
        is_completed = item.get("is_completed", False)

        # Fuzzy match: substring in either direction
        matched_project = None
        for p in all_projects:
            if project_name.lower() in p.name.lower() or p.name.lower() in project_name.lower():
                matched_project = p
                break

        if not matched_project:
            logger.debug(f"Status report: no project matched for '{project_name}'")
            continue

        # Update progress
        if progress is not None:
            matched_project.progress_percent = int(progress)
            matched_project.progress_mode = "manual"

        if is_completed:
            matched_project.status = "completed"
            matched_project.progress_percent = 100
            matched_project.completed_at = datetime.utcnow()

        updated.append({
            "project_name": matched_project.name,
            "progress": matched_project.progress_percent,
            "status": "completed" if is_completed else (
                matched_project.status if isinstance(matched_project.status, str)
                else matched_project.status.value
            ),
        })

    if updated:
        await db.commit()
        logger.info(f"Updated {len(updated)} projects from status report by {user_name}")

    return updated


# Порог схожести заголовков: 0.82 ловит «Очистить кеш Cloudflare для домена X»
# против «Очистить кэш Cloudflare домена X», но не склеивает разные задачи.
TITLE_SIMILARITY_MIN = 0.82


def _norm_title(t: str) -> str:
    t = (t or "").lower().replace("ё", "е")
    return re.sub(r'[^a-zа-я0-9 ]+', ' ', t).strip()


def _find_similar_title(title: str, existing: list[str]) -> Optional[str]:
    """Вернуть похожий заголовок из уже открытых задач проекта."""
    a = _norm_title(title)
    if not a:
        return None
    for e in existing:
        b = _norm_title(e)
        if not b:
            continue
        if a == b or difflib.SequenceMatcher(None, a, b).ratio() >= TITLE_SIMILARITY_MIN:
            return e
    return None


async def parse_message_to_tasks(text: str, user_name: str, existing_tasks: list[dict]) -> list[dict]:
    """Use Claude AI to parse a chat message into structured tasks."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set, cannot parse tasks")
        return []

    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed, cannot parse tasks")
        return []

    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)

        existing_str = "\n".join(
            [f"- {t['title']} (status: {t['status']})" for t in existing_tasks[:20]]
        ) or "Нет задач"

        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[{"role": "user", "content": f"""Разбери сообщение из рабочего чата на отдельные задачи.

СООБЩЕНИЕ от {user_name}:
{text}

СУЩЕСТВУЮЩИЕ ЗАДАЧИ В ПРОЕКТЕ:
{existing_str}

Для каждой задачи из сообщения верни JSON объект:
{{
  "title": "Краткое название задачи",
  "description": "Детальное описание из контекста сообщения",
  "priority": 0-3 (0=низкий, 1=нормальный, 2=высокий, 3=критический),
  "estimated_hours": число или null,
  "is_duplicate": true/false (есть ли похожая в существующих),
  "assignee_name": "имя человека если указано в тексте, ОБЯЗАТЕЛЬНО В ИМЕНИТЕЛЬНОМ ПАДЕЖЕ (например 'Диме нужно' → 'Дима', 'для Миши' → 'Миша', 'на Клима' → 'Клим')" или null,
  "project_hint": "название проекта если указано (например 'по проекту Platform')" или null,
  "deadline_hint": "когда дедлайн если указано (сегодня/завтра/дата)" или "сегодня"
}}

Правила:
- Извлекай ТОЛЬКО рабочие задачи, связанные с разработкой/проектами/работой
- ИГНОРИРУЙ бытовые дела (помыть посуду, сходить в магазин, приготовить обед, погулять и т.д.)
- ИГНОРИРУЙ шутки, мемы, разговоры не по работе
- Если в тексте нет ни одной рабочей задачи — верни пустой массив []
- Если написано "задача:" или "ставлю задачу" — это прямая постановка, приоритет выше (2)
- Если указан конкретный человек — он assignee (имя в именительном падеже!), иначе автор сообщения
- "Диме надо сделать X" → assignee = "Дима", а НЕ автор сообщения
- Если указан проект — запомни его в project_hint
- Дедлайн по умолчанию — сегодня, если не указано иное

Верни ТОЛЬКО JSON массив, без markdown. Если нет рабочих задач — верни []."""}],
        )

        ai_text = response.content[0].text.strip()
        if ai_text.startswith("```"):
            ai_text = ai_text.split("```")[1]
            if ai_text.startswith("json"):
                ai_text = ai_text[4:]
            ai_text = ai_text.strip()

        return json.loads(ai_text)
    except Exception as e:
        logger.error(f"AI parse error: {e}")
        return []


async def create_tasks_from_message(
    db: AsyncSession,
    message_text: str,
    user_name: str,
    telegram_user_id: Optional[int],
    chat_id: Optional[int],
    telegram_username: Optional[str] = None,
    blocker_id: Optional[int] = None,
    dry_run: bool = False,
) -> list[dict]:
    """Разбор сообщения → задачи.

    dry_run=True возвращает РАЗБОР, ничего не создавая: бот показывает его в
    чате с кнопкой «Создать» (владелец, 25.09.2026). Создание — потом, через
    create_tasks_from_preview.
    """
    from ..models.database import (
        Project, ProjectTask, ProjectMember, ProjectStatus, ProjectRole, User, Chat, OrgMember,
    )

    blocker_mode = is_blocker(message_text)
    # Раньше слова «не работает / падает / сломал» создавали задачи в обход
    # любой проверки — в рабочем чате это самые частые слова. Теперь блокер
    # только повышает приоритет, а решение всё равно за моделью.
    is_task = await should_trigger_ai(message_text)
    if not is_task:
        logger.info(f"⏭️ No trigger (regex+AI) for {user_name}: {message_text[:80]}...")
        return []
    if blocker_mode:
        logger.info(f"🚨 Blocker detected from {user_name}: {message_text[:80]}...")

    logger.info(f"✅ Task trigger activated for {user_name}: {message_text[:100]}...")

    # Find user by telegram_id, then telegram_username, then name
    user = None
    if telegram_user_id:
        result = await db.execute(
            select(User).where(User.telegram_id == telegram_user_id)
        )
        user = result.scalar_one_or_none()

        # If not found by telegram_id, auto-bind for future lookups
        if not user and telegram_username:
            result = await db.execute(
                select(User).where(func.lower(User.telegram_username) == telegram_username.lower())
            )
            user = result.scalar_one_or_none()
            if user and not user.telegram_id:
                user.telegram_id = telegram_user_id
                await db.flush()
                logger.info(f"Auto-bound telegram_id {telegram_user_id} to user {user.name}")

    if not user and user_name:
        result = await db.execute(
            select(User).where(User.name.ilike(f"%{user_name}%"))
        )
        user = result.scalar_one_or_none()

    # Find org — either from user or from the chat
    org_id = None
    if user:
        org_result = await db.execute(
            select(OrgMember.org_id).where(OrgMember.user_id == user.id).limit(1)
        )
        org_id = org_result.scalar_one_or_none()

    # If user not found or user has no org — try to get org from the chat
    if not org_id and chat_id:
        chat_result = await db.execute(
            select(Chat).where(Chat.telegram_chat_id == chat_id)
        )
        chat_obj = chat_result.scalar_one_or_none()
        if chat_obj and chat_obj.org_id:
            org_id = chat_obj.org_id
            # Also try to find a fallback user (chat owner) for created_by
            if not user and chat_obj.owner_id:
                owner_result = await db.execute(
                    select(User).where(User.id == chat_obj.owner_id)
                )
                user = owner_result.scalar_one_or_none()
                if user:
                    logger.info(f"Using chat owner {user.name} as fallback for unregistered sender {user_name}")

    # If user still not found, try to find ANY user in the org as creator fallback
    if not user and org_id:
        from ..models.database import Organization
        # Use the first superadmin or admin as fallback creator
        fallback_result = await db.execute(
            select(User)
            .join(OrgMember, OrgMember.user_id == User.id)
            .where(OrgMember.org_id == org_id)
            .where(User.role.in_(["superadmin", "admin"]))
            .limit(1)
        )
        user = fallback_result.scalar_one_or_none()
        if user:
            logger.info(f"Using org admin {user.name} as fallback creator for unregistered sender {user_name}")

    if not user:
        logger.warning(f"❌ User not found and no fallback: {user_name} (tg_id={telegram_user_id}, tg_username={telegram_username})")
        return []

    logger.info(f"👤 User resolved: {user.name} (id={user.id}) for sender {user_name}")

    if not org_id:
        logger.warning(f"❌ No organization found for user {user_name}")
        return []

    logger.info(f"🏢 Org resolved: org_id={org_id}")

    # Get ALL org projects (we only create tasks if message mentions one of them by name)
    all_projects_result = await db.execute(
        select(Project).where(Project.org_id == org_id)
    )
    all_projects = list(all_projects_result.scalars().all())
    logger.info(f"📂 Found {len(all_projects)} org projects: {[p.name for p in all_projects[:5]]}")

    # LENIENT MATCHING: normalize both sides (lowercase, strip non-alphanumerics,
    # transliterate Cyrillic → Latin) so:
    #  - "AdsCombinePro" matches "AdsCombine Pro", "ads-combine-pro"
    #  - "Saturn" matches "Сатурн" (и наоборот) — переведено в одну нотацию
    def _normalize(s: str) -> str:
        s = s.lower()
        s = ''.join(_CYR_TO_LAT.get(c, c) for c in s)
        return re.sub(r'[^a-z0-9]+', '', s)

    text_lower = message_text.lower()
    text_normalized = _normalize(message_text)
    text_matched_project = None
    # Pass 1 — точный/нормализованный substring.
    for p in all_projects:
        if len(p.name) < 3:
            continue
        name_lower = p.name.lower()
        name_normalized = _normalize(p.name)
        if name_lower in text_lower or (name_normalized and name_normalized in text_normalized):
            text_matched_project = p
            logger.info(f"🎯 Matched project '{p.name}' from message text (exact)")
            break

    # Pass 2 — fuzzy-fallback для опечаток («Сатург» → «Saturn»).
    # Берём слова из сообщения, сравниваем по difflib.ratio (stdlib).
    # Порог 0.8 — ловит 1-2 опечатки на коротких именах, при этом не цепляется
    # к похожим но другим проектам.
    if not text_matched_project:
        tokens = re.findall(r'[A-Za-zА-Яа-я0-9]+', message_text)
        best_p = None
        best_ratio = 0.0
        for p in all_projects:
            if len(p.name) < 4:  # слишком короткие — слишком много ложных
                continue
            name_norm = _normalize(p.name)
            if not name_norm:
                continue
            for tok in tokens:
                tok_norm = _normalize(tok)
                # сравниваем только токены сопоставимой длины
                if not tok_norm or abs(len(tok_norm) - len(name_norm)) > 3:
                    continue
                r = difflib.SequenceMatcher(None, tok_norm, name_norm).ratio()
                if r > best_ratio:
                    best_ratio = r
                    best_p = p
        if best_p and best_ratio >= 0.8:
            text_matched_project = best_p
            logger.info(
                f"🎯 Matched project '{best_p.name}' from message text "
                f"(fuzzy, ratio={best_ratio:.2f})"
            )

    if not text_matched_project:
        logger.warning(
            f"⏭️ No project name mentioned — available: {[p.name for p in all_projects]}; "
            f"message: {message_text[:160]}"
        )
        return []

    project = text_matched_project
    projects = [project]

    # Get existing tasks for duplicate detection
    existing_result = await db.execute(
        select(ProjectTask)
        .where(ProjectTask.project_id == project.id)
        .where(ProjectTask.status.notin_(['done', 'cancelled']))
    )
    existing_rows = list(existing_result.scalars().all())
    existing_tasks = [
        {"title": t.title, "status": t.status if isinstance(t.status, str) else t.status.value}
        for t in existing_rows
    ]
    existing_titles = [t.title or "" for t in existing_rows]

    # Parse message with AI
    parsed_tasks = await parse_message_to_tasks(message_text, user_name, existing_tasks)

    if not parsed_tasks:
        return []

    created = []
    today = datetime.utcnow().replace(hour=23, minute=59, second=59)

    for task_data in parsed_tasks:
        if task_data.get("is_duplicate"):
            continue
        # Дубли ловим и сами: модель сверяет только заголовки и промахивается,
        # когда ту же задачу на следующий день пишет другой человек (на проде
        # «Очистить кеш Cloudflare…» завели дважды, 16 и 17 сентября).
        similar = _find_similar_title(task_data.get("title", ""), existing_titles)
        if similar:
            logger.info(f"🔁 Похожая задача уже есть, пропускаю: «{task_data.get('title')}» ≈ «{similar}»")
            continue

        # Resolve project from hint
        target_project = project
        project_hint = task_data.get("project_hint")
        if project_hint:
            hint_norm = _normalize(project_hint)
            for p in all_projects:
                p_norm = _normalize(p.name)
                if project_hint.lower() in p.name.lower() or (hint_norm and p_norm and hint_norm in p_norm):
                    target_project = p
                    break

        # Resolve assignee from hint — prioritize chat owner, then search by name
        assignee_id = user.id
        assignee_display = user_name
        assignee_resolved = False  # стал ли хинт известным юзером
        assignee_hint = task_data.get("assignee_name")
        if assignee_hint:
            hint_lower = assignee_hint.lower()
            found_user = None

            # 1. PRIORITY: Check if the current chat's owner matches the hint
            #    (e.g., chat "RND - Евгений" → owner is the correct Евгений)
            if chat_id:
                chat_search_result = await db.execute(
                    select(Chat).where(Chat.telegram_chat_id == chat_id)
                )
                current_chat = chat_search_result.scalar_one_or_none()
                if current_chat and current_chat.owner_id:
                    owner_result = await db.execute(
                        select(User).where(User.id == current_chat.owner_id)
                    )
                    chat_owner = owner_result.scalar_one_or_none()
                    if chat_owner:
                        owner_name_lower = (chat_owner.name or "").lower()
                        # Check if hint matches chat owner name
                        if hint_lower in owner_name_lower or owner_name_lower in hint_lower:
                            found_user = chat_owner
                            logger.info(f"🎯 Assignee matched to chat owner: {chat_owner.name}")
                        # Also check chat title contains the hint (e.g. "RND - Евгений")
                        chat_title = (current_chat.custom_name or current_chat.title or "").lower()
                        if not found_user and hint_lower in chat_title:
                            found_user = chat_owner
                            logger.info(f"🎯 Assignee matched via chat title to owner: {chat_owner.name}")

            # 2. Search org members by name (scoped to org, not global)
            if not found_user:
                org_members_result = await db.execute(
                    select(User)
                    .join(OrgMember, OrgMember.user_id == User.id)
                    .where(OrgMember.org_id == org_id)
                    .where(User.name.ilike(f"%{assignee_hint}%"))
                )
                candidates = list(org_members_result.scalars().all())
                if len(candidates) == 1:
                    found_user = candidates[0]
                elif len(candidates) > 1:
                    # Multiple matches — prefer chat owner if any match
                    logger.warning(f"⚠️ Multiple users match '{assignee_hint}': {[u.name for u in candidates]}")
                    # Don't pick randomly, keep default assignee (message sender)

            # 3. If not found, search by chat title (chats named like "RND - Дима")
            if not found_user:
                chat_search = await db.execute(
                    select(Chat).where(
                        Chat.is_active == True,
                        (Chat.custom_name.ilike(f"%{assignee_hint}%")) | (Chat.title.ilike(f"%{assignee_hint}%"))
                    )
                )
                matched_chat = chat_search.scalar_one_or_none()
                if matched_chat and matched_chat.owner_id:
                    owner_result = await db.execute(
                        select(User).where(User.id == matched_chat.owner_id)
                    )
                    found_user = owner_result.scalar_one_or_none()

            # 4. If still not found, try first name match among org members
            if not found_user:
                all_members_result = await db.execute(
                    select(User)
                    .join(OrgMember, OrgMember.user_id == User.id)
                    .where(OrgMember.org_id == org_id)
                )
                all_members = all_members_result.scalars().all()
                for m in all_members:
                    member_name_lower = (m.name or "").lower()
                    member_first = member_name_lower.split()[0] if member_name_lower else ""
                    if hint_lower in member_name_lower or member_name_lower in hint_lower:
                        found_user = m
                        break
                    if hint_lower.startswith(member_first[:3]) and len(member_first) >= 3:
                        found_user = m
                        break

            if found_user:
                assignee_id = found_user.id
                assignee_display = found_user.name
                assignee_resolved = True

        # Блокер → вешаем на разработчика проекта, если явный ассайни не зарезолвлен
        # (не было хинта, либо хинт был, но никого не нашли в орге)
        if blocker_mode and not assignee_resolved:
            dev_result = await db.execute(
                select(User)
                .join(ProjectMember, ProjectMember.user_id == User.id)
                .where(ProjectMember.project_id == target_project.id)
                .where(ProjectMember.role == ProjectRole.developer)
                .order_by(ProjectMember.joined_at)
                .limit(1)
            )
            project_dev = dev_result.scalar_one_or_none()
            if project_dev:
                assignee_id = project_dev.id
                assignee_display = project_dev.name
                logger.info(f"🚨 Blocker → assigned to project developer: {project_dev.name}")

        # Блокер — всегда критический приоритет
        priority = task_data.get("priority", 1)
        if blocker_mode:
            priority = 3

        if dry_run:
            # Разбор для подтверждения в чате: ничего не пишем в базу
            created.append({
                "title": task_data.get("title"),
                "description": task_data.get("description"),
                "priority": priority,
                "estimated_hours": task_data.get("estimated_hours"),
                "assignee": assignee_display,
                "assignee_id": assignee_id,
                "project": target_project.name,
                "project_id": target_project.id,
                "is_blocker": blocker_mode,
                "creator_id": user.id,
                "blocker_id": blocker_id if blocker_mode else None,
            })
            existing_titles.append(task_data.get("title") or "")
            continue

        # Increment project task counter
        target_project.task_counter = (target_project.task_counter or 0) + 1

        task = ProjectTask(
            project_id=target_project.id,
            task_number=target_project.task_counter,
            title=task_data.get("title", "Без названия"),
            description=task_data.get("description"),
            status="todo",
            priority=priority,
            estimated_hours=task_data.get("estimated_hours"),
            assignee_id=assignee_id,
            due_date=today,
            created_by=user.id,
            blocker_id=blocker_id if blocker_mode else None,
            created_by_bot=True,
            source_chat_id=chat_id,
            source_message=message_text[:4000],
        )
        db.add(task)
        await db.flush()

        task_key = f"{target_project.prefix}-{target_project.task_counter}" if target_project.prefix else f"#{target_project.task_counter}"
        created.append({
            "task_key": task_key,
            "task_id": task.id,
            "title": task_data.get("title"),
            "assignee": assignee_display,
            "assignee_id": assignee_id,
            "project": target_project.name,
            "project_id": target_project.id,
            "is_blocker": blocker_mode,
            "creator_id": user.id,
        })

    if created and not dry_run:
        await db.commit()
        logger.info(f"Created {len(created)} tasks from chat message by {user_name}")

    return created


async def create_tasks_from_preview(
    db: AsyncSession,
    preview: list[dict],
    message_text: str,
    chat_id: Optional[int],
) -> list[dict]:
    """Создать задачи из разбора, который человек подтвердил кнопкой в чате."""
    from ..models.database import Project, ProjectTask

    created = []
    today = datetime.utcnow().replace(hour=23, minute=59, second=59)
    for item in preview:
        project = await db.get(Project, item["project_id"])
        if not project:
            logger.warning(f"Проект {item['project_id']} исчез, пропускаю задачу «{item['title']}»")
            continue
        project.task_counter = (project.task_counter or 0) + 1
        task = ProjectTask(
            project_id=project.id,
            task_number=project.task_counter,
            title=item.get("title") or "Без названия",
            description=item.get("description"),
            status="todo",
            priority=item.get("priority", 1),
            estimated_hours=item.get("estimated_hours"),
            assignee_id=item.get("assignee_id"),
            due_date=today,
            created_by=item.get("creator_id"),
            blocker_id=item.get("blocker_id"),
            created_by_bot=True,
            source_chat_id=chat_id,
            source_message=(message_text or "")[:4000],
        )
        db.add(task)
        await db.flush()
        task_key = f"{project.prefix}-{project.task_counter}" if project.prefix else f"#{project.task_counter}"
        created.append({**item, "task_key": task_key, "task_id": task.id})

    if created:
        await db.commit()
        logger.info(f"TASK_CONFIRMED: создано {len(created)} задач после подтверждения в чате")
    return created
