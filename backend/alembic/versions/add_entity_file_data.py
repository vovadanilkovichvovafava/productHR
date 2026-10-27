"""Add file_data column to entity_files for DB storage

Store file content in PostgreSQL bytea instead of disk.
Survives Railway redeploys without persistent volumes.

Revision ID: add_entity_file_data
Revises: add_vacancy_visible_to_all
Create Date: 2026-04-09
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_entity_file_data'
down_revision = 'add_vacancy_visible_to_all'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    conn = op.get_bind()
    result = conn.execute(sa.text(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = :table AND column_name = :col
        """
    ), {"table": table_name, "col": column_name})
    return result.fetchone() is not None


def upgrade():
    if not column_exists('entity_files', 'file_data'):
        op.add_column('entity_files', sa.Column('file_data', sa.LargeBinary(), nullable=True))

    # Make file_path nullable (no longer required when using DB storage)
    op.alter_column('entity_files', 'file_path',
                    existing_type=sa.String(512),
                    nullable=True)


def downgrade():
    op.alter_column('entity_files', 'file_path',
                    existing_type=sa.String(512),
                    nullable=False)
    op.drop_column('entity_files', 'file_data')
