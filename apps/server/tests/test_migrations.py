from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Engine


def test_baseline_generates_postgresql_sql_without_business_tables_or_credentials() -> None:
    output = StringIO()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"), output_buffer=output)

    command.upgrade(config, "0001_foundation", sql=True)

    sql = output.getvalue()
    assert "CREATE TABLE alembic_version" in sql
    assert "0001_foundation" in sql
    assert sql.count("CREATE TABLE") == 1
    assert "postgresql://" not in sql
    assert ScriptDirectory.from_config(config).get_revision("0001_foundation") is not None


def test_m1_migrations_match_the_registered_models(pg_engine: Engine) -> None:
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from life_archive.db import Base

    tables = set(inspect(pg_engine).get_table_names())
    assert {"users", "sessions", "login_throttle", "entries", "entry_revisions"} <= tables
    with pg_engine.connect() as connection:
        context = MigrationContext.configure(connection)
        assert compare_metadata(context, Base.metadata) == []
