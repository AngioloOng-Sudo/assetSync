"""Support diagnostics and ticket handling service."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.models.db import DB_PATH, SUPPORT_TICKETS_PATH, cleanup_events, list_tombstones, utcnow_iso
from backend.services.activity_logger import get_activity, get_state, log_activity
from backend.services.notifications import send_outbound_webhook
from backend.services.autosync_engine import get_sync_status, process_pending_events, retry_failed_events
from backend.services.kaseya_client import check_kaseya_connectivity
from backend.services.resilience import get_resilience_snapshot
from backend.services.revnue_client import check_revnue_connectivity
from backend.services.settings_manager import get_bool_setting, get_setting
from backend.utils.file_io import append_jsonl, read_jsonl
from backend.utils.security import is_secret_key, mask_secret


def run_connectivity_checks(targets: list[str] | None = None) -> dict[str, Any]:
    """Run outbound connectivity checks for configured integrations."""
    configured_targets = {
        "kaseya": get_setting("KASEYA_ASSETS_URL", "").strip() or get_setting("KASEYA_BASE_URL", "").strip(),
        "revnue": get_setting("REVNUE_TEST_URL", "").strip() or get_setting("REVNUE_ASSET_URL", "").strip(),
    }
    if targets:
        configured_targets = {key: value for key, value in configured_targets.items() if key in targets}

    results: dict[str, Any] = {}
    for name, url in configured_targets.items():
        if name == "kaseya":
            kaseya_result = check_kaseya_connectivity()
            kaseya_result["target"] = url or kaseya_result.get("url")
            results[name] = kaseya_result
            continue
        if name == "revnue":
            revnue_result = check_revnue_connectivity()
            revnue_result["target"] = url or revnue_result.get("url")
            results[name] = revnue_result
            continue
        if get_bool_setting("USE_MOCK_APIS", True):
            results[name] = {"target": url or "mock", "reachable": True, "status_code": 200, "mode": "mock"}
            continue
        results[name] = {"target": url, "reachable": False, "error": "unsupported_target", "mode": "live"}
    return results


def safe_config_snapshot() -> dict[str, str]:
    """Return safe visibility config values for support tooling."""
    keys = [
        "USE_MOCK_APIS",
        "AUTOSYNC_ENABLED",
        "AUTOSYNC_INTERVAL_SECONDS",
        "AUTOSYNC_CRON_WINDOWS",
        "EVENT_DEDUP_WINDOW_SECONDS",
        "DEFAULT_USER_AGENT",
        "REVNUE_COMPANY",
        "REVNUE_TEST_URL",
        "REVNUE_ASSET_URL",
        "REVNUE_API_TOKEN",
        "KASEYA_BASE_URL",
        "KASEYA_ASSETS_URL",
        "KASEYA_API_TOKEN",
        "USE_MOCK_FIXTURE_REPLAY",
        "MOCK_KASEYA_FIXTURE_PATH",
        "MOCK_REVNUE_FIXTURE_PATH",
        "REVNUE_TOKEN",
        "KASEYA_TOKEN_ID",
        "KASEYA_TOKEN_SECRET",
        "WEBHOOK_SHARED_SECRET",
    ]
    output: dict[str, str] = {}
    for key in keys:
        value = get_setting(key, "")
        output[key] = mask_secret(value) if is_secret_key(key) else value
    return output


def system_health_snapshot() -> dict[str, Any]:
    """Collect a health snapshot for support diagnostics."""
    sync_status = get_sync_status()
    activity = get_activity(limit=20)
    return {
        "timestamp": utcnow_iso(),
        "storage": {
            "sync_events_db_exists": DB_PATH.exists(),
            "sync_events_db_size_bytes": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
            "support_tickets_exists": SUPPORT_TICKETS_PATH.exists(),
        },
        "safe_config": safe_config_snapshot(),
        "runtime_state": get_state().get("status", {}),
        "resilience": get_resilience_snapshot(),
        "sync_status": sync_status,
        "tombstones": list_tombstones(limit=50),
        "recent_activity": activity,
        "recent_failed_or_partial_activity": [
            item for item in activity if item.get("level") in {"warning", "error"}
        ],
    }


def create_ticket(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a support ticket in JSONL storage."""
    existing = read_jsonl(SUPPORT_TICKETS_PATH, limit=10_000)
    next_id = len(existing) + 1
    ticket = {
        "id": next_id,
        "created_at": utcnow_iso(),
        "title": payload.get("title", "").strip(),
        "description": payload.get("description", "").strip(),
        "priority": payload.get("priority", "normal"),
        "diagnostics": payload.get("diagnostics") or system_health_snapshot(),
        "status": "open",
    }
    append_jsonl(SUPPORT_TICKETS_PATH, ticket)
    log_activity(
        level="info",
        category="support",
        message=f"Support ticket {next_id} created.",
        details={"ticket_id": next_id, "priority": ticket["priority"]},
    )
    return ticket


def list_tickets(limit: int = 100) -> list[dict[str, Any]]:
    """Return recent support tickets."""
    return read_jsonl(SUPPORT_TICKETS_PATH, limit=limit)


def export_diagnostics() -> dict[str, Any]:
    """Export diagnostics package payload."""
    payload = {
        "generated_at": utcnow_iso(),
        "health_snapshot": system_health_snapshot(),
        "connectivity": run_connectivity_checks(),
        "tickets": list_tickets(limit=200),
    }
    return payload


def run_support_maintenance() -> dict[str, Any]:
    """Run support maintenance actions for monitoring workflows."""
    retry_outcome = retry_failed_events()
    process_outcome = process_pending_events(limit=25)
    cleaned = cleanup_events(days=30)
    return {
        "retry_outcome": retry_outcome,
        "process_outcome": process_outcome,
        "cleaned_events": cleaned,
    }


def export_diagnostics_json() -> str:
    """Return serialized diagnostics data for download."""
    return json.dumps(export_diagnostics(), indent=2, ensure_ascii=True)


def diagnostics_file_path() -> Path:
    """Return default path where diagnostics exports can be stored."""
    return SUPPORT_TICKETS_PATH.parent / "diagnostics_export.json"


def send_test_outbound_notification() -> dict[str, Any]:
    """Send a test outbound webhook notification."""
    payload = {
        "message": "GSIS Asset Sync test notification",
        "timestamp": utcnow_iso(),
        "sync_status": get_sync_status(),
    }
    result = send_outbound_webhook("test_notification", payload)
    log_activity(
        level="info" if result.get("sent") else "warning",
        category="support",
        message="Outbound notification test executed.",
        details=result,
    )
    return result
