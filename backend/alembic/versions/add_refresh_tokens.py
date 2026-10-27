"""Add refresh_tokens table for secure session management

Creates:
- refresh_tokens: Stores hashed refresh tokens for JWT rotation

Features:
- Token hashing (SHA-256) for security - raw tokens are never stored
- Device tracking for session management UI
- IP address logging for security auditing
- Expiration tracking for automatic cleanup
- Soft revocation support (revoked_at timestamp)

Revision ID: add_refresh_tokens
Revises: fix_callsource_and_fk_constraints
Create Date: 2026-01-13
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_refresh_tokens'
down_revision = 'fix_callsource_and_fk_constraints'
branch_labels = None
depends_on = None


def table_exists(table_name):
    """Check if a table exists."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = :table"
    ), {"table": table_name})
    return result.fetchone() is not None


def index_exists(index_name):
    """Check if an index exists."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_indexes WHERE indexname = :name"
    ), {"name": index_name})
    return result.fetchone() is not None


def upgrade():
    """Create refresh_tokens table with indexes."""

    if not table_exists('refresh_tokens'):
        op.create_table(
            'refresh_tokens',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('token_hash', sa.String(255), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('device_name', sa.String(255), nullable=True),
            sa.Column('ip_address', sa.String(45), nullable=True),  # IPv6 support
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('revoked_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )

        # Create indexes for efficient lookups
        op.create_index('ix_refresh_tokens_token_hash', 'refresh_tokens', ['token_hash'], unique=True)
        op.create_index('ix_refresh_tokens_user_id', 'refresh_tokens', ['user_id'])
        op.create_index('ix_refresh_tokens_expires_at', 'refresh_tokens', ['expires_at'])
        op.create_index('ix_refresh_tokens_user_expires', 'refresh_tokens', ['user_id', 'expires_at'])


def downgrade():
    """Remove refresh_tokens table."""
    op.drop_table('refresh_tokens')
