"""Add time_off_requests and blockers tables

Revision ID: add_timeoff_blockers
Revises: None
Create Date: 2026-04-10
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_timeoff_blockers'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # Create TimeOff enums
    timeoff_type = sa.Enum('vacation', 'day_off', 'sick_leave', 'other', name='timeofftype')
    timeoff_status = sa.Enum('pending', 'approved', 'rejected', name='timeoffstatus')
    blocker_status = sa.Enum('open', 'resolved', name='blockerstatus')

    if 'time_off_requests' not in existing_tables:
        timeoff_type.create(conn, checkfirst=True)
        timeoff_status.create(conn, checkfirst=True)
        op.create_table(
            'time_off_requests',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('org_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('type', timeoff_type, default='vacation'),
            sa.Column('status', timeoff_status, default='pending'),
            sa.Column('date_from', sa.DateTime(), nullable=False),
            sa.Column('date_to', sa.DateTime(), nullable=False),
            sa.Column('reason', sa.Text(), nullable=True),
            sa.Column('reviewed_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('reviewed_at', sa.DateTime(), nullable=True),
            sa.Column('reject_reason', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        )
        op.create_index('ix_timeoff_org_status', 'time_off_requests', ['org_id', 'status'])
        op.create_index('ix_timeoff_user_status', 'time_off_requests', ['user_id', 'status'])

    if 'blockers' not in existing_tables:
        blocker_status.create(conn, checkfirst=True)
        op.create_table(
            'blockers',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('org_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id', ondelete='SET NULL'), nullable=True),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('status', blocker_status, default='open'),
            sa.Column('resolved_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('resolved_at', sa.DateTime(), nullable=True),
            sa.Column('resolve_comment', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        )
        op.create_index('ix_blocker_org_status', 'blockers', ['org_id', 'status'])


def downgrade():
    op.drop_table('blockers')
    op.drop_table('time_off_requests')
    sa.Enum(name='blockerstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='timeoffstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='timeofftype').drop(op.get_bind(), checkfirst=True)
