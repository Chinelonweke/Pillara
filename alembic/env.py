# alembic/env.py
#
# REWRITTEN FROM THE GENERIC TEMPLATE to work with Pillara's actual setup:
# 1. Async engine — Pillara uses SQLAlchemy's async API everywhere (asyncpg),
#    so migrations need to run through an async connection too, not a sync one.
# 2. Points target_metadata at core.database.Base — this is what makes
#    `alembic revision --autogenerate` actually able to "see" User, Profile,
#    Medication, Reminder, AuditLog and detect schema differences.
# 3. Reads DATABASE_URL from Settings (Infisical-backed) instead of a
#    hardcoded value in alembic.ini — so migrations always run against
#    whichever database your .env/Infisical setup currently points to.

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ─── IMPORT PILLARA'S ACTUAL MODELS AND CONFIG ────────────────────────────────
# These imports MUST happen before target_metadata is set below, since
# importing models/user.py is what registers User, Profile, Medication,
# Reminder, and AuditLog onto Base.metadata. If we forget this import,
# Alembic would see an empty Base with no tables and generate a migration
# that does nothing.
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# WHY THIS PATH INSERT: alembic/env.py runs from inside the alembic/ folder,
# but it needs to import from the project root (core/, models/) one level up.

from core.database import Base
from core.config import settings
import models.user  # noqa: F401 — import registers all models onto Base.metadata


# this is the Alembic Config object, which provides access to values
# within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# WHY WE OVERRIDE THE INI FILE'S sqlalchemy.url HERE:
# alembic.ini normally hardcodes a database URL as a static string.
# We don't want that — we want migrations to always use whatever
# DATABASE_URL is currently active via Infisical/.env, the same source
# of truth the actual running app uses. This means `alembic upgrade head`
# always targets the correct database without manual edits to alembic.ini.
config.set_main_option("sqlalchemy.url", settings.database_url_async)

# add your model's MetaData object here for 'autogenerate' support
# THIS is the line that makes autogenerate actually work — it tells
# Alembic "compare the database against these table definitions."
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine,
    though an Engine is acceptable here as well. By skipping the Engine
    creation we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    WHEN THIS IS USED: `alembic upgrade head --sql` — generates raw SQL
    without touching a live database. Useful for handing a DBA a SQL
    script to review/run manually, rather than letting Alembic connect directly.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """
    Shared migration logic — called with a live, already-connected
    Connection object, whether that connection came from sync or async setup.
    """
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    ASYNC ENGINE SETUP:
    Pillara's core/database.py uses create_async_engine with asyncpg.
    Alembic's default template assumes a sync engine — this function is
    the async-aware replacement, using async_engine_from_config and running
    the actual migration logic through connection.run_sync(), since Alembic's
    internal migration execution is itself synchronous even though our
    connection is async.
    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        # NullPool: migrations are a one-off script run, not a long-lived
        # app server — we don't want connection pooling overhead/complexity
        # here, just a single clean connection that opens and closes.
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode — i.e. actually connect to the
    database and apply changes. This is what `alembic upgrade head` uses.
    """
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()