"""Add custom_stages, kanban_card_fields to vacancies + form_vacancy junction table

Revision ID: add_funnel_customization
Revises: add_vacancy_sharing
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_funnel_customization'
down_revision = 'b5e2a1d3c908'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Add custom funnel fields to vacancies (idempotent)
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns WHERE table_name='vacancies' AND column_name='custom_stages'"
    ))
    if not result.fetchone():
        op.add_column('vacancies', sa.Column('custom_stages', sa.JSON(), nullable=True))

    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns WHERE table_name='vacancies' AND column_name='kanban_card_fields'"
    ))
    if not result.fetchone():
        op.add_column('vacancies', sa.Column('kanban_card_fields', sa.JSON(), nullable=True))

    # Create form_vacancy junction table (many-to-many: form <-> vacancy)
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name='form_vacancy'"
    ))
    if not result.fetchone():
        op.create_table(
            'form_vacancy',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('form_id', sa.Integer(), sa.ForeignKey('form_templates.id', ondelete='CASCADE'), nullable=False),
            sa.Column('vacancy_id', sa.Integer(), sa.ForeignKey('vacancies.id', ondelete='CASCADE'), nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint('form_id', 'vacancy_id', name='uq_form_vacancy'),
        )
        op.create_index('ix_form_vacancy_form_id', 'form_vacancy', ['form_id'])
        op.create_index('ix_form_vacancy_vacancy_id', 'form_vacancy', ['vacancy_id'])

    # Migrate existing form_templates.vacancy_id data to junction table
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns WHERE table_name='form_templates' AND column_name='vacancy_id'"
    ))
    if result.fetchone():
        op.execute("""
            INSERT INTO form_vacancy (form_id, vacancy_id)
            SELECT id, vacancy_id FROM form_templates
            WHERE vacancy_id IS NOT NULL
            ON CONFLICT DO NOTHING
        """)


def downgrade() -> None:
    op.drop_table('form_vacancy')
    op.drop_column('vacancies', 'kanban_card_fields')
    op.drop_column('vacancies', 'custom_stages')
