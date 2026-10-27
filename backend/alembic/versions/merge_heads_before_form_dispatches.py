"""Merge all floating heads before form_dispatches

Revision ID: merge_heads_2026_06_17
Revises: add_chat_auto_tasks, add_entity_file_data, add_funnel_customization,
         add_hr_orgrole_001, add_timeoff_blockers, enable_auto_tasks
Create Date: 2026-06-17
"""
from alembic import op

revision = 'merge_heads_2026_06_17'
down_revision = (
    'add_chat_auto_tasks',
    'add_entity_file_data',
    'add_funnel_customization',
    'add_hr_orgrole_001',
    'add_timeoff_blockers',
    'enable_auto_tasks',
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
