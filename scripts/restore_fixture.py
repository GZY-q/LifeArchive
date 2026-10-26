"""Executed via stdin code in the isolated API image, never a production command."""

import base64
import hashlib
import io
import json
import sys
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from PIL import Image
from sqlalchemy import select, update

from life_archive.auth.models import User
from life_archive.auth.service import create_owner
from life_archive.db import get_engine, get_session_factory
from life_archive.journal.models import Entry, EntryRevision, EntryTag, Tag
from life_archive.journal.schemas import EntryCreate, EntryUpdate, TagCreate
from life_archive.journal.service import create_entry, delete_entry, edit_entry
from life_archive.journal.tags import create_tag
from life_archive.media.models import Asset, EntryAsset
from life_archive.media.storage import read_original, write_original
from life_archive.settings import get_media_settings


def synthetic_image(color: str) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (2, 2), color).save(output, format="PNG")
    return output.getvalue()


def seed() -> dict:
    password = json.load(sys.stdin)["password"]
    with get_session_factory()() as db:
        owner = create_owner(db, "restore-smoke-owner", password, "Pacific/Kiritimati")
        tags = [
            create_tag(db, owner.id, TagCreate(name=name))[0]
            for name in ("合成原始标签", "合成当前标签", "合成软删除标签", "合成未使用标签")
        ]
        from life_archive.media.service import create_asset

        assets = [
            create_asset(db, owner.id, synthetic_image(color), "image/png")[0]
            for color in ("red", "blue")
        ]
        raw = "# 合成恢复 😀\r\n\r\n中文原文尾空格  \n<script>text only</script>\n"
        first, _ = create_entry(
            db,
            owner.id,
            EntryCreate(
                content_md=raw,
                entry_date="2000-02-29",
                client_request_id=uuid4(),
                tag_ids=[tags[0].id],
                asset_ids=[assets[0].id],
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
                tag_ids=[],
                asset_ids=[],
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
                tag_ids=[tags[1].id],
                asset_ids=[assets[1].id],
            ),
        )
        second, _ = create_entry(
            db,
            owner.id,
            EntryCreate(
                content_md="合成同日第二篇",
                entry_date="2000-02-29",
                client_request_id=uuid4(),
                tag_ids=[tags[0].id],
            ),
        )
        deleted, _ = create_entry(
            db,
            owner.id,
            EntryCreate(
                content_md="合成软删除历史",
                entry_date="0001-01-01",
                client_request_id=uuid4(),
                tag_ids=[tags[2].id],
                asset_ids=[assets[0].id],
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
        return {
            "first": str(first.id),
            "second": str(second.id),
            "deleted": str(deleted.id),
            "asset_original": str(assets[0].id),
            "asset_current": str(assets[1].id),
            **{
                key: str(tag.id)
                for key, tag in zip(
                    ("tag_original", "tag_current", "tag_deleted", "tag_unused"), tags, strict=True
                )
            },
        }


def snapshot() -> dict:
    digest = hashlib.sha256()
    with get_engine().connect() as connection:
        owner = dict(
            connection.execute(select(User.id, User.username, User.timezone, User.created_at))
            .mappings()
            .one()
        )
        counts = {}
        media = []
        for model in (Entry, EntryRevision, Tag, EntryTag, Asset, EntryAsset):
            query = select(model.__table__).order_by(*model.__table__.primary_key.columns)
            rows = connection.execute(query).mappings().all()
            counts[model.__tablename__] = len(rows)
            digest.update(
                json.dumps([dict(row) for row in rows], default=str, sort_keys=True).encode()
            )
            if model is Entry:
                counts["deleted"] = sum(row["deleted_at"] is not None for row in rows)
            if model is Asset:
                for row in rows:
                    data = read_original(row)
                    media.append(
                        {
                            "id": str(row["id"]),
                            "bytes": len(data),
                            "sha256": hashlib.sha256(data).hexdigest(),
                        }
                    )
        heads = MigrationContext.configure(connection).get_current_heads()
    return {
        "owner": owner,
        "counts": counts,
        "journal_sha256": digest.hexdigest(),
        "heads": list(heads),
        "expected_head": ScriptDirectory.from_config(Config("alembic.ini")).get_current_head(),
        "media": media,
    }


def media_export() -> dict:
    with get_engine().connect() as connection:
        assets = connection.execute(select(Asset.__table__).order_by(Asset.id)).mappings().all()
        if len(assets) != 2:
            raise ValueError("Unexpected synthetic media catalog")
        return {
            "files": [
                {
                    "storage_key": asset["storage_key"],
                    "byte_size": asset["byte_size"],
                    "sha256": asset["sha256"],
                    "data": base64.b64encode(read_original(asset)).decode("ascii"),
                }
                for asset in assets
            ]
        }


def media_restore() -> dict:
    # Only this script's two tiny synthetic images are accepted. No tar or
    # arbitrary host path is used, and every target original is exclusive-create.
    payload = json.loads(sys.stdin.buffer.read(4097))
    root = get_media_settings().media_root
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink() or any(root.iterdir()):
        raise ValueError("Target media is not empty")
    with get_engine().connect() as connection:
        assets = connection.execute(select(Asset.__table__).order_by(Asset.id)).mappings().all()
    files = payload.get("files")
    if len(assets) != 2 or not isinstance(files, list) or len(files) != 2:
        raise ValueError("Unexpected synthetic media catalog")
    expected = {asset["storage_key"]: asset for asset in assets}
    validated = {}
    for item in files:
        key = item["storage_key"]
        if (
            key not in expected
            or key in validated
            or len(key) != 32
            or any(c not in "0123456789abcdef" for c in key)
        ):
            raise ValueError("Invalid synthetic media identity")
        data = base64.b64decode(item["data"], validate=True)
        asset = expected[key]
        if (
            len(data) > 1024
            or len(data) != asset["byte_size"]
            or len(data) != item["byte_size"]
            or hashlib.sha256(data).hexdigest() != asset["sha256"]
            or asset["sha256"] != item["sha256"]
        ):
            raise ValueError("Synthetic media integrity mismatch")
        validated[key] = data
    for key, data in validated.items():
        write_original(key, data, root)
    return {"files": len(validated)}


if __name__ == "__main__":
    try:
        actions = {
            "seed": seed,
            "snapshot": snapshot,
            "media_export": media_export,
            "media_restore": media_restore,
        }
        result = actions[sys.argv[1]]()
        print(json.dumps(result, default=str, sort_keys=True))
    except Exception:
        raise SystemExit("Isolated fixture/snapshot operation failed") from None
