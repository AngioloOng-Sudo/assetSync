"""Session-based dashboard authentication utilities."""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

from fastapi import HTTPException, Request, status

from backend.services.settings_manager import get_setting


def _session_timeout_seconds() -> int:
    raw = get_setting("DASHBOARD_SESSION_TIMEOUT_SECONDS", "1800").strip() or "1800"
    try:
        value = int(raw)
    except ValueError:
        value = 1800
    return max(300, min(value, 86400))


def _password_config() -> tuple[str, str]:
    plain = get_setting("DASHBOARD_PASSWORD", "").strip()
    hashed = get_setting("DASHBOARD_PASSWORD_HASH", "").strip().lower()
    return plain, hashed


def is_auth_required() -> bool:
    """Return True when dashboard auth has been configured."""
    plain, hashed = _password_config()
    return bool(plain or hashed)


def verify_dashboard_password(password: str) -> bool:
    """Verify submitted password against plain or sha256 hash settings."""
    plain, hashed = _password_config()
    if not (plain or hashed):
        return True
    provided = password or ""
    if hashed:
        digest = hashlib.sha256(provided.encode("utf-8")).hexdigest()
        return hmac.compare_digest(digest, hashed)
    return hmac.compare_digest(provided, plain)


def login_dashboard_session(request: Request) -> None:
    """Mark the request session as authenticated."""
    now = int(time.time())
    request.session["dashboard_authenticated"] = True
    request.session["dashboard_authenticated_at"] = now


def logout_dashboard_session(request: Request) -> None:
    """Clear dashboard authentication from the current session."""
    request.session.clear()


def is_dashboard_authenticated(request: Request) -> bool:
    """Return True when the current session is authenticated and not expired."""
    if not is_auth_required():
        return True
    if not bool(request.session.get("dashboard_authenticated")):
        return False
    authenticated_at = request.session.get("dashboard_authenticated_at")
    try:
        auth_epoch = int(authenticated_at)
    except (TypeError, ValueError):
        logout_dashboard_session(request)
        return False
    if auth_epoch <= 0:
        logout_dashboard_session(request)
        return False
    if int(time.time()) - auth_epoch > _session_timeout_seconds():
        logout_dashboard_session(request)
        return False
    request.session["dashboard_authenticated_at"] = int(time.time())
    return True


def require_dashboard_auth(request: Request) -> None:
    """Raise 401 when dashboard authentication is required but missing."""
    if is_dashboard_authenticated(request):
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="settings_auth_required",
    )


def auth_status_payload(request: Request) -> dict[str, Any]:
    """Build auth status payload for frontend clients."""
    required = is_auth_required()
    return {
        "required": required,
        "authenticated": is_dashboard_authenticated(request),
        "session_timeout_seconds": _session_timeout_seconds() if required else 0,
    }
