"""Sync status and queue KPI APIs."""

from __future__ import annotations

from fastapi import APIRouter, Query

from backend.models.schemas import TransferRequest
from backend.services.autosync_engine import get_sync_overview, get_sync_status, run_reconciliation
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
