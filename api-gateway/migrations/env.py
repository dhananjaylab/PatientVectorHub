"""Alembic environment — async SQLAlchemy support."""
import asyncio
import os
import ssl
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override URL from environment (priority: DATABASE_URL > DATABASE_URL_SYNC > alembic.ini)
db_url = os.getenv("DATABASE_URL") or os.getenv("DATABASE_URL_SYNC")
if not db_url:
    db_url = config.get_main_option("sqlalchemy.url")

# Ensure URL uses asyncpg for async migrations
if db_url:
    if "psycopg2" in db_url:
        db_url = db_url.replace("postgresql+psycopg2", "postgresql+asyncpg")
    elif "postgresql://" in db_url and "+" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")

config.set_main_option("sqlalchemy.url", db_url)

target_metadata = None  # Phase 2 adds SQLAlchemy models


def run_migrations_offline() -> None:
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
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations asynchronously with SSL support for remote databases."""
    db_url = config.get_main_option("sqlalchemy.url")
    
    # Create SSL context for Aiven (no CA verification by default per Aiven docs)
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    # Create async engine with SSL support for Aiven/cloud databases
    connectable = create_async_engine(
        db_url,
        poolclass=pool.NullPool,
        echo=False,
        connect_args={"ssl": ssl_context} if "aivencloud.com" in (db_url or "") else {},
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
