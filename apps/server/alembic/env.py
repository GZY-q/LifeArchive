"""Alembic reads runtime credentials, never an interpolated secret in alembic.ini."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from life_archive.auth import models as auth_models  # noqa: F401 -- register model metadata
from life_archive.db import Base
from life_archive.journal import models as journal_models  # noqa: F401 -- register model metadata
from life_archive.media import models as media_models  # noqa: F401 -- register model metadata
from life_archive.settings import get_database_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# All implemented models must be imported here before migration autogeneration.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    # SQL generation needs a dialect, not a database password or live connection.
    context.configure(
        dialect_name="postgresql",
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        context.configure(connection=supplied_connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = create_engine(
        get_database_settings().url,
        poolclass=pool.NullPool,
        hide_parameters=True,
        connect_args={"connect_timeout": 5, "options": "-c timezone=UTC"},
    )
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
