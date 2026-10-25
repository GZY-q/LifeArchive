import hashlib
import json
import os
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4
from zipfile import ZipFile

import pytest
from sqlalchemy import create_engine, insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import CreateSchema

from life_archive import cli
from life_archive.auth.models import AuthSession, LoginThrottle, User
from life_archive.journal import export as exporter
from life_archive.journal.models import Entry, EntryRevision, EntryTag, Tag
from life_archive.journal.schemas import EntryCreate, EntryUpdate, TagCreate
from life_archive.journal.service import create_entry, delete_entry, edit_entry
from life_archive.journal.tags import create_tag

RAW = "  # 中文 /../ 标题 😀\r\n\r\n<script>private()</script>  \n组合字 e\u0301\n"


def create(
    db: Session,
    owner: User,
    content: str = RAW,
    day: str = "2000-02-29",
    *,
    tags: tuple[Tag, ...] = (),
) -> Entry:
    entry, _ = create_entry(
        db,
        owner.id,
        EntryCreate(
            content_md=content,
            entry_date=day,
            client_request_id=uuid4(),
            tag_ids=[tag.id for tag in tags],
        ),
    )
    return entry


def inspect_export(path: Path) -> tuple[dict, dict[str, bytes]]:
    assert path.stat().st_mode & 0o777 == 0o600
    with ZipFile(path) as archive:
        names = archive.namelist()
        assert len(set(names)) == len(names)
        assert names[-1] == "manifest.json"
        manifest = json.loads(archive.read("manifest.json"))
        files = manifest["files"]
        assert [item["path"] for item in files] == sorted(item["path"] for item in files)
        assert set(names) == {item["path"] for item in files} | {"manifest.json"}
        data = {}
        for item in files:
            assert set(item) == {"path", "bytes", "sha256"}
            assert not item["path"].startswith("/") and ".." not in item["path"].split("/")
            raw = archive.read(item["path"])
            assert len(raw) == item["bytes"]
            assert hashlib.sha256(raw).hexdigest() == item["sha256"]
            assert archive.getinfo(item["path"]).external_attr >> 16 & 0o777 == 0o600
            data[item["path"]] = raw
        return manifest, data


def database_rows(db: Session) -> dict:
    return {
        model.__tablename__: db.execute(
            select(model.__table__).order_by(*model.__table__.primary_key.columns)
        ).all()
        for model in (User, Entry, EntryRevision, Tag, EntryTag, AuthSession, LoginThrottle)
    }


@pytest.mark.parametrize("include_deleted", [False, True])
def test_raw_metadata_all_selected_revisions_and_deleted_policy_are_read_only(
    pg_engine: Engine,
    db_session: Session,
    journal_owner: User,
    tmp_path: Path,
    include_deleted: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    tags = [
        create_tag(db_session, journal_owner.id, TagCreate(name=name))[0]
        for name in ("原始标签", "当前标签", "未使用标签", "仅软删除标签")
    ]
    entry = create(db_session, journal_owner, tags=(tags[0],))
    original_request = entry.client_request_id
    edited = RAW + "\n修订保留尾空格  \n"
    edit_entry(
        db_session,
        journal_owner.id,
        entry.id,
        EntryUpdate(
            expected_revision=1,
            content_md=edited,
            entry_date="0001-01-01",
            tag_ids=[tags[1].id],
        ),
    )
    instant = datetime(2026, 10, 25, 12, 30, tzinfo=timezone(timedelta(hours=8)))
    db_session.execute(
        update(Entry)
        .where(Entry.id == entry.id)
        .values(
            occurred_at=instant,
            occurred_timezone="Asia/Shanghai",
        )
    )
    db_session.add(
        AuthSession(
            token_hash="f" * 64,
            user_id=journal_owner.id,
            created_at=instant,
            expires_at=instant + timedelta(days=1),
        )
    )
    db_session.add(LoginThrottle(id=1, window_started_at=instant, attempts=2))
    db_session.commit()
    deleted = create(db_session, journal_owner, "软删除仍保留历史", "9999-12-31", tags=(tags[3],))
    delete_entry(db_session, journal_owner.id, deleted.id, 1)
    before = database_rows(db_session)
    caplog.clear()
    output = tmp_path / "archive.zip"
    result = exporter.export_journal(pg_engine, output, include_deleted=include_deleted)
    manifest, files = inspect_export(output)
    assert manifest["schema_version"] == 2
    assert manifest["alembic_revision"] == "0004_entry_tags"
    catalog = json.loads(files["tags.json"])
    assert catalog == [
        {"id": str(tag.id), "name": tag.name, "created_at": tag.created_at.isoformat()}
        for tag in sorted(tags, key=lambda tag: tag.id)
    ]
    assert datetime.fromisoformat(manifest["exported_at"]).utcoffset() == timedelta(0)
    assert manifest["owner"] == {
        "id": str(journal_owner.id),
        "username": journal_owner.username,
        "timezone": journal_owner.timezone,
        "created_at": journal_owner.created_at.isoformat(),
    }
    expected_count = 2 if include_deleted else 1
    assert manifest["deleted_policy"] == ("include_deleted" if include_deleted else "active_only")
    assert manifest["entry_count"] == result.entry_count == expected_count
    assert manifest["revision_count"] == result.revision_count == expected_count * 2
    base = f"entries/{entry.id}"
    assert files[base + ".md"] == edited.encode("utf-8")
    current = json.loads(files[base + ".json"])
    assert set(current) == {
        "id",
        "user_id",
        "entry_date",
        "occurred_at",
        "occurred_timezone",
        "created_at",
        "updated_at",
        "deleted_at",
        "revision",
        "client_request_id",
        "markdown_path",
        "tags",
    }
    assert current["id"] == str(entry.id) and current["user_id"] == str(journal_owner.id)
    assert current["client_request_id"] == str(original_request)
    assert current["entry_date"] == "0001-01-01" and current["revision"] == 2
    assert current["deleted_at"] is None
    assert current["occurred_at"] == "2026-10-25T04:30:00+00:00"
    assert current["occurred_timezone"] == "Asia/Shanghai"
    assert current["tags"] == [{"id": str(tags[1].id), "name": tags[1].name}]
    for field in ("created_at", "updated_at"):
        assert datetime.fromisoformat(current[field]).utcoffset() == timedelta(0)
    for number, content in ((1, RAW), (2, edited)):
        path = f"revisions/{entry.id}/{number}"
        assert files[path + ".md"] == content.encode("utf-8")
        revision = json.loads(files[path + ".json"])
        assert set(revision) == {
            "id",
            "entry_id",
            "editor_id",
            "revision",
            "entry_date",
            "changed_at",
            "markdown_path",
            "tags",
        }
        assert revision["entry_id"] == str(entry.id)
        assert revision["editor_id"] == str(journal_owner.id)
        assert revision["entry_date"] == ("2000-02-29" if number == 1 else "0001-01-01")
        assert datetime.fromisoformat(revision["changed_at"]).utcoffset() == timedelta(0)
        tag = tags[number - 1]
        assert revision["tags"] == [{"id": str(tag.id), "name": tag.name}]
    if include_deleted:
        removed = json.loads(files[f"entries/{deleted.id}.json"])
        assert removed["deleted_at"] is not None and removed["revision"] == 2
        assert removed["occurred_at"] is None and removed["occurred_timezone"] is None
        assert files[f"revisions/{deleted.id}/1.md"] == "软删除仍保留历史".encode()
        assert removed["entry_date"] == "9999-12-31"
        assert removed["tags"] == [{"id": str(tags[3].id), "name": tags[3].name}]
        assert json.loads(files[f"revisions/{deleted.id}/2.json"])["tags"] == removed["tags"]
    else:
        assert all(str(deleted.id) not in path for path in files)
    public_metadata = json.dumps(manifest) + "".join(
        raw.decode() for path, raw in files.items() if path.endswith(".json")
    )
    for secret in ("password_hash", "token_hash", "csrf", "sessions", journal_owner.password_hash):
        assert secret not in public_metadata
    assert RAW not in caplog.text and journal_owner.password_hash not in caplog.text
    assert database_rows(db_session) == before


def test_consistent_read_only_snapshot_survives_concurrent_edit_and_delete(
    pg_engine: Engine,
    db_session: Session,
    journal_owner: User,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_tag, _ = create_tag(db_session, journal_owner.id, TagCreate(name="快照标签"))
    first = create(db_session, journal_owner, "快照原文一", tags=(original_tag,))
    second = create(db_session, journal_owner, "快照原文二")
    initial = {str(first.id): "快照原文一", str(second.id): "快照原文二"}
    original_write = ZipFile.writestr
    triggered = False

    def race(archive, info, data, *args, **kwargs):
        nonlocal triggered
        if not triggered and info.filename.startswith("entries/"):
            triggered = True
            with session_factory() as writer:
                changed_tag, _ = create_tag(writer, journal_owner.id, TagCreate(name="并发标签"))
                edit_entry(
                    writer,
                    journal_owner.id,
                    first.id,
                    EntryUpdate(
                        expected_revision=1,
                        content_md="并发新原文",
                        entry_date="2026-10-25",
                        tag_ids=[changed_tag.id],
                    ),
                )
                delete_entry(writer, journal_owner.id, second.id, 1)
        return original_write(archive, info, data, *args, **kwargs)

    original_snapshot = exporter._write_snapshot

    def check_transaction(connection, archive, include_deleted):
        assert (
            connection.exec_driver_sql("SHOW transaction_isolation").scalar_one()
            == "repeatable read"
        )
        assert connection.exec_driver_sql("SHOW transaction_read_only").scalar_one() == "on"
        return original_snapshot(connection, archive, include_deleted)

    monkeypatch.setattr(ZipFile, "writestr", race)
    monkeypatch.setattr(exporter, "_write_snapshot", check_transaction)
    output = tmp_path / "snapshot.zip"
    exporter.export_journal(pg_engine, output)
    manifest, files = inspect_export(output)
    assert triggered and manifest["entry_count"] == manifest["revision_count"] == 2
    assert [tag["name"] for tag in json.loads(files["tags.json"])] == ["快照标签"]
    for entry_id, content in initial.items():
        assert files[f"entries/{entry_id}.md"] == content.encode()
        assert files[f"revisions/{entry_id}/1.md"] == content.encode()
        assert json.loads(files[f"entries/{entry_id}.json"])["revision"] == 1
        assert json.loads(files[f"entries/{entry_id}.json"])["deleted_at"] is None
        assert f"revisions/{entry_id}/2.md" not in files
        expected_tags = (
            [{"id": str(original_tag.id), "name": original_tag.name}]
            if entry_id == str(first.id)
            else []
        )
        for path in (f"entries/{entry_id}.json", f"revisions/{entry_id}/1.json"):
            assert json.loads(files[path])["tags"] == expected_tags
    with session_factory() as reader:
        assert reader.get(Entry, first.id).content_md == "并发新原文"
        assert reader.get(Entry, second.id).deleted_at is not None


def test_empty_archive_and_repeated_exports_have_stable_data_files(
    pg_engine: Engine,
    db_session: Session,
    journal_owner: User,
    tmp_path: Path,
) -> None:
    empty = tmp_path / "empty.zip"
    exporter.export_journal(pg_engine, empty)
    manifest, files = inspect_export(empty)
    assert manifest["entry_count"] == manifest["revision_count"] == 0
    assert files == {"tags.json": b"[]\n"}
    create(db_session, journal_owner)
    outputs = [tmp_path / "one.zip", tmp_path / "two.zip"]
    for path in outputs:
        exporter.export_journal(pg_engine, path)
    assert inspect_export(outputs[0])[1] == inspect_export(outputs[1])[1]


def test_export_streams_more_than_one_batch_of_entries_and_revisions(
    pg_engine: Engine,
    db_session: Session,
    journal_owner: User,
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC)
    entries, revisions = [], []
    for index in range(103):
        entry_id = uuid4()
        count = 101 if index == 0 else 1
        entries.append(
            dict(
                id=entry_id,
                user_id=journal_owner.id,
                content_md=f"批次 {index}/{count}",
                entry_date=date(2000, 2, 29),
                created_at=now,
                updated_at=now,
                revision=count,
            )
        )
        revisions.extend(
            dict(
                id=uuid4(),
                entry_id=entry_id,
                editor_id=journal_owner.id,
                revision=revision,
                content_md=f"批次 {index}/{revision}",
                entry_date=date(2000, 2, 29),
                changed_at=now,
            )
            for revision in range(1, count + 1)
        )
    db_session.execute(insert(Entry), entries)
    db_session.execute(insert(EntryRevision), revisions)
    db_session.commit()
    output = tmp_path / "batches.zip"
    exporter.export_journal(pg_engine, output)
    manifest, files = inspect_export(output)
    assert manifest["entry_count"] == 103 and manifest["revision_count"] == 203
    assert len(files) == (103 + 203) * 2 + 1
    for row in entries:
        assert files[f"entries/{row['id']}.md"] == row["content_md"].encode()
    for row in revisions:
        assert (
            files[f"revisions/{row['entry_id']}/{row['revision']}.md"] == row["content_md"].encode()
        )


@pytest.mark.parametrize("kind", ["file", "directory", "symlink", "dangling_symlink"])
def test_existing_output_is_refused_without_changing_it(
    kind: str,
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    target.write_bytes(b"existing private bytes")
    output = tmp_path / "archive.zip"
    if kind == "file":
        output.write_bytes(b"existing output")
    elif kind == "directory":
        output.mkdir()
    else:
        output.symlink_to(target if kind == "symlink" else tmp_path / "missing")
    engine = Mock(spec=Engine)
    with pytest.raises(FileExistsError):
        exporter.export_journal(engine, output)
    engine.connect.assert_not_called()
    assert target.read_bytes() == b"existing private bytes"
    if kind == "file":
        assert output.read_bytes() == b"existing output"
    elif kind == "directory":
        assert list(output.iterdir()) == []
    else:
        assert output.is_symlink()


def test_relative_path_missing_parent_and_unwritable_directory_are_refused(tmp_path: Path) -> None:
    engine = Mock(spec=Engine)
    with pytest.raises(exporter.ExportError, match="absolute path"):
        exporter.export_journal(engine, Path("relative.zip"))
    with pytest.raises(FileNotFoundError):
        exporter.export_journal(engine, tmp_path / "missing" / "archive.zip")
    directory = tmp_path / "locked"
    directory.mkdir(mode=0o500)
    try:
        if os.geteuid() != 0:
            with pytest.raises(PermissionError):
                exporter.export_journal(engine, directory / "archive.zip")
    finally:
        directory.chmod(0o700)
    engine.connect.assert_not_called()


def test_missing_owner_and_missing_migration_fail_without_creating_data(
    pg_engine: Engine,
    tmp_path: Path,
) -> None:
    with pytest.raises(exporter.ExportError, match="Owner has not"):
        exporter.export_journal(pg_engine, tmp_path / "no-owner.zip")
    schema = "export_unmigrated_" + uuid4().hex
    with pg_engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    engine = create_engine(
        pg_engine.url,
        hide_parameters=True,
        connect_args={
            "options": f"-c search_path={schema} -c timezone=UTC",
        },
    )
    try:
        with pytest.raises(exporter.ExportError, match="migrations are missing"):
            exporter.export_journal(engine, tmp_path / "unmigrated.zip")
        with engine.connect() as connection:
            assert (
                connection.exec_driver_sql(
                    "SELECT count(*) FROM pg_tables WHERE schemaname = current_schema()"
                ).scalar_one()
                == 0
            )
    finally:
        engine.dispose()
    for path in (tmp_path / "no-owner.zip", tmp_path / "unmigrated.zip"):
        assert path.stat().st_mode & 0o777 == 0o600
        with ZipFile(path) as archive:
            assert "manifest.json" not in archive.namelist()


def test_cli_exports_without_password_prompt_or_private_output_and_refuses_overwrite(
    pg_engine: Engine,
    db_session: Session,
    journal_owner: User,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    create(db_session, journal_owner)
    monkeypatch.setattr(cli, "get_engine", lambda: pg_engine)
    monkeypatch.setattr(
        cli.getpass, "getpass", lambda _: pytest.fail("Export requested a password")
    )
    output = tmp_path / "archive.zip"
    arguments = ["export-journal", "--output", str(output), "--include-deleted"]
    assert cli.main(arguments) == 0
    capture = capsys.readouterr()
    assert json.loads(capture.out) == {"output": str(output), "entries": 1, "revisions": 1}
    assert capture.err == ""
    before = output.read_bytes()
    assert cli.main(arguments) == 1
    capture = capsys.readouterr()
    assert capture.out == "" and "already exists" in capture.err
    assert output.read_bytes() == before
    assert RAW not in capture.err and journal_owner.password_hash not in capture.err


@pytest.mark.parametrize(
    "failure", [RuntimeError("private SQL password=secret"), KeyboardInterrupt()]
)
def test_interrupted_exports_fail_privately_and_retain_incomplete_output(
    pg_engine: Engine,
    db_session: Session,
    journal_owner: User,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: BaseException,
) -> None:
    create(db_session, journal_owner)
    monkeypatch.setattr(cli, "get_engine", lambda: pg_engine)
    original = ZipFile.writestr

    def fail(archive, info, data, *args, **kwargs):
        assert os.fstat(archive.fp.fileno()).st_mode & 0o777 == 0o600
        if info.filename.endswith(".json"):
            raise failure
        return original(archive, info, data, *args, **kwargs)

    monkeypatch.setattr(ZipFile, "writestr", fail)
    output = tmp_path / "interrupted.zip"
    status = cli.main(["export-journal", "--output", str(output)])
    assert status == (130 if isinstance(failure, KeyboardInterrupt) else 1)
    capture = capsys.readouterr()
    assert capture.out == "" and str(output) in capture.err
    assert "private SQL" not in capture.err and "password=" not in capture.err
    assert RAW not in capture.err and "Traceback" not in capture.err
    assert output.exists() and output.stat().st_mode & 0o777 == 0o600
    with ZipFile(output) as archive:
        assert len(archive.namelist()) == 1
        assert "manifest.json" not in archive.namelist()


def test_verification_failure_cannot_be_reported_as_success(
    pg_engine: Engine,
    db_session: Session,
    journal_owner: User,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    create(db_session, journal_owner)
    monkeypatch.setattr(cli, "get_engine", lambda: pg_engine)
    original = ZipFile.writestr

    def corrupt(archive, info, data, *args, **kwargs):
        return original(
            archive, info, b"corrupted" if info.filename.endswith(".md") else data, *args, **kwargs
        )

    monkeypatch.setattr(ZipFile, "writestr", corrupt)
    output = tmp_path / "corrupted.zip"
    assert cli.main(["export-journal", "--output", str(output)]) == 1
    capture = capsys.readouterr()
    assert capture.out == "" and "verification failed" in capture.err
    assert output.exists()


def test_configuration_failure_and_parser_errors_do_not_expose_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def bad_database():
        raise ValueError("postgresql://owner:private-password@database/private")

    monkeypatch.setattr(cli, "get_engine", bad_database)
    assert cli.main(["export-journal", "--output", str(tmp_path / "archive.zip")]) == 1
    capture = capsys.readouterr()
    assert capture.out == "" and "private-password" not in capture.err
    assert "postgresql://" not in capture.err
    for arguments in (["export-journal"], ["export-journal", "--output", "/tmp/test", "--force"]):
        with pytest.raises(SystemExit) as error:
            cli.main(arguments)
        assert error.value.code == 2
