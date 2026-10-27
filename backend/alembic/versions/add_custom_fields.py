"""Add project custom fields and task custom field values

Revision ID: add_custom_fields
Revises: add_projects_module
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_custom_fields'
down_revision = 'add_projects_module'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'project_custom_fields',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('field_type', sa.String(30), nullable=False),
        sa.Column('options', sa.JSON(), server_default='[]'),
        sa.Column('currency', sa.String(10), nullable=True),
        sa.Column('sort_order', sa.Integer(), server_default='0'),
        sa.Column('is_required', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_project_custom_fields_project_id', 'project_custom_fields', ['project_id'])
    op.create_index('ix_cf_project', 'project_custom_fields', ['project_id', 'sort_order'])

    op.create_table(
        'task_custom_field_values',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('task_id', sa.Integer(), sa.ForeignKey('project_tasks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('field_id', sa.Integer(), sa.ForeignKey('project_custom_fields.id', ondelete='CASCADE'), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
    )
    op.create_index('ix_task_custom_field_values_task_id', 'task_custom_field_values', ['task_id'])
    op.create_index('ix_task_custom_field_values_field_id', 'task_custom_field_values', ['field_id'])
    op.create_unique_constraint('uq_task_field_value', 'task_custom_field_values', ['task_id', 'field_id'])


def downgrade() -> None:
    op.drop_table('task_custom_field_values')
    op.drop_table('project_custom_fields')
