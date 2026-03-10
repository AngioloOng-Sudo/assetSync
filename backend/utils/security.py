"""Security and input hygiene utilities."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

SECRET_KEYWORDS = ("TOKEN", "SECRET", "PASSWORD", "KEY")


def sanitize_text(value: str) -> str:
    """Trim and remove null bytes from text input."""
    return value.replace("\x00", "").strip()


def sanitize_payload(payload: Any) -> Any:
    """Recursively sanitize payload values."""
    if isinstance(payload, str):
        return sanitize_text(payload)
    if isinstance(payload, list):
        return [sanitize_payload(item) for item in payload]
    if isinstance(payload, dict):
        return {sanitize_text(str(key)): sanitize_payload(value) for key, value in payload.items()}
    return payload


def is_secret_key(key: str) -> bool:
    """Return True for keys that should be treated as secrets."""
    uppercase_key = key.upper()
    return any(keyword in uppercase_key for keyword in SECRET_KEYWORDS)


def mask_secret(value: str) -> str:
    """Mask a secret value while keeping short shape visibility."""
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


def mask_env_values(values: dict[str, str], reveal_secrets: bool = False) -> dict[str, str]:
    """Mask secret-like values unless reveal_secrets is requested."""
    if reveal_secrets:
        return dict(values)
    masked: dict[str, str] = {}
    for key, value in values.items():
        masked[key] = mask_secret(value) if is_secret_key(key) else value
    return masked


def validate_webhook_secret(provided_secret: str | None, expected_secret: str | None) -> bool:
    """Simple secret equality check for webhook validation."""
    if not expected_secret:
        # Allow local development when no secret is configured.
        return True
    return bool(provided_secret and provided_secret == expected_secret)


def validate_webhook_hmac_signature(
    raw_body: bytes,
    provided_signature: str | None,
    expected_secret: str | None,
) -> bool:
    """
    Validate webhook HMAC signature.

    Accepts header formats:
    - `sha256=<hex>`
    - `<hex>`
    """
    if not expected_secret:
        return True
    if not provided_signature:
        return False
    signature = provided_signature.strip()
    if "=" in signature:
        _, signature = signature.split("=", 1)
    normalized_signature = signature.lower()

    def _matches(body: bytes) -> bool:
        digest = hmac.new(expected_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(normalized_signature, digest.lower())

    if _matches(raw_body):
        return True

    # Some clients compute signatures from equivalent JSON with different whitespace.
    # Accept those canonical variants to keep integrations resilient.
    try:
        parsed = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return False

    candidates = [
        json.dumps(parsed, ensure_ascii=True).encode("utf-8"),
        json.dumps(parsed, ensure_ascii=True, separators=(",", ":")).encode("utf-8"),
    ]
    return any(_matches(candidate) for candidate in candidates)
