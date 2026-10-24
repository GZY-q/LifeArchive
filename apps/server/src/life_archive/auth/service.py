"""Explicit transactions for owner setup, globally bounded login attempts and sessions."""

import hmac
import math
from datetime import datetime, timedelta

from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from life_archive.auth.models import AuthSession, LoginThrottle, User
from life_archive.auth.schemas import OwnerInput
from life_archive.auth.security import (
    SESSION_MAX_AGE,
    dummy_password_hash,
    hash_password,
    new_session_token,
    password_hasher,
    token_digest,
    valid_session_token,
    verify_password,
)

LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 300


class OwnerSetupError(ValueError):
    pass


class LoginRateLimited(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after


def create_owner(db: Session, username: str, password: str, timezone: str) -> User:
    try:
        values = OwnerInput(username=username, password=password, timezone=timezone)
    except ValidationError as error:
        raise OwnerSetupError(
            "Invalid owner configuration: username, IANA timezone, "
            "and 15–1024 character password required"
        ) from error
    if db.scalar(select(User.id).limit(1)) is not None:
        raise OwnerSetupError("An owner already exists; no changes were made")
    user = User(
        username=values.username,
        password_hash=hash_password(values.password.get_secret_value()),
        timezone=values.timezone,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as error:
        # The singleton UNIQUE + CHECK constraints also reject racing initializations.
        db.rollback()
        raise OwnerSetupError("An owner already exists; no changes were made") from error
    return user


def consume_login_attempt(db: Session) -> None:
    """Reserve one attempt before hashing, shared by all workers/usernames/IPs."""
    db.execute(
        insert(LoginThrottle)
        .values(id=1, window_started_at=func.clock_timestamp(), attempts=0)
        .on_conflict_do_nothing(index_elements=[LoginThrottle.id])
    )
    throttle = db.scalar(select(LoginThrottle).where(LoginThrottle.id == 1).with_for_update())
    assert throttle is not None
    now = db.scalar(select(func.clock_timestamp()))
    assert isinstance(now, datetime)
    window_end = throttle.window_started_at + timedelta(seconds=LOGIN_WINDOW_SECONDS)
    if now >= window_end:
        throttle.window_started_at = now
        throttle.attempts = 0
    elif throttle.attempts >= LOGIN_ATTEMPTS:
        retry_after = max(1, math.ceil((window_end - now).total_seconds()))
        db.rollback()
        raise LoginRateLimited(retry_after)
    throttle.attempts += 1
    # Persist before verification: failures/crashes cannot roll back the attempt.
    db.commit()


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.scalar(select(User).limit(1))
    digest = user.password_hash if user is not None else dummy_password_hash()
    password_matches = verify_password(digest, password)
    username_matches = user is not None and hmac.compare_digest(
        user.username.encode("utf-8"), username.encode("utf-8")
    )
    if not username_matches or not password_matches:
        return None
    assert user is not None
    if password_hasher().check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    return user


def create_session(db: Session, user: User, old_token: str | None) -> tuple[str, datetime]:
    now = db.scalar(select(func.clock_timestamp()))
    assert isinstance(now, datetime)
    expires_at = now + timedelta(seconds=SESSION_MAX_AGE)
    if valid_session_token(old_token):
        assert old_token is not None
        db.execute(
            update(AuthSession)
            .where(
                AuthSession.token_hash == token_digest(old_token), AuthSession.user_id == user.id
            )
            .values(revoked_at=now)
        )
    token = new_session_token()
    db.add(
        AuthSession(
            token_hash=token_digest(token), user_id=user.id, created_at=now, expires_at=expires_at
        )
    )
    db.commit()
    return token, expires_at
