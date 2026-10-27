"""Add entity transfer tracking fields

Revision ID: add_entity_transfer
Revises: add_sub_admin_to_userrole
Create Date: 2025-12-24

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_entity_transfer'
down_revision = 'add_sub_admin_to_userrole'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in the table."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns WHERE table_name = :table AND column_name = :column"
    ), {"table": table_name, "column": column_name})
    return result.fetchone() is not None


def index_exists(index_name):
    """Check if an index exists."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_indexes WHERE indexname = :index_name"
    ), {"index_name": index_name})
    return result.fetchone() is not None


def constraint_exists(constraint_name):
    """Check if a constraint exists."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.table_constraints WHERE constraint_name = :name"
    ), {"name": constraint_name})
    return result.fetchone() is not None


def upgrade():
    # Add is_transferred column
    if not column_exists('entities', 'is_transferred'):
        op.add_column('entities', sa.Column('is_transferred', sa.Boolean(), nullable=True, server_default='false'))
    if not index_exists('ix_entities_is_transferred'):
        op.create_index('ix_entities_is_transferred', 'entities', ['is_transferred'])

    # Add transferred_to_id column (FK to users)
    if not column_exists('entities', 'transferred_to_id'):
        op.add_column('entities', sa.Column('transferred_to_id', sa.Integer(), nullable=True))
    if not constraint_exists('fk_entities_transferred_to_id'):
        op.create_foreign_key('fk_entities_transferred_to_id', 'entities', 'users', ['transferred_to_id'], ['id'])

    # Add transferred_at column
    if not column_exists('entities', 'transferred_at'):
        op.add_column('entities', sa.Column('transferred_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('entities', 'transferred_at')
    op.drop_constraint('fk_entities_transferred_to_id', 'entities', type_='foreignkey')
    op.drop_column('entities', 'transferred_to_id')
    op.drop_index('ix_entities_is_transferred', 'entities')
    op.drop_column('entities', 'is_transferred')
