"""Учёт расхода Claude и короткий разбор резюме (21.10.2026).

Запросы к Anthropic подменены локальным транспортом — реальных вызовов нет.
"""
import json
import logging

import httpx
import pytest
from anthropic import AsyncAnthropic

from api.services import ai_usage, parser
from api.services.ai_usage import estimate_cost, label_of


def _client(handler):
    return AsyncAnthropic(api_key="test", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def _ok_message(text: str, inp: int = 1200, out: int = 150):
    return {
        "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-sonnet-4-6",
        "content": [{"type": "text", "text": text}], "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {"input_tokens": inp, "output_tokens": out},
    }


@pytest.fixture(autouse=True)
def installed():
    ai_usage.install()


def test_cost_and_labels():
    # Sonnet 4.6: $3 / $15 за миллион.
    assert estimate_cost("claude-sonnet-4-6", 1_000_000, 0) == 3.0
    assert estimate_cost("claude-sonnet-4-6", 0, 1_000_000) == 15.0
    assert estimate_cost("claude-haiku-5-5", 1_000_000, 1_000_000) == 0.6
    assert estimate_cost("unknown-model", 10, 10) is None
    assert label_of("services/parser.py:parse_with_ai").startswith("Разбор резюме")
    assert label_of("services/whatever.py:x") == "services/whatever.py:x"


async def test_card_parse_asks_only_card_fields_and_is_counted(monkeypatch, caplog):
    sent = {}

    def handler(request: httpx.Request):
        sent.update(json.loads(request.content))
        answer = {"name": "Иванов Иван", "email": "ivan@mail.ru", "phone": None, "telegram": None,
                  "position": "Маркетолог", "company": None, "location": "Минск",
                  "experience_years": 3, "skills": [f"s{i}" for i in range(40)],
                  "salary_min": None, "salary_max": None, "salary_currency": None,
                  "summary": "Маркетолог с опытом 3 года."}
        return httpx.Response(200, json=_ok_message(json.dumps(answer, ensure_ascii=False)))

    monkeypatch.setattr(parser, "_get_ai_client", lambda: _client(handler))

    class _Doc:
        status, content, error = "parsed", "Иванов Иван\nМаркетолог\nivan@mail.ru", None

    async def fake_parse(*a, **k):
        return _Doc()
    monkeypatch.setattr(parser.document_parser, "parse", fake_parse)

    with caplog.at_level(logging.INFO, logger="hr-analyzer.ai_usage"):
        resume = await parser.parse_resume_from_file(b"%PDF", "cv.pdf", card=True)

    prompt = sent["messages"][0]["content"]
    assert prompt.startswith(parser.RESUME_CARD_PROMPT)
    assert "experience\"" not in parser.RESUME_CARD_PROMPT and "education" not in parser.RESUME_CARD_PROMPT
    assert sent["max_tokens"] == 2048
    assert resume.name == "Иванов Иван" and resume.summary
    assert resume.salary_currency == "RUB"          # null от модели → по умолчанию
    assert len(resume.skills) == 30                 # не больше 30

    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("AI_USAGE model"))
    assert "caller=services/parser.py:parse_with_ai" in line
    assert "in=1200 out=150" in line
    assert "cost=$0.00585" in line                  # 1200×3 + 150×15 за миллион


async def test_failed_call_is_counted_too(monkeypatch, caplog):
    def handler(request):
        return httpx.Response(400, json={"type": "error", "error": {
            "type": "invalid_request_error", "message": "Your credit balance is too low"}})

    client = _client(handler)
    with caplog.at_level(logging.INFO, logger="hr-analyzer.ai_usage"):
        with pytest.raises(Exception):
            await client.messages.create(model="claude-sonnet-4-6", max_tokens=10,
                                         messages=[{"role": "user", "content": "x"}])
    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("AI_USAGE model"))
    assert "error=" in line and "credit balance" in line


async def test_stream_usage_counted(caplog):
    class _Snapshot:
        class usage:
            input_tokens, output_tokens = 500, 40
            cache_read_input_tokens = cache_creation_input_tokens = 0

    class _Stream:
        current_message_snapshot = _Snapshot()

    class _Manager:
        async def __aenter__(self):
            return _Stream()

        async def __aexit__(self, *exc):
            return False

    proxy = ai_usage._AsyncStreamManagerProxy(_Manager(), "claude-sonnet-4-6", "services/ai.py:chat", 0.0)
    with caplog.at_level(logging.INFO, logger="hr-analyzer.ai_usage"):
        async with proxy:
            pass
    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("AI_USAGE model"))
    assert "in=500 out=40" in line and "caller=services/ai.py:chat" in line
