from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints, field_validator

Username = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64, pattern=r"^\S+$")
]


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    username: Username
    password: SecretStr = Field(min_length=1, max_length=1024)


class SessionRevokeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    current_password: SecretStr = Field(min_length=1, max_length=1024)

    @field_validator("current_password")
    @classmethod
    def require_utf8_current_password(cls, value: SecretStr) -> SecretStr:
        try:
            value.get_secret_value().encode("utf-8")
        except UnicodeError:
            raise ValueError("Invalid password encoding") from None
        return value


class PasswordChangeInput(SessionRevokeInput):
    new_password: SecretStr = Field(min_length=15, max_length=1024)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: SecretStr) -> SecretStr:
        plain = value.get_secret_value()
        if not plain.strip() or "\x00" in plain:
            raise ValueError("Invalid new password")
        try:
            plain.encode("utf-8")
        except UnicodeError:
            raise ValueError("Invalid password encoding") from None
        return value


class OwnerInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    username: Username
    password: SecretStr = Field(min_length=15, max_length=1024)
    timezone: str = Field(min_length=1, max_length=64)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("Timezone must be a valid IANA name") from error
        return value

    @field_validator("password")
    @classmethod
    def reject_blank_password(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("Password cannot be blank")
        return value


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    timezone: str


class AuthResponse(BaseModel):
    user: UserResponse
    csrf_token: str
