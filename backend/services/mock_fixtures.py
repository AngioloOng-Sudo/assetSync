"""Replayable mock fixture loaders for deterministic API test scenarios."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.services.settings_manager import get_bool_setting, get_setting
from backend.utils.file_io import read_json

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_path(raw: str) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    return (PROJECT_ROOT / candidate).resolve()


def load_fixture_assets(env_key: str, fallback_assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Load list fixture payload from configured path when replay mode is enabled.

    Expected format: JSON array of objects.
    """
    if not get_bool_setting("USE_MOCK_FIXTURE_REPLAY", False):
        return fallback_assets

    raw_path = get_setting(env_key, "").strip()
    if not raw_path:
        return fallback_assets

    path = _resolve_path(raw_path)
    data = read_json(path, fallback_assets)
    if not isinstance(data, list):
        return fallback_assets
    return [item for item in data if isinstance(item, dict)]
