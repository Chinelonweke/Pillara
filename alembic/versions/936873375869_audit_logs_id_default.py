"""add server-side default to audit_logs.id

Revision ID: 936873375869
Revises: 557f6b331fc8
Create Date: 2026-06-20

WHY THIS MIGRATION:
monitoring/audit.py writes to audit_logs using raw SQL (text()) rather than
the SQLAlchemy ORM, deliberately - see the comment in _write_to_database():
"the audit log must ALWAYS be written, even if there's an ORM issue."

The AuditLog model's id column has a Python-side default
(default=lambda: str(uuid.uuid4())), but Python-side defaults only fire
when SQLAlchemy itself constructs the INSERT. Raw SQL via text() never
goes through that code path, so id was never populated - and since id
is NOT NULL, every audit log write failed with:
    asyncpg.exceptions.NotNullViolationError: null value in column "id"

This caused a real production failure: a user_registered event failed to
write, which aborted the surrounding transaction, which then caused the
NEXT query in that same request (a refresh token UPDATE) to also fail -
turning a missing audit log into a full 500 error on registration.

WHY A SERVER-SIDE DEFAULT (not just fixing the Python caller):
audit_logs is the HIPAA compliance trail. It should be structurally
incapable of silently failing to populate its primary key, regardless of
whether a future caller uses the ORM, raw SQL, or anything else. Moving
the default into the database itself means EVERY future INSERT into this
table - ORM-based or raw SQL - gets a valid id automatically, with no
dependency on application code remembering to set it.

gen_random_uuid() is built into PostgreSQL 13+ (pgvector/pgvector:pg16,
our image, definitely includes it) - no extension needs to be enabled.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "936873375869"
down_revision = "557f6b331fc8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE audit_logs ALTER COLUMN id SET DEFAULT gen_random_uuid();"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE audit_logs ALTER COLUMN id DROP DEFAULT;"
    )
