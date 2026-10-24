import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateSchema

from life_archive import settings as settings_module
from life_archive.db import get_db_session
from life_archive.settings import (
    EnvironmentSettings,
    get_database_settings,
    get_settings,
)


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Unit tests never read a developer's .env file or database credentials."""
    for name in tuple(os.environ):
        if name.startswith(("POSTGRES_", "LIFEARCHIVE_")):
            monkeypatch.delenv(name, raising=False)
    for settings_class in EnvironmentSettings.__subclasses__():
        monkeypatch.setitem(settings_class.model_config, "env_file", None)
    get_settings.cache_clear()
    get_database_settings.cache_clear()
    auth_settings = getattr(settings_module, "get_auth_settings", None)
    if auth_settings is not None:
        auth_settings.cache_clear()
    yield
    get_settings.cache_clear()
    get_database_settings.cache_clear()
    if auth_settings is not None:
        auth_settings.cache_clear()


@pytest.fixture
def pg_engine() -> Iterator[Engine]:
    """Each integration test migrates a fresh schema in an explicit test database."""
    password = os.environ.get("TEST_POSTGRES_PASSWORD")
    if not password:
        pytest.skip("Set TEST_POSTGRES_* to execute the real PostgreSQL integration tests")
    url = URL.create(
        "postgresql+psycopg",
        username=os.environ.get("TEST_POSTGRES_USER", "life_archive_tests"),
        password=password,
        host=os.environ.get("TEST_POSTGRES_HOST", "127.0.0.1"),
        port=int(os.environ.get("TEST_POSTGRES_PORT", "25432")),
        database=os.environ.get("TEST_POSTGRES_DB", "life_archive_tests"),
    )
    schema = f"m1_test_{uuid4().hex}"
    admin = create_engine(url, poolclass=NullPool, hide_parameters=True)
    with admin.begin() as connection:
        connection.execute(CreateSchema(schema))
    engine = create_engine(
        url,
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={"options": f"-c search_path={schema} -c timezone=UTC"},
    )
    try:
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()
        admin.dispose()
        # The isolated test schema is retained for inspection; no user data is reset.


@pytest.fixture
def session_factory(pg_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=pg_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        yield session


@pytest.fixture
def db_client(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    from life_archive.main import create_app

    monkeypatch.setenv("LIFEARCHIVE_COOKIE_SECURE", "false")
    auth_settings = getattr(settings_module, "get_auth_settings", None)
    if auth_settings is not None:
        auth_settings.cache_clear()
    app = create_app()

    def override_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        yield client
