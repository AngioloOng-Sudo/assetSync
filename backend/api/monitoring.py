"""Monitoring and metrics endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from backend.models.db import dedup_metrics, event_metrics
from backend.services.activity_logger import get_state
from backend.services.autosync_engine import get_sync_audit_history
from backend.services.resilience import get_resilience_snapshot

router = APIRouter(tags=["monitoring"])


def _to_unix_timestamp(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return float(dt.timestamp())


@router.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
def prometheus_metrics() -> str:
    """Expose Prometheus-compatible metrics."""
    metrics = event_metrics()
    dedup = dedup_metrics()
    state = get_state().get("status", {})
    resilience = get_resilience_snapshot()
    latest_runs = get_sync_audit_history(limit=1)
    latest_run = latest_runs[0] if latest_runs else {}

    lines: list[str] = []
    lines.append("# HELP gsis_sync_events_total Total queued/processed sync events by status")
    lines.append("# TYPE gsis_sync_events_total gauge")
    for status, count in sorted(metrics.items()):
        lines.append(f'gsis_sync_events_total{{status="{status}"}} {int(count)}')

    lines.append("# HELP gsis_sync_last_run_timestamp_seconds Last sync run completion timestamp")
    lines.append("# TYPE gsis_sync_last_run_timestamp_seconds gauge")
    lines.append(f"gsis_sync_last_run_timestamp_seconds {_to_unix_timestamp(state.get('last_sync_run_at'))}")

    lines.append("# HELP gsis_sync_worker_heartbeat_timestamp_seconds Last worker heartbeat timestamp")
    lines.append("# TYPE gsis_sync_worker_heartbeat_timestamp_seconds gauge")
    lines.append(
        f"gsis_sync_worker_heartbeat_timestamp_seconds {_to_unix_timestamp(state.get('worker_heartbeat_at'))}"
    )

    lines.append("# HELP gsis_sync_audit_last_processed Last audit run processed count")
    lines.append("# TYPE gsis_sync_audit_last_processed gauge")
    lines.append(f"gsis_sync_audit_last_processed {int(latest_run.get('processed', 0))}")

    lines.append("# HELP gsis_sync_audit_last_failed Last audit run failed count")
    lines.append("# TYPE gsis_sync_audit_last_failed gauge")
    lines.append(f"gsis_sync_audit_last_failed {int(latest_run.get('failed', 0))}")

    lines.append("# HELP gsis_sync_dedup_active_fingerprints Active dedup cache entries")
    lines.append("# TYPE gsis_sync_dedup_active_fingerprints gauge")
    lines.append(f"gsis_sync_dedup_active_fingerprints {int(dedup.get('active_fingerprints', 0))}")

    lines.append("# HELP gsis_circuit_breaker_open Circuit breaker open state (1=open, 0=closed)")
    lines.append("# TYPE gsis_circuit_breaker_open gauge")
    for service, snapshot in sorted(resilience.items()):
        is_open = 1 if snapshot.get("circuit_open") else 0
        lines.append(f'gsis_circuit_breaker_open{{service="{service}"}} {is_open}')

    lines.append("# HELP gsis_circuit_breaker_failures Current failure counter per service")
    lines.append("# TYPE gsis_circuit_breaker_failures gauge")
    for service, snapshot in sorted(resilience.items()):
        lines.append(f'gsis_circuit_breaker_failures{{service="{service}"}} {int(snapshot.get("failures", 0))}')

    lines.append("# HELP gsis_rate_tokens_available Current token bucket balance per service")
    lines.append("# TYPE gsis_rate_tokens_available gauge")
    for service, snapshot in sorted(resilience.items()):
        lines.append(
            f'gsis_rate_tokens_available{{service="{service}"}} {float(snapshot.get("tokens_available", 0.0))}'
        )

    return "\n".join(lines) + "\n"
