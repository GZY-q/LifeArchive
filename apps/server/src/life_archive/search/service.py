"""Owner-scoped literal substring search; never writes or searches old revisions."""

import base64
import binascii
import hashlib
import hmac
import json
import re
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from life_archive.journal.models import Entry
from life_archive.journal.schemas import EntryPage, EntryResponse
from life_archive.search.schemas import SearchCursor, SearchRequest


def _filter_digest(user_id: UUID, payload: SearchRequest) -> str:
    filters = {
        "owner": str(user_id),
        "query": payload.query,
        "date_from": payload.date_from.isoformat() if payload.date_from else None,
        "date_to": payload.date_to.isoformat() if payload.date_to else None,
    }
    normalized = json.dumps(filters, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode()).hexdigest()


def _decode_cursor(cursor: str, filter_digest: str) -> SearchCursor:
    try:
        if re.fullmatch(r"[A-Za-z0-9_-]+", cursor) is None:
            raise ValueError("Invalid cursor encoding")
        decoded = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        position = SearchCursor.model_validate_json(decoded)
        if not hmac.compare_digest(position.filter_digest, filter_digest):
            raise ValueError("Invalid cursor filters")
    except (ValueError, binascii.Error, ValidationError) as error:
        raise HTTPException(status_code=422, detail="Invalid request") from error
    return position


def search_entries(session: Session, user_id: UUID, payload: SearchRequest) -> EntryPage:
    digest = _filter_digest(user_id, payload)
    statement = select(Entry).where(Entry.user_id == user_id, Entry.deleted_at.is_(None))
    if payload.query:
        # SQLAlchemy escapes LIKE metacharacters and binds the entire literal query.
        statement = statement.where(Entry.content_md.icontains(payload.query, autoescape=True))
    if payload.date_from is not None:
        statement = statement.where(Entry.entry_date >= payload.date_from)
    if payload.date_to is not None:
        statement = statement.where(Entry.entry_date <= payload.date_to)
    if payload.cursor is not None:
        position = _decode_cursor(payload.cursor, digest)
        statement = statement.where(
            tuple_(Entry.entry_date, Entry.created_at, Entry.id)
            < (position.entry_date, position.created_at, position.id)
        )
    entries = list(
        session.scalars(
            statement.order_by(
                Entry.entry_date.desc(), Entry.created_at.desc(), Entry.id.desc()
            ).limit(payload.limit + 1)
        )
    )
    next_cursor = None
    if len(entries) > payload.limit:
        last = entries[payload.limit - 1]
        position = SearchCursor(
            version="search-v1",
            filter_digest=digest,
            entry_date=last.entry_date,
            created_at=last.created_at,
            id=last.id,
        )
        next_cursor = (
            base64.urlsafe_b64encode(position.model_dump_json().encode()).decode().rstrip("=")
        )
    return EntryPage(
        items=[EntryResponse.model_validate(entry) for entry in entries[: payload.limit]],
        next_cursor=next_cursor,
    )
