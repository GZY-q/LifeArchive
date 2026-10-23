from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from life_archive import db


@pytest.fixture
def sessions(monkeypatch: pytest.MonkeyPatch) -> Iterator[sessionmaker[Session]]:
    # SQLite exercises SQLAlchemy transaction cleanup only, not PostgreSQL compatibility.
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE session_probe (value TEXT NOT NULL)"))
    factory = sessionmaker(engine)
    monkeypatch.setattr(db, "get_session_factory", lambda: factory)
    yield factory
    engine.dispose()


def test_dependency_preserves_explicit_commit(sessions: sessionmaker[Session]) -> None:
    dependency = db.get_db_session()
    session = next(dependency)
    with session.begin():
        session.execute(text("INSERT INTO session_probe VALUES ('committed')"))
    dependency.close()

    with sessions() as reader:
        assert reader.scalar(text("SELECT value FROM session_probe")) == "committed"


def test_dependency_never_commits_implicitly(sessions: sessionmaker[Session]) -> None:
    dependency = db.get_db_session()
    next(dependency).execute(text("INSERT INTO session_probe VALUES ('uncommitted')"))
    dependency.close()

    with sessions() as reader:
        assert reader.scalar(text("SELECT count(*) FROM session_probe")) == 0


def test_dependency_rolls_back_on_error(sessions: sessionmaker[Session]) -> None:
    dependency = db.get_db_session()
    next(dependency).execute(text("INSERT INTO session_probe VALUES ('failed')"))
    with pytest.raises(RuntimeError, match="service failed"):
        dependency.throw(RuntimeError("service failed"))

    with sessions() as reader:
        assert reader.scalar(text("SELECT count(*) FROM session_probe")) == 0
