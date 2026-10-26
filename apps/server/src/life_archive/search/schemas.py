"""Bounded JSON-only search filters and a separate versioned keyset cursor."""

from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from life_archive.journal.schemas import ArchiveDate


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(default="", strict=True, max_length=200)
    date_from: ArchiveDate | None = None
    date_to: ArchiveDate | None = None
    tag_id: UUID | None = None
    limit: int = Field(default=20, strict=True, ge=1, le=100)
    cursor: str | None = Field(default=None, strict=True, min_length=1, max_length=2048)

    @field_validator("query", mode="before")
    @classmethod
    def normalize_query(cls, value: object) -> object:
        if isinstance(value, str):
            if "\x00" in value:
                raise ValueError("Invalid search query")
            return value.strip()
        return value

    @model_validator(mode="after")
    def require_filters(self) -> Self:
        if (
            not self.query
            and self.date_from is None
            and self.date_to is None
            and self.tag_id is None
        ):
            raise ValueError("Provide a search query, date bound or tag")
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_from > self.date_to
        ):
            raise ValueError("Invalid date range")
        return self


class SearchCursor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["search-v1"]
    filter_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    entry_date: ArchiveDate
    created_at: AwareDatetime
    id: UUID
