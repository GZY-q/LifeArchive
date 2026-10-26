"""Image originals are private files; metadata and owner constraints live in PG."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from life_archive.db import Base


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("user_id", "sha256", name="uq_assets_user_id_sha256"),
        UniqueConstraint("id", "user_id", name="uq_assets_id_user_id"),
        CheckConstraint("byte_size > 0 AND byte_size <= 5242880", name="bounded_bytes"),
        CheckConstraint(
            "width > 0 AND height > 0 AND width <= 20000 AND height <= 20000 "
            "AND CAST(width AS BIGINT) * height <= 20000000",
            name="bounded_pixels",
        ),
        CheckConstraint(
            "mime_type IN ('image/jpeg', 'image/png', 'image/webp')", name="raster_mime"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(32), nullable=False)
    byte_size: Mapped[int] = mapped_column(nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int] = mapped_column(nullable=False)
    height: Mapped[int] = mapped_column(nullable=False)
    storage_key: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EntryAsset(Base):
    __tablename__ = "entry_assets"
    __table_args__ = (
        ForeignKeyConstraint(
            ["entry_id", "user_id"],
            ["entries.id", "entries.user_id"],
            name="fk_entry_assets_entry_owner",
        ),
        ForeignKeyConstraint(
            ["asset_id", "user_id"],
            ["assets.id", "assets.user_id"],
            name="fk_entry_assets_asset_owner",
        ),
        Index("ix_entry_assets_owner_asset_entry", "user_id", "asset_id", "entry_id"),
    )

    entry_id: Mapped[UUID] = mapped_column(primary_key=True)
    asset_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(nullable=False)
