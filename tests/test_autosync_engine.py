from backend.services.autosync_engine import (
    enqueue_event,
    get_sync_status,
    process_pending_events,
    retry_failed_events,
    set_autosync_enabled,
)


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

