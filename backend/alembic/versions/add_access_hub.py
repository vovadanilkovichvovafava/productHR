"""Хаб доступов: каталог ресурсов, гранты ролям, заявки, аудит

Revision ID: add_access_hub
Revises: add_form_template_is_template
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_access_hub'
down_revision = 'add_form_template_is_template'
branch_labels = None
depends_on = None


def _has_table(conn, name: str) -> bool:
    return bool(conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = :n"
    ), {"n": name}).scalar())


def upgrade():
    # Идемпотентно: схему в этом проекте фактически материализует Base.metadata
    # create_all на старте, поэтому таблицы могут уже существовать к моменту
    # прогона миграции. Без проверок ревизия падала бы на DuplicateTable.
    conn = op.get_bind()

    if not _has_table(conn, 'resource_catalog'):
        op.create_table(
            'resource_catalog',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('org_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
            sa.Column('key', sa.String(64), nullable=False),
            sa.Column('name', sa.String(200), nullable=False),
            sa.Column('category', sa.String(32), nullable=False, server_default='other'),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('responsible_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('params_schema', sa.JSON(), nullable=True),
            sa.Column('unlock_condition', sa.String(40), nullable=False, server_default='always'),
            sa.Column('limit_per_month', sa.Integer(), nullable=True),
            sa.Column('limit_amount_month', sa.Integer(), nullable=True),
            sa.Column('currency', sa.String(8), nullable=True, server_default='RUB'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint('org_id', 'key', name='uq_resource_catalog_org_key'),
        )
        op.create_index('ix_resource_catalog_org_active', 'resource_catalog', ['org_id', 'is_active'])
        op.create_index('ix_resource_catalog_org_id', 'resource_catalog', ['org_id'])

    if not _has_table(conn, 'role_resource_grants'):
        op.create_table(
            'role_resource_grants',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('role_id', sa.Integer(), sa.ForeignKey('custom_roles.id', ondelete='CASCADE'), nullable=False),
            sa.Column('resource_id', sa.Integer(), sa.ForeignKey('resource_catalog.id', ondelete='CASCADE'), nullable=False),
            sa.Column('can_request', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint('role_id', 'resource_id', name='uq_role_resource_grant'),
        )

    if not _has_table(conn, 'access_requests'):
        op.create_table(
            'access_requests',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('org_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
            sa.Column('requester_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('target_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
            sa.Column('resource_id', sa.Integer(), sa.ForeignKey('resource_catalog.id', ondelete='RESTRICT'), nullable=False),
            sa.Column('company_unit_id', sa.Integer(), sa.ForeignKey('org_units.id', ondelete='SET NULL'), nullable=True),
            sa.Column('params', sa.JSON(), nullable=True),
            sa.Column('comment', sa.Text(), nullable=True),
            sa.Column('status', sa.String(20), nullable=False, server_default='new'),
            sa.Column('assignee_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('amount', sa.Integer(), nullable=True),
            sa.Column('currency', sa.String(8), nullable=True),
            sa.Column('decided_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('decided_at', sa.DateTime(), nullable=True),
            sa.Column('decision_comment', sa.Text(), nullable=True),
            sa.Column('granted_at', sa.DateTime(), nullable=True),
            sa.Column('revoked_at', sa.DateTime(), nullable=True),
            sa.Column('revoke_reason', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        )
        op.create_index('ix_access_request_org_status', 'access_requests', ['org_id', 'status'])
        op.create_index('ix_access_request_assignee_status', 'access_requests', ['assignee_user_id', 'status'])
        op.create_index('ix_access_request_target_status', 'access_requests', ['target_user_id', 'status'])

    if not _has_table(conn, 'access_request_audit'):
        op.create_table(
            'access_request_audit',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('request_id', sa.Integer(), sa.ForeignKey('access_requests.id', ondelete='CASCADE'), nullable=False),
            sa.Column('org_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
            sa.Column('from_status', sa.String(20), nullable=True),
            sa.Column('to_status', sa.String(20), nullable=False),
            sa.Column('action', sa.String(30), nullable=False),
            sa.Column('changed_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('comment', sa.Text(), nullable=True),
            sa.Column('details', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        )
        op.create_index('ix_access_audit_request_created', 'access_request_audit', ['request_id', 'created_at'])


def downgrade():
    op.drop_table('access_request_audit')
    op.drop_table('access_requests')
    op.drop_table('role_resource_grants')
    op.drop_table('resource_catalog')
