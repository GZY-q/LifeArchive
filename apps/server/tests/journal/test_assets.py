"""Five focused PG cases for private originals and atomic journal associations."""

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from uuid import UUID, uuid4

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from life_archive.auth.dependencies import require_csrf, require_user
from life_archive.auth.models import User
from life_archive.db import Base
from life_archive.main import create_app
from life_archive.media.models import Asset
from life_archive.media.service import create_asset
from life_archive.settings import get_media_settings


def picture(format: str = "PNG", *, size: tuple[int, int] = (2, 3), color: str = "red") -> bytes:
    stream = BytesIO()
    Image.new("RGB", size, color).save(stream, format=format)
    return stream.getvalue()


def upload(client: TestClient, data: bytes, mime: str = "image/png"):
    return client.post(
        "/api/v1/assets",
        content=data,
        headers={"Content-Type": mime, "X-LifeArchive-Request": "1"},
    )


def test_originals_are_private_verbatim_deduplicated_and_migration_matches(
    journal_client: TestClient, pg_engine: Engine, db_session: Session
) -> None:
    for format, mime in (("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")):
        raw = picture(format)
        response = upload(journal_client, raw, mime)
        assert response.status_code == 201
        asset = response.json()
        assert set(asset) == {
            "id",
            "mime_type",
            "byte_size",
            "sha256",
            "width",
            "height",
            "created_at",
        }
        assert asset["sha256"] == hashlib.sha256(raw).hexdigest()
        assert (asset["byte_size"], asset["width"], asset["height"]) == (len(raw), 2, 3)
        duplicate = upload(journal_client, raw, mime)
        assert duplicate.status_code == 200 and duplicate.json() == asset
        original = journal_client.get("/api/v1/assets/" + asset["id"])
        assert original.status_code == 200 and original.content == raw
        assert original.headers["content-type"] == mime
        assert original.headers["x-content-type-options"] == "nosniff"
        assert original.headers["cache-control"] == "no-store"
        stored = db_session.get(Asset, UUID(asset["id"]))
        assert (
            get_media_settings().media_root / stored.storage_key
        ).stat().st_mode & 0o777 == 0o600
    with TestClient(create_app()) as anonymous:
        assert anonymous.get("/api/v1/assets/" + asset["id"]).status_code == 401
        assert upload(anonymous, raw, mime).status_code == 401
    stranger = SimpleNamespace(id=uuid4())
    journal_client.app.dependency_overrides[require_user] = lambda: stranger
    journal_client.app.dependency_overrides[require_csrf] = lambda: stranger
    assert journal_client.get("/api/v1/assets/" + asset["id"]).status_code == 404
    with pg_engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


def test_upload_bounds_mime_decoding_and_animation_are_rejected(journal_client: TestClient) -> None:
    png = picture()
    assert upload(journal_client, png, "image/jpeg").status_code == 422
    assert upload(journal_client, b"<svg></svg>", "image/svg+xml").status_code == 422
    assert upload(journal_client, b"<html>not an image</html>").status_code == 422
    assert upload(journal_client, picture("JPEG")[:200], "image/jpeg").status_code == 422
    assert upload(journal_client, png[:-10]).status_code == 422
    assert upload(journal_client, b"").status_code == 422
    assert upload(journal_client, picture(size=(20_001, 1))).status_code == 422
    assert upload(journal_client, picture(size=(5000, 5000))).status_code == 422
    animation = BytesIO()
    Image.new("RGB", (2, 2), "red").save(
        animation,
        format="PNG",
        save_all=True,
        append_images=[Image.new("RGB", (2, 2), "blue")],
        duration=100,
        loop=0,
    )
    assert upload(journal_client, animation.getvalue()).status_code == 422
    response = journal_client.post(
        "/api/v1/assets",
        content=(b"x" * 1024 * 1024 for _ in range(6)),
        headers={"Content-Type": "image/png", "Content-Length": "1", "X-LifeArchive-Request": "1"},
    )
    assert response.status_code == 413
    assert (
        journal_client.post(
            "/api/v1/assets", content=png, headers={"Content-Type": "image/png"}
        ).status_code
        == 403
    )


def test_owner_lock_serializes_deduplication_and_quota(
    journal_client: TestClient,
    journal_owner: User,
    session_factory: sessionmaker[Session],
    db_session: Session,
    monkeypatch,
) -> None:
    raw = picture()
    monkeypatch.setenv("LIFEARCHIVE_MEDIA_QUOTA_BYTES", str(len(raw)))
    get_media_settings.cache_clear()
    barrier = Barrier(2)
    owner_id = journal_owner.id

    def send(_: int) -> tuple[UUID, bool]:
        with session_factory() as session:
            barrier.wait(timeout=10)
            asset, created = create_asset(session, owner_id, raw, "image/png")
            return asset.id, created

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(send, range(2)))
    assert results[0][0] == results[1][0] and sorted(row[1] for row in results) == [False, True]
    assert upload(journal_client, raw).status_code == 200
    assert upload(journal_client, picture(color="blue")).status_code == 413
    assert db_session.scalar(select(func.count()).select_from(Asset)) == 1
    assert len(list(get_media_settings().media_root.iterdir())) == 1


def test_assets_follow_journal_cas_history_replay_and_restore(journal_client: TestClient) -> None:
    first, second = [
        upload(journal_client, picture(color=color)).json() for color in ("red", "blue")
    ]
    request = {
        "content_md": "  原文不插入图片\r\n",
        "entry_date": "2000-02-29",
        "client_request_id": str(uuid4()),
        "asset_ids": [first["id"]],
    }
    created = journal_client.post("/api/v1/entries", json=request)
    assert created.status_code == 201 and created.json()["assets"] == [first]
    path = "/api/v1/entries/" + created.json()["id"]
    cleared = journal_client.patch(path, json={"expected_revision": 1, "asset_ids": []})
    assert cleared.status_code == 200 and cleared.json()["assets"] == []
    replay = journal_client.post("/api/v1/entries", json=request)
    assert replay.status_code == 200 and replay.json() == cleared.json()
    assert (
        journal_client.post(
            "/api/v1/entries", json={**request, "asset_ids": [second["id"]]}
        ).status_code
        == 409
    )
    current = journal_client.patch(path, json={"expected_revision": 2, "asset_ids": [second["id"]]})
    assert current.status_code == 200 and current.json()["assets"] == [second]
    assert (
        journal_client.patch(path, json={"expected_revision": 2, "asset_ids": []}).status_code
        == 409
    )
    for ids in (
        None,
        [first["id"], first["id"]],
        [str(uuid4())],
        [str(uuid4()) for _ in range(11)],
    ):
        assert (
            journal_client.patch(
                path, json={"expected_revision": 3, "asset_ids": ids, "content_md": "不得局部保存"}
            ).status_code
            == 422
        )
    assert journal_client.get(path).json() == current.json()
    assert journal_client.delete(path, params={"expected_revision": 3}).status_code == 204
    assert journal_client.get("/api/v1/trash").json()["items"][0]["assets"] == [second]
    restored = journal_client.post(path + "/restore", json={"expected_revision": 4})
    assert restored.status_code == 200 and restored.json()["assets"] == [second]
    history = journal_client.get(path + "/revisions").json()["items"]
    assert [revision["assets"] for revision in history] == [
        [second],
        [second],
        [second],
        [],
        [first],
    ]
    assert all(revision["content_md"] == request["content_md"] for revision in history)
    assert journal_client.get("/api/v1/assets/" + first["id"]).status_code == 200


def test_missing_corrupt_and_symlink_originals_fail_without_overwrite(
    journal_client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    raw = picture()
    asset = upload(journal_client, raw).json()
    record = db_session.get(Asset, UUID(asset["id"]))
    path = get_media_settings().media_root / record.storage_key
    path.write_bytes(b"x" * len(raw))
    assert journal_client.get("/api/v1/assets/" + asset["id"]).status_code == 503
    assert upload(journal_client, raw).status_code == 503
    assert path.read_bytes() == b"x" * len(raw)
    path.rename(tmp_path / "retained-corrupt-original")
    assert journal_client.get("/api/v1/assets/" + asset["id"]).status_code == 503
    target = tmp_path / "outside-original"
    target.write_bytes(raw)
    os.symlink(target, path)
    response = journal_client.get("/api/v1/assets/" + asset["id"])
    assert response.status_code == 503 and str(tmp_path) not in response.text
    assert target.read_bytes() == raw
