from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, update

from life_archive.auth.dependencies import (
    DbSession,
    require_csrf,
    require_login_request,
    require_user,
)
from life_archive.auth.models import AuthSession, User
from life_archive.auth.schemas import (
    AuthResponse,
    LoginInput,
    PasswordChangeInput,
    SessionRevokeInput,
    UserResponse,
)
from life_archive.auth.security import (
    COOKIE_PATH,
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    csrf_token,
    token_digest,
)
from life_archive.auth.service import (
    LoginRateLimited,
    authenticate,
    consume_login_attempt,
    create_session,
    rotate_account_session,
)
from life_archive.settings import get_auth_settings

router = APIRouter(prefix="/auth", tags=["auth"])


def _session_response(
    response: Response, user: User, token: str, expires_at: datetime
) -> AuthResponse:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_MAX_AGE,
        expires=expires_at,
        path=COOKIE_PATH,
        secure=get_auth_settings().cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    return AuthResponse(user=UserResponse.model_validate(user), csrf_token=csrf_token(token))


def _rate_limited(error: LoginRateLimited) -> HTTPException:
    return HTTPException(
        429,
        "Too many login attempts; try again later",
        headers={"Retry-After": str(error.retry_after), "Cache-Control": "no-store"},
    )


@router.post("/login", response_model=AuthResponse, dependencies=[Depends(require_login_request)])
def login(body: LoginInput, request: Request, response: Response, db: DbSession) -> AuthResponse:
    try:
        consume_login_attempt(db)
    except LoginRateLimited as error:
        raise _rate_limited(error) from None
    try:
        user = authenticate(db, body.username, body.password.get_secret_value())
        if user is None:
            raise HTTPException(401, "Invalid credentials", headers={"Cache-Control": "no-store"})
        token, expires_at = create_session(db, user, request.cookies.get(SESSION_COOKIE))
        return _session_response(response, user, token, expires_at)
    except Exception:
        db.rollback()
        raise


@router.post(
    "/password", response_model=AuthResponse, dependencies=[Depends(require_login_request)]
)
def change_password(
    body: PasswordChangeInput,
    request: Request,
    response: Response,
    user: Annotated[User, Depends(require_csrf)],
    db: DbSession,
) -> AuthResponse:
    try:
        current, token, expires_at = rotate_account_session(
            db,
            user.id,
            request.cookies[SESSION_COOKIE],
            body.current_password.get_secret_value(),
            body.new_password.get_secret_value(),
        )
    except LoginRateLimited as error:
        raise _rate_limited(error) from None
    return _session_response(response, current, token, expires_at)


@router.post(
    "/sessions/revoke", response_model=AuthResponse, dependencies=[Depends(require_login_request)]
)
def revoke_sessions(
    body: SessionRevokeInput,
    request: Request,
    response: Response,
    user: Annotated[User, Depends(require_csrf)],
    db: DbSession,
) -> AuthResponse:
    try:
        current, token, expires_at = rotate_account_session(
            db, user.id, request.cookies[SESSION_COOKIE], body.current_password.get_secret_value()
        )
    except LoginRateLimited as error:
        raise _rate_limited(error) from None
    return _session_response(response, current, token, expires_at)


@router.get("/me", response_model=AuthResponse)
def me(
    request: Request, response: Response, user: Annotated[User, Depends(require_user)]
) -> AuthResponse:
    response.headers["Cache-Control"] = "no-store"
    return AuthResponse(
        user=UserResponse.model_validate(user),
        csrf_token=csrf_token(request.cookies[SESSION_COOKIE]),
    )


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    user: Annotated[User, Depends(require_csrf)],
    db: DbSession,
) -> None:
    db.execute(
        update(AuthSession)
        .where(
            AuthSession.token_hash == token_digest(request.cookies[SESSION_COOKIE]),
            AuthSession.user_id == user.id,
        )
        .values(revoked_at=func.now())
    )
    db.commit()
    response.delete_cookie(
        SESSION_COOKIE,
        path=COOKIE_PATH,
        secure=get_auth_settings().cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
