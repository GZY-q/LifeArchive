from pathlib import Path

import pytest
from pydantic import ValidationError

from life_archive.settings import DatabaseSettings, Settings


def test_database_credentials_are_required_but_app_settings_are_independent() -> None:
    assert Settings().app_name == "LifeArchive"
    with pytest.raises(ValidationError, match="postgres_password"):
        DatabaseSettings()


@pytest.mark.parametrize(
    "password",
    ["", " " * 32, "short", "replace-with-a-long-random-password", "change-me-please-now"],
)
def test_placeholder_passwords_fail_without_printing_input(password: str) -> None:
    with pytest.raises(ValidationError) as error:
        DatabaseSettings(postgres_password=password)

    assert "input_value" not in str(error.value)
    if password:
        assert repr(password) not in str(error.value)


def test_special_characters_are_preserved_and_password_is_redacted() -> None:
    password = "test-only:@/%#?strong-secret"
    settings = DatabaseSettings(postgres_password=password)

    assert settings.url.password == password
    assert settings.url.drivername == "postgresql+psycopg"
    assert password not in str(settings)
    assert password not in settings.model_dump_json()
    assert password not in str(settings.url)


def test_env_overrides_dotenv_and_unrelated_compose_values_are_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "POSTGRES_PASSWORD=test-only-dotenv-secret\n"
        "POSTGRES_HOST=file-host\n"
        "WEB_PORT=8080\n"
        "LIFEARCHIVE_LOG_LEVEL=WARNING\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("POSTGRES_HOST", "environment-host")

    assert DatabaseSettings(_env_file=env_file).postgres_host == "environment-host"
    assert Settings(_env_file=env_file).log_level == "WARNING"


def test_invalid_port_is_rejected() -> None:
    with pytest.raises(ValidationError, match="postgres_port"):
        DatabaseSettings(postgres_password="test-only-strong-secret", postgres_port=65536)
