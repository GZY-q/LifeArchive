import pytest
from pydantic import ValidationError

from life_archive.auth.schemas import OwnerInput
from life_archive.auth.security import (
    csrf_token,
    hash_password,
    new_session_token,
    token_digest,
    valid_csrf_token,
    valid_session_token,
    verify_password,
)
from life_archive.settings import AuthSettings


def test_password_round_trip_preserves_unicode_and_uses_argon2id() -> None:
    password = "仅供测试的密码 with whitespace "
    encoded = hash_password(password)
    assert encoded.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert password not in encoded
    assert verify_password(encoded, password)
    assert not verify_password(encoded, password.strip())
    assert not verify_password("invalid-hash", password)


def test_session_and_csrf_tokens_are_bound_but_not_interchangeable() -> None:
    first, second = new_session_token(), new_session_token()
    assert valid_session_token(first)
    assert len(token_digest(first)) == 64
    assert first not in token_digest(first)
    assert valid_csrf_token(first, csrf_token(first))
    assert not valid_csrf_token(second, csrf_token(first))
    assert not valid_csrf_token(first, "秘密" * 32)
    assert not valid_csrf_token(first, first)
    assert not valid_session_token("short")
    assert not valid_session_token(None)


def test_secure_cookies_are_default_and_external_plain_http_is_rejected() -> None:
    assert AuthSettings().cookie_secure is True
    with pytest.raises(ValidationError):
        AuthSettings(trusted_origins=("http://archive.example",))
    with pytest.raises(ValidationError):
        AuthSettings(cookie_secure=False, trusted_origins=("https://archive.example",))
    assert AuthSettings(cookie_secure=False).cookie_secure is False


@pytest.mark.parametrize(
    "origin",
    [
        "https://*.example",
        "https://a.example/path",
        "https://a.example/",
        "null",
        "https://a@b.example",
    ],
)
def test_trusted_origins_are_exact_origins(origin: str) -> None:
    with pytest.raises(ValidationError):
        AuthSettings(trusted_origins=(origin,))


def test_owner_timezone_and_password_are_validated_without_leaking_password() -> None:
    with pytest.raises(ValidationError) as error:
        OwnerInput(username="owner", password="private", timezone="not/a-timezone")
    assert "private" not in str(error.value)
    assert (
        OwnerInput(
            username="主人", password="test-only-owner-passphrase", timezone="Asia/Shanghai"
        ).timezone
        == "Asia/Shanghai"
    )
