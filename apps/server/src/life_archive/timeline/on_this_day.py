"""Read past years' exact calendar anniversaries without changing journal originals."""

import base64
import binascii
import re
from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import extract, select, tuple_
from sqlalchemy.orm import Session

from life_archive.journal.models import Entry
from life_archive.journal.schemas import EntryPage, EntryResponse
from life_archive.timeline.schemas import OnThisDayCursor


def owner_today(timezone: str) -> date:
    return datetime.now(UTC).astimezone(ZoneInfo(timezone)).date()


def _decode_cursor(cursor: str, user_id: UUID, reference_date: date) -> OnThisDayCursor:
    try:
        if re.fullmatch(r"[A-Za-z0-9_-]+", cursor) is None:
            raise ValueError("Invalid cursor encoding")
        decoded = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        position = OnThisDayCursor.model_validate_json(decoded)
        if (
            position.user_id != user_id
            or position.reference_date != reference_date
            or position.entry_date.year >= reference_date.year
            or (position.entry_date.month, position.entry_date.day)
            != (reference_date.month, reference_date.day)
        ):
            raise ValueError("Invalid cursor scope")
    except (ValueError, binascii.Error, ValidationError) as error:
        raise HTTPException(status_code=422, detail="Invalid request") from error
    return position


def on_this_day_entries(
    session: Session,
    user_id: UUID,
    reference_date: date,
    *,
    limit: int = 20,
    cursor: str | None = None,
) -> EntryPage:
    # Restrict years with a date bound; never shift February 29 to a nearby day.
    statement = select(Entry).where(
        Entry.user_id == user_id,
        Entry.deleted_at.is_(None),
        Entry.entry_date < date(reference_date.year, 1, 1),
        extract("month", Entry.entry_date) == reference_date.month,
        extract("day", Entry.entry_date) == reference_date.day,
    )
    if cursor is not None:
        position = _decode_cursor(cursor, user_id, reference_date)
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
        position = OnThisDayCursor(
            version="on-this-day-v1",
            user_id=user_id,
            reference_date=reference_date,
            entry_date=last.entry_date,
            created_at=last.created_at,
            id=last.id,
        )
        next_cursor = (
            base64.urlsafe_b64encode(position.model_dump_json().encode()).decode().rstrip("=")
        )
    return EntryPage(
        items=[EntryResponse.model_validate(entry) for entry in entries[:limit]],
        next_cursor=next_cursor,
    )
