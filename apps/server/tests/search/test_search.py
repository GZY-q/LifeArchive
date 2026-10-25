import base64
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from life_archive.auth.dependencies import require_csrf, require_user
from life_archive.db import get_db_session
from life_archive.journal.models import Entry, EntryRevision
from life_archive.main import create_app
from life_archive.search.schemas import SearchRequest


def create(client: TestClient, content: str, day: str = "2000-02-29") -> dict:
    response = client.post("/api/v1/entries", json={"content_md": content, "entry_date": day})
    assert response.status_code == 201
    return response.json()


def search(client: TestClient, query: str = "", **filters: object) -> dict:
    response = client.post("/api/v1/search", json={"query": query, **filters})
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.request.url.query == b""
    result = response.json()
    assert set(result) == {"items", "next_cursor"}
    return result


def ids(page: dict) -> list[str]:
    return [entry["id"] for entry in page["items"]]


def encode_cursor(value: object) -> str:
    return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")


def decode_cursor(value: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))


def test_chinese_whole_phrase_case_insensitive_and_exact_markdown(
    search_client: TestClient,
) -> None:
    original = (
        "# 私密原文\n\n今天去北京，明天看海。 MixedCase\n  尾部空格  \n<script>text</script>\n"
    )
    entry = create(search_client, original)
    create(search_client, "今天去上海。Mixed separately Case")
    for query in ("  今天去北京  ", "mixedcase", "MIXEDCASE", "北京，明天", "<script>"):
        result = search(search_client, query)
        assert result == {"items": [entry], "next_cursor": None}
        assert result["items"][0]["content_md"] == original
    assert search(search_client, "北京 看海")["items"] == []


def test_like_metacharacters_and_injection_text_are_literal(search_client: TestClient) -> None:
    cases = [
        ("%", "完成 100%", "完成 1000"),
        ("_", "a_b", "axb"),
        ("/", "a/b", "ab"),
        ("\\", "a\\b", "ab"),
        ("/%_\\", "特殊 /%_\\ 字符", "特殊 /abcZ\\ 字符"),
        ("' OR 1=1 --", "正文 ' OR 1=1 --", "正文不含查询"),
    ]
    entries = [(query, create(search_client, hit)) for query, hit, _ in cases]
    all_entries = [entry for _, entry in entries]
    all_entries.extend(create(search_client, miss) for _, _, miss in cases)
    # A negative example for one query may contain a different query's literal.
    for query, hit in entries:
        result = search(search_client, query)
        expected = {entry["id"] for entry in all_entries if query in entry["content_md"]}
        assert set(ids(result)) == expected
        assert hit["id"] in expected
    assert search(search_client, "nonexistent' OR 1=1 --")["items"] == []


def test_inclusive_dates_use_entry_date_not_creation_or_timezone(
    search_client: TestClient, db_session: Session
) -> None:
    dates = ["0001-01-01", "1999-12-31", "2000-02-29", "2000-03-01", "9999-12-31"]
    entries = [create(search_client, "归档日期", day) for day in dates]
    db_session.execute(update(Entry).values(created_at=datetime(2026, 10, 25, 23, tzinfo=UTC)))
    db_session.commit()
    assert ids(search(search_client, "归档", date_from=dates[1], date_to=dates[2])) == [
        entries[2]["id"],
        entries[1]["id"],
    ]
    assert ids(search(search_client, date_from=dates[-1])) == [entries[-1]["id"]]
    assert ids(search(search_client, date_to=dates[0])) == [entries[0]["id"]]
    assert ids(search(search_client, "   ", date_from=dates[2], date_to=dates[2])) == [
        entries[2]["id"]
    ]
    assert search(search_client, date_from="2001-01-01", date_to="2001-12-31")["items"] == []


def test_search_tracks_edits_dates_and_soft_deletion_without_searching_revisions(
    search_client: TestClient,
) -> None:
    entry = create(search_client, "旧关键词")
    response = search_client.patch(
        f"/api/v1/entries/{entry['id']}",
        json={"expected_revision": 1, "content_md": "新关键词", "entry_date": "1999-12-31"},
    )
    assert response.status_code == 200
    assert search(search_client, "旧关键词")["items"] == []
    assert search(search_client, "新关键词")["items"] == [response.json()]
    assert search(search_client, "新关键词", date_from="2000-01-01")["items"] == []
    assert ids(search(search_client, date_to="1999-12-31")) == [entry["id"]]
    deletion = search_client.delete(f"/api/v1/entries/{entry['id']}?expected_revision=2")
    assert deletion.status_code == 204
    assert search(search_client, "新关键词")["items"] == []
    assert search(search_client, date_to="9999-12-31")["items"] == []


def test_owner_scope_and_cursor_owner_binding(search_client: TestClient) -> None:
    create(search_client, "属于日记主人")
    create(search_client, "属于日记主人")
    cursor = search(search_client, "主人", limit=1)["next_cursor"]
    stranger = SimpleNamespace(id=uuid4())
    search_client.app.dependency_overrides[require_user] = lambda: stranger
    try:
        assert search(search_client, "主人")["items"] == []
        assert search(search_client, date_to="9999-12-31")["items"] == []
        rejected = search_client.post("/api/v1/search", json={"query": "主人", "cursor": cursor})
        assert rejected.status_code == 422
        assert rejected.json() == {"detail": "Invalid request"}
    finally:
        search_client.app.dependency_overrides.pop(require_user)


def test_keyset_pagination_ties_and_newer_insert(
    search_client: TestClient, db_session: Session
) -> None:
    entries = [create(search_client, f"分页记录 {index}") for index in range(4)]
    older = create(search_client, "分页记录 更早", "1999-12-31")
    same_instant = datetime(2026, 1, 1, tzinfo=UTC)
    db_session.execute(update(Entry).values(created_at=same_instant))
    db_session.commit()
    expected = sorted((entry["id"] for entry in entries), reverse=True) + [older["id"]]
    first = search(search_client, "分页记录", limit=2)
    assert ids(first) == expected[:2]
    position = decode_cursor(first["next_cursor"])
    assert position["version"] == "search-v1"
    assert set(position) == {"version", "filter_digest", "entry_date", "created_at", "id"}
    assert "分页记录" not in json.dumps(position, ensure_ascii=False)
    create(search_client, "分页记录 插入较新", "2001-01-01")
    # Page size is independent of the bound filters; trimming is canonical.
    second = search(search_client, "  分页记录  ", limit=1, cursor=first["next_cursor"])
    third = search(search_client, "分页记录", limit=100, cursor=second["next_cursor"])
    assert ids(first) + ids(second) + ids(third) == expected
    assert third["next_cursor"] is None


def test_cursor_bound_to_both_dates_query_and_search_endpoint(search_client: TestClient) -> None:
    create(search_client, "cursor 私密词")
    create(search_client, "cursor 私密词")
    filters = {"query": "私密词", "date_from": "1999-01-01", "date_to": "2001-01-01"}
    cursor = search_client.post("/api/v1/search", json={**filters, "limit": 1}).json()[
        "next_cursor"
    ]
    for changed in (
        {"query": "cursor"},
        {"date_from": "1999-01-02"},
        {"date_to": "2001-01-02"},
        {"date_from": None},
        {"date_to": None},
    ):
        response = search_client.post(
            "/api/v1/search", json={**filters, **changed, "cursor": cursor}
        )
        assert response.status_code == 422
        assert response.json() == {"detail": "Invalid request"}
        assert response.headers["Cache-Control"] == "no-store"
    journal_cursor = search_client.get("/api/v1/entries?limit=1").json()["next_cursor"]
    day_cursor = search_client.get("/api/v1/days/2000-02-29?limit=1").json()["entries"][
        "next_cursor"
    ]
    for other_cursor in (journal_cursor, day_cursor):
        response = search_client.post("/api/v1/search", json={**filters, "cursor": other_cursor})
        assert response.status_code == 422
        assert response.json() == {"detail": "Invalid request"}
    assert search_client.get("/api/v1/entries", params={"cursor": cursor}).status_code == 422
    assert (
        search_client.get("/api/v1/days/2000-02-29", params={"cursor": cursor}).status_code == 422
    )


def test_malformed_cursors_are_generic_and_do_not_echo_queries(search_client: TestClient) -> None:
    create(search_client, "不要泄露私密查询")
    create(search_client, "不要泄露私密查询")
    valid = decode_cursor(search(search_client, "私密查询", limit=1)["next_cursor"])
    missing_version = {key: value for key, value in valid.items() if key != "version"}
    invalid = [
        "!invalid",
        "a",
        "中文",
        encode_cursor([]),
        encode_cursor({}),
        encode_cursor(missing_version),
        encode_cursor({**valid, "version": "search-v2"}),
        encode_cursor({**valid, "extra": "私密查询"}),
        encode_cursor({**valid, "created_at": "2000-01-01T00:00:00"}),
        encode_cursor({**valid, "entry_date": "20000229"}),
        encode_cursor({**valid, "entry_date": "2000-02-30"}),
        encode_cursor({**valid, "filter_digest": "x" * 64}),
        encode_cursor({**valid, "id": "invalid"}),
    ]
    for cursor in invalid:
        response = search_client.post(
            "/api/v1/search", json={"query": "私密查询", "cursor": cursor}
        )
        assert response.status_code == 422
        assert response.json() == {"detail": "Invalid request"}
        assert response.headers["Cache-Control"] == "no-store"


def test_search_is_read_only_and_does_not_log_private_terms(
    search_client: TestClient, db_session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    entry = create(search_client, "# 私密读测试\n\n  原文保留  \n")
    before_entries = db_session.execute(select(Entry.__table__)).all()
    before_revisions = db_session.execute(select(EntryRevision.__table__)).all()
    caplog.clear()
    assert ids(search(search_client, "私密读测试")) == [entry["id"]]
    assert ids(search(search_client, date_to="9999-12-31")) == [entry["id"]]
    assert db_session.execute(select(Entry.__table__)).all() == before_entries
    assert db_session.execute(select(EntryRevision.__table__)).all() == before_revisions
    assert "私密读测试" not in caplog.text


def test_session_csrf_origin_and_no_get_search(search_client: TestClient) -> None:
    secret = {"query": "私密请求"}
    token = search_client.headers.pop("X-CSRF-Token")
    assert search_client.post("/api/v1/search", json=secret).status_code == 403
    search_client.headers["X-CSRF-Token"] = token
    for headers in ({"Origin": "https://invalid.example"}, {"Origin": ""}, {"X-CSRF-Token": "bad"}):
        response = search_client.post("/api/v1/search", json=secret, headers=headers)
        assert response.status_code == 403
        assert "私密请求" not in response.text
        assert response.headers["Cache-Control"] == "no-store"
    assert search_client.get("/api/v1/search").status_code == 405
    assert search_client.post("/api/v1/auth/logout").status_code == 204
    response = search_client.post("/api/v1/search", json=secret)
    assert response.status_code == 401
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("cookie", [None, "not-a-token"])
def test_anonymous_search_rejected_without_database_configuration(cookie: str | None) -> None:
    with TestClient(create_app()) as client:
        if cookie is not None:
            client.cookies.set("life_archive_session", cookie)
        response = client.post("/api/v1/search", json={"query": "私密查询"})
    assert response.status_code == 401
    assert "私密查询" not in response.text
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"query": " \n "},
        {"query": None},
        {"query": 12},
        {"query": True},
        {"query": "私" * 201},
        {"query": "私密\x00查询"},
        {"query": "私密", "date_from": "2000-2-29"},
        {"query": "私密", "date_from": "20000229"},
        {"query": "私密", "date_from": "2000-02-30"},
        {"query": "私密", "date_from": "0000-01-01"},
        {"query": "私密", "date_to": "10000-01-01"},
        {"query": "私密", "date_from": "2000-02-29T00:00:00Z"},
        {"query": "私密", "date_from": 951782400},
        {"date_from": "2000-03-01", "date_to": "2000-02-29"},
        *[{"query": "私密", "limit": limit} for limit in (0, 101, True, "1", 1.5, 1.0, None)],
        *[{"query": "私密", "cursor": cursor} for cursor in ("", "a" * 2049, 1, False)],
        {"query": "私密", "unknown": "私密"},
    ],
)
def test_invalid_payloads_are_generic_without_echoing_inputs(payload: dict) -> None:
    app = create_app()
    app.dependency_overrides[require_csrf] = lambda: SimpleNamespace(id=uuid4())
    app.dependency_overrides[get_db_session] = lambda: None
    with TestClient(app) as client:
        response = client.post("/api/v1/search", json=payload)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request"}
    assert response.headers["Cache-Control"] == "no-store"


def test_search_request_defaults_and_normalized_length() -> None:
    request = SearchRequest(query="  " + "词" * 200 + " \n")
    assert request.query == "词" * 200
    assert request.limit == 20
    assert request.cursor is None and request.date_from is None and request.date_to is None
    assert SearchRequest(date_from="0001-01-01", date_to="9999-12-31", limit=100).query == ""
