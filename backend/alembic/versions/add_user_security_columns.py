"""Add user security columns

Revision ID: add_user_security_cols
Revises: 3908ad1d4246
Create Date: 2024-12-24

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_user_security_cols'
down_revision = '3908ad1d4246'
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
    # Add token_version column (idempotent)
    if not column_exists('users', 'token_version'):
        op.add_column('users', sa.Column('token_version', sa.Integer(), nullable=True))
        op.execute("UPDATE users SET token_version = 0 WHERE token_version IS NULL")
        op.alter_column('users', 'token_version', nullable=False, server_default='0')

    # Add failed_login_attempts column (idempotent)
    if not column_exists('users', 'failed_login_attempts'):
        op.add_column('users', sa.Column('failed_login_attempts', sa.Integer(), nullable=True, server_default='0'))

    # Add locked_until column (idempotent)
    if not column_exists('users', 'locked_until'):
        op.add_column('users', sa.Column('locked_until', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('users', 'locked_until')
    op.drop_column('users', 'failed_login_attempts')
    op.drop_column('users', 'token_version')
