"""Authenticated raw-byte uploads and owner-only immutable original reads."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from life_archive.journal.router import Database, Owner, WriteOwner
from life_archive.media.schemas import AssetResponse
from life_archive.media.service import EXTENSION_BY_MIME, MIME_BY_FORMAT, create_asset, get_asset
from life_archive.media.storage import MAX_UPLOAD_BYTES, MediaStorageError, read_original

router = APIRouter(prefix="/assets", tags=["media"])


@router.post("", response_model=AssetResponse, status_code=201)
async def upload(
    request: Request, response: Response, user: WriteOwner, session: Database
) -> AssetResponse:
    if request.headers.get("x-lifearchive-request") != "1":
        raise HTTPException(403, "Upload request rejected")
    mime = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if mime not in MIME_BY_FORMAT.values():
        raise HTTPException(422, "Unsupported image type")
    chunks = bytearray()
    async for chunk in request.stream():
        if len(chunks) + len(chunk) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Image exceeds the upload limit")
        chunks.extend(chunk)

    def store() -> tuple[AssetResponse, bool]:
        asset, created = create_asset(session, user.id, bytes(chunks), mime)
        return AssetResponse.model_validate(asset), created

    asset, created = await run_in_threadpool(store)
    response.status_code = 201 if created else 200
    return asset


@router.get("/{asset_id}")
def read(asset_id: UUID, user: Owner, session: Database) -> Response:
    asset = get_asset(session, user.id, asset_id)
    try:
        data = read_original(asset)
    except MediaStorageError:
        raise HTTPException(503, "Private media is unavailable") from None
    filename = f"{asset.id}.{EXTENSION_BY_MIME[asset.mime_type]}"
    return Response(
        data,
        media_type=asset.mime_type,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'inline; filename="{filename}"',
        },
    )
