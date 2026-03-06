"""Matching rules for Kaseya and Revnue assets."""

from __future__ import annotations

from typing import Any


def find_exact_match(
    kaseya_asset: dict[str, Any],
    revnue_assets: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Match by SOP rule only: Identifier == serial_number OR asset_tag."""
    identifier = (kaseya_asset.get("Identifier") or "").strip()
    if not identifier:
        return None
    for asset in revnue_assets:
        if asset.get("serial_number") == identifier or asset.get("asset_tag") == identifier:
            return asset
    return None


def compare_assets(
    kaseya_assets: list[dict[str, Any]],
    revnue_assets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Create comparison records for dashboard display."""
    results: list[dict[str, Any]] = []
    for kaseya in kaseya_assets:
        match = find_exact_match(kaseya, revnue_assets)
        identifier = kaseya.get("Identifier", "")
        results.append(
            {
                "identifier": identifier,
                "kaseya_asset": kaseya,
                "revnue_asset": match,
                "match_status": "matched" if match else "missing_in_revnue",
                # Explicitly tracked to enforce SOP no-name-matching.
                "matching_rule": "identifier_to_serial_or_asset_tag_only",
            }
        )
    return results

