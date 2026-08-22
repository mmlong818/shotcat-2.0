from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AssetReferenceCreate(BaseModel):
    entity_type: Literal["actor", "character", "scene", "prop", "costume"]
    entity_id: str = Field(min_length=1, max_length=64)
    image_id: int | None = None
    file_id: str = Field(min_length=1, max_length=64)
    display_name: str | None = Field(default=None, max_length=255)
    source: Literal["generated", "upload"] = "generated"
    adopt: bool = False
    lock: bool = False


class AssetReferenceUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    is_adopted: bool | None = None
    is_locked: bool | None = None


class AssetReferenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    entity_type: str
    entity_id: str
    image_id: int | None
    file_id: str
    display_name: str
    version: int
    source: str
    is_adopted: bool
    is_locked: bool
    created_at: datetime
    updated_at: datetime
