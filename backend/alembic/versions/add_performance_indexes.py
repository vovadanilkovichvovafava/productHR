"""Add performance indexes for common query patterns

Revision ID: add_performance_indexes
Revises: sync_entity_status_from_applications
Create Date: 2025-01-22

This migration adds composite indexes to optimize frequently used queries:
- Message filtering by chat and user
- Entity filtering by org + status/type/creator
- VacancyApplication lookups
"""

from alembic import op
import logging

# revision identifiers, used by Alembic.
revision = 'add_performance_indexes'
down_revision = 'add_composite_indexes'
branch_labels = None
depends_on = None

logger = logging.getLogger('alembic.runtime.migration')


def upgrade() -> None:
    """Add composite indexes for performance optimization."""

    # Index for message filtering by chat and telegram user
    # Used when filtering messages by sender within a chat
    logger.info("Creating index ix_message_chat_telegram_user...")
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_message_chat_telegram_user
        ON messages (chat_id, telegram_user_id)
    """)

    # Index for entity filtering by org + status
    # Most common query pattern: list entities by status within org
    logger.info("Creating index ix_entity_org_status...")
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_entity_org_status
        ON entities (org_id, status)
    """)

    # Index for entity filtering by org + creator
    # Used for "my entities" queries
    logger.info("Creating index ix_entity_org_created_by...")
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_entity_org_created_by
        ON entities (org_id, created_by)
    """)

    # Index for entity filtering by org + type
    # Used for filtering by entity type (candidate, client, etc.)
    logger.info("Creating index ix_entity_org_type...")
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_entity_org_type
        ON entities (org_id, type)
    """)

    # Index for vacancy application lookups
    # Used when checking all applications for an entity
    logger.info("Creating index ix_vacancy_application_entity_vacancy...")
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_vacancy_application_entity_vacancy
        ON vacancy_applications (entity_id, vacancy_id)
    """)

    logger.info("All performance indexes created successfully")


def downgrade() -> None:
    """Remove the added indexes."""

    op.execute("DROP INDEX IF EXISTS ix_message_chat_telegram_user")
    op.execute("DROP INDEX IF EXISTS ix_entity_org_status")
    op.execute("DROP INDEX IF EXISTS ix_entity_org_created_by")
    op.execute("DROP INDEX IF EXISTS ix_entity_org_type")
    op.execute("DROP INDEX IF EXISTS ix_vacancy_application_entity_vacancy")

    logger.info("Performance indexes removed")
