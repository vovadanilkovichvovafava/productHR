"""Разовый импорт дампа по частям (27.10.2026, api/routes/dump_import.py).

Ручки заменяют базу целиком, поэтому главное — что без переменной
IMPORT_DUMP_TOKEN и без верного токена их как будто нет (404), а собранный
файл не уходит в pg_restore, если размер или хеш не сошлись.
"""
import hashlib

import pytest

from api.routes import dump_import

TOKEN = "t" * 40


@pytest.fixture
def enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("IMPORT_DUMP_TOKEN", TOKEN)
    monkeypatch.setenv("IMPORT_DUMP_DIR", str(tmp_path))
    dump_import._state.update(stage="idle", received_bytes=0)
    calls = []

    async def fake_restore(path):
        calls.append(path.read_bytes())
        dump_import._state.update(stage="done", returncode=0)

    monkeypatch.setattr(dump_import, "_run_restore", fake_restore)
    yield calls
    dump_import._state.update(stage="idle")


async def test_closed_without_variable(client, monkeypatch):
    monkeypatch.delenv("IMPORT_DUMP_TOKEN", raising=False)
    r = await client.post("/api/dump-import/start", headers={"X-Import-Token": TOKEN})
    assert r.status_code == 404


async def test_closed_with_short_variable_or_wrong_token(client, monkeypatch, enabled):
    r = await client.post("/api/dump-import/start", headers={"X-Import-Token": "wrong" * 10})
    assert r.status_code == 404
    monkeypatch.setenv("IMPORT_DUMP_TOKEN", "short")
    r = await client.post("/api/dump-import/start", headers={"X-Import-Token": "short"})
    assert r.status_code == 404


async def test_chunks_assemble_and_restore_starts(client, enabled):
    h = {"X-Import-Token": TOKEN}
    payload = b"PGDMP" + bytes(range(256)) * 10
    a, b = payload[:1000], payload[1000:]
    assert (await client.post("/api/dump-import/start", headers=h)).status_code == 200
    # вторая часть раньше первой и повтор первой — файл всё равно собирается
    r = await client.put("/api/dump-import/chunk?offset=1000", content=b, headers=h)
    assert r.status_code == 200 and r.json()["sha256"] == hashlib.sha256(b).hexdigest()
    for _ in range(2):
        assert (await client.put("/api/dump-import/chunk?offset=0", content=a, headers=h)).status_code == 200

    r = await client.post("/api/dump-import/finish", json={"size": len(payload), "sha256": "0" * 64}, headers=h)
    assert r.status_code == 400 and not enabled

    r = await client.post(
        "/api/dump-import/finish",
        json={"size": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}, headers=h,
    )
    assert r.status_code == 200, r.text
    import asyncio
    await asyncio.sleep(0)
    assert enabled == [payload]
    st = await client.get("/api/dump-import/status", headers=h)
    assert st.json()["stage"] == "done"


async def test_chunk_before_start_rejected(client, enabled):
    r = await client.put("/api/dump-import/chunk?offset=0", content=b"x", headers={"X-Import-Token": TOKEN})
    assert r.status_code == 409
