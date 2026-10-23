"""Lazy PostgreSQL connections and request-scoped synchronous sessions."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from life_archive.settings import get_database_settings


class Base(DeclarativeBase):
    # Stable names make future Alembic revisions and constraint changes reviewable.
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        get_database_settings().url,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"connect_timeout": 5, "options": "-c timezone=UTC"},
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db_session() -> Iterator[Session]:
    """Always close; services must explicitly commit or use session.begin()."""
    with get_session_factory()() as session:
        yield session
