# ACTUAL_TASKS.md — Актуальные задачи HR-bot

> **Создано:** 18 января 2026, 23:45 MSK
> **Статус:** Актуальный список после полного аудита проекта

---

## СТАТУС ПРОЕКТА: 10/10 ✅

Проект прошёл полный рефакторинг безопасности, архитектуры и функционала.
**ВСЕ задачи выполнены.** Полная синхронизация Entity.status ↔ VacancyApplication.stage.

---

## ОСТАВШИЕСЯ ЗАДАЧИ

**НЕТ ЗАДАЧ** — всё выполнено!

---

## ФАЙЛЫ — ПОЛНАЯ ПОДДЕРЖКА ✅

DocumentParser (`backend/api/services/documents.py`) поддерживает:

| Категория | Форматы |
|-----------|---------|
| Документы | PDF, DOCX, DOC, ODT, RTF, TXT, MD |
| **HTML** | **HTML, HTM** ✅ |
| Таблицы | XLSX, XLS, CSV, ODS |
| Презентации | PPTX, PPT, ODP |
| Изображения (OCR) | JPG, PNG, GIF, WEBP, BMP, TIFF, HEIC |
| Архивы | ZIP, RAR, 7Z |
| Прочее | JSON, XML, YAML, EML, MSG |

Все файлы автоматически парсятся и отправляются в AI ассистент Entity.

---

## ВЫПОЛНЕННЫЕ ЗАДАЧИ ✅

### Безопасность
- ✅ JWT secret из переменных окружения
- ✅ Superadmin password из переменных окружения
- ✅ CORS ограничен production доменами
- ✅ Rate Limiting на auth endpoints
- ✅ Brute-force protection
- ✅ Token invalidation при смене пароля
- ✅ Токен в Authorization header (не в querystring)
- ✅ rehype-sanitize для XSS защиты
- ✅ localStorage утилита с try-catch

### Архитектура Backend
- ✅ Bare except → конкретные исключения + logging
- ✅ Циклические импорты исправлены
- ✅ Database URL утилита (`utils/db_url.py`)
- ✅ Thread safety для глобального состояния
- ✅ Role mapping утилита (`utils/roles.py`)
- ✅ Dead code удалён

### Архитектура Frontend
- ✅ api.ts разбит на модули (7 файлов)
- ✅ WebSocket discriminated unions
- ✅ Memory leaks исправлены (isMounted, cleanup)
- ✅ useReducer для больших компонентов
- ✅ Error Boundary добавлен
- ✅ Naming conventions унифицированы

### Функционал от Alex
- ✅ База кандидатов с отдельной вкладкой
- ✅ Контроль доступа (feature flags)
- ✅ Вкладка "База" в Вакансиях
- ✅ Поддержка ВСЕХ файлов (DOCX, ZIP, HTML, PDF и др.)
- ✅ AI извлекает инфо из файлов
- ✅ Kanban drag & drop работает
- ✅ Enum синхронизация исправлена (PR #410, #411)

### База данных
- ✅ Индексы на часто используемых полях
- ✅ UNIQUE constraints добавлены
- ✅ Cascade delete настроен
- ✅ Entity.status синхронизация исправлена

### Синхронизация Entity.status ↔ VacancyApplication.stage (ПОЛНАЯ)
- ✅ PUT /entities/{id} → sync to application.stage
- ✅ PATCH /entities/{id}/status → sync to application.stage
- ✅ PUT /applications/{id} → sync to entity.status
- ✅ POST /applications/bulk-move → sync to entity.status
- ✅ POST /{vacancy_id}/applications → uses entity.status as initial stage
- ✅ POST /entities/{id}/apply-to-vacancy → one-vacancy restriction + sync
- ✅ DELETE /applications/{id} → reset entity.status to 'new'
- ✅ vacancy_recommender.auto_apply → sync entity.status
- ✅ Double-click защита во всех UI компонентах

---

## ИСТОРИЯ PR

| PR | Описание | Статус |
|----|----------|--------|
| #400 | Критические баги безопасности | ✅ Merged |
| #402 | Архитектурный рефакторинг | ✅ Merged |
| #408 | WebSocket Type Safety | ✅ Merged |
| #409 | KanbanBoard useReducer | ✅ Merged |
| #410 | Entity.status sync fix | ✅ Merged |
| #411 | Merge to main | ✅ Merged |

---

## DEPLOYMENT

- **Production:** https://hr-bot-production-c613.up.railway.app
- **Branch:** main (auto-deploy)
- **Last deploy:** 18 января 2026, ~23:00 MSK

---

*Проект полностью готов к production использованию.*
