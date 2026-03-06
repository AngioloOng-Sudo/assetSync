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
- `KASEYA_TOKEN_ID`
- `KASEYA_TOKEN_SECRET`
- `WEBHOOK_SHARED_SECRET`
- `USE_MOCK_APIS`
- `AUTOSYNC_ENABLED`
- `AUTOSYNC_INTERVAL_SECONDS`

## API Contracts
- Dashboard: `GET /api/kaseya/assets`, `GET /api/revnue/assets`, `POST /api/transfer`
- Autosync: `GET /api/sync/status`, `GET /api/sync/overview`, `POST /api/sync/reconcile`, `POST /api/sync/dry-run`, `POST /api/webhooks/kaseya`
- Logs: `GET /api/logs`, `POST /api/logs/mark-read`
- Settings: `GET /api/settings/env`, `POST /api/settings/env`
- Support: `GET /api/support/diagnostics`, `GET /api/support/checks`, `GET /api/support/tickets`, `POST /api/support/tickets`

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
