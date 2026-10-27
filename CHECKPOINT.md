# CHECKPOINT — Embeddings система для HR-bot

**Задача:** Внедрить embeddings для быстрого поиска похожих кандидатов и подходящих вакансий

**Проект:** HR-bot-

**План:**
1. [x] Миграция pgvector + embedding колонки (Entity, Vacancy)
2. [x] Сервис embeddings (генерация через OpenAI, кеш в Redis)
3. [x] Унифицированный similarity search
4. [x] Обновить endpoints
5. [x] Автотесты
6. [ ] Git + PR + deploy
7. [ ] Тест на проде

**Текущий статус:** Шаг 6 - Git + PR

**Агенты:**
- Миграция pgvector
- Сервис embeddings
- Тесты

**Архитектура:**
```
Entity/Vacancy сохранён
        ↓
   Генерация embedding (OpenAI text-embedding-3-small)
        ↓
   Сохранение в БД (vector column)
        ↓
   При поиске: cosine similarity через pgvector
        ↓
   <100ms результат
```

**Файлы будут созданы/изменены:**
- `backend/alembic/versions/add_embeddings.py` (миграция)
- `backend/api/services/embedding_service.py` (новый)
- `backend/api/services/similarity_search.py` (новый)
- `backend/api/routes/entities/search.py` (обновление)
- `backend/tests/test_embeddings.py` (новый)

**Технические детали:**
- pgvector extension для PostgreSQL
- OpenAI text-embedding-3-small (1536 dimensions)
- Кеш embeddings в Redis (TTL 7 дней)
- Batch генерация для существующих записей
