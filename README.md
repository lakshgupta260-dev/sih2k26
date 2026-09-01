# SIH 2K26 — Problem Statement 26122

**AI-Powered Planning-to-Execution Project Progress Intelligence Platform**

Smart India Hackathon 2026 · Oil India Limited · Theme: Smart Automation

Bridges planned project schedules (hierarchical L1–L6 activities from
Primavera / MS Project) with actual site progress arriving as PDFs, Excel
files, CSVs, free-text reports, scanned documents and images.

## Repository layout

```
SIH26122-Platform/
└── backend/     FastAPI modular monolith — see backend/README.md
```

The frontend and any shared assets will be added alongside `backend/`.

## Getting started

**New here? Start with the [Phase 1 Start Guide](docs/PHASE-1-START-GUIDE.md)** — prerequisites, a
Docker and a native path, how to verify it works, and troubleshooting.

For architecture and design decisions see [`backend/README.md`](backend/README.md).

## Build status

Phase 1 (scaffolding, configuration, database, Alembic, Docker) is complete and
validated against a live PostgreSQL 16 instance. Phase 2 (authentication, RBAC,
users, projects) is next. The full phase plan is in `backend/README.md`.
