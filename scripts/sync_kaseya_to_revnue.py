"""CLI transfer helper with dry-run/live options."""

from __future__ import annotations

import argparse
import json

from backend.services.transfer_engine import transfer_kaseya_assets_to_revnue


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Kaseya assets to Revnue.")
    parser.add_argument(
        "--identifiers",
        default="",
        help="Comma-separated Kaseya identifiers. Empty means all assets.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Execute live writes. Default mode is dry-run.",
    )
    args = parser.parse_args()

    identifiers = [value.strip() for value in args.identifiers.split(",") if value.strip()]
    result = transfer_kaseya_assets_to_revnue(identifiers or None, dry_run=not args.live)
    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()

