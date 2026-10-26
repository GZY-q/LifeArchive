"""Journal storage; archive dates are separate from UTC instants."""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    and_,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from life_archive.db import Base
from life_archive.media.models import Asset, EntryAsset


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("user_id", "name_key", name="uq_tags_user_id_name_key"),
        UniqueConstraint("id", "user_id", name="uq_tags_id_user_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    name_key: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EntryTag(Base):
    __tablename__ = "entry_tags"
    __table_args__ = (
        ForeignKeyConstraint(
            ["entry_id", "user_id"],
            ["entries.id", "entries.user_id"],
            name="fk_entry_tags_entry_owner",
        ),
        ForeignKeyConstraint(
            ["tag_id", "user_id"],
            ["tags.id", "tags.user_id"],
            name="fk_entry_tags_tag_owner",
        ),
        Index("ix_entry_tags_owner_tag_entry", "user_id", "tag_id", "entry_id"),
    )

    entry_id: Mapped[UUID] = mapped_column(primary_key=True)
    tag_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(nullable=False)


class Entry(Base):
    __tablename__ = "entries"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "client_request_id", name="uq_entries_user_id_client_request_id"
        ),
        UniqueConstraint("id", "user_id", name="uq_entries_id_user_id"),
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
    is_pinned: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=text("false")
    )
    client_request_id: Mapped[UUID | None]
    tags: Mapped[list[Tag]] = relationship(
        secondary=EntryTag.__table__,
        primaryjoin=lambda: and_(Entry.id == EntryTag.entry_id, Entry.user_id == EntryTag.user_id),
        secondaryjoin=lambda: and_(Tag.id == EntryTag.tag_id, Tag.user_id == EntryTag.user_id),
        order_by=lambda: Tag.id,
        viewonly=True,
        lazy="selectin",
    )
    assets: Mapped[list[Asset]] = relationship(
        secondary=EntryAsset.__table__,
        primaryjoin=lambda: and_(
            Entry.id == EntryAsset.entry_id, Entry.user_id == EntryAsset.user_id
        ),
        secondaryjoin=lambda: and_(
            Asset.id == EntryAsset.asset_id, Asset.user_id == EntryAsset.user_id
        ),
        order_by=lambda: Asset.id,
        viewonly=True,
        lazy="selectin",
    )


Index(
    "ix_entries_owner_date_created_id",
    Entry.user_id,
    Entry.entry_date.desc(),
    Entry.created_at.desc(),
    Entry.id.desc(),
)

Index(
    "ix_entries_active_owner_pinned_date_created_id",
    Entry.user_id,
    Entry.is_pinned.desc(),
    Entry.entry_date.desc(),
    Entry.created_at.desc(),
    Entry.id.desc(),
    postgresql_where=Entry.deleted_at.is_(None),
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
    is_pinned: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=text("false")
    )
    tags: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    assets: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
