"""SQLite and local storage helpers for autosync and operational state."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any

_DB_LOCK = Lock()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "backend" / "data"
DB_PATH = DATA_DIR / "sync_events.db"
ACTIVITY_LOG_PATH = DATA_DIR / "activity_log.jsonl"
ACTIVITY_STATE_PATH = DATA_DIR / "activity_state.json"
SUPPORT_TICKETS_PATH = DATA_DIR / "support_tickets.jsonl"
MOCK_REVNUE_ASSETS_PATH = DATA_DIR / "revnue_assets.json"


def utcnow_iso() -> str:
    """Return the current UTC timestamp as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _ensure_data_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not ACTIVITY_LOG_PATH.exists():
        ACTIVITY_LOG_PATH.write_text("", encoding="utf-8")

    if not ACTIVITY_STATE_PATH.exists():
        initial_state = {
            "last_updated_at": utcnow_iso(),
            "notifications": [],
            "messages": [],
            "unread_count": 0,
            "status": {"autosync_enabled": False},
        }
        ACTIVITY_STATE_PATH.write_text(
            json.dumps(initial_state, indent=2), encoding="utf-8"
        )

    if not SUPPORT_TICKETS_PATH.exists():
        SUPPORT_TICKETS_PATH.write_text("", encoding="utf-8")

    if not MOCK_REVNUE_ASSETS_PATH.exists():
        MOCK_REVNUE_ASSETS_PATH.write_text("[]", encoding="utf-8")


def get_connection() -> sqlite3.Connection:
    """Get a SQLite connection for the sync event database."""
    _ensure_data_files()
    connection = sqlite3.connect(DB_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    """Initialize the SQLite schema."""
    with _DB_LOCK:
        conn = get_connection()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sync_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    identifier TEXT,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    retries INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_sync_events_status
                ON sync_events(status);

                CREATE INDEX IF NOT EXISTS idx_sync_events_created_at
                ON sync_events(created_at);
                """
            )
            conn.commit()
        finally:
            conn.close()


def bootstrap_storage() -> None:
    """Create all local storage artifacts required by the SOP."""
    init_db()


def insert_sync_event(event_type: str, identifier: str | None, payload: dict[str, Any]) -> int:
    """Insert a new event into sync_events and return its id."""
    now = utcnow_iso()
    payload_json = json.dumps(payload, ensure_ascii=True)
    with _DB_LOCK:
        conn = get_connection()
        try:
            cursor = conn.execute(
                """
                INSERT INTO sync_events (
                    event_type, identifier, payload_json, status, retries, last_error, created_at, updated_at
                ) VALUES (?, ?, ?, 'queued', 0, NULL, ?, ?)
                """,
                (event_type, identifier, payload_json, now, now),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()


def claim_queued_events(limit: int = 50) -> list[dict[str, Any]]:
    """Claim queued events by moving them to processing status and returning rows."""
    with _DB_LOCK:
        conn = get_connection()
        try:
            rows = conn.execute(
                """
                SELECT * FROM sync_events
                WHERE status = 'queued'
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            now = utcnow_iso()
            for row in rows:
                conn.execute(
                    "UPDATE sync_events SET status = 'processing', updated_at = ? WHERE id = ?",
                    (now, row["id"]),
                )
            conn.commit()
            return [dict(row) for row in rows]
        finally:
            conn.close()


def update_sync_event(
    event_id: int,
    *,
    status: str,
    retries: int | None = None,
    last_error: str | None = None,
) -> None:
    """Update event status and metadata."""
    now = utcnow_iso()
    with _DB_LOCK:
        conn = get_connection()
        try:
            if retries is None:
                conn.execute(
                    """
                    UPDATE sync_events
                    SET status = ?, last_error = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (status, last_error, now, event_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE sync_events
                    SET status = ?, retries = ?, last_error = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (status, retries, last_error, now, event_id),
                )
            conn.commit()
        finally:
            conn.close()


def fetch_events(
    *,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Fetch sync events, optionally filtered by status."""
    with _DB_LOCK:
        conn = get_connection()
        try:
            if status:
                rows = conn.execute(
                    """
                    SELECT * FROM sync_events
                    WHERE status = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM sync_events
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()


def event_metrics() -> dict[str, int]:
    """Return queue metrics by status."""
    statuses = ["queued", "processing", "success", "failed", "partial"]
    output: dict[str, int] = {status: 0 for status in statuses}
    with _DB_LOCK:
        conn = get_connection()
        try:
            rows = conn.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM sync_events
                GROUP BY status
                """
            ).fetchall()
            for row in rows:
                output[row["status"]] = int(row["count"])
        finally:
            conn.close()
    return output


def cleanup_events(days: int = 30) -> int:
    """Delete processed events older than the provided day retention."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _DB_LOCK:
        conn = get_connection()
        try:
            cursor = conn.execute(
                """
                DELETE FROM sync_events
                WHERE created_at < ?
                  AND status IN ('success', 'failed', 'partial')
                """,
                (cutoff,),
            )
            conn.commit()
            return int(cursor.rowcount)
        finally:
            conn.close()
