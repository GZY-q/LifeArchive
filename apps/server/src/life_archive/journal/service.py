"""Owner-scoped reads and atomic writes of originals plus revision snapshots."""

import base64
import binascii
from datetime import UTC, date, datetime
from typing import NoReturn
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, tuple_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from life_archive.journal.models import Entry, EntryRevision
from life_archive.journal.schemas import (
    EntryCreate,
    EntryCursor,
    EntryPage,
    EntryResponse,
    EntryUpdate,
    RevisionPage,
    RevisionResponse,
)


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
    session.add(
        EntryRevision(
            entry_id=entry.id,
            editor_id=editor_id,
            content_md=entry.content_md,
            entry_date=entry.entry_date,
            revision=entry.revision,
            changed_at=entry.updated_at,
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
    if original.content_md != payload.content_md or original.entry_date != payload.entry_date:
        raise _conflict(
            "idempotency_conflict", "This request ID was already used for a different journal entry"
        )
    return entry, False


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
    )
    try:
        session.add(entry)
        session.flush()  # Obtain its ID before adding the foreign-key snapshot.
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
    changes = payload.model_dump(exclude_unset=True, exclude={"expected_revision"})
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


def _decode_cursor(cursor: str, filter_date: date | None) -> EntryCursor:
    try:
        decoded = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        value = EntryCursor.model_validate_json(decoded)
        if value.filter_date != filter_date:
            raise ValueError("Cursor belongs to a different date filter")
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
) -> EntryPage:
    statement = select(Entry).where(Entry.user_id == user_id, Entry.deleted_at.is_(None))
    if entry_date is not None:
        statement = statement.where(Entry.entry_date == entry_date)
    if cursor is not None:
        position = _decode_cursor(cursor, entry_date)
        statement = statement.where(
            tuple_(Entry.entry_date, Entry.created_at, Entry.id)
            < (position.entry_date, position.created_at, position.id)
        )
    entries = list(
        session.scalars(
            statement.order_by(
                Entry.entry_date.desc(), Entry.created_at.desc(), Entry.id.desc()
            ).limit(limit + 1)
        )
    )
    next_cursor = None
    if len(entries) > limit:
        last = entries[limit - 1]
        position = EntryCursor(
            entry_date=last.entry_date,
            created_at=last.created_at,
            id=last.id,
            filter_date=entry_date,
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
