"""HTTP entry point. Importing or starting the API never starts a scheduler."""

from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel

from life_archive.auth.errors import validation_exception_handler
from life_archive.auth.router import router as auth_router
from life_archive.journal.export_router import router as export_router
from life_archive.journal.router import router as journal_router
from life_archive.journal.tag_router import router as tag_router
from life_archive.journal.trash_router import router as trash_router
from life_archive.media.router import router as media_router
from life_archive.search.router import router as search_router
from life_archive.settings import get_settings
from life_archive.timeline.router import router as timeline_router


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


def create_app() -> FastAPI:
    app = FastAPI(
        title=get_settings().app_name,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(journal_router, prefix="/api/v1")
    app.include_router(export_router, prefix="/api/v1")
    app.include_router(tag_router, prefix="/api/v1")
    app.include_router(trash_router, prefix="/api/v1")
    app.include_router(media_router, prefix="/api/v1")
    app.include_router(timeline_router, prefix="/api/v1")
    app.include_router(search_router, prefix="/api/v1")

    @app.middleware("http")
    async def prevent_private_response_caching(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/v1/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        """Non-sensitive process liveness; does not assert database readiness."""
        return HealthResponse()

    return app


app = create_app()
