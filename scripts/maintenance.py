"""Maintenance script for routine cleanup and health checks."""

from __future__ import annotations

import argparse
import json

from backend.models.db import cleanup_events
from backend.services.support_module import run_support_maintenance, system_health_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Run GSIS Asset Sync maintenance tasks.")
    parser.add_argument("--cleanup-days", type=int, default=30, help="Retention days for processed sync events.")
    args = parser.parse_args()

    cleaned = cleanup_events(days=args.cleanup_days)
    maintenance = run_support_maintenance()
    health = system_health_snapshot()

    print(
        json.dumps(
            {
                "cleaned_events": cleaned,
                "maintenance": maintenance,
                "health": {
                    "timestamp": health["timestamp"],
                    "storage": health["storage"],
                    "sync_status": health["sync_status"],
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

