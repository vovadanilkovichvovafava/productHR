"""Add cancel fields to EntityTransfer

Revision ID: add_transfer_cancel_fields
Revises: add_member_to_userrole
Create Date: 2025-12-28

Adds fields to support transfer cancellation within 1 hour:
- copy_entity_id: Reference to the frozen copy created during transfer
- cancelled_at: When the transfer was cancelled
- cancel_deadline: Deadline for cancellation (transfer time + 1 hour)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_transfer_cancel_fields'
down_revision = 'add_member_to_userrole'
branch_labels = None
depends_on = None


def upgrade():
    """Add cancel-related columns to entity_transfers table."""
    op.add_column('entity_transfers',
        sa.Column('copy_entity_id', sa.Integer(), nullable=True)
    )
    op.add_column('entity_transfers',
        sa.Column('cancelled_at', sa.DateTime(), nullable=True)
    )
    op.add_column('entity_transfers',
        sa.Column('cancel_deadline', sa.DateTime(), nullable=True)
    )

    # Add foreign key for copy_entity_id
    op.create_foreign_key(
        'fk_entity_transfers_copy_entity_id',
        'entity_transfers', 'entities',
        ['copy_entity_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade():
    """Remove cancel-related columns from entity_transfers table."""
    op.drop_constraint('fk_entity_transfers_copy_entity_id', 'entity_transfers', type_='foreignkey')
    op.drop_column('entity_transfers', 'cancel_deadline')
    op.drop_column('entity_transfers', 'cancelled_at')
    op.drop_column('entity_transfers', 'copy_entity_id')
