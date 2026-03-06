"""List Revnue assets with optional filters for validation."""

from __future__ import annotations

import argparse
import json

from backend.services.revnue_client import fetch_revnue_assets


def main() -> None:
    parser = argparse.ArgumentParser(description="List Revnue assets.")
    parser.add_argument("--company", default=None, help="Company id filter.")
    parser.add_argument("--search", default="", help="Search text for serial/tag/name.")
    parser.add_argument("--top", type=int, default=200)
    parser.add_argument("--skip", type=int, default=0)
    args = parser.parse_args()

    assets = fetch_revnue_assets(company=args.company, top=args.top, skip=args.skip)
    search = args.search.strip().lower()
    if search:
        assets = [
            asset
            for asset in assets
            if search in str(asset.get("serial_number", "")).lower()
            or search in str(asset.get("asset_tag", "")).lower()
            or search in str(asset.get("name", "")).lower()
        ]
    print(json.dumps({"count": len(assets), "items": assets}, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()

