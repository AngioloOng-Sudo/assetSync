"""Webhook endpoints for external event ingestion."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from backend.models.schemas import WebhookPayload
from backend.services.activity_logger import log_activity
from backend.services.autosync_engine import process_webhook
from backend.services.settings_manager import get_setting
from backend.utils.security import sanitize_payload, validate_webhook_secret

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/kaseya")
def kaseya_webhook(
    payload: WebhookPayload,
    x_webhook_secret: str | None = Header(default=None),
) -> dict:
    expected_secret = get_setting("WEBHOOK_SHARED_SECRET")
    if not validate_webhook_secret(x_webhook_secret, expected_secret):
        raise HTTPException(status_code=401, detail="invalid_webhook_secret")

    sanitized = sanitize_payload(payload.model_dump())
    result = process_webhook(sanitized)
    log_activity(
        level="info",
        category="webhook",
        message="Kaseya webhook received.",
        details={"event_type": sanitized.get("event_type"), "identifier": sanitized.get("identifier")},
    )
    return result

