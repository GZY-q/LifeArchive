"""Exercise M1 and calendar/day views in an isolated test deployment, never real journals."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import date
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener
from uuid import uuid4


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:18080")
    parser.add_argument("--username", default="m1-smoke-owner")
    parser.add_argument("--allow-test-writes", action="store_true", required=True)
    parser.add_argument("--restart-postgres", action="store_true")
    args = parser.parse_args()
    project = os.environ.get("COMPOSE_PROJECT_NAME", "")
    if not project.startswith(("life-archive-ci-", "life-archive-smoke")):
        parser.error("Set COMPOSE_PROJECT_NAME to an isolated life-archive-ci-/smoke project")
    password = os.environ.get("LIFEARCHIVE_SMOKE_PASSWORD")
    if not password:
        parser.error("Set LIFEARCHIVE_SMOKE_PASSWORD to the isolated owner's password")
    base_url = args.base_url.rstrip("/")
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        parser.error("Smoke writes are restricted to a loopback HTTP test deployment")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    cookies = CookieJar()
    client = build_opener(HTTPCookieProcessor(cookies))

    def request(
        method: str,
        path: str,
        expected: int,
        body: object = None,
        *,
        csrf: str | None = None,
        source_origin: str = origin,
        extra_headers: dict[str, str] | None = None,
    ) -> object:
        headers = {"Accept": "application/json"}
        if method != "GET":
            headers.update({"Origin": source_origin, "X-LifeArchive-Request": "1"})
        if csrf is not None:
            headers["X-CSRF-Token"] = csrf
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body, ensure_ascii=False).encode()
        headers.update(extra_headers or {})
        try:
            response = client.open(
                Request(base_url + "/api/v1" + path, data=data, headers=headers, method=method),
                timeout=10,
            )
        except HTTPError as error:
            response = error
        with response:
            assert response.status == expected, (
                f"{method} {path}: expected {expected}, got {response.status}"
            )
            assert response.headers.get("Cache-Control") == "no-store"
            raw = response.read()
            return json.loads(raw) if raw else None

    def calendar_count(day: str) -> int:
        selected = date.fromisoformat(day)
        calendar = request("GET", f"/calendar?year={selected.year}&month={selected.month}", 200)
        assert isinstance(calendar, dict) and set(calendar) == {"year", "month", "days"}
        assert (calendar["year"], calendar["month"]) == (selected.year, selected.month)
        days = calendar["days"]
        assert isinstance(days, list)
        counts = {}
        for item in days:
            assert set(item) == {"date", "entry_count"}
            calendar_day = date.fromisoformat(item["date"])
            assert (calendar_day.year, calendar_day.month) == (selected.year, selected.month)
            assert type(item["entry_count"]) is int and item["entry_count"] > 0
            counts[item["date"]] = item["entry_count"]
        assert [item["date"] for item in days] == sorted(counts)
        return counts.get(day, 0)

    def day_page(day: str, *, limit: int = 100, cursor: str | None = None) -> dict:
        params = {"limit": str(limit)}
        if cursor is not None:
            params["cursor"] = cursor
        response = request("GET", f"/days/{day}?{urlencode(params)}", 200)
        assert isinstance(response, dict) and set(response) == {"date", "entries"}
        assert response["date"] == day
        page = response["entries"]
        assert set(page) == {"items", "next_cursor"}
        assert isinstance(page["items"], list) and len(page["items"]) <= limit
        assert all(item["entry_date"] == day for item in page["items"])
        assert page["next_cursor"] is None or (
            isinstance(page["next_cursor"], str) and page["next_cursor"]
        )
        return page

    def day_entries(day: str) -> dict[str, dict]:
        entries = {}
        cursor = None
        seen_cursors = set()
        while True:
            page = day_page(day, cursor=cursor)
            for item in page["items"]:
                assert item["id"] not in entries, "Day pagination repeated an entry"
                entries[item["id"]] = item
            cursor = page["next_cursor"]
            if cursor is None:
                return entries
            assert cursor not in seen_cursors, "Day pagination repeated a cursor"
            seen_cursors.add(cursor)

    source_day = "2000-02-29"
    destination_day = "1999-12-31"
    request("GET", "/entries", 401)
    request("GET", "/calendar?year=2000&month=2", 401)
    request("GET", f"/days/{source_day}", 401)
    session = request("POST", "/auth/login", 200, {"username": args.username, "password": password})
    assert isinstance(session, dict)
    csrf = session["csrf_token"]
    user_id = session["user"]["id"]
    cookie = next(item for item in cookies if item.name == "life_archive_session")
    assert cookie.path == "/api/v1" and cookie.has_nonstandard_attr("HttpOnly")
    original_cookie = f"{cookie.name}={cookie.value}"
    assert request("GET", "/auth/me", 200) == session
    print("PASS: anonymous access denied; owner session and HttpOnly cookie work")

    # Existing test journals may share these dates; assert only our own count changes.
    source_baseline = calendar_count(source_day)
    destination_baseline = calendar_count(destination_day)
    markdown = "# 隔离验收\n\n中文原文、尾部空格。  \n<script>test-only</script>\n"
    payload = {
        "content_md": markdown,
        "entry_date": source_day,
        "client_request_id": str(uuid4()),
    }
    request("POST", "/entries", 403, payload)
    request("POST", "/entries", 403, payload, csrf=csrf, source_origin="https://invalid.example")
    entry = request("POST", "/entries", 201, payload, csrf=csrf)
    assert isinstance(entry, dict) and entry["content_md"] == markdown
    assert entry["entry_date"] == payload["entry_date"] and entry["revision"] == 1
    replay = request("POST", "/entries", 200, payload, csrf=csrf)
    assert replay["id"] == entry["id"]
    request("POST", "/entries", 409, {**payload, "content_md": "different"}, csrf=csrf)
    another = request(
        "POST", "/entries", 201, {**payload, "client_request_id": str(uuid4())}, csrf=csrf
    )
    assert another["id"] != entry["id"]
    assert request("GET", f"/entries/{entry['id']}", 200)["content_md"] == markdown
    print("PASS: CSRF/origin enforced; raw Markdown, backdating and creation deduplication work")

    assert calendar_count(source_day) == source_baseline + 2
    first_day_page = day_page(source_day, limit=1)
    assert len(first_day_page["items"]) == 1 and first_day_page["next_cursor"]
    day_cursor = first_day_page["next_cursor"]
    second_day_page = day_page(source_day, limit=1, cursor=day_cursor)
    assert len(second_day_page["items"]) == 1
    assert first_day_page["items"][0]["id"] != second_day_page["items"][0]["id"]
    request("GET", f"/days/{destination_day}?{urlencode({'cursor': day_cursor})}", 422)
    original_day = day_entries(source_day)
    assert len(original_day) == source_baseline + 2
    assert original_day[entry["id"]] == entry
    assert original_day[another["id"]] == another
    print("PASS: leap-day counts, raw Markdown, day pagination and date-bound cursors work")

    patch = {
        "expected_revision": 1,
        "content_md": markdown + "修改\n",
        "entry_date": destination_day,
    }
    edited = request("PATCH", f"/entries/{entry['id']}", 200, patch, csrf=csrf)
    assert edited["revision"] == 2
    request("PATCH", f"/entries/{entry['id']}", 409, patch, csrf=csrf)
    history = request("GET", f"/entries/{entry['id']}/revisions", 200)
    assert [item["revision"] for item in history["items"]] == [2, 1]
    assert history["items"][1]["content_md"] == markdown
    page = request("GET", "/entries?limit=1", 200)
    assert page["next_cursor"]
    print("PASS: edits create immutable revisions; stale writes return 409; pagination works")

    assert calendar_count(source_day) == source_baseline + 1
    assert calendar_count(destination_day) == destination_baseline + 1
    remaining_day = day_entries(source_day)
    assert entry["id"] not in remaining_day and remaining_day[another["id"]] == another
    assert day_entries(destination_day)[entry["id"]] == edited
    print("PASS: moving a journal across months/years updates calendar counts and day views")

    if args.restart_postgres:
        subprocess.run(["docker", "compose", "restart", "postgres"], check=True)
        for _ in range(40):
            ready = subprocess.run(
                [
                    "docker",
                    "compose",
                    "exec",
                    "-T",
                    "postgres",
                    "sh",
                    "-c",
                    'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise AssertionError("PostgreSQL did not become ready")
        assert request("GET", "/auth/me", 200)["user"]["id"] == user_id
        assert request("GET", f"/entries/{entry['id']}", 200) == edited
        assert calendar_count(source_day) == source_baseline + 1
        assert calendar_count(destination_day) == destination_baseline + 1
        assert day_entries(destination_day)[entry["id"]] == edited
        print("PASS: owner session and journal revision persist across PostgreSQL restart")

    request("DELETE", f"/entries/{entry['id']}?expected_revision=1", 409, csrf=csrf)
    request("DELETE", f"/entries/{entry['id']}?expected_revision=2", 204, csrf=csrf)
    request("GET", f"/entries/{entry['id']}", 404)
    request("POST", "/entries", 404, payload, csrf=csrf)
    assert calendar_count(destination_day) == destination_baseline
    assert entry["id"] not in day_entries(destination_day)
    assert calendar_count(source_day) == source_baseline + 1
    request("DELETE", f"/entries/{another['id']}?expected_revision=1", 204, csrf=csrf)
    assert calendar_count(source_day) == source_baseline
    assert {entry["id"], another["id"]}.isdisjoint(day_entries(source_day))
    print("PASS: soft-deleted test journals disappear from calendar counts and day views")
    request("POST", "/auth/logout", 204, csrf=csrf)
    request("GET", "/auth/me", 401)
    request("GET", "/auth/me", 401, extra_headers={"Cookie": original_cookie})
    print("PASS: revision-checked soft deletion, no resurrection, logout revocation")
    print("PASS: all M1 journal and M2 first-slice calendar/day smoke checks completed")


if __name__ == "__main__":
    main()
