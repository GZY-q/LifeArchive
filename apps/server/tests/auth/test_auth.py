from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from life_archive.auth.models import AuthSession, User
from life_archive.auth.security import SESSION_COOKIE, SESSION_MAX_AGE, token_digest
from life_archive.settings import get_auth_settings

OWNER_PASSWORD = "test-only-owner-passphrase"
ORIGIN = "http://127.0.0.1:8080"


def test_login_sets_private_cookie_and_stores_only_session_digest(
    auth_client: TestClient, owner: User, db_session: Session
) -> None:
    response = auth_client.post(
        "/api/v1/auth/login", json={"username": owner.username, "password": OWNER_PASSWORD}
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/api/v1" in cookie
    assert f"Max-Age={SESSION_MAX_AGE}" in cookie
    raw = auth_client.cookies[SESSION_COOKIE]
    record = db_session.scalar(select(AuthSession))
    assert record is not None and record.token_hash == token_digest(raw)
    assert record.token_hash != raw
    assert record.expires_at - record.created_at == timedelta(days=7)
    assert record.created_at.utcoffset() == timedelta(0)
    assert set(response.json()["user"]) == {"id", "username", "timezone"}
    assert OWNER_PASSWORD not in response.text and owner.password_hash not in response.text
    assert raw not in response.text
    me = auth_client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json() == response.json()
    assert me.headers["cache-control"] == "no-store"


def test_secure_cookie_flag_is_enabled_when_configured(
    auth_client: TestClient, owner: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIFEARCHIVE_COOKIE_SECURE", "true")
    get_auth_settings.cache_clear()
    response = auth_client.post(
        "/api/v1/auth/login", json={"username": owner.username, "password": OWNER_PASSWORD}
    )
    assert response.status_code == 200
    assert "Secure" in response.headers["set-cookie"]


def test_login_requires_trusted_origin_json_and_custom_header(
    auth_client: TestClient, owner: User
) -> None:
    body = {"username": owner.username, "password": OWNER_PASSWORD}
    assert (
        auth_client.post(
            "/api/v1/auth/login", json=body, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert (
        auth_client.post(
            "/api/v1/auth/login", json=body, headers={"X-LifeArchive-Request": "0"}
        ).status_code
        == 403
    )
    assert (
        auth_client.post(
            "/api/v1/auth/login", content="anything", headers={"Content-Type": "text/plain"}
        ).status_code
        == 415
    )
    auth_client.headers.pop("origin")
    assert auth_client.post("/api/v1/auth/login", json=body).status_code == 403


def test_wrong_username_and_password_have_the_same_generic_error(
    auth_client: TestClient, owner: User
) -> None:
    wrong_password = auth_client.post(
        "/api/v1/auth/login", json={"username": owner.username, "password": "incorrect"}
    )
    wrong_username = auth_client.post(
        "/api/v1/auth/login", json={"username": "不存在", "password": OWNER_PASSWORD}
    )
    assert wrong_password.status_code == wrong_username.status_code == 401
    assert wrong_password.json() == wrong_username.json() == {"detail": "Invalid credentials"}
    assert "set-cookie" not in wrong_username.headers


def test_validation_errors_do_not_echo_passwords_or_json_keys(auth_client: TestClient) -> None:
    private = "must-never-appear-in-response"
    malformed = auth_client.post(
        "/api/v1/auth/login", json={"username": "owner", "password": {private: private}}
    )
    extra_key = auth_client.post(
        "/api/v1/auth/login", json={"username": "owner", "password": private, private: private}
    )
    for response in (malformed, extra_key):
        assert response.status_code == 422
        assert response.json() == {"detail": "Invalid request"}
        assert private not in response.text


def test_session_is_readable_by_a_new_client_instance(
    authenticated: tuple[TestClient, str],
) -> None:
    client, _ = authenticated
    raw = client.cookies[SESSION_COOKIE]
    with TestClient(client.app, base_url=ORIGIN) as second:
        response = second.get("/api/v1/auth/me", headers={"Cookie": f"{SESSION_COOKIE}={raw}"})
    assert response.status_code == 200


def test_logout_requires_matching_csrf_and_origin_then_revokes_session(
    authenticated: tuple[TestClient, str], db_session: Session
) -> None:
    client, csrf = authenticated
    raw = client.cookies[SESSION_COOKIE]
    for headers in (
        {},
        {"X-CSRF-Token": "invalid"},
        {"X-CSRF-Token": csrf, "Origin": "https://evil.example"},
    ):
        assert client.post("/api/v1/auth/logout", headers=headers).status_code == 403
    response = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 204 and not response.content
    assert "Max-Age=0" in response.headers["set-cookie"]
    record = db_session.get(AuthSession, token_digest(raw))
    assert record is not None and record.revoked_at is not None
    assert (
        client.get("/api/v1/auth/me", headers={"Cookie": f"{SESSION_COOKIE}={raw}"}).status_code
        == 401
    )


def test_expired_and_unknown_sessions_are_rejected(
    authenticated: tuple[TestClient, str], db_session: Session
) -> None:
    client, _ = authenticated
    raw = client.cookies[SESSION_COOKIE]
    db_session.execute(
        update(AuthSession)
        .where(AuthSession.token_hash == token_digest(raw))
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    db_session.commit()
    assert client.get("/api/v1/auth/me").status_code == 401
    assert (
        client.get("/api/v1/auth/me", headers={"Cookie": f"{SESSION_COOKIE}=invalid"}).status_code
        == 401
    )


def test_reauthentication_rotates_and_revokes_the_previous_cookie(
    authenticated: tuple[TestClient, str], owner: User
) -> None:
    client, _ = authenticated
    previous = client.cookies[SESSION_COOKIE]
    response = client.post(
        "/api/v1/auth/login", json={"username": owner.username, "password": OWNER_PASSWORD}
    )
    assert response.status_code == 200
    assert client.cookies[SESSION_COOKIE] != previous
    assert (
        client.get(
            "/api/v1/auth/me", headers={"Cookie": f"{SESSION_COOKIE}={previous}"}
        ).status_code
        == 401
    )
