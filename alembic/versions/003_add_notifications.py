"""add notifications table

Revision ID: 003_add_notifications
Revises: 002_add_profile_sharing
Create Date: 2026-08-27

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '003_add_notifications'
down_revision = '002_add_profile_sharing'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'notifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('profile_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('type', sa.String(50), nullable=False),  # reminder_sent, interaction_alert
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('message', sa.Text, nullable=False),
        sa.Column('is_read', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_notifications_user_id', 'notifications', ['user_id'])
    op.create_index('ix_notifications_user_unread', 'notifications', ['user_id', 'is_read'])


def downgrade() -> None:
    op.drop_table('notifications')