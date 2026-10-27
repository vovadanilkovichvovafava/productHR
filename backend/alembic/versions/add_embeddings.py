"""Add embeddings for similarity search

Adds pgvector extension and embedding columns for AI-powered similarity search.

Creates:
- vector extension (pgvector)
- entities.embedding (vector(1536)) - OpenAI embedding dimension
- entities.embedding_updated_at (DateTime)
- vacancies.embedding (vector(1536))
- vacancies.embedding_updated_at (DateTime)
- IVFFlat indexes for fast similarity search

Revision ID: add_embeddings
Revises: add_parse_jobs
Create Date: 2026-01-29
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_embeddings'
down_revision = 'add_parse_jobs'
branch_labels = None
depends_on = None


def extension_exists(extension_name):
    """Check if a PostgreSQL extension exists."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_extension WHERE extname = :name"
    ), {"name": extension_name})
    return result.fetchone() is not None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns WHERE table_name = :table AND column_name = :column"
    ), {"table": table_name, "column": column_name})
    return result.fetchone() is not None


def index_exists(index_name):
    """Check if an index exists."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_indexes WHERE indexname = :name"
    ), {"name": index_name})
    return result.fetchone() is not None


def upgrade():
    """Add pgvector extension and embedding columns."""

    # Enable pgvector extension
    # Railway PostgreSQL supports pgvector out of the box
    try:
        if not extension_exists('vector'):
            op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    except Exception as e:
        print(f"Warning: Could not create pgvector extension: {e}")
        print("Embeddings will not be available. Install pgvector to enable.")
        return  # Skip rest of migration if pgvector not available

    # Add embedding columns to entities
    if not column_exists('entities', 'embedding'):
        op.execute('ALTER TABLE entities ADD COLUMN embedding vector(1536)')

    if not column_exists('entities', 'embedding_updated_at'):
        op.add_column('entities', sa.Column('embedding_updated_at', sa.DateTime(), nullable=True))

    # Add embedding columns to vacancies
    if not column_exists('vacancies', 'embedding'):
        op.execute('ALTER TABLE vacancies ADD COLUMN embedding vector(1536)')

    if not column_exists('vacancies', 'embedding_updated_at'):
        op.add_column('vacancies', sa.Column('embedding_updated_at', sa.DateTime(), nullable=True))

    # Create IVFFlat indexes for fast similarity search
    # Note: IVFFlat requires existing data for optimal performance.
    # For tables with <1000 rows, consider using HNSW instead.
    # lists=100 is good for tables with 10k-100k rows.

    if not index_exists('ix_entities_embedding'):
        op.execute('''
            CREATE INDEX ix_entities_embedding ON entities
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        ''')

    if not index_exists('ix_vacancies_embedding'):
        op.execute('''
            CREATE INDEX ix_vacancies_embedding ON vacancies
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        ''')


def downgrade():
    """Remove embedding columns and pgvector extension."""

    # Drop indexes first
    if index_exists('ix_vacancies_embedding'):
        op.drop_index('ix_vacancies_embedding', table_name='vacancies')

    if index_exists('ix_entities_embedding'):
        op.drop_index('ix_entities_embedding', table_name='entities')

    # Drop columns from vacancies
    if column_exists('vacancies', 'embedding_updated_at'):
        op.drop_column('vacancies', 'embedding_updated_at')

    if column_exists('vacancies', 'embedding'):
        op.drop_column('vacancies', 'embedding')

    # Drop columns from entities
    if column_exists('entities', 'embedding_updated_at'):
        op.drop_column('entities', 'embedding_updated_at')

    if column_exists('entities', 'embedding'):
        op.drop_column('entities', 'embedding')

    # Note: We don't drop the vector extension as it might be used by other tables
    # If you want to drop it, uncomment the line below:
    # op.execute('DROP EXTENSION IF EXISTS vector')
