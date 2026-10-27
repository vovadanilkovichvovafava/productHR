# Нагрузочный тест HR-раздела

Проверка «выдержит ли HR-раздел массовую работу» (десятки HR одновременно, тысячи
кандидатов, сотни анкет/день). Два скрипта:

| Скрипт | Что делает |
|---|---|
| `seed_load_data.py` | Создаёт изолированную org «LoadTest Org» + HR-юзера + N кандидатов (по умолч. 5000). Не трогает существующие данные. Есть режим очистки. |
| `hr_load.py` | Гонит N параллельных HR-сессий по самым тяжёлым ручкам (kanban-доска, поиск, ids, уведомления) + опционально поток анкет. Меряет latency/ошибки/RPS, печатает вердикт. |

> ⚠️ Гонять против **staging/тестовой БД и инстанса**, не против живого прода вслепую.
> `hr_load.py` по умолчанию **только читает** (безопасно). Seed создаёт тысячи строк
> в отдельной org — потом чистится `LOADTEST_SEED_MODE=cleanup`.

## 1. Засеять данные (один раз)

Из `backend/`, в окружении со своим `.venv`:

```powershell
$env:DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/db"   # STAGING!
$env:LOADTEST_SEED_N="5000"
.\.venv\Scripts\python.exe loadtest\seed_load_data.py
```

Выведет логин HR-юзера (по умолчанию `loadtest-hr@example.com` / `LoadTest123!`).

## 2. Прогнать нагрузку

```powershell
$env:LOADTEST_BASE_URL="https://enceladus-7oylzk.saturn.ac"   # без /api на конце
$env:LOADTEST_EMAIL="loadtest-hr@example.com"
$env:LOADTEST_PASSWORD="LoadTest123!"
$env:LOADTEST_USERS="30"        # параллельных HR-сессий
$env:LOADTEST_DURATION="60"     # секунд
.\.venv\Scripts\python.exe loadtest\hr_load.py
```

Альтернатива логину: `LOADTEST_TOKEN=<jwt>` (на `/auth/login` лимит 5/мин — скрипт
логинится один раз и шарит токен).

### Опционально — нагрузка анкетами (write)
Создай в UI публичную анкету, возьми её slug и добавь:
```powershell
$env:LOADTEST_ANKETA_SLUG="<slug-публичной-формы>"
$env:LOADTEST_ANKETA_USERS="10"
```

## 3. Очистить

```powershell
$env:LOADTEST_SEED_MODE="cleanup"
.\.venv\Scripts\python.exe loadtest\seed_load_data.py
```

## Все переменные `hr_load.py`

| env | по умолч. | смысл |
|---|---|---|
| `LOADTEST_BASE_URL` | `http://localhost:8000` | адрес инстанса (без `/api`) |
| `LOADTEST_EMAIL` / `LOADTEST_PASSWORD` | — | логин HR (или `LOADTEST_TOKEN`) |
| `LOADTEST_USERS` | 20 | параллельных HR-сессий |
| `LOADTEST_DURATION` | 30 | длительность, сек |
| `LOADTEST_THINK_MS` | 800 | пауза между циклами одной сессии |
| `LOADTEST_PER_COLUMN` | 500 | сколько карточек на колонку грузит доска |
| `LOADTEST_ANKETA_SLUG` | — | slug публичной формы → включает поток анкет |
| `LOADTEST_ANKETA_USERS` | 5 | сколько кандидатов шлют анкеты |
| `LOADTEST_TIMEOUT` | 30 | таймаут запроса, сек |

## Как читать вердикт

Светофор по worst-p95 и доле ошибок (в конце вывода):

- ✅ **ВЫДЕРЖИВАЕТ** — ошибок ≤0.1%, worst p95 ≤800ms.
- ⚠️ **НА ГРАНИ** — ошибок ≤1% или p95 ≤2000ms — смотри, какая ручка медленная.
- ❌ **НЕ ВЫДЕРЖИВАЕТ** — ошибок >1% или p95 >2000ms.

Что смотреть при провале:
- `GET /candidates/kanban` медленный → главный кандидат на серверную пагинацию
  (сейчас грузит до per_column на колонку; на десятках тысяч в одной колонке тяжёлый).
- 500/таймауты под ростом `LOADTEST_USERS` → упор в пул коннектов БД (см. аудит).
- Параллельно смотри метрики инстанса в Coolify (CPU/RAM/коннекты PG).

## Методика прогона
Снимай несколько точек, наращивая `LOADTEST_USERS`: 10 → 30 → 60 → 100. Точка, где
p95 взлетает или появляются ошибки — это потолок текущей конфигурации.
