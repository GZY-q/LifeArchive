"""Validated configuration; database credentials are only needed by DB consumers."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class EnvironmentSettings(BaseSettings):
    # Local commands run from apps/server; containers receive environment variables.
    model_config = SettingsConfigDict(
        env_file="../../.env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
        frozen=True,
    )


class Settings(EnvironmentSettings):
    model_config = SettingsConfigDict(env_prefix="LIFEARCHIVE_")

    app_name: str = "LifeArchive"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


class DatabaseSettings(EnvironmentSettings):
    postgres_host: str = "postgres"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_user: str = "life_archive"
    postgres_password: SecretStr
    postgres_db: str = "life_archive"

    @field_validator("postgres_host", "postgres_user", "postgres_db")
    @classmethod
    def reject_empty_identifiers(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("PostgreSQL host, user and database must not be empty")
        return value

    @field_validator("postgres_password")
    @classmethod
    def require_configured_password(cls, value: SecretStr) -> SecretStr:
        password = value.get_secret_value()
        normalized = password.strip().lower()
        if (
            len(password) < 16
            or not normalized
            or normalized.startswith(("replace-", "replace_", "change-", "change_"))
            or normalized in {"changeme", "password", "your-password-here"}
        ):
            raise ValueError("POSTGRES_PASSWORD must be a non-placeholder secret of 16+ characters")
        return value

    @property
    def url(self) -> URL:
        """Build a URL without parsing password punctuation or exposing it in repr."""
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_database_settings() -> DatabaseSettings:
    return DatabaseSettings()
