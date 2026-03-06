from fastapi.testclient import TestClient

from backend.asset_dashboard import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"


def test_settings_mask_and_update():
    post_response = client.post(
        "/api/settings/env",
        json={"values": {"KASEYA_API_TOKEN": "secret-token-123", "AUTOSYNC_ENABLED": "true"}},
    )
    assert post_response.status_code == 200

    get_masked = client.get("/api/settings/env")
    assert get_masked.status_code == 200
    masked_value = get_masked.json()["values"]["KASEYA_API_TOKEN"]
    assert "*" in masked_value

    get_revealed = client.get("/api/settings/env?reveal_secrets=true")
    assert get_revealed.status_code == 200
    assert get_revealed.json()["values"]["KASEYA_API_TOKEN"] == "secret-token-123"


def test_webhook_requires_secret_when_configured():
    client.post("/api/settings/env", json={"values": {"WEBHOOK_SHARED_SECRET": "topsecret"}})

    response = client.post(
        "/api/webhooks/kaseya",
        json={"event_type": "asset.updated", "identifier": "GSIS-001"},
    )
    assert response.status_code == 401

    response_ok = client.post(
        "/api/webhooks/kaseya",
        json={"event_type": "asset.updated", "identifier": "GSIS-001"},
        headers={"x-webhook-secret": "topsecret"},
    )
    assert response_ok.status_code == 200
    assert response_ok.json()["queued"] is True


def test_transfer_and_sync_status():
    transfer_response = client.post("/api/transfer", json={"identifiers": ["GSIS-001", "GSIS-004"]})
    assert transfer_response.status_code == 200
    transfer_payload = transfer_response.json()
    assert transfer_payload["total"] == 2

    sync_response = client.get("/api/sync/status")
    assert sync_response.status_code == 200
    sync_payload = sync_response.json()
    assert "queue_metrics" in sync_payload


def test_requested_alias_endpoints_exist():
    kaseya_response = client.get("/api/kaseya/assets")
    assert kaseya_response.status_code == 200

    revnue_response = client.get("/api/revnue/assets")
    assert revnue_response.status_code == 200

    logs_response = client.get("/api/logs?limit=10")
    assert logs_response.status_code == 200
    assert "channels" in logs_response.json()

    mark_read_response = client.post("/api/logs/mark-read", json={"channels": ["notifications"]})
    assert mark_read_response.status_code == 200
    assert mark_read_response.json()["unread_count"] == 0

    overview_response = client.get("/api/sync/overview?window=1h")
    assert overview_response.status_code == 200
    assert overview_response.json()["window"] == "1h"

    dry_run_response = client.post("/api/sync/dry-run", json={"identifiers": ["GSIS-001"]})
    assert dry_run_response.status_code == 200
    assert dry_run_response.json()["dry_run"] is True

    checks_response = client.get("/api/support/checks")
    assert checks_response.status_code == 200
    assert "results" in checks_response.json()
