"""Add multiple identifiers to Entity (telegram_usernames, emails, phones)

Revision ID: add_entity_multiple_ids
Revises: add_entity_transfer
Create Date: 2025-12-25

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'add_entity_multiple_ids'
down_revision = 'add_impersonation_logs'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in the table."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns WHERE table_name = :table AND column_name = :column"
    ), {"table": table_name, "column": column_name})
    return result.fetchone() is not None


def upgrade():
    """Add telegram_usernames, emails, phones JSON columns and migrate existing data."""

    # Add new JSON columns with default empty arrays
    if not column_exists('entities', 'telegram_usernames'):
        op.add_column('entities', sa.Column('telegram_usernames', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    if not column_exists('entities', 'emails'):
        op.add_column('entities', sa.Column('emails', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    if not column_exists('entities', 'phones'):
        op.add_column('entities', sa.Column('phones', postgresql.JSON(astext_type=sa.Text()), nullable=True))

    # Migrate existing data: move email to emails[], phone to phones[]
    # This uses PostgreSQL's JSONB functions to create arrays from single values
    # Only run if columns were just created (data might already be migrated)
    op.execute("""
        UPDATE entities
        SET emails = CASE
            WHEN email IS NOT NULL AND email != '' THEN to_jsonb(ARRAY[email])
            ELSE '[]'::jsonb
        END
        WHERE emails IS NULL
    """)

    op.execute("""
        UPDATE entities
        SET phones = CASE
            WHEN phone IS NOT NULL AND phone != '' THEN to_jsonb(ARRAY[phone])
            ELSE '[]'::jsonb
        END
        WHERE phones IS NULL
    """)

    # Set telegram_usernames to empty array for all rows
    op.execute("""
        UPDATE entities
        SET telegram_usernames = '[]'::jsonb
        WHERE telegram_usernames IS NULL
    """)

    # Set default values for new rows
    op.alter_column('entities', 'telegram_usernames', server_default='[]')
    op.alter_column('entities', 'emails', server_default='[]')
    op.alter_column('entities', 'phones', server_default='[]')


def downgrade():
    """Remove multiple identifier columns and migrate data back to single fields."""

    # Migrate data back: take first element from arrays
    # Only update if the single field is NULL and array has elements
    op.execute("""
        UPDATE entities
        SET email = CASE
            WHEN email IS NULL AND jsonb_array_length(emails) > 0
            THEN emails->>0
            ELSE email
        END
    """)

    op.execute("""
        UPDATE entities
        SET phone = CASE
            WHEN phone IS NULL AND jsonb_array_length(phones) > 0
            THEN phones->>0
            ELSE phone
        END
    """)

    # Drop the new columns
    op.drop_column('entities', 'phones')
    op.drop_column('entities', 'emails')
    op.drop_column('entities', 'telegram_usernames')
