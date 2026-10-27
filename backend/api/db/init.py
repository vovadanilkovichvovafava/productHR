"""
Database initialization module.

This module handles all database initialization logic including:
- Running migrations
- Adding enum values
- Creating tables
- Setting up default data
"""

import asyncio
import logging
from pathlib import Path

from sqlalchemy import text

from api.utils.db_url import get_sync_database_url
from api.db.migrations import (
    ENUM_DEFINITIONS,
    CHATTYPE_VALUES,
    ROLE_ENUM_VALUES,
    HR_PIPELINE_STAGES,
    CREATE_CALL_RECORDINGS_SQL,
    CALL_RECORDINGS_INDEXES,
    COLUMN_MIGRATIONS,
    CREATE_ENTITY_AI_CONVERSATIONS_SQL,
    ENTITY_AI_CONVERSATIONS_INDEXES,
    CREATE_ENTITY_ANALYSES_SQL,
    ENTITY_ANALYSES_INDEXES,
    CREATE_ORGANIZATIONS_SQL,
    CREATE_ORG_MEMBERS_SQL,
    ORG_MEMBERS_INDEXES,
    MULTI_TENANCY_COLUMNS,
    SMART_CONTEXT_COLUMNS,
    CREATE_DEPARTMENTS_SQL,
    CREATE_DEPARTMENT_MEMBERS_SQL,
    DEPARTMENT_INDEXES,
    DEPARTMENT_COLUMNS,
    ENTITY_TRANSFERS_COLUMNS,
    ENTITY_TRACKING_COLUMNS,
    CREATE_INVITATIONS_SQL,
    INVITATIONS_INDEXES,
    CREATE_VACANCYSTATUS_ENUM,
    CREATE_APPLICATIONSTAGE_ENUM,
    APPLICATIONSTAGE_VALUES,
    CREATE_VACANCIES_SQL,
    VACANCIES_INDEXES,
    CREATE_VACANCY_APPLICATIONS_SQL,
    VACANCY_APPLICATIONS_INDEXES,
    CREATE_ENTITYFILETYPE_ENUM,
    CREATE_ENTITY_FILES_SQL,
    ENTITY_FILES_INDEXES,
    CREATE_DEPARTMENT_FEATURES_SQL,
    DEPARTMENT_FEATURES_INDEXES,
    ROLE_CONVERSIONS,
    SHARED_ACCESS_COLUMNS,
    SHARED_ACCESS_CALL_ID,
    SHARED_ACCESS_VACANCY_ID,
    ENTITY_FILES_ORG_ID,
    ENTITY_TAG_ARCHIVED_AT,
    ENTITY_TAG_COLOR_WIDTH,
    ENTITY_TAG_KIND,
    ENTITY_TAG_SHOW_AT_NAME,
    CREATE_ORG_UNITS_SQL,
    ORG_UNITS_INDEXES,
    EMPLOYEE_ORG_UNIT_COLUMN,
    EMPLOYEE_MANAGER_COLUMN,
)

logger = logging.getLogger("hr-analyzer")


async def run_migration(engine, sql: str, description: str):
    """Run a single migration in its own transaction."""
    try:
        async with engine.begin() as conn:
            await conn.execute(text(sql))
        logger.info(f"Migration OK: {description}")
        return True
    except Exception as e:
        logger.warning(f"Migration failed ({description}): {e}")
        return False


def add_enum_value_sync(enum_name: str, value: str, description: str):
    """Add a value to an existing enum type using psycopg2 with autocommit.

    PostgreSQL requires ALTER TYPE ADD VALUE to run outside of a transaction block.
    We use synchronous psycopg2 with autocommit=True to ensure no transaction wrapping.
    """
    import psycopg2

    try:
        # Get sync database URL for psycopg2
        db_url = get_sync_database_url()

        # Connect with autocommit enabled
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        try:
            cur = conn.cursor()
            cur.execute(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{value}'")
            cur.close()
            logger.info(f"Enum value OK: {description}")
            return True
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"Enum value failed ({description}): {e}")
        return False


async def add_enum_value(engine, enum_name: str, value: str, description: str):
    """Async wrapper for add_enum_value_sync - runs in executor to not block event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, add_enum_value_sync, enum_name, value, description)


async def init_database():
    """Initialize database with separate transactions for each migration."""
    from api.database import engine, AsyncSessionLocal
    from api.models.database import Base
    from api.services.auth import create_superadmin_if_not_exists

    logger.info("=== DATABASE INITIALIZATION START ===")

    # Step 1: Create enum types (each in separate transaction)
    for enum_name, values in ENUM_DEFINITIONS:
        values_str = ', '.join([f"'{v}'" for v in values])
        await run_migration(engine, f"CREATE TYPE {enum_name} AS ENUM ({values_str})", f"Create {enum_name} enum")

    # Step 2: Add enum values to chattype (each in separate transaction)
    for value in CHATTYPE_VALUES:
        await run_migration(engine, f"ALTER TYPE chattype ADD VALUE IF NOT EXISTS '{value}'", f"Add {value} to chattype")

    # Step 2.1: Add sub_admin to role enums (critical for sandbox - moved here to ensure it runs early)
    await run_migration(engine, "ALTER TYPE deptrole ADD VALUE IF NOT EXISTS 'sub_admin'", "Add sub_admin to deptrole enum")
    await run_migration(engine, "ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'sub_admin'", "Add sub_admin to userrole enum")

    # Step 2.2: Add lowercase role values to userrole enum (for migration)
    for role_val in ROLE_ENUM_VALUES:
        await run_migration(engine, f"ALTER TYPE userrole ADD VALUE IF NOT EXISTS '{role_val}'", f"Add {role_val} to userrole enum")

    # Step 2.3: Add HR pipeline stages to entitystatus enum (for Entity.status sync)
    for status_val in HR_PIPELINE_STAGES:
        await run_migration(engine, f"ALTER TYPE entitystatus ADD VALUE IF NOT EXISTS '{status_val}'", f"Add {status_val} to entitystatus enum")

    # Step 2.4: Add archival/terminal statuses present in EntityStatus model but
    # missing from the original PG enum (withdrawn = candidate withdrew, reserve =
    # imported/archived candidates e.g. ClickUp backlog). Without this the enum
    # drifts from the model and INSERTs crash with "invalid input value for enum".
    for status_val in ('withdrawn', 'reserve'):
        await run_migration(engine, f"ALTER TYPE entitystatus ADD VALUE IF NOT EXISTS '{status_val}'", f"Add {status_val} to entitystatus enum")

    # Step 3: Create all tables
    logger.info("Creating tables with create_all...")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Tables created successfully")
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        return

    # Step 3.0: КОЛОНКИ, БЕЗ КОТОРЫХ ПАДАЕТ ВЕСЬ HR-РАЗДЕЛ.
    # create_all выше заводит только недостающие ТАБЛИЦЫ, колонки в уже
    # существующих он не добавляет. 28.09.2026 из-за этого лёг прод: код с
    # vacancy_applications.pinned_entry_key уехал, а колонки не было — SELECT по
    # заявкам валился с UndefinedColumnError, и карточка кандидата, смена этапа
    # и лента перестали работать у всех. ALTER-ы были в start.sh, но в самом
    # конце общего блока: любая ошибка выше — и до них дело не доходило.
    # Здесь каждый идёт своей транзакцией (run_migration), поэтому сосед по
    # списку упасть им не мешает.
    for sql, description in (
        ("ALTER TABLE stage_transitions ADD COLUMN IF NOT EXISTS edited_at TIMESTAMP",
         "stage_transitions.edited_at"),
        ("ALTER TABLE stage_transitions ADD COLUMN IF NOT EXISTS edited_by INTEGER "
         "REFERENCES users(id) ON DELETE SET NULL",
         "stage_transitions.edited_by"),
        ("ALTER TABLE vacancy_applications ADD COLUMN IF NOT EXISTS pinned_entry_key VARCHAR(64)",
         "vacancy_applications.pinned_entry_key"),
        # Скоуп наблюдателя по воронкам (01.10.2026): пусто = ограничения нет,
        # поэтому для всех существующих участников поведение не меняется.
        ("ALTER TABLE org_members ADD COLUMN IF NOT EXISTS scope_vacancy_ids JSON",
         "org_members.scope_vacancy_ids"),
        # Задачи из чата (25.09.2026, соседняя ветка работ). Их ALTER-ы лежали
        # в том же хвосте start.sh и на прод не доехали: 28.09 проверка
        # SCHEMA_DRIFT показала, что колонок нет, хотя модель их требует —
        # значит, запросы к задачам падали так же, как вчера падали заявки.
        # Сами таблицы спаслись через create_all, колонки в существующих — нет.
        ("ALTER TABLE project_tasks ADD COLUMN IF NOT EXISTS created_by_bot BOOLEAN DEFAULT false",
         "project_tasks.created_by_bot"),
        ("CREATE INDEX IF NOT EXISTS ix_project_tasks_created_by_bot ON project_tasks (created_by_bot)",
         "индекс project_tasks.created_by_bot"),
        ("ALTER TABLE project_tasks ADD COLUMN IF NOT EXISTS source_chat_id BIGINT",
         "project_tasks.source_chat_id"),
        ("ALTER TABLE project_tasks ADD COLUMN IF NOT EXISTS source_message TEXT",
         "project_tasks.source_message"),
        # Иерархия и видимость отделов доски (30.09.2026): песочницы —
        # родительские, команды — дочерние; юниты видны не всем.
        ("ALTER TABLE staff_board_departments ADD COLUMN IF NOT EXISTS kind VARCHAR(10) DEFAULT 'team'",
         "staff_board_departments.kind"),
        ("ALTER TABLE staff_board_departments ADD COLUMN IF NOT EXISTS parent_id INTEGER "
         "REFERENCES staff_board_departments(id) ON DELETE SET NULL",
         "staff_board_departments.parent_id"),
        ("ALTER TABLE staff_board_departments ADD COLUMN IF NOT EXISTS visibility VARCHAR(10) DEFAULT 'all'",
         "staff_board_departments.visibility"),
        ("ALTER TABLE staff_board_departments ADD COLUMN IF NOT EXISTS visible_to JSON DEFAULT '[]'",
         "staff_board_departments.visible_to"),
        # Назначения: человек в отделе. Строка доски = назначение, поэтому без
        # таблицы доска не открывается вообще — заводим её здесь, не надеясь
        # на create_all.
        ("""CREATE TABLE IF NOT EXISTS staff_board_placements (
                id SERIAL PRIMARY KEY,
                org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                department_id INTEGER NOT NULL REFERENCES staff_board_departments(id) ON DELETE CASCADE,
                extra JSON DEFAULT '{}',
                created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT uq_placement_entity_dept UNIQUE (entity_id, department_id)
            )""", "Create staff_board_placements table"),
        ("CREATE INDEX IF NOT EXISTS ix_staff_board_placements_org_id ON staff_board_placements (org_id)",
         "индекс staff_board_placements.org_id"),
        ("CREATE INDEX IF NOT EXISTS ix_staff_board_placements_entity_id ON staff_board_placements (entity_id)",
         "индекс staff_board_placements.entity_id"),
        ("CREATE INDEX IF NOT EXISTS ix_staff_board_placements_department_id ON staff_board_placements (department_id)",
         "индекс staff_board_placements.department_id"),
        # Личные наборы секций доски (07.10.2026): у каждого свой и для каждой
        # вкладки свой. Нет записи — показываем все секции.
        ("""CREATE TABLE IF NOT EXISTS staff_board_status_views (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                scope_key VARCHAR(32) NOT NULL,
                org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                statuses JSON DEFAULT '[]',
                updated_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (user_id, scope_key)
            )""", "Create staff_board_status_views table"),
        ("CREATE INDEX IF NOT EXISTS ix_staff_board_status_views_org_id ON staff_board_status_views (org_id)",
         "индекс staff_board_status_views.org_id"),
        # Личный набор КОЛОНОК (08.10.2026) — рядом с набором секций.
        ("ALTER TABLE staff_board_status_views ADD COLUMN IF NOT EXISTS column_keys JSON DEFAULT '[]'",
         "staff_board_status_views.column_keys"),
        # Вопросы анкеты на момент ответа (20.10.2026): правка шаблона больше не
        # переписывает подписи в старых ответах и не прячет ответы на удалённые
        # вопросы. Пусто у старых ответов — для них берутся поля шаблона.
        ("ALTER TABLE form_submissions ADD COLUMN IF NOT EXISTS fields_snapshot JSON",
         "form_submissions.fields_snapshot"),
        # Корзина и для «Удалить с воронки» (21.10.2026): что удалено, из какой
        # воронки, чей был кандидат и на каком этапе.
        ("ALTER TABLE deleted_entities ADD COLUMN IF NOT EXISTS kind VARCHAR(20) DEFAULT 'entity'",
         "deleted_entities.kind"),
        ("ALTER TABLE deleted_entities ADD COLUMN IF NOT EXISTS vacancy_id INTEGER",
         "deleted_entities.vacancy_id"),
        ("ALTER TABLE deleted_entities ADD COLUMN IF NOT EXISTS vacancy_title VARCHAR(500)",
         "deleted_entities.vacancy_title"),
        ("ALTER TABLE deleted_entities ADD COLUMN IF NOT EXISTS owner_name VARCHAR(255)",
         "deleted_entities.owner_name"),
        ("ALTER TABLE deleted_entities ADD COLUMN IF NOT EXISTS stage VARCHAR(50)",
         "deleted_entities.stage"),
    ):
        await run_migration(engine, sql, description)

    # Step 3.1: Convert existing uppercase role values to lowercase (critical fix)
    for sql, description in ROLE_CONVERSIONS:
        await run_migration(engine, sql, description)

    # Step 3.2: Add 'vacancy' to resourcetype enum (needed for vacancy sharing)
    await add_enum_value(engine, "resourcetype", "vacancy", "Add vacancy to resourcetype enum")

    # Step 3.3: Add foreign key columns to shared_access for proper cascade delete (critical for sandbox)
    for sql, description in SHARED_ACCESS_COLUMNS:
        await run_migration(engine, sql, description)

    # Step 3.4: Add vacancy_id to shared_access EARLY (critical for vacancy sharing/deletion)
    # This runs early because vacancies table already exists in production
    await run_migration(engine, SHARED_ACCESS_VACANCY_ID[0], SHARED_ACCESS_VACANCY_ID[1])

    # Step 4: Create call_recordings table if not exists (preserves existing data)
    logger.info("=== SETTING UP call_recordings TABLE ===")
    await run_migration(engine, CREATE_CALL_RECORDINGS_SQL, "Create call_recordings table")

    # Create indexes
    for sql, description in CALL_RECORDINGS_INDEXES:
        await run_migration(engine, sql, description)

    logger.info("=== call_recordings TABLE READY ===")

    # Step 4.1: Now add call_id to shared_access (requires call_recordings to exist)
    await run_migration(engine, SHARED_ACCESS_CALL_ID[0], SHARED_ACCESS_CALL_ID[1])

    # Step 5: Other column migrations
    for sql, description in COLUMN_MIGRATIONS:
        await run_migration(engine, sql, description)

    # Entity AI tables
    await run_migration(engine, CREATE_ENTITY_AI_CONVERSATIONS_SQL, "Create entity_ai_conversations table")
    for sql, description in ENTITY_AI_CONVERSATIONS_INDEXES:
        await run_migration(engine, sql, description)

    await run_migration(engine, CREATE_ENTITY_ANALYSES_SQL, "Create entity_analyses table")
    for sql, description in ENTITY_ANALYSES_INDEXES:
        await run_migration(engine, sql, description)

    # Step 6: Multi-tenancy - Organizations
    logger.info("=== SETTING UP MULTI-TENANCY ===")

    # Create enums for organizations
    await run_migration(engine, "CREATE TYPE orgrole AS ENUM ('owner', 'admin', 'member')", "Create orgrole enum")
    await run_migration(engine, "CREATE TYPE subscriptionplan AS ENUM ('free', 'pro', 'enterprise')", "Create subscriptionplan enum")

    # Create organizations table
    await run_migration(engine, CREATE_ORGANIZATIONS_SQL, "Create organizations table")
    await run_migration(engine, "CREATE INDEX IF NOT EXISTS ix_organizations_slug ON organizations(slug)", "Index organizations.slug")

    # Create org_members table
    await run_migration(engine, CREATE_ORG_MEMBERS_SQL, "Create org_members table")
    for sql, description in ORG_MEMBERS_INDEXES:
        await run_migration(engine, sql, description)

    # Add org_id to existing tables
    for sql, description in MULTI_TENANCY_COLUMNS:
        await run_migration(engine, sql, description)

    # Smart context fields for AI analysis
    for sql, description in SMART_CONTEXT_COLUMNS:
        await run_migration(engine, sql, description)

    logger.info("=== MULTI-TENANCY TABLES READY ===")

    # Step 8: Departments
    logger.info("=== SETTING UP DEPARTMENTS ===")

    # Create deptrole enum
    await run_migration(engine, "CREATE TYPE deptrole AS ENUM ('lead', 'member')", "Create deptrole enum")

    # Create departments table
    await run_migration(engine, CREATE_DEPARTMENTS_SQL, "Create departments table")
    await run_migration(engine, CREATE_DEPARTMENT_MEMBERS_SQL, "Create department_members table")
    for sql, description in DEPARTMENT_INDEXES:
        await run_migration(engine, sql, description)

    # Department additional columns
    for sql, description in DEPARTMENT_COLUMNS:
        await run_migration(engine, sql, description)

    # Entity transfers columns
    for sql, description in ENTITY_TRANSFERS_COLUMNS:
        await run_migration(engine, sql, description)

    logger.info("=== DEPARTMENTS TABLES READY ===")

    # Entity transfer tracking columns
    for sql, description in ENTITY_TRACKING_COLUMNS:
        await run_migration(engine, sql, description)

    # Step 8.5: Org units (HR org chart) — изолированная HR-структура
    logger.info("=== SETTING UP ORG UNITS ===")
    await run_migration(engine, CREATE_ORG_UNITS_SQL, "Create org_units table")
    for sql, description in ORG_UNITS_INDEXES:
        await run_migration(engine, sql, description)
    for sql, description in EMPLOYEE_ORG_UNIT_COLUMN:
        await run_migration(engine, sql, description)
    for sql, description in EMPLOYEE_MANAGER_COLUMN:
        await run_migration(engine, sql, description)
    logger.info("=== ORG UNITS READY ===")

    # Step 8: Invitations table
    logger.info("=== SETTING UP INVITATIONS ===")
    await run_migration(engine, CREATE_INVITATIONS_SQL, "Create invitations table")
    for sql, description in INVITATIONS_INDEXES:
        await run_migration(engine, sql, description)

    logger.info("=== INVITATIONS TABLE READY ===")

    # Step 9: Vacancies and Kanban pipeline
    logger.info("=== SETTING UP VACANCIES ===")

    # Create vacancy status enum
    await run_migration(engine, CREATE_VACANCYSTATUS_ENUM, "Create vacancystatus enum")

    # Create application stage enum
    await run_migration(engine, CREATE_APPLICATIONSTAGE_ENUM, "Create applicationstage enum")

    # Add HR Pipeline stages to applicationstage enum (MUST use autocommit - no transaction)
    for value in APPLICATIONSTAGE_VALUES:
        await add_enum_value(engine, "applicationstage", value, f"Add {value} to applicationstage enum")

    # Create vacancies table
    await run_migration(engine, CREATE_VACANCIES_SQL, "Create vacancies table")
    for sql, description in VACANCIES_INDEXES:
        await run_migration(engine, sql, description)

    # Create vacancy_applications table
    await run_migration(engine, CREATE_VACANCY_APPLICATIONS_SQL, "Create vacancy_applications table")
    for sql, description in VACANCY_APPLICATIONS_INDEXES:
        await run_migration(engine, sql, description)

    # Add vacancy_id to shared_access (requires vacancies table to exist)
    await run_migration(engine, SHARED_ACCESS_VACANCY_ID[0], SHARED_ACCESS_VACANCY_ID[1])

    logger.info("=== VACANCIES TABLES READY ===")

    # Step 10: Entity files for document attachments
    logger.info("=== SETTING UP ENTITY FILES ===")

    # Create entity file type enum
    await run_migration(engine, CREATE_ENTITYFILETYPE_ENUM, "Create entityfiletype enum")

    # Create entity_files table
    await run_migration(engine, CREATE_ENTITY_FILES_SQL, "Create entity_files table")
    for sql, description in ENTITY_FILES_INDEXES:
        await run_migration(engine, sql, description)

    # Add org_id column if table exists but column doesn't (for existing deployments)
    await run_migration(engine, ENTITY_FILES_ORG_ID[0], ENTITY_FILES_ORG_ID[1])
    await run_migration(engine, ENTITY_TAG_ARCHIVED_AT[0], ENTITY_TAG_ARCHIVED_AT[1])
    await run_migration(engine, ENTITY_TAG_COLOR_WIDTH[0], ENTITY_TAG_COLOR_WIDTH[1])
    await run_migration(engine, ENTITY_TAG_KIND[0], ENTITY_TAG_KIND[1])
    await run_migration(engine, ENTITY_TAG_SHOW_AT_NAME[0], ENTITY_TAG_SHOW_AT_NAME[1])

    logger.info("=== ENTITY FILES TABLE READY ===")

    # Step 11: Department Features for feature access control
    logger.info("=== SETTING UP DEPARTMENT FEATURES ===")

    # Create department_features table
    await run_migration(engine, CREATE_DEPARTMENT_FEATURES_SQL, "Create department_features table")
    for sql, description in DEPARTMENT_FEATURES_INDEXES:
        await run_migration(engine, sql, description)

    logger.info("=== DEPARTMENT FEATURES TABLE READY ===")

    # Step 11.1: Enable vacancies feature org-wide by default for all organizations
    logger.info("=== ENABLING VACANCIES FEATURE ===")
    try:
        async with engine.begin() as conn:
            # Get all organization IDs
            orgs_result = await conn.execute(text("SELECT id FROM organizations"))
            org_ids = [row[0] for row in orgs_result.fetchall()]

            for org_id in org_ids:
                # Check if vacancies feature already exists for this org (org-wide setting)
                check_result = await conn.execute(
                    text("""
                        SELECT id FROM department_features
                        WHERE org_id = :org_id
                        AND feature_name = 'vacancies'
                        AND department_id IS NULL
                    """),
                    {"org_id": org_id}
                )
                existing = check_result.fetchone()

                if not existing:
                    # Enable vacancies org-wide
                    await conn.execute(
                        text("""
                            INSERT INTO department_features (org_id, department_id, feature_name, enabled, created_at, updated_at)
                            VALUES (:org_id, NULL, 'vacancies', TRUE, NOW(), NOW())
                        """),
                        {"org_id": org_id}
                    )
                    logger.info(f"Enabled vacancies feature for org_id={org_id}")

        logger.info("=== VACANCIES FEATURE ENABLED ===")
    except Exception as e:
        logger.warning(f"Enable vacancies feature: {e}")

    # Step 12: Create superadmin and default organization
    try:
        async with AsyncSessionLocal() as db:
            await create_superadmin_if_not_exists(db)
    except Exception as e:
        logger.warning(f"Superadmin creation: {e}")

    # Step 12: Fix chats with NULL org_id - assign them to the default organization
    logger.info("=== FIXING CHATS WITH NULL ORG_ID ===")
    try:
        async with engine.begin() as conn:
            # Get the first organization (default org)
            result = await conn.execute(text("SELECT id FROM organizations ORDER BY id LIMIT 1"))
            org_row = result.fetchone()
            if org_row:
                default_org_id = org_row[0]
                # Update all chats with NULL org_id
                update_result = await conn.execute(
                    text("UPDATE chats SET org_id = :org_id WHERE org_id IS NULL"),
                    {"org_id": default_org_id}
                )
                logger.info(f"Updated {update_result.rowcount} chats with NULL org_id to org_id={default_org_id}")

                # Also update entities and call_recordings with NULL org_id
                await conn.execute(
                    text("UPDATE entities SET org_id = :org_id WHERE org_id IS NULL"),
                    {"org_id": default_org_id}
                )
                await conn.execute(
                    text("UPDATE call_recordings SET org_id = :org_id WHERE org_id IS NULL"),
                    {"org_id": default_org_id}
                )
    except Exception as e:
        logger.warning(f"Fix NULL org_id: {e}")

    # Теги у ФИО отделены от меток, метки — только сорсеры (21.09.2026), см.
    # services/tags_split.py. Прежний бэкафилл extra_data.headline_tags →
    # метки снят: на проде он давно отработал (всё уже в связях show_at_name,
    # которые этот шаг и переносит), а на каждом старте он возвращал к имени
    # теги, которые рекрутёр оттуда убрал, и воскрешал бы удалённые метки-слова.
    # Некритичен: упасть из-за него старт не должен.
    try:
        from ..services.tags_split import split_tags_and_labels
        from ..database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await split_tags_and_labels(session)
    except Exception as e:
        logger.warning(f"Tags/labels split failed (non-critical): {e}")

    # Решения «разные люди» из extra_data.dismissed_duplicate_ids → таблица
    # duplicate_pair_decisions (22.09.2026, services/duplicate_decisions.py).
    # Одноразово (отметка в data_migration_marks); сбой старт не роняет —
    # старые списки ещё читаются как запасной источник.
    try:
        from ..services.duplicate_decisions import import_legacy_once
        from ..database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await import_legacy_once(session)
    except Exception as e:
        logger.warning(f"Duplicate decisions legacy import failed (non-critical): {e}")

    # support@rabota.by и прочие служебные ящики — не почта кандидата (22.09.2026,
    # services/service_email_cleanup.py). Одноразово, с пересчётом плашек дублей.
    try:
        from ..services.service_email_cleanup import remove_service_emails_once
        from ..database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await remove_service_emails_once(session)
    except Exception as e:
        logger.warning(f"Service email cleanup failed (non-critical): {e}")

    # Пометки дубля на удалённые (влитые) карточки — разово снять (22.10.2026,
    # services/duplicate_flags.py); при открытии карточки дубль найдётся заново.
    try:
        from ..services.duplicate_flags import clear_dangling_once
        from ..database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await clear_dangling_once(session)
    except Exception as e:
        logger.warning(f"Dangling duplicate flags cleanup failed (non-critical): {e}")

    # hh_b2b и прочие каналы порталов в telegram_usernames — одноразово (22.09.2026).
    try:
        from ..services.service_email_cleanup import remove_junk_telegram_once
        from ..database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await remove_junk_telegram_once(session)
    except Exception as e:
        logger.warning(f"Junk telegram cleanup failed (non-critical): {e}")

    # Отдел из карточки → назначения на доске «Статусы» (30.09.2026,
    # services/board_placements.py). Одноразово: строки доски теперь строятся
    # по назначениям, и без переноса у всех, кто уже стоял в отделе, отдел
    # пропал бы из таблицы. Старые ключи в extra_data остаются на месте.
    try:
        from ..services.board_placements import migrate_board_departments_once
        from ..database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await migrate_board_departments_once(session)
    except Exception as e:
        logger.warning(f"Board placements migration failed (non-critical): {e}")

    # Журнал действий: строки старше года — удалить (services/audit.py).
    try:
        from ..services.audit import purge_old
        from ..database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            removed = await purge_old(session)
            await session.commit()
            if removed:
                logger.info(f"AUDIT purge: удалено старых строк журнала: {removed}")
    except Exception as e:
        logger.warning(f"Audit purge failed (non-critical): {e}")

    # Заявки людей, которых доска «Штат» перевела в отдел, не сдвинув заявку
    # с «Практики» (20.10.2026, services/board_stage_sync.py). Одноразово.
    try:
        from ..services.board_stage_sync import sync_transferred_applications_once
        from ..database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await sync_transferred_applications_once(session)
    except Exception as e:
        logger.warning(f"Board stage sync failed (non-critical): {e}")

    # Даты отдела собрать в одном месте — у рабочего назначения (13.10.2026,
    # services/board_placements.py). Одноразово: до этого они лежали у каждого
    # назначения своими, и на вкладках у человека выходили разные даты.
    try:
        from ..services.board_placements import merge_team_dates_once
        from ..database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await merge_team_dates_once(session)
    except Exception as e:
        logger.warning(f"Board team dates merge failed (non-critical): {e}")

    # Метка «HR: Имя» в карточке для уже назначенных на доске (20.10.2026,
    # services/board_placements.py). Одноразово: PATCH доски пишет её сам, но у
    # тех, кому HR поставили раньше, в карточке её нет.
    try:
        from ..services.board_placements import backfill_board_hr_tags_once
        from ..database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await backfill_board_hr_tags_once(session)
    except Exception as e:
        logger.warning(f"Board HR tags backfill failed (non-critical): {e}")

    # Контакты из шапки уже сохранённых резюме (22.09.2026) — одноразово.
    try:
        from ..services.resume_contacts import backfill_resume_contacts_once
        from ..database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await backfill_resume_contacts_once(session)
    except Exception as e:
        logger.warning(f"Resume contacts backfill failed (non-critical): {e}")

    # Последним шагом сверяем модели с базой: если какая-то колонка так и не
    # доехала, это видно в логе деплоя сразу, а не по жалобам рекрутёров.
    await check_schema_drift(engine)

    logger.info("=== DATABASE INITIALIZATION COMPLETE ===")


async def check_schema_drift(engine) -> list[str]:
    """Сверить колонки моделей с тем, что реально есть в базе.

    28.09.2026: код с новой колонкой уехал на прод, а колонки в базе не
    оказалось — SQLAlchemy перечисляет ВСЕ поля модели в каждом SELECT, поэтому
    любой запрос к заявкам падал целиком, и у рекрутёров перестали открываться
    карточки и двигаться кандидаты. В логе деплоя при этом было тихо.

    Теперь при старте пишем явное «в таблице X нет колонок: …» с маркером
    SCHEMA_DRIFT. Ничего не чиним и не роняем приложение: задача — чтобы такая
    рассинхронизация была видна в логе деплоя, а не в чате с рекрутёрами.
    """
    from api.models.database import Base

    missing: list[str] = []
    try:
        async with engine.begin() as conn:
            rows = await conn.execute(text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public'"
            ))
            actual: dict[str, set[str]] = {}
            for table_name, column_name in rows:
                actual.setdefault(table_name, set()).add(column_name)

        for table in Base.metadata.sorted_tables:
            have = actual.get(table.name)
            # Таблицы вообще нет — это другой случай (её заводит create_all),
            # и отдельная строка в логе тут только зашумит.
            if not have:
                continue
            gone = [c.name for c in table.columns if c.name not in have]
            if gone:
                missing.append(f"{table.name}: {', '.join(sorted(gone))}")

        if missing:
            for row in missing:
                logger.error("SCHEMA_DRIFT: в базе нет колонок — %s", row)
            logger.error(
                "SCHEMA_DRIFT: таблиц с расхождением — %s. Запросы к ним будут "
                "падать целиком (UndefinedColumnError), пока колонки не заведут.",
                len(missing),
            )
        else:
            logger.info("SCHEMA_DRIFT: расхождений нет, все колонки моделей есть в базе")
    except Exception as e:
        logger.warning(f"SCHEMA_DRIFT: проверку выполнить не удалось: {e}")
    return missing


def run_alembic_migrations_sync():
    """Run Alembic migrations synchronously on startup."""
    import subprocess

    backend_dir = Path(__file__).parent.parent.parent

    try:
        # First try 'head' (single head expected)
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=backend_dir,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            logger.info("Alembic migrations applied successfully")
            if result.stdout:
                for line in result.stdout.strip().split('\n'):
                    if line:
                        logger.info(f"  {line}")
        elif "Multiple head" in result.stderr:
            # Fallback: if multiple heads, try 'heads' to apply all
            logger.warning("Multiple Alembic heads detected, trying 'heads'...")
            result = subprocess.run(
                ["alembic", "upgrade", "heads"],
                cwd=backend_dir,
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode == 0:
                logger.info("Alembic migrations applied (multiple heads)")
            else:
                logger.error(f"Alembic: {result.stderr or 'unknown error'}")
        else:
            logger.warning(f"Alembic: {result.stderr or 'unknown error'}")
    except FileNotFoundError:
        logger.warning("Alembic not found in PATH, skipping migrations")
    except subprocess.TimeoutExpired:
        logger.error("Alembic migration timed out")
    except Exception as e:
        logger.warning(f"Alembic migration skipped: {e}")

    # Safety net: ensure critical columns exist even if migration failed
    _ensure_critical_columns()


def _ensure_critical_columns():
    """Ensure critical columns exist in the database, even if alembic migration failed."""
    import psycopg2
    try:
        db_url = get_sync_database_url()
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur = conn.cursor()
        for table, column, col_type in [
            ("vacancies", "custom_stages", "JSONB"),
            ("vacancies", "kanban_card_fields", "JSONB"),
            ("vacancy_applications", "interview_summary", "TEXT"),
            ("vacancy_applications", "compatibility_score", "JSONB"),
            ("vacancy_applications", "created_by", "INTEGER"),
            ("vacancy_applications", "stage_order", "INTEGER DEFAULT 0"),
        ]:
            cur.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name=%s AND column_name=%s",
                (table, column)
            )
            if not cur.fetchone():
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                logger.info(f"Safety net: added {column} column to {table}")
        cur.close()
        conn.close()
    except Exception as e:
        logger.warning(f"Safety net column check failed: {e}")
