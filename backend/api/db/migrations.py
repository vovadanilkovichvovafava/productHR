"""
Database migration definitions.

This module contains all SQL migrations for the HR Analyzer application.
Migrations are defined as dictionaries with SQL and description for each step.
"""

# Enum type definitions
ENUM_DEFINITIONS = [
    ("entitytype", ['candidate', 'client', 'contractor', 'lead', 'partner', 'custom']),
    ("entitystatus", ['new', 'screening', 'interview', 'offer', 'hired', 'rejected', 'active', 'paused', 'churned', 'converted', 'ended', 'negotiation']),
    ("callsource", ['meet', 'zoom', 'teams', 'upload', 'telegram']),
    ("callstatus", ['pending', 'connecting', 'recording', 'processing', 'transcribing', 'analyzing', 'done', 'failed']),
    ("reporttype", ['daily_hr', 'weekly_summary', 'daily_calls', 'weekly_pipeline']),
    ("deliverymethod", ['telegram', 'email'])
]

# Chattype enum values to add
CHATTYPE_VALUES = ['work', 'hr', 'project', 'client', 'contractor', 'sales', 'support', 'custom']

# Role enum values to add
ROLE_ENUM_VALUES = ['superadmin', 'admin', 'sub_admin']

# HR pipeline stages for entitystatus enum
HR_PIPELINE_STAGES = ['practice', 'tech_practice', 'is_interview']

# Create call_recordings table SQL
CREATE_CALL_RECORDINGS_SQL = """
    CREATE TABLE IF NOT EXISTS call_recordings (
        id SERIAL PRIMARY KEY,
        title VARCHAR(255),
        entity_id INTEGER REFERENCES entities(id) ON DELETE SET NULL,
        owner_id INTEGER REFERENCES users(id),
        source_type callsource NOT NULL,
        source_url VARCHAR(500),
        bot_name VARCHAR(100) DEFAULT 'HR Recorder',
        status callstatus DEFAULT 'pending',
        duration_seconds INTEGER,
        audio_file_path VARCHAR(500),
        fireflies_transcript_id VARCHAR(100),
        transcript TEXT,
        speakers JSONB,
        summary TEXT,
        action_items JSONB,
        key_points JSONB,
        error_message TEXT,
        created_at TIMESTAMP DEFAULT NOW(),
        started_at TIMESTAMP,
        ended_at TIMESTAMP,
        processed_at TIMESTAMP
    )
"""

# Call recordings indexes
CALL_RECORDINGS_INDEXES = [
    ("CREATE INDEX IF NOT EXISTS ix_call_recordings_entity_id ON call_recordings(entity_id)", "Index entity_id"),
    ("CREATE INDEX IF NOT EXISTS ix_call_recordings_owner_id ON call_recordings(owner_id)", "Index owner_id"),
    ("CREATE INDEX IF NOT EXISTS ix_call_recordings_status ON call_recordings(status)", "Index status"),
    ("CREATE INDEX IF NOT EXISTS ix_call_recordings_fireflies_transcript_id ON call_recordings(fireflies_transcript_id)", "Index fireflies_transcript_id"),
]

# Column migrations for various tables
COLUMN_MIGRATIONS = [
    # API tokens for external integrations (Claude MCP, etc.)
    (
        """CREATE TABLE IF NOT EXISTS api_tokens (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(80) NOT NULL,
            token_hash VARCHAR(64) UNIQUE NOT NULL,
            prefix VARCHAR(12) NOT NULL,
            last_used_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT now()
        )""",
        "Create api_tokens table"
    ),
    ("CREATE INDEX IF NOT EXISTS ix_api_tokens_user_id ON api_tokens(user_id)", "Index api_tokens.user_id"),
    ("CREATE INDEX IF NOT EXISTS ix_api_tokens_token_hash ON api_tokens(token_hash)", "Index api_tokens.token_hash"),

    # Fireflies integration migrations
    ("ALTER TYPE callsource ADD VALUE IF NOT EXISTS 'teams'", "Add teams to callsource enum"),
    ("ALTER TYPE callsource ADD VALUE IF NOT EXISTS 'fireflies'", "Add fireflies to callsource enum"),

    # External links integration migrations
    ("ALTER TYPE callsource ADD VALUE IF NOT EXISTS 'google_doc'", "Add google_doc to callsource enum"),
    ("ALTER TYPE callsource ADD VALUE IF NOT EXISTS 'google_drive'", "Add google_drive to callsource enum"),
    ("ALTER TYPE callsource ADD VALUE IF NOT EXISTS 'direct_url'", "Add direct_url to callsource enum"),
    ("ALTER TABLE call_recordings ADD COLUMN IF NOT EXISTS fireflies_transcript_id VARCHAR(100)", "Add fireflies_transcript_id"),
    ("CREATE INDEX IF NOT EXISTS ix_call_recordings_fireflies_transcript_id ON call_recordings(fireflies_transcript_id)", "Index fireflies_transcript_id on existing table"),

    # Progress tracking for long-running processing
    ("ALTER TABLE call_recordings ADD COLUMN IF NOT EXISTS progress INTEGER DEFAULT 0", "Add progress to call_recordings"),
    ("ALTER TABLE call_recordings ADD COLUMN IF NOT EXISTS progress_stage VARCHAR(100)", "Add progress_stage to call_recordings"),

    # Chats table migrations
    ("ALTER TABLE chats ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP", "Add deleted_at to chats"),
    ("CREATE INDEX IF NOT EXISTS ix_chats_deleted_at ON chats(deleted_at)", "Index chats.deleted_at"),
    ("ALTER TABLE chats ADD COLUMN IF NOT EXISTS entity_id INTEGER REFERENCES entities(id) ON DELETE SET NULL", "Add entity_id to chats"),
    ("CREATE INDEX IF NOT EXISTS ix_chats_entity_id ON chats(entity_id)", "Index chats.entity_id"),

    # Messages table migrations
    ("ALTER TABLE messages ADD COLUMN IF NOT EXISTS file_path VARCHAR(512)", "Add file_path to messages"),
    ("ALTER TABLE messages ADD COLUMN IF NOT EXISTS is_imported BOOLEAN DEFAULT FALSE", "Add is_imported to messages"),

    # Analysis history migrations
    ("ALTER TABLE analysis_history ADD COLUMN IF NOT EXISTS entity_id INTEGER REFERENCES entities(id) ON DELETE SET NULL", "Add entity_id to analysis_history"),

    # User security columns
    ("ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER DEFAULT 0", "Add token_version to users"),
    ("ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER DEFAULT 0", "Add failed_login_attempts to users"),
    ("ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP", "Add locked_until to users"),

    # User profile additional contact identifiers
    ("ALTER TABLE users ADD COLUMN IF NOT EXISTS additional_emails JSONB DEFAULT '[]'::jsonb", "Add additional_emails to users"),
    ("ALTER TABLE users ADD COLUMN IF NOT EXISTS additional_telegram_usernames JSONB DEFAULT '[]'::jsonb", "Add additional_telegram_usernames to users"),

    # Embedding columns for similarity search (pgvector)
    ("ALTER TABLE entities ADD COLUMN IF NOT EXISTS embedding_updated_at TIMESTAMP", "Add embedding_updated_at to entities"),
    ("ALTER TABLE vacancies ADD COLUMN IF NOT EXISTS embedding_updated_at TIMESTAMP", "Add embedding_updated_at to vacancies"),

    # Task attachments — храним содержимое файла в БД (Railway /tmp эфемерный,
    # стирается при редеплое → скрины в комментариях пропадали).
    ("ALTER TABLE task_attachments ADD COLUMN IF NOT EXISTS file_data BYTEA", "Add file_data to task_attachments"),
    ("ALTER TABLE task_attachments ALTER COLUMN storage_path DROP NOT NULL", "task_attachments.storage_path nullable"),

    # «Наблюдатель» — read-only набор прав поверх роли (менторам): видит всё, но
    # любые изменения запрещены (не-GET запросы → 403 в get_current_user).
    ("ALTER TABLE org_members ADD COLUMN IF NOT EXISTS is_readonly BOOLEAN DEFAULT FALSE NOT NULL", "Add is_readonly to org_members"),
]

# Entity AI conversations table
CREATE_ENTITY_AI_CONVERSATIONS_SQL = """
    CREATE TABLE IF NOT EXISTS entity_ai_conversations (
        id SERIAL PRIMARY KEY,
        entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id),
        messages JSONB DEFAULT '[]'::jsonb,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )
"""

ENTITY_AI_CONVERSATIONS_INDEXES = [
    ("CREATE INDEX IF NOT EXISTS ix_entity_ai_conversations_entity_id ON entity_ai_conversations(entity_id)", "Index entity_ai_conversations.entity_id"),
    ("CREATE INDEX IF NOT EXISTS ix_entity_ai_conversations_user_id ON entity_ai_conversations(user_id)", "Index entity_ai_conversations.user_id"),
]

# Entity analyses table
CREATE_ENTITY_ANALYSES_SQL = """
    CREATE TABLE IF NOT EXISTS entity_analyses (
        id SERIAL PRIMARY KEY,
        entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id),
        analysis_type VARCHAR(50),
        result TEXT NOT NULL,
        scores JSONB DEFAULT '{}'::jsonb,
        created_at TIMESTAMP DEFAULT NOW()
    )
"""

ENTITY_ANALYSES_INDEXES = [
    ("CREATE INDEX IF NOT EXISTS ix_entity_analyses_entity_id ON entity_analyses(entity_id)", "Index entity_analyses.entity_id"),
]

# Organizations table
CREATE_ORGANIZATIONS_SQL = """
    CREATE TABLE IF NOT EXISTS organizations (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        slug VARCHAR(100) UNIQUE NOT NULL,
        subscription_plan subscriptionplan DEFAULT 'free',
        settings JSONB DEFAULT '{}'::jsonb,
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )
"""

# Org members table
CREATE_ORG_MEMBERS_SQL = """
    CREATE TABLE IF NOT EXISTS org_members (
        id SERIAL PRIMARY KEY,
        org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role orgrole DEFAULT 'member',
        invited_by INTEGER REFERENCES users(id),
        created_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(org_id, user_id)
    )
"""

ORG_MEMBERS_INDEXES = [
    ("CREATE INDEX IF NOT EXISTS ix_org_members_org_id ON org_members(org_id)", "Index org_members.org_id"),
    ("CREATE INDEX IF NOT EXISTS ix_org_members_user_id ON org_members(user_id)", "Index org_members.user_id"),
]

# Multi-tenancy column additions
MULTI_TENANCY_COLUMNS = [
    ("ALTER TABLE chats ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE", "Add org_id to chats"),
    ("CREATE INDEX IF NOT EXISTS ix_chats_org_id ON chats(org_id)", "Index chats.org_id"),
    ("ALTER TABLE entities ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE", "Add org_id to entities"),
    ("CREATE INDEX IF NOT EXISTS ix_entities_org_id ON entities(org_id)", "Index entities.org_id"),
    ("ALTER TABLE call_recordings ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE", "Add org_id to call_recordings"),
    ("CREATE INDEX IF NOT EXISTS ix_call_recordings_org_id ON call_recordings(org_id)", "Index call_recordings.org_id"),
]

# Smart context fields for AI analysis
SMART_CONTEXT_COLUMNS = [
    ("ALTER TABLE call_recordings ADD COLUMN IF NOT EXISTS participant_roles JSONB DEFAULT '{}'::jsonb", "Add participant_roles to call_recordings"),
    ("ALTER TABLE call_recordings ADD COLUMN IF NOT EXISTS speaker_stats JSONB DEFAULT '{}'::jsonb", "Add speaker_stats to call_recordings"),
    ("ALTER TABLE call_recordings ADD COLUMN IF NOT EXISTS segments JSONB DEFAULT '[]'::jsonb", "Add segments to call_recordings"),
    ("CREATE UNIQUE INDEX IF NOT EXISTS ix_call_recordings_org_source_url ON call_recordings(org_id, source_url) WHERE source_url IS NOT NULL", "Unique index on call_recordings(org_id, source_url)"),
]

# Departments table
CREATE_DEPARTMENTS_SQL = """
    CREATE TABLE IF NOT EXISTS departments (
        id SERIAL PRIMARY KEY,
        org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        name VARCHAR(255) NOT NULL,
        description TEXT,
        color VARCHAR(20),
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )
"""

# Department members table
CREATE_DEPARTMENT_MEMBERS_SQL = """
    CREATE TABLE IF NOT EXISTS department_members (
        id SERIAL PRIMARY KEY,
        department_id INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role deptrole DEFAULT 'member',
        created_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(department_id, user_id)
    )
"""

DEPARTMENT_INDEXES = [
    ("CREATE INDEX IF NOT EXISTS ix_departments_org_id ON departments(org_id)", "Index departments.org_id"),
    ("CREATE INDEX IF NOT EXISTS ix_department_members_department_id ON department_members(department_id)", "Index department_members.department_id"),
    ("CREATE INDEX IF NOT EXISTS ix_department_members_user_id ON department_members(user_id)", "Index department_members.user_id"),
]

# Department additional columns
DEPARTMENT_COLUMNS = [
    ("ALTER TABLE departments ADD COLUMN IF NOT EXISTS parent_id INTEGER REFERENCES departments(id) ON DELETE CASCADE", "Add parent_id to departments"),
    ("CREATE INDEX IF NOT EXISTS ix_departments_parent_id ON departments(parent_id)", "Index departments.parent_id"),
    ("ALTER TABLE entities ADD COLUMN IF NOT EXISTS department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL", "Add department_id to entities"),
    ("CREATE INDEX IF NOT EXISTS ix_entities_department_id ON entities(department_id)", "Index entities.department_id"),
]

# Entity transfers columns
ENTITY_TRANSFERS_COLUMNS = [
    ("ALTER TABLE entity_transfers ADD COLUMN IF NOT EXISTS from_department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL", "Add from_department_id to entity_transfers"),
    ("ALTER TABLE entity_transfers ADD COLUMN IF NOT EXISTS to_department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL", "Add to_department_id to entity_transfers"),
    ("CREATE INDEX IF NOT EXISTS ix_entity_transfers_from_department_id ON entity_transfers(from_department_id)", "Index entity_transfers.from_department_id"),
    ("CREATE INDEX IF NOT EXISTS ix_entity_transfers_to_department_id ON entity_transfers(to_department_id)", "Index entity_transfers.to_department_id"),
    ("ALTER TABLE entity_transfers ADD COLUMN IF NOT EXISTS copy_entity_id INTEGER REFERENCES entities(id) ON DELETE SET NULL", "Add copy_entity_id to entity_transfers"),
    ("ALTER TABLE entity_transfers ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMP", "Add cancelled_at to entity_transfers"),
    ("ALTER TABLE entity_transfers ADD COLUMN IF NOT EXISTS cancel_deadline TIMESTAMP", "Add cancel_deadline to entity_transfers"),
]

# Entity tracking columns
ENTITY_TRACKING_COLUMNS = [
    ("ALTER TABLE entities ADD COLUMN IF NOT EXISTS is_transferred BOOLEAN DEFAULT FALSE", "Add is_transferred to entities"),
    ("CREATE INDEX IF NOT EXISTS ix_entities_is_transferred ON entities(is_transferred)", "Index entities.is_transferred"),
    ("ALTER TABLE entities ADD COLUMN IF NOT EXISTS transferred_to_id INTEGER REFERENCES users(id) ON DELETE SET NULL", "Add transferred_to_id to entities"),
    ("ALTER TABLE entities ADD COLUMN IF NOT EXISTS transferred_at TIMESTAMP", "Add transferred_at to entities"),
    ("ALTER TABLE entities ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1", "Add version to entities"),
]

# Invitations table
CREATE_INVITATIONS_SQL = """
    CREATE TABLE IF NOT EXISTS invitations (
        id SERIAL PRIMARY KEY,
        token VARCHAR(64) UNIQUE NOT NULL,
        org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        email VARCHAR(255),
        name VARCHAR(255),
        org_role orgrole DEFAULT 'member',
        department_ids JSONB DEFAULT '[]'::jsonb,
        invited_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        expires_at TIMESTAMP,
        used_at TIMESTAMP,
        used_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMP DEFAULT NOW()
    )
"""

INVITATIONS_INDEXES = [
    ("CREATE INDEX IF NOT EXISTS ix_invitations_token ON invitations(token)", "Index invitations.token"),
    ("CREATE INDEX IF NOT EXISTS ix_invitations_org_id ON invitations(org_id)", "Index invitations.org_id"),
]

# Vacancy status enum (with IF NOT EXISTS workaround)
CREATE_VACANCYSTATUS_ENUM = """
    DO $$ BEGIN
        CREATE TYPE vacancystatus AS ENUM ('draft', 'open', 'paused', 'closed', 'cancelled');
    EXCEPTION
        WHEN duplicate_object THEN null;
    END $$
"""

# Application stage enum
CREATE_APPLICATIONSTAGE_ENUM = """
    DO $$ BEGIN
        CREATE TYPE applicationstage AS ENUM ('applied', 'screening', 'phone_screen', 'interview', 'assessment', 'offer', 'hired', 'rejected', 'withdrawn');
    EXCEPTION
        WHEN duplicate_object THEN null;
    END $$
"""

# Application stage additional values (must use autocommit)
APPLICATIONSTAGE_VALUES = ['new', 'practice', 'tech_practice', 'is_interview']

# Vacancies table
CREATE_VACANCIES_SQL = """
    CREATE TABLE IF NOT EXISTS vacancies (
        id SERIAL PRIMARY KEY,
        org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
        department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
        title VARCHAR(255) NOT NULL,
        description TEXT,
        requirements TEXT,
        responsibilities TEXT,
        salary_min INTEGER,
        salary_max INTEGER,
        salary_currency VARCHAR(10) DEFAULT 'RUB',
        location VARCHAR(255),
        employment_type VARCHAR(50),
        experience_level VARCHAR(50),
        status vacancystatus DEFAULT 'draft',
        priority INTEGER DEFAULT 0,
        tags JSONB DEFAULT '[]'::jsonb,
        extra_data JSONB DEFAULT '{}'::jsonb,
        hiring_manager_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        published_at TIMESTAMP,
        closes_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )
"""

VACANCIES_INDEXES = [
    ("CREATE INDEX IF NOT EXISTS ix_vacancies_org_id ON vacancies(org_id)", "Index vacancies.org_id"),
    ("CREATE INDEX IF NOT EXISTS ix_vacancies_department_id ON vacancies(department_id)", "Index vacancies.department_id"),
    ("CREATE INDEX IF NOT EXISTS ix_vacancies_status ON vacancies(status)", "Index vacancies.status"),
    ("CREATE INDEX IF NOT EXISTS ix_vacancies_title ON vacancies(title)", "Index vacancies.title"),
]

# Vacancy applications table
CREATE_VACANCY_APPLICATIONS_SQL = """
    CREATE TABLE IF NOT EXISTS vacancy_applications (
        id SERIAL PRIMARY KEY,
        vacancy_id INTEGER NOT NULL REFERENCES vacancies(id) ON DELETE CASCADE,
        entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
        stage applicationstage DEFAULT 'applied',
        stage_order INTEGER DEFAULT 0,
        rating INTEGER,
        notes TEXT,
        rejection_reason VARCHAR(255),
        source VARCHAR(100),
        next_interview_at TIMESTAMP,
        applied_at TIMESTAMP DEFAULT NOW(),
        last_stage_change_at TIMESTAMP DEFAULT NOW(),
        created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        updated_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(vacancy_id, entity_id)
    )
"""

VACANCY_APPLICATIONS_INDEXES = [
    ("CREATE INDEX IF NOT EXISTS ix_vacancy_applications_vacancy_id ON vacancy_applications(vacancy_id)", "Index vacancy_applications.vacancy_id"),
    ("CREATE INDEX IF NOT EXISTS ix_vacancy_applications_entity_id ON vacancy_applications(entity_id)", "Index vacancy_applications.entity_id"),
    ("CREATE INDEX IF NOT EXISTS ix_vacancy_applications_stage ON vacancy_applications(stage)", "Index vacancy_applications.stage"),
    ("CREATE INDEX IF NOT EXISTS ix_vacancy_application_stage ON vacancy_applications(vacancy_id, stage)", "Index vacancy_applications(vacancy_id, stage)"),
]

# Entity file type enum
CREATE_ENTITYFILETYPE_ENUM = """
    DO $$ BEGIN
        CREATE TYPE entityfiletype AS ENUM ('resume', 'cover_letter', 'test_assignment', 'certificate', 'portfolio', 'other');
    EXCEPTION
        WHEN duplicate_object THEN null;
    END $$
"""

# Entity files table
CREATE_ENTITY_FILES_SQL = """
    CREATE TABLE IF NOT EXISTS entity_files (
        id SERIAL PRIMARY KEY,
        entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
        org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        file_type entityfiletype DEFAULT 'other',
        file_name VARCHAR(255) NOT NULL,
        file_path VARCHAR(512) NOT NULL,
        file_size INTEGER,
        mime_type VARCHAR(100),
        description VARCHAR(500),
        uploaded_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMP DEFAULT NOW()
    )
"""

ENTITY_FILES_INDEXES = [
    ("CREATE INDEX IF NOT EXISTS ix_entity_files_entity_id ON entity_files(entity_id)", "Index entity_files.entity_id"),
    ("CREATE INDEX IF NOT EXISTS ix_entity_files_org_id ON entity_files(org_id)", "Index entity_files.org_id"),
]

# Department features table
CREATE_DEPARTMENT_FEATURES_SQL = """
    CREATE TABLE IF NOT EXISTS department_features (
        id SERIAL PRIMARY KEY,
        org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        department_id INTEGER REFERENCES departments(id) ON DELETE CASCADE,
        feature_name VARCHAR(50) NOT NULL,
        enabled BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(org_id, department_id, feature_name)
    )
"""

DEPARTMENT_FEATURES_INDEXES = [
    ("CREATE INDEX IF NOT EXISTS ix_department_features_org_id ON department_features(org_id)", "Index department_features.org_id"),
    ("CREATE INDEX IF NOT EXISTS ix_department_features_lookup ON department_features(org_id, feature_name)", "Index department_features lookup"),
]

# Role conversions (uppercase to lowercase)
ROLE_CONVERSIONS = [
    ("UPDATE users SET role = 'superadmin' WHERE role::text = 'SUPERADMIN'", "Convert SUPERADMIN to superadmin"),
    ("UPDATE users SET role = 'admin' WHERE role::text = 'ADMIN'", "Convert ADMIN to admin"),
    ("UPDATE users SET role = 'sub_admin' WHERE role::text = 'SUB_ADMIN'", "Convert SUB_ADMIN to sub_admin"),
]

# Shared access columns (cascade delete support)
SHARED_ACCESS_COLUMNS = [
    ("ALTER TABLE shared_access ADD COLUMN IF NOT EXISTS entity_id INTEGER REFERENCES entities(id) ON DELETE CASCADE", "Add entity_id to shared_access"),
    ("ALTER TABLE shared_access ADD COLUMN IF NOT EXISTS chat_id INTEGER REFERENCES chats(id) ON DELETE CASCADE", "Add chat_id to shared_access"),
]

# Vacancy_id column for shared_access (requires vacancies table to exist)
SHARED_ACCESS_VACANCY_ID = (
    "ALTER TABLE shared_access ADD COLUMN IF NOT EXISTS vacancy_id INTEGER REFERENCES vacancies(id) ON DELETE CASCADE",
    "Add vacancy_id to shared_access"
)

# Call_id column for shared_access (requires call_recordings to exist)
SHARED_ACCESS_CALL_ID = (
    "ALTER TABLE shared_access ADD COLUMN IF NOT EXISTS call_id INTEGER REFERENCES call_recordings(id) ON DELETE CASCADE",
    "Add call_id to shared_access"
)

# Entity files org_id migration
ENTITY_FILES_ORG_ID = (
    "ALTER TABLE entity_files ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE",
    "Add org_id to entity_files"
)

# Метка «уходит из списка», но остаётся у тех кандидатов, кому уже проставлена.
# Настоящий DELETE тут не годится: у entity_tags стоит ondelete=CASCADE, и
# удаление записи справочника молча срывает метку со ВСЕХ карточек. Поэтому
# «удалить за ненадобностью» = archived_at, а связи кандидат↔метка не трогаем.
ENTITY_TAG_ARCHIVED_AT = (
    "ALTER TABLE entity_tags_catalog ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP",
    "Add archived_at to entity_tags_catalog"
)

# color заводили под hex (#3b82f6 — 7 символов), а палитра в интерфейсе шлёт
# CSS-переменные: 'var(--hf-status-purple)' это 23 символа. В VARCHAR(20) лезут
# только «Красный» и «Зелёный», остальные 6 цветов роняли создание метки в 500.
ENTITY_TAG_COLOR_WIDTH = (
    "ALTER TABLE entity_tags_catalog ALTER COLUMN color TYPE VARCHAR(40)",
    "Widen entity_tags_catalog.color to 40"
)

# Тип метки. Для системы «Сорсер Иван», «Срочно» и «Знает английский» были
# неразличимы — просто строки, поэтому отдельную аналитику по сорсерам собрать
# было не из чего. Старые метки становятся 'general', ничего не ломая.
ENTITY_TAG_KIND = (
    "ALTER TABLE entity_tags_catalog ADD COLUMN IF NOT EXISTS kind VARCHAR(20) NOT NULL DEFAULT 'general'",
    "Add kind to entity_tags_catalog"
)

# «Показывать у имени» — ЯРКИЙ ярлык рядом с ФИО кандидата. Флаг стоит на СВЯЗИ
# кандидат↔метка, а не на самой метке: до объединения такие ярлыки жили в
# extra_data.headline_tags конкретного человека («перфомер» у Руслана, а не у
# всех подряд). Повесь мы флаг на справочник — метка, проставленная кому-то
# ещё, тут же вылезла бы у имени у всех, а это не то поведение, что было.
ENTITY_TAG_SHOW_AT_NAME = (
    "ALTER TABLE entity_tags ADD COLUMN IF NOT EXISTS show_at_name BOOLEAN NOT NULL DEFAULT FALSE",
    "Add show_at_name to entity_tags"
)

# ── Org units (HR org chart) — изолировано от рекрутинговых departments ──
CREATE_ORG_UNITS_SQL = """
    CREATE TABLE IF NOT EXISTS org_units (
        id SERIAL PRIMARY KEY,
        org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        parent_id INTEGER REFERENCES org_units(id) ON DELETE CASCADE,
        name VARCHAR(255) NOT NULL,
        color VARCHAR(20),
        sort_order INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT NOW()
    )
"""

ORG_UNITS_INDEXES = [
    ("CREATE INDEX IF NOT EXISTS ix_org_units_org_id ON org_units(org_id)", "Index org_units.org_id"),
    ("CREATE INDEX IF NOT EXISTS ix_org_units_parent_id ON org_units(parent_id)", "Index org_units.parent_id"),
]

EMPLOYEE_ORG_UNIT_COLUMN = [
    ("ALTER TABLE employees ADD COLUMN IF NOT EXISTS org_unit_id INTEGER REFERENCES org_units(id) ON DELETE SET NULL", "Add org_unit_id to employees"),
    ("CREATE INDEX IF NOT EXISTS ix_employees_org_unit_id ON employees(org_unit_id)", "Index employees.org_unit_id"),
]

# Manager (reporting line) for the org chart — self-reference on employees
EMPLOYEE_MANAGER_COLUMN = [
    ("ALTER TABLE employees ADD COLUMN IF NOT EXISTS manager_id INTEGER REFERENCES employees(id) ON DELETE SET NULL", "Add manager_id to employees"),
    ("CREATE INDEX IF NOT EXISTS ix_employees_manager_id ON employees(manager_id)", "Index employees.manager_id"),
]
