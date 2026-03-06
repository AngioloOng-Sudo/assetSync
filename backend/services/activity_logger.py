"""Activity logging service backed by JSONL and state JSON files."""

from __future__ import annotations

from typing import Any

from backend.models.db import ACTIVITY_LOG_PATH, ACTIVITY_STATE_PATH, utcnow_iso
from backend.utils.file_io import append_jsonl, read_json, read_jsonl, write_json

MAX_NOTIFICATIONS = 200


def _default_state() -> dict[str, Any]:
    return {
        "last_updated_at": utcnow_iso(),
        "notifications": [],
        "messages": [],
        "unread_count": 0,
        "status": {"autosync_enabled": False, "last_sync_run_at": None},
    }


def _load_state() -> dict[str, Any]:
    state = read_json(ACTIVITY_STATE_PATH, _default_state())
    state.setdefault("notifications", [])
    state.setdefault("messages", [])
    state.setdefault("unread_count", 0)
    state.setdefault("status", {"autosync_enabled": False, "last_sync_run_at": None})
    return state


def _save_state(state: dict[str, Any]) -> None:
    state["last_updated_at"] = utcnow_iso()
    write_json(ACTIVITY_STATE_PATH, state)


def log_activity(
    *,
    level: str,
    category: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write one activity record and update state notifications."""
    record = {
        "timestamp": utcnow_iso(),
        "level": level,
        "category": category,
        "message": message,
        "details": details or {},
    }
    append_jsonl(ACTIVITY_LOG_PATH, record)

    state = _load_state()
    notifications = state.get("notifications", [])
    entry = {
        "timestamp": record["timestamp"],
        "level": level,
        "message": message,
        "category": category,
        "read": False,
    }
    notifications.append(entry)
    messages = state.get("messages", [])
    messages.append({**entry, "details": record.get("details", {})})
    state["notifications"] = notifications[-MAX_NOTIFICATIONS:]
    state["messages"] = messages[-MAX_NOTIFICATIONS:]
    state["unread_count"] = sum(1 for item in state["notifications"] if not item.get("read"))
    _save_state(state)
    return record


def set_status(key: str, value: Any) -> None:
    """Update a status key in activity state."""
    state = _load_state()
    status = state.setdefault("status", {})
    status[key] = value
    _save_state(state)


def get_activity(limit: int = 100) -> list[dict[str, Any]]:
    """Return recent activity records."""
    return read_jsonl(ACTIVITY_LOG_PATH, limit=limit)


def get_state() -> dict[str, Any]:
    """Return activity state snapshot."""
    return _load_state()


def mark_logs_as_read() -> dict[str, Any]:
    """Mark all notification and message entries as read."""
    state = _load_state()
    notifications = state.get("notifications", [])
    messages = state.get("messages", [])
    for entry in notifications:
        entry["read"] = True
    for entry in messages:
        entry["read"] = True
    state["unread_count"] = 0
    _save_state(state)
    return {"marked_read": len(notifications), "unread_count": 0}
