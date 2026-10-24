"""Calendar labels are user-assigned dates, independent of UTC creation times."""

from calendar import monthrange
from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from life_archive.journal.models import Entry
from life_archive.timeline.schemas import CalendarDay, CalendarResponse


def calendar_month(session: Session, user_id: UUID, year: int, month: int) -> CalendarResponse:
    first = date(year, month, 1)
    # An inclusive upper bound works even for December of year 9999.
    last = date(year, month, monthrange(year, month)[1])
    counts = session.execute(
        select(Entry.entry_date, func.count(Entry.id))
        .where(
            Entry.user_id == user_id,
            Entry.deleted_at.is_(None),
            Entry.entry_date >= first,
            Entry.entry_date <= last,
        )
        .group_by(Entry.entry_date)
        .order_by(Entry.entry_date)
    )
    return CalendarResponse(
        year=year,
        month=month,
        days=[CalendarDay(date=day, entry_count=count) for day, count in counts],
    )
