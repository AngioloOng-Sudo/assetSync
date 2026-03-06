# Operations Runbook

## Before Production Transfer
1. Check `/api/sync/status`
2. Run diagnostics (`/api/support/diagnostics`)
3. Verify connectivity (`/api/support/connectivity`)

## Regular Operations
- Review `backend/data/activity_log.jsonl`
- Monitor queue metrics and failed events
- Run support maintenance endpoint or `scripts/maintenance.py`
- Restart backend after code updates

## Debug Indicators
- `has_assetinfo`
- `assetinfo_count`
- `detail_source`
- `mapped_nonempty_count`

## Database Cleanup
- `python scripts/maintenance.py --cleanup-days 30`

