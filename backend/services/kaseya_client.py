"""Kaseya API v3 client with local mock fallback for development."""

from __future__ import annotations

import base64
from typing import Any

import requests

from backend.services.settings_manager import get_bool_setting, get_setting


def _mock_kaseya_assets() -> list[dict[str, Any]]:
    return [
        {
            "Identifier": "GSIS-001",
            "Name": "Finance-Laptop-01",
            "Manufacturer": "Dell",
            "Model": "Latitude 5440",
            "ModifiedDate": "2026-03-05T06:15:00Z",
            "assetinfo": [{"key": "department", "value": "Finance"}],
            "detail_source": "mock_kaseya",
        },
        {
            "Identifier": "GSIS-002",
            "Name": "HR-Laptop-02",
            "Manufacturer": "Lenovo",
            "Model": "ThinkPad T14",
            "ModifiedDate": "2026-03-05T08:25:00Z",
            "assetinfo": [{"key": "department", "value": "HR"}],
            "detail_source": "mock_kaseya",
        },
        {
            "Identifier": "GSIS-003",
            "Name": "Ops-Desktop-03",
            "Manufacturer": "HP",
            "Model": "EliteDesk 800",
            "ModifiedDate": "2026-03-06T01:05:00Z",
            "assetinfo": [],
            "detail_source": "mock_kaseya",
        },
        {
            "Identifier": "GSIS-004",
            "Name": "",
            "Manufacturer": "Acer",
            "Model": "TravelMate",
            "ModifiedDate": "2026-03-06T02:12:00Z",
            "assetinfo": [],
            "detail_source": "mock_kaseya",
        },
    ]


def _auth_headers() -> dict[str, str]:
    bearer = get_setting("KASEYA_API_TOKEN")
    if bearer:
        return {"Authorization": f"Bearer {bearer}"}

    token_id = get_setting("KASEYA_TOKEN_ID")
    token_secret = get_setting("KASEYA_TOKEN_SECRET")
    if token_id and token_secret:
        encoded = base64.b64encode(f"{token_id}:{token_secret}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {encoded}"}

    return {}


def _base_assets_url() -> str:
    base_url = get_setting("KASEYA_BASE_URL").rstrip("/")
    return f"{base_url}/assets"


def fetch_kaseya_assets(top: int = 100, skip: int = 0) -> list[dict[str, Any]]:
    """Fetch Kaseya assets from API or mock provider (paged)."""
    if get_bool_setting("USE_MOCK_APIS", True):
        assets = _mock_kaseya_assets()
        return assets[skip : skip + top]

    headers = _auth_headers()
    response = requests.get(
        _base_assets_url(),
        headers=headers,
        params={"$top": max(1, min(top, 100)), "$skip": max(skip, 0)},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, list):
        return payload
    return payload.get("items", [])


def fetch_all_kaseya_assets(page_size: int = 100, max_pages: int = 100) -> list[dict[str, Any]]:
    """Fetch all Kaseya assets using paged retrieval."""
    if get_bool_setting("USE_MOCK_APIS", True):
        return _mock_kaseya_assets()

    all_assets: list[dict[str, Any]] = []
    skip = 0
    for _ in range(max_pages):
        page = fetch_kaseya_assets(top=page_size, skip=skip)
        if not page:
            break
        all_assets.extend(page)
        if len(page) < page_size:
            break
        skip += page_size
    return all_assets


def _filter_lookup(identifier: str) -> dict[str, Any] | None:
    if get_bool_setting("USE_MOCK_APIS", True):
        return None
    headers = _auth_headers()
    response = requests.get(
        _base_assets_url(),
        headers=headers,
        params={"$filter": f"Identifier eq '{identifier}'", "$top": 1},
        timeout=20,
    )
    if response.status_code >= 400:
        return None
    payload = response.json()
    items = payload if isinstance(payload, list) else payload.get("items", [])
    return items[0] if items else None


def _specific_device_lookup(identifier: str) -> dict[str, Any] | None:
    if get_bool_setting("USE_MOCK_APIS", True):
        return None
    headers = _auth_headers()
    response = requests.get(f"{_base_assets_url()}/{identifier}", headers=headers, timeout=20)
    if response.status_code == 404:
        return None
    if response.status_code >= 400:
        return None
    payload = response.json()
    if isinstance(payload, dict):
        return payload
    return None


def fetch_kaseya_asset_by_identifier(identifier: str) -> dict[str, Any] | None:
    """
    Fetch one Kaseya asset by identifier.

    Detail resolver order:
    1) unpaged list source
    2) filter lookup
    3) specific-device endpoint
    4) paged list fallback
    """
    identifier = identifier.strip()
    if not identifier:
        return None

    # 1) unpaged list source (primary)
    from_unpaged = next(
        (asset for asset in fetch_all_kaseya_assets(page_size=100, max_pages=1) if asset.get("Identifier") == identifier),
        None,
    )
    if from_unpaged:
        result = dict(from_unpaged)
        result["detail_source"] = "unpaged_list"
        return result

    # 2) filter lookup
    from_filter = _filter_lookup(identifier)
    if from_filter:
        result = dict(from_filter)
        result["detail_source"] = "filter_lookup"
        return result

    # 3) specific-device endpoint candidates
    from_specific = _specific_device_lookup(identifier)
    if from_specific:
        result = dict(from_specific)
        result["detail_source"] = "specific_endpoint"
        return result

    # 4) paged list fallback
    from_paged = next(
        (asset for asset in fetch_all_kaseya_assets(page_size=100, max_pages=100) if asset.get("Identifier") == identifier),
        None,
    )
    if from_paged:
        result = dict(from_paged)
        result["detail_source"] = "paged_list"
        return result
    return None
