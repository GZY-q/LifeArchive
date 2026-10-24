from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from life_archive.auth.dependencies import require_csrf, require_user
from life_archive.journal import service
from life_archive.journal.models import Entry, EntryRevision

MARKDOWN = "  # 原始日记\n\n中文与 **Markdown**\r\n- [ ] 记住这一天\n\n```text\n<原文>\n```\n  "


def create(client: TestClient, **changes: object) -> dict:
    response = client.post(
        "/api/v1/entries", json={"content_md": MARKDOWN, "entry_date": "2001-01-02", **changes}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_markdown_roundtrip_and_local_day(journal_client: TestClient) -> None:
    entry = create(journal_client)
    assert entry["content_md"] == MARKDOWN
    assert entry["entry_date"] == "2001-01-02"
    assert entry["revision"] == 1
    assert entry["occurred_at"] is None
    assert entry["occurred_timezone"] is None
    assert datetime.fromisoformat(entry["created_at"]).utcoffset().total_seconds() == 0
    assert datetime.fromisoformat(entry["updated_at"]).utcoffset().total_seconds() == 0
    assert journal_client.get(f"/api/v1/entries/{entry['id']}").json() == entry
    history = journal_client.get(f"/api/v1/entries/{entry['id']}/revisions").json()
    assert history["next_cursor"] is None
    assert history["items"][0]["content_md"] == MARKDOWN
    assert history["items"][0]["entry_date"] == "2001-01-02"
    assert history["items"][0]["revision"] == 1


def test_edit_preserves_snapshots_and_rejects_stale_version(journal_client: TestClient) -> None:
    entry = create(journal_client)
    path = f"/api/v1/entries/{entry['id']}"
    response = journal_client.patch(
        path,
        json={"expected_revision": 1, "content_md": "第二版\n", "entry_date": "1999-12-31"},
    )
    assert response.status_code == 200
    assert response.json()["revision"] == 2
    assert response.json()["created_at"] == entry["created_at"]
    stale = journal_client.patch(path, json={"expected_revision": 1, "content_md": "覆盖"})
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "revision_conflict"
    current = journal_client.get(path).json()
    assert current["content_md"] == "第二版\n"
    assert current["entry_date"] == "1999-12-31"
    history = journal_client.get(path + "/revisions").json()["items"]
    assert [item["revision"] for item in history] == [2, 1]
    assert [item["content_md"] for item in history] == ["第二版\n", MARKDOWN]
    assert [item["entry_date"] for item in history] == ["1999-12-31", "2001-01-02"]


def test_request_retry_uses_original_payload_after_edit(journal_client: TestClient) -> None:
    key = str(uuid4())
    entry = create(journal_client, client_request_id=key)
    path = f"/api/v1/entries/{entry['id']}"
    journal_client.patch(path, json={"expected_revision": 1, "content_md": "编辑后"})
    payload = {"content_md": MARKDOWN, "entry_date": "2001-01-02", "client_request_id": key}
    repeated = journal_client.post("/api/v1/entries", json=payload)
    assert repeated.status_code == 200
    assert repeated.json()["id"] == entry["id"]
    assert repeated.json()["content_md"] == "编辑后"
    for difference in ({"content_md": "不同内容"}, {"entry_date": "2000-01-01"}):
        conflict = journal_client.post("/api/v1/entries", json=payload | difference)
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["code"] == "idempotency_conflict"
    assert len(journal_client.get("/api/v1/entries").json()["items"]) == 1


def test_date_only_edit_keeps_markdown_verbatim(journal_client: TestClient) -> None:
    entry = create(journal_client)
    response = journal_client.patch(
        f"/api/v1/entries/{entry['id']}",
        json={"expected_revision": 1, "entry_date": "1990-05-01"},
    )
    assert response.status_code == 200
    assert response.json()["content_md"] == MARKDOWN
    assert response.json()["entry_date"] == "1990-05-01"
    assert response.json()["revision"] == 2


def test_creation_rejects_unassigned_fields_and_accepts_content_limit(
    journal_client: TestClient,
) -> None:
    rejected = journal_client.post(
        "/api/v1/entries",
        json={"content_md": "越权字段", "entry_date": "2000-01-01", "user_id": str(uuid4())},
    )
    assert rejected.status_code == 422
    assert create(journal_client, content_md="界" * 100_000)["content_md"] == "界" * 100_000


def test_delete_is_versioned_and_preserves_history_without_resurrection(
    journal_client: TestClient, db_session: Session
) -> None:
    key = str(uuid4())
    entry = create(journal_client, client_request_id=key)
    path = f"/api/v1/entries/{entry['id']}"
    assert journal_client.delete(path, params={"expected_revision": 9}).status_code == 409
    assert journal_client.delete(path, params={"expected_revision": 1}).status_code == 204
    assert journal_client.get(path).status_code == 404
    assert journal_client.get(path + "/revisions").status_code == 404
    assert (
        journal_client.patch(path, json={"expected_revision": 2, "content_md": "复活"}).status_code
        == 404
    )
    assert journal_client.delete(path, params={"expected_revision": 2}).status_code == 404
    assert journal_client.get("/api/v1/entries").json()["items"] == []
    replay = journal_client.post(
        "/api/v1/entries",
        json={"content_md": MARKDOWN, "entry_date": "2001-01-02", "client_request_id": key},
    )
    assert replay.status_code == 404
    stored = db_session.get(Entry, UUID(entry["id"]))
    assert stored is not None and stored.deleted_at is not None and stored.revision == 2
    history = db_session.scalars(
        select(EntryRevision).where(EntryRevision.entry_id == stored.id)
    ).all()
    assert len(history) == 2
    assert all(revision.content_md == MARKDOWN for revision in history)


def test_every_operation_rejects_a_different_owner(journal_client: TestClient) -> None:
    entry = create(journal_client)
    path = f"/api/v1/entries/{entry['id']}"
    stranger = SimpleNamespace(id=uuid4())
    journal_client.app.dependency_overrides[require_user] = lambda: stranger
    journal_client.app.dependency_overrides[require_csrf] = lambda: stranger
    assert journal_client.get("/api/v1/entries").json()["items"] == []
    assert journal_client.get(path).status_code == 404
    assert journal_client.get(path + "/revisions").status_code == 404
    assert (
        journal_client.patch(path, json={"expected_revision": 1, "content_md": "越权"}).status_code
        == 404
    )
    assert journal_client.delete(path, params={"expected_revision": 1}).status_code == 404


def test_all_journal_routes_require_authentication(db_client: TestClient) -> None:
    path = f"/api/v1/entries/{uuid4()}"
    responses = [
        db_client.get("/api/v1/entries"),
        db_client.get(path),
        db_client.get(path + "/revisions"),
        db_client.post("/api/v1/entries", json={"content_md": "私密", "entry_date": "2000-01-01"}),
        db_client.patch(path, json={"expected_revision": 1, "content_md": "私密"}),
        db_client.delete(path, params={"expected_revision": 1}),
    ]
    assert [response.status_code for response in responses] == [401] * 6


def test_keyset_pagination_breaks_ties_and_survives_new_entries(
    journal_client: TestClient, db_session: Session
) -> None:
    entries = [create(journal_client, content_md=f"第{i}篇") for i in range(5)]
    tied_time = datetime(2020, 1, 1, tzinfo=UTC)
    db_session.execute(update(Entry).values(created_at=tied_time))
    db_session.commit()
    expected = sorted([entry["id"] for entry in entries], reverse=True)
    first = journal_client.get("/api/v1/entries", params={"limit": 2}).json()
    create(journal_client, content_md="后来新增", entry_date="2002-01-01")
    ids = [item["id"] for item in first["items"]]
    cursor = first["next_cursor"]
    while cursor is not None:
        page = journal_client.get("/api/v1/entries", params={"limit": 2, "cursor": cursor}).json()
        ids.extend(item["id"] for item in page["items"])
        cursor = page["next_cursor"]
    assert ids == expected


def test_date_filter_and_cursor_validation(journal_client: TestClient) -> None:
    for day in ("1999-12-31", "2001-01-02", "2001-01-02"):
        create(journal_client, entry_date=day)
    page = journal_client.get(
        "/api/v1/entries", params={"entry_date": "2001-01-02", "limit": 1}
    ).json()
    assert len(page["items"]) == 1 and page["items"][0]["entry_date"] == "2001-01-02"
    assert (
        journal_client.get(
            "/api/v1/entries", params={"entry_date": "1999-12-31", "cursor": page["next_cursor"]}
        ).status_code
        == 422
    )
    assert (
        journal_client.get("/api/v1/entries", params={"cursor": "not-a-cursor!"}).status_code == 422
    )
    for limit in (0, 101):
        assert journal_client.get("/api/v1/entries", params={"limit": limit}).status_code == 422


def test_revision_pagination(journal_client: TestClient) -> None:
    entry = create(journal_client)
    path = f"/api/v1/entries/{entry['id']}"
    for revision in range(1, 4):
        assert (
            journal_client.patch(
                path, json={"expected_revision": revision, "content_md": f"版本{revision + 1}"}
            ).status_code
            == 200
        )
    page = journal_client.get(path + "/revisions", params={"limit": 2}).json()
    assert [item["revision"] for item in page["items"]] == [4, 3]
    older = journal_client.get(
        path + "/revisions", params={"limit": 2, "before_revision": page["next_cursor"]}
    ).json()
    assert [item["revision"] for item in older["items"]] == [2, 1]
    assert older["next_cursor"] is None


@pytest.mark.parametrize("content", ["", " \n\t", "x" * 100_001, "\x00"])
def test_invalid_content_rejected(journal_client: TestClient, content: str) -> None:
    response = journal_client.post(
        "/api/v1/entries", json={"content_md": content, "entry_date": "2000-01-01"}
    )
    assert response.status_code == 422
    assert journal_client.get("/api/v1/entries").json()["items"] == []


@pytest.mark.parametrize("day", [0, True, "2020-01-01T00:00:00Z", "not-a-date", "2025-02-29"])
def test_entry_date_must_be_a_calendar_date(journal_client: TestClient, day: object) -> None:
    assert (
        journal_client.post(
            "/api/v1/entries", json={"content_md": "不能按时间戳转换日期", "entry_date": day}
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"expected_revision": 1},
        {"expected_revision": 1, "content_md": None},
        {"expected_revision": 1, "entry_date": None},
        {"expected_revision": 1, "content_md": " \n"},
        {"expected_revision": 0, "content_md": "更新"},
        {"expected_revision": True, "content_md": "更新"},
        {"expected_revision": 1, "content_md": "更新", "user_id": str(uuid4())},
    ],
)
def test_invalid_edits_cannot_change_original(journal_client: TestClient, payload: dict) -> None:
    entry = create(journal_client)
    path = f"/api/v1/entries/{entry['id']}"
    assert journal_client.patch(path, json=payload).status_code == 422
    assert journal_client.get(path).json() == entry


def test_revision_failure_rolls_back_creation_and_edit(
    journal_client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = create(journal_client)
    path = f"/api/v1/entries/{entry['id']}"

    def fail_snapshot(*_args: object) -> None:
        raise RuntimeError("simulated snapshot failure")

    monkeypatch.setattr(service, "_snapshot", fail_snapshot)
    with pytest.raises(RuntimeError, match="simulated snapshot failure"):
        journal_client.post(
            "/api/v1/entries", json={"content_md": "不可留孤儿", "entry_date": "2000-01-01"}
        )
    with pytest.raises(RuntimeError, match="simulated snapshot failure"):
        journal_client.patch(path, json={"expected_revision": 1, "content_md": "不可丢失原文"})
    assert journal_client.get(path).json() == entry
    assert db_session.scalar(select(func.count()).select_from(Entry)) == 1
    assert db_session.scalar(select(func.count()).select_from(EntryRevision)) == 1
