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

*Last checked 2026-09-03 against the actual code in `backend/`; see
[`docs/PROGRESS.md`](docs/PROGRESS.md) for the full breakdown and how each
line below was verified.*

Phases 1–7 are complete and were validated against a live PostgreSQL 16
instance. Phase 8 is code-complete (reports and notifications) but has not
yet had its test suite re-run against Postgres since this doc was last
updated — see `backend/README.md` for exactly what that does and doesn't
cover.

* **Phase 1** — scaffolding, configuration, database, Alembic, Docker
* **Phase 2** — authentication (access/refresh JWTs, bcrypt), RBAC across
  `ADMIN` / `PROJECT_MANAGER` / `SITE_SUPERVISOR`, users, projects,
  memberships, project-level authorization, audit logging
* **Phase 3** — schedule upload, Excel/CSV/XER/MS Project parsing, L1–L6
  activity hierarchy, dependencies
* **Phase 4** — document upload, PDF/Excel/OCR-ready processing, Celery job
  queue
* **Phase 5** — AI extraction and activity matching (fuzzy + lexical +
  discipline/hierarchy signals), human review queue
* **Phase 6** — progress engine, planned-vs-actual analytics, dashboard
  aggregation
* **Phase 7** — ML delay prediction (rule-based baseline + Random Forest,
  promoted only when it beats the baseline), risk scoring
* **Phase 8** — PDF/Excel report generation, multi-channel notifications
  (in-app is live; email/WhatsApp are dry-run stubs pending Phase 9)

Not started: **Phase 9** (Meta/WhatsApp integration), **Phase 10** (Vapi
voice assistant), **Phase 11** (hardening, seed data, production Docker
overlay). The full phase plan is in `backend/README.md`.
