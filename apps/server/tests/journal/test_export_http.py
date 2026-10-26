import hashlib
import io
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from uuid import uuid4
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from life_archive.auth.dependencies import require_csrf
from life_archive.auth.models import User
from life_archive.auth.security import SESSION_COOKIE, csrf_token
from life_archive.auth.service import create_session
from life_archive.db import Base
from life_archive.journal import export as exporter
from life_archive.journal import export_router as endpoint
from life_archive.media.service import create_asset
from life_archive.media.storage import MediaStorageError

HEADERS = {"Origin": "http://127.0.0.1:8080", "X-LifeArchive-Request": "1"}
RAW = "  # 原文 😀\r\n组合字 e\u0301  \n"


def rows(session: Session) -> dict:
    return {
        table.name: session.execute(select(table).order_by(*table.primary_key.columns)).all()
        for table in Base.metadata.sorted_tables
    }


@pytest.mark.parametrize("include_deleted", [False, True])
def test_http_archive_has_all_selected_history_and_originals_without_database_writes(
    journal_client: TestClient,
    db_session: Session,
    journal_owner: User,
    monkeypatch: pytest.MonkeyPatch,
    include_deleted: bool,
) -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(buffer, format="PNG")
    original = buffer.getvalue()
    asset, _ = create_asset(db_session, journal_owner.id, original, "image/png")
    tag = journal_client.post("/api/v1/tags", json={"name": "旧名称"}).json()
    payload = {"content_md": RAW, "entry_date": "2000-02-29", "client_request_id": str(uuid4())}
    entry = journal_client.post(
        "/api/v1/entries",
        json=payload | {"tag_ids": [tag["id"]], "asset_ids": [str(asset.id)], "is_pinned": True},
    ).json()
    path = f"/api/v1/entries/{entry['id']}"
    assert (
        journal_client.patch(
            f"/api/v1/tags/{tag['id']}",
            json={"name": "新名称", "expected_name": "旧名称"},
            headers=HEADERS,
        ).status_code
        == 200
    )
    assert (
        journal_client.patch(path, json={"expected_revision": 1, "asset_ids": []}).status_code
        == 200
    )
    deleted = journal_client.post(
        "/api/v1/entries", json=payload | {"client_request_id": str(uuid4())}
    ).json()
    assert (
        journal_client.delete(
            f"/api/v1/entries/{deleted['id']}", params={"expected_revision": 1}
        ).status_code
        == 204
    )
    snapshot = exporter._write_snapshot

    def check_snapshot(connection, archive, selected_deleted, **options):
        assert connection.exec_driver_sql("SHOW transaction_read_only").scalar_one() == "on"
        assert (
            connection.exec_driver_sql("SHOW transaction_isolation").scalar_one()
            == "repeatable read"
        )
        assert connection.exec_driver_sql("SHOW statement_timeout").scalar_one() == "3s"
        assert options["owner_id"] == journal_owner.id
        return snapshot(connection, archive, selected_deleted, **options)

    monkeypatch.setattr(exporter, "_write_snapshot", check_snapshot)
    before = rows(db_session)
    response = journal_client.post(
        "/api/v1/journal-export", json={"include_deleted": include_deleted}, headers=HEADERS
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["cache-control"] == "no-store"
    assert (
        response.headers["content-disposition"] == 'attachment; filename="life-archive-journal.zip"'
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert int(response.headers["content-length"]) == len(response.content)
    with ZipFile(io.BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["schema_version"] == 4 and manifest["owner"]["id"] == str(journal_owner.id)
        assert manifest["deleted_policy"] == (
            "include_deleted" if include_deleted else "active_only"
        )
        assert manifest["entry_count"] == (2 if include_deleted else 1)
        assert manifest["revision_count"] == (4 if include_deleted else 2)
        assert manifest["asset_count"] == 1
        assert archive.read(f"entries/{entry['id']}.md") == RAW.encode()
        current = json.loads(archive.read(f"entries/{entry['id']}.json"))
        assert current["assets"] == [] and current["is_pinned"] is True
        assert current["tags"][0]["name"] == "新名称"
        assert (
            json.loads(archive.read(f"revisions/{entry['id']}/1.json"))["tags"][0]["name"]
            == "旧名称"
        )
        assert archive.read(f"assets/{asset.id}.png") == original
        assert len(archive.namelist()) == len(manifest["files"]) + 1
        for item in manifest["files"]:
            content = archive.read(item["path"])
            assert len(content) == item["bytes"]
            assert hashlib.sha256(content).hexdigest() == item["sha256"]
        metadata = "".join(
            archive.read(name).decode() for name in archive.namelist() if name.endswith(".json")
        )
        assert "password_hash" not in metadata and "token_hash" not in metadata
    assert rows(db_session) == before


def test_http_export_requires_session_origin_json_csrf_and_strict_options(
    db_client: TestClient, db_session: Session, journal_owner: User
) -> None:
    path = "/api/v1/journal-export"
    assert db_client.post(path, json={}, headers=HEADERS).status_code == 401
    token, _ = create_session(db_session, journal_owner, None)
    db_client.cookies.set(SESSION_COOKIE, token)
    headers = HEADERS | {"X-CSRF-Token": csrf_token(token)}
    before = rows(db_session)
    for invalid, status in (
        ({"Origin": "https://evil.example"}, 403),
        ({"X-CSRF-Token": "invalid"}, 403),
        ({"X-LifeArchive-Request": "0"}, 403),
        ({"Content-Type": "text/plain"}, 415),
    ):
        response = db_client.post(path, json={}, headers=headers | invalid)
        assert response.status_code == status and response.headers["cache-control"] == "no-store"
    assert (
        db_client.post(path, json={}, headers={"X-CSRF-Token": csrf_token(token)}).status_code
        == 403
    )
    for body in (
        {"include_deleted": "false"},
        {"include_deleted": 1},
        {"include_deleted": None},
        {"owner": str(journal_owner.id)},
        {"path": "/private/value"},
    ):
        invalid = db_client.post(path, json=body, headers=headers)
        assert invalid.status_code == 422 and invalid.json() == {"detail": "Invalid request"}
    assert db_client.get(path).status_code == 405
    assert db_client.post(path, json={}, headers=headers).status_code == 200
    # An authenticated owner ID can never fall back to the database's singleton owner.
    db_client.app.dependency_overrides[require_csrf] = lambda: SimpleNamespace(id=uuid4())
    denied = db_client.post(path, json={}, headers=headers)
    assert denied.status_code == 503 and "content-disposition" not in denied.headers
    assert rows(db_session) == before


def test_count_limits_reject_instead_of_truncating_and_release_slot(
    journal_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal_client.post("/api/v1/tags", json={"name": "标签"})
    journal_client.post(
        "/api/v1/entries",
        json={"content_md": RAW, "entry_date": "2000-02-29", "client_request_id": str(uuid4())},
    )
    for limits in (
        exporter.ExportLimits(entries=0),
        exporter.ExportLimits(revisions=0),
        exporter.ExportLimits(tags=0),
    ):
        with monkeypatch.context() as patch:
            patch.setattr(endpoint, "LIMITS", limits)
            response = journal_client.post("/api/v1/journal-export", json={}, headers=HEADERS)
            assert (
                response.status_code == 413
                and response.json()["detail"]["code"] == "export_too_large"
            )
            assert "content-disposition" not in response.headers
    assert (
        journal_client.post("/api/v1/journal-export", json={}, headers=HEADERS).status_code == 200
    )


def test_size_deadline_sql_timeout_and_corrupt_media_fail_without_an_attachment(
    journal_client: TestClient,
    db_session: Session,
    journal_owner: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (1, 1), "blue").save(buffer, format="PNG")
    asset, _ = create_asset(db_session, journal_owner.id, buffer.getvalue(), "image/png")
    journal_client.post(
        "/api/v1/entries",
        json={
            "content_md": RAW,
            "entry_date": "2000-02-29",
            "client_request_id": str(uuid4()),
            "asset_ids": [str(asset.id)],
        },
    )

    def missing_original(*args, **kwargs):
        raise MediaStorageError("private original path must not escape")

    def sql_timeout(connection, *args, **kwargs):
        connection.exec_driver_sql("SET LOCAL statement_timeout = '10ms'")
        connection.exec_driver_sql("SELECT pg_sleep(0.05)")

    def corrupt(*args, **kwargs):
        raise exporter.ExportError("private source must not escape")

    before = rows(db_session)
    for target, name, value, status, code in (
        (endpoint, "MAX_ARCHIVE_BYTES", 10, 413, "export_too_large"),
        (endpoint, "EXPORT_SECONDS", -1, 504, "export_timeout"),
        (exporter, "_write_snapshot", sql_timeout, 504, "export_timeout"),
        (exporter, "read_original", missing_original, 503, "export_unavailable"),
        (exporter, "_verify_written_archive", corrupt, 503, "export_unavailable"),
    ):
        with monkeypatch.context() as patch:
            patch.setattr(target, name, value)
            response = journal_client.post("/api/v1/journal-export", json={}, headers=HEADERS)
            assert response.status_code == status and response.json() == {"detail": {"code": code}}
            assert "content-disposition" not in response.headers
            assert response.headers["cache-control"] == "no-store"
    assert rows(db_session) == before
    assert (
        journal_client.post("/api/v1/journal-export", json={}, headers=HEADERS).status_code == 200
    )


def test_overlapping_requests_are_rejected_and_slot_recovers(
    journal_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    started, release = Event(), Event()
    snapshot = exporter._write_snapshot

    def blocked(*args, **kwargs):
        started.set()
        assert release.wait(timeout=5)
        return snapshot(*args, **kwargs)

    monkeypatch.setattr(exporter, "_write_snapshot", blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(journal_client.post, "/api/v1/journal-export", json={}, headers=HEADERS)
        try:
            assert started.wait(timeout=5)
            busy = journal_client.post("/api/v1/journal-export", json={}, headers=HEADERS)
            assert busy.status_code == 429 and busy.json()["detail"]["code"] == "export_busy"
            assert busy.headers["retry-after"] == "5"
        finally:
            release.set()
        assert first.result(timeout=5).status_code == 200
    assert (
        journal_client.post("/api/v1/journal-export", json={}, headers=HEADERS).status_code == 200
    )
