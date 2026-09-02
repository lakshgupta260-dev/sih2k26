# Build Progress

Status of the SIH26122 backend against the eleven-phase plan.

> **Last updated:** 2026-09-03, by reading the actual `backend/` source tree
> (models, services, routers, migrations, tests) rather than carrying forward
> old status text. See [§7](#7-how-this-was-verified) for exactly what was
> and wasn't run in that pass — this update did not have Postgres or the
> project's Python dependencies available, so it verifies *code presence and
> wiring*, not a fresh test-suite pass. Treat "code complete" and
> "validated" as different claims below; they are not used interchangeably.

---

## 1. Where things stand

**7 of 11 phases validated; 1 more code-complete pending re-validation.**

| Metric | Value |
|---|---|
| Phases validated (live PG16 + passing tests, per earlier sessions) | **7 / 11** (Phases 1–7) |
| Phases code-complete, not re-validated this pass | **1 / 11** (Phase 8) |
| Phases not started | **3 / 11** (Phases 9–11) |
| Application files | 113 Python files, ~13,000 lines (`app/`) |
| Test files | 27 files, ~5,800 lines |
| Test functions | 293 (some are multi-assertion "flow" tests covering several scenarios each, not 293 independent cases) |
| Database tables | 18 (+ `alembic_version`) |
| API endpoints | 65 across 14 routers |
| Migrations | 11, single linear chain (hand-traced this pass; no branching found) |

## 2. Phase status

| # | Phase | Status | Validated |
|---|---|---|---|
| 1 | Scaffolding, config, database, Alembic, Docker | **Complete** | Live PG16 + Docker |
| 2 | Auth, RBAC, users, projects | **Complete** | Live PG16, tests passing |
| 3 | Schedule upload, Excel/CSV parsing, L1–L6, dependencies | **Complete** | Live PG16 + Docker |
| 4 | Report upload, document processing, processing jobs | **Complete** | Live PG16 |
| 5 | AI extraction, matching, confidence, human review | **Complete** | Live PG16 |
| 6 | Progress engine, planned-vs-actual analytics, dashboard | **Complete** | Live PG16 |
| 7 | ML delay prediction, risk scoring, explainability | **Complete** | Live PG16 |
| 8 | Report generation, notifications | **Code complete** | Not re-run this pass — see §7 |
| 9 | Meta / WhatsApp integration | Not started | — |
| 10 | Vapi integration, AI project assistant | Not started | — |
| 11 | Testing, hardening, performance, documentation | Not started | — |

Phases 1–7's "Live PG16" status is carried forward from prior work sessions
that had database access; this pass didn't have the ability to re-run them
and instead confirmed their code and migrations are still structurally
present and consistent. If you want a fresh number, `pytest -v` is the
source of truth, not this file.

## 3. What is built

### Phase 1 — foundation

| Component | Location |
|---|---|
| Application factory, lifespan, middleware | `app/main.py` |
| Typed settings, no hard-coded secrets | `app/core/config.py` |
| Domain enumerations | `app/core/constants.py` |
| Error hierarchy + single JSON envelope | `app/core/exceptions.py` |
| Structured logging, request correlation ids | `app/core/logging.py`, `middleware.py` |
| Declarative base with naming convention | `app/db/base.py` |
| UUID / timestamp / soft-delete mixins | `app/db/mixins.py` |
| Engine, session lifecycle, DB probe | `app/db/session.py` |
| Generic typed repository | `app/repositories/base.py` |
| Alembic reading URL from settings | `alembic/env.py` |
| Liveness + readiness endpoints | `app/api/v1/health.py` |
| Dockerfile, compose (PG16 + Redis 7 + API) | `Dockerfile`, `docker-compose.yml` |

### Phase 2 — auth, RBAC, tenancy

| Component | Location |
|---|---|
| bcrypt hashing, JWT encode/decode | `app/core/security.py` |
| Models: user, refresh token | `app/models/user.py` |
| Models: project, membership | `app/models/project.py` |
| Model: append-only audit log | `app/models/audit.py` |
| Auth service (register/login/refresh/logout) | `app/services/auth.py` |
| User administration service | `app/services/user.py` |
| Project + membership service | `app/services/project.py` |
| Audit service | `app/services/audit.py` |
| Auth dependencies, role guards, project guards | `app/api/deps.py` |
| Routers | `app/api/v1/{auth,users,projects}.py` |
| Admin bootstrap CLI | `app/cli.py` |

### Phase 3 — schedule ingestion

Models `Schedule`, `Activity` (L1–L6, WBS path, discipline, planned dates,
budgeted quantity/UOM), `ActivityDependency` (FS/SS/FF/SF + lag). Excel/CSV
parsing with configurable column mapping, hierarchy and dependency-cycle
validation. Endpoints in `app/api/v1/{schedules,activities}.py`.

### Phase 4 — document processing and jobs

Models `UploadedFile`, `ProcessingJob`, `ProgressReport`. Celery + Redis
workers; upload returns a `job_id` immediately and jobs are claimed under
`SELECT ... FOR UPDATE` so a redelivered task can't double-process a file.
Endpoints in `app/api/v1/documents.py`.

### Phase 5 — extraction and matching

Extraction layer independent of ORM models (`app/ai/`), replaceable
`LLMProvider`/`EmbeddingProvider` interfaces, matching engine combining exact
id/code, fuzzy string similarity (`rapidfuzz`), keyword overlap, discipline
and hierarchy agreement. Models `ExtractedActivity`, `ActivityMatch` with
confidence and method. Endpoints in `app/api/v1/matching.py`.

### Phase 6 — progress engine and analytics

Model `ActualProgress`. `ProgressService` owns progress computation and
roll-up L6 → L1, planned-vs-actual variance, S-curve series. Endpoints in
`app/api/v1/{progress,analytics}.py`.

### Phase 7 — ML delay prediction

Two-tier design: a deterministic rate-based baseline that always answers,
and a Random Forest promoted only when it beats that baseline on held-out
data by an explicit margin (`ML_BASELINE_MARGIN`) — not just on raw
accuracy. 26 engineered features, grouped cross-validation by activity to
avoid leaking correlated cutoffs across folds. Models `DelayModelVersion`,
`DelayPrediction`. Endpoints in `app/api/v1/prediction.py`. Full design
rationale is in `backend/README.md` under "Delay prediction (Phase 7)".

### Phase 8 — reports and notifications

Model `GeneratedReport` (PDF/XLSX artefacts, SHA-256 + size recorded, status
machine `PENDING → COMPLETED/FAILED`) and `Notification` (one row per
channel-specific delivery attempt, unique `idempotency_key`). Builders:
`PDFReportBuilder` (ReportLab, capped at 25 activities — meant to be read)
and `ExcelReportBuilder` (openpyxl, three sheets, uncapped — meant as the
full export). `NotificationDispatcher` routes to `InAppDispatcher` (real),
`EmailDispatcher` and `WhatsAppDispatcher` (both dry-run/logged only — no
SMTP or Meta provider wired in yet, that's Phase 9's job). 9 endpoints across
`app/api/v1/{generated_reports,notifications}.py`. Full detail, including
what was and wasn't independently verified, is in `backend/README.md` under
"Reports and notifications (Phase 8)".

## 4. What is left

### Phase 9 — Meta / WhatsApp

* Webhook verification (`hub.challenge`) and payload signature validation
  (`X-Hub-Signature-256`)
* Inbound message ingestion into the progress pipeline
* Outbound sending behind a replaceable provider interface — this is also
  where `WhatsAppDispatcher` (currently dry-run) gets a real backend
* Endpoint: `integrations/meta.py` (currently an empty package)

### Phase 10 — Vapi and AI assistant

* Vapi webhook handling with signature validation
* Voice-driven progress logging
* Authenticated AI project assistant scoped by the caller's memberships so
  it cannot leak data across projects
* Endpoints: `integrations/vapi.py`, `assistant.py`

### Phase 11 — hardening

* Rate limiting on authentication endpoints
* Realistic seed data: multiple phases, Civil / Piping / Electrical /
  Mechanical / Instrumentation, 100+ L5/L6 activities, dependencies,
  planned dates, simulated actuals with delays, daily progress reports
* Production Docker overlay (no `--reload`, gunicorn/uvicorn workers)
* Query performance review and index tuning
* `admin.py` router, coverage sweep, API documentation polish
* A real SMTP provider behind `EmailDispatcher`, if email is still wanted
  once Phase 9's WhatsApp path exists

## 5. Known gaps and open items

| Item | Impact | When |
|---|---|---|
| Phase 8 test suite not re-run against Postgres since this doc's last real check | Can't yet claim "validated" for Phase 8 the way Phases 1–7 can | Run `pytest -v` on the 4 Phase 8 test files locally |
| `EmailDispatcher` / `WhatsAppDispatcher` are dry-run only | No real email or WhatsApp message goes out yet; don't demo this as if it does | Phase 9 (WhatsApp) / Phase 11 (email) |
| No password reset flow | Needs an email provider | Blocked on the item above |
| No rate limiting on login | Brute-force exposure | Phase 11 |
| Access tokens cannot be revoked before expiry | By design; keep lifetime short | — |
| Seed data script not written | Spec requires it; needed for demo | Phase 11 |
| `integrations/` package is empty (only `__init__.py`) | Phases 9–10 genuinely haven't started, confirmed by directory listing | Phase 9/10 |
| Git history not reviewable | This pass worked from a zip export with no `.git`; commit/push status is unknown from here | Check locally |

## 6. Decisions taken (and why)

| Decision | Rationale |
|---|---|
| Synchronous SQLAlchemy, not async | FastAPI runs sync deps in a threadpool; the same session factory is reusable from Celery workers. |
| Roles as enum columns, not a `roles` table | The set is closed and immutable at exactly three values. |
| PyJWT over python-jose | Actively maintained; avoids the unmaintained `ecdsa` dependency. |
| `bcrypt` pinned to 4.0.1 | passlib 1.7.4 reads `bcrypt.__about__`, removed in bcrypt ≥ 4.1. |
| Non-members receive 404, not 403 | Confirming a project id exists leaks across the tenancy boundary — applied consistently through Phase 8's report/notification access checks too. |
| Refresh tokens recorded server-side | A stateless JWT cannot be logged out without a revocation record. |
| Audit writes join the caller's transaction | A rolled-back action must not leave a log claiming it happened. |
| UUID primary keys | Ids appear in URLs and cross-project references; sequential ids are an enumeration risk. |
| `Notification` = one row per channel attempt, not per event | An email failure can't hide an already-delivered in-app notification; fan-out is the caller writing multiple rows sharing an `event_key`. |
| PDF report capped at 25 activities, Excel uncapped | The PDF is a readable summary; the Excel is the full export. Deliberately different jobs, not an oversight. |

## 7. How this was verified

This update was produced by reading the code directly (`app/reports/`,
`app/notifications/`, `app/services/{reporting,notification}.py`,
`app/api/v1/{generated_reports,notifications}.py`, `app/models/reporting.py`,
the migration chain, and all four Phase 8 test files) and by hand-tracing
every migration's `revision`/`down_revision` pair to confirm a single linear
chain. `PDFReportBuilder` and `ExcelReportBuilder` were additionally run
standalone, outside the FastAPI/DB stack, against representative sample data:
both produced valid binaries (a genuine `%PDF` header; a genuine xlsx zip
container that reloads in openpyxl with the expected three sheets and
correct dimensions).

What this update did **not** do: run `pytest` against a live PostgreSQL
instance, because the environment it ran in had no network access and none
of `sqlalchemy`, `fastapi`, `pydantic`, or `alembic` installed. Numbers under
"Validated" for Phases 1–7 are carried forward from earlier sessions that
did have a database; they were not independently re-confirmed here. Before
relying on this document for a demo or a submission, run:

```bash
cd backend && source .venv/bin/activate
pytest -v
```

and update §1/§2 with the real pass/fail count if anything here turns out to
disagree with it.

## 8. Immediate next actions

1. **Run `pytest -v` locally** and confirm Phase 8 passes against live
   Postgres — flip its row in §2 to "Live PG16" once it does, or fix
   whatever fails.
2. **Decide what's next**: Phase 9 (Meta/WhatsApp — gives `WhatsAppDispatcher`
   a real backend) or Phase 11's seed data (needed for any demo regardless
   of which integration phase comes first).
3. **Rebuild the Docker image** if it hasn't been rebuilt since Phase 8's
   dependency (`reportlab`) was added — `docker compose up --build`.
4. Decide whether `EmailDispatcher` gets a real SMTP backend before or after
   Phase 9's WhatsApp work, since both are currently dry-run placeholders.

> The synthetic labelled dataset built for Phases 3–6 (a 306-row L1–L6
> baseline schedule, 806 labelled field-report lines across four channels,
> plus ground-truth link labels) is not committed to this repository.
