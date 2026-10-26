"""Public immutable metadata; storage paths are never exposed in API snapshots."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    mime_type: Literal["image/jpeg", "image/png", "image/webp"]
    byte_size: int = Field(gt=0, le=5 * 1024 * 1024)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    width: int = Field(gt=0, le=20_000)
    height: int = Field(gt=0, le=20_000)
    created_at: AwareDatetime
