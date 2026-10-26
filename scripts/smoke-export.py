"""Run inside the isolated API container after journal/browser smoke fixtures."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile

from sqlalchemy import select

from life_archive.auth.models import AuthSession, LoginThrottle, User
from life_archive.db import get_engine
from life_archive.journal.models import Entry, EntryRevision, EntryTag, Tag
from life_archive.media.models import Asset, EntryAsset
from life_archive.media.storage import read_original


def fingerprint() -> str:
    digest = hashlib.sha256()
    with get_engine().connect() as connection:
        for model in (
            User,
            AuthSession,
            LoginThrottle,
            Entry,
            EntryRevision,
            Tag,
            EntryTag,
            Asset,
            EntryAsset,
        ):
            digest.update(model.__tablename__.encode())
            query = select(model.__table__).order_by(*model.__table__.primary_key.columns)
            with connection.execute(query.execution_options(yield_per=100)) as rows:
                for row in rows.mappings():
                    digest.update(json.dumps(dict(row), default=str, sort_keys=True).encode())
                    if model is Asset:
                        digest.update(hashlib.sha256(read_original(row)).digest())
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-isolated-export", action="store_true", required=True)
    parser.parse_args()
    project = os.environ.get("LIFEARCHIVE_EXPORT_SMOKE_PROJECT", "")
    if not project.startswith(("life-archive-ci-", "life-archive-smoke")):
        parser.error("Explicit isolated CI/smoke project required")
    directory = Path(tempfile.mkdtemp(prefix="life-archive-export-smoke-"))
    directory.chmod(0o700)
    before = fingerprint()
    counts = []
    for include_deleted in (False, True):
        output = directory / ("with-deleted.zip" if include_deleted else "active.zip")
        arguments = [
            sys.executable,
            "-m",
            "life_archive.cli",
            "export-journal",
            "--output",
            str(output),
        ]
        if include_deleted:
            arguments.append("--include-deleted")
        process = subprocess.run(arguments, capture_output=True, text=True, check=False)
        assert process.returncode == 0, "Isolated CLI export failed"
        result = json.loads(process.stdout)
        assert set(result) == {"output", "entries", "revisions"}
        assert result["output"] == str(output)
        assert output.stat().st_mode & 0o777 == 0o600
        with ZipFile(output) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["schema_version"] == 4
            assert manifest["deleted_policy"] == (
                "include_deleted" if include_deleted else "active_only"
            )
            assert manifest["entry_count"] == result["entries"]
            assert manifest["revision_count"] == result["revisions"]
            assert set(manifest["owner"]) == {"id", "username", "timezone", "created_at"}
            names = archive.namelist()
            assert len(names) == len(set(names)) and names[-1] == "manifest.json"
            assert set(names) == {"manifest.json"} | {item["path"] for item in manifest["files"]}
            catalog = json.loads(archive.read("tags.json"))
            assert all(set(tag) == {"id", "name", "created_at"} for tag in catalog)
            assets = json.loads(archive.read("assets.json"))
            assert len(assets) == manifest["asset_count"]
            for asset in assets:
                original = archive.read(asset["file_path"])
                assert len(original) == asset["byte_size"]
                assert hashlib.sha256(original).hexdigest() == asset["sha256"]
            for item in manifest["files"]:
                data = archive.read(item["path"])
                assert len(data) == item["bytes"]
                assert hashlib.sha256(data).hexdigest() == item["sha256"]
                if item["path"].startswith(("entries/", "revisions/")) and item["path"].endswith(
                    ".json"
                ):
                    assert type(json.loads(data)["is_pinned"]) is bool
        unchanged = hashlib.sha256(output.read_bytes()).digest()
        refused = subprocess.run(arguments, capture_output=True, text=True, check=False)
        assert refused.returncode == 1 and refused.stdout == ""
        assert "already exists" in refused.stderr
        assert hashlib.sha256(output.read_bytes()).digest() == unchanged
        counts.append(result["entries"])
    # Earlier smoke created and soft-deleted synthetic entries. This ensures
    # the installed image actually exported data and historical snapshots.
    assert counts[1] > counts[0], "Expected soft-deleted isolated smoke fixtures"
    assert fingerprint() == before, "Export changed source data"
    print(
        "PASS: installed CLI exports, SHA-256, 0600, deleted policy, "
        "overwrite refusal, source unchanged"
    )


if __name__ == "__main__":
    main()
