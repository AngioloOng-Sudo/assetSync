# Deployment Guide

## Workflow
1. Build backend container (`docker build -t gsis-asset-sync .`)
2. Build/start services (`docker compose up --build`)
3. Configure `.env` values (API URLs/tokens/secrets)
4. Start API server (`uvicorn backend.asset_dashboard:app --host 0.0.0.0 --port 8000`)
5. Configure nginx reverse proxy (`deploy/nginx.conf`)
6. Enable autosync worker (`deploy/asset-sync-worker.service`)

## Production Stack
- Linux server
- Docker
- nginx
- systemd worker service

