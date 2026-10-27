"""Add document_templates and signed_documents tables

Creates:
- document_templates: Templates for NDA, contracts, etc.
- signed_documents: Signed document instances with canvas signature

Revision ID: add_document_signing
Revises: add_employees_and_leave
Create Date: 2026-04-03
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_document_signing'
down_revision = 'add_employees_and_leave'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Document templates table
    op.create_table(
        'document_templates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('org_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(300), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('variables', sa.JSON(), server_default='[]'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_document_templates_org_id', 'document_templates', ['org_id'])

    # Signed documents table
    op.create_table(
        'signed_documents',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('template_id', sa.Integer(), sa.ForeignKey('document_templates.id', ondelete='SET NULL'), nullable=True),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(300), nullable=False),
        sa.Column('content_rendered', sa.Text(), nullable=False),
        sa.Column('signature_data', sa.Text(), nullable=True),
        sa.Column('signed_at', sa.DateTime(), nullable=True),
        sa.Column('signer_ip', sa.String(50), nullable=True),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_signed_documents_employee_id', 'signed_documents', ['employee_id'])


def downgrade() -> None:
    op.drop_table('signed_documents')
    op.drop_table('document_templates')
