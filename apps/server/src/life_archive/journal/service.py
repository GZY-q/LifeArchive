"""Owner-scoped reads and atomic writes of originals plus revision snapshots."""

import base64
import binascii
from datetime import UTC, date, datetime
from typing import NoReturn
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import delete, insert, select, tuple_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from life_archive.journal.models import Entry, EntryRevision, EntryTag, Tag
from life_archive.journal.schemas import (
    EntryCreate,
    EntryCursor,
    EntryOrder,
    EntryPage,
    EntryResponse,
    EntryUpdate,
    RevisionPage,
    RevisionResponse,
)
from life_archive.media.models import Asset, EntryAsset
from life_archive.media.schemas import AssetResponse


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Entry not found")


def _conflict(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=409, detail={"code": code, "message": message})


def get_entry(session: Session, user_id: UUID, entry_id: UUID) -> Entry:
    entry = session.scalar(
        select(Entry).where(
            Entry.id == entry_id, Entry.user_id == user_id, Entry.deleted_at.is_(None)
        )
    )
    if entry is None:
        raise _not_found()
    return entry


def _snapshot(session: Session, entry: Entry, editor_id: UUID) -> None:
    # A successful CAS holds the row lock; re-read associations even when this
    # Session had cached a version from before another committed edit.
    session.expire(entry, ["tags", "assets"])
    session.add(
        EntryRevision(
            entry_id=entry.id,
            editor_id=editor_id,
            content_md=entry.content_md,
            entry_date=entry.entry_date,
            revision=entry.revision,
            changed_at=entry.updated_at,
            is_pinned=entry.is_pinned,
            tags=[{"id": str(tag.id), "name": tag.name} for tag in entry.tags],
            assets=[
                AssetResponse.model_validate(asset).model_dump(mode="json")
                for asset in entry.assets
            ],
        )
    )


def _find_request(session: Session, user_id: UUID, request_id: UUID) -> Entry | None:
    return session.scalar(
        select(Entry).where(Entry.user_id == user_id, Entry.client_request_id == request_id)
    )


def _replay(session: Session, entry: Entry, payload: EntryCreate) -> tuple[Entry, bool]:
    if entry.deleted_at is not None:
        raise _not_found()
    original = session.scalar(
        select(EntryRevision).where(EntryRevision.entry_id == entry.id, EntryRevision.revision == 1)
    )
    if original is None:
        raise RuntimeError("Journal original revision is missing")
    if (
        original.content_md != payload.content_md
        or original.entry_date != payload.entry_date
        or original.is_pinned != payload.is_pinned
        or {UUID(tag["id"]) for tag in original.tags} != set(payload.tag_ids)
        or {UUID(asset["id"]) for asset in original.assets} != set(payload.asset_ids)
    ):
        raise _conflict(
            "idempotency_conflict", "This request ID was already used for a different journal entry"
        )
    return entry, False


def _validate_tags(session: Session, user_id: UUID, tag_ids: list[UUID]) -> None:
    if not tag_ids:
        return
    found = set(session.scalars(select(Tag.id).where(Tag.user_id == user_id, Tag.id.in_(tag_ids))))
    if found != set(tag_ids):
        raise HTTPException(status_code=422, detail="One or more tags are unavailable")


def _replace_tags(session: Session, entry: Entry, tag_ids: list[UUID]) -> None:
    # Entry has already been inserted or locked by the successful revision CAS.
    session.execute(
        delete(EntryTag).where(EntryTag.entry_id == entry.id, EntryTag.user_id == entry.user_id)
    )
    if tag_ids:
        session.execute(
            insert(EntryTag),
            [
                {"entry_id": entry.id, "tag_id": tag_id, "user_id": entry.user_id}
                for tag_id in tag_ids
            ],
        )
    # Core association writes bypass the identity map, including eager-loaded relationships.
    session.expire(entry, ["tags"])


def _validate_assets(session: Session, user_id: UUID, asset_ids: list[UUID]) -> None:
    if not asset_ids:
        return
    found = set(
        session.scalars(select(Asset.id).where(Asset.user_id == user_id, Asset.id.in_(asset_ids)))
    )
    if found != set(asset_ids):
        raise HTTPException(status_code=422, detail="One or more images are unavailable")


def _replace_assets(session: Session, entry: Entry, asset_ids: list[UUID]) -> None:
    session.execute(
        delete(EntryAsset).where(
            EntryAsset.entry_id == entry.id, EntryAsset.user_id == entry.user_id
        )
    )
    if asset_ids:
        session.execute(
            insert(EntryAsset),
            [
                {"entry_id": entry.id, "asset_id": asset_id, "user_id": entry.user_id}
                for asset_id in asset_ids
            ],
        )
    session.expire(entry, ["assets"])


def create_entry(session: Session, user_id: UUID, payload: EntryCreate) -> tuple[Entry, bool]:
    if payload.client_request_id is not None:
        existing = _find_request(session, user_id, payload.client_request_id)
        if existing is not None:
            return _replay(session, existing, payload)

    now = datetime.now(UTC)
    entry = Entry(
        user_id=user_id,
        content_md=payload.content_md,
        entry_date=payload.entry_date,
        client_request_id=payload.client_request_id,
        created_at=now,
        updated_at=now,
        revision=1,
        is_pinned=payload.is_pinned,
    )
    try:
        _validate_tags(session, user_id, payload.tag_ids)
        _validate_assets(session, user_id, payload.asset_ids)
        session.add(entry)
        session.flush()  # Obtain its ID before adding the foreign-key snapshot.
        _replace_tags(session, entry, payload.tag_ids)
        _replace_assets(session, entry, payload.asset_ids)
        _snapshot(session, entry, user_id)
        session.commit()
    except IntegrityError:
        # The unique owner/request constraint also handles simultaneous first attempts.
        session.rollback()
        if payload.client_request_id is not None:
            existing = _find_request(session, user_id, payload.client_request_id)
            if existing is not None:
                return _replay(session, existing, payload)
        raise
    except Exception:
        session.rollback()
        raise
    return entry, True


def _failed_compare_and_swap(session: Session, user_id: UUID, entry_id: UUID) -> NoReturn:
    session.rollback()
    get_entry(session, user_id, entry_id)
    raise _conflict("revision_conflict", "The journal entry changed; reload it before retrying")


def edit_entry(session: Session, user_id: UUID, entry_id: UUID, payload: EntryUpdate) -> Entry:
    changes = payload.model_dump(
        exclude_unset=True, exclude={"expected_revision", "tag_ids", "asset_ids"}
    )
    try:
        entry = session.scalar(
            update(Entry)
            .where(
                Entry.id == entry_id,
                Entry.user_id == user_id,
                Entry.deleted_at.is_(None),
                Entry.revision == payload.expected_revision,
            )
            .values(**changes, updated_at=datetime.now(UTC), revision=Entry.revision + 1)
            .returning(Entry)
            .execution_options(populate_existing=True)
        )
        if entry is None:
            _failed_compare_and_swap(session, user_id, entry_id)
        if payload.tag_ids is not None:
            _validate_tags(session, user_id, payload.tag_ids)
            _replace_tags(session, entry, payload.tag_ids)
        if payload.asset_ids is not None:
            _validate_assets(session, user_id, payload.asset_ids)
            _replace_assets(session, entry, payload.asset_ids)
        _snapshot(session, entry, user_id)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return entry


def delete_entry(session: Session, user_id: UUID, entry_id: UUID, expected_revision: int) -> None:
    now = datetime.now(UTC)
    try:
        entry = session.scalar(
            update(Entry)
            .where(
                Entry.id == entry_id,
                Entry.user_id == user_id,
                Entry.deleted_at.is_(None),
                Entry.revision == expected_revision,
            )
            .values(deleted_at=now, updated_at=now, revision=Entry.revision + 1)
            .returning(Entry)
            .execution_options(populate_existing=True)
        )
        if entry is None:
            _failed_compare_and_swap(session, user_id, entry_id)
        _snapshot(session, entry, user_id)
        session.commit()
    except Exception:
        session.rollback()
        raise


def _decode_cursor(
    cursor: str, filter_date: date | None, tag_id: UUID | None, order: EntryOrder
) -> EntryCursor:
    try:
        decoded = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        value = EntryCursor.model_validate_json(decoded)
        if (
            value.filter_date != filter_date
            or value.filter_tag_id != tag_id
            or value.filter_order != order
        ):
            raise ValueError("Cursor belongs to a different filter")
    except (ValueError, binascii.Error, ValidationError) as error:
        raise HTTPException(status_code=422, detail="Invalid pagination cursor") from error
    return value


def list_entries(
    session: Session,
    user_id: UUID,
    *,
    limit: int,
    cursor: str | None,
    entry_date: date | None,
    tag_id: UUID | None = None,
    order: EntryOrder = "date",
) -> EntryPage:
    statement = select(Entry).where(Entry.user_id == user_id, Entry.deleted_at.is_(None))
    if entry_date is not None:
        statement = statement.where(Entry.entry_date == entry_date)
    if tag_id is not None:
        statement = statement.where(
            select(EntryTag.entry_id)
            .where(
                EntryTag.entry_id == Entry.id,
                EntryTag.user_id == user_id,
                EntryTag.tag_id == tag_id,
            )
            .exists()
        )
    if cursor is not None:
        position = _decode_cursor(cursor, entry_date, tag_id, order)
        if order == "pinned":
            statement = statement.where(
                tuple_(Entry.is_pinned, Entry.entry_date, Entry.created_at, Entry.id)
                < (position.is_pinned, position.entry_date, position.created_at, position.id)
            )
        else:
            statement = statement.where(
                tuple_(Entry.entry_date, Entry.created_at, Entry.id)
                < (position.entry_date, position.created_at, position.id)
            )
    sorting = [Entry.entry_date.desc(), Entry.created_at.desc(), Entry.id.desc()]
    if order == "pinned":
        sorting.insert(0, Entry.is_pinned.desc())
    entries = list(session.scalars(statement.order_by(*sorting).limit(limit + 1)))
    next_cursor = None
    if len(entries) > limit:
        last = entries[limit - 1]
        position = EntryCursor(
            entry_date=last.entry_date,
            created_at=last.created_at,
            id=last.id,
            filter_date=entry_date,
            filter_tag_id=tag_id,
            filter_order=order,
            is_pinned=last.is_pinned,
        )
        next_cursor = (
            base64.urlsafe_b64encode(position.model_dump_json().encode()).decode().rstrip("=")
        )
    return EntryPage(
        items=[EntryResponse.model_validate(entry) for entry in entries[:limit]],
        next_cursor=next_cursor,
    )


def list_revisions(
    session: Session,
    user_id: UUID,
    entry_id: UUID,
    *,
    limit: int,
    before_revision: int | None,
) -> RevisionPage:
    get_entry(session, user_id, entry_id)
    statement = select(EntryRevision).where(EntryRevision.entry_id == entry_id)
    if before_revision is not None:
        statement = statement.where(EntryRevision.revision < before_revision)
    revisions = list(
        session.scalars(statement.order_by(EntryRevision.revision.desc()).limit(limit + 1))
    )
    return RevisionPage(
        items=[RevisionResponse.model_validate(revision) for revision in revisions[:limit]],
        next_cursor=revisions[limit - 1].revision if len(revisions) > limit else None,
    )
