"""Add auto_tasks_enabled to chats (default false)

Revision ID: add_chat_auto_tasks
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_chat_auto_tasks'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('chats')]
    if 'auto_tasks_enabled' not in columns:
        op.add_column('chats', sa.Column('auto_tasks_enabled', sa.Boolean(), server_default='false', nullable=True))
    else:
        # Set all existing chats to false (off by default)
        op.execute("UPDATE chats SET auto_tasks_enabled = false")


def downgrade():
    op.drop_column('chats', 'auto_tasks_enabled')
