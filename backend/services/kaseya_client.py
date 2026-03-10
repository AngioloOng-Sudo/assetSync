"""Kaseya API v3 client with local mock fallback for development."""

from __future__ import annotations

import base64
from typing import Any

import requests
from pydantic import ValidationError

from backend.models.external_schemas import KaseyaAssetModel
from backend.services.activity_logger import log_activity
from backend.services.mock_fixtures import load_fixture_assets
from backend.services.resilience import resilient_request
from backend.services.settings_manager import get_bool_setting, get_setting


def _mock_kaseya_assets() -> list[dict[str, Any]]:
    defaults = [
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
    return load_fixture_assets("MOCK_KASEYA_FIXTURE_PATH", defaults)


def _auth_headers() -> dict[str, str]:
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": get_setting("DEFAULT_USER_AGENT", "gsis-Kaseya-client/1.0"),
    }
    bearer = get_setting("KASEYA_API_TOKEN")
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
        return headers

    token_id = get_setting("KASEYA_TOKEN_ID")
    token_secret = get_setting("KASEYA_TOKEN_SECRET")
    if token_id and token_secret:
        encoded = base64.b64encode(f"{token_id}:{token_secret}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {encoded}"
        return headers

    return headers


def _base_assets_url() -> str:
    explicit_assets_url = get_setting("KASEYA_ASSETS_URL", "").strip()
    if explicit_assets_url:
        return explicit_assets_url.rstrip("/")
    base_url = get_setting("KASEYA_BASE_URL").rstrip("/")
    return f"{base_url}/assets"


def _extract_http_error_message(exc: requests.RequestException) -> str:
    response = getattr(exc, "response", None)
    if response is None:
        return str(exc)
    try:
        payload = response.json()
    except Exception:
        payload = None

    if isinstance(payload, dict):
        meta = payload.get("Meta")
        if isinstance(meta, dict):
            detail = str(meta.get("ErrorMessage") or "").strip()
            if detail:
                return detail
        for key in ("detail", "message", "error"):
            detail = str(payload.get(key) or "").strip()
            if detail:
                return detail

    text = str(getattr(response, "text", "") or "").strip()
    if text:
        return text[:240]
    return str(exc)


def _normalize_assets(items: Any, source: str) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    candidate_items = items if isinstance(items, list) else []
    for raw in candidate_items:
        if not isinstance(raw, dict):
            continue
        try:
            parsed = KaseyaAssetModel.model_validate(raw).model_dump()
            if not parsed.get("assetinfo") and isinstance(parsed.get("AssetInfo"), list):
                parsed["assetinfo"] = parsed.get("AssetInfo")
            parsed.setdefault("detail_source", source)
            normalized.append(parsed)
        except ValidationError as exc:
            log_activity(
                level="warning",
                category="kaseya_client",
                message="Skipped invalid Kaseya asset payload.",
                details={"source": source, "error": str(exc)[:200]},
            )
    return normalized


def _dict_value_case_insensitive(payload: dict[str, Any], target_key: str) -> Any:
    lowered_target = target_key.lower()
    for key, value in payload.items():
        if str(key).lower() == lowered_target:
            return value
    return None


def _extract_assets_payload(payload: Any, depth: int = 0) -> tuple[list[Any], bool]:
    """
    Return candidate list payload plus recognition flag.

    `recognized` tells the caller whether the response shape looks valid,
    even when there are zero assets.
    """
    if depth > 4:
        return [], False
    if isinstance(payload, list):
        return payload, True
    if not isinstance(payload, dict):
        return [], False

    for key in ("items", "value", "data", "results", "assets", "result", "rows", "records", "entityresults"):
        candidate = _dict_value_case_insensitive(payload, key)
        if candidate is None:
            continue
        if isinstance(candidate, list):
            return candidate, True
        if isinstance(candidate, dict):
            nested_items, recognized = _extract_assets_payload(candidate, depth + 1)
            return nested_items, recognized
        return [], True

    # Fallback for uncommon wrappers: if the dict includes any list-like field, try it.
    for value in payload.values():
        if isinstance(value, list):
            return value, True
        if isinstance(value, dict):
            nested_items, recognized = _extract_assets_payload(value, depth + 1)
            if recognized:
                return nested_items, True
    return [], False


def fetch_kaseya_assets(top: int = 100, skip: int = 0) -> list[dict[str, Any]]:
    """Fetch Kaseya assets from API or mock provider (paged)."""
    if get_bool_setting("USE_MOCK_APIS", True):
        assets = _mock_kaseya_assets()
        return _normalize_assets(assets[skip : skip + top], "mock")

    bounded_top = max(1, min(top, 100))
    bounded_skip = max(skip, 0)
    headers = _auth_headers()
    attempts: tuple[dict[str, int], ...] = (
        {"$top": bounded_top, "$skip": bounded_skip},
        {"top": bounded_top, "skip": bounded_skip},
        {},
    )

    last_error: Exception | None = None
    for params in attempts:
        request_kwargs: dict[str, Any] = {"headers": headers, "timeout": 20}
        if params:
            request_kwargs["params"] = params
        try:
            response = resilient_request("kaseya", "GET", _base_assets_url(), **request_kwargs)
            payload = response.json()
            items, recognized = _extract_assets_payload(payload)
            if recognized:
                return _normalize_assets(items, "kaseya_api")
            log_activity(
                level="warning",
                category="kaseya_client",
                message="Kaseya response shape was not recognized.",
                details={
                    "url": _base_assets_url(),
                    "params": params,
                    "payload_type": type(payload).__name__,
                    "payload_keys": list(payload.keys())[:15] if isinstance(payload, dict) else [],
                },
            )
        except requests.RequestException as exc:
            detail = _extract_http_error_message(exc)
            last_error = RuntimeError(f"Kaseya upstream error: {detail}")
            continue

    if last_error:
        raise last_error
    raise RuntimeError("Kaseya upstream response shape not recognized.")


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
    try:
        response = resilient_request(
            "kaseya",
            "GET",
            _base_assets_url(),
            headers=headers,
            params={"$filter": f"Identifier eq '{identifier}'", "$top": 1},
            timeout=20,
        )
    except Exception:
        return None
    payload = response.json()
    items, recognized = _extract_assets_payload(payload)
    if not recognized:
        return None
    normalized = _normalize_assets(items, "filter_lookup")
    return normalized[0] if normalized else None


def _specific_device_lookup(identifier: str) -> dict[str, Any] | None:
    if get_bool_setting("USE_MOCK_APIS", True):
        return None
    headers = _auth_headers()
    try:
        response = resilient_request(
            "kaseya",
            "GET",
            f"{_base_assets_url()}/{identifier}",
            headers=headers,
            timeout=20,
        )
    except Exception:
        return None
    payload = response.json()
    if isinstance(payload, dict):
        normalized = _normalize_assets([payload], "specific_endpoint")
        return normalized[0] if normalized else None
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


def check_kaseya_connectivity() -> dict[str, Any]:
    """Basic Kaseya connectivity check for support tooling."""
    endpoint = _base_assets_url()
    if get_bool_setting("USE_MOCK_APIS", True):
        return {"reachable": True, "mode": "mock", "url": endpoint or "mock", "status_code": 200}

    headers = _auth_headers()
    if not headers.get("Authorization"):
        return {
            "reachable": False,
            "mode": "live",
            "url": endpoint,
            "error": "missing_credentials",
        }

    attempts: tuple[dict[str, int], ...] = (
        {"$top": 1, "$skip": 0},
        {"top": 1, "skip": 0},
        {},
    )

    last_status_code: int | None = None
    last_error = ""
    for params in attempts:
        request_kwargs: dict[str, Any] = {"headers": headers, "timeout": 10}
        if params:
            request_kwargs["params"] = params
        try:
            response = resilient_request("kaseya", "GET", endpoint, **request_kwargs)
            return {
                "reachable": True,
                "mode": "live",
                "url": endpoint,
                "status_code": response.status_code,
            }
        except requests.RequestException as exc:
            detail = _extract_http_error_message(exc)
            response = getattr(exc, "response", None)
            if response is not None and isinstance(getattr(response, "status_code", None), int):
                last_status_code = int(response.status_code)
            last_error = detail or str(exc)
            continue
        except Exception as exc:
            last_error = str(exc)
            continue

    result = {
        "reachable": False,
        "mode": "live",
        "url": endpoint,
        "error": last_error or "request_failed",
    }
    if last_status_code is not None:
        result["status_code"] = last_status_code
    return result
