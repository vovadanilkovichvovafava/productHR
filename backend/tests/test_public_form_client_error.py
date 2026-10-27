"""Отчёт браузера о сбое отправки публичной анкеты (19.10.2026).

17.10 кандидат пять раз подряд видел «Произошла ошибка при отправке», а в логах
бэкенда и nginx не осталось ни одного запроса отправки. Теперь страница анкеты
сама сообщает о сбое — здесь проверяем, что отчёт принимается без авторизации,
попадает в лог с маркером и не тащит туда секрет целиком.
"""
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.forms import router

app = FastAPI()
app.include_router(router, prefix="/api/forms")
client = TestClient(app)


def test_report_is_accepted_and_logged(caplog):
    caplog.set_level(logging.WARNING, logger="hr-analyzer.forms")
    r = client.post(
        "/api/forms/public/client-error",
        json={"link": "hsG6UFTG111hsQtk3tRM2Q", "kind": "network", "status": None,
              "message": "AxiosError: ERR_NETWORK Network Error", "online": True},
        headers={"User-Agent": "Mozilla/5.0 (iPhone)"},
    )
    assert r.status_code == 204
    line = next(rec.getMessage() for rec in caplog.records if "PUBLIC_FORM_CLIENT_ERROR" in rec.getMessage())
    assert "kind=network" in line
    assert "iPhone" in line
    # Личная ссылка кандидата — секрет: в лог только начало.
    assert "hsG6UF…" in line
    assert "hsG6UFTG111hsQtk3tRM2Q" not in line


def test_huge_message_is_trimmed(caplog):
    caplog.set_level(logging.WARNING, logger="hr-analyzer.forms")
    r = client.post("/api/forms/public/client-error", json={"message": "x" * 5000, "kind": "client"})
    assert r.status_code == 204
    line = next(rec.getMessage() for rec in caplog.records if "PUBLIC_FORM_CLIENT_ERROR" in rec.getMessage())
    assert len(line) < 1200


def test_empty_report_does_not_fail():
    assert client.post("/api/forms/public/client-error", json={}).status_code == 204
