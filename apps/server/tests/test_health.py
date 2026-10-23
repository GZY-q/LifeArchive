import pytest
from fastapi.testclient import TestClient


def test_health_is_non_sensitive_and_does_not_need_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from life_archive.main import create_app

    monkeypatch.setenv("POSTGRES_PASSWORD", "invalid")
    monkeypatch.setenv("POSTGRES_HOST", "not-a-database.invalid")
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json", "/api/v1/entries"])
def test_only_m0_health_is_exposed(path: str) -> None:
    from life_archive.main import create_app

    with TestClient(create_app()) as client:
        assert client.get(path).status_code == 404
