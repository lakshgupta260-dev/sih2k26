# SIH26122 Backend — Progress Intelligence Platform

FastAPI backend bridging planned L1–L6 project schedules with actual site
progress. Built as a modular monolith.

## Status

| Phase | Scope | State |
|---|---|---|
| 1 | Scaffolding, config, DB, Alembic, Docker | **Done, validated** |
| 2 | Auth, RBAC, users, projects | **Done, validated** |
| 3 | Schedule upload, Excel/CSV parsing, L1–L6, dependencies | **Done, validated** |
| 4 | Report upload, document processing, processing jobs | **Done, validated** |
| 5 | AI extraction, matching, confidence, human review | **Done, validated** |
| 6 | Progress engine, planned-vs-actual analytics | **Done, validated** |
| 7 | ML delay prediction, risk, explainability | **Done, validated** |
| 8 | Report generation, notifications | **Code complete — pending validation run** |
| 9 | Meta / WhatsApp | Not started |
| 10 | Vapi, AI project assistant | Not started |
| 11 | Testing, hardening, performance, docs | Not started |

## Bootstrapping the first administrator

Self-registration only ever creates a `SITE_SUPERVISOR`, and creating a user
with a higher role requires an existing administrator. Something outside the
HTTP API therefore has to create the first one:

```bash
# native
python -m app.cli create-admin --email you@yourdomain.com
# docker
docker compose exec api python -m app.cli create-admin --email you@yourdomain.com

python -m app.cli list-admins
```

Omit `--password` to be prompted rather than putting it in your shell history.
Re-running against an existing address promotes that user and resets their
password, so it doubles as account recovery.

> Note: the email must be a genuinely valid address. Reserved TLDs such as
> `.local` and `.test` are rejected — by the CLI as well as the API, so the CLI
> cannot mint an account the API would refuse to authenticate.

## Quick start (native)

```bash
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then edit POSTGRES_* to match your database
createdb sih26122             # or use any existing PostgreSQL 14+ instance
alembic upgrade head
uvicorn app.main:app --reload
```

* Swagger UI — http://localhost:8000/docs
* ReDoc — http://localhost:8000/redoc
* OpenAPI — http://localhost:8000/api/v1/openapi.json

## Quick start (Docker)

```bash
cd backend
cp .env.example .env
docker compose up --build
```

`docker-compose.yml` starts PostgreSQL 16, Redis 7 and the API, runs
`alembic upgrade head` on boot, and serves on port 8000. The compose file is
development-shaped (`--reload`, bind-mounted upload dirs); a production
overlay comes in Phase 11.

## Tests

```bash
cd backend && source .venv/bin/activate
pytest -v
```

The suite runs against a **real PostgreSQL instance**, not SQLite: the schema
uses JSONB, partial indexes and check constraints, and a SQLite run would pass
while the production schema was broken. Tests connect to
`<POSTGRES_DB>_test`, creating it if absent, and each test runs inside a
transaction that is rolled back afterwards, so they neither see nor leave each
other's rows.

`tests/test_migrations.py` is a guard rather than a feature test. It asserts a
single Alembic head, that every revision is reachable, and that
`alembic upgrade head` produces exactly the schema the models declare. That
last check exists because the fixtures build the schema with
`Base.metadata.create_all()` and never run Alembic — which once let a split
migration head reach `main` invisibly.

## Architecture

```
app/
├── main.py              application factory, middleware, exception handlers
├── core/                config, constants, error hierarchy, logging, middleware
├── db/                  declarative base, mixins, engine and session lifecycle
├── models/              SQLAlchemy models (import every module in __init__.py)
├── schemas/             Pydantic v2 request/response contracts
├── repositories/        persistence; owns queries
├── services/            business logic; owns transaction boundaries
├── api/v1/              routers only — no business logic
├── ai/                  LLM and embedding providers (replaceable)
├── ml/                  delay prediction (scikit-learn, not an LLM)
├── document_processing/ PDF / Excel / OCR abstractions
├── integrations/        Meta WhatsApp, Vapi (replaceable)
├── notifications/       channel-agnostic notification dispatch
└── utils/
```

### Decisions worth knowing

**Synchronous SQLAlchemy.** FastAPI runs sync dependencies in a threadpool, and
the same `SessionLocal` is reusable from Celery workers without a second async
engine. The heavy work here (PDF parsing, embeddings, model inference) is
CPU-bound and belongs in workers, so async DB access would add moving parts
without buying throughput.

**UUID primary keys.** Ids appear in URLs and cross-project references; a
guessable sequential id is an enumeration risk in a multi-tenant system.

**Explicit constraint naming convention** (`app/db/base.py`). Without it Alembic
autogenerate emits unnamed constraints and altering them later needs handwritten
migrations.

**Alembic reads the DB URL from settings**, not `alembic.ini`, so there is one
source of truth and no credential is ever committed.

**Single error envelope.** Every failure — ours, FastAPI validation, unhandled —
serialises to `{"error": {"code", "message", "details"}}`. The frontend parses
one shape.

**Repository / service split.** Repositories own queries, services own business
rules and transactions, routers own neither.

**Readiness vs liveness.** A failed DB check at startup logs loudly but does not
abort: `/health/ready` reports it so an orchestrator holds traffic instead of
crash-looping the API.

**Providers are named in configuration** (`LLM_PROVIDER`, `EMBEDDING_PROVIDER`,
`OCR_PROVIDER`), so an implementation swaps without touching call sites.

## Configuration

Every value comes from the environment; see `.env.example`. `SECRET_KEY` is
required in staging/production and must be ≥32 chars — the app refuses to start
otherwise. Locally, a blank key is auto-generated per process (tokens will not
survive a restart, which is intentional).

`CORS_ORIGINS` and `ALLOWED_UPLOAD_EXTENSIONS` accept either a comma-separated
string or a JSON array.

## Endpoints

### Health
| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/api/v1/health` | public | Liveness. Always 200 while the process is up. |
| GET | `/api/v1/health/ready` | public | Readiness. 200 when the DB is reachable, 503 otherwise. |

### Auth
| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/api/v1/auth/register` | public | Self-register. Always yields SITE_SUPERVISOR. |
| POST | `/api/v1/auth/login` | public | JSON login → access + refresh tokens. |
| POST | `/api/v1/auth/token` | public | Form login, so Swagger's **Authorize** works. |
| POST | `/api/v1/auth/refresh` | public | Rotate the refresh token, get a new pair. |
| POST | `/api/v1/auth/logout` | any | Revoke one session, or all when no token is sent. |
| GET | `/api/v1/auth/me` | any | The authenticated user. |
| POST | `/api/v1/auth/change-password` | any | Change password; revokes all other sessions. |

### Users
| Method | Path | Access |
|---|---|---|
| GET | `/api/v1/users` | ADMIN |
| POST | `/api/v1/users` | ADMIN (may set role) |
| GET | `/api/v1/users/{id}` | self or ADMIN |
| PATCH | `/api/v1/users/{id}` | self or ADMIN (profile only) |
| PATCH | `/api/v1/users/{id}/role` | ADMIN |
| PATCH | `/api/v1/users/{id}/status` | ADMIN |

### Projects
| Method | Path | Access |
|---|---|---|
| GET | `/api/v1/projects` | any (scoped to your memberships) |
| POST | `/api/v1/projects` | ADMIN or PROJECT_MANAGER |
| GET | `/api/v1/projects/{id}` | project member or ADMIN |
| PATCH | `/api/v1/projects/{id}` | project manager or ADMIN |
| DELETE | `/api/v1/projects/{id}` | project manager or ADMIN (soft delete) |
| GET | `/api/v1/projects/{id}/members` | project member or ADMIN |
| POST | `/api/v1/projects/{id}/members` | project manager or ADMIN |
| PATCH | `/api/v1/projects/{id}/members/{user_id}` | project manager or ADMIN |
| DELETE | `/api/v1/projects/{id}/members/{user_id}` | project manager or ADMIN |

Every response carries `X-Request-ID`; supply your own to trace a call through
the logs.

## Extraction and matching (Phase 5)

The planning-to-execution bridge. Field text becomes linked, reviewable
activity events.

### Honesty about what is AI

| Component | What it actually is |
|---|---|
| Extraction | **Deterministic rules.** Domain vocabulary, regex field parsing, tense/modality classification. Fast, free, reproducible, auditable. |
| LLM extraction | **Interface only, inactive by default.** With no `LLM_API_KEY` the provider reports itself unavailable and nothing is fabricated. Every run response states `llm_available`. |
| `EMBEDDING_PROVIDER=tfidf` | **Lexical** vector similarity (word + character n-grams). Strong on abbreviations and typos, blind to synonyms sharing no characters. Named accordingly, not passed off as semantic. |
| `EMBEDDING_PROVIDER=sentence_transformer` | **True semantic embeddings.** Opt-in; needs `pip install sentence-transformers` (~1–2 GB of torch). Falls back to tfidf automatically if absent. |

`auto_precision` in `/matching/stats` is measured against human decisions, not
estimated. It is `null` until reviews exist.

### The seven signals

Each returns 0..1 or `None`. **`None` is not zero** — an unstated discipline
must not be scored like a wrong one, so the combiner renormalises over the
signals that were actually available.

| Signal | What it measures |
|---|---|
| `exact_code` | Activity code stated in the text. Floored at 0.95 when it resolves — a unique identifier outranks any text similarity. A stated code that does *not* match is negative evidence. |
| `location` | Chainage or joint-band overlap. Nearly unambiguous on linear works. Compared like-with-like only. |
| `fuzzy` | rapidfuzz token-set ratio on expanded text. |
| `embedding` | Cosine from the configured provider. |
| `keyword` | Containment of the plan activity's vocabulary — not Jaccard, because a field line legitimately carries extra words. |
| `discipline` | Agreement. `OTHER` counts as unlabelled, not as disagreement. |
| `hierarchy` | Prefers granular L5/L6 nodes, and nodes near a confident match earlier in the same document. |

The **domain lexicon** (`app/ai/matching/lexicon.py`) is what makes this work at
all: it bridges `L&B` → "lowering backfilling", `G&T` → "glanding termination",
`RT` → "radiographic testing". No amount of fuzzy matching or general-corpus
embedding recovers those. It is curated data, kept apart from scoring logic so a
planner can review it — extending it is how accuracy improves.

### Two things that are never linked

`PLANNED_NOT_ACTUAL` (future intent — "to be taken up tomorrow") and `NONE`
(site administration, negation) are refused however well they would score.
Booking tomorrow's plan as today's progress is the most damaging thing this
pipeline could do. Both are still stored, because "what did the report say and
what did we do with it" is the audit question that matters.

Two candidates within 0.05 of each other go to review even above the automatic
threshold: indistinguishable options are a human's decision, not a guess.

### Endpoints

| Method | Path | Access |
|---|---|---|
| POST | `/api/v1/projects/{id}/matching/run` | project manager |
| GET | `/api/v1/projects/{id}/matching/matches?status=NEEDS_REVIEW` | project member |
| GET | `/api/v1/projects/{id}/matching/matches/{match_id}` | project member |
| POST | `/api/v1/projects/{id}/matching/matches/{match_id}/review` | project manager |
| GET | `/api/v1/projects/{id}/matching/matches/{match_id}/history` | project member |
| GET | `/api/v1/projects/{id}/matching/stats` | project member |
| GET | `/api/v1/projects/{id}/matching/extracted` | project member |

Review decisions preserve the machine's original verdict in `auto_status`, so
the matcher can be scored against human judgement later.

## Progress and analytics (Phase 6)

Where confirmed matches become a measured position against the plan.

### Booking progress

One record per activity per reporting date. Re-posting a date **corrects** that
day's figure rather than appending a second contradictory one; the superseded
values are kept in the audit entry, so a correction is still traceable.

`POST /progress/apply-matches` closes the
document → extract → match → progress chain. It is deliberately narrow:

| Input | Treatment |
|---|---|
| `AUTO_MATCHED`, `MANUALLY_CONFIRMED` | Booked against the plan activity. |
| `NEEDS_REVIEW`, `UNMATCHED`, rejected | Left alone. |
| `PLANNED_NOT_ACTUAL`, `NONE` | **Never booked**, even if a reviewer confirmed the link by hand. |
| Event with no determinable date | Skipped, not dated to today. |

Every refusal is counted and named in the response, so "why didn't my report
show up" has an answer instead of a shrug.

### Weighting

Completion rolls up from the leaves weighted by `budgeted_quantity`, so 40 km
of lowering does not count the same as one survey task. Where the plan states
no budget the weight falls back to 1.0, degrading to a plain activity count
rather than dropping the activity out of the denominator. A reported quantity
of **zero is a measurement**, not a blank — it does not fall through to the
percentage field.

The traversal is a single iterative post-order pass, so a 5,000-activity WBS
costs one walk rather than one subtree walk per activity, and a corrupt
`parent_id` cycle degrades to leaf reporting instead of hanging the request.

### What the analytics refuse to invent

| Field | Null means |
|---|---|
| `schedule_variance` | The ingested plan carries no dates, so there is nothing to be ahead or behind of. Not `0.0`. |
| `planned_completion_percentage` | Same. |
| `SCurvePoint.actual_percentage` | Nothing was measured at that sample. Carrying the last value forward would draw a flat line that reads as an observed stall. |
| `/s-curve` returning `[]` | No planned window anywhere; there is no curve to draw. |

Planned effort is spread **linearly** inside each activity's planned window.
A real plan may front- or back-load, but start and finish are the only
distribution the ingested schedule states — assuming an S-shape here would be
inventing a curve the plan never gave.

`schedule_variance` is actual minus planned completion in percentage points,
negative meaning behind plan.

### Endpoints

| Method | Path | Access |
|---|---|---|
| POST | `…/schedules/{sid}/activities/{aid}/progress` | project manager |
| GET | `…/schedules/{sid}/activities/{aid}/progress` | project member |
| GET | `…/schedules/{sid}/progress/rollup` | project member |
| POST | `…/schedules/{sid}/progress/apply-matches` | project manager |
| GET | `…/schedules/{sid}/analytics/summary?as_of=` | project member |
| GET | `…/schedules/{sid}/analytics/s-curve` | project member |

All of them prove the schedule belongs to the project in the path and the
activity belongs to that schedule, so a guessed or foreign id is a 404 rather
than a cross-tenant read.

## Delay prediction (Phase 7)

Two tiers, and the response always says which one answered.

### The honest part first

| Tier | What it is | When it runs |
|---|---|---|
| `RULE_BASED_RATE` | **Deterministic arithmetic.** At the rate this activity has actually progressed, does the remaining work fit in the remaining days? Plus explicit adjustments for predecessor slip, a stalled reporting cadence and a late start. | Always available, including on day one. Used whenever no fitted model is promoted. |
| `RANDOM_FOREST` | **Fitted scikit-learn model**, promoted only after passing evaluation. | Only when a model exists, loads cleanly, and was fitted on the feature set the running code builds. |
| `NOT_FORECASTABLE` | No forecast. The plan gives the activity no finish date, so there is nothing to be late against. | Recorded as such rather than given a probability of zero. |

Even when the forest supplies the probability, the arithmetic is computed and
attached as the explanation, and its own probability is included as
`rule_based_probability`. When the two disagree by more than 0.35 the response
says so in the caveats. A probability with no checkable reasoning behind it is
not something to reschedule a crew on.

### What training refuses to do

`POST /ml/train` returning `trained: false` is a normal outcome, not an error.
It trains only on completed activities that have both a planned and an actual
finish -- real outcomes from the project's own schedules, never synthesised --
and refuses when the result would not mean anything:

| `reason` | Refused because |
|---|---|
| `INSUFFICIENT_SAMPLES` | Fewer completed activities than `ML_MIN_TRAINING_SAMPLES`. Counted in **distinct activities**, not rows. |
| `INSUFFICIENT_MINORITY_CLASS` | Too few of one outcome. A model fitted on 3 late and 80 on-time predicts the majority class and scores 96% doing it. |
| `BELOW_ACCURACY_FLOOR` | Out-of-fold ROC AUC under `ML_MIN_HELDOUT_ROC_AUC`. |
| `NOT_BETTER_THAN_BASELINE` | The model does not beat the rule-based arithmetic on the same rows by `ML_BASELINE_MARGIN`. |

That last one is the guard that matters, and it exists because of a real
failure found while validating this phase. A homogeneous training population
-- fifty activities of identical duration and reporting shape -- produces
cross-validation folds that are near-duplicates of each other. The forest
reported a **ROC AUC of 1.000** and was worse than useless: it gave an activity
that provably lands 587 days late a probability of 0.515, where the arithmetic
said 0.953. No accuracy floor can reject a 1.000. Scoring the arithmetic on the
same rows does, because the arithmetic cannot overfit.

Both paths are exercised live: on a rate-homogeneous project the model scores
0.937 against the baseline's 0.944 and is **refused**; on a project where
lateness is driven by monsoon-season finishes -- something the arithmetic only
notes without moving its number -- the model scores 1.000 against 0.501 and is
**promoted**, with `is_monsoon_finish` and the cyclic month features ranked top.

### Where the training rows come from

Getting the sampling moment right is the whole game, and the obvious choice is
wrong. Building each row *just before its activity finished* looks like a
careful leakage guard. It is not one: an activity that finishes late is, the day
before it finishes, already past its planned finish with work outstanding. The
label is then readable straight off the features, and both tiers score
near-perfectly without having predicted anything.

So rows are taken **partway through the planned window** -- at 30%, 50% and 70%
by default -- which is when a planner actually wants an answer and when the
outcome is still open. Several cutoffs per activity both multiply thin history
and match the spread of elapsed fractions seen at serving time. Rows from one
activity are correlated, so cross-validation is **grouped by activity**:
splitting two cutoffs of the same activity across folds would leak between them.

### The features

26 features, all derived from ingested plan data and booked progress. The set
is built around **achieved rate against the rate required**, because that ratio
is what predicts a late finish on execution work; static attributes alone teach
a model which disciplines were historically unlucky rather than which
activities are in trouble now. Unknown values carry an explicit `*_known` flag
rather than a silent zero -- an unstated planned duration and a zero-length one
are different facts, and a tree will split on the difference if you let it.
`GET /ml/features` lists them with plain-language labels.

### Explainability

| Tier | What you get |
|---|---|
| Rule-based | The arithmetic itself, as named drivers, in the plan's own units: *"achieving about 1.5 m/day with 910 m remaining needs about 617 days, against 30 days left in the plan"*. |
| Fitted | The same drivers, plus `notable_features`: inputs that are both influential in the model and unusual for this activity, with the direction and how many standard deviations out. |

`notable_features` is labelled in the response as an indication of what stands
out, **not a decomposition of the probability** — that is the honest limit of
what a tree ensemble can say without a SHAP dependency, and overselling it
would be the same mistake as a fabricated accuracy figure.

### Endpoints

| Method | Path | Access |
|---|---|---|
| POST | `…/ml/train` | project manager |
| GET | `…/ml/models` | project member |
| GET | `…/ml/features` | project member |
| POST | `…/schedules/{sid}/ml/predict` | project manager |
| GET | `…/schedules/{sid}/ml/predictions?risk_level=&predicted_late=` | project member |
| GET | `…/schedules/{sid}/ml/predictions/{activity_id}` | project member |
| GET | `…/schedules/{sid}/ml/risk-summary?top=` | project member |

An empty risk summary says nothing has been predicted yet; it is not a finding
of low risk. A summary older than a week says how stale it is. A stale or
unloadable model artefact falls back to the arithmetic and says the artefact
was rejected, rather than silently producing numbers.

Training and prediction are also available as Celery tasks
(`prediction.train_delay_model`, `prediction.predict_schedule`) — fitting 300
trees and building features for a large schedule should not hold an HTTP
connection open.

## Reports and notifications (Phase 8)

Two independent features sharing one migration: on-demand report artefacts,
and a multi-channel notification inbox. Both persist to `generated_reports`
and `notifications` respectively (added in
`20260902_1500_add_reporting_and_notification_models.py`).

### Report generation

`POST /projects/{id}/generated-reports` takes a `report_type`
(`progress_summary`, `delay_risk`, or `executive_overview`) and an
`output_format` (`PDF` or `XLSX`), pulls a live snapshot of that project's
activities, and renders it through one of two builders:

| Builder | Library | Output |
|---|---|---|
| `PDFReportBuilder` | ReportLab (`SimpleDocTemplate`) | Title block, metadata table, executive summary, and an activity table capped at the top 25 rows — a PDF meant to be read, not a full export. |
| `ExcelReportBuilder` | openpyxl | Three sheets — Executive Summary, Activity Details (every activity, uncapped), Delay Risk Analysis — meant as the full data export the PDF deliberately isn't. |

The generated bytes are SHA-256 hashed, written to `GENERATED_REPORTS_DIR`,
and the row is marked `COMPLETED`; a builder exception is caught, recorded
verbatim in `error_message`, and the row is marked `FAILED` instead of
raising past the API boundary. `storage_path` is an internal filesystem key,
never handed to the client directly — `GET .../download` re-checks project
membership and streams the file only after that passes, the same
membership-then-404 pattern used everywhere else in this codebase.

### Notifications

`Notification` is one row per **channel-specific delivery attempt**, not one
row per event — a service fans an event out to several channels by writing
several rows sharing an `event_key`, so an email failure can't hide an
already-delivered in-app notification. `idempotency_key` is unique at the
database level; resending with the same key returns the original row rather
than dispatching twice.

| Channel | Dispatcher | Status |
|---|---|---|
| `IN_APP` | `InAppDispatcher` | Real — the row itself *is* the delivery; read via the inbox endpoints below. |
| `EMAIL` | `EmailDispatcher` | **Dry-run only.** Logs the send and returns a synthetic `provider_message_id`; no SMTP or provider is wired in. Nothing is actually emailed yet. |
| `WHATSAPP` | `WhatsAppDispatcher` | **Dry-run only**, same reasoning — this is the seam Phase 9's Meta integration plugs into, not a working send path. |

### Endpoints

| Method | Path | Access |
|---|---|---|
| POST | `…/generated-reports` | project member |
| GET | `…/generated-reports` | project member |
| GET | `…/generated-reports/{id}` | project member |
| GET | `…/generated-reports/{id}/download` | project member |
| GET | `/notifications` | authenticated user (own inbox) |
| GET | `/notifications/unread-count` | authenticated user |
| PATCH | `/notifications/{id}/read` | authenticated user (own notifications only) |
| POST | `/notifications/read-all` | authenticated user |
| POST | `…/projects/{id}/notifications` | project manager or admin |

### What "code complete" means here, and what it doesn't

Every file the Phase 8 plan called for exists and is wired into
`api/v1/router.py` — no `TODO`, no `NotImplementedError`, no stub. This was
checked by reading the service, model, dispatcher and API code directly, and
by running `PDFReportBuilder` and `ExcelReportBuilder` standalone against
sample data outside the app: both produced valid binaries (a real `%PDF`
header; a real xlsx zip container that reloads cleanly in openpyxl with the
three sheets above).

What that check *didn't* do is run `tests/test_report_builders.py`,
`tests/test_notification_service.py`, `tests/api/test_generated_reports.py`
or `tests/api/test_notifications.py` against a live Postgres instance — that
requires this project's actual dependencies and a database, neither of which
were available in the environment this review ran in. Run the four files
above with `pytest -v` before treating this row as "Done, validated" like
Phases 1–7; if they pass, flip the table above accordingly.

## Schedule ingestion (Phase 3)

### Nothing is dropped silently

Every import returns and stores a `parse_summary`:

```json
{"rows_read": 412, "activities_created": 409, "rows_skipped_blank": 3,
 "dependencies_created": 387, "dependencies_duplicate": 4,
 "predecessors_unresolved": 11, "dates_unparsed": 0,
 "parents_relinked_to_ancestor": 2, "warnings": ["..."]}
```

A schedule can import `COMPLETED` and still have dropped predecessor edges —
a typo'd predecessor code, a row filtered out as blank, a date in a format we
could not read. Those used to vanish with no trace, so nobody went looking.
The counts are exact; only the example warnings are capped.

### Ambiguity resolved in a fixed order

**Dates** get three passes, and the order is the point: ISO 8601 first
(`2026-05-01` is unambiguously 1 May — passing `dayfirst` at an ISO string
makes pandas return 5 January), then day-first for what remains
(`03/04/2026` in an Indian or European export means 3 April), then one
generic attempt for named months. A single column can hold all three
without either being misread. What survives all three is null *and counted*.

**Dependency lag** is a float column in days, so a stated unit is converted
on the way in: `A1010FS+8h` is eight hours, not eight days, and `+0.5` is
half a day rather than zero.

**WBS gaps** attach to the nearest existing ancestor. An export listing only
leaf rows has no `1.2` for a `1.2.3` to hang off; taking the immediate parent
alone left such nodes parentless, and they then surfaced as top-level roots
beside real L1 activities — a flat list presented as a hierarchy. Each relink
is counted. Duplicate WBS paths are rejected outright, since two rows claiming
one node makes parent linking arbitrary.

### Validation before anything is written

The column mapping and the file are both checked before the schedule row is
created. Creating it first turned a malformed mapping into an unhandled 500
*and* left a schedule stuck in `PENDING` forever, because the code that marks
a schedule `FAILED` lives inside the parser and was never reached. Size,
extension and emptiness are enforced here too — this endpoint has its own,
narrower format list than the global upload allowlist, since accepting a PDF
would create a schedule row and then fail on read.

Extension matching is case-insensitive (`SCHEDULE.CSV` is Excel-on-Windows'
default), and `.xls` is read with `xlrd` rather than `openpyxl`, which cannot
read the legacy BIFF format at all.

Cycle detection is iterative. A linear finish-to-start chain of a few thousand
activities is routine on a pipeline, and recursion blew the stack at around a
thousand — surfacing to the user as a file-content complaint.

### Trees and scoping

`/activities/tree` returns the whole schedule unpaginated. A tree with an
offset window in it is not a tree: a truncated list makes every activity whose
parent fell outside the window look like a root. The ORM `children`
relationship is `raiseload`ed and the tree is built from `parent_id` alone, so
serialisation cannot silently trigger one query per activity.

Ids are checked against their parents, not just for access: a schedule id from
another project, or an activity id from another schedule, is a 404 even when
the caller can see both. Authorising against the object's own project alone
let a member of two projects fetch one project's schedule through the other's
URL.

## Document processing (Phase 4)

Jobs are claimed under `SELECT ... FOR UPDATE` before any work starts. Celery
redelivers tasks — `acks_late`, visibility timeouts, manual retries — and
without a claim two workers process the same upload, the second trips the
unique constraint on `progress_reports.uploaded_file_id`, and the job is
marked `FAILED` *after* the first worker marked it `COMPLETED`. A redelivery
is now a no-op, and a retry of a job whose report already landed refreshes it
rather than failing.

If the broker is unreachable at upload time the job is marked `FAILED` with
the reason. The file is still stored and the job is re-runnable; what it no
longer does is sit in `PENDING` with no task id, leaving a client polling
`/jobs/{id}` forever on a job that existed nowhere.

Note that document upload deliberately requires only project **membership**,
not the manager role, unlike schedule upload — a site supervisor filing a
daily progress report is the primary use case for this endpoint.

## Authorization model

Two independent layers:

**System role** (`users.role`) — one of `ADMIN`, `PROJECT_MANAGER`,
`SITE_SUPERVISOR`. Gates platform-wide capabilities such as listing users or
creating a project at all.

**Project role** (`project_memberships.role`) — the caller's role *on one
project*. A user who is `SITE_SUPERVISOR` system-wide can be the
`PROJECT_MANAGER` of a specific project, and a `PROJECT_MANAGER` system-wide
has no access to a project they are not a member of.

Rules worth knowing:

* Project access is resolved from membership, not from the system role. `ADMIN`
  is the one deliberate bypass and is treated as project manager everywhere.
* A non-member gets **404, not 403**. Confirming that a project id exists is
  itself a leak across the tenancy boundary.
* Creating a project enrols the creator as its project manager, otherwise they
  would immediately lose sight of it.
* A project must always retain at least one project manager; the last one
  cannot be demoted or removed.
* The last active administrator cannot be demoted, and no administrator can
  demote or deactivate themselves.
* Changing a role or deactivating an account revokes that user's refresh
  tokens, so the change applies immediately rather than at token expiry.

## Tokens

Access tokens are short-lived (default 30 min) and carry `role` and `email`
claims. Refresh tokens are long-lived (default 7 days), single-purpose, and
recorded server-side by `jti` so they can genuinely be revoked — a stateless
JWT alone cannot be logged out.

Refresh is **rotating**: presenting a refresh token revokes it and issues a new
one. Replaying an already-revoked token is treated as evidence of theft and
revokes every session for that user.

The `type` claim (`access` / `refresh`) is enforced on decode, so a refresh
token cannot be replayed as an access token.

## Audit trail

`audit_logs` is append-only — the repository raises on update and delete.
Audit writes join the caller's transaction deliberately: if an action rolls
back, its audit row rolls back with it, so the log can never claim something
happened that did not. Registration, login, logout, password change, role and
status changes, and all project and membership mutations are recorded.
