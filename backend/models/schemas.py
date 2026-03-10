"""Pydantic schema definitions for API contracts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class TransferRequest(BaseModel):
    """Transfer request payload."""

    identifiers: list[str] | None = Field(
        default=None, description="Optional specific Kaseya identifiers to transfer."
    )
    dry_run: bool = False

    @field_validator("identifiers")
    @classmethod
    def normalize_identifiers(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        return [identifier.strip() for identifier in value if identifier and identifier.strip()]


class AssetDetailResponse(BaseModel):
    """Detailed asset view payload for dashboard slide-over panel."""

    identifier: str
    kaseya: dict[str, Any] | None = None
    revnue_match: dict[str, Any] | None = None
    sync_events: list[dict[str, Any]] = Field(default_factory=list)


class DeleteAssetRequest(BaseModel):
    """Delete request for a Revnue asset."""

    identifier: str


class EnvUpdateRequest(BaseModel):
    """Payload for updating .env values."""

    values: dict[str, str]


class WebhookPayload(BaseModel):
    """Webhook payload from Kaseya."""

    event_type: str = Field(default="asset.updated")
    identifier: str | None = None
    asset: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConnectivityCheckRequest(BaseModel):
    """Optional list of connectivity targets to test."""

    targets: list[str] | None = None


class SupportTicketRequest(BaseModel):
    """Ticket creation payload."""

    title: str
    description: str
    priority: str = Field(default="normal")
    diagnostics: dict[str, Any] | None = None


class AutosyncStateRequest(BaseModel):
    """Autosync state update payload."""

    enabled: bool


class MarkReadRequest(BaseModel):
    """Mark-read payload for activity center channels."""

    channels: list[str] | None = None


class AuthLoginRequest(BaseModel):
    """Login payload for dashboard authentication."""

    password: str = Field(default="", min_length=1, max_length=256)


class SyncRunRequest(BaseModel):
    """Manual sync cycle trigger payload."""

    force: bool = Field(
        default=True,
        description="Run even when AUTOSYNC_ENABLED=false.",
    )
    process_limit: int = Field(default=50, ge=1, le=500)


class TokenRotateRequest(BaseModel):
    """Rotate one token/secret in .env without service restart."""

    key: str = Field(min_length=2, max_length=128)
    value: str = Field(min_length=1, max_length=4096)
    keep_previous: bool = True


class MappingConfigUpdateRequest(BaseModel):
    """Payload for updating external field mapping configuration."""

    config: dict[str, Any]
