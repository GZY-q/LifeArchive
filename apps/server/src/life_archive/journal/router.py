"""All journal operations require the owner; writes additionally require CSRF."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from life_archive.auth.dependencies import require_csrf, require_user
from life_archive.auth.models import User
from life_archive.db import get_db_session
from life_archive.journal import service
from life_archive.journal.models import Entry
from life_archive.journal.schemas import (
    ArchiveDate,
    EntryCreate,
    EntryPage,
    EntryResponse,
    EntryRestore,
    EntryUpdate,
    RevisionPage,
)
from life_archive.journal.trash import restore_entry

router = APIRouter(prefix="/entries", tags=["journal"])
Database = Annotated[Session, Depends(get_db_session)]
Owner = Annotated[User, Depends(require_user)]
WriteOwner = Annotated[User, Depends(require_csrf)]
PageLimit = Annotated[int, Query(ge=1, le=100)]


@router.post("", response_model=EntryResponse, status_code=status.HTTP_201_CREATED)
def create(payload: EntryCreate, response: Response, user: WriteOwner, session: Database) -> Entry:
    entry, created = service.create_entry(session, user.id, payload)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return entry


@router.get("", response_model=EntryPage)
def list_page(
    user: Owner,
    session: Database,
    limit: PageLimit = 20,
    cursor: Annotated[str | None, Query(max_length=1024)] = None,
    entry_date: ArchiveDate | None = None,
    tag_id: UUID | None = None,
) -> EntryPage:
    return service.list_entries(
        session, user.id, limit=limit, cursor=cursor, entry_date=entry_date, tag_id=tag_id
    )


@router.get("/{entry_id}", response_model=EntryResponse)
def read(entry_id: UUID, user: Owner, session: Database) -> Entry:
    return service.get_entry(session, user.id, entry_id)


@router.patch("/{entry_id}", response_model=EntryResponse)
def edit(entry_id: UUID, payload: EntryUpdate, user: WriteOwner, session: Database) -> Entry:
    return service.edit_entry(session, user.id, entry_id, payload)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(
    entry_id: UUID,
    user: WriteOwner,
    session: Database,
    expected_revision: Annotated[int, Query(gt=0)],
) -> Response:
    service.delete_entry(session, user.id, entry_id, expected_revision)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{entry_id}/revisions", response_model=RevisionPage)
def revisions(
    entry_id: UUID,
    user: Owner,
    session: Database,
    limit: PageLimit = 20,
    before_revision: Annotated[int | None, Query(gt=0)] = None,
) -> RevisionPage:
    return service.list_revisions(
        session, user.id, entry_id, limit=limit, before_revision=before_revision
    )


@router.post("/{entry_id}/restore", response_model=EntryResponse)
def restore(entry_id: UUID, payload: EntryRestore, user: WriteOwner, session: Database) -> Entry:
    return restore_entry(session, user.id, entry_id, payload.expected_revision)
