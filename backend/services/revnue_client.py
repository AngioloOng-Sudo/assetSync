"""Revnue API client with local JSON-backed mock implementation."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from backend.models.db import MOCK_REVNUE_ASSETS_PATH
from backend.models.external_schemas import RevnueAssetModel
from backend.services.activity_logger import log_activity
from backend.services.mock_fixtures import load_fixture_assets
from backend.services.resilience import resilient_request
from backend.services.settings_manager import get_bool_setting, get_setting
from backend.utils.file_io import read_json, write_json


def _load_mock_assets() -> list[dict[str, Any]]:
    assets = read_json(MOCK_REVNUE_ASSETS_PATH, [])
    if get_bool_setting("USE_MOCK_FIXTURE_REPLAY", False):
        needs_seed = not isinstance(assets, list) or not assets
        if needs_seed:
            seeded = load_fixture_assets("MOCK_REVNUE_FIXTURE_PATH", [])
            assets = seeded
            _save_mock_assets(assets if isinstance(assets, list) else [])
    return assets if isinstance(assets, list) else []


def _save_mock_assets(assets: list[dict[str, Any]]) -> None:
    write_json(MOCK_REVNUE_ASSETS_PATH, assets)


def _asset_url() -> str:
    explicit_asset_url = get_setting("REVNUE_ASSET_URL")
    if explicit_asset_url:
        return explicit_asset_url.rstrip("/")
    base_url = get_setting("REVNUE_BASE_URL").rstrip("/")
    return f"{base_url}/assets" if base_url else ""


def _test_url() -> str:
    explicit_test_url = get_setting("REVNUE_TEST_URL")
    if explicit_test_url:
        return explicit_test_url.rstrip("/")
    return _asset_url()


def _headers() -> dict[str, str]:
    token = get_setting("REVNUE_API_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _normalize_assets(items: Any, source: str) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    candidate_items = items if isinstance(items, list) else []
    for raw in candidate_items:
        if not isinstance(raw, dict):
            continue
        try:
            parsed = RevnueAssetModel.model_validate(raw).model_dump()
            normalized.append(parsed)
        except ValidationError as exc:
            log_activity(
                level="warning",
                category="revnue_client",
                message="Skipped invalid Revnue asset payload.",
                details={"source": source, "error": str(exc)[:200]},
            )
    return normalized


def fetch_revnue_assets(
    company: str | int | None = None,
    top: int = 100,
    skip: int = 0,
) -> list[dict[str, Any]]:
    """Fetch Revnue assets (paged)."""
    if get_bool_setting("USE_MOCK_APIS", True):
        assets = _load_mock_assets()
        scoped_assets = [asset for asset in assets if not company or str(asset.get("company")) == str(company)]
        return _normalize_assets(scoped_assets[skip : skip + top], "mock")

    company_value = str(company or get_setting("REVNUE_COMPANY", "1")).strip() or "1"
    response = resilient_request(
        "revnue",
        "GET",
        _asset_url(),
        headers=_headers(),
        params={"company": company_value, "limit": max(1, top), "offset": max(skip, 0)},
        timeout=20,
    )
    payload = response.json()
    if isinstance(payload, list):
        return _normalize_assets(payload, "revnue_api")
    return _normalize_assets(payload.get("items", []), "revnue_api")


def fetch_all_revnue_assets(company: str | int | None = None, page_size: int = 100) -> list[dict[str, Any]]:
    """Fetch all Revnue assets by paginating until exhaustion."""
    if get_bool_setting("USE_MOCK_APIS", True):
        return fetch_revnue_assets(company=company, top=100_000, skip=0)

    all_assets: list[dict[str, Any]] = []
    skip = 0
    for _ in range(200):
        page = fetch_revnue_assets(company=company, top=page_size, skip=skip)
        if not page:
            break
        all_assets.extend(page)
        if len(page) < page_size:
            break
        skip += page_size
    return all_assets


def fetch_revnue_exact_matches(
    company: str | int | None = None,
    identifiers: list[str] | None = None,
    names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return exact identifier matches (serial_number or asset_tag); names are ignored for matching."""
    normalized_ids = [identifier.strip() for identifier in (identifiers or []) if identifier and identifier.strip()]
    if not normalized_ids:
        return []

    _ = names  # Explicitly ignored by business rule.
    assets = fetch_all_revnue_assets(company=company)
    id_set = set(normalized_ids)
    return [asset for asset in assets if asset.get("serial_number") in id_set or asset.get("asset_tag") in id_set]


def upsert_revnue_asset(
    identifier: str,
    mapped_asset: dict[str, Any],
    company: str | int | None = None,
) -> dict[str, Any]:
    """Update existing exact match or create new Revnue asset."""
    identifier = identifier.strip()
    company_value = str(company or mapped_asset.get("company") or get_setting("REVNUE_COMPANY", "1"))
    matches = fetch_revnue_exact_matches(company=company_value, identifiers=[identifier])

    if get_bool_setting("USE_MOCK_APIS", True):
        assets = _load_mock_assets()
        if matches:
            match = matches[0]
            asset_id = match.get("id")
            updated = []
            target: dict[str, Any] | None = None
            for asset in assets:
                if asset.get("id") == asset_id:
                    merged = dict(asset)
                    merged.update(mapped_asset)
                    target = merged
                    updated.append(merged)
                else:
                    updated.append(asset)
            _save_mock_assets(updated)
            return {"action": "updated", "asset": target}

        existing_ids = [int(asset.get("id", 0)) for asset in assets if str(asset.get("id", "")).isdigit()]
        next_id = (max(existing_ids) + 1) if existing_ids else 1
        created = {"id": next_id, "company": company_value, **mapped_asset}
        assets.append(created)
        _save_mock_assets(assets)
        return {"action": "created", "asset": created}

    if matches:
        match = matches[0]
        revnue_id = match.get("id")
        response = resilient_request(
            "revnue",
            "PUT",
            f"{_asset_url().rstrip('/')}/{revnue_id}",
            headers=_headers(),
            json=mapped_asset,
            timeout=20,
        )
        asset = response.json()
        normalized = _normalize_assets([asset], "revnue_update")
        return {"action": "updated", "asset": normalized[0] if normalized else asset}

    response = resilient_request(
        "revnue",
        "POST",
        _asset_url(),
        headers=_headers(),
        json=mapped_asset,
        params={"company": company_value},
        timeout=20,
    )
    asset = response.json()
    normalized = _normalize_assets([asset], "revnue_create")
    return {"action": "created", "asset": normalized[0] if normalized else asset}


def delete_revnue_asset(identifier: str, company: str | int | None = None) -> bool:
    """Delete Revnue asset matched by identifier."""
    identifier = identifier.strip()
    company_value = str(company or get_setting("REVNUE_COMPANY", "1"))
    matches = fetch_revnue_exact_matches(company=company_value, identifiers=[identifier])
    if not matches:
        return False

    if get_bool_setting("USE_MOCK_APIS", True):
        target_id = matches[0].get("id")
        assets = _load_mock_assets()
        filtered = [asset for asset in assets if asset.get("id") != target_id]
        _save_mock_assets(filtered)
        return True

    resilient_request(
        "revnue",
        "DELETE",
        f"{_asset_url().rstrip('/')}/{matches[0].get('id')}",
        headers=_headers(),
        params={"company": company_value},
        timeout=20,
    )
    return True


def delete_revnue_asset_by_id(company: str | int, revnue_id: str | int) -> bool:
    """Delete Revnue asset by explicit Revnue id (helper for CLI/tools)."""
    if get_bool_setting("USE_MOCK_APIS", True):
        target_id = str(revnue_id)
        assets = _load_mock_assets()
        filtered = [asset for asset in assets if str(asset.get("id")) != target_id]
        if len(filtered) == len(assets):
            return False
        _save_mock_assets(filtered)
        return True

    resilient_request(
        "revnue",
        "DELETE",
        f"{_asset_url().rstrip('/')}/{revnue_id}",
        headers=_headers(),
        params={"company": str(company)},
        timeout=20,
    )
    return True


def check_revnue_connectivity() -> dict[str, Any]:
    """Basic Revnue connectivity check for support/CLI."""
    if get_bool_setting("USE_MOCK_APIS", True):
        return {"reachable": True, "mode": "mock", "url": _test_url(), "status_code": 200}

    try:
        response = resilient_request("revnue", "GET", _test_url(), headers=_headers(), timeout=10)
        return {
            "reachable": response.ok,
            "mode": "live",
            "url": _test_url(),
            "status_code": response.status_code,
        }
    except Exception as exc:  # pragma: no cover - network failure path
        return {"reachable": False, "mode": "live", "url": _test_url(), "error": str(exc)}
