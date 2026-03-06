"""Webhook endpoints for external event ingestion."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from backend.models.schemas import WebhookPayload
from backend.services.activity_logger import log_activity
from backend.services.autosync_engine import process_webhook
from backend.services.settings_manager import get_setting
from backend.utils.security import (
    sanitize_payload,
    validate_webhook_hmac_signature,
    validate_webhook_secret,
)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/kaseya")
async def kaseya_webhook(
    request: Request,
    payload: WebhookPayload,
    x_webhook_secret: str | None = Header(default=None),
    x_webhook_signature: str | None = Header(default=None),
) -> dict:
    expected_secret = get_setting("WEBHOOK_SHARED_SECRET")
    if expected_secret:
        body_bytes = await request.body()
        valid_secret = validate_webhook_secret(x_webhook_secret, expected_secret)
        valid_signature = validate_webhook_hmac_signature(
            body_bytes,
            x_webhook_signature,
            expected_secret,
        )
        if not (valid_secret or valid_signature):
            raise HTTPException(status_code=401, detail="invalid_webhook_signature")

    sanitized = sanitize_payload(payload.model_dump())
    result = process_webhook(sanitized)
    log_activity(
        level="info",
        category="webhook",
        message="Kaseya webhook received.",
        details={"event_type": sanitized.get("event_type"), "identifier": sanitized.get("identifier")},
    )
    return result
