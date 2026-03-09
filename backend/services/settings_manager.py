"""Settings manager for loading and updating .env configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from backend.utils.security import is_secret_key, mask_env_values, mask_secret, sanitize_payload

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"

# Canonical-key to compatible key order (first non-empty value wins).
SETTING_ALIASES: dict[str, tuple[str, ...]] = {
    "REVNUE_API_TOKEN": ("REVNUE_API_TOKEN", "REVNUE_TOKEN"),
    "REVNUE_TOKEN": ("REVNUE_TOKEN", "REVNUE_API_TOKEN"),
    "REVNUE_BASE_URL": ("REVNUE_BASE_URL",),
    "REVNUE_ASSET_URL": ("REVNUE_ASSET_URL",),
    "REVNUE_TEST_URL": ("REVNUE_TEST_URL",),
    "REVNUE_COMPANY": ("REVNUE_COMPANY",),
    "KASEYA_API_TOKEN": ("KASEYA_API_TOKEN",),
    "KASEYA_ASSETS_URL": ("KASEYA_ASSETS_URL",),
    "KASEYA_BASE_URL": ("KASEYA_BASE_URL",),
    "KASEYA_TOKEN_ID": ("KASEYA_TOKEN_ID",),
    "KASEYA_TOKEN_SECRET": ("KASEYA_TOKEN_SECRET",),
    "DEFAULT_USER_AGENT": ("DEFAULT_USER_AGENT",),
    "WEBHOOK_SHARED_SECRET": ("WEBHOOK_SHARED_SECRET",),
}

TOKEN_ROTATABLE_KEYS: tuple[str, ...] = (
    "REVNUE_API_TOKEN",
    "REVNUE_TOKEN",
    "KASEYA_API_TOKEN",
    "KASEYA_TOKEN_SECRET",
    "WEBHOOK_SHARED_SECRET",
    "OUTBOUND_WEBHOOK_URL",
)

CORE_ENV_KEYS: tuple[str, ...] = (
    "USE_MOCK_APIS",
    "USE_MOCK_FIXTURE_REPLAY",
    "MOCK_KASEYA_FIXTURE_PATH",
    "MOCK_REVNUE_FIXTURE_PATH",
    "DEFAULT_USER_AGENT",
    "AUTOSYNC_ENABLED",
    "AUTOSYNC_INTERVAL_SECONDS",
    "AUTOSYNC_MAX_INTERVAL_SECONDS",
    "AUTOSYNC_CRON_WINDOWS",
    "WEBHOOK_SHARED_SECRET",
    "DASHBOARD_PASSWORD",
    "DASHBOARD_PASSWORD_HASH",
    "DASHBOARD_SESSION_SECRET",
    "DASHBOARD_SESSION_TIMEOUT_SECONDS",
    "REVNUE_COMPANY",
    "OUTBOUND_WEBHOOK_URL",
    "OUTBOUND_WEBHOOK_TIMEOUT_SECONDS",
    "CIRCUIT_BREAKER_FAILURE_THRESHOLD",
    "CIRCUIT_BREAKER_COOLDOWN_SECONDS",
    "RATE_LIMIT_CAPACITY",
    "RATE_LIMIT_REFILL_PER_SECOND",
    "EVENT_DEDUP_WINDOW_SECONDS",
    "REVNUE_API_TOKEN",
    "REVNUE_TOKEN",
    "REVNUE_TEST_URL",
    "REVNUE_ASSET_URL",
    "KASEYA_API_TOKEN",
    "KASEYA_ASSETS_URL",
    "KASEYA_TOKEN_ID",
    "KASEYA_TOKEN_SECRET",
    "KASEYA_BASE_URL",
)


def _serialize_env(values: dict[str, str]) -> str:
    lines = [f"{key}={value}" for key, value in sorted(values.items())]
    return "\n".join(lines).strip() + "\n"


def load_env_values() -> dict[str, str]:
    """Load env values from .env with string normalization."""
    if not ENV_PATH.exists():
        ENV_PATH.write_text("", encoding="utf-8")
    raw = dotenv_values(ENV_PATH)
    values: dict[str, str] = {}
    for key, value in raw.items():
        if key is None:
            continue
        values[key] = "" if value is None else str(value)
    return values


def save_env_values(values: dict[str, str]) -> None:
    """Persist env values to .env."""
    ENV_PATH.write_text(_serialize_env(values), encoding="utf-8")


def get_env_view(*, reveal_secrets: bool = False) -> dict[str, Any]:
    """Return .env values, masking secrets by default."""
    values = load_env_values()
    return {
        "values": mask_env_values(values, reveal_secrets=reveal_secrets),
        "masked": not reveal_secrets,
        "core_keys": list(CORE_ENV_KEYS),
    }


def update_env_values(new_values: dict[str, str]) -> dict[str, Any]:
    """Update .env key-values after sanitizing user input."""
    sanitized = sanitize_payload(new_values)
    existing = load_env_values()
    for key, value in sanitized.items():
        if not key:
            continue
        key_str = str(key)
        value_str = str(value)
        if (
            is_secret_key(key_str)
            and "*" in value_str
            and existing.get(key_str)
            and value_str != existing.get(key_str)
        ):
            # Keep existing secret when masked value is posted back by UI.
            continue
        existing[key_str] = value_str
    save_env_values(existing)
    return get_env_view(reveal_secrets=False)


def summarize_env_changes(before: dict[str, str], after: dict[str, str]) -> list[dict[str, str]]:
    """Return masked before/after records for keys changed between two env snapshots."""
    changes: list[dict[str, str]] = []
    all_keys = sorted(set(before.keys()) | set(after.keys()))
    for key in all_keys:
        old_value = before.get(key, "")
        new_value = after.get(key, "")
        if old_value == new_value:
            continue
        is_secret = is_secret_key(key)
        changes.append(
            {
                "key": key,
                "change_type": "added" if not old_value and new_value else "removed" if old_value and not new_value else "updated",
                "before": mask_secret(old_value) if is_secret else old_value,
                "after": mask_secret(new_value) if is_secret else new_value,
            }
        )
    return changes


def rotate_secret_token(key: str, new_value: str, *, keep_previous: bool = True) -> dict[str, Any]:
    """
    Rotate one secret token without downtime by updating .env atomically.

    Clients read .env on each request path, so rotation applies immediately.
    """
    token_key = str(key).strip()
    if token_key not in TOKEN_ROTATABLE_KEYS:
        raise ValueError("token_key_not_allowed")
    value = str(new_value).strip()
    if not value:
        raise ValueError("token_value_required")

    env_values = load_env_values()
    previous = env_values.get(token_key, "")
    env_values[token_key] = value
    if keep_previous and previous and previous != value:
        env_values[f"{token_key}_PREVIOUS"] = previous
    save_env_values(env_values)
    return {
        "rotated": True,
        "key": token_key,
        "changed": previous != value,
        "previous_preserved": bool(keep_previous and previous and previous != value),
        "active_value_masked": mask_secret(value),
    }


def get_setting(key: str, default: str = "") -> str:
    """Get one setting from .env with compatibility alias support."""
    values = load_env_values()
    candidates = SETTING_ALIASES.get(key, (key,))
    for candidate in candidates:
        value = values.get(candidate, "")
        if value not in ("", None):
            return str(value)
    return default


def get_setting_any(keys: tuple[str, ...], default: str = "") -> str:
    """Get the first non-empty setting from the provided keys."""
    values = load_env_values()
    for key in keys:
        value = values.get(key, "")
        if value not in ("", None):
            return str(value)
    return default


def get_bool_setting(key: str, default: bool = False) -> bool:
    """Read a boolean setting from .env."""
    raw = get_setting(key, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}
