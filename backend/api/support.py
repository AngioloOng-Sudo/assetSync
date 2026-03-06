"""Support diagnostics and ticket APIs."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from backend.models.schemas import ConnectivityCheckRequest, SupportTicketRequest
from backend.services.activity_logger import log_activity
from backend.services.support_module import (
    create_ticket,
    export_diagnostics,
    export_diagnostics_json,
    list_tickets,
    run_connectivity_checks,
    run_support_maintenance,
    send_test_outbound_notification,
    system_health_snapshot,
)
from backend.utils.security import sanitize_payload

router = APIRouter(prefix="/api/support", tags=["support"])


@router.get("/health")
def get_health_snapshot() -> dict:
    return system_health_snapshot()


@router.post("/connectivity")
def connectivity_checks(request: ConnectivityCheckRequest | None = None) -> dict:
    targets = request.targets if request else None
    return {"results": run_connectivity_checks(targets)}


@router.get("/checks")
def connectivity_checks_get() -> dict:
    return {"results": run_connectivity_checks(None)}


@router.post("/tickets")
def submit_ticket(request: SupportTicketRequest) -> dict:
    payload = sanitize_payload(request.model_dump())
    ticket = create_ticket(payload)
    log_activity(
        level="info",
        category="support",
        message="Support ticket submitted.",
        details={"ticket_id": ticket["id"], "title": ticket["title"]},
    )
    return ticket


@router.get("/tickets")
def get_tickets(limit: int = Query(default=100, ge=1, le=500)) -> dict:
    return {"items": list_tickets(limit=limit)}


@router.get("/diagnostics")
def get_diagnostics() -> dict:
    return export_diagnostics()


@router.get("/diagnostics/export", response_class=PlainTextResponse)
def download_diagnostics() -> str:
    return export_diagnostics_json()


@router.post("/maintenance")
def support_maintenance() -> dict:
    return run_support_maintenance()


@router.post("/notifications/test")
def test_outbound_notification() -> dict:
    return send_test_outbound_notification()
