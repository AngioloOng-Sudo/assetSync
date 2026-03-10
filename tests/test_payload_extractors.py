from backend.services.kaseya_client import _extract_assets_payload as extract_kaseya_assets_payload
from backend.services.revnue_client import _extract_assets_payload as extract_revnue_assets_payload


def test_kaseya_payload_extractor_handles_nested_case_insensitive_keys():
    payload = {"Result": {"Items": [{"Identifier": "GSIS-001"}]}}
    items, recognized = extract_kaseya_assets_payload(payload)
    assert recognized is True
    assert isinstance(items, list)
    assert items[0]["Identifier"] == "GSIS-001"


def test_revnue_payload_extractor_handles_case_insensitive_results():
    payload = {"RESULTS": [{"serial_number": "GSIS-001"}]}
    items, recognized = extract_revnue_assets_payload(payload)
    assert recognized is True
    assert isinstance(items, list)
    assert items[0]["serial_number"] == "GSIS-001"


def test_payload_extractors_report_unrecognized_shapes():
    items_kaseya, recognized_kaseya = extract_kaseya_assets_payload({"meta": {"total": 5}})
    assert recognized_kaseya is False
    assert items_kaseya == []

    items_revnue, recognized_revnue = extract_revnue_assets_payload({"meta": {"total": 5}})
    assert recognized_revnue is False
    assert items_revnue == []
