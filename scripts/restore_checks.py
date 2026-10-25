"""Read-only HTTP and portable-export comparisons for synthetic restore fixtures."""

from __future__ import annotations

import hashlib
import json
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener
from zipfile import ZipFile

from restore_support import require


class Client:
    def __init__(self, port: int):
        self.origin = f"http://127.0.0.1:{port}"
        self.http = build_opener(HTTPCookieProcessor(CookieJar()))
        self.csrf: str | None = None

    def request(self, path: str, *, status: int = 200, body: dict | None = None) -> dict:
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers.update(
                {
                    "Content-Type": "application/json",
                    "Origin": self.origin,
                    "X-LifeArchive-Request": "1",
                }
            )
            if self.csrf:
                headers["X-CSRF-Token"] = self.csrf
        try:
            response = self.http.open(
                Request(self.origin + "/api/v1" + path, data=data, headers=headers), timeout=15
            )
        except HTTPError as error:
            response = error
        with response:
            require(response.status == status, "Restored HTTP status mismatch")
            require(response.headers.get("Cache-Control") == "no-store", "Missing private no-store")
            return json.loads(response.read())

    def login(self, password: str) -> dict:
        self.request("/entries", status=401)
        session = self.request(
            "/auth/login", body={"username": "restore-smoke-owner", "password": password}
        )
        self.csrf = session["csrf_token"]
        return session["user"]

    def views(self, ids: dict[str, str]) -> dict:
        result = {"entries": self.request("/entries?limit=100")}
        require(
            {item["id"] for item in result["entries"]["items"]} == {ids["first"], ids["second"]},
            "Restored active entries mismatch",
        )
        result["entry"] = self.request("/entries/" + ids["first"])
        result["history"] = self.request("/entries/" + ids["first"] + "/revisions")
        require(
            [row["revision"] for row in result["history"]["items"]] == [3, 2, 1],
            "Restored revision history mismatch",
        )
        result["tags"] = self.request("/tags?limit=200")
        require(
            {tag["id"] for tag in result["tags"]["items"]}
            == {ids[key] for key in ("tag_original", "tag_current", "tag_deleted", "tag_unused")}
            and result["tags"]["next_cursor"] is None,
            "Restored tag catalog mismatch",
        )
        require(
            [tag["id"] for tag in result["entry"]["tags"]] == [ids["tag_current"]]
            and [[tag["id"] for tag in row["tags"]] for row in result["history"]["items"]]
            == [[ids["tag_current"]], [], [ids["tag_original"]]],
            "Restored current or historical tags mismatch",
        )
        result["tag_filter"] = self.request("/entries?tag_id=" + ids["tag_original"])
        require(
            [row["id"] for row in result["tag_filter"]["items"]] == [ids["second"]],
            "Restored tag filter mismatch",
        )
        require(
            self.request("/entries?tag_id=" + ids["tag_deleted"])["items"] == [],
            "Deleted tagged entry unexpectedly visible",
        )
        self.request("/entries/" + ids["deleted"], status=404)
        result["calendar"] = self.request("/calendar?year=2000&month=2")
        require(
            result["calendar"]["days"] == [{"date": "2000-02-29", "entry_count": 2}],
            "Restored calendar mismatch",
        )
        result["day"] = self.request("/days/2000-02-29?limit=100")
        result["search"] = self.request(
            "/search",
            body={
                "query": "合成",
                "date_from": "2000-02-29",
                "date_to": "2000-02-29",
                "limit": 100,
            },
        )
        result["past"] = self.request("/on-this-day?date=2024-02-29&limit=100")
        for page in (result["day"]["entries"], result["search"], result["past"]["entries"]):
            require(
                {row["id"] for row in page["items"]} == {ids["first"], ids["second"]},
                "Restored date/search/past-year membership mismatch",
            )
        require(
            self.request("/on-this-day?date=2000-02-29")["entries"]["items"] == [],
            "Same-year entry unexpectedly included",
        )
        return result


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verified_manifest(archive: ZipFile) -> dict:
    manifest = json.loads(archive.read("manifest.json"))
    require(
        manifest["schema_version"] == 2 and manifest["deleted_policy"] == "include_deleted",
        "Unexpected portable export format or deleted policy",
    )
    names = archive.namelist()
    paths = [item["path"] for item in manifest["files"]]
    require(
        len(names) == len(set(names))
        and paths == sorted(set(paths))
        and "tags.json" in paths
        and set(names) == set(paths) | {"manifest.json"},
        "Export member set mismatch",
    )
    for item in manifest["files"]:
        digest, size = hashlib.sha256(), 0
        with archive.open(item["path"]) as member:
            for chunk in iter(lambda: member.read(65536), b""):
                digest.update(chunk)
                size += len(chunk)
        require(
            size == item["bytes"] and digest.hexdigest() == item["sha256"], "Export hash mismatch"
        )
    return manifest


def compare_exports(source: Path, target: Path, expected_head: str) -> dict:
    with ZipFile(source) as left, ZipFile(target) as right:
        a, b = verified_manifest(left), verified_manifest(right)
        for field in (
            "schema_version",
            "alembic_revision",
            "owner",
            "deleted_policy",
            "entry_count",
            "revision_count",
            "files",
        ):
            require(a[field] == b[field], "Source/target portable metadata mismatch")
        require(a["alembic_revision"] == expected_head, "Export migration head mismatch")
        for item in a["files"]:
            with left.open(item["path"]) as x, right.open(item["path"]) as y:
                while True:
                    chunk = x.read(65536)
                    require(chunk == y.read(65536), "Source/target portable bytes mismatch")
                    if not chunk:
                        break
        return {
            "entries": a["entry_count"],
            "revisions": a["revision_count"],
            "files": len(a["files"]),
        }
