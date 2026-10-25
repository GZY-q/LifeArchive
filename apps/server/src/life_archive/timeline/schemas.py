from datetime import date as CalendarDate
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from life_archive.journal.schemas import ArchiveDate, EntryPage


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


class OnThisDayCursor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["on-this-day-v1"]
    user_id: UUID
    reference_date: ArchiveDate
    entry_date: ArchiveDate
    created_at: AwareDatetime
    id: UUID
