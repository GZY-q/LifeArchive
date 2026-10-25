"""Read-only POST keeps private search terms out of URLs and access logs."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from life_archive.auth.dependencies import require_csrf
from life_archive.auth.models import User
from life_archive.db import get_db_session
from life_archive.journal.schemas import EntryPage
from life_archive.search.schemas import SearchRequest
from life_archive.search.service import search_entries

router = APIRouter(prefix="/search", tags=["search"])
Owner = Annotated[User, Depends(require_csrf)]
Database = Annotated[Session, Depends(get_db_session)]


@router.post("", response_model=EntryPage)
def search(payload: SearchRequest, user: Owner, session: Database) -> EntryPage:
    return search_entries(session, user.id, payload)
