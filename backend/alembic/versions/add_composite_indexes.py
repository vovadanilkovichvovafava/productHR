"""Add composite database indexes for query performance.

Revision ID: add_composite_indexes
Revises: sync_entity_status_from_applications
Create Date: 2025-01-22

New indexes:
- ix_chat_org_deleted: Filter non-deleted chats by org
- ix_chat_owner_activity: Filter by owner and sort by activity
- ix_message_chat_timestamp: Sort messages by timestamp within chat
- ix_vacancy_org_status: Filter vacancies by org and status
- ix_vacancy_dept_status: Filter vacancies by department and status
- ix_entity_file_entity_type: List files by entity and type
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision = "add_composite_indexes"
down_revision = "sync_entity_status_001"
branch_labels = None
depends_on = None


def upgrade():
    # Chat indexes
    op.create_index(
        "ix_chat_org_deleted",
        "chats",
        ["org_id", "deleted_at"],
        if_not_exists=True
    )
    op.create_index(
        "ix_chat_owner_activity",
        "chats",
        ["owner_id", "last_activity"],
        if_not_exists=True
    )

    # Message indexes
    op.create_index(
        "ix_message_chat_timestamp",
        "messages",
        ["chat_id", "timestamp"],
        if_not_exists=True
    )

    # Vacancy indexes
    op.create_index(
        "ix_vacancy_org_status",
        "vacancies",
        ["org_id", "status"],
        if_not_exists=True
    )
    op.create_index(
        "ix_vacancy_dept_status",
        "vacancies",
        ["department_id", "status"],
        if_not_exists=True
    )

    # EntityFile indexes
    op.create_index(
        "ix_entity_file_entity_type",
        "entity_files",
        ["entity_id", "file_type"],
        if_not_exists=True
    )


def downgrade():
    # Drop all new indexes
    op.drop_index("ix_entity_file_entity_type", table_name="entity_files", if_exists=True)
    op.drop_index("ix_vacancy_dept_status", table_name="vacancies", if_exists=True)
    op.drop_index("ix_vacancy_org_status", table_name="vacancies", if_exists=True)
    op.drop_index("ix_message_chat_timestamp", table_name="messages", if_exists=True)
    op.drop_index("ix_chat_owner_activity", table_name="chats", if_exists=True)
    op.drop_index("ix_chat_org_deleted", table_name="chats", if_exists=True)
