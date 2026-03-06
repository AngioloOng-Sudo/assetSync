"""Outbound notification integrations."""

from __future__ import annotations

from typing import Any

import requests

from backend.services.settings_manager import get_setting


def send_outbound_webhook(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Send outbound notification webhook if configured."""
    webhook_url = get_setting("OUTBOUND_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return {"sent": False, "reason": "not_configured"}
    timeout_raw = get_setting("OUTBOUND_WEBHOOK_TIMEOUT_SECONDS", "8").strip() or "8"
    try:
        timeout_seconds = max(1, int(timeout_raw))
    except ValueError:
        timeout_seconds = 8

    body = {"event_type": event_type, "payload": payload}
    try:
        response = requests.post(webhook_url, json=body, timeout=timeout_seconds)
        return {
            "sent": response.ok,
            "status_code": response.status_code,
            "target": webhook_url,
        }
    except Exception as exc:  # pragma: no cover - network failure path
        return {"sent": False, "target": webhook_url, "error": str(exc)}
