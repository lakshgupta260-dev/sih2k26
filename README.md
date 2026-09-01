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

**New here? Start with the [Start Guide](docs/START-GUIDE.md)** — prerequisites, a
Docker and a native path, creating the first administrator, how to verify it
works, the API reference and troubleshooting. ([PDF](docs/SIH26122-Start-Guide.pdf))

Current status and remaining scope: [Progress Sheet](docs/PROGRESS.md) ([PDF](docs/SIH26122-Progress-Sheet.pdf)).

For architecture and design decisions see [`backend/README.md`](backend/README.md).

## Build status

Phases 1 and 2 are complete and validated against a live PostgreSQL 16
instance, with 81 passing tests.

* **Phase 1** — scaffolding, configuration, database, Alembic, Docker
* **Phase 2** — authentication (access/refresh JWTs, bcrypt), RBAC across
  `ADMIN` / `PROJECT_MANAGER` / `SITE_SUPERVISOR`, users, projects,
  memberships, project-level authorization, audit logging

Phase 3 (schedule upload, Excel/CSV parsing, L1–L6 activities, dependencies) is
next. The full phase plan is in `backend/README.md`.
