"""Authenticated, paginated tag catalogue with existing CSRF requirements."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from life_archive.auth.dependencies import require_login_request
from life_archive.journal import tags
from life_archive.journal.models import Tag
from life_archive.journal.router import Database, Owner, WriteOwner
from life_archive.journal.schemas import TagCreate, TagPage, TagRename, TagResponse

router = APIRouter(prefix="/tags", tags=["journal"])


@router.get("", response_model=TagPage)
def list_page(
    user: Owner,
    session: Database,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    cursor: UUID | None = None,
) -> TagPage:
    return tags.list_tags(session, user.id, limit=limit, cursor=cursor)


@router.post("", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
def create(payload: TagCreate, response: Response, user: WriteOwner, session: Database) -> Tag:
    tag, created = tags.create_tag(session, user.id, payload)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return tag


@router.patch(
    "/{tag_id}", response_model=TagResponse, dependencies=[Depends(require_login_request)]
)
def rename(tag_id: UUID, payload: TagRename, user: WriteOwner, session: Database) -> Tag:
    return tags.rename_tag(session, user.id, tag_id, payload)
