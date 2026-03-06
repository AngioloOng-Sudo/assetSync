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

                CREATE TABLE IF NOT EXISTS sync_audit_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_type TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    autosync_enabled INTEGER NOT NULL,
                    changes_found INTEGER NOT NULL,
                    reconcile_queued INTEGER NOT NULL DEFAULT 0,
                    retry_requeued INTEGER NOT NULL DEFAULT 0,
                    processed INTEGER NOT NULL DEFAULT 0,
                    success INTEGER NOT NULL DEFAULT 0,
                    partial INTEGER NOT NULL DEFAULT 0,
                    failed INTEGER NOT NULL DEFAULT 0,
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL DEFAULT 0,
                    notes_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_sync_audit_runs_completed_at
                ON sync_audit_runs(completed_at);

                CREATE TABLE IF NOT EXISTS asset_content_hashes (
                    identifier TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS asset_tombstones (
                    identifier TEXT PRIMARY KEY,
                    deleted_at TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS asset_event_stream (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    identifier TEXT,
                    source TEXT NOT NULL DEFAULT 'system',
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_asset_event_stream_created_at
                ON asset_event_stream(created_at);

                CREATE INDEX IF NOT EXISTS idx_asset_event_stream_identifier
                ON asset_event_stream(identifier);

                CREATE TABLE IF NOT EXISTS sync_event_dedup (
                    fingerprint TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_sync_event_dedup_expires_at
                ON sync_event_dedup(expires_at);
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


def insert_sync_audit_run(entry: dict[str, Any]) -> int:
    """Insert one sync audit run entry and return its id."""
    payload = {
        "run_type": str(entry.get("run_type", "manual")),
        "trigger": str(entry.get("trigger", "unknown")),
        "autosync_enabled": 1 if entry.get("autosync_enabled") else 0,
        "changes_found": 1 if entry.get("changes_found") else 0,
        "reconcile_queued": int(entry.get("reconcile_queued", 0)),
        "retry_requeued": int(entry.get("retry_requeued", 0)),
        "processed": int(entry.get("processed", 0)),
        "success": int(entry.get("success", 0)),
        "partial": int(entry.get("partial", 0)),
        "failed": int(entry.get("failed", 0)),
        "started_at": str(entry.get("started_at") or utcnow_iso()),
        "completed_at": str(entry.get("completed_at") or utcnow_iso()),
        "duration_ms": int(entry.get("duration_ms", 0)),
        "notes_json": json.dumps(entry.get("notes", {}), ensure_ascii=True),
    }
    with _DB_LOCK:
        conn = get_connection()
        try:
            cursor = conn.execute(
                """
                INSERT INTO sync_audit_runs (
                    run_type,
                    trigger,
                    autosync_enabled,
                    changes_found,
                    reconcile_queued,
                    retry_requeued,
                    processed,
                    success,
                    partial,
                    failed,
                    started_at,
                    completed_at,
                    duration_ms,
                    notes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["run_type"],
                    payload["trigger"],
                    payload["autosync_enabled"],
                    payload["changes_found"],
                    payload["reconcile_queued"],
                    payload["retry_requeued"],
                    payload["processed"],
                    payload["success"],
                    payload["partial"],
                    payload["failed"],
                    payload["started_at"],
                    payload["completed_at"],
                    payload["duration_ms"],
                    payload["notes_json"],
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()


def fetch_sync_audit_runs(limit: int = 50) -> list[dict[str, Any]]:
    """Return recent sync audit run entries."""
    with _DB_LOCK:
        conn = get_connection()
        try:
            rows = conn.execute(
                """
                SELECT *
                FROM sync_audit_runs
                ORDER BY completed_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            conn.close()
    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        try:
            item["notes"] = json.loads(item.get("notes_json") or "{}")
        except json.JSONDecodeError:
            item["notes"] = {}
        item.pop("notes_json", None)
        item["autosync_enabled"] = bool(item.get("autosync_enabled"))
        item["changes_found"] = bool(item.get("changes_found"))
        items.append(item)
    return items


def append_asset_event(
    event_type: str,
    identifier: str | None,
    source: str,
    payload: dict[str, Any] | None = None,
) -> int:
    """Append one immutable record to asset_event_stream."""
    payload_json = json.dumps(payload or {}, ensure_ascii=True)
    now = utcnow_iso()
    with _DB_LOCK:
        conn = get_connection()
        try:
            cursor = conn.execute(
                """
                INSERT INTO asset_event_stream (event_type, identifier, source, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_type, identifier, source, payload_json, now),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()


def fetch_asset_events(
    *,
    limit: int = 200,
    identifier: str | None = None,
    event_type: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch immutable asset event stream entries (latest first)."""
    with _DB_LOCK:
        conn = get_connection()
        try:
            query = """
                SELECT *
                FROM asset_event_stream
                WHERE (? IS NULL OR identifier = ?)
                  AND (? IS NULL OR event_type = ?)
                ORDER BY id DESC
                LIMIT ?
            """
            rows = conn.execute(
                query,
                (identifier, identifier, event_type, event_type, limit),
            ).fetchall()
        finally:
            conn.close()

    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        try:
            item["payload"] = json.loads(item.get("payload_json") or "{}")
        except json.JSONDecodeError:
            item["payload"] = {}
        item.pop("payload_json", None)
        items.append(item)
    return items


def register_event_fingerprint(fingerprint: str, ttl_seconds: int = 600) -> bool:
    """
    Register one event fingerprint for short-window deduplication.

    Returns True when accepted (new fingerprint), False when duplicate.
    """
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    expires = (now_dt + timedelta(seconds=max(1, ttl_seconds))).isoformat()
    with _DB_LOCK:
        conn = get_connection()
        try:
            conn.execute("DELETE FROM sync_event_dedup WHERE expires_at < ?", (now,))
            existing = conn.execute(
                "SELECT 1 FROM sync_event_dedup WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
            if existing:
                conn.commit()
                return False
            conn.execute(
                """
                INSERT INTO sync_event_dedup (fingerprint, created_at, expires_at)
                VALUES (?, ?, ?)
                """,
                (fingerprint, now, expires),
            )
            conn.commit()
            return True
        finally:
            conn.close()


def dedup_metrics() -> dict[str, int]:
    """Return dedup cache size metrics."""
    now = utcnow_iso()
    with _DB_LOCK:
        conn = get_connection()
        try:
            conn.execute("DELETE FROM sync_event_dedup WHERE expires_at < ?", (now,))
            row = conn.execute("SELECT COUNT(*) AS count FROM sync_event_dedup").fetchone()
            active = int(row["count"]) if row else 0
            conn.commit()
        finally:
            conn.close()
    return {"active_fingerprints": active}


def get_asset_content_hash(identifier: str) -> str | None:
    """Return last stored content hash for identifier."""
    with _DB_LOCK:
        conn = get_connection()
        try:
            row = conn.execute(
                """
                SELECT content_hash
                FROM asset_content_hashes
                WHERE identifier = ?
                """,
                (identifier,),
            ).fetchone()
        finally:
            conn.close()
    return str(row["content_hash"]) if row else None


def set_asset_content_hash(identifier: str, content_hash: str) -> None:
    """Upsert content hash for identifier."""
    now = utcnow_iso()
    with _DB_LOCK:
        conn = get_connection()
        try:
            conn.execute(
                """
                INSERT INTO asset_content_hashes (identifier, content_hash, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(identifier) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    updated_at = excluded.updated_at
                """,
                (identifier, content_hash, now),
            )
            conn.commit()
        finally:
            conn.close()


def upsert_tombstone(identifier: str, reason: str, metadata: dict[str, Any] | None = None) -> None:
    """Create or update local tombstone record for a deleted asset."""
    now = utcnow_iso()
    with _DB_LOCK:
        conn = get_connection()
        try:
            conn.execute(
                """
                INSERT INTO asset_tombstones (identifier, deleted_at, reason, metadata_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(identifier) DO UPDATE SET
                    deleted_at = excluded.deleted_at,
                    reason = excluded.reason,
                    metadata_json = excluded.metadata_json
                """,
                (identifier, now, reason, json.dumps(metadata or {}, ensure_ascii=True)),
            )
            conn.commit()
        finally:
            conn.close()


def remove_tombstone(identifier: str) -> None:
    """Remove tombstone marker for identifier."""
    with _DB_LOCK:
        conn = get_connection()
        try:
            conn.execute("DELETE FROM asset_tombstones WHERE identifier = ?", (identifier,))
            conn.commit()
        finally:
            conn.close()


def is_tombstoned(identifier: str) -> bool:
    """Return True when identifier is currently tombstoned."""
    with _DB_LOCK:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT 1 FROM asset_tombstones WHERE identifier = ?",
                (identifier,),
            ).fetchone()
        finally:
            conn.close()
    return row is not None


def list_tombstones(limit: int = 200) -> list[dict[str, Any]]:
    """Return recent tombstone records."""
    with _DB_LOCK:
        conn = get_connection()
        try:
            rows = conn.execute(
                """
                SELECT * FROM asset_tombstones
                ORDER BY deleted_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            conn.close()
    output: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        try:
            item["metadata"] = json.loads(item.get("metadata_json") or "{}")
        except json.JSONDecodeError:
            item["metadata"] = {}
        item.pop("metadata_json", None)
        output.append(item)
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
            conn.execute(
                """
                DELETE FROM sync_audit_runs
                WHERE completed_at < ?
                """,
                (cutoff,),
            )
            conn.execute(
                """
                DELETE FROM asset_content_hashes
                WHERE updated_at < ?
                """,
                (cutoff,),
            )
            conn.execute(
                """
                DELETE FROM asset_tombstones
                WHERE deleted_at < ?
                """,
                (cutoff,),
            )
            conn.execute(
                """
                DELETE FROM sync_event_dedup
                WHERE expires_at < ?
                """,
                (utcnow_iso(),),
            )
            conn.commit()
            return int(cursor.rowcount)
        finally:
            conn.close()
