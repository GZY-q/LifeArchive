from collections.abc import Iterator

import pytest

from life_archive.settings import (
    EnvironmentSettings,
    get_database_settings,
    get_settings,
)


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Unit tests never read a developer's .env file or database credentials."""
    for name in (
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "LIFEARCHIVE_APP_NAME",
        "LIFEARCHIVE_LOG_LEVEL",
    ):
        monkeypatch.delenv(name, raising=False)
    for settings_class in EnvironmentSettings.__subclasses__():
        monkeypatch.setitem(settings_class.model_config, "env_file", None)
    get_settings.cache_clear()
    get_database_settings.cache_clear()
    yield
    get_settings.cache_clear()
    get_database_settings.cache_clear()
