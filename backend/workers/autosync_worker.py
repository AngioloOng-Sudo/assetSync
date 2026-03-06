"""Standalone autosync worker loop (for systemd/background execution)."""

from __future__ import annotations

import signal
import time

from backend.models.db import bootstrap_storage, utcnow_iso
from backend.services.activity_logger import log_activity, set_status
from backend.services.autosync_engine import process_pending_events, retry_failed_events, run_reconciliation
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


def run_worker_loop() -> None:
    """Run reconciliation, retry, and queue processing in a loop."""
    bootstrap_storage()
    interval_seconds = int(get_setting("AUTOSYNC_INTERVAL_SECONDS", "15"))
    log_activity(
        level="info",
        category="autosync_worker",
        message=f"Autosync worker started with interval={interval_seconds}s.",
    )

    while _RUNNING:
        set_status("worker_heartbeat_at", utcnow_iso())
        run_reconciliation()
        retry_failed_events()
        process_pending_events(limit=50)
        time.sleep(interval_seconds)

    log_activity(level="info", category="autosync_worker", message="Autosync worker stopped.")


def main() -> None:
    signal.signal(signal.SIGINT, _stop_handler)
    signal.signal(signal.SIGTERM, _stop_handler)
    run_worker_loop()


if __name__ == "__main__":
    main()
