"""Authenticated read-only trash listing; restoration uses the journal write route."""

from typing import Annotated

from fastapi import APIRouter, Query

from life_archive.journal.router import Database, Owner, PageLimit
from life_archive.journal.schemas import TrashPage
from life_archive.journal.trash import list_trash

router = APIRouter(prefix="/trash", tags=["journal"])


@router.get("", response_model=TrashPage)
def list_page(
    user: Owner,
    session: Database,
    limit: PageLimit = 20,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> TrashPage:
    return list_trash(session, user.id, limit=limit, cursor=cursor)
