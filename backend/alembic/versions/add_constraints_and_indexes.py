"""Add UNIQUE constraints, indexes, and cascade deletes

Revision ID: add_constraints_and_indexes
Revises: add_entity_ai_memory
Create Date: 2025-12-25

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_constraints_and_indexes'
down_revision = 'add_entity_ai_memory'
branch_labels = None
depends_on = None


def get_constraint_columns(constraint_name, table_name):
    """Get the columns of a unique constraint."""
    conn = op.get_bind()
    result = conn.execute(sa.text("""
        SELECT array_agg(a.attname ORDER BY array_position(c.conkey, a.attnum))
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.conkey)
        WHERE c.conname = :constraint_name
        AND t.relname = :table_name
        AND c.contype = 'u'
    """), {"constraint_name": constraint_name, "table_name": table_name})
    row = result.fetchone()
    return row[0] if row and row[0] else []


def constraint_exists(constraint_name):
    """Check if a constraint exists."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.table_constraints WHERE constraint_name = :name"
    ), {"name": constraint_name})
    return result.fetchone() is not None


def upgrade():
    """
    Add database constraints and indexes for data integrity and performance.

    Changes:
    1. Update SharedAccess unique constraint to include shared_by_id
       (allows same resource to be shared with same person by different sharers)

    Note: All other required constraints, indexes, and cascade behaviors are already
    present in the models from previous migrations:
    - OrgMember has unique constraint on (user_id, org_id)
    - DepartmentMember has unique constraint on (user_id, department_id)
    - All search columns already have indexes (Organization.name, Department.name,
      Entity.name, Entity.email, User.name, Message.content_type)
    - Cascade deletes are handled by ForeignKey ondelete='CASCADE' at database level
      and cascade='all, delete-orphan' at ORM level (now added to Organization.chats
      and Organization.calls in the models)
    """
    # Check if constraint needs to be updated
    if constraint_exists('uq_shared_access_resource_user'):
        columns = get_constraint_columns('uq_shared_access_resource_user', 'shared_access')
        # If constraint already has 4 columns (including shared_by_id), skip
        if len(columns) == 4 and 'shared_by_id' in columns:
            return
        # Drop old unique constraint on shared_access
        op.drop_constraint('uq_shared_access_resource_user', 'shared_access', type_='unique')

    # Create new unique constraint including shared_by_id
    # This ensures the same resource can be shared with the same person by different users
    op.create_unique_constraint(
        'uq_shared_access_resource_user',
        'shared_access',
        ['resource_type', 'resource_id', 'shared_with_id', 'shared_by_id']
    )


def downgrade():
    """
    Revert the unique constraint change.
    """
    # Drop new unique constraint
    op.drop_constraint('uq_shared_access_resource_user', 'shared_access', type_='unique')

    # Restore old unique constraint (without shared_by_id)
    op.create_unique_constraint(
        'uq_shared_access_resource_user',
        'shared_access',
        ['resource_type', 'resource_id', 'shared_with_id']
    )
