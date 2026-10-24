"""Owner, revocable opaque sessions, and shared login rate limiting."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from life_archive.db import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("singleton", name="single_owner"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    singleton: Mapped[bool] = mapped_column(
        Boolean, nullable=False, unique=True, default=True, server_default="true"
    )
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class AuthSession(Base):
    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LoginThrottle(Base):
    __tablename__ = "login_throttle"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint("attempts >= 0", name="nonnegative_attempts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
