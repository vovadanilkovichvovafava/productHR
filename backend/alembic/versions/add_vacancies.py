"""Add vacancy management tables

Creates:
- vacancies: Job openings/positions
- vacancy_applications: Candidate pipeline tracking

Revision ID: add_vacancies
Revises: add_entity_ai_memory
Create Date: 2026-01-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'add_vacancies'
down_revision = 'add_must_change_pwd'  # Fixed: was add_entity_ai_memory, now follows linear chain
branch_labels = None
depends_on = None


def table_exists(table_name):
    """Check if a table exists."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = :table"
    ), {"table": table_name})
    return result.fetchone() is not None


def enum_exists(enum_name):
    """Check if an enum type exists."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_type WHERE typname = :name"
    ), {"name": enum_name})
    return result.fetchone() is not None


def upgrade():
    """Create vacancy management tables."""

    # Create VacancyStatus enum
    if not enum_exists('vacancystatus'):
        op.execute("""
            CREATE TYPE vacancystatus AS ENUM (
                'draft', 'open', 'paused', 'closed', 'cancelled'
            )
        """)

    # Create ApplicationStage enum
    if not enum_exists('applicationstage'):
        op.execute("""
            CREATE TYPE applicationstage AS ENUM (
                'applied', 'screening', 'phone_screen', 'interview',
                'assessment', 'offer', 'hired', 'rejected', 'withdrawn'
            )
        """)

    # Create vacancies table
    if not table_exists('vacancies'):
        op.create_table(
            'vacancies',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('org_id', sa.Integer(), nullable=True),
            sa.Column('department_id', sa.Integer(), nullable=True),
            sa.Column('title', sa.String(255), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('requirements', sa.Text(), nullable=True),
            sa.Column('responsibilities', sa.Text(), nullable=True),
            sa.Column('salary_min', sa.Integer(), nullable=True),
            sa.Column('salary_max', sa.Integer(), nullable=True),
            sa.Column('salary_currency', sa.String(10), server_default='RUB'),
            sa.Column('location', sa.String(255), nullable=True),
            sa.Column('employment_type', sa.String(50), nullable=True),
            sa.Column('experience_level', sa.String(50), nullable=True),
            sa.Column('status', postgresql.ENUM('draft', 'open', 'paused', 'closed', 'cancelled', name='vacancystatus', create_type=False), server_default='draft'),
            sa.Column('priority', sa.Integer(), server_default='0'),
            sa.Column('tags', postgresql.JSON(astext_type=sa.Text()), server_default='[]'),
            sa.Column('extra_data', postgresql.JSON(astext_type=sa.Text()), server_default='{}'),
            sa.Column('hiring_manager_id', sa.Integer(), nullable=True),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.Column('published_at', sa.DateTime(), nullable=True),
            sa.Column('closes_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['hiring_manager_id'], ['users.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_vacancies_org_id', 'vacancies', ['org_id'])
        op.create_index('ix_vacancies_department_id', 'vacancies', ['department_id'])
        op.create_index('ix_vacancies_status', 'vacancies', ['status'])
        op.create_index('ix_vacancies_title', 'vacancies', ['title'])

    # Create vacancy_applications table
    if not table_exists('vacancy_applications'):
        op.create_table(
            'vacancy_applications',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('vacancy_id', sa.Integer(), nullable=False),
            sa.Column('entity_id', sa.Integer(), nullable=False),
            sa.Column('stage', postgresql.ENUM('applied', 'screening', 'phone_screen', 'interview', 'assessment', 'offer', 'hired', 'rejected', 'withdrawn', name='applicationstage', create_type=False), server_default='applied'),
            sa.Column('stage_order', sa.Integer(), server_default='0'),
            sa.Column('rating', sa.Integer(), nullable=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('rejection_reason', sa.String(255), nullable=True),
            sa.Column('source', sa.String(100), nullable=True),
            sa.Column('next_interview_at', sa.DateTime(), nullable=True),
            sa.Column('applied_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('last_stage_change_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['vacancy_id'], ['vacancies.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('vacancy_id', 'entity_id', name='uq_vacancy_application')
        )
        op.create_index('ix_vacancy_applications_vacancy_id', 'vacancy_applications', ['vacancy_id'])
        op.create_index('ix_vacancy_applications_entity_id', 'vacancy_applications', ['entity_id'])
        op.create_index('ix_vacancy_applications_stage', 'vacancy_applications', ['stage'])
        op.create_index('ix_vacancy_application_stage', 'vacancy_applications', ['vacancy_id', 'stage'])


def downgrade():
    """Remove vacancy management tables."""
    op.drop_table('vacancy_applications')
    op.drop_table('vacancies')
    op.execute('DROP TYPE IF EXISTS applicationstage')
    op.execute('DROP TYPE IF EXISTS vacancystatus')
