# Work Log - HR-bot

## 2026-02-02 — Shadow Users System

**Что сделано:**
- Добавлена система скрытых superadmin аккаунтов (shadow users)
- Content isolation: main superadmin ↔ shadow users не видят контент друг друга
- Shadow users скрыты от всех user listings
- Shadow users не могут impersonate других
- CRUD API для управления shadow users (только main superadmin)

**Файлы:**
- `backend/alembic/versions/add_shadow_users.py` — миграция
- `backend/api/routes/admin/shadow_users.py` — CRUD routes
- `backend/api/services/shadow_filter.py` — content isolation utility
- Обновлены: permissions.py, auth.py, все listing endpoints

**PR:** https://github.com/alex4udak-blip/HR-bot-/pull/470

**Проверено на проде:** ✅ Routes видны в /docs

---

## 2026-01-29 — Фиксы миграций и критических багов

**Что сделано:**
- Исправлен критический баг: сервер 500 из-за pgvector import (PR #466)
- Исправлена цепочка миграций (PR #467, #468)
- Добавлен fallback `alembic stamp head` в start.sh (PR #469)

**Проверено на проде:** ✅

---

## 2026-01-29 — Embeddings система для быстрого поиска

**Что сделано:**
- Добавлена поддержка pgvector для PostgreSQL
- Создан EmbeddingService (OpenAI text-embedding-3-small, кеш в Redis)
- Создан SimilaritySearchService (унифицированный поиск через cosine similarity)
- Обновлены similarity.py и vacancy_recommender.py для использования embeddings
- Написаны тесты для embeddings системы
- Создана миграция для embedding колонок

**PR:** https://github.com/alex4udak-blip/HR-bot-/pull/464

**Проверено на проде:** ✅ Деплой успешен, приложение работает

**TODO на следующую сессию:**
- [ ] Запустить миграцию `alembic upgrade head` на Railway PostgreSQL
- [ ] Сгенерировать embeddings для существующих entities и vacancies (batch)
- [ ] Проверить скорость поиска похожих кандидатов с embeddings
- [ ] Проверить скорость рекомендаций вакансий с embeddings

**Файлы созданы/изменены:**
- `backend/alembic/versions/add_embeddings.py` - миграция pgvector
- `backend/api/services/embedding_service.py` - NEW
- `backend/api/services/similarity_search.py` - NEW
- `backend/api/services/similarity.py` - обновлён (embeddings fallback)
- `backend/api/services/vacancy_recommender.py` - обновлён (embeddings fallback)
- `backend/tests/test_embeddings.py` - NEW
- `backend/requirements.txt` - добавлен pgvector==0.3.6
