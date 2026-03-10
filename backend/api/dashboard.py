"""Dashboard and transfer API endpoints."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from backend.models.db import fetch_asset_events
from backend.models.schemas import AssetDetailResponse, AutosyncStateRequest, MarkReadRequest, TransferRequest
from backend.services.activity_logger import get_activity, get_state, mark_logs_as_read
from backend.services.autosync_engine import (
    get_autosync_enabled,
    process_pending_events,
    run_reconciliation,
    set_autosync_enabled,
)
from backend.services.kaseya_client import fetch_all_kaseya_assets, fetch_kaseya_asset_by_identifier
from backend.services.matching import compare_assets
from backend.services.parallel_fetch import fetch_asset_snapshots_async
from backend.services.revnue_client import fetch_all_revnue_assets, fetch_revnue_exact_matches
from backend.services.transfer_engine import delete_revnue_asset, transfer_kaseya_assets_to_revnue

router = APIRouter(prefix="/api", tags=["dashboard"])


def _paginate(items: list[dict], page: int, page_size: int) -> dict:
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "items": items[start:end],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


def _matched_identifiers(revnue_assets: list[dict]) -> set[str]:
    return {
        str(asset.get("serial_number") or "")
        for asset in revnue_assets
        if asset.get("serial_number") or asset.get("asset_tag")
    } | {
        str(asset.get("asset_tag") or "")
        for asset in revnue_assets
        if asset.get("serial_number") or asset.get("asset_tag")
    }


def _filter_kaseya_assets_by_search(assets: list[dict], search: str) -> list[dict]:
    search_text = search.strip().lower()
    if not search_text:
        return assets
    return [
        asset
        for asset in assets
        if search_text in (asset.get("Identifier", "").lower())
        or search_text in (asset.get("Name", "").lower())
        or search_text in (asset.get("Manufacturer", "").lower())
        or search_text in (asset.get("Model", "").lower())
    ]


def _filter_revnue_assets_by_search(assets: list[dict], search: str) -> list[dict]:
    search_text = search.strip().lower()
    if not search_text:
        return assets
    return [
        asset
        for asset in assets
        if search_text in str(asset.get("serial_number", "")).lower()
        or search_text in str(asset.get("asset_tag", "")).lower()
        or search_text in str(asset.get("name", "")).lower()
    ]


@router.get("/assets/kaseya")
def get_kaseya_assets(
    search: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    only_missing: bool = Query(default=False),
) -> dict:
    try:
        assets = fetch_all_kaseya_assets(page_size=100, max_pages=1000)
    except Exception as exc:  # upstream/network/auth errors
        raise HTTPException(status_code=502, detail=f"Kaseya API request failed: {exc}") from exc
    if only_missing:
        revnue_assets = fetch_all_revnue_assets(company=None)
        matched = _matched_identifiers(revnue_assets)
        assets = [asset for asset in assets if str(asset.get("Identifier") or "") not in matched]
    assets = _filter_kaseya_assets_by_search(assets, search)
    return _paginate(assets, page, page_size)


@router.get("/kaseya/assets")
def get_kaseya_assets_alias(
    search: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    only_missing: bool = Query(default=False),
) -> dict:
    return get_kaseya_assets(search=search, page=page, page_size=page_size, only_missing=only_missing)


@router.get("/assets/revnue")
def get_revnue_assets(
    search: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
) -> dict:
    assets = fetch_all_revnue_assets(company=None)
    assets = _filter_revnue_assets_by_search(assets, search)
    return _paginate(assets, page, page_size)


@router.get("/revnue/assets")
def get_revnue_assets_alias(
    search: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
) -> dict:
    return get_revnue_assets(search=search, page=page, page_size=page_size)


@router.get("/assets/strev")
def get_strev_assets(
    search: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
) -> dict:
    return get_revnue_assets(search=search, page=page, page_size=page_size)


@router.get("/strev/assets")
def get_strev_assets_alias(
    search: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
) -> dict:
    return get_revnue_assets(search=search, page=page, page_size=page_size)


@router.get("/dashboard/assets")
def get_dashboard_assets(
    kaseya_search: str = Query(default="", max_length=100),
    kaseya_page: int = Query(default=1, ge=1),
    kaseya_page_size: int = Query(default=10, ge=1, le=100),
    strev_search: str = Query(default="", max_length=100),
    strev_page: int = Query(default=1, ge=1),
    strev_page_size: int = Query(default=10, ge=1, le=100),
    only_missing: bool = Query(default=False),
) -> dict:
    try:
        kaseya_assets = fetch_all_kaseya_assets(page_size=100, max_pages=1000)
    except Exception as exc:  # upstream/network/auth errors
        raise HTTPException(status_code=502, detail=f"Kaseya API request failed: {exc}") from exc

    strev_assets = fetch_all_revnue_assets(company=None)
    if only_missing:
        matched = _matched_identifiers(strev_assets)
        kaseya_assets = [asset for asset in kaseya_assets if str(asset.get("Identifier") or "") not in matched]

    kaseya_payload = _paginate(_filter_kaseya_assets_by_search(kaseya_assets, kaseya_search), kaseya_page, kaseya_page_size)
    strev_payload = _paginate(_filter_revnue_assets_by_search(strev_assets, strev_search), strev_page, strev_page_size)
    return {
        "kaseya": kaseya_payload,
        "strev": strev_payload,
        "revnue": dict(strev_payload),
    }


@router.get("/assets/detail/{identifier}", response_model=AssetDetailResponse)
def get_asset_detail(identifier: str) -> AssetDetailResponse:
    normalized_identifier = identifier.strip()
    if not normalized_identifier:
        raise HTTPException(status_code=400, detail="Identifier is required.")

    try:
        kaseya_asset = fetch_kaseya_asset_by_identifier(normalized_identifier)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Kaseya API request failed: {exc}") from exc

    if not kaseya_asset:
        raise HTTPException(status_code=404, detail=f'Asset "{normalized_identifier}" was not found in Kaseya.')

    try:
        matches = fetch_revnue_exact_matches(identifiers=[normalized_identifier])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Revnue API request failed: {exc}") from exc

    sync_events = fetch_asset_events(identifier=normalized_identifier, limit=20)
    revnue_match = matches[0] if matches else None
    return AssetDetailResponse(
        identifier=normalized_identifier,
        kaseya=kaseya_asset,
        revnue_match=revnue_match,
        sync_events=sync_events,
    )


@router.get("/assets/compare")
async def get_asset_comparison() -> dict:
    kaseya_assets, revnue_assets = await fetch_asset_snapshots_async()
    return {
        "items": compare_assets(kaseya_assets, revnue_assets),
        "matching_rule": "Identifier == serial_number OR Identifier == asset_tag",
    }


@router.get("/assets/export.csv", response_class=PlainTextResponse)
async def export_asset_comparison_csv() -> str:
    """Export asset comparison view as CSV for reporting."""
    kaseya_assets, revnue_assets = await fetch_asset_snapshots_async()
    comparison = compare_assets(kaseya_assets, revnue_assets)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "identifier",
            "match_status",
            "source_name",
            "source_manufacturer",
            "source_model",
            "source_modified_date",
            "destination_id",
            "destination_name",
            "destination_serial_number",
            "destination_asset_tag",
        ]
    )
    for row in comparison:
        kaseya_asset = row.get("kaseya_asset") or {}
        revnue_asset = row.get("revnue_asset") or {}
        writer.writerow(
            [
                row.get("identifier", ""),
                row.get("match_status", ""),
                kaseya_asset.get("Name", ""),
                kaseya_asset.get("Manufacturer", ""),
                kaseya_asset.get("Model", ""),
                kaseya_asset.get("ModifiedDate", ""),
                revnue_asset.get("id", ""),
                revnue_asset.get("name", ""),
                revnue_asset.get("serial_number", ""),
                revnue_asset.get("asset_tag", ""),
            ]
        )
    return buffer.getvalue()


@router.post("/transfer")
def transfer_assets(request: TransferRequest) -> dict:
    # Manual sync requests should be able to restore assets that were tombstoned by prior deletes.
    return transfer_kaseya_assets_to_revnue(
        request.identifiers,
        dry_run=request.dry_run,
        respect_tombstones=False,
    )


@router.delete("/assets/revnue/{identifier}")
def delete_asset(identifier: str) -> dict:
    return delete_revnue_asset(identifier)


@router.get("/activity")
def get_recent_activity(limit: int = Query(default=100, ge=1, le=500)) -> dict:
    return {"items": get_activity(limit=limit)}


@router.get("/logs")
def get_logs(limit: int = Query(default=50, ge=1, le=500)) -> dict:
    state = get_state()
    return {
        "items": get_activity(limit=limit),
        "channels": {
            "notifications": state.get("notifications", []),
            "messages": state.get("messages", []),
            "unread_count": state.get("unread_count", 0),
        },
    }


@router.post("/logs/mark-read")
def mark_logs_read(_request: MarkReadRequest | None = None) -> dict:
    return mark_logs_as_read()


@router.get("/activity/state")
def get_activity_state() -> dict:
    return get_state()


@router.get("/autosync/state")
def get_autosync_state() -> dict:
    return {"enabled": get_autosync_enabled()}


@router.post("/autosync/state")
def set_autosync_state(request: AutosyncStateRequest) -> dict:
    return set_autosync_enabled(request.enabled)


@router.post("/autosync/reconcile")
def trigger_reconcile() -> dict:
    return run_reconciliation()


@router.post("/autosync/process")
def trigger_process() -> dict:
    return process_pending_events(limit=50)
