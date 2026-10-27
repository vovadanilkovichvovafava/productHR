"""Add project management tables

Creates:
- projects: Project tracking
- project_members: User-to-project assignments
- project_milestones: Development phases
- project_tasks: Tasks within projects
- task_time_logs: Effort tracking

Revision ID: add_projects_module
Revises: add_prometheus_review_cache
Create Date: 2026-03-30
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_projects_module'
down_revision = 'add_prometheus_review_cache'
branch_labels = None
depends_on = None


def table_exists(table_name):
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = :table"
    ), {"table": table_name})
    return result.fetchone() is not None


def upgrade():
    # --- projects ---
    if not table_exists('projects'):
        op.create_table(
            'projects',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('org_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
            sa.Column('department_id', sa.Integer(), sa.ForeignKey('departments.id', ondelete='SET NULL'), nullable=True),
            sa.Column('name', sa.String(300), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('status', sa.String(20), nullable=False, server_default='planning'),
            sa.Column('priority', sa.Integer(), server_default='1'),
            sa.Column('client_name', sa.String(300), nullable=True),
            sa.Column('progress_percent', sa.Integer(), server_default='0'),
            sa.Column('progress_mode', sa.String(10), server_default='auto'),
            sa.Column('start_date', sa.DateTime(), nullable=True),
            sa.Column('target_date', sa.DateTime(), nullable=True),
            sa.Column('predicted_date', sa.DateTime(), nullable=True),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.Column('tags', sa.JSON(), server_default='[]'),
            sa.Column('extra_data', sa.JSON(), server_default='{}'),
            sa.Column('color', sa.String(20), nullable=True),
            sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        )
        op.create_index('ix_project_org_id', 'projects', ['org_id'])
        op.create_index('ix_project_department_id', 'projects', ['department_id'])
        op.create_index('ix_project_org_status', 'projects', ['org_id', 'status'])
        op.create_index('ix_project_dept_status', 'projects', ['department_id', 'status'])

    # --- project_members ---
    if not table_exists('project_members'):
        op.create_table(
            'project_members',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('role', sa.String(20), nullable=False, server_default='developer'),
            sa.Column('allocation_percent', sa.Integer(), server_default='100'),
            sa.Column('joined_at', sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint('project_id', 'user_id', name='uq_project_member'),
        )
        op.create_index('ix_pm_project_id', 'project_members', ['project_id'])
        op.create_index('ix_pm_user_id', 'project_members', ['user_id'])

    # --- project_milestones ---
    if not table_exists('project_milestones'):
        op.create_table(
            'project_milestones',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
            sa.Column('name', sa.String(300), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('target_date', sa.DateTime(), nullable=True),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.Column('sort_order', sa.Integer(), server_default='0'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        )
        op.create_index('ix_milestone_project_id', 'project_milestones', ['project_id'])

    # --- project_tasks ---
    if not table_exists('project_tasks'):
        op.create_table(
            'project_tasks',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
            sa.Column('milestone_id', sa.Integer(), sa.ForeignKey('project_milestones.id', ondelete='SET NULL'), nullable=True),
            sa.Column('title', sa.String(500), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('status', sa.String(20), nullable=False, server_default='backlog'),
            sa.Column('priority', sa.Integer(), server_default='1'),
            sa.Column('assignee_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('estimated_hours', sa.Integer(), nullable=True),
            sa.Column('due_date', sa.DateTime(), nullable=True),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.Column('sort_order', sa.Integer(), server_default='0'),
            sa.Column('tags', sa.JSON(), server_default='[]'),
            sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        )
        op.create_index('ix_task_project_id', 'project_tasks', ['project_id'])
        op.create_index('ix_task_milestone_id', 'project_tasks', ['milestone_id'])
        op.create_index('ix_task_assignee_id', 'project_tasks', ['assignee_id'])
        op.create_index('ix_task_project_status', 'project_tasks', ['project_id', 'status'])
        op.create_index('ix_task_assignee_status', 'project_tasks', ['assignee_id', 'status'])

    # --- task_time_logs ---
    if not table_exists('task_time_logs'):
        op.create_table(
            'task_time_logs',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('task_id', sa.Integer(), sa.ForeignKey('project_tasks.id', ondelete='CASCADE'), nullable=False),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('hours', sa.Integer(), nullable=False),
            sa.Column('date', sa.DateTime(), nullable=False),
            sa.Column('note', sa.String(500), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        )
        op.create_index('ix_timelog_task_id', 'task_time_logs', ['task_id'])
        op.create_index('ix_timelog_user_id', 'task_time_logs', ['user_id'])


def downgrade():
    op.drop_table('task_time_logs')
    op.drop_table('project_tasks')
    op.drop_table('project_milestones')
    op.drop_table('project_members')
    op.drop_table('projects')
