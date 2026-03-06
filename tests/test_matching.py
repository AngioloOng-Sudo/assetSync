from backend.services.matching import compare_assets, find_exact_match


def test_matching_uses_identifier_only():
    kaseya_asset = {"Identifier": "ABC-123", "Name": "Laptop A"}
    revnue_assets = [
        {"id": 1, "serial_number": "ABC-123", "asset_tag": "TAG-1", "name": "Different name"},
        {"id": 2, "serial_number": "XYZ-987", "asset_tag": "Laptop A", "name": "Laptop A"},
    ]

    match = find_exact_match(kaseya_asset, revnue_assets)
    assert match is not None
    assert match["id"] == 1


def test_compare_assets_returns_missing_status():
    kaseya_assets = [{"Identifier": "NO-MATCH"}]
    revnue_assets = [{"serial_number": "SER-1", "asset_tag": "TAG-1"}]
    compared = compare_assets(kaseya_assets, revnue_assets)
    assert compared[0]["match_status"] == "missing_in_revnue"
    assert compared[0]["matching_rule"] == "identifier_to_serial_or_asset_tag_only"

