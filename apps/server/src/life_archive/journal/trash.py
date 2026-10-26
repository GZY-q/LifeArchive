"""Owner-scoped trash browsing and revision-checked restoration of the same entry."""

import base64
import binascii
import re
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import AwareDatetime, BaseModel, ConfigDict, ValidationError
from sqlalchemy import select, tuple_, update
from sqlalchemy.orm import Session

from life_archive.journal.models import Entry
from life_archive.journal.schemas import TrashEntryResponse, TrashPage
from life_archive.journal.service import _conflict, _not_found, _snapshot


class TrashCursor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["trash-v1"]
    user_id: UUID
    deleted_at: AwareDatetime
    id: UUID


def _decode_cursor(cursor: str, user_id: UUID) -> TrashCursor:
    try:
        if re.fullmatch(r"[A-Za-z0-9_-]+", cursor) is None:
            raise ValueError("Invalid cursor encoding")
        decoded = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        position = TrashCursor.model_validate_json(decoded)
        if position.user_id != user_id:
            raise ValueError("Invalid cursor owner")
    except (ValueError, binascii.Error, ValidationError) as error:
        raise HTTPException(status_code=422, detail="Invalid pagination cursor") from error
    return position


def list_trash(session: Session, user_id: UUID, *, limit: int, cursor: str | None) -> TrashPage:
    statement = select(Entry).where(Entry.user_id == user_id, Entry.deleted_at.is_not(None))
    if cursor is not None:
        position = _decode_cursor(cursor, user_id)
        statement = statement.where(
            tuple_(Entry.deleted_at, Entry.id) < (position.deleted_at, position.id)
        )
    entries = list(
        session.scalars(
            statement.order_by(Entry.deleted_at.desc(), Entry.id.desc()).limit(limit + 1)
        )
    )
    next_cursor = None
    if len(entries) > limit:
        last = entries[limit - 1]
        position = TrashCursor(
            version="trash-v1", user_id=user_id, deleted_at=last.deleted_at, id=last.id
        )
        next_cursor = (
            base64.urlsafe_b64encode(position.model_dump_json().encode()).decode().rstrip("=")
        )
    return TrashPage(
        items=[TrashEntryResponse.model_validate(entry) for entry in entries[:limit]],
        next_cursor=next_cursor,
    )


def restore_entry(session: Session, user_id: UUID, entry_id: UUID, expected_revision: int) -> Entry:
    try:
        entry = session.scalar(
            update(Entry)
            .where(
                Entry.id == entry_id,
                Entry.user_id == user_id,
                Entry.deleted_at.is_not(None),
                Entry.revision == expected_revision,
            )
            .values(deleted_at=None, updated_at=datetime.now(UTC), revision=Entry.revision + 1)
            .returning(Entry)
            .execution_options(populate_existing=True)
        )
        if entry is None:
            session.rollback()
            existing = session.scalar(
                select(Entry.id).where(Entry.id == entry_id, Entry.user_id == user_id)
            )
            if existing is None:
                raise _not_found()
            raise _conflict(
                "revision_conflict",
                "The journal entry changed or was restored; reload before retrying",
            )
        # Never trust a relationship cached before another request's completed edit.
        session.expire(entry, ["tags", "assets"])
        _snapshot(session, entry, user_id)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return entry
