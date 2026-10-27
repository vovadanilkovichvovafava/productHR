"""Add parse_jobs table for background resume parsing

Creates:
- parsejobstatus enum: pending, processing, completed, failed
- parse_jobs: Tracks background parsing jobs

Revision ID: add_parse_jobs
Revises: add_performance_indexes
Create Date: 2026-01-26
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_parse_jobs'
down_revision = 'add_performance_indexes'
branch_labels = None
depends_on = None


def table_exists(table_name):
    """Check if a table exists."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = :table"
    ), {"table": table_name})
    return result.fetchone() is not None


def enum_exists(enum_name):
    """Check if an enum exists."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_type WHERE typname = :name"
    ), {"name": enum_name})
    return result.fetchone() is not None


def index_exists(index_name):
    """Check if an index exists."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_indexes WHERE indexname = :name"
    ), {"name": index_name})
    return result.fetchone() is not None


def upgrade():
    """Create parse_jobs table with indexes."""

    # Create enum if it doesn't exist
    if not enum_exists('parsejobstatus'):
        op.execute("CREATE TYPE parsejobstatus AS ENUM ('pending', 'processing', 'completed', 'failed')")

    if not table_exists('parse_jobs'):
        op.create_table(
            'parse_jobs',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('org_id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('status', sa.Enum('pending', 'processing', 'completed', 'failed', name='parsejobstatus'), nullable=True),
            sa.Column('file_name', sa.String(255), nullable=False),
            sa.Column('file_path', sa.String(512), nullable=False),
            sa.Column('file_size', sa.Integer(), nullable=True),
            sa.Column('entity_id', sa.Integer(), nullable=True),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('progress', sa.Integer(), default=0),
            sa.Column('progress_stage', sa.String(100), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
            sa.Column('started_at', sa.DateTime(), nullable=True),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id')
        )

        # Create indexes
        if not index_exists('ix_parse_jobs_status'):
            op.create_index('ix_parse_jobs_status', 'parse_jobs', ['status'])
        if not index_exists('ix_parse_jobs_org_id'):
            op.create_index('ix_parse_jobs_org_id', 'parse_jobs', ['org_id'])
        if not index_exists('ix_parse_jobs_user_id'):
            op.create_index('ix_parse_jobs_user_id', 'parse_jobs', ['user_id'])
        if not index_exists('ix_parse_jobs_entity_id'):
            op.create_index('ix_parse_jobs_entity_id', 'parse_jobs', ['entity_id'])
        if not index_exists('ix_parse_job_user_status'):
            op.create_index('ix_parse_job_user_status', 'parse_jobs', ['user_id', 'status'])
        if not index_exists('ix_parse_job_org_created'):
            op.create_index('ix_parse_job_org_created', 'parse_jobs', ['org_id', 'created_at'])


def downgrade():
    """Drop parse_jobs table."""
    op.drop_table('parse_jobs')
    op.execute("DROP TYPE IF EXISTS parsejobstatus")
