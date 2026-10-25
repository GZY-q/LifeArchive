import base64
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from life_archive.auth.dependencies import require_user
from life_archive.auth.models import User
from life_archive.db import get_db_session
from life_archive.journal.models import Entry, EntryRevision
from life_archive.main import create_app
from life_archive.timeline import on_this_day as service

RAW = "  # 往年原文\r\n\n中文 **Markdown** 😀  \n<script>not executed</script>\n"


def create(client: TestClient, day: str, content: str = RAW) -> dict:
    response = client.post("/api/v1/entries", json={"entry_date": day, "content_md": content})
    assert response.status_code == 201
    return response.json()


def read(client: TestClient, day: str | None = None, **params: object) -> dict:
    if day is not None:
        params["date"] = day
    response = client.get("/api/v1/on-this-day", params=params)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    data = response.json()
    assert set(data) == {"date", "entries"}
    assert set(data["entries"]) == {"items", "next_cursor"}
    if day is not None:
        assert data["date"] == day
    return data


def ids(data: dict) -> list[str]:
    return [entry["id"] for entry in data["entries"]["items"]]


def decode(cursor: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))


def encode(value: object) -> str:
    return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")


def test_matches_only_past_years_exact_month_and_day_with_original_markdown(
    timeline_client: TestClient, db_session: Session
) -> None:
    old = create(timeline_client, "1990-10-25")
    recent = create(timeline_client, "2025-10-25")
    for day in ("2026-10-25", "2027-10-25", "2025-10-24", "2025-11-25"):
        create(timeline_client, day)
    # Creation instant is unrelated to the user-assigned anniversary.
    db_session.execute(update(Entry).values(created_at=datetime(2030, 1, 1, tzinfo=UTC)))
    db_session.commit()
    result = read(timeline_client, "2026-10-25")
    assert ids(result) == [recent["id"], old["id"]]
    assert [item["content_md"] for item in result["entries"]["items"]] == [RAW, RAW]
    assert result["entries"]["next_cursor"] is None


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("2024-02-29", ["2004-02-29", "2000-02-29", "1600-02-29"]),
        ("2000-02-29", ["1600-02-29"]),
        ("2024-02-28", ["2001-02-28", "1900-02-28"]),
        ("2024-03-01", ["2001-03-01"]),
    ],
)
def test_gregorian_anniversary_never_moves_leap_day(
    timeline_client: TestClient, reference: str, expected: list[str]
) -> None:
    for day in (
        "1600-02-29",
        "1900-02-28",
        "2000-02-29",
        "2004-02-29",
        "2001-02-28",
        "2001-03-01",
        "2024-02-29",
        "2028-02-29",
    ):
        create(timeline_client, day)
    result = read(timeline_client, reference)
    assert [item["entry_date"] for item in result["entries"]["items"]] == expected


def test_year_boundaries_and_empty_days(timeline_client: TestClient) -> None:
    earliest = create(timeline_client, "0001-12-31")
    penultimate = create(timeline_client, "9998-12-31")
    create(timeline_client, "9999-12-31")
    assert ids(read(timeline_client, "9999-12-31")) == [penultimate["id"], earliest["id"]]
    for day in ("0001-12-31", "0001-01-01", "9999-12-30"):
        assert read(timeline_client, day) == {
            "date": day,
            "entries": {"items": [], "next_cursor": None},
        }


def test_refresh_tracks_current_edits_and_soft_delete_not_historical_revisions(
    timeline_client: TestClient,
) -> None:
    entry = create(timeline_client, "2020-10-25")
    edited = timeline_client.patch(
        f"/api/v1/entries/{entry['id']}",
        json={"expected_revision": 1, "entry_date": "2021-10-26", "content_md": "新的原文"},
    )
    assert edited.status_code == 200
    assert ids(read(timeline_client, "2026-10-25")) == []
    assert read(timeline_client, "2026-10-26")["entries"]["items"] == [edited.json()]
    assert (
        timeline_client.delete(
            f"/api/v1/entries/{entry['id']}", params={"expected_revision": 2}
        ).status_code
        == 204
    )
    assert ids(read(timeline_client, "2026-10-26")) == []


def test_owner_scope_and_owner_bound_cursor(timeline_client: TestClient) -> None:
    create(timeline_client, "2020-10-25")
    create(timeline_client, "2020-10-25")
    cursor = read(timeline_client, "2026-10-25", limit=1)["entries"]["next_cursor"]
    timeline_client.app.dependency_overrides[require_user] = lambda: SimpleNamespace(
        id=uuid4(), timezone="UTC"
    )
    assert ids(read(timeline_client, "2026-10-25")) == []
    response = timeline_client.get(
        "/api/v1/on-this-day", params={"date": "2026-10-25", "cursor": cursor}
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request"}


def test_default_page_size_keyset_ties_and_newer_insert(
    timeline_client: TestClient, db_session: Session
) -> None:
    entries = [create(timeline_client, "2020-10-25", f"原文 {index}") for index in range(21)]
    older = create(timeline_client, "2019-10-25")
    db_session.execute(update(Entry).values(created_at=datetime(2026, 1, 1, tzinfo=UTC)))
    db_session.commit()
    expected = sorted((entry["id"] for entry in entries), reverse=True) + [older["id"]]
    first = read(timeline_client, "2026-10-25")
    assert ids(first) == expected[:20]
    cursor = first["entries"]["next_cursor"]
    assert decode(cursor)["version"] == "on-this-day-v1"
    create(timeline_client, "2025-10-25", "新增较新记录")
    second = read(timeline_client, "2026-10-25", cursor=cursor, limit=1)
    third = read(timeline_client, "2026-10-25", cursor=second["entries"]["next_cursor"], limit=100)
    assert ids(first) + ids(second) + ids(third) == expected
    assert third["entries"]["next_cursor"] is None


def test_cursors_cannot_cross_reference_dates_or_other_endpoints(
    timeline_client: TestClient,
) -> None:
    for _ in range(2):
        create(timeline_client, "2020-10-25")
    cursor = read(timeline_client, "2026-10-25", limit=1)["entries"]["next_cursor"]
    for reference in ("2027-10-25", "2026-10-26"):
        response = timeline_client.get(
            "/api/v1/on-this-day", params={"date": reference, "cursor": cursor}
        )
        assert response.status_code == 422
        assert response.json() == {"detail": "Invalid request"}
    journal = timeline_client.get("/api/v1/entries?limit=1").json()["next_cursor"]
    day = timeline_client.get("/api/v1/days/2020-10-25?limit=1").json()["entries"]["next_cursor"]
    search = timeline_client.post("/api/v1/search", json={"query": "往年", "limit": 1}).json()[
        "next_cursor"
    ]
    for foreign in (journal, day, search):
        response = timeline_client.get(
            "/api/v1/on-this-day", params={"date": "2026-10-25", "cursor": foreign}
        )
        assert response.status_code == 422
        assert response.json() == {"detail": "Invalid request"}
    assert timeline_client.get("/api/v1/entries", params={"cursor": cursor}).status_code == 422
    assert (
        timeline_client.get("/api/v1/days/2020-10-25", params={"cursor": cursor}).status_code == 422
    )
    assert (
        timeline_client.post("/api/v1/search", json={"query": "往年", "cursor": cursor}).status_code
        == 422
    )


def test_malformed_or_incoherent_cursor_has_generic_error(timeline_client: TestClient) -> None:
    for _ in range(2):
        create(timeline_client, "2020-10-25")
    valid = decode(read(timeline_client, "2026-10-25", limit=1)["entries"]["next_cursor"])
    bad_cursors = [
        "!invalid",
        "a",
        "中文",
        encode([]),
        encode({}),
        encode({**valid, "version": "other"}),
        encode({**valid, "private": RAW}),
        encode({**valid, "user_id": "invalid"}),
        encode({**valid, "reference_date": "20261025"}),
        encode({**valid, "created_at": "2020-01-01T00:00:00"}),
        encode({**valid, "entry_date": "2026-10-25"}),
        encode({**valid, "entry_date": "2020-10-26"}),
        encode({**valid, "id": "invalid"}),
    ]
    for cursor in bad_cursors:
        response = timeline_client.get(
            "/api/v1/on-this-day", params={"date": "2026-10-25", "cursor": cursor}
        )
        assert response.status_code == 422
        assert response.json() == {"detail": "Invalid request"}
        assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    ("timezone", "expected"),
    [("Pacific/Kiritimati", "2026-01-01"), ("Pacific/Honolulu", "2025-12-31")],
)
def test_default_date_uses_current_utc_in_owner_timezone(
    timeline_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    timezone: str,
    expected: str,
) -> None:
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is UTC
            return datetime(2026, 1, 1, 5, 30, tzinfo=UTC)

    monkeypatch.setattr(service, "datetime", FrozenDatetime)
    db_session.execute(update(User).values(timezone=timezone))
    db_session.commit()
    january = create(timeline_client, "2020-01-01")
    december = create(timeline_client, "2020-12-31")
    result = read(timeline_client)
    assert result["date"] == expected
    assert ids(result) == [january["id"] if expected.endswith("01-01") else december["id"]]
    assert ids(read(timeline_client, "2026-01-01")) == [january["id"]]


def test_returned_reference_date_stabilizes_pagination_across_midnight(
    timeline_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    instant = datetime(2026, 10, 24, 9, 59, tzinfo=UTC)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is UTC
            return instant

    monkeypatch.setattr(service, "datetime", Clock)
    old = create(timeline_client, "2019-10-24")
    create(timeline_client, "2020-10-24")
    next_day = create(timeline_client, "2020-10-25")
    first = read(timeline_client, limit=1)
    assert first["date"] == "2026-10-24"
    cursor = first["entries"]["next_cursor"]
    instant = datetime(2026, 10, 24, 10, 1, tzinfo=UTC)
    assert ids(read(timeline_client, first["date"], cursor=cursor)) == [old["id"]]
    assert ids(read(timeline_client)) == [next_day["id"]]
    assert timeline_client.get("/api/v1/on-this-day", params={"cursor": cursor}).status_code == 422


def test_reads_preserve_entries_and_revisions_and_require_live_session(
    timeline_client: TestClient, db_session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    create(timeline_client, "2020-10-25")
    before_entries = db_session.execute(select(Entry.__table__)).all()
    before_revisions = db_session.execute(select(EntryRevision.__table__)).all()
    caplog.clear()
    assert len(ids(read(timeline_client, "2026-10-25"))) == 1
    assert db_session.execute(select(Entry.__table__)).all() == before_entries
    assert db_session.execute(select(EntryRevision.__table__)).all() == before_revisions
    assert RAW not in caplog.text
    assert timeline_client.post("/api/v1/auth/logout").status_code == 204
    response = timeline_client.get("/api/v1/on-this-day?date=2026-10-25")
    assert response.status_code == 401
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("cookie", [None, "not-a-session"])
def test_anonymous_request_fails_without_database_configuration(cookie: str | None) -> None:
    with TestClient(create_app()) as client:
        if cookie is not None:
            client.cookies.set("life_archive_session", cookie)
        response = client.get("/api/v1/on-this-day")
    assert response.status_code == 401
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    "params",
    [
        *[
            {"date": day}
            for day in (
                "",
                "2023-02-29",
                "1900-02-29",
                "2024-2-29",
                "20240229",
                "0000-01-01",
                "10000-01-01",
                "2024-02-29T00:00:00Z",
                "私密原文",
            )
        ],
        *[{"limit": limit} for limit in (0, 101, -1, "true", "1.5")],
        {"cursor": ""},
        {"cursor": "x" * 2049},
    ],
)
def test_invalid_queries_return_no_store_generic_validation_error(params: dict) -> None:
    app = create_app()
    app.dependency_overrides[require_user] = lambda: SimpleNamespace(id=uuid4(), timezone="UTC")
    app.dependency_overrides[get_db_session] = lambda: None
    with TestClient(app) as client:
        response = client.get("/api/v1/on-this-day", params=params)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request"}
    assert response.headers["Cache-Control"] == "no-store"
