"""Strict write contracts preserve the supplied Markdown without normalization."""

import re
import unicodedata
from datetime import date
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

from life_archive.media.schemas import AssetResponse

Markdown = Annotated[str, Field(min_length=1, max_length=100_000)]
RevisionNumber = Annotated[int, Field(strict=True, gt=0)]
TagIds = Annotated[list[UUID], Field(max_length=20)]
AssetIds = Annotated[list[UUID], Field(max_length=10)]
EntryOrder = Literal["date", "pinned"]


def normalize_tag_name(value: str) -> tuple[str, str]:
    if any(unicodedata.category(char) in {"Cc", "Cs", "Zl", "Zp"} for char in value):
        raise ValueError("Tag names cannot contain control characters or line breaks")
    name = unicodedata.normalize("NFC", value.strip())
    key = unicodedata.normalize("NFKC", name).casefold()
    if not 1 <= len(name) <= 40 or not 1 <= len(key) <= 40:
        raise ValueError("Tag names must contain 1 to 40 characters after normalization")
    return name, key


def unique_tag_ids(value: list[UUID] | None) -> list[UUID] | None:
    if value is not None and len(set(value)) != len(value):
        raise ValueError("Duplicate tag IDs are not allowed")
    return value


def unique_asset_ids(value: list[UUID] | None) -> list[UUID] | None:
    if value is not None and len(set(value)) != len(value):
        raise ValueError("Duplicate asset IDs are not allowed")
    return value


class TagCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=256)]

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_tag_name(value)[0]


class TagRename(TagCreate):
    # This is a comparison token from a prior catalogue read, not a new name.
    expected_name: Annotated[str, Field(strict=True, min_length=1, max_length=40)]


class TagLabel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str


class TagResponse(TagLabel):
    created_at: AwareDatetime


class TagPage(BaseModel):
    items: list[TagResponse]
    next_cursor: UUID | None


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
    tag_ids: TagIds = Field(default_factory=list)
    asset_ids: AssetIds = Field(default_factory=list)
    is_pinned: StrictBool = False

    _unique_tags = field_validator("tag_ids")(unique_tag_ids)
    _unique_assets = field_validator("asset_ids")(unique_asset_ids)

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
    tag_ids: TagIds | None = None
    asset_ids: AssetIds | None = None
    is_pinned: StrictBool | None = None

    _unique_tags = field_validator("tag_ids")(unique_tag_ids)
    _unique_assets = field_validator("asset_ids")(unique_asset_ids)

    @model_validator(mode="after")
    def require_changes(self) -> Self:
        changed = self.model_fields_set - {"expected_revision"}
        if not changed:
            raise ValueError("Provide at least one editable journal field")
        if any(getattr(self, name) is None for name in changed):
            raise ValueError("Journal fields cannot be null")
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
    tags: list[TagLabel]
    assets: list[AssetResponse]
    is_pinned: bool


class EntryRestore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: RevisionNumber


class TrashEntryResponse(EntryResponse):
    deleted_at: AwareDatetime


class TrashPage(BaseModel):
    items: list[TrashEntryResponse]
    next_cursor: str | None


class RevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    revision: int
    content_md: str
    entry_date: date
    changed_at: AwareDatetime
    editor_id: UUID
    tags: list[TagLabel]
    assets: list[AssetResponse]
    is_pinned: bool


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
    filter_tag_id: UUID | None = None
    filter_order: EntryOrder = "date"
    is_pinned: StrictBool = False
