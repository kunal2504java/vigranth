"""Initial schema — users, credentials, messages, contacts, sync_states

Revision ID: 001
Revises: None
Create Date: 2026-02-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('password_hash', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('settings', postgresql.JSON, server_default='{}'),
    )
    op.create_index('ix_users_email', 'users', ['email'])

    # Platform credentials
    op.create_table(
        'platform_credentials',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('platform', sa.String(50), nullable=False),
        sa.Column('access_token', sa.Text, nullable=False),
        sa.Column('refresh_token', sa.Text, nullable=True),
        sa.Column('token_expiry', sa.DateTime(timezone=True), nullable=True),
        sa.Column('platform_user_id', sa.String(255), nullable=True),
        sa.Column('scopes', sa.Text, nullable=True),
        sa.Column('webhook_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'platform', name='uq_user_platform'),
    )

    # Messages
    op.create_table(
        'messages',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('platform', sa.String(50), nullable=False),
        sa.Column('platform_message_id', sa.String(255), nullable=False),
        sa.Column('thread_id', sa.String(255), nullable=True),
        sa.Column('sender_id', sa.String(255), nullable=False),
        sa.Column('sender_name', sa.String(255), nullable=True),
        sa.Column('sender_email', sa.String(255), nullable=True),
        sa.Column('content_text', sa.Text, nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_read', sa.Boolean, server_default='false'),
        sa.Column('is_done', sa.Boolean, server_default='false'),
        sa.Column('snoozed_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('priority_score', sa.Float, server_default='0.0'),
        sa.Column('priority_label', sa.String(20), server_default="'fyi'"),
        sa.Column('sentiment', sa.String(20), server_default="'neutral'"),
        sa.Column('ai_context_note', sa.Text, nullable=True),
        sa.Column('summary', sa.Text, nullable=True),
        sa.Column('classification_reasoning', sa.Text, nullable=True),
        sa.Column('is_complaint', sa.Boolean, server_default='false'),
        sa.Column('needs_careful_response', sa.Boolean, server_default='false'),
        sa.Column('suggested_approach', sa.Text, nullable=True),
        sa.Column('suggested_actions', postgresql.JSON, server_default='[]'),
        sa.Column('draft_reply', sa.Text, nullable=True),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'platform', 'platform_message_id', name='uq_user_platform_msg'),
    )
    op.create_index('idx_messages_feed', 'messages', ['user_id', sa.text('priority_score DESC'), sa.text('timestamp DESC')])
    op.create_index('idx_messages_platform', 'messages', ['user_id', 'platform'])
    op.create_index('idx_messages_thread', 'messages', ['thread_id'])
    op.create_index('idx_messages_snooze', 'messages', ['snoozed_until'], postgresql_where=sa.text('snoozed_until IS NOT NULL'))

    # Contacts
    op.create_table(
        'contacts',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('contact_identifier', sa.String(255), nullable=False),
        sa.Column('platform', sa.String(50), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=True),
        sa.Column('relationship', sa.String(50), server_default="'stranger'"),
        sa.Column('is_vip', sa.Boolean, server_default='false'),
        sa.Column('reply_rate', sa.Float, server_default='0.0'),
        sa.Column('message_count', sa.Integer, server_default='0'),
        sa.Column('last_interaction', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'platform', 'contact_identifier', name='uq_user_platform_contact'),
    )
    op.create_index('idx_contacts_user', 'contacts', ['user_id'])
    op.create_index('idx_contacts_vip', 'contacts', ['user_id', 'is_vip'])

    # Sync states
    op.create_table(
        'sync_states',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('platform', sa.String(50), nullable=False),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_history_id', sa.String(255), nullable=True),
        sa.Column('status', sa.String(20), server_default="'idle'"),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'platform', name='uq_user_platform_sync'),
    )


def downgrade() -> None:
    op.drop_table('sync_states')
    op.drop_table('contacts')
    op.drop_table('messages')
    op.drop_table('platform_credentials')
    op.drop_table('users')
