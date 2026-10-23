"""HTTP entry point. Importing or starting the API never starts a scheduler."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from life_archive.settings import get_settings


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


def create_app() -> FastAPI:
    app = FastAPI(
        title=get_settings().app_name,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/api/v1/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        """Non-sensitive process liveness; does not assert database readiness."""
        return HealthResponse()

    return app


app = create_app()
