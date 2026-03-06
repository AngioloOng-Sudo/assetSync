"""External API response models for Kaseya and Revnue payload validation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class KaseyaAssetModel(BaseModel):
    """Expected Kaseya asset payload shape (per asset)."""

    model_config = ConfigDict(extra="allow")

    Identifier: str = Field(min_length=1)
    Name: str | None = None
    Manufacturer: str | None = None
    Model: str | None = None
    ModifiedDate: str | None = None
    AssetInfo: list[dict[str, Any]] | None = None
    assetinfo: list[dict[str, Any]] | None = None
    detail_source: str | None = None


class RevnueAssetModel(BaseModel):
    """Expected Revnue asset payload shape (per asset)."""

    model_config = ConfigDict(extra="allow")

    id: int | str | None = None
    company: str | int | None = None
    serial_number: str | None = None
    asset_tag: str | None = None
    name: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    template_fields: list[dict[str, Any]] | None = None
