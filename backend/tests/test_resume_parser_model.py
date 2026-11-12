"""Разбор резюме в окне «Загрузка из файла» — на Haiku 5.5 (12.11.2026).

Sonnet 4.6 стоил ≈1,5 цента за резюме, Haiku 5.5 — ≈0,05. Правила:
- дешёвая модель отвечает с блоками размышлений впереди — ответ берём по типу
  блока, а не content[0];
- отказ / кривой JSON / ошибка дешёвой модели — тот же запрос уходит основной;
- первые N разборов сверяются с основной моделью в фоне (RESUME_COMPARE).
"""
import asyncio
from types import SimpleNamespace

import pytest

from api.services import parser as P


def _resp(text, stop="end_turn", thinking=True):
    blocks = []
    if thinking:
        blocks.append(SimpleNamespace(type="thinking", thinking="", signature="x"))
    blocks.append(SimpleNamespace(type="text", text=text))
    return SimpleNamespace(content=blocks, stop_reason=stop)


class FakeClient:
    def __init__(self, answers):
        self.answers = answers  # model -> response | Exception
        self.calls = []
        self.messages = self

    async def create(self, **kw):
        self.calls.append(kw)
        a = self.answers[kw["model"]]
        if isinstance(a, Exception):
            raise a
        return a


@pytest.fixture
def models(monkeypatch):
    monkeypatch.setattr(P.settings, "resume_parser_model", "claude-haiku-5-5")
    monkeypatch.setattr(P.settings, "claude_model", "claude-sonnet-4-6")
    monkeypatch.setattr(P, "_compare_left", 0)


def _use(monkeypatch, client):
    monkeypatch.setattr(P, "_get_ai_client", lambda: client)


@pytest.mark.asyncio
async def test_card_goes_to_haiku_and_reads_text_block(monkeypatch, models):
    c = FakeClient({"claude-haiku-5-5": _resp('{"name": "Иван Петров", "skills": ["Python"]}')})
    _use(monkeypatch, c)
    data = await P.parse_with_ai("резюме", "resume_card")
    assert data["name"] == "Иван Петров"
    assert [x["model"] for x in c.calls] == ["claude-haiku-5-5"]
    # Низкое усилие — полем запроса (SDK 0.76 не знает output_config).
    assert c.calls[0]["extra_body"] == {"output_config": {"effort": "low"}}
    assert "temperature" not in c.calls[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("haiku", [
    _resp("", stop="refusal", thinking=False),
    _resp("это не json"),
    RuntimeError("сеть"),
])
async def test_haiku_failure_falls_back_to_main_model(monkeypatch, models, haiku):
    c = FakeClient({
        "claude-haiku-5-5": haiku,
        "claude-sonnet-4-6": _resp('{"name": "Иван"}', thinking=False),
    })
    _use(monkeypatch, c)
    data = await P.parse_with_ai("резюме", "resume_card")
    assert data == {"name": "Иван"}
    assert [x["model"] for x in c.calls] == ["claude-haiku-5-5", "claude-sonnet-4-6"]
    assert "extra_body" not in c.calls[1]


@pytest.mark.asyncio
async def test_full_resume_and_vacancy_stay_on_main_model(monkeypatch, models):
    c = FakeClient({"claude-sonnet-4-6": _resp('{"title": "x"}', thinking=False)})
    _use(monkeypatch, c)
    await P.parse_with_ai("текст", "vacancy")
    await P.parse_with_ai("текст", "resume")
    assert {x["model"] for x in c.calls} == {"claude-sonnet-4-6"}


@pytest.mark.asyncio
async def test_same_model_means_old_behaviour(monkeypatch, models):
    monkeypatch.setattr(P.settings, "resume_parser_model", "claude-sonnet-4-6")
    c = FakeClient({"claude-sonnet-4-6": _resp('{"name": "x"}', thinking=False)})
    _use(monkeypatch, c)
    await P.parse_with_ai("резюме", "resume_card")
    assert len(c.calls) == 1 and c.calls[0]["max_tokens"] == 2048


@pytest.mark.asyncio
async def test_background_compare_runs_limited_times(monkeypatch, models, caplog):
    monkeypatch.setattr(P, "_compare_left", 1)
    c = FakeClient({
        "claude-haiku-5-5": _resp('{"name": "Иван Петров", "phone": "+7 916 123-45-67", "skills": ["A", "B"]}'),
        "claude-sonnet-4-6": _resp('{"name": "иван  петров", "phone": "89161234567", "skills": ["a"]}',
                                   thinking=False),
    })
    _use(monkeypatch, c)
    caplog.set_level("INFO")
    await P.parse_with_ai("резюме", "resume_card")
    await asyncio.gather(*list(P._compare_tasks))
    await P.parse_with_ai("резюме", "resume_card")  # лимит исчерпан — без сверки
    assert [x["model"] for x in c.calls] == ["claude-haiku-5-5", "claude-sonnet-4-6", "claude-haiku-5-5"]
    line = next(r.getMessage() for r in caplog.records if "RESUME_COMPARE" in r.getMessage())
    assert "совпали 11/11" in line and "навыки 50%" in line
    # В лог не попадают данные кандидата.
    assert "Петров" not in line and "916" not in line


def test_compare_parses_buckets():
    c = P.compare_parses(
        {"name": "А", "email": None, "position": "Дизайнер", "experience_years": 5.2},
        {"name": "а", "email": "a@b.c", "position": "Продакт", "company": None, "experience_years": 5},
    )
    assert "name" in c["same"] and "experience_years" in c["same"]
    assert c["diff"] == ["position"]
    assert c["only_main"] == ["email"]
