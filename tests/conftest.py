from __future__ import annotations

from pathlib import Path

import pytest

from backend.models.db import (
    ACTIVITY_LOG_PATH,
    ACTIVITY_STATE_PATH,
    DB_PATH,
    MOCK_REVNUE_ASSETS_PATH,
    SUPPORT_TICKETS_PATH,
    bootstrap_storage,
)
from backend.services.settings_manager import load_env_values, save_env_values


@pytest.fixture(autouse=True)
def reset_local_storage():
    original_env = load_env_values()

    for file_path in [
        DB_PATH,
        ACTIVITY_LOG_PATH,
        ACTIVITY_STATE_PATH,
        SUPPORT_TICKETS_PATH,
        MOCK_REVNUE_ASSETS_PATH,
    ]:
        if file_path.exists():
            file_path.unlink()

    bootstrap_storage()
    save_env_values(
        {
            "USE_MOCK_APIS": "true",
            "AUTOSYNC_ENABLED": "false",
            "AUTOSYNC_INTERVAL_SECONDS": "15",
            "WEBHOOK_SHARED_SECRET": "",
            "KASEYA_BASE_URL": "https://kaseya.example/api/v3",
            "KASEYA_API_TOKEN": "",
            "KASEYA_TOKEN_ID": "demo-token-id",
            "KASEYA_TOKEN_SECRET": "demo-token-secret",
            "REVNUE_BASE_URL": "https://revnue.example/api",
            "REVNUE_API_TOKEN": "",
            "REVNUE_TOKEN": "",
            "REVNUE_TEST_URL": "https://api.dashboard.strev.ai/api/v2/contractids/?company=1",
            "REVNUE_ASSET_URL": "https://api.dashboard.strev.ai/api/v2/asset",
            "REVNUE_COMPANY": "1",
        }
    )

    yield

    save_env_values(original_env)


@pytest.fixture()
def web_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "web"
