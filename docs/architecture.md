# Architecture Document

## High-Level Flow
Frontend UI -> FastAPI backend (`backend/asset_dashboard.py`) -> Service layer -> External APIs (or mock mode) + Local storage.

## Components
- Frontend (`web/`): Dashboard, Sync Status, Settings, Support
- API layer (`backend/api/`): routes for assets, transfer, autosync, webhooks, settings, support
- Services (`backend/services/`): Kaseya/Revnue clients, transfer engine, autosync engine, logger, settings manager, diagnostics
- Models/storage (`backend/models/`): SQLite queue table + JSONL/state files
- Worker (`backend/workers/autosync_worker.py`): reconciliation, retry scheduling, queue processing

## Storage
- `.env`
- `backend/data/sync_events.db`
- `backend/data/activity_log.jsonl`
- `backend/data/activity_state.json`
- `backend/data/support_tickets.jsonl`

## Matching Rule
- `Kaseya.Identifier == Revnue.serial_number`
- OR `Kaseya.Identifier == Revnue.asset_tag`
- Asset name is never used for matching.

## Transfer Rule
- Exact identifier match exists -> UPDATE
- No exact identifier match -> CREATE
- Empty incoming mapped value preserves existing Revnue value
- Incomplete mapped data marks transfer as partial and logs warning

