"""Portable originals and revisions from one independent, read-only PG snapshot."""

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import BinaryIO, Literal, TypedDict
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from alembic.runtime.migration import MigrationContext
from sqlalchemy import select
from sqlalchemy.engine import Connection, Engine

from life_archive.auth.models import User
from life_archive.journal.models import Entry, EntryRevision, EntryTag, Tag
from life_archive.media.models import Asset, EntryAsset
from life_archive.media.storage import MediaStorageError, read_original

ENTRY_FIELDS = (
    "id",
    "user_id",
    "entry_date",
    "occurred_at",
    "occurred_timezone",
    "created_at",
    "updated_at",
    "deleted_at",
    "revision",
    "client_request_id",
    "tags",
    "assets",
)
REVISION_FIELDS = (
    "id",
    "entry_id",
    "editor_id",
    "revision",
    "entry_date",
    "changed_at",
    "tags",
    "assets",
)
ASSET_FIELDS = ("id", "mime_type", "byte_size", "sha256", "width", "height", "created_at")
ASSET_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


class ExportError(Exception):
    """A fixed, safe-to-display failure reason; never include source data or SQL."""


class FileRecord(TypedDict):
    path: str
    bytes: int
    sha256: str


class Manifest(TypedDict):
    schema_version: int
    exported_at: datetime
    alembic_revision: str
    owner: dict[str, object]
    deleted_policy: Literal["active_only", "include_deleted"]
    entry_count: int
    revision_count: int
    asset_count: int
    files: list[FileRecord]


@dataclass(frozen=True)
class ExportResult:
    output: Path
    entry_count: int
    revision_count: int


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ExportError("A source timestamp is missing its timezone")
        return value.astimezone(UTC).isoformat()
    if isinstance(value, (date, UUID)):
        return value.isoformat() if isinstance(value, date) else str(value)
    raise ExportError("Unsupported source metadata")


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, default=_json_default, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n"
    ).encode("utf-8")


def _write_member(archive: ZipFile, path: str, data: bytes) -> FileRecord:
    # ZIP timestamps are fixed format metadata, never journal occurrence instants.
    info = ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100600 << 16
    archive.writestr(info, data)
    return {"path": path, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _write_record(
    archive: ZipFile, base: str, row: Mapping[str, object], fields: tuple[str, ...]
) -> list[FileRecord]:
    markdown_path = base + ".md"
    content = row["content_md"]
    if not isinstance(content, str):
        raise ExportError("Invalid source Markdown")
    metadata = {field: row[field] for field in fields}
    metadata["markdown_path"] = markdown_path
    return [
        _write_member(archive, markdown_path, content.encode("utf-8")),
        _write_member(archive, base + ".json", _json_bytes(metadata)),
    ]


def _referenced_assets(labels: object) -> set[UUID]:
    if not isinstance(labels, list):
        raise ExportError("Invalid source asset metadata")
    try:
        return {UUID(str(label["id"])) for label in labels}
    except (ValueError, TypeError, KeyError):
        raise ExportError("Invalid source asset metadata") from None


def _write_assets(
    connection: Connection, archive: ZipFile, owner_id: UUID, selected: set[UUID]
) -> list[FileRecord]:
    files: list[FileRecord] = []
    catalog = []
    # Only assets referenced by the selected current records or their revisions
    # are portable members. Unassociated uploads remain in database/media backups.
    for asset_id in sorted(selected):
        asset = (
            connection.execute(
                select(Asset.__table__).where(Asset.id == asset_id, Asset.user_id == owner_id)
            )
            .mappings()
            .one_or_none()
        )
        if asset is None or asset["mime_type"] not in ASSET_EXTENSIONS:
            raise ExportError("Referenced asset metadata is unavailable")
        try:
            original = read_original(asset)
        except MediaStorageError:
            raise ExportError("Referenced original media is missing or corrupt") from None
        path = f"assets/{asset_id}.{ASSET_EXTENSIONS[asset['mime_type']]}"
        files.append(_write_member(archive, path, original))
        catalog.append({**{field: asset[field] for field in ASSET_FIELDS}, "file_path": path})
    files.append(_write_member(archive, "assets.json", _json_bytes(catalog)))
    return files


def _write_snapshot(connection: Connection, archive: ZipFile, include_deleted: bool) -> Manifest:
    heads = MigrationContext.configure(connection).get_current_heads()
    if len(heads) != 1:
        raise ExportError("Database migrations are missing or ambiguous")
    owner = (
        connection.execute(select(User.id, User.username, User.timezone, User.created_at))
        .mappings()
        .one_or_none()
    )
    if owner is None:
        raise ExportError("Owner has not been initialized")
    entries = select(Entry.__table__).where(Entry.user_id == owner["id"])
    if not include_deleted:
        entries = entries.where(Entry.deleted_at.is_(None))
    files: list[FileRecord] = []
    entry_count = revision_count = 0
    selected_assets: set[UUID] = set()
    # Core rows avoid an ORM identity map retaining all journal originals.
    with connection.execute(entries.order_by(Entry.id).execution_options(yield_per=100)) as rows:
        for entry in rows.mappings():
            tags = connection.execute(
                select(Tag.id, Tag.name)
                .join(EntryTag, (EntryTag.tag_id == Tag.id) & (EntryTag.user_id == Tag.user_id))
                .where(EntryTag.entry_id == entry["id"], Tag.user_id == owner["id"])
                .order_by(Tag.id)
            ).mappings()
            current = dict(entry)
            current["tags"] = [dict(tag) for tag in tags]
            assets = connection.execute(
                select(*(getattr(Asset, field) for field in ASSET_FIELDS))
                .join(
                    EntryAsset,
                    (EntryAsset.asset_id == Asset.id) & (EntryAsset.user_id == Asset.user_id),
                )
                .where(EntryAsset.entry_id == entry["id"], Asset.user_id == owner["id"])
                .order_by(Asset.id)
            ).mappings()
            current["assets"] = [dict(asset) for asset in assets]
            selected_assets.update(_referenced_assets(current["assets"]))
            files.extend(_write_record(archive, f"entries/{entry['id']}", current, ENTRY_FIELDS))
            entry_count += 1
            revisions = (
                select(EntryRevision.__table__)
                .where(EntryRevision.entry_id == entry["id"])
                .order_by(EntryRevision.revision)
                .execution_options(yield_per=100)
            )
            with connection.execute(revisions) as history:
                for revision in history.mappings():
                    selected_assets.update(_referenced_assets(revision["assets"]))
                    base = f"revisions/{entry['id']}/{revision['revision']}"
                    files.extend(_write_record(archive, base, revision, REVISION_FIELDS))
                    revision_count += 1
    # The owner catalog is complete, including unused tags and tags attached only
    # to deleted entries. The deleted policy limits journals, never this catalog.
    catalog = connection.execute(
        select(Tag.id, Tag.name, Tag.created_at).where(Tag.user_id == owner["id"]).order_by(Tag.id)
    ).mappings()
    files.append(_write_member(archive, "tags.json", _json_bytes([dict(tag) for tag in catalog])))
    files.extend(_write_assets(connection, archive, owner["id"], selected_assets))
    manifest: Manifest = {
        "schema_version": 3,
        "exported_at": datetime.now(UTC),
        "alembic_revision": heads[0],
        "owner": dict(owner),
        "deleted_policy": "include_deleted" if include_deleted else "active_only",
        "entry_count": entry_count,
        "revision_count": revision_count,
        "asset_count": len(selected_assets),
        "files": sorted(files, key=lambda item: item["path"]),
    }
    # Last member: its presence alone still does not replace full hash verification.
    _write_member(archive, "manifest.json", _json_bytes(manifest))
    return manifest


def _verify_written_archive(file: BinaryIO, manifest: Manifest) -> None:
    file.seek(0)
    with ZipFile(file, "r") as archive:
        expected_paths = [item["path"] for item in manifest["files"]] + ["manifest.json"]
        if sorted(archive.namelist()) != sorted(expected_paths):
            raise ExportError("Export member verification failed")
        if archive.read("manifest.json") != _json_bytes(manifest):
            raise ExportError("Export manifest verification failed")
        for item in manifest["files"]:
            digest = hashlib.sha256()
            size = 0
            with archive.open(item["path"]) as member:
                while chunk := member.read(65536):
                    digest.update(chunk)
                    size += len(chunk)
            if size != item["bytes"] or digest.hexdigest() != item["sha256"]:
                raise ExportError("Export content verification failed")


def export_journal(engine: Engine, output: Path, *, include_deleted: bool = False) -> ExportResult:
    """Create a new private ZIP, retaining incomplete output on failure for inspection."""
    if not output.is_absolute():
        raise ExportError("Output must be an absolute path with an existing parent directory")
    flags = os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(output, flags, 0o600)
    with os.fdopen(descriptor, "w+b") as file:
        os.fchmod(file.fileno(), 0o600)
        # Set transaction characteristics before ANY source query. Never borrow an
        # authentication Session whose transaction/snapshot may already have begun.
        with engine.connect().execution_options(
            isolation_level="REPEATABLE READ", postgresql_readonly=True
        ) as connection:
            with connection.begin(), ZipFile(file, "w", compression=ZIP_DEFLATED) as archive:
                manifest = _write_snapshot(connection, archive, include_deleted)
        file.flush()
        os.fsync(file.fileno())
        _verify_written_archive(file, manifest)
    return ExportResult(output, manifest["entry_count"], manifest["revision_count"])
