# SDLC_SOP.md

**GSIS Asset Sync Platform Implementation SOP**\
(Kaseya → Strev/Revnue)

------------------------------------------------------------------------

# 1. Purpose

This document defines the **Standard Operating Procedure (SOP)** for
implementing the **GSIS Asset Sync Platform**, a system that
synchronizes assets between **Kaseya** and **Strev/Revnue**.

The SOP provides:

-   a full **SDLC development framework**
-   coding standards and architecture guidelines
-   frontend and backend implementation workflow
-   deployment and operational procedures

The objective is to ensure **consistent, secure, and production‑grade
implementation** across all development environments.

------------------------------------------------------------------------

# 2. Scope

This SOP applies to:

-   Full platform development
-   Backend services
-   Frontend web interface
-   API integrations
-   Deployment pipelines
-   Maintenance and monitoring

System components covered:

-   Operator Dashboard
-   Autosync Engine
-   Activity Logging System
-   Settings Manager
-   Support Diagnostics Module

------------------------------------------------------------------------

# 3. Technology Stack

## Backend

Language

Python 3.11+

Server

Python HTTP server / FastAPI

Database

SQLite (initial)\
PostgreSQL (future scalability)

Storage

JSONL logs\
.env configuration

API Integrations

Kaseya API v3\
Strev/Revnue API

------------------------------------------------------------------------

## Frontend

Framework

Vanilla JS + modular architecture

Pages

Dashboard\
Sync Status\
Settings\
Support

Styling

CSS system\
Responsive UI

------------------------------------------------------------------------

## DevOps

Environment

Docker\
GitHub\
CI/CD

Deployment

Linux server\
nginx reverse proxy

------------------------------------------------------------------------

# 4. System Architecture

## High-Level Components

Frontend UI\
→ API Gateway\
→ Backend Service (`asset_dashboard.py`)\
→ External APIs + Local Storage

External Services:

-   Kaseya API
-   Strev/Revnue API

Local Storage:

-   .env
-   sync_events.db
-   activity_log.jsonl
-   activity_state.json
-   support_tickets.jsonl

------------------------------------------------------------------------

# 5. SDLC Development Phases

## Phase 1 --- Planning

Objectives:

-   Define system requirements
-   Identify stakeholders
-   Define project scope

Deliverables:

-   Project Charter
-   Architecture Document
-   Requirement Specification

Core system features:

-   asset comparison dashboard
-   asset transfer engine
-   autosync worker
-   system health monitoring
-   support diagnostics

------------------------------------------------------------------------

# Phase 2 --- Requirements Analysis

Functional requirements:

-   compare Kaseya and Strev assets
-   perform controlled transfer
-   autosync assets
-   log operations
-   support diagnostics

Non-functional requirements:

-   high reliability
-   API security
-   fault tolerance
-   detailed observability

------------------------------------------------------------------------

# Phase 3 --- System Design

## Backend Architecture

Modules:

-   asset_dashboard.py
-   autosync_engine.py
-   kaseya_client.py
-   revnue_client.py
-   activity_logger.py
-   settings_manager.py
-   support_module.py

Folder structure:

backend/ api/ services/ models/ workers/ utils/

------------------------------------------------------------------------

## Frontend Architecture

Structure:

web/ index.html app.js sync-status.html sync-status.js settings.html
settings.js support.html support.js styles.css

------------------------------------------------------------------------

# Phase 4 --- Implementation

## Backend Implementation Steps

### Step 1 --- Project Setup

Repository structure:

backend/\
web/\
scripts/\
docs/

Dependencies:

pip install fastapi uvicorn requests python-dotenv

------------------------------------------------------------------------

### Step 2 --- API Integration Layer

Kaseya client:

-   fetch_kaseya_assets()
-   fetch_kaseya_asset_by_identifier()

Strev client:

-   fetch_revnue_assets()
-   fetch_revnue_exact_matches()

------------------------------------------------------------------------

### Step 3 --- Matching Logic

Matching rule:

Kaseya.Identifier == Strev.serial_number\
OR\
Kaseya.Identifier == Strev.asset_tag

Asset names must not be used for matching.

------------------------------------------------------------------------

### Step 4 --- Transfer Engine

Decision logic:

if identifier exists → UPDATE\
else → CREATE

Core functions:

-   transfer_kaseya_assets_to_revnue()
-   delete_revnue_asset()

------------------------------------------------------------------------

### Step 5 --- Autosync Engine

Components:

-   event queue
-   webhook processor
-   reconciliation worker
-   retry scheduler

Database table:

sync_events

Webhook endpoint:

POST /api/webhooks/kaseya

------------------------------------------------------------------------

### Step 6 --- Activity Logging

Files:

activity_log.jsonl\
activity_state.json

Capabilities:

-   notifications
-   messages
-   status tracking

------------------------------------------------------------------------

### Step 7 --- Settings Manager

Endpoints:

GET /api/settings/env\
POST /api/settings/env

Manages `.env` configuration.

------------------------------------------------------------------------

### Step 8 --- Support Module

Features:

-   connectivity checks
-   system health snapshot
-   ticket creation

Ticket storage:

support_tickets.jsonl

------------------------------------------------------------------------

# Phase 5 --- Frontend Development

## Dashboard

Features:

-   Kaseya table
-   Strev table
-   search and pagination
-   multi-select transfer
-   batch confirmation modal
-   activity center
-   autosync toggle
-   loading overlay

------------------------------------------------------------------------

## Sync Status Page

Displays:

-   system health
-   queue metrics
-   success rate KPIs
-   recent events
-   failed events

------------------------------------------------------------------------

## Settings Page

Capabilities:

-   .env editor
-   secret visibility toggle
-   save and reload

------------------------------------------------------------------------

## Support Page

Tools:

-   diagnostics viewer
-   connectivity tests
-   ticket submission
-   ticket history
-   diagnostics export

------------------------------------------------------------------------

# Phase 6 --- Testing

Testing types:

-   unit tests
-   integration tests
-   API tests
-   frontend functional tests

Required validation:

-   API connectivity
-   data mapping accuracy
-   autosync reliability
-   UI responsiveness

------------------------------------------------------------------------

# Phase 7 --- Deployment

Deployment workflow:

1.  build backend container
2.  build frontend assets
3.  configure environment variables
4.  start API server
5.  configure nginx reverse proxy
6.  enable autosync worker

Production stack:

Linux server\
Docker\
nginx\
systemd worker

------------------------------------------------------------------------

# Phase 8 --- Maintenance

Operational tasks:

-   log monitoring
-   API health checks
-   database cleanup
-   performance tuning
-   security updates

Operational rules:

-   restart backend after code updates
-   verify sync health before production transfers
-   review activity logs regularly

------------------------------------------------------------------------

# 6. Security Guidelines

Rules:

-   never expose API tokens
-   store secrets in `.env`
-   sanitize all API inputs
-   validate webhook payloads

------------------------------------------------------------------------

# 7. Data Quality Safeguards

If incoming mapped value is empty:

→ preserve existing Strev value

If asset data incomplete:

→ mark transfer as partial\
→ log warning

------------------------------------------------------------------------

# 8. Future Extensions

## SMAX Integration

Planned capabilities:

-   create incident
-   store ticket ID
-   sync ticket status

------------------------------------------------------------------------

## AI Field Mapping

Future system:

-   detect unmapped fields
-   generate mapping suggestions
-   confidence scoring
-   approval workflow
-   mapping version control

------------------------------------------------------------------------

# 9. Operational Guidelines

Before production transfer:

-   check sync status
-   run diagnostics
-   verify API connectivity

Debug indicators:

-   has_assetinfo
-   assetinfo_count
-   detail_source
-   mapped_nonempty_count

------------------------------------------------------------------------

# 10. Documentation Standards

Every module must include:

-   docstrings
-   API documentation
-   error handling
-   logging
-   unit tests

------------------------------------------------------------------------

# 11. Code Review SOP

Pull request rules:

-   minimum 1 reviewer
-   tests must pass
-   lint checks must pass

------------------------------------------------------------------------

# 12. Versioning

Version format:

MAJOR.MINOR.PATCH

Example:

v1.0.0

------------------------------------------------------------------------

# End of Document
