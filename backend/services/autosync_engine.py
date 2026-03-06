"""Autosync engine with queue, webhook processor, reconciliation, and retry logic."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.models.db import (
    claim_queued_events,
    event_metrics,
    fetch_events,
    insert_sync_event,
    update_sync_event,
)
from backend.services.activity_logger import get_state, log_activity, set_status
from backend.services.kaseya_client import fetch_kaseya_assets
from backend.services.matching import compare_assets
from backend.services.revnue_client import fetch_all_revnue_assets
from backend.services.transfer_engine import delete_revnue_asset, transfer_kaseya_assets_to_revnue

DEFAULT_MAX_RETRIES = 3
VALID_WINDOWS = {"15m", "1h", "24h", "7d"}


def enqueue_event(
    *,
    event_type: str,
    identifier: str | None,
    payload: dict[str, Any],
) -> int:
    """Add a sync event to the queue."""
    event_id = insert_sync_event(event_type, identifier, payload)
    log_activity(
        level="info",
        category="autosync",
        message=f"Event queued: {event_type}",
        details={"event_id": event_id, "identifier": identifier},
    )
    return event_id


def set_autosync_enabled(enabled: bool) -> dict[str, Any]:
    """Set autosync status in activity state."""
    set_status("autosync_enabled", enabled)
    log_activity(
        level="info",
        category="autosync",
        message=f"Autosync {'enabled' if enabled else 'disabled'}.",
    )
    return {"enabled": enabled}


def get_autosync_enabled() -> bool:
    """Return current autosync enabled state."""
    return bool(get_state().get("status", {}).get("autosync_enabled", False))


def process_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    """Process Kaseya webhook payload and enqueue for worker."""
    parsed = parse_kaseya_webhook_payload(payload)
    identifier = parsed.get("identifier")
    event_type = parsed.get("event_type", "asset.updated")
    data = parsed.get("payload", payload)
    event_id = enqueue_event(event_type=event_type, identifier=identifier, payload=payload)
    return {"queued": True, "event_id": event_id, "parsed": {"event_type": event_type, "identifier": identifier, "payload": data}}


def parse_kaseya_webhook_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize webhook payload from common Kaseya webhook shapes."""
    event_type = (
        payload.get("event_type")
        or payload.get("eventType")
        or payload.get("type")
        or "asset.updated"
    )
    identifier = payload.get("identifier")
    asset = payload.get("asset")

    if not identifier and isinstance(asset, dict):
        identifier = asset.get("Identifier") or asset.get("identifier")

    if not identifier:
        identifier = (
            payload.get("Identifier")
            or payload.get("serial_number")
            or payload.get("asset_tag")
        )

    return {
        "event_type": str(event_type),
        "identifier": str(identifier).strip() if identifier else None,
        "payload": payload,
    }


def _process_event_row(event: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(event["payload_json"])
    identifier = event.get("identifier")
    event_type = event.get("event_type", "")

    if event_type == "asset.deleted" and identifier:
        delete_outcome = delete_revnue_asset(identifier)
        success = delete_outcome.get("status") == "deleted"
        return {
            "status": "success" if success else "failed",
            "details": delete_outcome,
            "error": None if success else "delete_failed",
        }

    transfer_identifiers = [identifier] if identifier else None
    if payload.get("asset") and payload["asset"].get("Identifier"):
        transfer_identifiers = [payload["asset"]["Identifier"]]

    transfer_result = transfer_kaseya_assets_to_revnue(transfer_identifiers)
    summary = transfer_result["summary"]

    if summary["failed"] > 0:
        status = "failed"
    elif summary["partial"] > 0:
        status = "partial"
    else:
        status = "success"

    return {"status": status, "details": transfer_result, "error": None}


def process_pending_events(limit: int = 25) -> dict[str, Any]:
    """Process queued events using transfer and delete logic."""
    if not get_autosync_enabled():
        return {"processed": 0, "message": "autosync_disabled"}

    claimed = claim_queued_events(limit=limit)
    processed = 0
    failed = 0
    partial = 0
    success = 0

    for event in claimed:
        processed += 1
        event_id = int(event["id"])
        retries = int(event.get("retries", 0))
        try:
            result = _process_event_row(event)
            status = result["status"]
            if status == "success":
                success += 1
            elif status == "partial":
                partial += 1
            else:
                failed += 1
            update_sync_event(event_id, status=status, retries=retries, last_error=result.get("error"))
        except Exception as exc:  # pragma: no cover - defensive path
            failed += 1
            update_sync_event(
                event_id,
                status="failed",
                retries=retries + 1,
                last_error=str(exc),
            )
            log_activity(
                level="error",
                category="autosync",
                message=f"Event {event_id} processing failed.",
                details={"error": str(exc), "event": event},
            )

    set_status("last_sync_run_at", get_state().get("last_updated_at"))
    set_status("worker_heartbeat_at", get_state().get("last_updated_at"))
    return {
        "processed": processed,
        "success": success,
        "partial": partial,
        "failed": failed,
    }


def retry_failed_events(max_retries: int = DEFAULT_MAX_RETRIES) -> dict[str, Any]:
    """Re-queue failed events if retries remain."""
    failed_events = fetch_events(status="failed", limit=200)
    requeued = 0
    for event in failed_events:
        retries = int(event.get("retries", 0))
        if retries < max_retries:
            update_sync_event(int(event["id"]), status="queued", retries=retries + 1)
            requeued += 1
    if requeued:
        log_activity(
            level="info",
            category="autosync",
            message=f"Retry scheduler re-queued {requeued} failed events.",
        )
    return {"requeued": requeued}


def run_reconciliation() -> dict[str, Any]:
    """Queue reconciliation events for assets missing in Revnue."""
    kaseya_assets = fetch_kaseya_assets(top=100_000, skip=0)
    revnue_assets = fetch_all_revnue_assets(company=None)
    comparison = compare_assets(kaseya_assets, revnue_assets)
    queued = 0
    for item in comparison:
        if item["match_status"] == "missing_in_revnue":
            enqueue_event(
                event_type="asset.reconcile",
                identifier=item["identifier"],
                payload={"reason": "missing_in_revnue", "identifier": item["identifier"]},
            )
            queued += 1
    if queued:
        log_activity(
            level="info",
            category="autosync",
            message=f"Reconciliation queued {queued} events.",
        )
    set_status("last_reconcile_at", get_state().get("last_updated_at"))
    return {"queued": queued}


def _health_state(metrics: dict[str, int]) -> str:
    queued = metrics.get("queued", 0)
    failed = metrics.get("failed", 0)
    partial = metrics.get("partial", 0)
    if failed >= 10 or queued >= 100:
        return "critical"
    if failed > 0 or partial > 0 or queued >= 20:
        return "degraded"
    return "healthy"


def _window_to_start(window: str) -> datetime:
    now = datetime.now(timezone.utc)
    if window == "15m":
        return now - timedelta(minutes=15)
    if window == "1h":
        return now - timedelta(hours=1)
    if window == "24h":
        return now - timedelta(hours=24)
    return now - timedelta(days=7)


def _events_within_window(events: list[dict[str, Any]], window: str) -> list[dict[str, Any]]:
    if window not in VALID_WINDOWS:
        window = "24h"
    start_time = _window_to_start(window)
    filtered: list[dict[str, Any]] = []
    for event in events:
        created_at = event.get("created_at")
        if not created_at:
            continue
        try:
            event_dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        except ValueError:
            continue
        if event_dt >= start_time:
            filtered.append(event)
    return filtered


def get_sync_overview(window: str = "24h") -> dict[str, Any]:
    """Return KPI overview for the requested time window."""
    if window not in VALID_WINDOWS:
        window = "24h"
    events = fetch_events(limit=5000)
    scoped = _events_within_window(events, window)
    total = len(scoped)
    success = len([event for event in scoped if event.get("status") == "success"])
    failed = len([event for event in scoped if event.get("status") == "failed"])
    partial = len([event for event in scoped if event.get("status") == "partial"])
    success_rate = round((success / total * 100.0), 2) if total else 0.0
    return {
        "window": window,
        "totals": {"events": total, "success": success, "failed": failed, "partial": partial},
        "success_rate": success_rate,
        "health_state": _health_state(event_metrics()),
    }


def get_sync_status() -> dict[str, Any]:
    """Return health and queue status for sync-status page."""
    metrics = event_metrics()
    total_processed = metrics.get("success", 0) + metrics.get("failed", 0) + metrics.get("partial", 0)
    successful = metrics.get("success", 0)
    success_rate = (successful / total_processed * 100.0) if total_processed else 0.0
    status = get_state().get("status", {})
    return {
        "autosync_enabled": get_autosync_enabled(),
        "queue_metrics": metrics,
        "health_state": _health_state(metrics),
        "worker_heartbeat_at": status.get("worker_heartbeat_at"),
        "last_reconcile_at": status.get("last_reconcile_at"),
        "success_rate": round(success_rate, 2),
        "recent_events": fetch_events(limit=20),
        "failed_events": fetch_events(status="failed", limit=20),
        "partial_events": fetch_events(status="partial", limit=20),
    }
