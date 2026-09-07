"""Fix Profile.user_id cascade from CASCADE to SET NULL

Prevents profile deletion when the creator (caregiver) deletes their account.
A claimed profile belongs to the patient (owner_user_id) — it must survive
the caregiver's account deletion.

Revision ID: 004
Revises: 003
Create Date: 2026-09-04
"""
from alembic import op

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the existing foreign key constraint
    op.drop_constraint('profiles_user_id_fkey', 'profiles', type_='foreignkey')

    # Allow user_id to be NULL (caregiver deleted their account)
    op.alter_column('profiles', 'user_id', nullable=True)

    # Re-create with SET NULL instead of CASCADE
    op.create_foreign_key(
        'profiles_user_id_fkey',
        'profiles',
        'users',
        ['user_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('profiles_user_id_fkey', 'profiles', type_='foreignkey')
    op.alter_column('profiles', 'user_id', nullable=False)
    op.create_foreign_key(
        'profiles_user_id_fkey',
        'profiles',
        'users',
        ['user_id'],
        ['id'],
        ondelete='CASCADE',
    )