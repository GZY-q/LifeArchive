from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


def test_baseline_generates_postgresql_sql_without_business_tables_or_credentials() -> None:
    output = StringIO()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"), output_buffer=output)

    command.upgrade(config, "head", sql=True)

    sql = output.getvalue()
    assert "CREATE TABLE alembic_version" in sql
    assert "0001_foundation" in sql
    assert sql.count("CREATE TABLE") == 1
    assert "postgresql://" not in sql
    assert ScriptDirectory.from_config(config).get_current_head() == "0001_foundation"
