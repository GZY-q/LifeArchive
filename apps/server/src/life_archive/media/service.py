"""Validated immutable uploads; owner row locks serialize deduplication and quota."""

import hashlib
import warnings
from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID, uuid4

from fastapi import HTTPException
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from life_archive.auth.models import User
from life_archive.media.models import Asset
from life_archive.media.storage import (
    MAX_UPLOAD_BYTES,
    MediaStorageError,
    read_original,
    write_original,
)
from life_archive.settings import get_media_settings

MIME_BY_FORMAT = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
EXTENSION_BY_MIME = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def _image_metadata(data: bytes, content_type: str) -> tuple[str, int, int]:
    if not data:
        raise HTTPException(422, "Invalid image")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Image exceeds the upload limit")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data), formats=tuple(MIME_BY_FORMAT)) as image:
                mime = MIME_BY_FORMAT[image.format]
                width, height = image.size
                if (
                    mime != content_type
                    or not 0 < width <= 20_000
                    or not 0 < height <= 20_000
                    or width * height > 20_000_000
                    or getattr(image, "n_frames", 1) != 1
                ):
                    raise ValueError("Unsupported image")
                image.verify()
            # verify() does not decode JPEG pixels. Decode separately to reject
            # truncated originals while still retaining the untouched upload bytes.
            with Image.open(BytesIO(data), formats=tuple(MIME_BY_FORMAT)) as image:
                image.load()
        return mime, width, height
    except (
        OSError,
        ValueError,
        SyntaxError,
        EOFError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ):
        raise HTTPException(422, "Invalid or unsupported image") from None


def create_asset(
    session: Session, user_id: UUID, data: bytes, content_type: str
) -> tuple[Asset, bool]:
    mime, width, height = _image_metadata(data, content_type)
    digest = hashlib.sha256(data).hexdigest()
    try:
        owner = session.scalar(select(User.id).where(User.id == user_id).with_for_update())
        if owner is None:
            raise HTTPException(401, "Authentication required")
        existing = session.scalar(
            select(Asset).where(Asset.user_id == user_id, Asset.sha256 == digest)
        )
        if existing is not None:
            # Deduplication is not a repair path: a broken original must not be
            # reported as a successful upload or silently overwritten.
            read_original(existing)
            session.commit()
            return existing, False
        used = session.scalar(
            select(func.coalesce(func.sum(Asset.byte_size), 0)).where(Asset.user_id == user_id)
        )
        if used + len(data) > get_media_settings().media_quota_bytes:
            raise HTTPException(413, "Private media quota exceeded")
        asset_id = uuid4()
        asset = Asset(
            id=asset_id,
            user_id=user_id,
            mime_type=mime,
            byte_size=len(data),
            sha256=digest,
            width=width,
            height=height,
            storage_key=asset_id.hex,
            created_at=datetime.now(UTC),
        )
        write_original(asset.storage_key, data)
        session.add(asset)
        session.commit()
    except MediaStorageError:
        session.rollback()
        raise HTTPException(503, "Private media is unavailable") from None
    except Exception:
        session.rollback()
        raise
    return asset, True


def get_asset(session: Session, user_id: UUID, asset_id: UUID) -> Asset:
    asset = session.scalar(select(Asset).where(Asset.id == asset_id, Asset.user_id == user_id))
    if asset is None:
        raise HTTPException(404, "Image not found")
    return asset
