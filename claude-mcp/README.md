# Enceladus MCP — Claude Code / Desktop integration

Дать Claude возможность создавать задачи в Энцеладусе одной командой:

> «Создай задачу в Saturn: починить webhook auto-deploy»
>
> *Claude вызывает `create_enceladus_task` → задача появляется в нужном проекте,
> назначается на ответственного, ссылка приходит в DM в Telegram.*

## Установка

### 1. Поставить Python-зависимости
```bash
pip install "mcp[cli]" httpx
```

### 2. Сгенерировать API-токен
Зайди на Энцеладус → пока через curl с твоим JWT (UI в профиле — todo):
```bash
# Получить JWT из cookie после логина (в DevTools → Application → Cookies)
TOKEN_JWT="..."

curl -X POST https://enceladus-ns9s2o.saturn.ac/api/integrations/api-tokens \
     -H "Authorization: Bearer $TOKEN_JWT" \
     -H "Content-Type: application/json" \
     -d '{"name":"Claude on MacBook"}'
```
В ответе будет поле `token` вида `enc_xxxxxxxx...` — **сохрани его сразу**,
второй раз не покажется. По нему все задачи будут создаваться от твоего имени.

### 3. Подключить в Claude
Открыть `~/.claude.json` или через `/mcp add` в Claude Code:
```jsonc
{
  "mcpServers": {
    "enceladus": {
      "command": "python3",
      "args": ["/абсолютный/путь/до/enceladus_mcp.py"],
      "env": {
        "ENCELADUS_URL": "https://enceladus-ns9s2o.saturn.ac",
        "ENCELADUS_TOKEN": "enc_xxxxxxxxxxxxxxxxxxxxxxxx..."
      }
    }
  }
}
```
Перезапустить Claude Code.

## Что доступно

- **`list_projects`** — список проектов твоей орги. Claude использует
  чтобы уточнить какой ты имел в виду.
- **`create_enceladus_task`** — создаёт задачу/задачи из NL-описания.
  Принимает `message` (что сделать) и опционально `project_hint`
  (название проекта). Матчинг проекта терпит:
  - Кириллицу ↔ латиницу: `Сатурн` ↔ `Saturn`
  - Опечатки: `Сатург` тоже найдёт `Saturn` (порог сходства 0.8)
  - Пробелы/регистр: `AdsCombine Pro` ↔ `adscombinepro`

  Если матч неоднозначный — Claude уточнит у тебя проект, потом дёрнет
  снова с `project_hint`.

## Под капотом

`create_enceladus_task` переиспользует `create_tasks_from_message` —
тот же сервис, который разбирает сообщения из Telegram (`/blocker`,
status reports). Поэтому всё что умеет бот, умеет и MCP:
- AI-парсинг multi-task сообщений
- Назначение на ответственного (по упоминанию `@username` или по
  владельцу проекта)
- Дедупликация (не создаст таску с тем же названием что уже в work)
- Telegram-DM ассайни сразу как задача создана

## Безопасность

- Токены хранятся как **sha256 hash**, plaintext показывается ОДИН раз
- Каждый токен принадлежит конкретному юзеру → задачи `created_by` =
  владелец токена
- Отзыв: `DELETE /api/integrations/api-tokens/{id}` (UI тоже todo)
- `last_used_at` обновляется при каждом запросе — видно живой ли токен
