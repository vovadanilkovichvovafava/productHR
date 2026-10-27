"""merge_all_heads

Revision ID: 8e2df4526551
Revises: add_custom_fields, add_notifications, add_project_status_defs, add_shadow_users, add_subtasks, add_task_attachments, add_task_comments, add_task_keys, add_vacancy_visible_to_all
Create Date: 2026-04-01 18:14:04.027629

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8e2df4526551'
down_revision: Union[str, Sequence[str], None] = ('add_custom_fields', 'add_notifications', 'add_project_status_defs', 'add_shadow_users', 'add_subtasks', 'add_task_attachments', 'add_task_comments', 'add_task_keys', 'add_vacancy_visible_to_all')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
