"""Settings manager API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from backend.models.schemas import EnvUpdateRequest, MappingConfigUpdateRequest, TokenRotateRequest
from backend.services.activity_logger import log_activity
from backend.services.auth_manager import require_dashboard_auth
from backend.services.mapping_config import load_mapping_config, save_mapping_config
from backend.services.settings_manager import (
    get_env_view,
    load_env_values,
    rotate_secret_token,
    summarize_env_changes,
    update_env_values,
)
from backend.utils.security import sanitize_payload

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/env")
def get_env(request: Request, reveal_secrets: bool = Query(default=False)) -> dict:
    require_dashboard_auth(request)
    return get_env_view(reveal_secrets=reveal_secrets)


@router.post("/env")
def update_env(http_request: Request, request: EnvUpdateRequest) -> dict:
    require_dashboard_auth(http_request)
    before_values = load_env_values()
    sanitized = sanitize_payload(request.values)
    result = update_env_values({str(key): str(value) for key, value in sanitized.items()})
    after_values = load_env_values()
    changes = summarize_env_changes(before_values, after_values)
    actor = (http_request.client.host if http_request.client else "unknown").strip() or "unknown"
    log_activity(
        level="info",
        category="settings",
        message="Environment values updated.",
        details={
            "actor": actor,
            "updated_keys": sorted(request.values.keys()),
            "change_count": len(changes),
            "changes": changes,
        },
    )
    return result


@router.post("/tokens/rotate")
def rotate_token(http_request: Request, request: TokenRotateRequest) -> dict:
    """Rotate one configured token/secret without restarting the app."""
    require_dashboard_auth(http_request)
    actor = (http_request.client.host if http_request.client else "unknown").strip() or "unknown"
    try:
        result = rotate_secret_token(request.key, request.value, keep_previous=request.keep_previous)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    log_activity(
        level="info",
        category="settings",
        message="Secret token rotated.",
        details={"actor": actor, "key": request.key, "previous_preserved": result.get("previous_preserved")},
    )
    return result


@router.get("/mapping")
def get_mapping_config(http_request: Request) -> dict:
    """Return external mapping configuration."""
    require_dashboard_auth(http_request)
    return {"config": load_mapping_config()}


@router.post("/mapping")
def update_mapping_config(http_request: Request, request: MappingConfigUpdateRequest) -> dict:
    """Update external mapping configuration."""
    require_dashboard_auth(http_request)
    actor = (http_request.client.host if http_request.client else "unknown").strip() or "unknown"
    config = save_mapping_config(sanitize_payload(request.config))
    log_activity(
        level="info",
        category="settings",
        message="Field mapping configuration updated.",
        details={"actor": actor, "version": config.get("version")},
    )
    return {"config": config}
