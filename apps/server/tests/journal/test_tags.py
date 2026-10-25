from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from life_archive.auth.dependencies import require_csrf, require_user
from life_archive.auth.models import User
from life_archive.journal import service, tags
from life_archive.journal.models import EntryRevision
from life_archive.journal.schemas import EntryCreate, EntryUpdate, TagCreate


def make_tag(client: TestClient, name: str) -> dict:
    response = client.post("/api/v1/tags", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def test_catalog_normalization_pagination_and_validation(journal_client: TestClient) -> None:
    first = make_tag(journal_client, "  Ｔravel  ")
    duplicate = journal_client.post("/api/v1/tags", json={"name": "travel"})
    assert duplicate.status_code == 200 and duplicate.json() == first
    make_tag(journal_client, "家庭")
    page = journal_client.get("/api/v1/tags", params={"limit": 1}).json()
    rest = journal_client.get(
        "/api/v1/tags", params={"limit": 1, "cursor": page["next_cursor"]}
    ).json()
    assert len(page["items"]) == len(rest["items"]) == 1
    assert page["items"][0]["id"] != rest["items"][0]["id"]
    assert rest["next_cursor"] is None
    for name in (" ", "a\nb", "\x00", "界" * 41):
        assert journal_client.post("/api/v1/tags", json={"name": name}).status_code == 422
    payload = {"content_md": "原文", "entry_date": "2000-01-01"}
    for tag_ids in (None, [first["id"], first["id"]], [str(uuid4())]):
        response = journal_client.post("/api/v1/entries", json=payload | {"tag_ids": tag_ids})
        assert response.status_code == 422
    assert journal_client.get("/api/v1/entries").json()["items"] == []


def test_atomic_tag_edits_history_and_original_request_replay(journal_client: TestClient) -> None:
    first, second = make_tag(journal_client, "家庭"), make_tag(journal_client, "旅程")
    payload = {
        "content_md": "  # 原文\r\n",
        "entry_date": "2000-01-01",
        "client_request_id": str(uuid4()),
        "tag_ids": [first["id"], second["id"]],
    }
    created = journal_client.post("/api/v1/entries", json=payload)
    assert created.status_code == 201
    path = "/api/v1/entries/" + created.json()["id"]
    edited = journal_client.patch(path, json={"expected_revision": 1, "tag_ids": []})
    assert edited.status_code == 200
    assert edited.json()["revision"] == 2 and edited.json()["tags"] == []
    assert edited.json()["content_md"] == payload["content_md"]
    invalid = journal_client.patch(
        path, json={"expected_revision": 2, "content_md": "不应保存", "tag_ids": [str(uuid4())]}
    )
    assert invalid.status_code == 422
    assert journal_client.get(path).json() == edited.json()
    replay = journal_client.post(
        "/api/v1/entries", json=payload | {"tag_ids": list(reversed(payload["tag_ids"]))}
    )
    assert replay.status_code == 200 and replay.json() == edited.json()
    assert journal_client.post("/api/v1/entries", json=payload | {"tag_ids": []}).status_code == 409
    history = journal_client.get(path + "/revisions").json()["items"]
    assert history[0]["tags"] == []
    assert [tag["id"] for tag in history[1]["tags"]] == sorted(payload["tag_ids"])


def test_filter_cursor_and_owner_isolation(journal_client: TestClient) -> None:
    tag = make_tag(journal_client, "私密")
    for _ in range(3):
        assert (
            journal_client.post(
                "/api/v1/entries",
                json={"content_md": "记录", "entry_date": "2000-01-01", "tag_ids": [tag["id"]]},
            ).status_code
            == 201
        )
    page = journal_client.get(
        "/api/v1/entries", params={"tag_id": tag["id"], "entry_date": "2000-01-01", "limit": 1}
    ).json()
    assert len(page["items"]) == 1 and page["next_cursor"] is not None
    assert (
        journal_client.get(
            "/api/v1/entries",
            params={"entry_date": "2000-01-01", "cursor": page["next_cursor"]},
        ).status_code
        == 422
    )
    assert (
        journal_client.get(
            "/api/v1/entries", params={"tag_id": tag["id"], "entry_date": "2001-01-01"}
        ).json()["items"]
        == []
    )
    stranger = SimpleNamespace(id=uuid4())
    journal_client.app.dependency_overrides[require_user] = lambda: stranger
    journal_client.app.dependency_overrides[require_csrf] = lambda: stranger
    assert journal_client.get("/api/v1/tags").json()["items"] == []
    assert journal_client.get("/api/v1/entries", params={"tag_id": tag["id"]}).json()["items"] == []
    assert (
        journal_client.post(
            "/api/v1/entries",
            json={"content_md": "越权", "entry_date": "2000-01-01", "tag_ids": [tag["id"]]},
        ).status_code
        == 422
    )


def test_concurrent_tag_edits_cannot_change_losing_request_associations(
    session_factory: sessionmaker[Session], journal_owner: User
) -> None:
    owner_id = journal_owner.id
    with session_factory() as session:
        tag_ids = [
            tags.create_tag(session, owner_id, TagCreate(name=name))[0].id
            for name in ("标签 A", "标签 B")
        ]
        entry, _ = service.create_entry(
            session, owner_id, EntryCreate(content_md="原文", entry_date=date(2000, 1, 1))
        )
        entry_id = entry.id
    barrier = Barrier(2)

    def edit(tag_id: UUID) -> tuple[int, UUID]:
        with session_factory() as session:
            barrier.wait(timeout=10)
            try:
                service.edit_entry(
                    session, owner_id, entry_id, EntryUpdate(expected_revision=1, tag_ids=[tag_id])
                )
            except HTTPException as error:
                assert error.detail["code"] == "revision_conflict"
                return error.status_code, tag_id
            return 200, tag_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(edit, tag_ids))
    assert sorted(status for status, _ in results) == [200, 409]
    winning_tag = next(tag_id for status, tag_id in results if status == 200)
    with session_factory() as session:
        current = service.get_entry(session, owner_id, entry_id)
        assert current.revision == 2 and [tag.id for tag in current.tags] == [winning_tag]
        revision = session.scalar(
            select(EntryRevision).where(
                EntryRevision.entry_id == entry_id, EntryRevision.revision == 2
            )
        )
        assert revision is not None and [tag["id"] for tag in revision.tags] == [str(winning_tag)]
