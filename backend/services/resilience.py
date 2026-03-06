"""Resilience helpers for external API access (circuit breaker + token bucket)."""

from __future__ import annotations

import time
from threading import Lock
from typing import Any

import requests

from backend.services.settings_manager import get_setting

_STATE_LOCK = Lock()
_CIRCUITS: dict[str, dict[str, Any]] = {}
_BUCKETS: dict[str, dict[str, float]] = {}


def _int_setting(primary_key: str, fallback_key: str, default: int, minimum: int) -> int:
    raw = get_setting(primary_key, "").strip() or get_setting(fallback_key, "").strip() or str(default)
    try:
        value = int(raw)
    except ValueError:
        value = default
    return max(minimum, value)


def _float_setting(primary_key: str, fallback_key: str, default: float, minimum: float) -> float:
    raw = get_setting(primary_key, "").strip() or get_setting(fallback_key, "").strip() or str(default)
    try:
        value = float(raw)
    except ValueError:
        value = default
    return max(minimum, value)


def _service_key(service: str) -> str:
    return service.strip().lower().replace("-", "_")


def _circuit_config(service: str) -> tuple[int, int]:
    key = _service_key(service).upper()
    threshold = _int_setting(
        f"CIRCUIT_BREAKER_{key}_FAILURE_THRESHOLD",
        "CIRCUIT_BREAKER_FAILURE_THRESHOLD",
        5,
        1,
    )
    cooldown_seconds = _int_setting(
        f"CIRCUIT_BREAKER_{key}_COOLDOWN_SECONDS",
        "CIRCUIT_BREAKER_COOLDOWN_SECONDS",
        120,
        1,
    )
    return threshold, cooldown_seconds


def _bucket_config(service: str) -> tuple[float, float]:
    key = _service_key(service).upper()
    capacity = _float_setting(
        f"RATE_LIMIT_{key}_CAPACITY",
        "RATE_LIMIT_CAPACITY",
        30.0,
        1.0,
    )
    refill_per_second = _float_setting(
        f"RATE_LIMIT_{key}_REFILL_PER_SECOND",
        "RATE_LIMIT_REFILL_PER_SECOND",
        5.0,
        0.1,
    )
    return capacity, refill_per_second


def _ensure_circuit(service: str) -> dict[str, Any]:
    state = _CIRCUITS.get(service)
    if state is None:
        state = {"failures": 0, "open_until": 0.0, "last_error": ""}
        _CIRCUITS[service] = state
    return state


def _ensure_bucket(service: str) -> dict[str, float]:
    state = _BUCKETS.get(service)
    if state is None:
        capacity, _ = _bucket_config(service)
        now = time.time()
        state = {"tokens": capacity, "updated_at": now}
        _BUCKETS[service] = state
    return state


def is_circuit_open(service: str) -> bool:
    service = _service_key(service)
    now = time.time()
    with _STATE_LOCK:
        state = _ensure_circuit(service)
        return float(state.get("open_until", 0.0)) > now


def _record_success(service: str) -> None:
    service = _service_key(service)
    with _STATE_LOCK:
        state = _ensure_circuit(service)
        state["failures"] = 0
        state["open_until"] = 0.0
        state["last_error"] = ""


def _record_failure(service: str, error_message: str) -> None:
    service = _service_key(service)
    threshold, cooldown_seconds = _circuit_config(service)
    with _STATE_LOCK:
        state = _ensure_circuit(service)
        failures = int(state.get("failures", 0)) + 1
        state["failures"] = failures
        state["last_error"] = error_message[:200]
        if failures >= threshold:
            state["open_until"] = time.time() + float(cooldown_seconds)


def _acquire_bucket_token(service: str) -> None:
    service = _service_key(service)
    capacity, refill_per_second = _bucket_config(service)

    while True:
        wait_seconds = 0.0
        with _STATE_LOCK:
            bucket = _ensure_bucket(service)
            now = time.time()
            elapsed = max(0.0, now - float(bucket.get("updated_at", now)))
            tokens = min(capacity, float(bucket.get("tokens", capacity)) + elapsed * refill_per_second)
            if tokens >= 1.0:
                bucket["tokens"] = tokens - 1.0
                bucket["updated_at"] = now
                return
            missing = 1.0 - tokens
            wait_seconds = missing / refill_per_second
            bucket["tokens"] = tokens
            bucket["updated_at"] = now
        time.sleep(min(max(wait_seconds, 0.01), 1.0))


def resilient_request(
    service: str,
    method: str,
    url: str,
    *,
    timeout: int = 20,
    **kwargs: Any,
) -> requests.Response:
    """
    Execute an HTTP request with basic circuit breaker and rate-limit pacing.

    - Circuit opens after repeated upstream failures.
    - Token bucket pacing avoids burst-rate spikes.
    """
    service = _service_key(service)
    if is_circuit_open(service):
        raise RuntimeError(f"{service}_circuit_open")

    _acquire_bucket_token(service)
    try:
        response = requests.request(method=method, url=url, timeout=timeout, **kwargs)
    except requests.RequestException as exc:
        _record_failure(service, str(exc))
        raise

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "1").strip()
        try:
            wait_seconds = float(retry_after)
        except ValueError:
            wait_seconds = 1.0
        _record_failure(service, "rate_limited")
        time.sleep(min(max(wait_seconds, 0.1), 5.0))
        response.raise_for_status()

    if response.status_code >= 500:
        _record_failure(service, f"http_{response.status_code}")
        response.raise_for_status()

    if response.status_code >= 400:
        response.raise_for_status()

    _record_success(service)
    return response


def get_resilience_snapshot() -> dict[str, Any]:
    """Return current circuit breaker and token bucket states."""
    now = time.time()
    output: dict[str, Any] = {}
    with _STATE_LOCK:
        services = set(_CIRCUITS.keys()) | set(_BUCKETS.keys()) | {"kaseya", "revnue"}
        for service in sorted(services):
            circuit = _ensure_circuit(service)
            bucket = _ensure_bucket(service)
            output[service] = {
                "circuit_open": float(circuit.get("open_until", 0.0)) > now,
                "failures": int(circuit.get("failures", 0)),
                "open_until_epoch": float(circuit.get("open_until", 0.0)),
                "last_error": str(circuit.get("last_error", "")),
                "tokens_available": round(float(bucket.get("tokens", 0.0)), 3),
            }
    return output
