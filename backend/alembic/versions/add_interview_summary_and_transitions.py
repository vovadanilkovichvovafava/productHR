"""Add interview_summary to vacancy_applications and stage_transitions table

Creates:
- interview_summary column on vacancy_applications
- stage_transitions table for audit logging of stage changes

Revision ID: a3f7c9e1b204
Revises: add_recruiter_bonuses
Create Date: 2026-04-06
"""
from alembic import op
import sqlalchemy as sa

revision = 'a3f7c9e1b204'
down_revision = 'add_recruiter_bonuses'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add interview_summary to vacancy_applications
    op.add_column(
        'vacancy_applications',
        sa.Column('interview_summary', sa.Text(), nullable=True)
    )

    # Create stage_transitions audit log table
    op.create_table(
        'stage_transitions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('application_id', sa.Integer(),
                  sa.ForeignKey('vacancy_applications.id', ondelete='CASCADE'), nullable=False),
        sa.Column('entity_id', sa.Integer(),
                  sa.ForeignKey('entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('from_stage', sa.String(50), nullable=True),
        sa.Column('to_stage', sa.String(50), nullable=False),
        sa.Column('changed_by', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_stage_transitions_application_id', 'stage_transitions', ['application_id'])
    op.create_index('ix_stage_transitions_entity_id', 'stage_transitions', ['entity_id'])


def downgrade() -> None:
    op.drop_table('stage_transitions')
    op.drop_column('vacancy_applications', 'interview_summary')
