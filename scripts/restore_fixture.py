"""Executed via stdin code in the isolated API image, never a production command."""

import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import select, update

from life_archive.auth.models import User
from life_archive.auth.service import create_owner
from life_archive.db import get_engine, get_session_factory
from life_archive.journal.models import Entry, EntryRevision
from life_archive.journal.schemas import EntryCreate, EntryUpdate
from life_archive.journal.service import create_entry, delete_entry, edit_entry


def seed() -> dict:
    password = json.load(sys.stdin)["password"]
    with get_session_factory()() as db:
        owner = create_owner(db, "restore-smoke-owner", password, "Pacific/Kiritimati")
        raw = "# 合成恢复 😀\r\n\r\n中文原文尾空格  \n<script>text only</script>\n"
        first, _ = create_entry(
            db,
            owner.id,
            EntryCreate(
                content_md=raw,
                entry_date="2000-02-29",
                client_request_id=uuid4(),
            ),
        )
        edit_entry(
            db,
            owner.id,
            first.id,
            EntryUpdate(
                expected_revision=1,
                content_md=raw + "第二版\n",
                entry_date="1999-12-31",
            ),
        )
        edit_entry(
            db,
            owner.id,
            first.id,
            EntryUpdate(
                expected_revision=2,
                content_md=raw + "第三版\n",
                entry_date="2000-02-29",
            ),
        )
        second, _ = create_entry(
            db,
            owner.id,
            EntryCreate(
                content_md="合成同日第二篇",
                entry_date="2000-02-29",
                client_request_id=uuid4(),
            ),
        )
        deleted, _ = create_entry(
            db,
            owner.id,
            EntryCreate(
                content_md="合成软删除历史",
                entry_date="0001-01-01",
                client_request_id=uuid4(),
            ),
        )
        delete_entry(db, owner.id, deleted.id, 1)
        db.execute(
            update(Entry)
            .where(Entry.id == first.id)
            .values(
                occurred_at=datetime(2026, 1, 1, 0, 30, tzinfo=timezone(timedelta(hours=14))),
                occurred_timezone="Pacific/Kiritimati",
                created_at=datetime(2025, 12, 31, 23, 30, tzinfo=UTC),
            )
        )
        db.commit()
        return {"first": str(first.id), "second": str(second.id), "deleted": str(deleted.id)}


def snapshot() -> dict:
    digest = hashlib.sha256()
    with get_engine().connect() as connection:
        owner = dict(
            connection.execute(select(User.id, User.username, User.timezone, User.created_at))
            .mappings()
            .one()
        )
        counts = {}
        for model in (Entry, EntryRevision):
            query = select(model.__table__).order_by(*model.__table__.primary_key.columns)
            rows = connection.execute(query).mappings().all()
            counts[model.__tablename__] = len(rows)
            digest.update(
                json.dumps([dict(row) for row in rows], default=str, sort_keys=True).encode()
            )
            if model is Entry:
                counts["deleted"] = sum(row["deleted_at"] is not None for row in rows)
        heads = MigrationContext.configure(connection).get_current_heads()
    return {
        "owner": owner,
        "counts": counts,
        "journal_sha256": digest.hexdigest(),
        "heads": list(heads),
        "expected_head": ScriptDirectory.from_config(Config("alembic.ini")).get_current_head(),
    }


if __name__ == "__main__":
    try:
        result = seed() if sys.argv[1] == "seed" else snapshot()
        print(json.dumps(result, default=str, sort_keys=True))
    except Exception:
        raise SystemExit("Isolated fixture/snapshot operation failed") from None
