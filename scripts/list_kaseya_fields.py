"""List observed Kaseya asset field names for schema extraction."""

from __future__ import annotations

import json

from backend.services.kaseya_client import fetch_kaseya_assets


def main() -> None:
    assets = fetch_kaseya_assets(top=200, skip=0)
    fields: set[str] = set()
    assetinfo_keys: set[str] = set()
    for asset in assets:
        fields.update(str(key) for key in asset.keys())
        for item in asset.get("assetinfo") or []:
            if isinstance(item, dict) and item.get("key"):
                assetinfo_keys.add(str(item["key"]))
    print(
        json.dumps(
            {
                "asset_field_count": len(fields),
                "asset_fields": sorted(fields),
                "assetinfo_key_count": len(assetinfo_keys),
                "assetinfo_keys": sorted(assetinfo_keys),
            },
            indent=2,
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()

