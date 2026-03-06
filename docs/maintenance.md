# Maintenance Guide

## Recurring Tasks
- Monitor activity logs and failed sync events
- Run API health checks (`/api/health`, `/api/support/health`)
- Execute DB cleanup (`scripts/maintenance.py --cleanup-days 30`)
- Review sync performance and adjust `AUTOSYNC_INTERVAL_SECONDS`
- Apply dependency security updates regularly

## Operational Rules
- Restart backend after code updates
- Verify sync health before production transfers
- Review activity logs regularly

