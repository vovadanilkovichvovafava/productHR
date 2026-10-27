"""Add recruiter_bonuses table for PEN dashboard

Creates:
- recruiter_bonuses: Tracks recruiter bonus accruals per candidate

Revision ID: add_recruiter_bonuses
Revises: add_document_signing
Create Date: 2026-04-06
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_recruiter_bonuses'
down_revision = 'add_document_signing'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'recruiter_bonuses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('org_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('recruiter_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('entity_id', sa.Integer(), sa.ForeignKey('entities.id', ondelete='SET NULL'), nullable=True),
        sa.Column('direction', sa.String(30), nullable=False),
        sa.Column('stage', sa.String(30), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('is_paid', sa.Boolean(), server_default='false'),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_recruiter_bonuses_org_id', 'recruiter_bonuses', ['org_id'])
    op.create_index('ix_recruiter_bonuses_recruiter_id', 'recruiter_bonuses', ['recruiter_id'])


def downgrade() -> None:
    op.drop_table('recruiter_bonuses')
