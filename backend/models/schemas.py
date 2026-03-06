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
