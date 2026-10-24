import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from life_archive.auth.service import create_owner


@pytest.fixture
def timeline_client(db_client: TestClient, db_session: Session) -> TestClient:
    password = "test-only-timeline-passphrase"
    owner = create_owner(db_session, "timeline-owner", password, "Pacific/Kiritimati")
    db_client.headers.update({"Origin": "http://127.0.0.1:8080", "X-LifeArchive-Request": "1"})
    login = db_client.post(
        "/api/v1/auth/login", json={"username": owner.username, "password": password}
    )
    assert login.status_code == 200
    db_client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
    return db_client
