"""Journal tests use real PostgreSQL; authentication itself is tested separately."""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from life_archive.auth.dependencies import require_csrf, require_user
from life_archive.auth.models import User


@pytest.fixture
def journal_owner(db_session: Session) -> User:
    owner = User(
        id=uuid4(),
        username="journal-owner",
        password_hash="unused-in-journal-tests",
        timezone="Asia/Shanghai",
    )
    db_session.add(owner)
    db_session.commit()
    return owner


@pytest.fixture
def journal_client(db_client: TestClient, journal_owner: User) -> Iterator[TestClient]:
    # Retain real HTTP routing and per-request database sessions, replacing only auth.
    db_client.app.dependency_overrides[require_user] = lambda: journal_owner
    db_client.app.dependency_overrides[require_csrf] = lambda: journal_owner
    yield db_client
    db_client.app.dependency_overrides.pop(require_user, None)
    db_client.app.dependency_overrides.pop(require_csrf, None)
