from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from life_archive.auth.models import AuthSession, User
from life_archive.auth.security import (
    SESSION_COOKIE,
    token_digest,
    valid_csrf_token,
    valid_session_token,
)
from life_archive.db import get_db_session
from life_archive.settings import get_auth_settings

DbSession = Annotated[Session, Depends(get_db_session)]


def unauthorized() -> HTTPException:
    return HTTPException(401, "Authentication required", headers={"Cache-Control": "no-store"})


def require_trusted_origin(request: Request) -> None:
    origins = request.headers.getlist("origin")
    if len(origins) != 1 or origins[0] not in get_auth_settings().trusted_origins:
        raise HTTPException(403, "Request origin rejected", headers={"Cache-Control": "no-store"})


def require_login_request(request: Request) -> None:
    require_trusted_origin(request)
    if request.headers.get("x-lifearchive-request") != "1":
        raise HTTPException(403, "Login request rejected", headers={"Cache-Control": "no-store"})
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise HTTPException(415, "JSON required", headers={"Cache-Control": "no-store"})


def require_session_token(request: Request) -> str:
    token = request.cookies.get(SESSION_COOKIE)
    if not valid_session_token(token):
        raise unauthorized()
    assert token is not None
    return token


def require_user(token: Annotated[str, Depends(require_session_token)], db: DbSession) -> User:
    user = db.scalar(
        select(User)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(
            AuthSession.token_hash == token_digest(token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > func.now(),
        )
    )
    if user is None:
        raise unauthorized()
    return user


def require_csrf(request: Request, user: Annotated[User, Depends(require_user)]) -> User:
    require_trusted_origin(request)
    token = request.cookies.get(SESSION_COOKIE)
    if token is None or not valid_csrf_token(token, request.headers.get("x-csrf-token")):
        raise HTTPException(403, "CSRF validation failed", headers={"Cache-Control": "no-store"})
    return user
