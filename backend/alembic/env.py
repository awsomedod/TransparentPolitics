import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import app.db.models  # noqa: F401 — registers all tables with Base.metadata
from alembic import context
from app.core.config import settings
from app.db.base import Base

config = context.config

# Override the DB URL from app settings — single source of truth.
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Tables that belong to our application (derived from ORM models).
# Alembic will only create/alter/drop these — PostGIS extension tables,
# TIGER geocoder tables, and topology tables are left untouched.
_our_tables: set[str] = set(target_metadata.tables.keys())


def include_object(object, name, type_, reflected, compare_to):  # noqa: A002
    """Filter Alembic's autogenerate to only manage our own tables."""
    if type_ == "table":
        return name in _our_tables
    # Always include indexes and constraints that belong to our tables.
    return True


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (outputs SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
