import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from life_archive.auth.models import User
from life_archive.auth.service import create_owner

OWNER_PASSWORD = "test-only-owner-passphrase"
ORIGIN = "http://127.0.0.1:8080"


@pytest.fixture
def owner(db_session: Session) -> User:
    return create_owner(db_session, "owner", OWNER_PASSWORD, "Asia/Shanghai")


@pytest.fixture
def auth_client(db_client: TestClient) -> TestClient:
    db_client.headers.update({"Origin": ORIGIN, "X-LifeArchive-Request": "1"})
    return db_client


@pytest.fixture
def authenticated(auth_client: TestClient, owner: User) -> tuple[TestClient, str]:
    response = auth_client.post(
        "/api/v1/auth/login", json={"username": owner.username, "password": OWNER_PASSWORD}
    )
    assert response.status_code == 200
    return auth_client, response.json()["csrf_token"]
