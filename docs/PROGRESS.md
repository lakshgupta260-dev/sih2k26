# Build Progress

Status of the SIH26122 backend against the eleven-phase plan.

---

## 1. Where things stand

**2 of 11 phases complete.** Both validated against a live PostgreSQL 16
instance rather than assumed working.

| Metric | Value |
|---|---|
| Phases complete | **2 / 11** (18%) |
| Application files | 49 Python files, 3,354 lines |
| Test files | 5 files, 1,228 lines, **81 passing tests** |
| Database tables | 5 (+ `alembic_version`) |
| API endpoints | 17 paths |
| Migrations | 1, with zero autogenerate drift |
| Commits | 4 (2 unpushed at time of writing) |

## 2. Phase status

| # | Phase | Status | Validated |
|---|---|---|---|
| 1 | Scaffolding, config, database, Alembic, Docker | **Complete** | Live PG16 + Docker |
| 2 | Auth, RBAC, users, projects | **Complete** | Live PG16, 81 tests |
| 3 | Schedule upload, Excel/CSV parsing, L1–L6, dependencies | Not started | — |
| 4 | Report upload, document processing, processing jobs | Not started | — |
| 5 | AI extraction, matching, confidence, human review | Not started | — |
| 6 | Progress engine, planned-vs-actual analytics, dashboard | Not started | — |
| 7 | ML delay prediction, risk scoring, explainability | Not started | — |
| 8 | Report generation, notifications | Not started | — |
| 9 | Meta / WhatsApp integration | Not started | — |
| 10 | Vapi integration, AI project assistant | Not started | — |
| 11 | Testing, hardening, performance, documentation | Not started | — |

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
| Migration creating all 5 tables | `alembic/versions/20260901_1219_*.py` |

**Tables:** `users`, `refresh_tokens`, `projects`, `project_memberships`,
`audit_logs`.

### Test coverage

| File | Tests | Covers |
|---|---|---|
| `test_config.py` | 8 | Settings contract, DB URL assembly, secret-key enforcement |
| `test_health.py` | 6 | Liveness, readiness, error envelope, OpenAPI |
| `test_auth.py` | 23 | Register, login, tokens, rotation, replay, logout, password change |
| `test_rbac.py` | 15 | Role guards, self-access, role changes, deactivation, admin guards |
| `test_projects.py` | 24 | Project CRUD, visibility scoping, membership, cross-project isolation |
| **Total** | **76 functions → 81 cases** | |

## 4. What is left

### Phase 3 — schedule ingestion *(next)*

* Models: `Schedule`, `Activity` (L1–L6, WBS path, discipline, planned dates,
  budgeted quantity/UOM), `ActivityDependency` (FS/SS/FF/SF plus lag)
* Excel and CSV parsers with **configurable column mapping** — real schedules
  never share a column layout
* Primavera P6 (`.xer`) and MS Project (`.xml`) import where feasible
* Hierarchy construction and validation: parent–child integrity, level
  consistency, dependency cycle detection
* Endpoints: `schedules.py` (upload, list, detail), `activities.py` (list,
  tree, detail, filter by discipline/level)
* Dependencies to add: `pandas`, `openpyxl`

### Phase 4 — document processing and jobs

* Models: `UploadedFile`, `ProcessingJob` (PENDING → PROCESSING → COMPLETED /
  FAILED), `ProgressReport`
* Abstractions: `DocumentProcessor`, `PDFProcessor`, `ExcelProcessor`,
  `OCRProcessor` (OCR-ready, provider swappable)
* Celery + Redis workers; upload returns a `job_id` immediately and the
  frontend polls status
* Upload validation: size cap, extension allow-list, content-type/magic-byte
  check, per-project storage isolation
* Endpoints: `documents.py`, `reports.py`, job status polling
* Dependencies to add: `pymupdf`, `pdfplumber`, `celery`, `redis`

### Phase 5 — extraction and matching *(the core of the problem statement)*

* Extraction layer independent of ORM models (plain dataclasses in `app/ai/`)
* Replaceable `LLMProvider` and `EmbeddingProvider` interfaces
* Matching engine combining: exact activity id, exact code, keyword overlap,
  fuzzy string similarity, semantic embeddings, discipline agreement,
  location/chainage agreement, hierarchy proximity
* Configurable confidence thresholds — auto-match / needs-review / unmatched
* Models: `ExtractedActivity`, `ActivityMatch` with confidence and method
* Human review endpoints with complete audit history
* Dependencies to add: `rapidfuzz`, `sentence-transformers`

### Phase 6 — progress engine and analytics

* Model: `ActualProgress` — historical, one row per activity per reporting date
* `ProgressService` owning progress computation and roll-up L6 → L1
* Planned-vs-actual variance, S-curve series, completion percentages
* Dashboard aggregation endpoints designed for direct frontend consumption
* Endpoints: `progress.py`, `analytics.py`

### Phase 7 — ML delay prediction

* Feature engineering from historical actuals (slip, duration ratio, discipline,
  dependency depth, weather/idle signals where available)
* Random Forest or XGBoost — explicitly **not** an LLM
* Training pipeline, model persistence and versioning
* Model: `DelayPrediction`, `RiskScore`
* **Data-backed explainability only** — feature contributions from the model,
  never an LLM inventing plausible-sounding reasons
* Endpoints: `ml.py`, `risks.py`
* Dependencies to add: `scikit-learn`, `joblib`, possibly `xgboost`

### Phase 8 — reports and notifications

* Model: `GeneratedReport`; PDF and Excel builders
* Generic `NotificationService` with pluggable channels (in-app, email,
  WhatsApp) and a `Notification` model
* Endpoints: `notifications.py`, report generation and download
* Dependencies to add: `reportlab` or `weasyprint`

### Phase 9 — Meta / WhatsApp

* Webhook verification (`hub.challenge`) and payload signature validation
  (`X-Hub-Signature-256`)
* Inbound message ingestion into the progress pipeline
* Outbound sending behind a replaceable provider interface
* Endpoint: `integrations/meta.py`

### Phase 10 — Vapi and AI assistant

* Vapi webhook handling with signature validation
* Voice-driven progress logging (the PS asks for a low-friction supervisor
  interface)
* Authenticated AI project assistant that **cannot leak data across projects** —
  every retrieval scoped by the caller's memberships
* Endpoints: `integrations/vapi.py`, `assistant.py`

### Phase 11 — hardening

* Rate limiting on authentication endpoints
* Realistic seed data: multiple phases, Civil / Piping / Electrical /
  Mechanical / Instrumentation, **100+ L5/L6 activities**, dependencies,
  planned dates, simulated actuals with delays, daily progress reports
* Production Docker overlay (no `--reload`, gunicorn/uvicorn workers)
* Query performance review and index tuning
* `admin.py` router, coverage sweep, API documentation polish

## 5. Known gaps and open items

| Item | Impact | When |
|---|---|---|
| Docker image not rebuilt since Phase 2 deps were added | `docker compose up --build` needed before the container runs Phase 2 code | Now |
| No password reset flow | Needs an email provider | Phase 8 |
| No rate limiting on login | Brute-force exposure | Phase 11 |
| Access tokens cannot be revoked before expiry | By design; keep lifetime short | — |
| Seed data script not written | Spec requires it; needed for demo | Phase 11 (or earlier if useful) |
| Concurrency on simultaneous refresh untested | Single-threaded test client only | Phase 11 |
| Two commits unpushed | Awaiting explicit approval | Your call |

## 6. Decisions taken (and why)

| Decision | Rationale |
|---|---|
| Synchronous SQLAlchemy, not async | FastAPI runs sync deps in a threadpool; the same session factory is reusable from Celery workers. Heavy work is CPU-bound and lives in workers, so async DB access adds moving parts without buying throughput. |
| Roles as enum columns, not a `roles` table | The set is closed and immutable at exactly three values. A lookup table would add a join to every authorization check for no benefit. Flag this if a normalized table is required. |
| PyJWT over python-jose | Actively maintained; avoids the unmaintained `ecdsa` dependency. |
| `bcrypt` pinned to 4.0.1 | passlib 1.7.4 reads `bcrypt.__about__`, removed in bcrypt ≥ 4.1. |
| Non-members receive 404, not 403 | Confirming a project id exists leaks across the tenancy boundary. |
| Refresh tokens recorded server-side | A stateless JWT cannot be logged out; without a revocation record, "logout" is a lie. |
| Audit writes join the caller's transaction | A rolled-back action must not leave a log claiming it happened. |
| UUID primary keys | Ids appear in URLs and cross-project references; sequential ids are an enumeration risk. |

## 7. Immediate next actions

1. **Rebuild the Docker image** — `docker compose up --build` — so the container
   picks up the four new Phase 2 dependencies.
2. **Bootstrap an administrator** —
   `docker compose exec api python -m app.cli create-admin --email you@yourdomain.com`
3. **Push, or keep holding** — 2 commits are staged locally and untouched.
4. **Begin Phase 3** — schedule upload, Excel/CSV parsing, L1–L6 hierarchy,
   dependencies.

> The synthetic labelled dataset built earlier (306-row L1–L6 baseline schedule,
> 806 labelled field-report lines across four channels, plus ground-truth link
> labels) is the intended test input for Phases 3 to 6. It is not committed to
> this repository.
