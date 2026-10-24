"""Password hashing and opaque session primitives; no persistent plaintext secrets."""

import hashlib
import hmac
import re
import secrets
from functools import lru_cache

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

SESSION_COOKIE = "life_archive_session"
COOKIE_PATH = "/api/v1"
SESSION_MAX_AGE = 7 * 24 * 60 * 60
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}\Z")


@lru_cache
def password_hasher() -> PasswordHasher:
    return PasswordHasher(
        time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16, type=Type.ID
    )


def hash_password(password: str) -> str:
    return password_hasher().hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher().verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


@lru_cache
def dummy_password_hash() -> str:
    # An absent owner still takes a password verification path, without a fixed secret.
    return hash_password(secrets.token_urlsafe(32))


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def valid_session_token(token: str | None) -> bool:
    return token is not None and _TOKEN_PATTERN.fullmatch(token) is not None


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def csrf_token(session_token: str) -> str:
    # The session secret is the HMAC key; the database digest cannot recreate it.
    return hmac.new(
        session_token.encode("ascii"), b"LifeArchive csrf-token v1", hashlib.sha256
    ).hexdigest()


def valid_csrf_token(session_token: str, supplied: str | None) -> bool:
    return (
        supplied is not None
        and re.fullmatch(r"[0-9a-f]{64}", supplied) is not None
        and hmac.compare_digest(csrf_token(session_token), supplied)
    )
