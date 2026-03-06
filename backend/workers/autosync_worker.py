"""Standalone autosync worker loop (for systemd/background execution)."""

from __future__ import annotations

import signal
import time

from backend.models.db import bootstrap_storage, utcnow_iso
from backend.services.activity_logger import log_activity, set_status
from backend.services.autosync_engine import run_sync_cycle
from backend.services.settings_manager import get_setting

_RUNNING = True


def _stop_handler(signum: int, _frame: object) -> None:
    global _RUNNING
    _RUNNING = False
    log_activity(
        level="info",
        category="autosync_worker",
        message=f"Autosync worker received stop signal {signum}.",
    )


def _read_interval_setting(key: str, default: int) -> int:
    raw = get_setting(key, str(default)).strip() or str(default)
    try:
        value = int(raw)
    except ValueError:
        value = default
    return max(1, value)


def run_worker_loop() -> None:
    """Run reconciliation, retry, and queue processing in a loop."""
    bootstrap_storage()
    interval_seconds = max(5, _read_interval_setting("AUTOSYNC_INTERVAL_SECONDS", 15))
    max_interval_seconds = max(
        interval_seconds,
        _read_interval_setting("AUTOSYNC_MAX_INTERVAL_SECONDS", 300),
    )
    current_interval_seconds = interval_seconds
    log_activity(
        level="info",
        category="autosync_worker",
        message=f"Autosync worker started with base={interval_seconds}s, max={max_interval_seconds}s.",
    )

    while _RUNNING:
        interval_seconds = max(5, _read_interval_setting("AUTOSYNC_INTERVAL_SECONDS", 15))
        max_interval_seconds = max(
            interval_seconds,
            _read_interval_setting("AUTOSYNC_MAX_INTERVAL_SECONDS", 300),
        )
        if current_interval_seconds < interval_seconds:
            current_interval_seconds = interval_seconds

        set_status("worker_heartbeat_at", utcnow_iso())
        cycle = run_sync_cycle(
            run_type="worker",
            trigger="interval",
            process_limit=50,
            respect_autosync_enabled=True,
        )
        changes_found = bool(cycle.get("changes_found"))
        skip_reason = str((cycle.get("notes") or {}).get("message") or "")
        if skip_reason == "outside_schedule_window":
            current_interval_seconds = interval_seconds
            set_status("worker_interval_mode", "scheduled_pause")
        elif changes_found:
            current_interval_seconds = interval_seconds
            set_status("worker_interval_mode", "base")
        else:
            current_interval_seconds = min(current_interval_seconds * 2, max_interval_seconds)
            set_status("worker_interval_mode", "backoff")
        set_status("worker_interval_seconds", current_interval_seconds)
        time.sleep(current_interval_seconds)

    log_activity(level="info", category="autosync_worker", message="Autosync worker stopped.")


def main() -> None:
    signal.signal(signal.SIGINT, _stop_handler)
    signal.signal(signal.SIGTERM, _stop_handler)
    run_worker_loop()


if __name__ == "__main__":
    main()
