from datetime import date as CalendarDate

from pydantic import BaseModel, Field

from life_archive.journal.schemas import EntryPage


class CalendarDay(BaseModel):
    date: CalendarDate
    entry_count: int = Field(gt=0)


class CalendarResponse(BaseModel):
    year: int = Field(ge=1, le=9999)
    month: int = Field(ge=1, le=12)
    days: list[CalendarDay]


class DayResponse(BaseModel):
    date: CalendarDate
    entries: EntryPage
