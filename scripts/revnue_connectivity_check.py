"""CLI connectivity check for Strev/Revnue."""

from __future__ import annotations

import json

from backend.services.revnue_client import check_revnue_connectivity


def main() -> None:
    print(json.dumps(check_revnue_connectivity(), indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()

