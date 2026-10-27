"""Add employees and leave_requests tables

Creates:
- employees: Employee records (personal cabinet, leave counters, contract tracking)
- leave_requests: Employee leave/vacation requests

Revision ID: add_employees_and_leave
Revises: add_form_templates
Create Date: 2026-04-03
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_employees_and_leave'
down_revision = 'add_form_templates'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Employees table
    op.create_table(
        'employees',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('org_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('entity_id', sa.Integer(), sa.ForeignKey('entities.id', ondelete='SET NULL'), nullable=True),
        sa.Column('department_id', sa.Integer(), sa.ForeignKey('departments.id', ondelete='SET NULL'), nullable=True),
        # Personal info
        sa.Column('position', sa.String(300), nullable=True),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('telegram_username', sa.String(200), nullable=True),
        # Employment dates
        sa.Column('practice_start_date', sa.DateTime(), nullable=True),
        sa.Column('department_start_date', sa.DateTime(), nullable=True),
        sa.Column('probation_end_date', sa.DateTime(), nullable=True),
        sa.Column('one_year_date', sa.DateTime(), nullable=True),
        # Leave counters
        sa.Column('vacation_days_total', sa.Integer(), server_default='0'),
        sa.Column('vacation_days_used', sa.Integer(), server_default='0'),
        sa.Column('sick_days_total', sa.Integer(), server_default='10'),
        sa.Column('sick_days_used', sa.Integer(), server_default='0'),
        sa.Column('family_leave_days_total', sa.Integer(), server_default='3'),
        sa.Column('family_leave_days_used', sa.Integer(), server_default='0'),
        # Contract
        sa.Column('nda_signed', sa.Boolean(), server_default='false'),
        sa.Column('nda_signed_at', sa.DateTime(), nullable=True),
        sa.Column('contract_signed', sa.Boolean(), server_default='false'),
        sa.Column('contract_signed_at', sa.DateTime(), nullable=True),
        # Status
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('dismissed_at', sa.DateTime(), nullable=True),
        sa.Column('dismissal_reason', sa.Text(), nullable=True),
        # Metadata
        sa.Column('extra_data', sa.JSON(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_employees_user_id', 'employees', ['user_id'])
    op.create_index('ix_employees_org_id', 'employees', ['org_id'])

    # Leave requests table
    op.create_table(
        'leave_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id', ondelete='CASCADE'), nullable=False),
        sa.Column('type', sa.String(30), nullable=False),
        sa.Column('start_date', sa.DateTime(), nullable=False),
        sa.Column('end_date', sa.DateTime(), nullable=False),
        sa.Column('days', sa.Integer(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('approved_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_leave_requests_employee_id', 'leave_requests', ['employee_id'])


def downgrade() -> None:
    op.drop_table('leave_requests')
    op.drop_table('employees')
