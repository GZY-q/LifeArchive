from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from life_archive.auth.models import LoginThrottle, User
from life_archive.auth.service import LoginRateLimited, consume_login_attempt


def test_failed_logins_are_limited_across_usernames_and_window_recovers(
    auth_client: TestClient, owner: User, db_session: Session
) -> None:
    for number in range(5):
        response = auth_client.post(
            "/api/v1/auth/login", json={"username": f"unknown-{number}", "password": "incorrect"}
        )
        assert response.status_code == 401
    limited = auth_client.post(
        "/api/v1/auth/login",
        json={"username": owner.username, "password": "test-only-owner-passphrase"},
    )
    assert limited.status_code == 429
    assert 1 <= int(limited.headers["retry-after"]) <= 300
    db_session.execute(
        update(LoginThrottle).values(window_started_at=datetime.now(UTC) - timedelta(seconds=301))
    )
    db_session.commit()
    assert (
        auth_client.post(
            "/api/v1/auth/login",
            json={"username": owner.username, "password": "test-only-owner-passphrase"},
        ).status_code
        == 200
    )


def test_parallel_connections_share_one_atomic_attempt_budget(
    session_factory: sessionmaker[Session],
) -> None:
    def attempt(_: int) -> bool:
        with session_factory() as db:
            try:
                consume_login_attempt(db)
            except LoginRateLimited:
                return False
            return True

    with ThreadPoolExecutor(max_workers=10) as executor:
        outcomes = list(executor.map(attempt, range(10)))
    assert outcomes.count(True) == 5
    with session_factory() as db:
        assert db.scalar(select(LoginThrottle.attempts)) == 5
