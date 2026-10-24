from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from life_archive.auth.models import User
from life_archive.journal import service
from life_archive.journal.models import Entry, EntryRevision
from life_archive.journal.schemas import EntryCreate, EntryUpdate


def test_concurrent_creation_has_one_original_and_one_snapshot(
    session_factory: sessionmaker[Session],
    journal_owner: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    barrier = Barrier(2)
    original_find = service._find_request

    def simultaneous_first_lookup(session: Session, *args: object) -> Entry | None:
        result = original_find(session, *args)
        if not session.info.get("initial_lookup_complete"):
            session.info["initial_lookup_complete"] = True
            barrier.wait(timeout=10)
        return result

    monkeypatch.setattr(service, "_find_request", simultaneous_first_lookup)
    payload = EntryCreate(
        content_md="相同请求\n", entry_date=date(2000, 1, 1), client_request_id=uuid4()
    )
    owner_id = journal_owner.id

    def create() -> tuple[str, bool]:
        with session_factory() as session:
            entry, created = service.create_entry(session, owner_id, payload)
            return str(entry.id), created

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: create(), range(2)))
    assert len({entry_id for entry_id, _ in results}) == 1
    assert sorted(created for _, created in results) == [False, True]
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Entry)) == 1
        assert session.scalar(select(func.count()).select_from(EntryRevision)) == 1


def test_concurrent_edits_cannot_overwrite_each_other(
    session_factory: sessionmaker[Session], journal_owner: User
) -> None:
    owner_id = journal_owner.id
    with session_factory() as session:
        entry, _ = service.create_entry(
            session, owner_id, EntryCreate(content_md="原文", entry_date=date(2000, 1, 1))
        )
        entry_id = entry.id
    barrier = Barrier(2)

    def edit(content: str) -> int:
        with session_factory() as session:
            barrier.wait(timeout=10)
            try:
                service.edit_entry(
                    session,
                    owner_id,
                    entry_id,
                    EntryUpdate(expected_revision=1, content_md=content),
                )
            except HTTPException as error:
                assert error.detail["code"] == "revision_conflict"
                return error.status_code
            return 200

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(edit, ["来自页面A", "来自页面B"]))
    assert sorted(results) == [200, 409]
    with session_factory() as session:
        entry = service.get_entry(session, owner_id, entry_id)
        assert entry.revision == 2 and entry.content_md in {"来自页面A", "来自页面B"}
        history = session.scalars(
            select(EntryRevision)
            .where(EntryRevision.entry_id == entry_id)
            .order_by(EntryRevision.revision)
        ).all()
        assert len(history) == 2
        assert history[0].content_md == "原文"
        assert history[1].content_md == entry.content_md


def test_delete_and_edit_compete_on_the_same_revision(
    session_factory: sessionmaker[Session], journal_owner: User
) -> None:
    owner_id = journal_owner.id
    with session_factory() as session:
        entry, _ = service.create_entry(
            session, owner_id, EntryCreate(content_md="原文", entry_date=date(2000, 1, 1))
        )
        entry_id = entry.id
    barrier = Barrier(2)

    def change(operation: str) -> int:
        with session_factory() as session:
            barrier.wait(timeout=10)
            try:
                if operation == "delete":
                    service.delete_entry(session, owner_id, entry_id, expected_revision=1)
                    return 204
                service.edit_entry(
                    session,
                    owner_id,
                    entry_id,
                    EntryUpdate(expected_revision=1, content_md="新原文"),
                )
                return 200
            except HTTPException as error:
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(change, ["delete", "edit"]))
    assert sorted(results) in ([200, 409], [204, 404])
    with session_factory() as session:
        stored = session.get(Entry, entry_id)
        assert stored is not None and stored.revision == 2
        assert (stored.deleted_at is not None) == (204 in results)
        assert session.scalar(select(func.count()).select_from(EntryRevision)) == 2
