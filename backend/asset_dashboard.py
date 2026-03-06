"""Main FastAPI application for the GSIS Asset Sync Platform."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api.dashboard import router as dashboard_router
from backend.api.settings import router as settings_router
from backend.api.support import router as support_router
from backend.api.sync_status import router as sync_status_router
from backend.api.webhooks import router as webhooks_router
from backend.models.db import bootstrap_storage
from backend.services.activity_logger import log_activity, set_status
from backend.services.settings_manager import get_bool_setting

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

app.include_router(dashboard_router)
app.include_router(settings_router)
app.include_router(support_router)
app.include_router(sync_status_router)
app.include_router(webhooks_router)


@app.on_event("startup")
def startup() -> None:
    bootstrap_storage()
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
    return {"status": "ok", "service": "gsis-asset-sync-platform", "version": "1.0.0"}


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

