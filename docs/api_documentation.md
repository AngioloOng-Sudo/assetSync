# API Documentation

## Core Endpoints

### Dashboard/Assets
- `GET /api/assets/kaseya`
- `GET /api/kaseya/assets`
- `GET /api/assets/revnue`
- `GET /api/revnue/assets`
- `GET /api/assets/compare`
- `POST /api/transfer`
- `DELETE /api/assets/revnue/{identifier}`

### Autosync
- `GET /api/autosync/state`
- `POST /api/autosync/state`
- `POST /api/autosync/reconcile`
- `POST /api/autosync/process`
- `GET /api/sync/status`
- `GET /api/sync/overview?window=15m|1h|24h|7d`
- `POST /api/sync/reconcile`
- `POST /api/sync/dry-run`
- `POST /api/webhooks/kaseya`

### Activity
- `GET /api/activity`
- `GET /api/activity/state`
- `GET /api/logs?limit=50`
- `POST /api/logs/mark-read`

### Settings
- `GET /api/settings/env`
- `POST /api/settings/env`

### Support
- `GET /api/support/health`
- `POST /api/support/connectivity`
- `GET /api/support/checks`
- `POST /api/support/tickets`
- `GET /api/support/tickets`
- `GET /api/support/diagnostics`
- `GET /api/support/diagnostics/export`
- `POST /api/support/maintenance`

### General
- `GET /api/health`
