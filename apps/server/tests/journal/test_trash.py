from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from life_archive.auth.dependencies import require_csrf, require_user
from life_archive.auth.models import User
from life_archive.journal.models import Entry, EntryRevision
from life_archive.journal.schemas import EntryCreate
from life_archive.journal.service import create_entry, delete_entry
from life_archive.journal.trash import restore_entry


def create(client: TestClient, **changes: object) -> dict:
    response = client.post(
        "/api/v1/entries",
        json={"content_md": "  # 恢复原文\r\n尾空格  \n", "entry_date": "2000-02-29"} | changes,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_restore_preserves_identity_tags_originals_and_history(journal_client: TestClient) -> None:
    tag = journal_client.post("/api/v1/tags", json={"name": "恢复标签"}).json()
    request_id = str(uuid4())
    original = create(journal_client, tag_ids=[tag["id"]], client_request_id=request_id)
    path = "/api/v1/entries/" + original["id"]
    assert journal_client.delete(path, params={"expected_revision": 1}).status_code == 204
    assert journal_client.get(path).status_code == 404
    assert journal_client.get(path + "/revisions").status_code == 404
    assert journal_client.get("/api/v1/entries").json()["items"] == []
    page = journal_client.get("/api/v1/trash")
    assert page.headers["cache-control"] == "no-store"
    deleted = page.json()["items"][0]
    assert deleted["revision"] == 2 and deleted["tags"] == original["tags"]
    assert deleted["content_md"] == original["content_md"]
    assert datetime.fromisoformat(deleted["deleted_at"]).utcoffset().total_seconds() == 0
    for body in ({}, {"expected_revision": True}, {"expected_revision": 2, "content_md": "禁改"}):
        assert journal_client.post(path + "/restore", json=body).status_code == 422
    response = journal_client.post(path + "/restore", json={"expected_revision": 2})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    restored = response.json()
    assert restored["revision"] == 3
    for field in (
        "id",
        "created_at",
        "entry_date",
        "content_md",
        "tags",
        "occurred_at",
        "occurred_timezone",
    ):
        assert restored[field] == original[field]
    assert journal_client.get("/api/v1/trash").json() == {"items": [], "next_cursor": None}
    assert journal_client.get("/api/v1/entries").json()["items"] == [restored]
    history = journal_client.get(path + "/revisions").json()["items"]
    assert [item["revision"] for item in history] == [3, 2, 1]
    assert all(item["tags"] == original["tags"] for item in history)
    assert journal_client.get("/api/v1/calendar?year=2000&month=2").json()["days"] == [
        {"date": "2000-02-29", "entry_count": 1}
    ]
    assert journal_client.get("/api/v1/days/2000-02-29").json()["entries"]["items"] == [restored]
    assert journal_client.post("/api/v1/search", json={"query": "恢复原文"}).json()["items"] == [
        restored
    ]
    assert journal_client.get("/api/v1/on-this-day?date=2024-02-29").json()["entries"]["items"] == [
        restored
    ]
    replay = journal_client.post(
        "/api/v1/entries",
        json={
            "content_md": original["content_md"],
            "entry_date": original["entry_date"],
            "tag_ids": [tag["id"]],
            "client_request_id": request_id,
        },
    )
    assert replay.status_code == 200 and replay.json() == restored


def test_trash_cursor_tie_breaker_scope_and_owner_isolation(
    journal_client: TestClient, db_session: Session
) -> None:
    ids = [create(journal_client)["id"] for _ in range(3)]
    active = create(journal_client)
    for entry_id in ids:
        assert (
            journal_client.delete(
                "/api/v1/entries/" + entry_id, params={"expected_revision": 1}
            ).status_code
            == 204
        )
    # Same deletion instant makes the UUID tie-breaker observable.
    db_session.execute(
        update(Entry)
        .where(Entry.id.in_([UUID(value) for value in ids]))
        .values(deleted_at=datetime(2026, 10, 26, tzinfo=UTC))
    )
    db_session.commit()
    page = journal_client.get("/api/v1/trash?limit=1").json()
    first_cursor = page["next_cursor"]
    actual = [page["items"][0]["id"]]
    while page["next_cursor"] is not None:
        page = journal_client.get(
            "/api/v1/trash", params={"limit": 1, "cursor": page["next_cursor"]}
        ).json()
        actual.extend(row["id"] for row in page["items"])
    assert actual == sorted(ids, reverse=True) and active["id"] not in actual
    assert journal_client.get("/api/v1/entries", params={"cursor": first_cursor}).status_code == 422
    assert journal_client.get("/api/v1/trash?cursor=invalid").status_code == 422
    stranger = SimpleNamespace(id=uuid4())
    journal_client.app.dependency_overrides[require_user] = lambda: stranger
    journal_client.app.dependency_overrides[require_csrf] = lambda: stranger
    assert journal_client.get("/api/v1/trash").json()["items"] == []
    assert journal_client.get("/api/v1/trash", params={"cursor": first_cursor}).status_code == 422
    assert (
        journal_client.post(
            "/api/v1/entries/" + ids[0] + "/restore", json={"expected_revision": 2}
        ).status_code
        == 404
    )


def test_stale_restore_cannot_resurrect_a_later_deletion(journal_client: TestClient) -> None:
    entry = create(journal_client)
    path = "/api/v1/entries/" + entry["id"]
    assert journal_client.delete(path, params={"expected_revision": 1}).status_code == 204
    assert journal_client.post(path + "/restore", json={"expected_revision": 1}).status_code == 409
    assert journal_client.post(path + "/restore", json={"expected_revision": 2}).status_code == 200
    active = journal_client.post(path + "/restore", json={"expected_revision": 2})
    assert active.status_code == 409 and active.json()["detail"]["code"] == "revision_conflict"
    assert journal_client.delete(path, params={"expected_revision": 3}).status_code == 204
    stale = journal_client.post(path + "/restore", json={"expected_revision": 2})
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "revision_conflict"
    assert journal_client.get(path).status_code == 404
    assert journal_client.get("/api/v1/trash").json()["items"][0]["revision"] == 4
    assert (
        journal_client.post(path + "/restore", json={"expected_revision": 4}).json()["revision"]
        == 5
    )
    assert (
        journal_client.post(
            "/api/v1/entries/" + str(uuid4()) + "/restore", json={"expected_revision": 2}
        ).status_code
        == 404
    )


def test_simultaneous_restores_create_only_one_revision(
    session_factory: sessionmaker[Session], journal_owner: User
) -> None:
    owner_id = journal_owner.id
    with session_factory() as db:
        entry, _ = create_entry(
            db, owner_id, EntryCreate(content_md="并发恢复", entry_date="2000-01-01")
        )
        entry_id = entry.id
        delete_entry(db, owner_id, entry_id, 1)
    barrier = Barrier(2)

    def restore(_: int) -> int:
        with session_factory() as db:
            barrier.wait(timeout=10)
            try:
                restore_entry(db, owner_id, entry_id, 2)
            except HTTPException as error:
                assert error.detail["code"] == "revision_conflict"
                return error.status_code
            return 200

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(restore, range(2))) == [200, 409]
    with session_factory() as db:
        current = db.get(Entry, entry_id)
        assert current is not None and current.revision == 3 and current.deleted_at is None
        assert (
            db.scalar(
                select(func.count())
                .select_from(EntryRevision)
                .where(EntryRevision.entry_id == entry_id)
            )
            == 3
        )
