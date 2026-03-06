"""External field mapping configuration for deterministic asset mapping."""

from __future__ import annotations

import copy
from typing import Any

from backend.models.db import DATA_DIR
from backend.services.settings_manager import get_setting
from backend.utils.file_io import read_json, write_json

MAPPING_CONFIG_PATH = DATA_DIR / "field_mapping.json"

DEFAULT_MAPPING_CONFIG: dict[str, Any] = {
    "version": 1,
    "direct_fields": {
        "name": "Name",
        "manufacturer": "Manufacturer",
        "model": "Model",
        "serial_number": "Identifier",
        "asset_tag": "Identifier",
    },
    "defaults": {
        "category": {"id": 25, "name": "Devices"},
    },
    "template_field_map": {},
}


def _coerce_mapping_config(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return copy.deepcopy(DEFAULT_MAPPING_CONFIG)

    merged = copy.deepcopy(DEFAULT_MAPPING_CONFIG)
    if isinstance(raw.get("version"), int):
        merged["version"] = max(1, int(raw["version"]))

    if isinstance(raw.get("direct_fields"), dict):
        merged["direct_fields"] = {
            str(key): str(value)
            for key, value in raw["direct_fields"].items()
            if str(key).strip() and str(value).strip()
        }

    if isinstance(raw.get("defaults"), dict):
        merged["defaults"] = raw["defaults"]

    if isinstance(raw.get("template_field_map"), dict):
        merged["template_field_map"] = {
            str(key): str(value)
            for key, value in raw["template_field_map"].items()
            if str(key).strip() and str(value).strip()
        }

    return merged


def ensure_mapping_config() -> None:
    """Create default external mapping configuration when missing."""
    MAPPING_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not MAPPING_CONFIG_PATH.exists():
        write_json(MAPPING_CONFIG_PATH, DEFAULT_MAPPING_CONFIG)


def load_mapping_config() -> dict[str, Any]:
    """Load mapping configuration from external JSON file."""
    ensure_mapping_config()
    loaded = read_json(MAPPING_CONFIG_PATH, copy.deepcopy(DEFAULT_MAPPING_CONFIG))
    return _coerce_mapping_config(loaded)


def save_mapping_config(config: dict[str, Any]) -> dict[str, Any]:
    """Persist mapping configuration and return normalized payload."""
    normalized = _coerce_mapping_config(config)
    write_json(MAPPING_CONFIG_PATH, normalized)
    return normalized


def _extract_template_fields(kaseya_asset: dict[str, Any], template_field_map: dict[str, str]) -> list[dict[str, Any]]:
    assetinfo = kaseya_asset.get("assetinfo") or kaseya_asset.get("AssetInfo") or []
    if not isinstance(assetinfo, list):
        return []

    output: list[dict[str, Any]] = []
    for item in assetinfo:
        if not isinstance(item, dict):
            continue
        source_key = str(item.get("key") or item.get("name") or "").strip()
        if not source_key:
            continue
        target_key = template_field_map.get(source_key, source_key)
        output.append({"field_key": target_key, "value": item.get("value")})
    return output


def map_kaseya_asset_with_config(kaseya_asset: dict[str, Any]) -> dict[str, Any]:
    """Map one Kaseya asset into Revnue payload using external config."""
    config = load_mapping_config()
    direct_fields = config.get("direct_fields") or {}
    mapped: dict[str, Any] = {}
    for target_field, source_key in direct_fields.items():
        if not isinstance(source_key, str):
            continue
        mapped[target_field] = kaseya_asset.get(source_key, "")

    identifier = str(mapped.get("serial_number") or kaseya_asset.get("Identifier") or "").strip()
    mapped["serial_number"] = identifier
    mapped["asset_tag"] = str(mapped.get("asset_tag") or identifier).strip()
    mapped["company"] = str(get_setting("REVNUE_COMPANY", "1"))
    mapped["category"] = config.get("defaults", {}).get("category", {"id": 25, "name": "Devices"})
    mapped["template_fields"] = _extract_template_fields(kaseya_asset, config.get("template_field_map") or {})
    mapped["detail_source"] = kaseya_asset.get("detail_source") or "kaseya"
    mapped["modified_date"] = kaseya_asset.get("ModifiedDate") or ""
    mapped["mapping_version"] = int(config.get("version", 1))
    return mapped
