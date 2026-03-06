"""Authentication endpoints for dashboard access control."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from backend.models.schemas import AuthLoginRequest
from backend.services.activity_logger import log_activity
from backend.services.auth_manager import (
    auth_status_payload,
    login_dashboard_session,
    logout_dashboard_session,
    verify_dashboard_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status")
def auth_status(request: Request) -> dict:
    """Return current authentication state."""
    return auth_status_payload(request)


@router.post("/login")
def auth_login(request: Request, payload: AuthLoginRequest) -> dict:
    """Authenticate the current session for protected dashboard operations."""
    if not verify_dashboard_password(payload.password):
        log_activity(level="warning", category="auth", message="Failed dashboard login attempt.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")
    login_dashboard_session(request)
    log_activity(level="info", category="auth", message="Dashboard session authenticated.")
    return auth_status_payload(request)


@router.post("/logout")
def auth_logout(request: Request) -> dict:
    """Log out dashboard session."""
    logout_dashboard_session(request)
    log_activity(level="info", category="auth", message="Dashboard session logged out.")
    return auth_status_payload(request)
