"""
Alembic Environment Configuration — Async SQLAlchemy

Loads the project metadata from ``app.infrastructure.database`` and
configures the migration context for both offline (``--sql``) and
online (live database) execution.

Phase 1  — infrastructure only, no models registered yet.
Phase 2+ — ``target_metadata`` will automatically include every ORM model
           that inherits from ``app.infrastructure.database.Base``.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# ---------------------------------------------------------------------------
# Alembic Config (alembic.ini)
# ---------------------------------------------------------------------------

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Project metadata — MUST be imported so Alembic knows about all tables.
# ---------------------------------------------------------------------------

# Phase 2: Import ORM models to populate ``metadata`` with all 14 tables.
# The import itself triggers model registration via ``Base`` subclasses.
from app.models import orm as _orm_models  # noqa: E402, F401
from app.infrastructure.database import CONVENTION, metadata  # noqa: E402

target_metadata = metadata


def include_object(obj, name, type_, reflected, compare_to):
    """Filter out Alembic's internal version table from autogenerate."""
    if type_ == "table" and name == "alembic_version":
        return False
    return True


# ---------------------------------------------------------------------------
# Offline (``--sql``) migration support
# ---------------------------------------------------------------------------


def run_migrations_offline() -> None:
    """Render migrations as raw SQL without connecting to a database."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online migration support (async)
# ---------------------------------------------------------------------------


def do_run_migrations(connection):
    """Configure and run migrations against a synchronous-style connection.

    Called inside ``connection.run_sync()`` which provides a synchronous
    facade over the async connection.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run pending migrations."""
    from app.config import get_settings

    settings = get_settings()
    database_url = settings.database.url

    connectable = create_async_engine(database_url, pool_pre_ping=True)

    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in online (live) mode using the async engine."""
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
