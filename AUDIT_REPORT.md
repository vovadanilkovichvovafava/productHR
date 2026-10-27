# ПОЛНЫЙ АУДИТ HR-BOT ПРОЕКТА

**Дата**: 2025-12-23
**Версия проекта**: Commit 8209a3b

---

## ОБЩАЯ СТАТИСТИКА

| Категория | Critical | High | Medium | Low | Всего |
|-----------|----------|------|--------|-----|-------|
| Бэкенд API | 2 | 5 | 6 | 4 | 17 |
| Фронтенд | 2 | 5 | 8 | 10 | 25 |
| База данных | 2 | 12 | 14 | 5 | 33 |
| Бизнес-логика | 3 | 5 | 4 | 0 | 12 |
| **ИТОГО** | **9** | **27** | **32** | **19** | **87** |

---

## КРИТИЧЕСКИЕ ПРОБЛЕМЫ (ТРЕБУЮТ НЕМЕДЛЕННОГО ИСПРАВЛЕНИЯ)

### 1. HARDCODED SECRETS
**Файл:** `backend/api/config.py:16,56`
```python
jwt_secret = "change-me-in-production"
superadmin_password = "changeme"
```
**Риск:** Любой, кто видит код, может получить доступ к системе.

### 2. UNDEFINED VARIABLE (RUNTIME ERROR)
**Файл:** `backend/api/routes/departments.py:293`
```python
members_count=1 if data.parent_id and not is_admin else 0,  # is_admin не определена!
```
**Риск:** NameError при создании департамента.

### 3. XSS УЯЗВИМОСТЬ - TOKEN В LOCALSTORAGE
**Файл:** `frontend/src/services/api.ts:16-22`, `frontend/src/stores/authStore.ts:16`
**Риск:** Любой XSS скрипт может украсть JWT токен.

### 4. CROSS-ORG SHARING (SECURITY HOLE)
**Файл:** `backend/api/routes/sharing.py:147-164`
```python
# Проверяется только существование пользователя, НЕ его организация!
result = await db.execute(select(User).where(User.id == data.shared_with_id))
```
**Риск:** Утечка данных между организациями.

### 5. N+1 QUERIES (PERFORMANCE CRITICAL)
**Файлы:**
- `backend/api/routes/chats.py:161-169` - для каждого чата 3 запроса
- `backend/api/routes/departments.py:176-192` - для каждого отдела 3 запроса
- `backend/api/routes/sharing.py:261-264` - для каждого share 2 запроса

**Риск:** При 100 записях = 300+ запросов к БД.

---

## БЭКЕНД: ВСЕ ПРОБЛЕМЫ

### Безопасность

| # | Проблема | Файл:Строка | Критичность |
|---|----------|-------------|-------------|
| 1 | Hardcoded JWT secret | config.py:16 | **CRITICAL** |
| 2 | Hardcoded superadmin password | config.py:56 | **CRITICAL** |
| 3 | CORS Allow All Origins с credentials | main.py:374 | HIGH |
| 4 | Отсутствие Rate Limiting на auth | routes/auth.py:19-35 | HIGH |
| 5 | Отсутствие brute-force protection | services/auth.py:127-132 | HIGH |
| 6 | Отсутствие валидации сложности пароля | routes/auth.py:64-75 | MEDIUM |
| 7 | Hardcoded Telegram bot username | routes/invitations.py:365 | MEDIUM |
| 8 | f-string в SQL миграциях | main.py:70 | MEDIUM |

### API Проблемы

| # | Проблема | Файл:Строка | Критичность |
|---|----------|-------------|-------------|
| 9 | Undefined variable is_admin | routes/departments.py:293 | **CRITICAL** |
| 10 | Missing input validation on search | routes/chats.py:84 | MEDIUM |
| 11 | Отсутствие обработки ошибок | routes/entities.py | MEDIUM |
| 12 | Inconsistent pagination | routes/* | LOW |

### Производительность

| # | Проблема | Файл:Строка | Критичность |
|---|----------|-------------|-------------|
| 13 | N+1 queries в departments | routes/departments.py:176-192 | HIGH |
| 14 | N+1 queries в sharing | routes/sharing.py:261-264 | HIGH |
| 15 | N+1 queries в users list | routes/users.py:28-33 | MEDIUM |

### Архитектура

| # | Проблема | Файл:Строка | Критичность |
|---|----------|-------------|-------------|
| 16 | Дублирование database URL conversion | database.py + bot.py | MEDIUM |
| 17 | Wildcard import в models/__init__.py | models/__init__.py:5 | LOW |

---

## ФРОНТЕНД: ВСЕ ПРОБЛЕМЫ

### Безопасность

| # | Проблема | Файл:Строка | Критичность |
|---|----------|-------------|-------------|
| 1 | Token в localStorage (XSS) | services/api.ts:16-22 | **CRITICAL** |
| 2 | CSRF уязвимость в API interceptor | services/api.ts:24-33 | **CRITICAL** |
| 3 | Утечка данных в console.error | stores/*.ts | MEDIUM |

### Производительность

| # | Проблема | Файл:Строка | Критичность |
|---|----------|-------------|-------------|
| 4 | Memory leak в polling (setInterval) | stores/callStore.ts:166-201 | HIGH |
| 5 | N+1 problem в DepartmentsPage | pages/DepartmentsPage.tsx:81-92 | HIGH |
| 6 | Чрезмерный рефетч (staleTime: 5s) | main.tsx:10-18 | HIGH |
| 7 | refetchOnMount: 'always' везде | pages/*.tsx | MEDIUM |
| 8 | Отсутствие виртуализации списков | pages/ContactsPage.tsx:290 | MEDIUM |
| 9 | Дублирование streaming логики | services/api.ts:169-265 | LOW |

### Типизация

| # | Проблема | Файл:Строка | Критичность |
|---|----------|-------------|-------------|
| 10 | Использование any типов | pages/LoginPage.tsx:27, UsersPage.tsx:97 | MEDIUM |
| 11 | Отсутствие типизации responses | services/api.ts:143 | MEDIUM |

### State Management

| # | Проблема | Файл:Строка | Критичность |
|---|----------|-------------|-------------|
| 12 | Неправильная зависимость useEffect | App.tsx:55 | HIGH |
| 13 | Race condition в entityStore | stores/entityStore.ts:45-61 | LOW |
| 14 | Отсутствие cleanup в stopRecording | stores/callStore.ts:101-111 | MEDIUM |
| 15 | Нет error state в chatStore | stores/chatStore.ts:4-16 | MEDIUM |

### UX Проблемы

| # | Проблема | Файл:Строка | Критичность |
|---|----------|-------------|-------------|
| 16 | Слабая валидация пароля (min 6) | pages/InvitePage.tsx:52 | MEDIUM |
| 17 | Отсутствие валидации email | pages/LoginPage.tsx:74 | LOW |
| 18 | Нет loading states при delete | pages/ContactsPage.tsx:140-152 | LOW |
| 19 | Нет уведомления при session expired | services/api.ts:24-33 | MEDIUM |

### Архитектура

| # | Проблема | Файл:Строка | Критичность |
|---|----------|-------------|-------------|
| 20 | God Components (1000+ строк) | pages/UsersPage.tsx, DepartmentsPage.tsx | MEDIUM |
| 21 | Дублирование modal логики | pages/DepartmentsPage.tsx:425-673 | LOW |
| 22 | Отсутствие Error Boundary | весь проект | HIGH |
| 23 | Отсутствие Loading Skeleton | весь проект | LOW |
| 24 | Плохая организация папок | src/ | LOW |
| 25 | Отсутствие custom hooks | весь проект | LOW |

---

## БАЗА ДАННЫХ: ВСЕ ПРОБЛЕМЫ

### Производительность (N+1 Queries)

| # | Проблема | Файл:Строка | Критичность |
|---|----------|-------------|-------------|
| 1 | N+1 в get_chats | routes/chats.py:161-169 | **CRITICAL** |
| 2 | N+1 в get_deleted_chats | routes/chats.py:408-411 | **CRITICAL** |

### Отсутствующие индексы

| # | Поле | Файл:Строка | Критичность |
|---|------|-------------|-------------|
| 3 | Organization.name | models/database.py:109 | HIGH |
| 4 | Department.name | models/database.py:147 | HIGH |
| 5 | Entity.name, Entity.email | models/database.py:315,318 | HIGH |
| 6 | User.name | models/database.py:181 | HIGH |
| 7 | Message.content_type | models/database.py:234 | MEDIUM |

### Cascade Delete проблемы

| # | Relationship | Файл:Строка | Критичность |
|---|--------------|-------------|-------------|
| 8 | Organization.entities | models/database.py:119 | HIGH |
| 9 | Organization.chats | models/database.py:120 | HIGH |
| 10 | Organization.calls | models/database.py:121 | HIGH |
| 11 | Entity.calls | models/database.py:332 | HIGH |

### Отсутствующие UNIQUE constraints

| # | Таблица | Поля | Критичность |
|---|---------|------|-------------|
| 12 | OrgMember | (org_id, user_id) | HIGH |
| 13 | DepartmentMember | (department_id, user_id) | HIGH |
| 14 | SharedAccess | (resource_type, resource_id, shared_with_id, shared_by_id) | HIGH |

### FK Constraints

| # | Проблема | Файл:Строка | Критичность |
|---|----------|-------------|-------------|
| 15 | AnalysisHistory.user_id без ondelete | models/database.py:295 | HIGH |

### Pydantic Schemas

| # | Проблема | Файл:Строка | Критичность |
|---|----------|-------------|-------------|
| 16 | telegram_id может overflow int32 | schemas.py:52 | HIGH |
| 17 | CriterionItem.weight без валидации 1-10 | schemas.py:150-154 | MEDIUM |
| 18 | report_type как str вместо Enum | schemas.py:218 | MEDIUM |
| 19 | password без валидации сложности | schemas.py:70 | MEDIUM |
| 20 | chat_type как str вместо Enum | schemas.py:90 | MEDIUM |
| 21 | role как str вместо Enum | schemas.py:51 | MEDIUM |

### Конфигурация

| # | Проблема | Файл:Строка | Критичность |
|---|----------|-------------|-------------|
| 22 | expire_on_commit=False (stale data) | database.py:23 | MEDIUM |
| 23 | Отсутствие Alembic миграций | database.py:35-37 | HIGH |

### Lazy Loading

| # | Проблема | Файл:Строка | Критичность |
|---|----------|-------------|-------------|
| 24 | Missing selectinload для inviter | routes/organizations.py:181-195 | MEDIUM |

### JSON Columns

| # | Проблема | Файл:Строка | Критичность |
|---|----------|-------------|-------------|
| 25 | document_metadata без структуры | models/database.py:239 | MEDIUM |
| 26 | Entity.tags default=list | models/database.py:322 | LOW |

### Отношения без back_populates

| # | Relationship | Файл:Строка | Критичность |
|---|--------------|-------------|-------------|
| 27 | OrgMember.inviter | models/database.py:137 | LOW |
| 28 | ReportSubscription.user | models/database.py:401 | LOW |
| 29 | EntityAIConversation.user | models/database.py:416 | LOW |
| 30 | EntityAnalysis.user | models/database.py:432 | LOW |

---

## БИЗНЕС-ЛОГИКА: ВСЕ ПРОБЛЕМЫ

### Права доступа

| # | Проблема | Файл:Строка | Критичность |
|---|----------|-------------|-------------|
| 1 | Cross-org sharing не проверяется | routes/sharing.py:147-164 | **CRITICAL** |
| 2 | Admin может приглашать других admins | routes/organizations.py:254-256 | HIGH |
| 3 | Entity transfer без проверки org | routes/entities.py:330-360 | HIGH |

### Race Conditions

| # | Проблема | Файл:Строка | Критичность |
|---|----------|-------------|-------------|
| 4 | Race condition при удалении user | routes/organizations.py:395-401 | **CRITICAL** |
| 5 | Race condition в accept_invitation | routes/invitations.py:315-358 | MEDIUM |

### Data Integrity

| # | Проблема | Файл:Строка | Критичность |
|---|----------|-------------|-------------|
| 6 | Orphan ReportSubscription при удалении user | routes/organizations.py:403-425 | MEDIUM |
| 7 | Orphan EntityAIConversation при удалении | routes/users.py:139-156 | MEDIUM |
| 8 | Несогласованность при invite existing user | routes/organizations.py:224-236 | HIGH |

### Runtime Errors

| # | Проблема | Файл:Строка | Критичность |
|---|----------|-------------|-------------|
| 9 | NameError: is_admin not defined | routes/departments.py:293 | **CRITICAL** |

### Edge Cases

| # | Проблема | Файл:Строка | Критичность |
|---|----------|-------------|-------------|
| 10 | Можно удалить себя как последнего lead | routes/departments.py:635-644 | HIGH |
| 11 | Отсутствие проверки cascade при delete org | models/database.py:117-121 | MEDIUM |

---

## ПРИОРИТИЗИРОВАННЫЙ ПЛАН ИСПРАВЛЕНИЯ

### ФАЗА 1: КРИТИЧЕСКИЕ (1-2 дня)

1. **Удалить hardcoded secrets** - `config.py:16,56`
2. **Исправить undefined variable** - `departments.py:293` (is_admin → is_owner)
3. **Добавить проверку организации в sharing** - `sharing.py:147-164`
4. **Перенести token в httpOnly cookie** - api.ts, authStore.ts
5. **Ограничить CORS origins** - `main.py:374`

### ФАЗА 2: ВЫСОКИЙ ПРИОРИТЕТ (3-5 дней)

6. **Исправить N+1 queries** - departments.py, sharing.py, chats.py
7. **Добавить Rate Limiting на auth** - auth.py
8. **Добавить Error Boundary** - React
9. **Исправить memory leak в polling** - callStore.ts
10. **Добавить UNIQUE constraints** - OrgMember, DepartmentMember, SharedAccess
11. **Добавить cascade delete** - Organization relationships
12. **Добавить индексы** - name поля
13. **Исправить useEffect зависимости** - App.tsx

### ФАЗА 3: СРЕДНИЙ ПРИОРИТЕТ (1-2 недели)

14. **Добавить валидацию паролей** - схемы и формы
15. **Добавить brute-force protection** - auth
16. **Оптимизировать рефетч стратегию** - staleTime, refetchOnMount
17. **Разделить God Components** - UsersPage, DepartmentsPage
18. **Добавить Alembic миграции** - database
19. **Исправить типизацию (убрать any)** - pages, stores
20. **Добавить Enum валидацию** - Pydantic schemas

### ФАЗА 4: УЛУЧШЕНИЯ (ongoing)

21. Рефакторить дублирующийся код
22. Добавить custom hooks
23. Добавить Skeleton UI
24. Реструктурировать папки
25. Добавить виртуализацию списков
26. Добавить back_populates к отношениям
27. Документировать модели

---

## КОМАНДЫ ДЛЯ ПРОВЕРКИ

```bash
# Найти все any типы
grep -rn ": any" frontend/src/

# Найти все console.log/error
grep -rn "console\." frontend/src/

# Найти N+1 паттерны (for + await db.execute)
grep -B2 -A2 "for.*in.*:" backend/api/routes/ | grep -A2 "await db.execute"

# Найти отсутствующие индексы
grep -n "Column.*nullable" backend/api/models/database.py | grep -v "index=True"

# Проверить CORS настройки
grep -n "allow_origins" backend/main.py
```

---

## ЗАКЛЮЧЕНИЕ

Проект имеет **87 проблем**, из которых **9 критических**. Основные области риска:
1. **Безопасность** - hardcoded secrets, CORS, XSS через localStorage
2. **Производительность** - N+1 queries могут убить production
3. **Data Integrity** - отсутствие constraints, orphan records
4. **Права доступа** - cross-org sharing, неправильные проверки ролей

Рекомендуется начать с Фазы 1 (критические проблемы) немедленно.
