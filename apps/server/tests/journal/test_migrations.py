from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.engine import Engine
from sqlalchemy.schema import SchemaItem

from life_archive.db import Base


def test_applied_journal_migration_matches_orm_metadata(pg_engine: Engine) -> None:
    def include_journal(
        _object: SchemaItem,
        name: str | None,
        kind: str,
        _reflected: bool,
        _compare_to: SchemaItem | None,
    ) -> bool:
        return kind != "table" or name in {"entries", "entry_revisions", "tags", "entry_tags"}

    with pg_engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"include_object": include_journal})
        assert compare_metadata(context, Base.metadata) == []
