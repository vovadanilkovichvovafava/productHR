"""Initial migration

Revision ID: 3908ad1d4246
Revises:
Create Date: 2025-12-23 19:41:10.217243

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '3908ad1d4246'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()

    # Check if tables already exist (idempotent migration)
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = 'users'"
    ))
    if result.fetchone() is not None:
        # Tables already exist, skip creation
        return

    # Create enums using raw SQL with IF NOT EXISTS for PostgreSQL compatibility
    # This is more reliable than checkfirst with asyncpg
    enum_types = [
        ("userrole", ['superadmin', 'admin']),
        ("chattype", ['work', 'hr', 'project', 'client', 'contractor', 'sales', 'support', 'custom']),
        ("entitytype", ['candidate', 'client', 'contractor', 'lead', 'partner', 'custom']),
        ("entitystatus", ['new', 'screening', 'interview', 'offer', 'hired', 'rejected', 'active', 'paused', 'churned', 'converted', 'ended', 'negotiation']),
        ("callsource", ['meet', 'zoom', 'teams', 'upload', 'telegram']),
        ("callstatus", ['pending', 'connecting', 'recording', 'processing', 'transcribing', 'analyzing', 'done', 'failed']),
        ("reporttype", ['daily_hr', 'weekly_summary', 'daily_calls', 'weekly_pipeline']),
        ("deliverymethod", ['telegram', 'email']),
        ("orgrole", ['owner', 'admin', 'member']),
        ("deptrole", ['lead', 'member']),
        ("subscriptionplan", ['free', 'pro', 'enterprise']),
        ("resourcetype", ['chat', 'entity', 'call']),
        ("accesslevel", ['view', 'edit', 'full']),
    ]

    for enum_name, values in enum_types:
        # Check if type exists before creating
        result = conn.execute(sa.text(
            "SELECT 1 FROM pg_type WHERE typname = :name"
        ), {"name": enum_name})
        if not result.fetchone():
            values_str = ", ".join(f"'{v}'" for v in values)
            conn.execute(sa.text(f"CREATE TYPE {enum_name} AS ENUM ({values_str})"))

    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('role', postgresql.ENUM('superadmin', 'admin', name='userrole', create_type=False), nullable=True),
        sa.Column('telegram_id', sa.BigInteger(), nullable=True),
        sa.Column('telegram_username', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('telegram_id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_telegram_id'), 'users', ['telegram_id'], unique=True)

    # Create organizations table
    op.create_table(
        'organizations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('subscription_plan', postgresql.ENUM('free', 'pro', 'enterprise', name='subscriptionplan', create_type=False), nullable=True),
        sa.Column('settings', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug')
    )
    op.create_index(op.f('ix_organizations_slug'), 'organizations', ['slug'], unique=True)

    # Create org_members table
    op.create_table(
        'org_members',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('org_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', postgresql.ENUM('owner', 'admin', 'member', name='orgrole', create_type=False), nullable=True),
        sa.Column('invited_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['invited_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_org_members_org_id'), 'org_members', ['org_id'], unique=False)
    op.create_index(op.f('ix_org_members_user_id'), 'org_members', ['user_id'], unique=False)

    # Create departments table
    op.create_table(
        'departments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('org_id', sa.Integer(), nullable=False),
        sa.Column('parent_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('color', sa.String(length=20), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_id'], ['departments.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_departments_org_id'), 'departments', ['org_id'], unique=False)
    op.create_index(op.f('ix_departments_parent_id'), 'departments', ['parent_id'], unique=False)

    # Create department_members table
    op.create_table(
        'department_members',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', postgresql.ENUM('lead', 'member', name='deptrole', create_type=False), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_department_members_department_id'), 'department_members', ['department_id'], unique=False)
    op.create_index(op.f('ix_department_members_user_id'), 'department_members', ['user_id'], unique=False)

    # Create entities table
    op.create_table(
        'entities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('org_id', sa.Integer(), nullable=True),
        sa.Column('department_id', sa.Integer(), nullable=True),
        sa.Column('type', postgresql.ENUM('candidate', 'client', 'contractor', 'lead', 'partner', 'custom', name='entitytype', create_type=False), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('status', postgresql.ENUM('new', 'screening', 'interview', 'offer', 'hired', 'rejected', 'active', 'paused', 'churned', 'converted', 'ended', 'negotiation', name='entitystatus', create_type=False), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('telegram_user_id', sa.BigInteger(), nullable=True),
        sa.Column('company', sa.String(length=255), nullable=True),
        sa.Column('position', sa.String(length=255), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('extra_data', sa.JSON(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_entities_department_id'), 'entities', ['department_id'], unique=False)
    op.create_index(op.f('ix_entities_org_id'), 'entities', ['org_id'], unique=False)
    op.create_index(op.f('ix_entities_status'), 'entities', ['status'], unique=False)
    op.create_index(op.f('ix_entities_telegram_user_id'), 'entities', ['telegram_user_id'], unique=False)
    op.create_index(op.f('ix_entities_type'), 'entities', ['type'], unique=False)

    # Create entity_transfers table
    op.create_table(
        'entity_transfers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('from_user_id', sa.Integer(), nullable=True),
        sa.Column('to_user_id', sa.Integer(), nullable=True),
        sa.Column('from_department_id', sa.Integer(), nullable=True),
        sa.Column('to_department_id', sa.Integer(), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['from_department_id'], ['departments.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['from_user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['to_department_id'], ['departments.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['to_user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_entity_transfers_entity_id'), 'entity_transfers', ['entity_id'], unique=False)
    op.create_index(op.f('ix_entity_transfers_from_department_id'), 'entity_transfers', ['from_department_id'], unique=False)
    op.create_index(op.f('ix_entity_transfers_to_department_id'), 'entity_transfers', ['to_department_id'], unique=False)

    # Create chats table
    op.create_table(
        'chats',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('org_id', sa.Integer(), nullable=True),
        sa.Column('telegram_chat_id', sa.BigInteger(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('custom_name', sa.String(length=255), nullable=True),
        sa.Column('chat_type', postgresql.ENUM('work', 'hr', 'project', 'client', 'contractor', 'sales', 'support', 'custom', name='chattype', create_type=False), nullable=True),
        sa.Column('custom_type_name', sa.String(length=255), nullable=True),
        sa.Column('custom_type_description', sa.Text(), nullable=True),
        sa.Column('owner_id', sa.Integer(), nullable=True),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('last_activity', sa.DateTime(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('telegram_chat_id')
    )
    op.create_index(op.f('ix_chats_chat_type'), 'chats', ['chat_type'], unique=False)
    op.create_index(op.f('ix_chats_deleted_at'), 'chats', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_chats_entity_id'), 'chats', ['entity_id'], unique=False)
    op.create_index(op.f('ix_chats_org_id'), 'chats', ['org_id'], unique=False)
    op.create_index(op.f('ix_chats_owner_id'), 'chats', ['owner_id'], unique=False)
    op.create_index(op.f('ix_chats_telegram_chat_id'), 'chats', ['telegram_chat_id'], unique=True)

    # Create messages table
    op.create_table(
        'messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('chat_id', sa.Integer(), nullable=False),
        sa.Column('telegram_message_id', sa.BigInteger(), nullable=True),
        sa.Column('telegram_user_id', sa.BigInteger(), nullable=False),
        sa.Column('username', sa.String(length=255), nullable=True),
        sa.Column('first_name', sa.String(length=255), nullable=True),
        sa.Column('last_name', sa.String(length=255), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('content_type', sa.String(length=50), nullable=False),
        sa.Column('file_id', sa.String(length=255), nullable=True),
        sa.Column('file_path', sa.String(length=512), nullable=True),
        sa.Column('file_name', sa.String(length=255), nullable=True),
        sa.Column('document_metadata', sa.JSON(), nullable=True),
        sa.Column('parse_status', sa.String(length=20), nullable=True),
        sa.Column('parse_error', sa.Text(), nullable=True),
        sa.Column('is_imported', sa.Boolean(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['chat_id'], ['chats.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_messages_chat_id'), 'messages', ['chat_id'], unique=False)
    op.create_index(op.f('ix_messages_telegram_user_id'), 'messages', ['telegram_user_id'], unique=False)

    # Create criteria_presets table
    op.create_table(
        'criteria_presets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('criteria', sa.JSON(), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('chat_type', postgresql.ENUM('work', 'hr', 'project', 'client', 'contractor', 'sales', 'support', 'custom', name='chattype', create_type=False), nullable=True),
        sa.Column('is_global', sa.Boolean(), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_criteria_presets_chat_type'), 'criteria_presets', ['chat_type'], unique=False)

    # Create chat_criteria table
    op.create_table(
        'chat_criteria',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('chat_id', sa.Integer(), nullable=False),
        sa.Column('criteria', sa.JSON(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['chat_id'], ['chats.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('chat_id')
    )

    # Create ai_conversations table
    op.create_table(
        'ai_conversations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('chat_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('messages', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['chat_id'], ['chats.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ai_conversations_chat_id'), 'ai_conversations', ['chat_id'], unique=False)
    op.create_index(op.f('ix_ai_conversations_user_id'), 'ai_conversations', ['user_id'], unique=False)

    # Create analysis_history table
    op.create_table(
        'analysis_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('chat_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column('result', sa.Text(), nullable=False),
        sa.Column('report_type', sa.String(length=50), nullable=True),
        sa.Column('report_format', sa.String(length=20), nullable=True),
        sa.Column('criteria_used', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['chat_id'], ['chats.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_analysis_history_chat_id'), 'analysis_history', ['chat_id'], unique=False)
    op.create_index(op.f('ix_analysis_history_entity_id'), 'analysis_history', ['entity_id'], unique=False)

    # Create call_recordings table
    op.create_table(
        'call_recordings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('org_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=True),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column('owner_id', sa.Integer(), nullable=True),
        sa.Column('source_type', postgresql.ENUM('meet', 'zoom', 'teams', 'upload', 'telegram', name='callsource', create_type=False), nullable=False),
        sa.Column('source_url', sa.String(length=500), nullable=True),
        sa.Column('bot_name', sa.String(length=100), nullable=True),
        sa.Column('status', postgresql.ENUM('pending', 'connecting', 'recording', 'processing', 'transcribing', 'analyzing', 'done', 'failed', name='callstatus', create_type=False), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('audio_file_path', sa.String(length=500), nullable=True),
        sa.Column('fireflies_transcript_id', sa.String(length=100), nullable=True),
        sa.Column('transcript', sa.Text(), nullable=True),
        sa.Column('speakers', sa.JSON(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('action_items', sa.JSON(), nullable=True),
        sa.Column('key_points', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_call_recordings_entity_id'), 'call_recordings', ['entity_id'], unique=False)
    op.create_index(op.f('ix_call_recordings_fireflies_transcript_id'), 'call_recordings', ['fireflies_transcript_id'], unique=False)
    op.create_index(op.f('ix_call_recordings_org_id'), 'call_recordings', ['org_id'], unique=False)
    op.create_index(op.f('ix_call_recordings_owner_id'), 'call_recordings', ['owner_id'], unique=False)
    op.create_index(op.f('ix_call_recordings_status'), 'call_recordings', ['status'], unique=False)

    # Create shared_access table
    op.create_table(
        'shared_access',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('resource_type', postgresql.ENUM('chat', 'entity', 'call', name='resourcetype', create_type=False), nullable=False),
        sa.Column('resource_id', sa.Integer(), nullable=False),
        sa.Column('shared_by_id', sa.Integer(), nullable=False),
        sa.Column('shared_with_id', sa.Integer(), nullable=False),
        sa.Column('access_level', postgresql.ENUM('view', 'edit', 'full', name='accesslevel', create_type=False), nullable=True),
        sa.Column('note', sa.String(length=500), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['shared_by_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['shared_with_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_shared_access_resource_id'), 'shared_access', ['resource_id'], unique=False)
    op.create_index(op.f('ix_shared_access_resource_type'), 'shared_access', ['resource_type'], unique=False)
    op.create_index(op.f('ix_shared_access_shared_by_id'), 'shared_access', ['shared_by_id'], unique=False)
    op.create_index(op.f('ix_shared_access_shared_with_id'), 'shared_access', ['shared_with_id'], unique=False)

    # Create invitations table
    op.create_table(
        'invitations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('org_id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('org_role', postgresql.ENUM('owner', 'admin', 'member', name='orgrole', create_type=False), nullable=True),
        sa.Column('department_ids', sa.JSON(), nullable=True),
        sa.Column('invited_by_id', sa.Integer(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('used_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['invited_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['used_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token')
    )
    op.create_index(op.f('ix_invitations_org_id'), 'invitations', ['org_id'], unique=False)
    op.create_index(op.f('ix_invitations_token'), 'invitations', ['token'], unique=True)

    # Create report_subscriptions table
    op.create_table(
        'report_subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('report_type', postgresql.ENUM('daily_hr', 'weekly_summary', 'daily_calls', 'weekly_pipeline', name='reporttype', create_type=False), nullable=False),
        sa.Column('delivery_method', postgresql.ENUM('telegram', 'email', name='deliverymethod', create_type=False), nullable=False),
        sa.Column('delivery_time', sa.Time(), nullable=True),
        sa.Column('filters', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create entity_ai_conversations table
    op.create_table(
        'entity_ai_conversations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('messages', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_entity_ai_conversations_entity_id'), 'entity_ai_conversations', ['entity_id'], unique=False)
    op.create_index(op.f('ix_entity_ai_conversations_user_id'), 'entity_ai_conversations', ['user_id'], unique=False)

    # Create entity_analyses table
    op.create_table(
        'entity_analyses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('analysis_type', sa.String(length=50), nullable=True),
        sa.Column('result', sa.Text(), nullable=False),
        sa.Column('scores', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_entity_analyses_entity_id'), 'entity_analyses', ['entity_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop tables in reverse order
    op.drop_index(op.f('ix_entity_analyses_entity_id'), table_name='entity_analyses')
    op.drop_table('entity_analyses')

    op.drop_index(op.f('ix_entity_ai_conversations_user_id'), table_name='entity_ai_conversations')
    op.drop_index(op.f('ix_entity_ai_conversations_entity_id'), table_name='entity_ai_conversations')
    op.drop_table('entity_ai_conversations')

    op.drop_table('report_subscriptions')

    op.drop_index(op.f('ix_invitations_token'), table_name='invitations')
    op.drop_index(op.f('ix_invitations_org_id'), table_name='invitations')
    op.drop_table('invitations')

    op.drop_index(op.f('ix_shared_access_shared_with_id'), table_name='shared_access')
    op.drop_index(op.f('ix_shared_access_shared_by_id'), table_name='shared_access')
    op.drop_index(op.f('ix_shared_access_resource_type'), table_name='shared_access')
    op.drop_index(op.f('ix_shared_access_resource_id'), table_name='shared_access')
    op.drop_table('shared_access')

    op.drop_index(op.f('ix_call_recordings_status'), table_name='call_recordings')
    op.drop_index(op.f('ix_call_recordings_owner_id'), table_name='call_recordings')
    op.drop_index(op.f('ix_call_recordings_org_id'), table_name='call_recordings')
    op.drop_index(op.f('ix_call_recordings_fireflies_transcript_id'), table_name='call_recordings')
    op.drop_index(op.f('ix_call_recordings_entity_id'), table_name='call_recordings')
    op.drop_table('call_recordings')

    op.drop_index(op.f('ix_analysis_history_entity_id'), table_name='analysis_history')
    op.drop_index(op.f('ix_analysis_history_chat_id'), table_name='analysis_history')
    op.drop_table('analysis_history')

    op.drop_index(op.f('ix_ai_conversations_user_id'), table_name='ai_conversations')
    op.drop_index(op.f('ix_ai_conversations_chat_id'), table_name='ai_conversations')
    op.drop_table('ai_conversations')

    op.drop_table('chat_criteria')

    op.drop_index(op.f('ix_criteria_presets_chat_type'), table_name='criteria_presets')
    op.drop_table('criteria_presets')

    op.drop_index(op.f('ix_messages_telegram_user_id'), table_name='messages')
    op.drop_index(op.f('ix_messages_chat_id'), table_name='messages')
    op.drop_table('messages')

    op.drop_index(op.f('ix_chats_telegram_chat_id'), table_name='chats')
    op.drop_index(op.f('ix_chats_owner_id'), table_name='chats')
    op.drop_index(op.f('ix_chats_org_id'), table_name='chats')
    op.drop_index(op.f('ix_chats_entity_id'), table_name='chats')
    op.drop_index(op.f('ix_chats_deleted_at'), table_name='chats')
    op.drop_index(op.f('ix_chats_chat_type'), table_name='chats')
    op.drop_table('chats')

    op.drop_index(op.f('ix_entity_transfers_to_department_id'), table_name='entity_transfers')
    op.drop_index(op.f('ix_entity_transfers_from_department_id'), table_name='entity_transfers')
    op.drop_index(op.f('ix_entity_transfers_entity_id'), table_name='entity_transfers')
    op.drop_table('entity_transfers')

    op.drop_index(op.f('ix_entities_type'), table_name='entities')
    op.drop_index(op.f('ix_entities_telegram_user_id'), table_name='entities')
    op.drop_index(op.f('ix_entities_status'), table_name='entities')
    op.drop_index(op.f('ix_entities_org_id'), table_name='entities')
    op.drop_index(op.f('ix_entities_department_id'), table_name='entities')
    op.drop_table('entities')

    op.drop_index(op.f('ix_department_members_user_id'), table_name='department_members')
    op.drop_index(op.f('ix_department_members_department_id'), table_name='department_members')
    op.drop_table('department_members')

    op.drop_index(op.f('ix_departments_parent_id'), table_name='departments')
    op.drop_index(op.f('ix_departments_org_id'), table_name='departments')
    op.drop_table('departments')

    op.drop_index(op.f('ix_org_members_user_id'), table_name='org_members')
    op.drop_index(op.f('ix_org_members_org_id'), table_name='org_members')
    op.drop_table('org_members')

    op.drop_index(op.f('ix_organizations_slug'), table_name='organizations')
    op.drop_table('organizations')

    op.drop_index(op.f('ix_users_telegram_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')

    # Drop enums
    sa.Enum(name='accesslevel').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='resourcetype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='subscriptionplan').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='deptrole').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='orgrole').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='deliverymethod').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='reporttype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='callstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='callsource').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='entitystatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='entitytype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='chattype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='userrole').drop(op.get_bind(), checkfirst=True)
