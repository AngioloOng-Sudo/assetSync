import hashlib
import hmac
import json

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


def test_settings_auth_flow_when_password_is_configured():
    configure_response = client.post(
        "/api/settings/env",
        json={"values": {"DASHBOARD_PASSWORD": "letmein123"}},
    )
    assert configure_response.status_code == 200

    locked_response = client.get("/api/settings/env")
    assert locked_response.status_code == 401

    auth_status = client.get("/api/auth/status")
    assert auth_status.status_code == 200
    assert auth_status.json()["required"] is True
    assert auth_status.json()["authenticated"] is False

    failed_login = client.post("/api/auth/login", json={"password": "wrong-password"})
    assert failed_login.status_code == 401

    success_login = client.post("/api/auth/login", json={"password": "letmein123"})
    assert success_login.status_code == 200
    assert success_login.json()["authenticated"] is True

    unlocked_response = client.get("/api/settings/env")
    assert unlocked_response.status_code == 200

    logout_response = client.post("/api/auth/logout")
    assert logout_response.status_code == 200
    assert logout_response.json()["authenticated"] is False


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


def test_webhook_accepts_hmac_signature():
    client.post("/api/settings/env", json={"values": {"WEBHOOK_SHARED_SECRET": "supersecret"}})
    payload = {"event_type": "asset.updated", "identifier": "GSIS-009"}
    body = json.dumps(payload).encode("utf-8")
    signature = hmac.new(b"supersecret", body, hashlib.sha256).hexdigest()
    response = client.post(
        "/api/webhooks/kaseya",
        json=payload,
        headers={"x-webhook-signature": signature},
    )
    assert response.status_code == 200
    assert response.json()["queued"] is True


def test_transfer_and_sync_status():
    transfer_response = client.post("/api/transfer", json={"identifiers": ["GSIS-001", "GSIS-004"]})
    assert transfer_response.status_code == 200
    transfer_payload = transfer_response.json()
    assert transfer_payload["total"] == 2

    sync_response = client.get("/api/sync/status")
    assert sync_response.status_code == 200
    sync_payload = sync_response.json()
    assert "queue_metrics" in sync_payload

    run_now_response = client.post("/api/sync/run-now", json={"force": True, "process_limit": 50})
    assert run_now_response.status_code == 200
    assert "processed" in run_now_response.json()

    audit_response = client.get("/api/sync/audit?limit=5")
    assert audit_response.status_code == 200
    assert isinstance(audit_response.json()["items"], list)


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


def test_monitoring_metrics_endpoint():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "gsis_sync_events_total" in response.text


def test_dashboard_csv_export_endpoint():
    response = client.get("/api/assets/export.csv")
    assert response.status_code == 200
    assert "identifier,match_status" in response.text


def test_webhook_deduplication_window():
    client.post("/api/settings/env", json={"values": {"WEBHOOK_SHARED_SECRET": "topsecret"}})
    payload = {"event_type": "asset.updated", "identifier": "GSIS-001"}
    first = client.post("/api/webhooks/kaseya", json=payload, headers={"x-webhook-secret": "topsecret"})
    second = client.post("/api/webhooks/kaseya", json=payload, headers={"x-webhook-secret": "topsecret"})
    assert first.status_code == 200
    assert first.json()["queued"] is True
    assert second.status_code == 200
    assert second.json()["deduplicated"] is True


def test_sync_schedule_and_events_stream_endpoints():
    schedule_response = client.get("/api/sync/schedule")
    assert schedule_response.status_code == 200
    assert "window_open" in schedule_response.json()

    client.post("/api/transfer", json={"identifiers": ["GSIS-001"]})
    events_response = client.get("/api/sync/events?limit=20")
    assert events_response.status_code == 200
    assert isinstance(events_response.json()["items"], list)


def test_token_rotation_and_mapping_config_endpoints():
    rotate = client.post(
        "/api/settings/tokens/rotate",
        json={"key": "REVNUE_TOKEN", "value": "rotated-token-abc", "keep_previous": True},
    )
    assert rotate.status_code == 200
    assert rotate.json()["rotated"] is True

    mapping_get = client.get("/api/settings/mapping")
    assert mapping_get.status_code == 200
    config = mapping_get.json()["config"]
    config["version"] = int(config.get("version", 1)) + 1
    mapping_post = client.post("/api/settings/mapping", json={"config": config})
    assert mapping_post.status_code == 200
    assert mapping_post.json()["config"]["version"] == config["version"]
