"""Journal storage; archive dates are separate from UTC instants."""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from life_archive.db import Base


class Entry(Base):
    __tablename__ = "entries"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "client_request_id", name="uq_entries_user_id_client_request_id"
        ),
        CheckConstraint("revision > 0", name="positive_revision"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    occurred_timezone: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(nullable=False)
    client_request_id: Mapped[UUID | None]


Index(
    "ix_entries_owner_date_created_id",
    Entry.user_id,
    Entry.entry_date.desc(),
    Entry.created_at.desc(),
    Entry.id.desc(),
)


class EntryRevision(Base):
    __tablename__ = "entry_revisions"
    __table_args__ = (
        UniqueConstraint("entry_id", "revision", name="uq_entry_revisions_entry_id_revision"),
        CheckConstraint("revision > 0", name="positive_revision"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    entry_id: Mapped[UUID] = mapped_column(ForeignKey("entries.id"), nullable=False)
    editor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    revision: Mapped[int] = mapped_column(nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
