# GSIS Asset Sync Platform

Implementation of the SOP-defined system that synchronizes assets between Kaseya and Strev/Revnue.

## Stack
- Backend: Python 3.11+, FastAPI, SQLite, JSONL
- Frontend: Vanilla JS, HTML, CSS
- Ops: Docker, nginx, systemd worker, GitHub Actions CI

## Quick Start (Local)
1. Install dependencies:
   - `py -3.11 -m pip install -r requirements-dev.txt`
2. Start API server:
   - `py -3.11 -m uvicorn backend.asset_dashboard:app --reload`
3. Optional worker:
   - `py -3.11 -m backend.workers.autosync_worker`
4. Open:
    - `http://127.0.0.1:8000/`

## Core Environment Variables
- `REVNUE_TOKEN`
- `REVNUE_TEST_URL`
- `REVNUE_ASSET_URL`
- `REVNUE_COMPANY`
- `REVNUE_API_TOKEN` (alias-compatible with `REVNUE_TOKEN`)
- `KASEYA_TOKEN_ID`
- `KASEYA_TOKEN_SECRET`
- `KASEYA_API_TOKEN` (optional bearer auth)
- `WEBHOOK_SHARED_SECRET`
- `DEFAULT_USER_AGENT`
- `KASEYA_BASE_URL`
- `KASEYA_ASSETS_URL` (optional override)
- `USE_MOCK_APIS`
- `USE_MOCK_FIXTURE_REPLAY`
- `MOCK_KASEYA_FIXTURE_PATH`
- `MOCK_REVNUE_FIXTURE_PATH`
- `AUTOSYNC_ENABLED`
- `AUTOSYNC_INTERVAL_SECONDS`
- `AUTOSYNC_MAX_INTERVAL_SECONDS`
- `AUTOSYNC_CRON_WINDOWS`
- `EVENT_DEDUP_WINDOW_SECONDS`
- `DASHBOARD_PASSWORD` or `DASHBOARD_PASSWORD_HASH`
- `DASHBOARD_SESSION_SECRET`
- `DASHBOARD_SESSION_TIMEOUT_SECONDS`
- `OUTBOUND_WEBHOOK_URL`
- `OUTBOUND_WEBHOOK_TIMEOUT_SECONDS`
- `CIRCUIT_BREAKER_FAILURE_THRESHOLD`
- `CIRCUIT_BREAKER_COOLDOWN_SECONDS`
- `RATE_LIMIT_CAPACITY`
- `RATE_LIMIT_REFILL_PER_SECOND`

## API Contracts
- Dashboard: `GET /api/kaseya/assets`, `GET /api/revnue/assets`, `POST /api/transfer`, `GET /api/assets/export.csv`
- Autosync: `GET /api/sync/status`, `GET /api/sync/overview`, `GET /api/sync/audit`, `GET /api/sync/events`, `GET /api/sync/schedule`, `POST /api/sync/reconcile`, `POST /api/sync/run-now`, `POST /api/sync/dry-run`, `POST /api/webhooks/kaseya`
- Logs: `GET /api/logs`, `POST /api/logs/mark-read`
- Auth: `GET /api/auth/status`, `POST /api/auth/login`, `POST /api/auth/logout`
- Settings: `GET /api/settings/env`, `POST /api/settings/env`, `POST /api/settings/tokens/rotate`, `GET /api/settings/mapping`, `POST /api/settings/mapping`
- Support: `GET /api/support/diagnostics`, `GET /api/support/checks`, `GET /api/support/tickets`, `POST /api/support/tickets`, `POST /api/support/notifications/test`
- Monitoring: `GET /metrics`, `GET /api/health`

## CLI Utilities
- `python scripts/kaseya_client.py`
- `powershell -File scripts/get_kaseya_assets.ps1`
- `python scripts/revnue_connectivity_check.py`
- `python scripts/list_kaseya_fields.py`
- `python scripts/list_revnue_assets.py`
- `python scripts/sync_kaseya_to_revnue.py --identifiers GSIS-001 --live`

## Project Structure
- `backend/` API, services, workers, models, utils
- `web/` dashboard pages and frontend scripts
- `docs/` charter, architecture, requirements, API, runbook
- `scripts/` helper scripts for run/maintenance
- `tests/` unit/integration/API/frontend tests

## SOP Checklist
- See `IMPLEMENTATION_CHECKLIST.md`
