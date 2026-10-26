"""Four focused PG cases for credential/session rotation and its lock boundaries."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event, current_thread

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from life_archive.auth import service
from life_archive.auth.models import AuthSession, LoginThrottle, User
from life_archive.auth.security import SESSION_COOKIE, token_digest, verify_password

ORIGIN = "http://127.0.0.1:8080"
PASSWORD = "test-only-owner-passphrase"
NEW_PASSWORD = "new-test-only-passphrase"


def test_password_change_rotates_all_sessions_and_preserves_journals(
    authenticated: tuple[TestClient, str], owner: User, db_session: Session
) -> None:
    client, csrf = authenticated
    old = client.cookies[SESSION_COOKIE]
    entry = client.post(
        "/api/v1/entries",
        json={"content_md": "  # 私密原文\r\n", "entry_date": "2000-02-29"},
        headers={"X-CSRF-Token": csrf},
    ).json()
    with TestClient(client.app, base_url=ORIGIN) as other:
        response = other.post(
            "/api/v1/auth/login",
            json={"username": owner.username, "password": PASSWORD},
            headers={"Origin": ORIGIN, "X-LifeArchive-Request": "1"},
        )
        assert response.status_code == 200
        other_token = other.cookies[SESSION_COOKIE]
        changed = client.post(
            "/api/v1/auth/password",
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            headers={"X-CSRF-Token": csrf},
        )
        assert changed.status_code == 200
        assert changed.headers["cache-control"] == "no-store"
        assert "HttpOnly" in changed.headers["set-cookie"]
        assert "SameSite=lax" in changed.headers["set-cookie"]
        assert "Path=/api/v1" in changed.headers["set-cookie"]
        new_token = client.cookies[SESSION_COOKIE]
        new_csrf = changed.json()["csrf_token"]
        assert new_token not in {old, other_token} and new_csrf != csrf
        assert client.get("/api/v1/auth/me").json() == changed.json()
        for token in (old, other_token):
            assert (
                other.get(
                    "/api/v1/auth/me", headers={"Cookie": f"{SESSION_COOKIE}={token}"}
                ).status_code
                == 401
            )
        assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 403
        assert client.get("/api/v1/entries/" + entry["id"]).json() == entry
        history = client.get("/api/v1/entries/" + entry["id"] + "/revisions").json()["items"]
        assert len(history) == 1 and history[0]["content_md"] == entry["content_md"]
        assert PASSWORD not in changed.text and NEW_PASSWORD not in changed.text
        db_session.refresh(owner)
        assert verify_password(owner.password_hash, NEW_PASSWORD)
        assert not verify_password(owner.password_hash, PASSWORD)
        assert (
            db_session.scalar(
                select(func.count())
                .select_from(AuthSession)
                .where(AuthSession.revoked_at.is_(None))
            )
            == 1
        )
        assert (
            client.post(
                "/api/v1/auth/login", json={"username": owner.username, "password": PASSWORD}
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/v1/auth/login", json={"username": owner.username, "password": NEW_PASSWORD}
            ).status_code
            == 200
        )


def test_revoke_validation_wrong_password_and_shared_attempt_budget(
    authenticated: tuple[TestClient, str], db_session: Session, owner: User
) -> None:
    client, csrf = authenticated
    old_token, old_hash = client.cookies[SESSION_COOKIE], owner.password_hash
    headers = {"X-CSRF-Token": csrf}
    path = "/api/v1/auth/sessions/revoke"
    for extra in (
        {"Origin": "https://evil.example"},
        {"X-LifeArchive-Request": "0"},
        {"X-CSRF-Token": "bad"},
    ):
        assert (
            client.post(
                path, json={"current_password": PASSWORD}, headers={**headers, **extra}
            ).status_code
            == 403
        )
    assert (
        client.post(
            path, content=b"plain", headers={**headers, "Content-Type": "text/plain"}
        ).status_code
        == 415
    )
    for body in ({}, {"current_password": "secret", "extra": True}):
        response = client.post(path, json=body, headers=headers)
        assert response.status_code == 422 and response.json() == {"detail": "Invalid request"}
    for raw in (
        b'{"current_password":"\\ud800"}',
        b'{"current_password":"old-password", "new_password":"abcdefghijklmno\\ud800"}',
    ):
        response = client.post(
            path if b"new_password" not in raw else "/api/v1/auth/password",
            content=raw,
            headers={**headers, "Content-Type": "application/json"},
        )
        assert response.status_code == 422 and response.json() == {"detail": "Invalid request"}
    for new in (" " * 15, "x" * 14, "a" * 15 + "\x00"):
        assert (
            client.post(
                "/api/v1/auth/password",
                json={"current_password": PASSWORD, "new_password": new},
                headers=headers,
            ).status_code
            == 422
        )
    assert db_session.scalar(select(LoginThrottle.attempts)) == 1
    unchanged = client.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": PASSWORD},
        headers=headers,
    )
    assert (
        unchanged.status_code == 422 and unchanged.json()["detail"]["code"] == "password_unchanged"
    )
    wrong = client.post(path, json={"current_password": "wrong-current"}, headers=headers)
    assert wrong.status_code == 403 and wrong.json()["detail"]["code"] == "invalid_current_password"
    assert client.cookies[SESSION_COOKIE] == old_token
    assert client.get("/api/v1/auth/me").status_code == 200
    rotated = client.post(path, json={"current_password": PASSWORD}, headers=headers)
    assert rotated.status_code == 200
    assert client.cookies[SESSION_COOKIE] != old_token
    csrf = rotated.json()["csrf_token"]
    db_session.refresh(owner)
    assert owner.password_hash == old_hash
    assert (
        client.get(
            "/api/v1/auth/me", headers={"Cookie": f"{SESSION_COOKIE}={old_token}"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            path, json={"current_password": "wrong-again"}, headers={"X-CSRF-Token": csrf}
        ).status_code
        == 403
    )
    for endpoint, body in (
        (path, {"current_password": PASSWORD}),
        ("/api/v1/auth/password", {"current_password": PASSWORD, "new_password": NEW_PASSWORD}),
    ):
        limited = client.post(endpoint, json=body, headers={"X-CSRF-Token": csrf})
        assert limited.status_code == 429 and int(limited.headers["retry-after"]) >= 1
        assert limited.headers["cache-control"] == "no-store"
        assert "set-cookie" not in limited.headers
    assert client.get("/api/v1/auth/me").status_code == 200
    db_session.refresh(owner)
    assert owner.password_hash == old_hash


def test_waiting_login_refreshes_cached_owner_after_password_rotation(
    session_factory: sessionmaker[Session], owner: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_id = owner.id
    with session_factory() as db:
        token, _ = service.create_session(db, owner, None)
    cached, locked, attempted = Event(), Event(), Event()
    original_verify = service.verify_password

    def verify(digest: str, password: str) -> bool:
        if current_thread().name.startswith("rotate"):
            locked.set()
            assert attempted.wait(10)
        return original_verify(digest, password)

    monkeypatch.setattr(service, "verify_password", verify)

    def login() -> str | None:
        with session_factory() as db:
            cached_owner = db.get(User, owner_id)
            assert cached_owner is not None
            db.commit()  # Retain a deliberately stale identity-map instance.
            cached.set()
            assert locked.wait(10)
            attempted.set()
            authenticated = service.authenticate(db, "owner", PASSWORD)
            if authenticated is None:
                return None
            return service.create_session(db, authenticated, None)[0]

    def rotate() -> str:
        assert cached.wait(10)
        with session_factory() as db:
            return service.rotate_account_session(db, owner_id, token, PASSWORD, NEW_PASSWORD)[1]

    with (
        ThreadPoolExecutor(1, thread_name_prefix="login") as logins,
        ThreadPoolExecutor(1, thread_name_prefix="rotate") as rotations,
    ):
        login_result, rotation_result = logins.submit(login), rotations.submit(rotate)
        assert rotation_result.result(timeout=15)
        assert login_result.result(timeout=15) is None
    with session_factory() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuthSession)
                .where(AuthSession.revoked_at.is_(None))
            )
            == 1
        )


def test_simultaneous_changes_recheck_revocation_and_expiry_under_locks(
    session_factory: sessionmaker[Session], owner: User
) -> None:
    owner_id = owner.id
    with session_factory() as db:
        token, _ = service.create_session(db, owner, None)
    barrier = Barrier(2)

    def rotate(index: int) -> tuple[int, str | None]:
        with session_factory() as db:
            barrier.wait(timeout=10)
            try:
                result = service.rotate_account_session(
                    db, owner_id, token, PASSWORD, NEW_PASSWORD + str(index)
                )
                return 200, result[1]
            except HTTPException as error:
                return error.status_code, None

    with ThreadPoolExecutor(2) as executor:
        results = list(executor.map(rotate, range(2)))
    assert sorted(status for status, _ in results) == [200, 401]
    replacement = next(token for status, token in results if status == 200)
    with session_factory() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuthSession)
                .where(AuthSession.revoked_at.is_(None))
            )
            == 1
        )
        db.execute(
            update(AuthSession)
            .where(AuthSession.token_hash == token_digest(replacement))
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        db.commit()
        with pytest.raises(HTTPException) as expired:
            service.rotate_account_session(db, owner_id, replacement, PASSWORD)
        assert expired.value.status_code == 401
