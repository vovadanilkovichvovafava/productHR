"""Enable auto_tasks_enabled by default for all chats

Revision ID: enable_auto_tasks
"""
from alembic import op

revision = 'enable_auto_tasks'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Enable auto-tasks for all existing chats
    op.execute("UPDATE chats SET auto_tasks_enabled = true WHERE auto_tasks_enabled = false OR auto_tasks_enabled IS NULL")
    # Change server default for new chats
    op.alter_column('chats', 'auto_tasks_enabled', server_default='true')


def downgrade():
    op.execute("UPDATE chats SET auto_tasks_enabled = false")
    op.alter_column('chats', 'auto_tasks_enabled', server_default='false')
