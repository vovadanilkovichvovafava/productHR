"""Add email templates and HR analytics tables

Revision ID: add_email_templates_analytics
Revises:
Create Date: 2026-01-22

New tables:
- email_templates: Email template definitions
- email_logs: Email sending history
- hr_analytics_snapshots: Periodic HR metrics
- vacancy_metrics: Per-vacancy cached metrics
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'add_email_templates_analytics'
down_revision = ('add_embeddings', 'add_compatibility_score')  # Merge two branches
branch_labels = None
depends_on = None


def upgrade():
    # Create enum types
    email_template_type = postgresql.ENUM(
        'interview_invite', 'interview_reminder', 'offer', 'rejection',
        'screening_request', 'test_assignment', 'welcome', 'follow_up', 'custom',
        name='emailtemplatetype',
        create_type=False
    )

    email_status = postgresql.ENUM(
        'pending', 'sent', 'delivered', 'opened', 'clicked', 'bounced', 'failed',
        name='emailstatus',
        create_type=False
    )

    snapshot_period = postgresql.ENUM(
        'daily', 'weekly', 'monthly',
        name='snapshotperiod',
        create_type=False
    )

    # Create enums
    op.execute("CREATE TYPE emailtemplatetype AS ENUM ('interview_invite', 'interview_reminder', 'offer', 'rejection', 'screening_request', 'test_assignment', 'welcome', 'follow_up', 'custom')")
    op.execute("CREATE TYPE emailstatus AS ENUM ('pending', 'sent', 'delivered', 'opened', 'clicked', 'bounced', 'failed')")
    op.execute("CREATE TYPE snapshotperiod AS ENUM ('daily', 'weekly', 'monthly')")

    # Create email_templates table
    op.create_table(
        'email_templates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('org_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('template_type', sa.Enum('interview_invite', 'interview_reminder', 'offer', 'rejection', 'screening_request', 'test_assignment', 'welcome', 'follow_up', 'custom', name='emailtemplatetype'), default='custom', index=True),
        sa.Column('subject', sa.String(500), nullable=False),
        sa.Column('body_html', sa.Text(), nullable=False),
        sa.Column('body_text', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('is_default', sa.Boolean(), default=False),
        sa.Column('variables', sa.JSON(), default=list),
        sa.Column('tags', sa.JSON(), default=list),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('updated_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint('org_id', 'name', name='uq_email_template_name'),
    )
    op.create_index('ix_email_template_org_type', 'email_templates', ['org_id', 'template_type'])

    # Create email_logs table
    op.create_table(
        'email_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('org_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('template_id', sa.Integer(), sa.ForeignKey('email_templates.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('template_name', sa.String(255), nullable=True),
        sa.Column('template_type', sa.Enum('interview_invite', 'interview_reminder', 'offer', 'rejection', 'screening_request', 'test_assignment', 'welcome', 'follow_up', 'custom', name='emailtemplatetype'), nullable=True),
        sa.Column('entity_id', sa.Integer(), sa.ForeignKey('entities.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('recipient_email', sa.String(255), nullable=False),
        sa.Column('recipient_name', sa.String(255), nullable=True),
        sa.Column('vacancy_id', sa.Integer(), sa.ForeignKey('vacancies.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('application_id', sa.Integer(), sa.ForeignKey('vacancy_applications.id', ondelete='SET NULL'), nullable=True),
        sa.Column('subject', sa.String(500), nullable=False),
        sa.Column('body_html', sa.Text(), nullable=True),
        sa.Column('variables_used', sa.JSON(), default=dict),
        sa.Column('status', sa.Enum('pending', 'sent', 'delivered', 'opened', 'clicked', 'bounced', 'failed', name='emailstatus'), default='pending', index=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('delivered_at', sa.DateTime(), nullable=True),
        sa.Column('opened_at', sa.DateTime(), nullable=True),
        sa.Column('clicked_at', sa.DateTime(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), default=0),
        sa.Column('message_id', sa.String(255), nullable=True),
        sa.Column('sent_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_email_log_entity', 'email_logs', ['entity_id', 'created_at'])
    op.create_index('ix_email_log_vacancy', 'email_logs', ['vacancy_id', 'created_at'])
    op.create_index('ix_email_log_status_date', 'email_logs', ['org_id', 'status', 'created_at'])

    # Create hr_analytics_snapshots table
    op.create_table(
        'hr_analytics_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('org_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('department_id', sa.Integer(), sa.ForeignKey('departments.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('period_type', sa.Enum('daily', 'weekly', 'monthly', name='snapshotperiod'), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('vacancies_total', sa.Integer(), default=0),
        sa.Column('vacancies_open', sa.Integer(), default=0),
        sa.Column('vacancies_closed', sa.Integer(), default=0),
        sa.Column('vacancies_new', sa.Integer(), default=0),
        sa.Column('avg_time_to_fill_days', sa.Float(), nullable=True),
        sa.Column('applications_total', sa.Integer(), default=0),
        sa.Column('applications_new', sa.Integer(), default=0),
        sa.Column('applications_hired', sa.Integer(), default=0),
        sa.Column('applications_rejected', sa.Integer(), default=0),
        sa.Column('funnel_data', sa.JSON(), default=dict),
        sa.Column('conversion_rates', sa.JSON(), default=dict),
        sa.Column('source_breakdown', sa.JSON(), default=dict),
        sa.Column('avg_time_in_stage_days', sa.JSON(), default=dict),
        sa.Column('department_breakdown', sa.JSON(), default=dict),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('computed_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('org_id', 'department_id', 'period_type', 'period_start', name='uq_analytics_snapshot'),
    )
    op.create_index('ix_analytics_snapshot_period', 'hr_analytics_snapshots', ['org_id', 'period_type', 'period_start'])

    # Create vacancy_metrics table
    op.create_table(
        'vacancy_metrics',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('vacancy_id', sa.Integer(), sa.ForeignKey('vacancies.id', ondelete='CASCADE'), nullable=False, unique=True, index=True),
        sa.Column('stage_counts', sa.JSON(), default=dict),
        sa.Column('avg_time_to_stage_days', sa.JSON(), default=dict),
        sa.Column('source_stats', sa.JSON(), default=dict),
        sa.Column('score_distribution', sa.JSON(), default=dict),
        sa.Column('avg_compatibility_score', sa.Float(), nullable=True),
        sa.Column('days_open', sa.Integer(), nullable=True),
        sa.Column('estimated_days_to_fill', sa.Integer(), nullable=True),
        sa.Column('avg_rating', sa.Float(), nullable=True),
        sa.Column('computed_at', sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table('vacancy_metrics')
    op.drop_table('hr_analytics_snapshots')
    op.drop_table('email_logs')
    op.drop_table('email_templates')

    op.execute("DROP TYPE IF EXISTS snapshotperiod")
    op.execute("DROP TYPE IF EXISTS emailstatus")
    op.execute("DROP TYPE IF EXISTS emailtemplatetype")
