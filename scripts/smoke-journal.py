"""Exercise M1 against an explicitly isolated test deployment, never real journals."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.parse import urlsplit
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

    request("GET", "/entries", 401)
    session = request("POST", "/auth/login", 200, {"username": args.username, "password": password})
    assert isinstance(session, dict)
    csrf = session["csrf_token"]
    user_id = session["user"]["id"]
    cookie = next(item for item in cookies if item.name == "life_archive_session")
    assert cookie.path == "/api/v1" and cookie.has_nonstandard_attr("HttpOnly")
    original_cookie = f"{cookie.name}={cookie.value}"
    assert request("GET", "/auth/me", 200) == session
    print("PASS: anonymous access denied; owner session and HttpOnly cookie work")

    markdown = "# 隔离验收\n\n中文原文、尾部空格。  \n<script>test-only</script>\n"
    payload = {
        "content_md": markdown,
        "entry_date": "2000-02-29",
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

    patch = {"expected_revision": 1, "content_md": markdown + "修改\n", "entry_date": "1999-12-31"}
    edited = request("PATCH", f"/entries/{entry['id']}", 200, patch, csrf=csrf)
    assert edited["revision"] == 2
    request("PATCH", f"/entries/{entry['id']}", 409, patch, csrf=csrf)
    history = request("GET", f"/entries/{entry['id']}/revisions", 200)
    assert [item["revision"] for item in history["items"]] == [2, 1]
    assert history["items"][1]["content_md"] == markdown
    page = request("GET", "/entries?limit=1", 200)
    assert page["next_cursor"]
    print("PASS: edits create immutable revisions; stale writes return 409; pagination works")

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
        print("PASS: owner session and journal revision persist across PostgreSQL restart")

    request("DELETE", f"/entries/{entry['id']}?expected_revision=1", 409, csrf=csrf)
    request("DELETE", f"/entries/{entry['id']}?expected_revision=2", 204, csrf=csrf)
    request("GET", f"/entries/{entry['id']}", 404)
    request("POST", "/entries", 404, payload, csrf=csrf)
    request("DELETE", f"/entries/{another['id']}?expected_revision=1", 204, csrf=csrf)
    request("POST", "/auth/logout", 204, csrf=csrf)
    request("GET", "/auth/me", 401)
    request("GET", "/auth/me", 401, extra_headers={"Cookie": original_cookie})
    print("PASS: revision-checked soft deletion, no resurrection, logout revocation")
    print("PASS: all M1 journal smoke checks completed")


if __name__ == "__main__":
    main()
