"""Autosync engine with queue, webhook processor, reconciliation, and retry logic."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.models.db import (
    append_asset_event,
    claim_queued_events,
    dedup_metrics,
    event_metrics,
    fetch_sync_audit_runs,
    fetch_events,
    is_tombstoned,
    insert_sync_event,
    insert_sync_audit_run,
    register_event_fingerprint,
    upsert_tombstone,
    update_sync_event,
    utcnow_iso,
)
from backend.services.activity_logger import get_state, log_activity, set_status
from backend.services.matching import compare_assets
from backend.services.notifications import send_outbound_webhook
from backend.services.parallel_fetch import fetch_asset_snapshots_parallel
from backend.services.resilience import get_resilience_snapshot
from backend.services.schedule_windows import is_sync_window_open, schedule_status_snapshot
from backend.services.settings_manager import get_setting
from backend.services.transfer_engine import delete_revnue_asset, transfer_kaseya_assets_to_revnue

DEFAULT_MAX_RETRIES = 3
VALID_WINDOWS = {"15m", "1h", "24h", "7d"}


def _event_fingerprint(event_type: str, identifier: str | None, payload: dict[str, Any]) -> str:
    canonical = {
        "event_type": str(event_type or ""),
        "identifier": str(identifier or ""),
        "payload": payload,
    }
    encoded = json.dumps(canonical, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def enqueue_event(
    *,
    event_type: str,
    identifier: str | None,
    payload: dict[str, Any],
    deduplicate: bool = False,
    dedup_window_seconds: int = 600,
) -> int | None:
    """Add a sync event to the queue."""
    if deduplicate:
        accepted = register_event_fingerprint(
            _event_fingerprint(event_type, identifier, payload),
            ttl_seconds=dedup_window_seconds,
        )
        if not accepted:
            log_activity(
                level="info",
                category="autosync",
                message=f"Duplicate event ignored: {event_type}",
                details={"identifier": identifier, "deduplicated": True},
            )
            return None
    event_id = insert_sync_event(event_type, identifier, payload)
    log_activity(
        level="info",
        category="autosync",
        message=f"Event queued: {event_type}",
        details={"event_id": event_id, "identifier": identifier},
    )
    append_asset_event(
        event_type=f"sync.{event_type}",
        identifier=identifier,
        source="autosync_engine",
        payload={"event_id": event_id, "payload": payload},
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
    try:
        dedup_window = int(get_setting("EVENT_DEDUP_WINDOW_SECONDS", "600") or "600")
    except ValueError:
        dedup_window = 600
    event_id = enqueue_event(
        event_type=event_type,
        identifier=identifier,
        payload=payload,
        deduplicate=True,
        dedup_window_seconds=max(1, dedup_window),
    )
    return {
        "queued": event_id is not None,
        "event_id": event_id,
        "deduplicated": event_id is None,
        "parsed": {"event_type": event_type, "identifier": identifier, "payload": data},
    }


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
        upsert_tombstone(
            identifier,
            reason="webhook_delete",
            metadata={"event_id": event.get("id"), "event_type": event_type},
        )
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


def _compact_event_summary(event: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "event_id": int(event.get("id", 0)),
        "event_type": str(event.get("event_type", "")),
        "identifier": event.get("identifier"),
        "status": result.get("status", "unknown"),
    }
    details = result.get("details")
    if not isinstance(details, dict):
        return summary

    if summary["event_type"] == "asset.deleted":
        summary["action"] = "deleted" if details.get("status") == "deleted" else "not_found"
        summary["field_diffs"] = [{"field": "asset", "before": "present", "after": "deleted"}]
        return summary

    transfer_results = details.get("results")
    if isinstance(transfer_results, list) and transfer_results:
        first = transfer_results[0] if isinstance(transfer_results[0], dict) else {}
        summary["action"] = first.get("action")
        summary["field_diffs"] = first.get("field_diffs", [])
        summary["partial_reasons"] = first.get("partial_reasons", [])
    return summary


def process_pending_events(limit: int = 25, *, force: bool = False) -> dict[str, Any]:
    """Process queued events using transfer and delete logic."""
    if not get_autosync_enabled() and not force:
        return {"processed": 0, "message": "autosync_disabled"}

    claimed = claim_queued_events(limit=limit)
    processed = 0
    failed = 0
    partial = 0
    success = 0
    event_summaries: list[dict[str, Any]] = []

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
            compact = _compact_event_summary(event, result)
            event_summaries.append(compact)
            append_asset_event(
                event_type=f"sync.event_{status}",
                identifier=event.get("identifier"),
                source="autosync_engine",
                payload=compact,
            )
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
            event_summaries.append(
                {
                    "event_id": event_id,
                    "event_type": event.get("event_type"),
                    "identifier": event.get("identifier"),
                    "status": "failed",
                    "action": "error",
                    "error": str(exc),
                    "field_diffs": [],
                }
            )
            append_asset_event(
                event_type="sync.event_failed",
                identifier=event.get("identifier"),
                source="autosync_engine",
                payload={"event_id": event_id, "error": str(exc)},
            )

    set_status("last_sync_run_at", get_state().get("last_updated_at"))
    set_status("worker_heartbeat_at", get_state().get("last_updated_at"))
    return {
        "processed": processed,
        "success": success,
        "partial": partial,
        "failed": failed,
        "events": event_summaries,
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
    kaseya_assets, revnue_assets = fetch_asset_snapshots_parallel()
    comparison = compare_assets(kaseya_assets, revnue_assets)
    queued = 0
    deduplicated = 0
    try:
        dedup_window = int(get_setting("EVENT_DEDUP_WINDOW_SECONDS", "600") or "600")
    except ValueError:
        dedup_window = 600
    for item in comparison:
        if item["match_status"] == "missing_in_revnue" and not is_tombstoned(item["identifier"]):
            event_id = enqueue_event(
                event_type="asset.reconcile",
                identifier=item["identifier"],
                payload={"reason": "missing_in_revnue", "identifier": item["identifier"]},
                deduplicate=True,
                dedup_window_seconds=max(1, dedup_window),
            )
            if event_id is None:
                deduplicated += 1
            else:
                queued += 1
    if queued:
        log_activity(
            level="info",
            category="autosync",
            message=f"Reconciliation queued {queued} events.",
        )
    if deduplicated:
        log_activity(
            level="info",
            category="autosync",
            message=f"Reconciliation deduplicated {deduplicated} events.",
        )
    set_status("last_reconcile_at", get_state().get("last_updated_at"))
    return {"queued": queued, "deduplicated": deduplicated}


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
    dedup = dedup_metrics()
    total_processed = metrics.get("success", 0) + metrics.get("failed", 0) + metrics.get("partial", 0)
    successful = metrics.get("success", 0)
    success_rate = (successful / total_processed * 100.0) if total_processed else 0.0
    status = get_state().get("status", {})
    return {
        "autosync_enabled": get_autosync_enabled(),
        "queue_metrics": metrics,
        "dedup_metrics": dedup,
        "health_state": _health_state(metrics),
        "resilience": get_resilience_snapshot(),
        "schedule": schedule_status_snapshot(),
        "worker_heartbeat_at": status.get("worker_heartbeat_at"),
        "last_reconcile_at": status.get("last_reconcile_at"),
        "success_rate": round(success_rate, 2),
        "recent_events": fetch_events(limit=20),
        "failed_events": fetch_events(status="failed", limit=20),
        "partial_events": fetch_events(status="partial", limit=20),
    }


def run_sync_cycle(
    *,
    run_type: str,
    trigger: str,
    process_limit: int = 50,
    respect_autosync_enabled: bool = True,
    respect_schedule_window: bool = True,
) -> dict[str, Any]:
    """Run a full sync cycle with audit logging."""
    started_at = utcnow_iso()
    autosync_enabled = get_autosync_enabled()
    notes: dict[str, Any] = {}
    reconcile_queued = 0
    retry_requeued = 0
    process_result = {"processed": 0, "success": 0, "partial": 0, "failed": 0}

    window_open = is_sync_window_open()
    notes["schedule"] = schedule_status_snapshot()

    if respect_schedule_window and not window_open:
        notes["message"] = "outside_schedule_window"
    elif respect_autosync_enabled and not autosync_enabled:
        notes["message"] = "autosync_disabled"
    else:
        reconcile_outcome = run_reconciliation()
        reconcile_queued = int(reconcile_outcome.get("queued", 0))
        retry_outcome = retry_failed_events(max_retries=DEFAULT_MAX_RETRIES)
        retry_requeued = int(retry_outcome.get("requeued", 0))
        process_result = process_pending_events(limit=process_limit, force=True)
        if process_result.get("message") == "autosync_disabled":
            notes["message"] = "processing_skipped_autosync_disabled"
        notes["diff_preview"] = list(process_result.get("events", []))[:80]

    completed_at = utcnow_iso()
    started_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    completed_dt = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
    duration_ms = max(0, int((completed_dt - started_dt).total_seconds() * 1000))

    changes_found = any(
        [
            reconcile_queued > 0,
            retry_requeued > 0,
            int(process_result.get("processed", 0)) > 0,
            int(process_result.get("success", 0)) > 0,
            int(process_result.get("partial", 0)) > 0,
            int(process_result.get("failed", 0)) > 0,
        ]
    )
    audit_entry: dict[str, Any] = {
        "run_type": run_type,
        "trigger": trigger,
        "autosync_enabled": autosync_enabled,
        "changes_found": changes_found,
        "reconcile_queued": reconcile_queued,
        "retry_requeued": retry_requeued,
        "processed": int(process_result.get("processed", 0)),
        "success": int(process_result.get("success", 0)),
        "partial": int(process_result.get("partial", 0)),
        "failed": int(process_result.get("failed", 0)),
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_ms": duration_ms,
        "notes": notes,
    }
    audit_entry["id"] = insert_sync_audit_run(audit_entry)
    notification_result = send_outbound_webhook(
        "sync_cycle_completed",
        {
            "sync_run_id": audit_entry["id"],
            "run_type": run_type,
            "trigger": trigger,
            "changes_found": changes_found,
            "processed": audit_entry["processed"],
            "success": audit_entry["success"],
            "partial": audit_entry["partial"],
            "failed": audit_entry["failed"],
            "completed_at": completed_at,
        },
    )
    audit_entry["notification"] = notification_result

    set_status("last_sync_run_at", completed_at)
    set_status("last_sync_changes_found", changes_found)
    set_status("worker_heartbeat_at", completed_at)
    set_status("schedule_window_open", window_open)
    log_activity(
        level="info",
        category="autosync",
        message=f"Sync cycle completed ({run_type}/{trigger}).",
        details={
            "audit_id": audit_entry["id"],
            "changes_found": changes_found,
            "processed": audit_entry["processed"],
            "failed": audit_entry["failed"],
            "notification_sent": notification_result.get("sent", False),
        },
    )
    if notification_result.get("sent") is False and notification_result.get("reason") != "not_configured":
        log_activity(
            level="warning",
            category="autosync",
            message="Outbound sync notification failed.",
            details=notification_result,
        )
    return audit_entry


def get_sync_audit_history(limit: int = 50) -> list[dict[str, Any]]:
    """Return recent sync run audit entries."""
    return fetch_sync_audit_runs(limit=limit)
