"""Focused pin state, keyset compatibility and revision concurrency checks."""

import base64
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from life_archive.auth.dependencies import require_csrf, require_user
from life_archive.auth.models import User
from life_archive.db import Base
from life_archive.journal.models import Entry, EntryRevision
from life_archive.journal.schemas import EntryCreate, EntryUpdate
from life_archive.journal.service import create_entry, edit_entry


def create(client: TestClient, day: str = "2000-02-29", **fields: object) -> dict:
    response = client.post(
        "/api/v1/entries",
        json={"content_md": "  # 原文\r\n末尾空格  \n", "entry_date": day, **fields},
    )
    assert response.status_code == 201
    return response.json()


def test_pin_snapshot_replay_restore_and_migration(
    journal_client: TestClient, pg_engine: Engine
) -> None:
    tag = journal_client.post("/api/v1/tags", json={"name": "保留标签"}).json()
    request_id = str(uuid4())
    original = create(journal_client, client_request_id=request_id, tag_ids=[tag["id"]])
    assert original["is_pinned"] is False
    path = "/api/v1/entries/" + original["id"]
    pinned = journal_client.patch(path, json={"expected_revision": 1, "is_pinned": True})
    assert pinned.status_code == 200 and pinned.json()["revision"] == 2
    assert pinned.json()["is_pinned"] is True
    for field in ("id", "content_md", "entry_date", "created_at", "tags", "assets"):
        assert pinned.json()[field] == original[field]
    replay_body = {
        "content_md": original["content_md"],
        "entry_date": original["entry_date"],
        "tag_ids": [tag["id"]],
        "client_request_id": request_id,
    }
    replay = journal_client.post("/api/v1/entries", json=replay_body)
    assert replay.status_code == 200 and replay.json() == pinned.json()
    assert (
        journal_client.post("/api/v1/entries", json={**replay_body, "is_pinned": True}).status_code
        == 409
    )
    assert journal_client.delete(path, params={"expected_revision": 2}).status_code == 204
    assert journal_client.get("/api/v1/trash").json()["items"][0]["is_pinned"] is True
    restored = journal_client.post(path + "/restore", json={"expected_revision": 3})
    assert restored.status_code == 200 and restored.json()["is_pinned"] is True
    history = journal_client.get(path + "/revisions").json()["items"]
    assert [row["is_pinned"] for row in history] == [True, True, True, False]
    assert (
        journal_client.patch(path, json={"expected_revision": 4, "is_pinned": False}).json()[
            "is_pinned"
        ]
        is False
    )
    with pg_engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


def test_pinned_pagination_filters_and_legacy_date_cursor(journal_client: TestClient) -> None:
    tag = journal_client.post("/api/v1/tags", json={"name": "分页"}).json()
    entries = [
        create(journal_client, day, is_pinned=pin, tag_ids=[tag["id"]])
        for day, pin in (
            ("1998-01-01", True),
            ("2000-02-29", False),
            ("1999-01-01", True),
            ("2000-02-29", False),
        )
    ]
    expected = sorted(
        entries,
        key=lambda row: (row["is_pinned"], row["entry_date"], row["created_at"], row["id"]),
        reverse=True,
    )
    filters = {"order": "pinned", "limit": 1, "tag_id": tag["id"]}
    page = journal_client.get("/api/v1/entries", params=filters).json()
    pinned_cursor = page["next_cursor"]
    actual = list(page["items"])
    while page["next_cursor"]:
        page = journal_client.get(
            "/api/v1/entries", params={**filters, "cursor": page["next_cursor"]}
        ).json()
        actual.extend(page["items"])
    assert actual == expected
    assert (
        journal_client.get(
            "/api/v1/entries", params={**filters, "order": "date", "cursor": pinned_cursor}
        ).status_code
        == 422
    )
    for changed in ({"tag_id": str(uuid4())}, {"entry_date": "1998-01-01"}):
        assert (
            journal_client.get(
                "/api/v1/entries", params={**filters, **changed, "cursor": pinned_cursor}
            ).status_code
            == 422
        )
    date_page = journal_client.get("/api/v1/entries", params={"limit": 1}).json()
    cursor = date_page["next_cursor"]
    position = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    position.pop("filter_order")
    position.pop("is_pinned")
    legacy = base64.urlsafe_b64encode(json.dumps(position).encode()).decode().rstrip("=")
    rest = journal_client.get("/api/v1/entries", params={"cursor": legacy}).json()["items"]
    expected_date = sorted(
        entries, key=lambda row: (row["entry_date"], row["created_at"], row["id"]), reverse=True
    )
    assert date_page["items"] + rest == expected_date
    assert (
        journal_client.get(
            "/api/v1/entries", params={"order": "pinned", "cursor": legacy}
        ).status_code
        == 422
    )
    # Day detail retains chronological order even when matching entries have pins.
    day = journal_client.get("/api/v1/days/2000-02-29").json()["entries"]["items"]
    assert day == [row for row in expected_date if row["entry_date"] == "2000-02-29"]


def test_pin_strict_inputs_and_owner_scope(journal_client: TestClient) -> None:
    entry = create(journal_client, is_pinned=True)
    path = "/api/v1/entries/" + entry["id"]
    for value in (None, 0, 1, "true", "false"):
        assert (
            journal_client.patch(
                path, json={"expected_revision": 1, "is_pinned": value}
            ).status_code
            == 422
        )
        assert (
            journal_client.post(
                "/api/v1/entries",
                json={"content_md": "原文", "entry_date": "2000-01-01", "is_pinned": value},
            ).status_code
            == 422
        )
    assert journal_client.get("/api/v1/entries?order=unknown").status_code == 422
    stranger = SimpleNamespace(id=uuid4())
    journal_client.app.dependency_overrides[require_user] = lambda: stranger
    journal_client.app.dependency_overrides[require_csrf] = lambda: stranger
    assert journal_client.get("/api/v1/entries?order=pinned").json()["items"] == []
    assert (
        journal_client.patch(path, json={"expected_revision": 1, "is_pinned": False}).status_code
        == 404
    )


def test_concurrent_pin_cas_has_one_winner(
    session_factory: sessionmaker[Session], journal_owner: User
) -> None:
    owner_id = journal_owner.id
    with session_factory() as db:
        entry, _ = create_entry(
            db, owner_id, EntryCreate(content_md="并发", entry_date="2000-01-01")
        )
        entry_id = entry.id
    barrier = Barrier(2)

    def pin(value: bool) -> int:
        with session_factory() as db:
            barrier.wait(timeout=10)
            try:
                edit_entry(
                    db, owner_id, entry_id, EntryUpdate(expected_revision=1, is_pinned=value)
                )
            except HTTPException as error:
                assert error.detail["code"] == "revision_conflict"
                return error.status_code
            return 200

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(pin, (True, False))) == [200, 409]
    with session_factory() as db:
        entry = db.get(Entry, entry_id)
        assert entry.revision == 2
        history = db.scalar(
            select(EntryRevision).where(
                EntryRevision.entry_id == entry_id, EntryRevision.revision == 2
            )
        )
        assert history.is_pinned == entry.is_pinned
        assert (
            db.scalar(
                select(func.count())
                .select_from(EntryRevision)
                .where(EntryRevision.entry_id == entry_id)
            )
            == 2
        )
