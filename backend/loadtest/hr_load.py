"""HR-раздел: нагрузочный харнесс для проверки «выдержит ли массовую работу».

Симулирует РЕАЛЬНЫЙ паттерн нагрузки HR-раздела:
  • N параллельных HR-сессий, которые крутят самые тяжёлые/частые ручки:
      - GET /candidates/kanban   (доска «Все кандидаты», фронт поллит каждые 15с)
      - GET /candidates/search   (поиск/список)
      - GET /candidates/ids      («Выбрать всех»)
      - GET /notifications + /unread-count (поллинг каждые 25с)
  • опционально — поток кандидатов, отправляющих публичную анкету
      (POST /forms/public/{slug}/submit), если задан LOADTEST_ANKETA_SLUG.

Меряет на каждую ручку: count, ошибки, RPS, p50/p95/p99/max латентности — и печатает
сводку + вердикт. По умолчанию ТОЛЬКО ЧТЕНИЕ (безопасно гонять против staging).

Запуск (PowerShell, из backend/):
    $env:LOADTEST_BASE_URL="https://enceladus-7oylzk.saturn.ac"
    $env:LOADTEST_EMAIL="hr@example.com"; $env:LOADTEST_PASSWORD="..."
    $env:LOADTEST_USERS="30"; $env:LOADTEST_DURATION="60"
    .\.venv\Scripts\python.exe loadtest\hr_load.py

Вместо email/пароля можно дать готовый токен: LOADTEST_TOKEN=...
Логинимся ОДИН раз (на /login лимит 5/мин) и шарим токен на все сессии.
"""
import asyncio
import os
import statistics
import time
from collections import defaultdict

import httpx

BASE_URL = os.environ.get("LOADTEST_BASE_URL", "http://localhost:8000").rstrip("/")
API = BASE_URL + "/api"
EMAIL = os.environ.get("LOADTEST_EMAIL", "")
PASSWORD = os.environ.get("LOADTEST_PASSWORD", "")
TOKEN = os.environ.get("LOADTEST_TOKEN", "")
USERS = int(os.environ.get("LOADTEST_USERS", "20"))
DURATION = float(os.environ.get("LOADTEST_DURATION", "30"))
THINK_MS = float(os.environ.get("LOADTEST_THINK_MS", "800"))
ANKETA_SLUG = os.environ.get("LOADTEST_ANKETA_SLUG", "")
ANKETA_USERS = int(os.environ.get("LOADTEST_ANKETA_USERS", "5"))
PER_COLUMN = int(os.environ.get("LOADTEST_PER_COLUMN", "500"))
TIMEOUT = float(os.environ.get("LOADTEST_TIMEOUT", "30"))

# endpoint -> list[latency_ms]; и endpoint -> error count
LAT: dict[str, list[float]] = defaultdict(list)
ERR: dict[str, int] = defaultdict(int)
STOP = False


async def timed(client: httpx.AsyncClient, name: str, method: str, url: str, **kw):
    """Один запрос с замером латентности и учётом ошибок (>=400 или исключение)."""
    t0 = time.perf_counter()
    try:
        r = await client.request(method, url, **kw)
        dt = (time.perf_counter() - t0) * 1000
        LAT[name].append(dt)
        if r.status_code >= 400:
            ERR[name] += 1
        return r
    except Exception:
        LAT[name].append((time.perf_counter() - t0) * 1000)
        ERR[name] += 1
        return None


async def hr_session(client: httpx.AsyncClient, headers: dict):
    """Цикл одной HR-сессии: тяжёлые ручки + think-time, пока не STOP."""
    q_cycle = ["", "ив", "developer", "manager", "анна", "qa"]
    i = 0
    while not STOP:
        await timed(client, "GET /candidates/kanban", "GET",
                    f"{API}/candidates/kanban", params={"per_column": PER_COLUMN}, headers=headers)
        await timed(client, "GET /notifications", "GET",
                    f"{API}/notifications", headers=headers)
        await timed(client, "GET /notifications/unread-count", "GET",
                    f"{API}/notifications/unread-count", headers=headers)
        await timed(client, "GET /candidates/search", "GET",
                    f"{API}/candidates/search", params={"q": q_cycle[i % len(q_cycle)], "per_page": 50}, headers=headers)
        await timed(client, "GET /candidates/ids", "GET",
                    f"{API}/candidates/ids", headers=headers)
        i += 1
        await asyncio.sleep(THINK_MS / 1000.0)


async def anketa_session(client: httpx.AsyncClient, slug: str, idx: int):
    """Кандидат отправляет публичную анкету (без авторизации)."""
    n = 0
    while not STOP:
        payload = {"data": {"name": f"LoadTest {idx}-{n}", "comment": "нагрузочный прогон"}}
        await timed(client, "POST /forms/public/submit", "POST",
                    f"{API}/forms/public/{slug}/submit", json=payload)
        n += 1
        await asyncio.sleep(THINK_MS / 1000.0)


async def get_token() -> str:
    if TOKEN:
        return TOKEN
    if not (EMAIL and PASSWORD):
        raise SystemExit("Нужен LOADTEST_TOKEN либо LOADTEST_EMAIL+LOADTEST_PASSWORD")
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(f"{API}/auth/login", json={"email": EMAIL, "password": PASSWORD})
        r.raise_for_status()
        tok = r.json().get("access_token")
        if not tok:
            raise SystemExit(f"Логин не вернул access_token: {r.text[:200]}")
        return tok


def pct(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    k = max(0, min(len(s) - 1, int(round(p / 100.0 * (len(s) - 1)))))
    return s[k]


def report(elapsed: float):
    print("\n" + "=" * 92)
    print(f"HR LOAD: {USERS} HR-сессий + {ANKETA_USERS if ANKETA_SLUG else 0} анкет, "
          f"{elapsed:.1f}s, target={BASE_URL}")
    print("=" * 92)
    print(f"{'endpoint':40} {'reqs':>7} {'err':>5} {'rps':>7} "
          f"{'p50':>7} {'p95':>8} {'p99':>8} {'max':>8}  (ms)")
    print("-" * 92)
    total_req = total_err = 0
    worst_p95 = 0.0
    for name in sorted(LAT):
        d = LAT[name]
        n, e = len(d), ERR[name]
        total_req += n
        total_err += e
        worst_p95 = max(worst_p95, pct(d, 95))
        print(f"{name:40} {n:>7} {e:>5} {n/elapsed:>7.1f} "
              f"{statistics.median(d):>7.0f} {pct(d,95):>8.0f} {pct(d,99):>8.0f} {max(d):>8.0f}")
    print("-" * 92)
    err_rate = (total_err / total_req * 100) if total_req else 0
    print(f"ИТОГО: {total_req} запросов, {total_err} ошибок ({err_rate:.2f}%), "
          f"{total_req/elapsed:.1f} rps, худший p95={worst_p95:.0f}ms")
    # Простой вердикт-светофор.
    verdict = "✅ ВЫДЕРЖИВАЕТ"
    if err_rate > 1 or worst_p95 > 2000:
        verdict = "❌ НЕ ВЫДЕРЖИВАЕТ (ошибки/латентность)"
    elif err_rate > 0.1 or worst_p95 > 800:
        verdict = "⚠️  НА ГРАНИ (смотри p95/ошибки)"
    print(f"ВЕРДИКТ: {verdict}")
    print("=" * 92)


async def main():
    global STOP
    token = await get_token()
    headers = {"Authorization": f"Bearer {token}"}
    print(f"target={BASE_URL}  HR-сессий={USERS}  анкет={ANKETA_USERS if ANKETA_SLUG else 0}  "
          f"длительность={DURATION}s  per_column={PER_COLUMN}")

    limits = httpx.Limits(max_connections=USERS + ANKETA_USERS + 10,
                          max_keepalive_connections=USERS + ANKETA_USERS + 10)
    async with httpx.AsyncClient(timeout=TIMEOUT, limits=limits) as client:
        tasks = [asyncio.create_task(hr_session(client, headers)) for _ in range(USERS)]
        if ANKETA_SLUG:
            tasks += [asyncio.create_task(anketa_session(client, ANKETA_SLUG, i))
                      for i in range(ANKETA_USERS)]
        t0 = time.perf_counter()
        await asyncio.sleep(DURATION)
        STOP = True
        await asyncio.gather(*tasks, return_exceptions=True)
        report(time.perf_counter() - t0)


if __name__ == "__main__":
    asyncio.run(main())
