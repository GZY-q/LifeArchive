"""Bounded, authenticated browser exports; no server-side export files or jobs."""

from io import BytesIO
from threading import BoundedSemaphore
from time import monotonic
from zipfile import BadZipFile

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, StrictBool
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from starlette.types import Receive, Scope, Send

from life_archive.auth.dependencies import require_login_request
from life_archive.journal.export import (
    ExportError,
    ExportLimitError,
    ExportLimits,
    write_journal_archive,
)
from life_archive.journal.router import Database, WriteOwner

router = APIRouter(prefix="/journal-export", tags=["journal"])
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
EXPORT_SECONDS = 30
LIMITS = ExportLimits()
_slot = BoundedSemaphore(1)


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_deleted: StrictBool = False


class ExportTimeoutError(ExportError):
    """The cooperative generation/verification deadline was exceeded."""


class ExportBuffer(BytesIO):
    def __init__(self) -> None:
        super().__init__()
        self.deadline = monotonic() + EXPORT_SECONDS

    def check_time(self) -> None:
        if monotonic() >= self.deadline:
            raise ExportTimeoutError("Browser export timed out")

    def write(self, data: bytes) -> int:
        self.check_time()
        if self.tell() + len(data) > MAX_ARCHIVE_BYTES:
            raise ExportLimitError("Browser export size exceeded")
        return super().write(data)

    def read(self, size: int = -1) -> bytes:
        self.check_time()
        return super().read(size)


class ExportResponse(Response):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            # Hold the slot through delivery, releasing even if sending disconnects.
            _slot.release()


@router.post("", dependencies=[Depends(require_login_request)])
def download(payload: ExportRequest, user: WriteOwner, session: Database) -> Response:
    if not _slot.acquire(blocking=False):
        raise HTTPException(429, {"code": "export_busy"}, headers={"Retry-After": "5"})
    response = None
    try:
        engine = session.get_bind()
        if not isinstance(engine, Engine):
            raise ExportError("Export database is unavailable")
        with ExportBuffer() as file:
            write_journal_archive(
                engine,
                file,
                include_deleted=payload.include_deleted,
                owner_id=user.id,
                limits=LIMITS,
            )
            file.check_time()
            data = file.getvalue()
        response = ExportResponse(
            data,
            media_type="application/zip",
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": 'attachment; filename="life-archive-journal.zip"',
                "X-Content-Type-Options": "nosniff",
            },
        )
        return response
    except ExportLimitError:
        raise HTTPException(413, {"code": "export_too_large"}) from None
    except ExportTimeoutError:
        raise HTTPException(504, {"code": "export_timeout"}) from None
    except DBAPIError as error:
        if getattr(error.orig, "sqlstate", None) == "57014":
            raise HTTPException(504, {"code": "export_timeout"}) from None
        raise HTTPException(503, {"code": "export_unavailable"}) from None
    except (ExportError, SQLAlchemyError, OSError, BadZipFile):
        raise HTTPException(503, {"code": "export_unavailable"}) from None
    finally:
        if response is None:
            _slot.release()
