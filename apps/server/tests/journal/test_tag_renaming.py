import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from uuid import UUID, uuid4
from zipfile import ZipFile

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from life_archive.auth.dependencies import require_csrf
from life_archive.auth.models import User
from life_archive.auth.security import SESSION_COOKIE, csrf_token
from life_archive.auth.service import create_session
from life_archive.journal import tags
from life_archive.journal.export import export_journal
from life_archive.journal.models import Entry, EntryRevision, EntryTag, Tag
from life_archive.journal.schemas import TagCreate, TagRename

HEADERS = {"Origin": "http://127.0.0.1:8080", "X-LifeArchive-Request": "1"}


def test_rename_normalization_conflicts_validation_and_owner_scope(
    journal_client: TestClient,
) -> None:
    tag = journal_client.post("/api/v1/tags", json={"name": "原名"}).json()
    taken = journal_client.post("/api/v1/tags", json={"name": "Travel"}).json()
    path = f"/api/v1/tags/{tag['id']}"
    body = {"name": "  e\u0301  ", "expected_name": "原名"}
    changed = journal_client.patch(path, json=body, headers=HEADERS)
    assert changed.status_code == 200
    assert changed.json() == tag | {"name": "é"}
    assert changed.headers["cache-control"] == "no-store"
    for name, expected, code in (
        ("覆盖", "原名", "tag_conflict"),
        ("覆盖", "e\u0301", "tag_conflict"),
        ("覆盖", " é ", "tag_conflict"),
        ("  ＴＲＡＶＥＬ  ", "é", "tag_name_taken"),
    ):
        response = journal_client.patch(
            path, json={"name": name, "expected_name": expected}, headers=HEADERS
        )
        assert response.status_code == 409 and response.json()["detail"]["code"] == code
        assert name not in response.text
    same = journal_client.patch(path, json={"name": "é", "expected_name": "é"}, headers=HEADERS)
    assert same.status_code == 200 and same.json() == changed.json()
    for body in (
        {"name": " ", "expected_name": "é"},
        {"name": "a\nb", "expected_name": "é"},
        {"name": "\ud800", "expected_name": "é"},
        {"name": "界" * 41, "expected_name": "é"},
        {"name": "有效", "expected_name": ""},
        {"name": "有效", "expected_name": 1},
        {"name": "有效", "expected_name": None},
        {"name": "有效", "expected_name": "é", "private-extra": "private-value"},
        {"name": "有效"},
    ):
        invalid = journal_client.patch(
            path,
            content=json.dumps(body),
            headers=HEADERS | {"Content-Type": "application/json"},
        )
        assert invalid.status_code == 422 and invalid.json() == {"detail": "Invalid request"}
    names = {
        item["id"]: item["name"] for item in journal_client.get("/api/v1/tags").json()["items"]
    }
    assert names == {tag["id"]: "é", taken["id"]: "Travel"}
    unknown = journal_client.patch(
        f"/api/v1/tags/{uuid4()}", json={"name": "有效", "expected_name": "é"}, headers=HEADERS
    )
    journal_client.app.dependency_overrides[require_csrf] = lambda: SimpleNamespace(id=uuid4())
    foreign = journal_client.patch(
        path, json={"name": "有效", "expected_name": "é"}, headers=HEADERS
    )
    assert unknown.status_code == foreign.status_code == 404
    assert unknown.json() == foreign.json()


def test_rename_requires_real_session_origin_json_custom_header_and_csrf(
    db_client: TestClient, db_session: Session, journal_owner: User
) -> None:
    tag, _ = tags.create_tag(db_session, journal_owner.id, TagCreate(name="安全标签"))
    path = f"/api/v1/tags/{tag.id}"
    body = {"name": "改名", "expected_name": tag.name}
    assert db_client.patch(path, json=body, headers=HEADERS).status_code == 401
    token, _ = create_session(db_session, journal_owner, None)
    db_client.cookies.set(SESSION_COOKIE, token)
    headers = HEADERS | {"X-CSRF-Token": csrf_token(token)}
    for overrides, status in (
        ({"Origin": "https://evil.example"}, 403),
        ({"X-CSRF-Token": "invalid"}, 403),
        ({"X-LifeArchive-Request": "0"}, 403),
        ({"Content-Type": "text/plain"}, 415),
    ):
        response = db_client.patch(path, json=body, headers=headers | overrides)
        assert response.status_code == status and response.headers["cache-control"] == "no-store"
    missing = db_client.patch(
        path, json=body, headers={key: value for key, value in headers.items() if key != "Origin"}
    )
    assert missing.status_code == 403
    assert db_client.patch(path, json=body, headers=headers).status_code == 200


def test_rename_preserves_originals_history_replay_and_export(
    journal_client: TestClient,
    db_session: Session,
    pg_engine: Engine,
    tmp_path: Path,
) -> None:
    tag = journal_client.post("/api/v1/tags", json={"name": "旧名称"}).json()
    payload = {
        "content_md": "  # 原文\r\n组合字 e\u0301  \n",
        "entry_date": "2000-02-29",
        "tag_ids": [tag["id"]],
        "client_request_id": str(uuid4()),
    }
    created = journal_client.post("/api/v1/entries", json=payload).json()
    path = f"/api/v1/entries/{created['id']}"
    before = {
        model: db_session.execute(select(model.__table__)).all()
        for model in (Entry, EntryTag, EntryRevision)
    }
    renamed = journal_client.patch(
        f"/api/v1/tags/{tag['id']}",
        json={"name": "新名称", "expected_name": "旧名称"},
        headers=HEADERS,
    )
    assert renamed.status_code == 200 and renamed.json() == tag | {"name": "新名称"}
    current = journal_client.get(path).json()
    assert current == created | {"tags": [{"id": tag["id"], "name": "新名称"}]}
    replay = journal_client.post("/api/v1/entries", json=payload)
    assert replay.status_code == 200 and replay.json() == current
    assert before == {
        model: db_session.execute(select(model.__table__)).all()
        for model in (Entry, EntryTag, EntryRevision)
    }
    history = journal_client.get(path + "/revisions").json()["items"]
    assert len(history) == 1 and history[0]["tags"] == [{"id": tag["id"], "name": "旧名称"}]
    output = tmp_path / "renamed-tag.zip"
    export_journal(pg_engine, output)
    with ZipFile(output) as archive:
        assert json.loads(archive.read("manifest.json"))["schema_version"] == 4
        exported_tag = json.loads(archive.read("tags.json"))[0]
        assert exported_tag | {"created_at": renamed.json()["created_at"]} == renamed.json()
        assert datetime.fromisoformat(exported_tag["created_at"]) == datetime.fromisoformat(
            renamed.json()["created_at"]
        )
        assert json.loads(archive.read(f"entries/{created['id']}.json"))["tags"] == current["tags"]
        assert (
            json.loads(archive.read(f"revisions/{created['id']}/1.json"))["tags"]
            == history[0]["tags"]
        )
        assert archive.read(f"entries/{created['id']}.md") == payload["content_md"].encode()
    # Subsequent snapshots adopt the current catalogue name; earlier revisions stay intact.
    assert journal_client.delete(path, params={"expected_revision": 1}).status_code == 204
    restored = journal_client.post(path + "/restore", json={"expected_revision": 2})
    assert restored.status_code == 200 and restored.json()["tags"] == current["tags"]
    revisions = journal_client.get(path + "/revisions").json()["items"]
    assert [revision["tags"][0]["name"] for revision in revisions] == ["新名称", "新名称", "旧名称"]


def test_concurrent_renames_serialize_and_database_uniqueness_rolls_back(
    session_factory: sessionmaker[Session], journal_owner: User
) -> None:
    owner_id = journal_owner.id
    with session_factory() as session:
        original, _ = tags.create_tag(session, owner_id, TagCreate(name="原名"))
        tag_id = original.id
    barrier = Barrier(2)

    def rename(name: str) -> tuple[int, str]:
        with session_factory() as session:
            # Force a stale identity-map object before the winning request commits.
            cached = session.get(Tag, tag_id)
            assert cached is not None and cached.name == "原名"
            barrier.wait(timeout=10)
            try:
                tags.rename_tag(
                    session, owner_id, tag_id, TagRename(name=name, expected_name="原名")
                )
                return 200, name
            except HTTPException as error:
                assert error.detail["code"] == "tag_conflict"
                return error.status_code, name

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(rename, ["并发甲", "并发乙"]))
    assert sorted(status for status, _ in results) == [200, 409]
    winner = next(name for status, name in results if status == 200)
    with session_factory() as session:
        assert session.get(Tag, tag_id).name == winner
        other, _ = tags.create_tag(session, owner_id, TagCreate(name="另一个"))
        other_id = other.id
    barrier = Barrier(2)

    def collide(item: tuple[UUID, str]) -> int:
        with session_factory() as session:
            barrier.wait(timeout=10)
            try:
                tags.rename_tag(
                    session, owner_id, item[0], TagRename(name="共同名称", expected_name=item[1])
                )
                return 200
            except HTTPException as error:
                assert error.detail["code"] == "tag_name_taken"
                # Constraint failure must have rolled the transaction back for reuse.
                assert session.scalar(select(Tag).where(Tag.id == item[0])).name == item[1]
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(collide, [(tag_id, winner), (other_id, "另一个")])) == [200, 409]
