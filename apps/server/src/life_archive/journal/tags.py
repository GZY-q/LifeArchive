"""Owner-scoped tag catalogue; journal associations are written by journal service."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from life_archive.journal.models import Tag
from life_archive.journal.schemas import TagCreate, TagPage, TagResponse, normalize_tag_name


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


def list_tags(session: Session, user_id: UUID, *, limit: int, cursor: UUID | None) -> TagPage:
    statement = select(Tag).where(Tag.user_id == user_id)
    if cursor is not None:
        statement = statement.where(Tag.id > cursor)
    tags = list(session.scalars(statement.order_by(Tag.id).limit(limit + 1)))
    return TagPage(
        items=[TagResponse.model_validate(tag) for tag in tags[:limit]],
        next_cursor=tags[limit - 1].id if len(tags) > limit else None,
    )
