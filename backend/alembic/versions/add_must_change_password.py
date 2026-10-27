"""Add must_change_password column to users

Revision ID: add_must_change_pwd
Revises: add_user_security_cols
Create Date: 2025-01-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_must_change_pwd'
down_revision = 'add_entity_criteria'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns WHERE table_name = :table AND column_name = :column"
    ), {"table": table_name, "column": column_name})
    return result.fetchone() is not None


def upgrade():
    # Add must_change_password column (idempotent)
    if not column_exists('users', 'must_change_password'):
        op.add_column('users', sa.Column('must_change_password', sa.Boolean(), nullable=True, server_default='false'))


def downgrade():
    op.drop_column('users', 'must_change_password')
