"""Parallel snapshot fetch helpers for Kaseya and Revnue APIs."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from backend.services.kaseya_client import fetch_kaseya_assets
from backend.services.revnue_client import fetch_all_revnue_assets


def fetch_asset_snapshots_parallel() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch Kaseya and Revnue snapshots in parallel threads."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        kaseya_future = pool.submit(fetch_kaseya_assets, 100_000, 0)
        revnue_future = pool.submit(fetch_all_revnue_assets, None)
        kaseya_assets = kaseya_future.result()
        revnue_assets = revnue_future.result()
    return kaseya_assets, revnue_assets


async def fetch_asset_snapshots_async() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch Kaseya and Revnue snapshots concurrently using async thread offload."""
    kaseya_task = asyncio.to_thread(fetch_kaseya_assets, 100_000, 0)
    revnue_task = asyncio.to_thread(fetch_all_revnue_assets, None)
    kaseya_assets, revnue_assets = await asyncio.gather(kaseya_task, revnue_task)
    return kaseya_assets, revnue_assets
