"""Main FastAPI application for the GSIS Asset Sync Platform."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from backend.api.auth import router as auth_router
from backend.api.dashboard import router as dashboard_router
from backend.api.monitoring import router as monitoring_router
from backend.api.settings import router as settings_router
from backend.api.support import router as support_router
from backend.api.sync_status import router as sync_status_router
from backend.api.webhooks import router as webhooks_router
from backend.models.db import bootstrap_storage, get_connection
from backend.services.activity_logger import get_state, log_activity, set_status
from backend.services.mapping_config import ensure_mapping_config
from backend.services.resilience import get_resilience_snapshot
from backend.services.settings_manager import get_bool_setting, get_setting

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = PROJECT_ROOT / "web"

app = FastAPI(
    title="GSIS Asset Sync Platform",
    version="1.0.0",
    description="Synchronizes assets between Kaseya and Strev/Revnue.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
session_secret = (
    get_setting("DASHBOARD_SESSION_SECRET", "").strip()
    or get_setting("WEBHOOK_SHARED_SECRET", "").strip()
    or "gsis-asset-sync-dev-session-secret"
)
try:
    session_max_age = int(get_setting("DASHBOARD_SESSION_TIMEOUT_SECONDS", "1800") or "1800")
except ValueError:
    session_max_age = 1800
session_max_age = max(300, min(session_max_age, 86400))
app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret,
    same_site="lax",
    max_age=session_max_age,
)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; connect-src 'self'; "
        "img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    )
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(monitoring_router)
app.include_router(settings_router)
app.include_router(support_router)
app.include_router(sync_status_router)
app.include_router(webhooks_router)


@app.on_event("startup")
def startup() -> None:
    bootstrap_storage()
    ensure_mapping_config()
    autosync_enabled = get_bool_setting("AUTOSYNC_ENABLED", False)
    set_status("autosync_enabled", autosync_enabled)
    log_activity(
        level="info",
        category="system",
        message="Asset dashboard API started.",
        details={"autosync_enabled": autosync_enabled},
    )


@app.get("/api/health")
def health() -> dict:
    db_ok = True
    try:
        conn = get_connection()
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
    except Exception:
        db_ok = False
    status_state = get_state().get("status", {})
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "gsis-asset-sync-platform",
        "version": "1.0.0",
        "checks": {
            "database": db_ok,
            "worker_heartbeat_at": status_state.get("worker_heartbeat_at"),
            "last_sync_run_at": status_state.get("last_sync_run_at"),
            "circuit_breakers": get_resilience_snapshot(),
        },
    }


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/sync-status", include_in_schema=False)
def sync_status_page() -> FileResponse:
    return FileResponse(WEB_DIR / "sync-status.html")


@app.get("/settings", include_in_schema=False)
def settings_page() -> FileResponse:
    return FileResponse(WEB_DIR / "settings.html")


@app.get("/support", include_in_schema=False)
def support_page() -> FileResponse:
    return FileResponse(WEB_DIR / "support.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
