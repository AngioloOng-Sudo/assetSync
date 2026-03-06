"""Sync status and queue KPI APIs."""

from __future__ import annotations

from fastapi import APIRouter, Query

from backend.models.db import fetch_asset_events
from backend.models.schemas import SyncRunRequest, TransferRequest
from backend.services.autosync_engine import (
    get_sync_audit_history,
    get_sync_overview,
    get_sync_status,
    run_reconciliation,
    run_sync_cycle,
)
from backend.services.schedule_windows import schedule_status_snapshot
from backend.services.transfer_engine import transfer_kaseya_assets_to_revnue

router = APIRouter(prefix="/api/sync", tags=["sync-status"])


@router.get("/status")
def sync_status() -> dict:
    return get_sync_status()


@router.get("/overview")
def sync_overview(window: str = Query(default="24h")) -> dict:
    return get_sync_overview(window=window)


@router.post("/reconcile")
def sync_reconcile() -> dict:
    return run_reconciliation()


@router.post("/dry-run")
def sync_dry_run(request: TransferRequest) -> dict:
    return transfer_kaseya_assets_to_revnue(request.identifiers, dry_run=True)


@router.get("/audit")
def sync_audit(limit: int = Query(default=50, ge=1, le=500)) -> dict:
    return {"items": get_sync_audit_history(limit=limit)}


@router.post("/run-now")
def sync_run_now(request: SyncRunRequest | None = None) -> dict:
    payload = request or SyncRunRequest()
    return run_sync_cycle(
        run_type="manual",
        trigger="api",
        process_limit=payload.process_limit,
        respect_autosync_enabled=not payload.force,
        respect_schedule_window=not payload.force,
    )


@router.get("/events")
def sync_events_stream(
    limit: int = Query(default=100, ge=1, le=1000),
    identifier: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
) -> dict:
    """Return immutable event-sourcing stream entries."""
    return {"items": fetch_asset_events(limit=limit, identifier=identifier, event_type=event_type)}


@router.get("/schedule")
def sync_schedule() -> dict:
    """Return cron-style sync window status."""
    return schedule_status_snapshot()
