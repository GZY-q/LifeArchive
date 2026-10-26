"""Owner-scoped tag catalogue; journal associations are written by journal service."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from life_archive.journal.models import Tag
from life_archive.journal.schemas import (
    TagCreate,
    TagPage,
    TagRename,
    TagResponse,
    normalize_tag_name,
)


def create_tag(session: Session, user_id: UUID, payload: TagCreate) -> tuple[Tag, bool]:
    name, name_key = normalize_tag_name(payload.name)
    statement = select(Tag).where(Tag.user_id == user_id, Tag.name_key == name_key)
    existing = session.scalar(statement)
    if existing is not None:
        return existing, False
    tag = Tag(user_id=user_id, name=name, name_key=name_key, created_at=datetime.now(UTC))
    try:
        session.add(tag)
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(statement)
        if existing is not None:
            return existing, False
        raise
    except Exception:
        session.rollback()
        raise
    return tag, True


def rename_tag(session: Session, user_id: UUID, tag_id: UUID, payload: TagRename) -> Tag:
    """Rename one catalogue row without rewriting journal or revision snapshots."""
    name, name_key = normalize_tag_name(payload.name)
    try:
        tag = session.scalar(
            select(Tag)
            .where(Tag.id == tag_id, Tag.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if tag is None:
            raise HTTPException(404, "Tag not found")
        if tag.name != payload.expected_name:
            raise HTTPException(
                409,
                {"code": "tag_conflict", "message": "Tag changed; reload before renaming"},
            )
        tag.name = name
        tag.name_key = name_key
        session.commit()
    except IntegrityError as error:
        session.rollback()
        if getattr(getattr(error.orig, "diag", None), "constraint_name", None) != (
            "uq_tags_user_id_name_key"
        ):
            raise
        raise HTTPException(
            409, {"code": "tag_name_taken", "message": "Tag name is already in use"}
        ) from None
    except Exception:
        session.rollback()
        raise
    return tag


def list_tags(session: Session, user_id: UUID, *, limit: int, cursor: UUID | None) -> TagPage:
    statement = select(Tag).where(Tag.user_id == user_id)
    if cursor is not None:
        statement = statement.where(Tag.id > cursor)
    tags = list(session.scalars(statement.order_by(Tag.id).limit(limit + 1)))
    return TagPage(
        items=[TagResponse.model_validate(tag) for tag in tags[:limit]],
        next_cursor=tags[limit - 1].id if len(tags) > limit else None,
    )
