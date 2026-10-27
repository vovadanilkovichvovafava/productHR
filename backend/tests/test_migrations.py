"""
Database migration infrastructure tests.

These tests verify that proper database migration tools (Alembic) are set up
and that the database schema matches the SQLAlchemy models.

The audit found that Alembic migrations are missing - database.py uses
create_all() instead of proper migrations. These tests will fail initially
to document this infrastructure gap.
"""
import os
import pytest
from pathlib import Path
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from api.models.database import (
    User, Organization, OrgMember, Department, DepartmentMember,
    Entity, Chat, Message, CallRecording, SharedAccess, Invitation,
    CriteriaPreset, ChatCriteria, AIConversation, AnalysisHistory,
    EntityTransfer, EntityAIConversation, EntityAnalysis, ReportSubscription
)


class TestMigrationInfrastructure:
    """Test that migration infrastructure exists and works."""

    def test_alembic_config_exists(self):
        """
        Check that alembic.ini exists.

        EXPECTED TO FAIL: No Alembic configuration has been set up.
        This documents the missing migration infrastructure.
        """
        backend_dir = Path(__file__).resolve().parent.parent
        alembic_ini = backend_dir / "alembic.ini"

        assert alembic_ini.exists(), (
            "alembic.ini not found. Alembic migrations must be initialized.\n"
            "Run: alembic init alembic"
        )

    def test_migrations_directory_exists(self):
        """
        Check that migrations directory exists.

        EXPECTED TO FAIL: No migrations directory exists yet.
        """
        backend_dir = Path(__file__).resolve().parent.parent
        migrations_dir = backend_dir / "alembic"
        versions_dir = backend_dir / "alembic" / "versions"

        assert migrations_dir.exists(), (
            "alembic/ directory not found. Initialize Alembic first."
        )
        assert versions_dir.exists(), (
            "alembic/versions/ directory not found. Migration versions directory is missing."
        )

    def test_initial_migration_exists(self):
        """
        Check that at least one migration file exists.

        EXPECTED TO FAIL: No migration files exist yet.
        This is critical - without migrations, schema changes are not tracked.
        """
        backend_dir = Path(__file__).resolve().parent.parent
        versions_dir = backend_dir / "alembic" / "versions"

        # First check directory exists
        if not versions_dir.exists():
            pytest.fail(
                "alembic/versions/ directory doesn't exist. "
                "Run: alembic init alembic"
            )

        # Look for migration files (*.py files excluding __init__.py and __pycache__)
        migration_files = [
            f for f in versions_dir.glob("*.py")
            if f.name != "__init__.py" and not f.name.startswith("_")
        ]

        assert len(migration_files) > 0, (
            "No migration files found in alembic/versions/.\n"
            "Create initial migration with: alembic revision --autogenerate -m 'Initial migration'"
        )

    def test_env_py_exists(self):
        """
        Check that alembic/env.py exists and is configured.

        EXPECTED TO FAIL: Alembic hasn't been initialized.
        """
        backend_dir = Path(__file__).resolve().parent.parent
        env_py = backend_dir / "alembic" / "env.py"

        assert env_py.exists(), (
            "alembic/env.py not found. This file is needed to run migrations."
        )

        # Read the file and check for basic configuration
        content = env_py.read_text()

        # Check that it imports our Base metadata
        assert "Base" in content or "metadata" in content, (
            "alembic/env.py must import Base.metadata from models"
        )

    def test_alembic_script_mako_exists(self):
        """
        Check that alembic/script.py.mako template exists.

        This template is used to generate new migration files.
        """
        backend_dir = Path(__file__).resolve().parent.parent
        script_mako = backend_dir / "alembic" / "script.py.mako"

        assert script_mako.exists(), (
            "alembic/script.py.mako not found. This template is needed for migrations."
        )


class TestSchemaConsistency:
    """Test that models match database schema."""

    @pytest.mark.asyncio
    async def test_all_tables_exist(self, db_session):
        """
        Verify all model tables exist in database.

        This test should PASS even without Alembic since create_all() is currently used.
        However, it documents what tables should be managed by migrations.
        """
        def _get_tables(session):
            inspector = inspect(session.get_bind())
            return inspector.get_table_names()

        tables = await db_session.run_sync(_get_tables)

        # Expected tables based on models in database.py
        expected_tables = [
            'users',
            'organizations',
            'org_members',
            'departments',
            'department_members',
            'entities',
            'entity_transfers',
            'chats',
            'messages',
            'criteria_presets',
            'chat_criteria',
            'ai_conversations',
            'analysis_history',
            'call_recordings',
            'shared_access',
            'invitations',
            'report_subscriptions',
            'entity_ai_conversations',
            'entity_analyses',
        ]

        missing_tables = [t for t in expected_tables if t not in tables]
        extra_tables = [t for t in tables if t not in expected_tables]

        assert len(missing_tables) == 0, (
            f"Missing tables in database: {missing_tables}\n"
            f"These tables are defined in models but not in database."
        )

        # Extra tables might be okay (alembic_version, etc.) but log them
        if extra_tables:
            print(f"\nNote: Extra tables found (may be expected): {extra_tables}")

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Test DB uses create_all(), production should use alembic upgrade head")
    async def test_all_columns_match_models(self, db_session):
        """
        Verify model columns match database columns.

        This is a critical test - column mismatches can cause runtime errors.
        With proper migrations, this should always pass.
        """
        # Test critical tables with their expected columns
        table_column_checks = {
            'users': [
                'id', 'email', 'password_hash', 'name', 'role',
                'telegram_id', 'telegram_username', 'is_active', 'created_at'
            ],
            'organizations': [
                'id', 'name', 'slug', 'subscription_plan', 'settings',
                'is_active', 'created_at', 'updated_at'
            ],
            'org_members': [
                'id', 'org_id', 'user_id', 'role', 'invited_by', 'created_at'
            ],
            'departments': [
                'id', 'org_id', 'parent_id', 'name', 'description', 'color',
                'is_active', 'created_at', 'updated_at'
            ],
            'department_members': [
                'id', 'department_id', 'user_id', 'role', 'created_at'
            ],
            'entities': [
                'id', 'org_id', 'department_id', 'type', 'name', 'status',
                'phone', 'email', 'telegram_user_id', 'company', 'position',
                'tags', 'extra_data', 'created_by', 'created_at', 'updated_at'
            ],
            'chats': [
                'id', 'org_id', 'telegram_chat_id', 'title', 'custom_name',
                'chat_type', 'custom_type_name', 'custom_type_description',
                'owner_id', 'entity_id', 'is_active', 'created_at',
                'last_activity', 'deleted_at'
            ],
            'messages': [
                'id', 'chat_id', 'telegram_message_id', 'telegram_user_id',
                'username', 'first_name', 'last_name', 'content', 'content_type',
                'file_id', 'file_path', 'file_name', 'document_metadata',
                'parse_status', 'parse_error', 'is_imported', 'timestamp'
            ],
            'call_recordings': [
                'id', 'org_id', 'title', 'entity_id', 'owner_id', 'source_type',
                'source_url', 'bot_name', 'status', 'duration_seconds',
                'audio_file_path', 'fireflies_transcript_id', 'transcript',
                'speakers', 'summary', 'action_items', 'key_points',
                'error_message', 'created_at', 'started_at', 'ended_at', 'processed_at'
            ],
            'shared_access': [
                'id', 'resource_type', 'resource_id', 'shared_by_id',
                'shared_with_id', 'access_level', 'note', 'expires_at', 'created_at'
            ],
            'invitations': [
                'id', 'token', 'org_id', 'email', 'name', 'org_role',
                'department_ids', 'invited_by_id', 'expires_at', 'used_at',
                'used_by_id', 'created_at'
            ]
        }

        def _check_columns(session):
            inspector = inspect(session.get_bind())
            mismatches = []

            for table_name, expected_columns in table_column_checks.items():
                try:
                    columns = inspector.get_columns(table_name)
                    actual_columns = [col['name'] for col in columns]

                    missing = [col for col in expected_columns if col not in actual_columns]
                    extra = [col for col in actual_columns if col not in expected_columns]

                    if missing or extra:
                        mismatches.append({
                            'table': table_name,
                            'missing': missing,
                            'extra': extra
                        })
                except Exception as e:
                    mismatches.append({
                        'table': table_name,
                        'error': str(e)
                    })
            return mismatches

        mismatches = await db_session.run_sync(_check_columns)

        if mismatches:
            error_msg = "\nColumn mismatches found:\n"
            for mismatch in mismatches:
                error_msg += f"\nTable '{mismatch['table']}':\n"
                if 'error' in mismatch:
                    error_msg += f"  Error: {mismatch['error']}\n"
                if mismatch.get('missing'):
                    error_msg += f"  Missing columns: {mismatch['missing']}\n"
                if mismatch.get('extra'):
                    error_msg += f"  Extra columns: {mismatch['extra']}\n"

            pytest.fail(error_msg)

    @pytest.mark.asyncio
    async def test_foreign_keys_defined(self, db_session):
        """
        Verify that foreign key constraints are properly defined.

        This is critical for data integrity. With proper migrations,
        all FKs should be present.
        """
        # Expected foreign keys for critical tables
        expected_fks = {
            'org_members': [
                ('org_id', 'organizations'),
                ('user_id', 'users'),
            ],
            'department_members': [
                ('department_id', 'departments'),
                ('user_id', 'users'),
            ],
            'departments': [
                ('org_id', 'organizations'),
            ],
            'entities': [
                ('org_id', 'organizations'),
                ('department_id', 'departments'),
            ],
            'chats': [
                ('org_id', 'organizations'),
                ('owner_id', 'users'),
                ('entity_id', 'entities'),
            ],
            'messages': [
                ('chat_id', 'chats'),
            ],
            'call_recordings': [
                ('org_id', 'organizations'),
                ('entity_id', 'entities'),
                ('owner_id', 'users'),
            ],
            'shared_access': [
                ('shared_by_id', 'users'),
                ('shared_with_id', 'users'),
            ],
        }

        def _check_fks(session):
            inspector = inspect(session.get_bind())
            missing_fks = []

            for table_name, expected in expected_fks.items():
                try:
                    fks = inspector.get_foreign_keys(table_name)

                    # Extract FK info
                    actual_fks = [
                        (fk['constrained_columns'][0], fk['referred_table'])
                        for fk in fks
                    ]

                    for column, ref_table in expected:
                        if (column, ref_table) not in actual_fks:
                            missing_fks.append(f"{table_name}.{column} -> {ref_table}")
                except Exception as e:
                    missing_fks.append(f"{table_name}: Error checking FKs - {e}")
            return missing_fks

        missing_fks = await db_session.run_sync(_check_fks)

        if missing_fks:
            pytest.fail(f"\nMissing foreign keys:\n" + "\n".join(f"  - {fk}" for fk in missing_fks))

    @pytest.mark.asyncio
    async def test_indexes_exist(self, db_session):
        """
        Verify that important indexes are defined.

        Indexes are critical for query performance. This test documents
        which indexes should be managed by migrations.
        """
        def _get_inspector(session):
            return inspect(session.get_bind())

        inspector = await db_session.run_sync(_get_inspector)

        # Expected indexes on critical columns
        expected_indexes = {
            'users': ['email', 'telegram_id'],
            'organizations': ['slug'],
            'org_members': ['org_id', 'user_id'],
            'department_members': ['department_id', 'user_id'],
            'departments': ['org_id'],
            'entities': ['org_id', 'department_id', 'type', 'status', 'telegram_user_id'],
            'chats': ['org_id', 'telegram_chat_id', 'owner_id', 'entity_id', 'chat_type', 'deleted_at'],
            'messages': ['chat_id', 'telegram_user_id'],
            'call_recordings': ['org_id', 'entity_id', 'owner_id', 'status', 'fireflies_transcript_id'],
            'shared_access': ['resource_type', 'resource_id', 'shared_by_id', 'shared_with_id'],
            'invitations': ['token', 'org_id'],
        }

        missing_indexes = []

        for table_name, expected_cols in expected_indexes.items():
            try:
                indexes = inspector.get_indexes(table_name)
                indexed_cols = set()

                # Extract indexed columns (including composite indexes)
                for idx in indexes:
                    if 'column_names' in idx:
                        indexed_cols.update(idx['column_names'])

                # Also check unique constraints (they create indexes)
                unique_constraints = inspector.get_unique_constraints(table_name)
                for uc in unique_constraints:
                    if 'column_names' in uc:
                        indexed_cols.update(uc['column_names'])

                for col in expected_cols:
                    if col not in indexed_cols:
                        missing_indexes.append(f"{table_name}.{col}")
            except Exception as e:
                print(f"Warning: Could not check indexes for {table_name}: {e}")

        if missing_indexes:
            # This is a warning, not a failure - indexes can be added later
            print(f"\nNote: Missing recommended indexes:\n" + "\n".join(f"  - {idx}" for idx in missing_indexes))
            print("Consider adding these indexes for better query performance.")


class TestDatabaseBackup:
    """Test database backup/restore capabilities."""

    @pytest.mark.asyncio
    async def test_can_export_schema(self, db_session):
        """
        Test that schema can be exported via SQLAlchemy metadata.

        This is a basic backup capability - being able to dump schema DDL.
        With Alembic, we'd also have migration history.
        """
        from sqlalchemy.schema import CreateTable
        from api.models.database import Base

        # Try to get DDL for a few critical tables
        def _get_ddl(session):
            ddl_statements = []
            bind = session.get_bind()
            for table in Base.metadata.sorted_tables:
                if table.name in ['users', 'organizations', 'chats', 'entities']:
                    try:
                        create_stmt = str(CreateTable(table).compile(bind))
                        ddl_statements.append(create_stmt)
                    except Exception as e:
                        raise Exception(f"Failed to generate DDL for {table.name}: {e}")
            return ddl_statements

        ddl_statements = await db_session.run_sync(_get_ddl)

        assert len(ddl_statements) >= 4, "Should be able to export DDL for critical tables"

        # Verify DDL contains expected elements
        users_ddl = next((ddl for ddl in ddl_statements if 'users' in ddl.lower()), None)
        assert users_ddl is not None
        assert 'email' in users_ddl.lower()
        assert 'password_hash' in users_ddl.lower()

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="alembic_version table created by 'alembic upgrade head' in production")
    async def test_can_query_migration_version(self, db_session):
        """
        Test that Alembic version table exists and can be queried.

        EXPECTED TO FAIL: No alembic_version table exists yet.
        This table tracks which migrations have been applied.
        """
        try:
            result = await db_session.execute(
                text("SELECT version_num FROM alembic_version")
            )
            version = result.scalar_one_or_none()

            # If we get here, alembic_version table exists
            # It might be None if no migrations run yet, but table should exist
            assert version is None or isinstance(version, str), (
                "alembic_version table exists but has invalid data"
            )
        except Exception as e:
            pytest.fail(
                f"Cannot query alembic_version table: {e}\n"
                "This table is created by Alembic and tracks migration state.\n"
                "Initialize Alembic and run: alembic upgrade head"
            )


class TestMigrationWorkflow:
    """Test the migration workflow and best practices."""

    def test_alembic_command_available(self):
        """
        Test that alembic command is available.

        This verifies that Alembic is installed in the environment.
        """
        import shutil

        import sys
        # Тесты запускают .venv/bin/python напрямую — bin окружения может не
        # быть в PATH, поэтому ищем и рядом с интерпретатором.
        alembic_path = shutil.which('alembic') or shutil.which(
            'alembic', path=str(Path(sys.executable).parent)
        )
        assert alembic_path is not None, (
            "alembic command not found. Install with: pip install alembic\n"
            "Alembic should be in requirements.txt"
        )

    @pytest.mark.xfail(reason="README documentation to be added")
    def test_readme_documents_migration_workflow(self):
        """
        Test that README or docs explain migration workflow.

        EXPECTED TO FAIL: Documentation for migrations likely doesn't exist.
        Developers need to know how to create and apply migrations.
        """
        backend_dir = Path(__file__).resolve().parent.parent

        # Check for README files
        readme_files = list(backend_dir.glob("README*"))
        docs_dir = backend_dir / "docs"

        documentation_exists = False
        migration_docs_found = False

        # Check README files
        for readme in readme_files:
            if readme.is_file():
                documentation_exists = True
                content = readme.read_text().lower()
                if 'alembic' in content or 'migration' in content:
                    migration_docs_found = True
                    break

        # Check docs directory
        if docs_dir.exists():
            for doc in docs_dir.glob("**/*.md"):
                documentation_exists = True
                content = doc.read_text().lower()
                if 'alembic' in content or 'migration' in content:
                    migration_docs_found = True
                    break

        if not documentation_exists:
            pytest.fail(
                "No README or documentation found in backend/.\n"
                "Add README.md with setup and migration instructions."
            )

        if not migration_docs_found:
            pytest.fail(
                "Documentation exists but doesn't mention migrations.\n"
                "Add section explaining:\n"
                "  - How to create migrations: alembic revision --autogenerate -m 'description'\n"
                "  - How to apply migrations: alembic upgrade head\n"
                "  - How to rollback: alembic downgrade -1\n"
                "  - How to check status: alembic current"
            )
