from backend.services.autosync_engine import (
    enqueue_event,
    get_sync_audit_history,
    get_sync_status,
    process_pending_events,
    retry_failed_events,
    run_sync_cycle,
    set_autosync_enabled,
)
from backend.services.settings_manager import load_env_values, save_env_values


def test_autosync_event_processing_reliability():
    set_autosync_enabled(True)
    enqueue_event(event_type="asset.updated", identifier="GSIS-001", payload={"identifier": "GSIS-001"})
    outcome = process_pending_events(limit=10)
    assert outcome["processed"] >= 1

    status = get_sync_status()
    assert "queue_metrics" in status
    assert status["queue_metrics"]["success"] >= 1 or status["queue_metrics"]["partial"] >= 1


def test_retry_scheduler_runs_without_errors():
    set_autosync_enabled(True)
    enqueue_event(event_type="asset.deleted", identifier="", payload={})
    process_pending_events(limit=10)
    retry = retry_failed_events(max_retries=3)
    assert "requeued" in retry


def test_run_sync_cycle_records_audit_entry():
    set_autosync_enabled(True)
    outcome = run_sync_cycle(
        run_type="manual",
        trigger="test",
        process_limit=20,
        respect_autosync_enabled=False,
    )
    assert "id" in outcome
    history = get_sync_audit_history(limit=5)
    assert history
    assert history[0]["id"] == outcome["id"]


def test_run_sync_cycle_respects_schedule_windows():
    set_autosync_enabled(True)
    values = load_env_values()
    values["AUTOSYNC_CRON_WINDOWS"] = "0 0 1 1 *"
    save_env_values(values)
    outcome = run_sync_cycle(
        run_type="worker",
        trigger="test_schedule",
        process_limit=10,
        respect_autosync_enabled=True,
        respect_schedule_window=True,
    )
    assert outcome["notes"].get("message") in {"outside_schedule_window", "autosync_disabled"}
