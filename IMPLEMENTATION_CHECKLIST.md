# GSIS Asset Sync Platform - Implementation Checklist

Source of truth: `SDLC_SOP.md`

## Phase 1 - Planning
- [x] Define project charter document
- [x] Define requirement specification document
- [x] Define architecture document
- [x] Confirm stakeholders and scope boundaries
- [x] Enumerate core features:
  - [x] Asset comparison dashboard
  - [x] Asset transfer engine
  - [x] Autosync worker
  - [x] System health monitoring
  - [x] Support diagnostics

## Phase 2 - Requirements Analysis
- [x] Implement functional requirement: compare Kaseya and Strev assets
- [x] Implement functional requirement: controlled transfer
- [x] Implement functional requirement: autosync assets
- [x] Implement functional requirement: log operations
- [x] Implement functional requirement: support diagnostics
- [x] Implement non-functional requirement: reliability controls
- [x] Implement non-functional requirement: API security controls
- [x] Implement non-functional requirement: fault tolerance (retry/recovery)
- [x] Implement non-functional requirement: observability

## Phase 3 - System Design
- [x] Create backend folder structure: `backend/api/services/models/workers/utils`
- [x] Create backend modules:
  - [x] `backend/asset_dashboard.py`
  - [x] `backend/services/autosync_engine.py`
  - [x] `backend/services/kaseya_client.py`
  - [x] `backend/services/revnue_client.py`
  - [x] `backend/services/activity_logger.py`
  - [x] `backend/services/settings_manager.py`
  - [x] `backend/services/support_module.py`
- [x] Create frontend structure:
  - [x] `web/index.html`
  - [x] `web/app.js`
  - [x] `web/sync-status.html`
  - [x] `web/sync-status.js`
  - [x] `web/settings.html`
  - [x] `web/settings.js`
  - [x] `web/support.html`
  - [x] `web/support.js`
  - [x] `web/styles.css`

## Phase 4 - Backend Implementation
- [x] Step 1 Project setup:
  - [x] Create repository folders `backend/`, `web/`, `scripts/`, `docs/`
  - [x] Add Python dependencies (`fastapi`, `uvicorn`, `requests`, `python-dotenv`)
- [x] Step 2 API integration layer:
  - [x] Implement `fetch_kaseya_assets()`
  - [x] Implement `fetch_kaseya_asset_by_identifier()`
  - [x] Implement `fetch_revnue_assets()`
  - [x] Implement `fetch_revnue_exact_matches()`
- [x] Step 3 Matching logic:
  - [x] Match only by `Identifier == serial_number` or `Identifier == asset_tag`
  - [x] Ensure asset names are never used for matching
- [x] Step 4 Transfer engine:
  - [x] Implement decision rule: identifier exists -> UPDATE, else -> CREATE
  - [x] Implement `transfer_kaseya_assets_to_revnue()`
  - [x] Implement `delete_revnue_asset()`
  - [x] Enforce data safeguards for empty mapped values and incomplete data
- [x] Step 5 Autosync engine:
  - [x] Implement event queue
  - [x] Implement webhook processor
  - [x] Implement reconciliation worker
  - [x] Implement retry scheduler
  - [x] Create `sync_events` table in SQLite
  - [x] Implement endpoint `POST /api/webhooks/kaseya`
- [x] Step 6 Activity logging:
  - [x] Implement `activity_log.jsonl` output
  - [x] Implement `activity_state.json` status tracking
  - [x] Implement notifications/messages/status tracking API
- [x] Step 7 Settings manager:
  - [x] Implement `GET /api/settings/env`
  - [x] Implement `POST /api/settings/env`
  - [x] Implement `.env` management with secret masking support
- [x] Step 8 Support module:
  - [x] Implement connectivity checks
  - [x] Implement system health snapshot
  - [x] Implement ticket creation
  - [x] Store tickets in `support_tickets.jsonl`

## Phase 5 - Frontend Implementation
- [x] Dashboard page:
  - [x] Kaseya table
  - [x] Strev table
  - [x] Search and pagination
  - [x] Multi-select transfer
  - [x] Batch confirmation modal
  - [x] Activity center
  - [x] Autosync toggle
  - [x] Loading overlay
- [x] Sync Status page:
  - [x] System health
  - [x] Queue metrics
  - [x] Success rate KPIs
  - [x] Recent events
  - [x] Failed events
- [x] Settings page:
  - [x] `.env` editor
  - [x] Secret visibility toggle
  - [x] Save and reload
- [x] Support page:
  - [x] Diagnostics viewer
  - [x] Connectivity tests
  - [x] Ticket submission
  - [x] Ticket history
  - [x] Diagnostics export

## Phase 6 - Testing
- [x] Add unit tests
- [x] Add integration tests
- [x] Add API tests
- [x] Add frontend functional tests
- [x] Validate API connectivity behavior
- [x] Validate data mapping accuracy
- [x] Validate autosync reliability behavior
- [x] Validate UI responsiveness baseline

## Phase 7 - Deployment
- [x] Add backend container build config
- [x] Add frontend asset build/serve config
- [x] Add environment variable configuration template
- [x] Add API server startup script
- [x] Add nginx reverse proxy configuration
- [x] Add autosync worker startup/systemd configuration

## Phase 8 - Maintenance
- [x] Add log monitoring procedure/script
- [x] Add API health check routine
- [x] Add database cleanup routine
- [x] Add performance tuning guidance
- [x] Add security update guidance
- [x] Add operational runbook rules

## Cross-Cutting SOP Requirements
- [x] Security:
  - [x] Never expose API tokens in responses/logs
  - [x] Store secrets in `.env`
  - [x] Sanitize all API inputs
  - [x] Validate webhook payloads
- [x] Data quality safeguards:
  - [x] Preserve existing Strev value if mapped value is empty
  - [x] Mark incomplete transfers as partial
  - [x] Log warning on partial transfer
- [x] Operational diagnostics indicators:
  - [x] `has_assetinfo`
  - [x] `assetinfo_count`
  - [x] `detail_source`
  - [x] `mapped_nonempty_count`
- [x] Documentation standards per module:
  - [x] Docstrings
  - [x] API docs
  - [x] Error handling
  - [x] Logging
  - [x] Unit tests
- [x] Code review SOP artifacts:
  - [x] CI test checks
  - [x] CI lint checks
  - [x] PR reviewer requirement documented
- [x] Versioning:
  - [x] Adopt `MAJOR.MINOR.PATCH`
  - [x] Initialize version to `v1.0.0`

## Phase 9 - Further Analysis Integration (`GSIS_AssetSync_Analysis.docx`)
- [x] Compile additional analysis items into implementation roadmap
- [x] Implement adaptive autosync interval backoff in worker loop
- [x] Implement sync cycle audit log storage (`sync_audit_runs`) and retrieval API
- [x] Implement manual sync trigger endpoint (`POST /api/sync/run-now`)
- [x] Implement sync audit history endpoint (`GET /api/sync/audit`)
- [x] Implement settings page access protection with session authentication
- [x] Implement auth endpoints (`/api/auth/status`, `/api/auth/login`, `/api/auth/logout`)
- [x] Implement dashboard preview action for selected assets using dry-run API
- [x] Implement Sync Status UI section for sync run history and manual trigger
- [ ] Implement field-level conflict resolution rule editor (planned)
- [ ] Implement external secret manager integration (planned)
- [ ] Implement outbound notification integrations (Slack/Teams/email) (planned)
- [ ] Implement multi-tenant company profile management (planned)
- [ ] Implement rollback/undo sync snapshot workflow (planned)

## Phase 10 - Best Practices Integration (`GSIS_AssetSync_BestPractices_Checklist.docx`)
- [x] Circuit breaker pattern for external API failures
- [x] Idempotent sync safety via content-hash no-op detection
- [x] Event sourcing for immutable asset change streams
- [x] Graceful shutdown handling in worker
- [x] Async I/O for parallel API calls
- [x] HMAC webhook signature validation
- [x] Token rotation endpoint without downtime
- [x] Settings change audit trail with masked before/after values
- [x] Content Security Policy and security headers
- [x] Pydantic schema validation on API responses (Kaseya/Revnue clients)
- [x] Content hashing for change detection
- [x] Soft deletes with tombstoning records
- [x] Deduplication engine
- [x] Structured JSON logging (JSONL activity log)
- [x] Prometheus metrics endpoint (`GET /metrics`)
- [x] Enhanced health check endpoint (`GET /api/health`)
- [x] Sync diff viewer in Sync Status page
- [x] Typed client behavior layer (validated/resilient service-level clients)
- [x] Field mapping as external configuration
- [x] Test suite with replayable mock API fixtures
- [x] Rate limit awareness with token bucket pacing
- [x] Bulk operations UI baseline (multi-select sync actions)
- [x] Export asset comparison to CSV
- [x] Outbound webhook notifications + test trigger
- [x] Scheduled sync windows (cron-style)
- [x] Docker + Docker Compose deployment artifacts

