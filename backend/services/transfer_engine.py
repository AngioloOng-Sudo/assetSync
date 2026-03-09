"""Asset transfer engine implementing SOP matching and safeguards."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.models.db import (
    append_asset_event,
    get_asset_content_hash,
    is_tombstoned,
    remove_tombstone,
    set_asset_content_hash,
    upsert_tombstone,
    utcnow_iso,
)
from backend.services.activity_logger import log_activity
from backend.services.kaseya_client import fetch_kaseya_asset_by_identifier, fetch_kaseya_assets
from backend.services.mapping_config import map_kaseya_asset_with_config
from backend.services.revnue_client import (
    delete_revnue_asset as revnue_delete_revnue_asset,
    fetch_revnue_exact_matches,
    upsert_revnue_asset,
)
from backend.services.settings_manager import get_bool_setting, get_setting

MAPPED_FIELDS = ("company", "name", "manufacturer", "model", "serial_number", "asset_tag")


def _is_blank(value: Any) -> bool:
    return value in ("", None, [], {})


def _merge_template_fields_preserve_existing(
    existing_asset: dict[str, Any] | None,
    incoming_fields: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Preserve non-empty existing template values when incoming mapped values are empty."""
    existing_list = (existing_asset or {}).get("template_fields") or []
    existing_map = {
        str(item.get("field_key")): item.get("value")
        for item in existing_list
        if isinstance(item, dict) and item.get("field_key")
    }
    incoming_map = {
        str(item.get("field_key")): item.get("value")
        for item in incoming_fields
        if isinstance(item, dict) and item.get("field_key")
    }

    merged_keys = set(existing_map) | set(incoming_map)
    merged: list[dict[str, Any]] = []
    for key in sorted(merged_keys):
        incoming_value = incoming_map.get(key)
        existing_value = existing_map.get(key)
        if _is_blank(incoming_value) and not _is_blank(existing_value):
            merged.append({"field_key": key, "value": existing_value})
        else:
            merged.append({"field_key": key, "value": incoming_value})
    return merged


def _map_kaseya_asset(kaseya_asset: dict[str, Any]) -> dict[str, Any]:
    mapped = map_kaseya_asset_with_config(kaseya_asset)
    mapped["company"] = mapped.get("company") or get_setting("REVNUE_COMPANY", "1")
    mapped["last_synced_at"] = utcnow_iso()
    return mapped


def _nonempty_count(payload: dict[str, Any]) -> int:
    return sum(1 for value in payload.values() if value not in ("", None, [], {}))


def _content_hash(mapped_asset: dict[str, Any]) -> str:
    payload = {
        "company": mapped_asset.get("company"),
        "serial_number": mapped_asset.get("serial_number"),
        "asset_tag": mapped_asset.get("asset_tag"),
        "name": mapped_asset.get("name"),
        "manufacturer": mapped_asset.get("manufacturer"),
        "model": mapped_asset.get("model"),
        "template_fields": mapped_asset.get("template_fields") or [],
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _compute_field_diffs(
    existing_asset: dict[str, Any] | None,
    prepared_asset: dict[str, Any],
    *,
    max_template_diffs: int = 25,
) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    compare_fields = ("name", "manufacturer", "model", "serial_number", "asset_tag", "company")
    for field in compare_fields:
        before = (existing_asset or {}).get(field)
        after = prepared_asset.get(field)
        if before != after:
            diffs.append({"field": field, "before": before, "after": after})

    old_template: dict[str, Any] = {}
    for item in (existing_asset or {}).get("template_fields") or []:
        if isinstance(item, dict) and item.get("field_key"):
            old_template[str(item["field_key"])] = item.get("value")
    new_template: dict[str, Any] = {}
    for item in prepared_asset.get("template_fields") or []:
        if isinstance(item, dict) and item.get("field_key"):
            new_template[str(item["field_key"])] = item.get("value")

    for key in sorted(set(old_template.keys()) | set(new_template.keys()))[:max_template_diffs]:
        before = old_template.get(key)
        after = new_template.get(key)
        if before != after:
            diffs.append({"field": f"template_fields.{key}", "before": before, "after": after})
    return diffs


def _apply_safeguards(
    mapped_asset: dict[str, Any],
    existing_asset: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[str]]:
    """
    Apply SOP data quality safeguards:
    - Preserve existing Revnue value if incoming mapped value is empty.
    - Mark transfer partial when key data is incomplete.
    """
    reasons: list[str] = []
    result = dict(mapped_asset)

    if existing_asset:
        for field in MAPPED_FIELDS:
            if _is_blank(result.get(field)) and not _is_blank(existing_asset.get(field)):
                result[field] = existing_asset.get(field)

    result["template_fields"] = _merge_template_fields_preserve_existing(
        existing_asset,
        result.get("template_fields") or [],
    )

    if not result.get("serial_number") and not result.get("asset_tag"):
        reasons.append("missing_identifier")
    if not result.get("name"):
        reasons.append("missing_name")
    if not result.get("manufacturer"):
        reasons.append("missing_manufacturer")
    if not result.get("model"):
        reasons.append("missing_model")

    return result, reasons


def _build_debug_indicators(kaseya_asset: dict[str, Any], mapped: dict[str, Any]) -> dict[str, Any]:
    assetinfo = kaseya_asset.get("assetinfo") or []
    return {
        "has_assetinfo": bool(assetinfo),
        "assetinfo_count": len(assetinfo),
        "detail_source": mapped.get("detail_source"),
        "mapped_nonempty_count": _nonempty_count(mapped),
        "template_fields_count": len(mapped.get("template_fields") or []),
    }


def _resolve_selected_assets(
    assets_or_identifiers: list[dict[str, Any]] | list[str] | None,
) -> list[dict[str, Any]]:
    if not assets_or_identifiers:
        return fetch_kaseya_assets(top=100_000, skip=0)

    first = assets_or_identifiers[0]
    if isinstance(first, dict):
        return [asset for asset in assets_or_identifiers if isinstance(asset, dict)]  # type: ignore[arg-type]

    identifiers = {
        str(identifier).strip()
        for identifier in assets_or_identifiers  # type: ignore[assignment]
        if str(identifier).strip()
    }
    if not identifiers:
        return fetch_kaseya_assets(top=100_000, skip=0)

    assets: list[dict[str, Any]] = []
    for identifier in identifiers:
        asset = fetch_kaseya_asset_by_identifier(identifier)
        if asset:
            assets.append(asset)
    return assets


def transfer_kaseya_assets_to_revnue(
    assets_or_identifiers: list[dict[str, Any]] | list[str] | None = None,
    *,
    dry_run: bool = False,
    respect_tombstones: bool = True,
) -> dict[str, Any]:
    """Transfer selected Kaseya assets to Revnue using SOP create/update logic."""
    selected_assets = _resolve_selected_assets(assets_or_identifiers)

    results: list[dict[str, Any]] = []
    summary = {"created": 0, "updated": 0, "partial": 0, "failed": 0, "skipped": 0}

    for asset in selected_assets:
        identifier = (asset.get("Identifier") or "").strip()
        if identifier and respect_tombstones and is_tombstoned(identifier):
            summary["skipped"] += 1
            result = {
                "identifier": identifier,
                "status": "success",
                "action": "skipped",
                "reason": "tombstoned",
                "field_diffs": [],
            }
            results.append(result)
            log_activity(
                level="info",
                category="transfer",
                message=f"Skipped tombstoned asset {identifier}.",
                details=result,
            )
            append_asset_event(
                event_type="asset.transfer_skipped",
                identifier=identifier,
                source="transfer_engine",
                payload=result,
            )
            continue

        mapped = _map_kaseya_asset(asset)
        company = mapped.get("company")
        existing_matches = (
            fetch_revnue_exact_matches(company=company, identifiers=[identifier]) if identifier else []
        )
        existing = existing_matches[0] if existing_matches else None
        prepared, partial_reasons = _apply_safeguards(mapped, existing)
        debug_indicators = _build_debug_indicators(asset, prepared)
        field_diffs = _compute_field_diffs(existing, prepared)
        content_hash = _content_hash(prepared)

        if not identifier:
            summary["partial"] += 1
            result = {
                "identifier": identifier,
                "status": "partial",
                "action": "skipped",
                "reason": "missing_identifier",
                "partial_reasons": partial_reasons or ["missing_identifier"],
                "debug": debug_indicators,
                "field_diffs": field_diffs,
            }
            results.append(result)
            log_activity(
                level="warning",
                category="transfer",
                message="Transfer marked partial due to incomplete data.",
                details=result,
            )
            append_asset_event(
                event_type="asset.transfer_partial",
                identifier=identifier,
                source="transfer_engine",
                payload=result,
            )
            continue

        try:
            previous_hash = get_asset_content_hash(identifier)
            if existing and previous_hash == content_hash and not dry_run:
                summary["skipped"] += 1
                result = {
                    "identifier": identifier,
                    "status": "success",
                    "action": "unchanged",
                    "reason": "content_hash_match",
                    "partial_reasons": partial_reasons,
                    "debug": debug_indicators,
                    "field_diffs": [],
                }
                results.append(result)
                log_activity(
                    level="info",
                    category="transfer",
                    message=f"Asset {identifier} unchanged (hash match).",
                    details=result,
                )
                append_asset_event(
                    event_type="asset.unchanged",
                    identifier=identifier,
                    source="transfer_engine",
                    payload=result,
                )
                continue

            action = "updated" if existing else "created"
            if dry_run:
                upsert_result = {"action": action, "asset": prepared}
            else:
                upsert_result = upsert_revnue_asset(identifier, prepared, company=company)
                set_asset_content_hash(identifier, content_hash)
                remove_tombstone(identifier)
            action = upsert_result["action"]
            status = "partial" if partial_reasons else "success"
            if action == "created":
                summary["created"] += 1
            else:
                summary["updated"] += 1
            if status == "partial":
                summary["partial"] += 1

            result = {
                "identifier": identifier,
                "status": status,
                "action": action,
                "partial_reasons": partial_reasons,
                "debug": debug_indicators,
                "asset": upsert_result.get("asset"),
                "field_diffs": field_diffs,
            }
            results.append(result)
            log_activity(
                level="warning" if status == "partial" else "info",
                category="transfer",
                message=f"Asset {identifier} {action} in Revnue{' (dry-run)' if dry_run else ''}.",
                details=result,
            )
            append_asset_event(
                event_type=f"asset.{action}",
                identifier=identifier,
                source="transfer_engine",
                payload={
                    "status": status,
                    "partial_reasons": partial_reasons,
                    "field_diffs": field_diffs,
                    "dry_run": dry_run,
                },
            )
        except Exception as exc:  # pragma: no cover - defensive logging path
            summary["failed"] += 1
            result = {
                "identifier": identifier,
                "status": "failed",
                "action": "error",
                "error": str(exc),
                "debug": debug_indicators,
                "field_diffs": field_diffs,
            }
            results.append(result)
            log_activity(
                level="error",
                category="transfer",
                message=f"Transfer failed for {identifier}.",
                details=result,
            )
            append_asset_event(
                event_type="asset.transfer_failed",
                identifier=identifier,
                source="transfer_engine",
                payload=result,
            )

    return {
        "summary": summary,
        "results": results,
        "total": len(selected_assets),
        "dry_run": dry_run,
        "mode": "mock" if get_bool_setting("USE_MOCK_APIS", True) else "live",
    }


def delete_revnue_asset(identifier: str, company: str | int | None = None) -> dict[str, Any]:
    """Delete one Revnue asset by identifier."""
    deleted = revnue_delete_revnue_asset(identifier, company=company)
    status = "deleted" if deleted else "not_found"
    details = {"identifier": identifier, "status": status}
    if deleted and identifier:
        upsert_tombstone(
            identifier,
            reason="manual_delete",
            metadata={"company": company, "deleted_at": utcnow_iso()},
        )
        append_asset_event(
            event_type="asset.deleted",
            identifier=identifier,
            source="transfer_engine",
            payload={"company": company, "status": status},
        )
    log_activity(
        level="info" if deleted else "warning",
        category="transfer",
        message=f"Delete Revnue asset {identifier}: {status}",
        details=details,
    )
    return details
