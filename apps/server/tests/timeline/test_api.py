from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from life_archive.auth.dependencies import require_user
from life_archive.journal.models import Entry

MARKDOWN = "  # 补记\n\n原始 **Markdown**\r\n- [ ] 中文\n\n```text\n<不渲染的原文>\n```\n  "


def create(client: TestClient, day: str, content: str = MARKDOWN) -> dict:
    response = client.post("/api/v1/entries", json={"content_md": content, "entry_date": day})
    assert response.status_code == 201, response.text
    return response.json()


def calendar(client: TestClient, year: int, month: int) -> dict:
    response = client.get("/api/v1/calendar", params={"year": year, "month": month})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def test_calendar_groups_backdated_entries_by_archive_date_not_utc_creation(
    timeline_client: TestClient, db_session: Session
) -> None:
    for day in ("2024-02-29", "2024-02-01", "2024-02-29", "2024-01-31", "2024-03-01"):
        create(timeline_client, day)
    # UTC creation, owner-local creation and archive day are three different labels.
    db_session.execute(update(Entry).values(created_at=datetime(2026, 1, 1, 23, tzinfo=UTC)))
    db_session.commit()
    assert calendar(timeline_client, 2024, 2) == {
        "year": 2024,
        "month": 2,
        "days": [
            {"date": "2024-02-01", "entry_count": 1},
            {"date": "2024-02-29", "entry_count": 2},
        ],
    }
    assert calendar(timeline_client, 2026, 1)["days"] == []
    day = timeline_client.get("/api/v1/days/2024-02-29")
    assert day.status_code == 200
    assert day.headers["cache-control"] == "no-store"
    assert set(day.json()) == {"date", "entries"}
    assert day.json()["date"] == "2024-02-29"
    assert [entry["content_md"] for entry in day.json()["entries"]["items"]] == [MARKDOWN] * 2
    assert day.json()["entries"]["next_cursor"] is None


@pytest.mark.parametrize(
    ("year", "month", "inside", "outside"),
    [
        (2023, 12, "2023-12-31", "2024-01-01"),
        (2024, 1, "2024-01-01", "2023-12-31"),
        (2023, 2, "2023-02-28", "2023-03-01"),
        (2000, 2, "2000-02-29", "2000-03-01"),
        (1900, 2, "1900-02-28", "1900-03-01"),
        (1, 1, "0001-01-01", "0001-02-01"),
        (9999, 12, "9999-12-31", "9999-11-30"),
    ],
)
def test_month_bounds_handle_year_edges_and_gregorian_leap_rules(
    timeline_client: TestClient, year: int, month: int, inside: str, outside: str
) -> None:
    create(timeline_client, inside)
    create(timeline_client, outside)
    assert calendar(timeline_client, year, month)["days"] == [{"date": inside, "entry_count": 1}]
    response = timeline_client.get(f"/api/v1/days/{inside}")
    assert response.status_code == 200
    assert [item["entry_date"] for item in response.json()["entries"]["items"]] == [inside]


def test_empty_month_and_day_are_successful_empty_responses(timeline_client: TestClient) -> None:
    assert calendar(timeline_client, 2024, 2) == {"year": 2024, "month": 2, "days": []}
    response = timeline_client.get("/api/v1/days/2024-02-29")
    assert response.status_code == 200
    assert response.json() == {"date": "2024-02-29", "entries": {"items": [], "next_cursor": None}}
    assert response.headers["cache-control"] == "no-store"


def test_day_pagination_reuses_journal_order_and_preserves_every_original(
    timeline_client: TestClient,
) -> None:
    selected = "2001-01-02"
    expected = [
        create(timeline_client, selected, f"{MARKDOWN}\n第 {number} 篇") for number in range(21)
    ]
    create(timeline_client, "2001-01-03", "其他日期，不应混入")
    first = timeline_client.get(f"/api/v1/days/{selected}").json()
    assert len(first["entries"]["items"]) == 20
    assert (
        first["entries"]
        == timeline_client.get("/api/v1/entries", params={"entry_date": selected}).json()
    )
    cursor = first["entries"]["next_cursor"]
    assert cursor is not None
    second = timeline_client.get(f"/api/v1/days/{selected}", params={"cursor": cursor}).json()
    assert len(second["entries"]["items"]) == 1
    assert second["entries"]["next_cursor"] is None
    combined = first["entries"]["items"] + second["entries"]["items"]
    assert {item["id"]: item["content_md"] for item in combined} == {
        item["id"]: item["content_md"] for item in expected
    }
    assert (
        timeline_client.get("/api/v1/days/2001-01-03", params={"cursor": cursor}).status_code == 422
    )


def test_unfiltered_journal_cursor_cannot_be_used_for_day_view(timeline_client: TestClient) -> None:
    for _ in range(2):
        create(timeline_client, "2001-01-02")
    cursor = timeline_client.get("/api/v1/entries", params={"limit": 1}).json()["next_cursor"]
    assert cursor is not None
    assert (
        timeline_client.get("/api/v1/days/2001-01-02", params={"cursor": cursor}).status_code == 422
    )


def test_date_edit_and_soft_delete_update_refreshed_counts_and_day_contents(
    timeline_client: TestClient,
) -> None:
    first = create(timeline_client, "2024-02-29")
    second = create(timeline_client, "2024-02-29", "第二条")
    moved = timeline_client.patch(
        f"/api/v1/entries/{first['id']}",
        json={"expected_revision": 1, "entry_date": "2024-03-01"},
    )
    assert moved.status_code == 200
    assert calendar(timeline_client, 2024, 2)["days"] == [{"date": "2024-02-29", "entry_count": 1}]
    assert calendar(timeline_client, 2024, 3)["days"] == [{"date": "2024-03-01", "entry_count": 1}]
    february = timeline_client.get("/api/v1/days/2024-02-29").json()
    assert [item["id"] for item in february["entries"]["items"]] == [second["id"]]
    assert (
        timeline_client.delete(
            f"/api/v1/entries/{second['id']}", params={"expected_revision": 1}
        ).status_code
        == 204
    )
    assert calendar(timeline_client, 2024, 2)["days"] == []
    assert timeline_client.get("/api/v1/days/2024-02-29").json()["entries"]["items"] == []
    assert (
        timeline_client.get("/api/v1/days/2024-03-01").json()["entries"]["items"][0]["content_md"]
        == MARKDOWN
    )


def test_calendar_and_day_never_include_a_different_owners_records(
    timeline_client: TestClient,
) -> None:
    create(timeline_client, "2024-02-29")
    stranger = SimpleNamespace(id=uuid4())
    timeline_client.app.dependency_overrides[require_user] = lambda: stranger
    assert calendar(timeline_client, 2024, 2)["days"] == []
    assert timeline_client.get("/api/v1/days/2024-02-29").json()["entries"]["items"] == []


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"year": 2024},
        {"month": 2},
        {"year": 0, "month": 2},
        {"year": 10000, "month": 2},
        {"year": "invalid", "month": 2},
        {"year": 2024, "month": 0},
        {"year": 2024, "month": 13},
        {"year": 2024, "month": "2.5"},
    ],
)
def test_invalid_month_queries_are_rejected(timeline_client: TestClient, params: dict) -> None:
    response = timeline_client.get("/api/v1/calendar", params=params)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request"}
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/days/2023-02-29",
        "/api/v1/days/1900-02-29",
        "/api/v1/days/2024-2-1",
        "/api/v1/days/2024-02-29T00:00:00Z",
        "/api/v1/days/0000-01-01",
        "/api/v1/days/10000-01-01",
        "/api/v1/days/2024-02-29?limit=0",
        "/api/v1/days/2024-02-29?limit=101",
        "/api/v1/days/2024-02-29?cursor=not-a-cursor!",
    ],
)
def test_invalid_day_queries_are_rejected(timeline_client: TestClient, path: str) -> None:
    response = timeline_client.get(path)
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", ["/api/v1/calendar?year=2024&month=2", "/api/v1/days/2024-02-29"])
def test_anonymous_requests_fail_before_database_configuration(path: str) -> None:
    from life_archive.main import create_app

    with TestClient(create_app()) as client:
        response = client.get(path)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
