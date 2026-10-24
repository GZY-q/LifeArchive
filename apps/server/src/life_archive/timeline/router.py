from typing import Annotated

from fastapi import APIRouter, Depends, Query

from life_archive.auth.dependencies import DbSession, require_user
from life_archive.auth.models import User
from life_archive.journal.schemas import ArchiveDate
from life_archive.journal.service import list_entries
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
