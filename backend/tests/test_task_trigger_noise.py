"""Бот не должен предлагать задачи из обычной переписки.

Сообщения ниже — настоящие, из рабочих чатов RND (выгрузка 25.09.2026).
Старая логика срабатывала на 14% ВСЕХ сообщений: регулярка «надо…проверить»,
«сегодня:», списки «1. 2.» решали за модель, а слова «не работает / падает»
создавали задачи вообще без проверки. Теперь регулярка — только предварительный
отбор, решает модель, а отчёты и короткие реплики отсекаются до неё.
"""
import pytest

from api.services import task_trigger as tt


# Настоящие сообщения, из которых задача возникать НЕ должна
NOISE = [
    "Так, если что я продолжаю работу над вчерашним",
    "Пока продолжаю работу",
    "Доброе утро, продолжаю работу)",
    "Доброе утро, продолжаю работу Напишу отчет вечером за сегодня и за вчера",
    "Отчет за сегодня: Улучшал генератор лендов, тестировал клонирование лендов, есть над чем работать",
    "принял, ща займусь",
    "Да, сейчас под него переделаю",
    "ок, сделаю позже",
]

# А это — настоящие постановки задач и планы
TASKS = [
    "доброе уутро, сегодня по плану разобраться почему адс павер иногда втихаря умирает, плюс пофиксить размер изображений",
    "Доброе утро Сегодня займусь двумя вещами: умной буферизацией сообщений и настройкой вебхуков",
    "Твоя задача пингавать этого баера",
    "Нужно переписать браузер для обхода клоаки",
]


@pytest.mark.parametrize("text", NOISE)
def test_noise_is_filtered_before_ai(text):
    """Отчёты и реплики отсекаются ещё до модели — это дёшево и предсказуемо."""
    assert tt.is_work_report(text) or tt.is_chatter(text) or tt.NEGATIVE_REGEX.search(text)


# План дня часто начинается с «продолжаю работу» — такие сообщения резать нельзя
PLANS_WITH_REPORT_PREFIX = [
    'Добрый день, продолжаю работу По планам: 1. Доделать кнопку "отправить" 2. Проверить вебхуки',
    "Доброе утро, сегодня по плану продолжаю работать над процессом обработки заявок, потом настрою алерты",
]


@pytest.mark.parametrize("text", PLANS_WITH_REPORT_PREFIX)
def test_plan_after_greeting_is_not_a_report(text):
    assert tt.is_work_report(text) is False


@pytest.mark.parametrize("text", TASKS)
def test_real_tasks_pass_prefilter(text):
    """Настоящие задачи предварительный отбор пропускает дальше, к модели."""
    assert not tt.is_work_report(text)
    assert not tt.is_chatter(text)
    assert tt.TRIGGER_REGEX.search(text)


@pytest.mark.asyncio
@pytest.mark.parametrize("text", NOISE)
async def test_noise_never_triggers(text, monkeypatch):
    """Даже если модель скажет «да», шум до неё не доходит."""
    async def _yes(_):
        return {"is_task": True, "confidence": 1.0, "reason": "тест"}
    monkeypatch.setattr(tt, "ai_decide", _yes)
    assert await tt.should_trigger_ai(text) is False


@pytest.mark.asyncio
async def test_model_decides_not_regex(monkeypatch):
    """Регулярка совпала, но модель сказала «нет» — задачи нет."""
    text = "и еще мало людей будут писать текстом"
    async def _no(_):
        return {"is_task": False, "confidence": 0.9, "reason": "обсуждение"}
    monkeypatch.setattr(tt, "ai_decide", _no)
    assert await tt.should_trigger_ai(text) is False


@pytest.mark.asyncio
async def test_low_confidence_is_rejected(monkeypatch):
    """Модель сомневается — чат не дёргаем."""
    async def _maybe(_):
        return {"is_task": True, "confidence": 0.4, "reason": "не уверен"}
    monkeypatch.setattr(tt, "ai_decide", _maybe)
    assert await tt.should_trigger_ai(TASKS[0]) is False


@pytest.mark.asyncio
async def test_blocker_words_are_not_a_bypass(monkeypatch):
    """«Не работает» больше не создаёт задачу в обход проверки."""
    text = "у меня не работает прод, смотрю логи"
    async def _no(_):
        return {"is_task": False, "confidence": 0.9, "reason": "жалоба, не задача"}
    monkeypatch.setattr(tt, "ai_decide", _no)
    assert tt.is_blocker(text) is True
    assert await tt.should_trigger_ai(text) is False


def test_similar_titles_are_duplicates():
    """Ту же задачу на следующий день от другого человека не заводим снова."""
    existing = ["Очистить кеш Cloudflare для домена pwa-proj-9y5yau.saturn.ac"]
    same = tt._find_similar_title("Очистить кэш Cloudflare для домена pwa-proj-9y5yau.saturn.ac", existing)
    assert same == existing[0]
    assert tt._find_similar_title("Поднять новый сервер под бота", existing) is None


# Настоящие постановки задач, которые бот пропускал: в них нет модального
# слова («надо», «нужно»), а список — из одного пункта (владелец, 28.09.2026)
DIRECT_TASKS = [
    "ZavodCamp:\n1. Проверить качество поиска по API для блока Assets Search",
    "Saturn: 1. Поднять новый сервер под бота",
    "- Добавить фильтр по датам на доске",
    "Проверить прод после выкатки",
]


@pytest.mark.parametrize("text", DIRECT_TASKS)
def test_direct_task_lines_pass_prefilter(text):
    assert tt.TRIGGER_REGEX.search(text), "предварительный отбор не увидел задачу"


@pytest.mark.asyncio
@pytest.mark.parametrize("text", DIRECT_TASKS)
async def test_direct_task_lines_reach_model(text, monkeypatch):
    calls = []

    async def _yes(t):
        calls.append(t)
        return {"is_task": True, "confidence": 0.9, "reason": "явная задача"}

    monkeypatch.setattr(tt, "ai_decide", _yes)
    assert await tt.should_trigger_ai(text) is True
    assert calls, "модель должна была получить сообщение"
