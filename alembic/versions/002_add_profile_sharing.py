"""Add profile sharing tables and columns

Revision ID: 002
Revises: 936873375869
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '002'
down_revision = '936873375869'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── NEW COLUMNS ON profiles ───────────────────────────────────────────────
    # Using UUID type to match users.id which is UUID in PostgreSQL
    op.add_column('profiles', sa.Column('owner_user_id', UUID(as_uuid=False), nullable=True))
    op.add_column('profiles', sa.Column('claim_token', sa.String(64), nullable=True))
    op.add_column('profiles', sa.Column('claim_token_expires', sa.DateTime(timezone=True), nullable=True))
    op.add_column('profiles', sa.Column('claim_email', sa.String(255), nullable=True))
    op.add_column('profiles', sa.Column('status', sa.String(20), nullable=False, server_default='active'))

    op.create_foreign_key(
        'fk_profiles_owner_user_id',
        'profiles', 'users',
        ['owner_user_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_profiles_claim_token', 'profiles', ['claim_token'], unique=True)
    op.create_index('ix_profiles_owner_user_id', 'profiles', ['owner_user_id'])

    # Backfill: all existing profiles are "My Profile" — creator IS the owner
    op.execute("UPDATE profiles SET owner_user_id = user_id WHERE owner_user_id IS NULL")

    # ── NEW TABLE: profile_access ─────────────────────────────────────────────
    op.create_table(
        'profile_access',
        sa.Column('id', UUID(as_uuid=False), primary_key=True),
        sa.Column('profile_id', UUID(as_uuid=False), sa.ForeignKey('profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('granted_to_user_id', UUID(as_uuid=False), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('granted_by_user_id', UUID(as_uuid=False), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(20), nullable=False, server_default='viewer'),
        sa.Column('invite_token', sa.String(64), nullable=True),
        sa.Column('invite_token_expires', sa.DateTime(timezone=True), nullable=True),
        sa.Column('invite_email', sa.String(255), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_profile_access_profile_user', 'profile_access', ['profile_id', 'granted_to_user_id'])
    op.create_index('ix_profile_access_user_active', 'profile_access', ['granted_to_user_id', 'status'])
    op.create_index('ix_profile_access_invite_token', 'profile_access', ['invite_token'], unique=True)


def downgrade() -> None:
    op.drop_table('profile_access')
    op.drop_constraint('fk_profiles_owner_user_id', 'profiles', type_='foreignkey')
    op.drop_index('ix_profiles_claim_token', 'profiles')
    op.drop_index('ix_profiles_owner_user_id', 'profiles')
    op.drop_column('profiles', 'status')
    op.drop_column('profiles', 'claim_email')
    op.drop_column('profiles', 'claim_token_expires')
    op.drop_column('profiles', 'claim_token')
    op.drop_column('profiles', 'owner_user_id')