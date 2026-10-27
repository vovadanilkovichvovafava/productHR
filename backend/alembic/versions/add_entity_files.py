"""Add entity files table

Creates:
- entity_files: Files attached to entities (resumes, cover letters, etc.)

Revision ID: add_entity_files
Revises: add_vacancies
Create Date: 2026-01-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'add_entity_files'
down_revision = 'add_vacancies'
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
    """Check if an enum type exists."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_type WHERE typname = :name"
    ), {"name": enum_name})
    return result.fetchone() is not None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    conn = op.get_bind()
    result = conn.execute(sa.text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = :table AND column_name = :column
    """), {"table": table_name, "column": column_name})
    return result.fetchone() is not None


def upgrade():
    """Create entity_files table."""

    # Create EntityFileType enum
    if not enum_exists('entityfiletype'):
        op.execute("""
            CREATE TYPE entityfiletype AS ENUM (
                'resume', 'cover_letter', 'test_assignment', 'certificate', 'portfolio', 'other'
            )
        """)

    # Create entity_files table
    if not table_exists('entity_files'):
        op.create_table(
            'entity_files',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('entity_id', sa.Integer(), nullable=False),
            sa.Column('org_id', sa.Integer(), nullable=False),
            sa.Column('file_type', postgresql.ENUM('resume', 'cover_letter', 'test_assignment', 'certificate', 'portfolio', 'other', name='entityfiletype', create_type=False), server_default='other'),
            sa.Column('file_name', sa.String(255), nullable=False),
            sa.Column('file_path', sa.String(512), nullable=False),
            sa.Column('file_size', sa.Integer(), nullable=True),
            sa.Column('mime_type', sa.String(100), nullable=True),
            sa.Column('description', sa.String(500), nullable=True),
            sa.Column('uploaded_by', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_entity_files_entity_id', 'entity_files', ['entity_id'])
        op.create_index('ix_entity_files_org_id', 'entity_files', ['org_id'])
    else:
        # Add org_id column if table exists but column doesn't
        if not column_exists('entity_files', 'org_id'):
            # First add as nullable
            op.add_column('entity_files', sa.Column('org_id', sa.Integer(), nullable=True))
            # Populate from entity's org_id
            op.execute("""
                UPDATE entity_files ef
                SET org_id = e.org_id
                FROM entities e
                WHERE ef.entity_id = e.id
            """)
            # Make not nullable
            op.alter_column('entity_files', 'org_id', nullable=False)
            # Add foreign key
            op.create_foreign_key(
                'fk_entity_files_org_id',
                'entity_files', 'organizations',
                ['org_id'], ['id'],
                ondelete='CASCADE'
            )
            op.create_index('ix_entity_files_org_id', 'entity_files', ['org_id'])


def downgrade():
    """Remove entity_files table."""
    op.drop_table('entity_files')
    op.execute('DROP TYPE IF EXISTS entityfiletype')
