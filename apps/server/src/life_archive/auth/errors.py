from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


async def validation_exception_handler(
    request: Request, error: RequestValidationError
) -> JSONResponse:
    """Never echo validation inputs, JSON keys, passwords, or journal text."""
    return JSONResponse(
        status_code=422,
        content={"detail": "Invalid request"},
        headers={"Cache-Control": "no-store"},
    )
