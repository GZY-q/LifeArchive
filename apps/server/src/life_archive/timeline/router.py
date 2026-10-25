from typing import Annotated

from fastapi import APIRouter, Depends, Query

from life_archive.auth.dependencies import DbSession, require_user
from life_archive.auth.models import User
from life_archive.journal.schemas import ArchiveDate
from life_archive.journal.service import list_entries
from life_archive.timeline.on_this_day import on_this_day_entries, owner_today
from life_archive.timeline.schemas import CalendarResponse, DayResponse
from life_archive.timeline.service import calendar_month

router = APIRouter(tags=["timeline"])
Owner = Annotated[User, Depends(require_user)]


@router.get("/calendar", response_model=CalendarResponse)
def month(
    user: Owner,
    session: DbSession,
    year: Annotated[int, Query(ge=1, le=9999)],
    month: Annotated[int, Query(ge=1, le=12)],
) -> CalendarResponse:
    return calendar_month(session, user.id, year, month)


@router.get("/days/{entry_date}", response_model=DayResponse)
def day(
    entry_date: ArchiveDate,
    user: Owner,
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=1024)] = None,
) -> DayResponse:
    return DayResponse(
        date=entry_date,
        entries=list_entries(session, user.id, limit=limit, cursor=cursor, entry_date=entry_date),
    )


@router.get("/on-this-day", response_model=DayResponse)
def on_this_day(
    user: Owner,
    session: DbSession,
    reference_date: Annotated[ArchiveDate | None, Query(alias="date")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(min_length=1, max_length=2048)] = None,
) -> DayResponse:
    selected = reference_date if reference_date is not None else owner_today(user.timezone)
    return DayResponse(
        date=selected,
        entries=on_this_day_entries(session, user.id, selected, limit=limit, cursor=cursor),
    )
