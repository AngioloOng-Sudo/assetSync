from backend.services.revnue_client import fetch_revnue_assets
from backend.services.transfer_engine import transfer_kaseya_assets_to_revnue


def test_transfer_creates_assets_and_marks_partial():
    result = transfer_kaseya_assets_to_revnue()
    summary = result["summary"]
    # Mock Kaseya data has 4 assets; one is intentionally incomplete.
    assert result["total"] == 4
    assert summary["created"] >= 1
    assert summary["partial"] >= 1

    assets = fetch_revnue_assets()
    identifiers = {asset.get("serial_number") for asset in assets}
    assert "GSIS-001" in identifiers
    created_asset = next(asset for asset in assets if asset.get("serial_number") == "GSIS-001")
    assert str(created_asset.get("company")) == "1"
    assert created_asset.get("category", {}).get("id") == 25


def test_transfer_update_path():
    first = transfer_kaseya_assets_to_revnue(["GSIS-001"])
    assert first["summary"]["created"] == 1
    second = transfer_kaseya_assets_to_revnue(["GSIS-001"])
    assert second["summary"]["updated"] == 1
