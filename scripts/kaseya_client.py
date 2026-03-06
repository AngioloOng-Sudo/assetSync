"""CLI helper for Kaseya connectivity and asset retrieval."""

from __future__ import annotations

import argparse
import json

from backend.services.kaseya_client import fetch_kaseya_asset_by_identifier, fetch_kaseya_assets


def main() -> None:
    parser = argparse.ArgumentParser(description="Kaseya CLI utility.")
    parser.add_argument("--identifier", help="Optional identifier for single asset lookup.")
    parser.add_argument("--top", type=int, default=100, help="Max assets for list mode.")
    parser.add_argument("--skip", type=int, default=0, help="Offset for list mode.")
    args = parser.parse_args()

    if args.identifier:
        asset = fetch_kaseya_asset_by_identifier(args.identifier)
        print(json.dumps({"asset": asset}, indent=2, ensure_ascii=True))
        return

    assets = fetch_kaseya_assets(top=args.top, skip=args.skip)
    print(json.dumps({"count": len(assets), "items": assets}, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()

