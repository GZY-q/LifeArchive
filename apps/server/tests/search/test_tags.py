import base64
import hashlib
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from life_archive.auth.dependencies import require_user
from life_archive.journal.models import Entry, EntryRevision, EntryTag, Tag


def tag(client: TestClient, name: str) -> str:
    response = client.post("/api/v1/tags", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def create(client: TestClient, content: str, day: str, tags: list[str]) -> dict:
    response = client.post(
        "/api/v1/entries", json={"content_md": content, "entry_date": day, "tag_ids": tags}
    )
    assert response.status_code == 201
    return response.json()


def search(client: TestClient, **filters: object) -> dict:
    response = client.post("/api/v1/search", json=filters)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.request.url.query == b""
    return response.json()


def rows(session: Session) -> dict:
    return {
        model.__tablename__: session.execute(
            select(model.__table__).order_by(*model.__table__.primary_key.columns)
        ).all()
        for model in (Entry, EntryRevision, Tag, EntryTag)
    }


def test_tag_search_combines_filters_and_tracks_current_associations_read_only(
    search_client: TestClient, db_session: Session
) -> None:
    selected, other = tag(search_client, "旅行"), tag(search_client, "阅读")
    hit = create(search_client, "  # 北京 /%_  \r\n", "2000-02-29", [selected, other])
    earlier = create(search_client, "北京 /%_", "1999-12-31", [selected])
    create(search_client, "上海", "2000-02-29", [selected])
    create(search_client, "北京 /%_", "2000-02-29", [other])
    create(search_client, "北京 /%_", "2000-02-29", [])
    before = rows(db_session)
    page = search(search_client, tag_id=selected)
    assert len(page["items"]) == 3 and len({entry["id"] for entry in page["items"]}) == 3
    assert search(
        search_client,
        tag_id=selected,
        query=" /%_ ",
        date_from="2000-02-29",
        date_to="2000-02-29",
    )["items"] == [hit]
    assert rows(db_session) == before
    path = "/api/v1/entries/" + hit["id"]
    assert (
        search_client.patch(path, json={"expected_revision": 1, "tag_ids": []}).status_code == 200
    )
    assert search(search_client, tag_id=selected, query="/%_")["items"] == [earlier]
    assert (
        search_client.patch(path, json={"expected_revision": 2, "tag_ids": [selected]}).status_code
        == 200
    )
    assert search_client.delete(path, params={"expected_revision": 3}).status_code == 204
    assert search(search_client, tag_id=selected, query="/%_")["items"] == [earlier]
    restored = search_client.post(path + "/restore", json={"expected_revision": 4})
    assert restored.status_code == 200
    assert search(search_client, tag_id=selected, query="/%_")["items"] == [
        restored.json(),
        earlier,
    ]


def test_tag_search_cursor_binds_tags_and_preserves_legacy_digest(
    search_client: TestClient, db_session: Session
) -> None:
    selected, other = tag(search_client, "分页"), tag(search_client, "其他")
    entries = [
        create(search_client, "分页原文", day, [selected, other])
        for day in ("2000-02-29", "1999-12-31", "1998-01-01")
    ]
    first = search(search_client, query="分页", tag_id=selected, limit=1)
    cursor = first["next_cursor"]
    second = search(search_client, query=" 分页 ", tag_id=selected, cursor=cursor)
    assert first["items"] + second["items"] == entries
    assert second["next_cursor"] is None
    for changed in ({"tag_id": other}, {"tag_id": None}, {}):
        response = search_client.post(
            "/api/v1/search", json={"query": "分页", "cursor": cursor, **changed}
        )
        assert response.status_code == 422 and response.json() == {"detail": "Invalid request"}
    legacy = search(search_client, query="分页", limit=1)
    position = json.loads(
        base64.urlsafe_b64decode(legacy["next_cursor"] + "=" * (-len(legacy["next_cursor"]) % 4))
    )
    owner_id = db_session.scalar(select(Entry.user_id).where(Entry.id == UUID(entries[0]["id"])))
    old_filters = {"owner": str(owner_id), "query": "分页", "date_from": None, "date_to": None}
    old_digest = hashlib.sha256(
        json.dumps(old_filters, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert position["version"] == "search-v1" and position["filter_digest"] == old_digest
    assert (
        search(search_client, query="分页", tag_id=None, cursor=legacy["next_cursor"])["items"]
        == entries[1:]
    )
    assert (
        search_client.post(
            "/api/v1/search",
            json={"query": "分页", "tag_id": selected, "cursor": legacy["next_cursor"]},
        ).status_code
        == 422
    )
    stranger = SimpleNamespace(id=uuid4())
    search_client.app.dependency_overrides[require_user] = lambda: stranger
    try:
        assert (
            search_client.post(
                "/api/v1/search", json={"query": "分页", "tag_id": selected, "cursor": cursor}
            ).status_code
            == 422
        )
    finally:
        search_client.app.dependency_overrides.pop(require_user)


def test_unknown_or_other_owner_tag_is_empty_and_invalid_tag_is_generic(
    search_client: TestClient,
) -> None:
    selected = tag(search_client, "私密标签")
    create(search_client, "仅主人可读", "2000-02-29", [selected])
    assert search(search_client, tag_id=str(uuid4())) == {"items": [], "next_cursor": None}
    stranger = SimpleNamespace(id=uuid4())
    search_client.app.dependency_overrides[require_user] = lambda: stranger
    try:
        assert search(search_client, tag_id=selected) == {"items": [], "next_cursor": None}
    finally:
        search_client.app.dependency_overrides.pop(require_user)
    for payload in ({}, {"tag_id": None}, {"tag_id": "private-invalid-tag"}, {"tag_id": True}):
        response = search_client.post("/api/v1/search", json=payload)
        assert response.status_code == 422 and response.json() == {"detail": "Invalid request"}
        assert response.headers["cache-control"] == "no-store"
