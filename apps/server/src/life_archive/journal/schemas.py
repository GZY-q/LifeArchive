"""Strict write contracts preserve the supplied Markdown without normalization."""

import re
from datetime import date
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

Markdown = Annotated[str, Field(min_length=1, max_length=100_000)]
RevisionNumber = Annotated[int, Field(strict=True, gt=0)]


def _calendar_date(value: object) -> object:
    if type(value) is date or (
        isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
    ):
        return value
    raise ValueError("Use a calendar date in YYYY-MM-DD format")


ArchiveDate = Annotated[date, BeforeValidator(_calendar_date)]


class EntryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_md: Markdown
    entry_date: ArchiveDate
    client_request_id: UUID | None = None

    @field_validator("content_md")
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Journal content must not be blank")
        if "\x00" in value:
            raise ValueError("Journal content cannot contain NUL characters")
        return value


class EntryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: RevisionNumber
    content_md: Markdown | None = None
    entry_date: ArchiveDate | None = None

    @model_validator(mode="after")
    def require_changes(self) -> Self:
        changed = self.model_fields_set - {"expected_revision"}
        if not changed:
            raise ValueError("Provide content_md or entry_date to edit")
        if any(getattr(self, name) is None for name in changed):
            raise ValueError("Journal content and entry_date cannot be null")
        if self.content_md is not None and not self.content_md.strip():
            raise ValueError("Journal content must not be blank")
        if self.content_md is not None and "\x00" in self.content_md:
            raise ValueError("Journal content cannot contain NUL characters")
        return self


class EntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    content_md: str
    entry_date: date
    revision: int
    occurred_at: AwareDatetime | None
    occurred_timezone: str | None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class RevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    revision: int
    content_md: str
    entry_date: date
    changed_at: AwareDatetime
    editor_id: UUID


class EntryPage(BaseModel):
    items: list[EntryResponse]
    next_cursor: str | None


class RevisionPage(BaseModel):
    items: list[RevisionResponse]
    next_cursor: int | None


class EntryCursor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_date: date
    created_at: AwareDatetime
    id: UUID
    filter_date: date | None
