"""Settings manager API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from backend.models.schemas import EnvUpdateRequest
from backend.services.activity_logger import log_activity
from backend.services.settings_manager import get_env_view, update_env_values
from backend.utils.security import sanitize_payload

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/env")
def get_env(reveal_secrets: bool = Query(default=False)) -> dict:
    return get_env_view(reveal_secrets=reveal_secrets)


@router.post("/env")
def update_env(request: EnvUpdateRequest) -> dict:
    sanitized = sanitize_payload(request.values)
    result = update_env_values({str(key): str(value) for key, value in sanitized.items()})
    log_activity(
        level="info",
        category="settings",
        message="Environment values updated.",
        details={"updated_keys": sorted(request.values.keys())},
    )
    return result

