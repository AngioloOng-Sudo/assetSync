"""Cron-style schedule window evaluation for autosync execution."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.models.db import utcnow_iso
from backend.services.settings_manager import get_setting


def _cron_now() -> datetime:
    return datetime.now()


def _value_in_field(value: int, field_expr: str, minimum: int, maximum: int) -> bool:
    expr = (field_expr or "*").strip()
    if not expr:
        return True

    for part in expr.split(","):
        token = part.strip()
        if not token:
            continue
        if "/" in token:
            base, step_raw = token.split("/", 1)
            try:
                step = int(step_raw.strip())
            except ValueError:
                return False
            if step <= 0:
                return False
        else:
            base = token
            step = 1

        if base == "*":
            start, end = minimum, maximum
        elif "-" in base:
            left, right = base.split("-", 1)
            try:
                start = int(left.strip())
                end = int(right.strip())
            except ValueError:
                return False
        else:
            try:
                start = end = int(base.strip())
            except ValueError:
                return False

        if start < minimum or end > maximum or start > end:
            return False
        if value < start or value > end:
            continue
        if ((value - start) % step) == 0:
            return True
    return False


def _normalized_weekday(dt: datetime) -> int:
    # Cron: Sunday=0 or 7, Monday=1 ... Saturday=6
    return dt.isoweekday() % 7


def cron_matches(expr: str, now: datetime | None = None) -> bool:
    """Return True when datetime matches one cron expression."""
    dt = now or _cron_now()
    fields = [field for field in expr.strip().split() if field]
    if len(fields) != 5:
        return False

    minute, hour, day, month, weekday = fields
    dow = _normalized_weekday(dt)
    weekday_expr = weekday.replace("7", "0")
    return all(
        [
            _value_in_field(dt.minute, minute, 0, 59),
            _value_in_field(dt.hour, hour, 0, 23),
            _value_in_field(dt.day, day, 1, 31),
            _value_in_field(dt.month, month, 1, 12),
            _value_in_field(dow, weekday_expr, 0, 6),
        ]
    )


def configured_sync_windows() -> list[str]:
    """Return configured cron expressions for autosync windows."""
    raw = get_setting("AUTOSYNC_CRON_WINDOWS", "").strip()
    if not raw:
        return []
    tokens = raw.replace("\n", ";").split(";")
    return [token.strip() for token in tokens if token.strip()]


def is_sync_window_open(now: datetime | None = None) -> bool:
    """
    Return True when autosync should run at current time.

    Empty AUTOSYNC_CRON_WINDOWS means always open.
    """
    windows = configured_sync_windows()
    if not windows:
        return True
    dt = now or _cron_now()
    return any(cron_matches(expr, dt) for expr in windows)


def schedule_status_snapshot(now: datetime | None = None) -> dict[str, Any]:
    """Return schedule window status for APIs/diagnostics."""
    dt = now or _cron_now()
    windows = configured_sync_windows()
    return {
        "enabled": bool(windows),
        "windows": windows,
        "window_open": is_sync_window_open(dt),
        "now_local": dt.isoformat(),
        "now_utc": utcnow_iso(),
    }
