"""add is_template to form_templates

Revision ID: add_form_template_is_template
Revises: add_form_dispatches
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_form_template_is_template'
# ИСПРАВЛЕНО: было 'add_custom_roles' — в её истории таблицы form_templates ещё
# НЕ существует (её создаёт add_form_templates), поэтому ветка топологически шла
# раньше таблицы и на чистой БД падала UndefinedTable. Плюс это была вторая
# head-ревизия: `alembic upgrade head` выдавал "Multiple head revisions",
# ошибка глушилась в start.sh и миграции молча не применялись вообще.
# Перепривязка к текущему head решает обе проблемы разом — без merge-ревизии.
down_revision = 'add_form_dispatches'
branch_labels = None
depends_on = None


def upgrade():
    # Идемпотентно: ту же колонку уже добавляет ручной блок в start.sh, поэтому
    # без проверки миграция падала бы с DuplicateColumn на существующей БД.
    conn = op.get_bind()
    exists = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'form_templates' AND column_name = 'is_template'"
    )).scalar()
    if not exists:
        op.add_column(
            'form_templates',
            sa.Column('is_template', sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade():
    op.drop_column('form_templates', 'is_template')
