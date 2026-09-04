# Architecture

Backend for SIH 2026 problem statement 26122 — an AI-assisted
planning-to-execution progress intelligence platform for Oil India Limited. The
job it does: take a planned L1–L6 project schedule, take whatever the site
actually reports (spreadsheets, PDFs, DPRs, WhatsApp messages, voice calls),
reconcile the two, and say where the project really is and what is likely to
slip.

## Shape

A **modular monolith**, not microservices. One FastAPI application, one
PostgreSQL database, one Celery worker pool. This is a deliberate choice for a
system whose core operation is a *join* — planned activity against reported
progress against forecast — where splitting the schedule, progress and
prediction domains across services would turn every meaningful read into a
distributed query and every write into a consistency problem, in exchange for
independent deployability that nobody needs yet.

```
                        ┌─────────────────────────────────────────┐
   HTTP / JWT ─────────▶│  app/api/v1          routers, guards    │
                        ├─────────────────────────────────────────┤
   WhatsApp webhook ───▶│  app/schemas         request/response   │
   Vapi webhook ───────▶│                      contracts          │
                        ├─────────────────────────────────────────┤
                        │  app/services        business logic     │
                        ├──────────────┬──────────────┬───────────┤
                        │ app/ai       │ app/ml       │ app/reports│
                        │ extraction   │ delay        │ pdf/xlsx   │
                        │ + matching   │ forecasting  │ builders   │
                        ├──────────────┴──────────────┴───────────┤
                        │  app/repositories    query construction │
                        ├─────────────────────────────────────────┤
                        │  app/models          SQLAlchemy mapping │
                        └──────────────┬──────────────────────────┘
                                       │
                        ┌──────────────▼──────────┐   ┌──────────────┐
                        │  PostgreSQL 16          │   │ Redis        │
                        │  19 tables              │◀──│ Celery broker│
                        └─────────────────────────┘   └──────────────┘
```

Roughly 14,300 lines of application code and 7,300 lines of tests across 68
routes, 19 tables and 12 migrations.

## Layering, and what each layer is not allowed to do

The rule that keeps this maintainable is that each layer may only call the one
below it.

| Layer | Holds | Must not |
|---|---|---|
| `app/api/v1` | Routers, path/query binding, auth dependencies | Contain business logic or build queries |
| `app/schemas` | Pydantic request/response contracts | Touch the database or ORM models |
| `app/services` | Business rules, transactions, audit writes | Know about HTTP status codes or `Request` |
| `app/repositories` | Query construction, eager/raise-load policy | Make business decisions |
| `app/models` | SQLAlchemy mappings, constraints, indexes | Import services or schemas |

`app/ai`, `app/ml`, `app/reports`, `app/notifications` and
`app/document_processing` hang off the service layer as pluggable capabilities.
They are called by services and never call back up.

`app/core` is cross-cutting: configuration, logging, security, middleware,
exceptions, and the Phase 11 hardening modules.

## Authorization

Three roles, fixed: `ADMIN`, `PROJECT_MANAGER`, `SITE_SUPERVISOR`. Project
access is by **membership**, not by role alone — a project manager on project A
has no access to project B.

Two dependencies in `app/api/deps.py` carry this, and endpoints are expected to
depend on one of them rather than accepting a raw `project_id`:

- `AccessibleProject` — the caller is a member (or an administrator). Reads.
- `ManagedProject` — the caller is a manager of *this* project (or an
  administrator). Writes and configuration.

Two conventions matter more than they look:

**A non-member gets 404, not 403.** Returning 403 would confirm that a project
with that id exists, which leaks the shape of the tenancy to anyone who can
guess an id. Every project-scoped route follows this.

**The ownership chain is verified, not assumed.** It is not enough to check
that the caller can see the project named in the path — the object must
actually belong to it. A route like
`/projects/{p}/schedules/{s}/activities/{a}` verifies that `schedule.project_id
== p` and `activity.schedule_id == s`. Without that, a caller who is a
legitimate member of project A can read project B's activity by pairing A's
project id with B's activity id. This class of hole was found and closed in
Phases 3, 4 and 6.

`tests/test_auth_boundary_matrix.py` enumerates the live route table and
asserts that all 59 non-public routes reject both anonymous callers and forged
bearer tokens, so a route added later cannot ship without a guard. The 8 public
routes are listed explicitly with a stated reason.

## The data model, and where truth lives

Nineteen tables. The ones that carry the domain:

```
users ──┬── project_memberships ──── projects ──┬── schedules ──── activities
        │                                       │                     │
        │                                       │            activity_dependencies
        │                                       │
        │                                       ├── uploaded_files ── processing_jobs
        │                                       │         └── progress_reports
        │                                       │                  └── extracted_activities
        │                                       │                            │
        │                                       │                    activity_matches
        │                                       │                            │
        │                                       ├──────────────────── actual_progress
        │                                       ├── delay_predictions ── delay_model_versions
        │                                       ├── generated_reports
        │                                       └── notifications
        └── refresh_tokens                          audit_logs
```

Two things about this shape are easy to get wrong, and did get got wrong twice:

**An `Activity` has no `project_id`.** It belongs to a `Schedule`, and the
schedule belongs to the project. Filtering activities by project means joining
through `schedules`. Two separate phases shipped code that queried
`Activity.project_id` — a column that does not exist — and both crashed at
runtime (Phase 8's report generator, documented in the git history; Phase 9/10's
voice assistant tools, documented in `PHASE9-10-AUDIT.md` finding 7).

**Status and percent-complete are not on `Activity` either.** They live on
`actual_progress`, one row per activity per reporting date. "Current status" is
therefore a *query*, not a field: the latest row per activity. The planned
schedule and the reported actuals are kept strictly separate, which is the whole
point of the product — the variance between them is the answer.

## The pipeline

The system's spine, from a document arriving to a forecast coming out.

```
 1. Schedule ingestion      XLSX/CSV/XLS/MPP-export ──▶ schedules + activities
    app/services/schedule_parser.py                     + activity_dependencies
                                                        + parse_summary (JSONB)

 2. Document intake         PDF/XLSX/CSV/image/WhatsApp ──▶ uploaded_files
    app/services/document.py                              + processing_jobs
                                                          (Celery, row-locked)

 3. Extraction              raw text ──▶ extracted_activities
    app/ai/                 (activity codes, quantities, dates, disciplines)

 4. Matching                extracted item ──▶ activity_matches
    app/services/matching.py  fuzzy + embedding candidates, scored,
                              AUTO_MATCHED / NEEDS_REVIEW / NONE

 5. Human review            confirm / reject / reassign  (audited)
    app/api/v1/matching.py

 6. Booking                 confirmed matches ──▶ actual_progress
    app/services/progress.py  rollup, S-curve, variance

 7. Forecasting             features ──▶ delay_predictions
    app/ml/                   rule-based always; RandomForest only if promoted
```

The design principle running through steps 1–4 is **nothing is dropped
silently**. Every skipped row, unparseable date and unresolved predecessor is
counted and surfaced in a stored `parse_summary` rather than discarded, because
a schedule importer that quietly loses 300 activities is worse than one that
refuses the file.

Step 5 is not optional. Matching proposes; a human disposes. Automatic matches
above the confidence threshold are booked, everything ambiguous queues for
review, and every decision is written to `audit_logs` with the actor.

## Delay forecasting

Two tiers, and the second one has to earn its place.

**Tier 1 — deterministic rate arithmetic** (`app/ml/baseline.py`). Achieved
rate versus required rate, adjusted for predecessor slip, stale reporting and
late starts. Always available, explainable line by line, needs no training
data. This is what answers the question on day one of a project.

**Tier 2 — a fitted `RandomForestClassifier`** (`app/ml/model.py`), trained on
completed activities, 26 features, and promoted **only** if it passes:

- minimum training rows and minimum minority-class rows,
- `StratifiedGroupKFold` cross-validation grouped by `activity_id`, so the
  several training rows sampled from one activity cannot straddle a fold and
  leak,
- a held-out ROC AUC floor, and
- **a baseline-comparison guard**: the rule-based forecast is scored on the
  *identical rows*, and the model is refused with `NOT_BETTER_THAN_BASELINE`
  unless it beats that by a configured margin.

That last guard exists because of a measured failure. On a rate-homogeneous
project the model reported a **cross-validated ROC AUC of 1.000** and gave an
activity that provably finished 587 days late a probability of 0.515, where the
rule-based arithmetic gave 0.953. No accuracy or AUC floor can reject a perfect
score. Comparing against the baseline on the same rows does: that model scored
0.937 against the baseline's 0.944 and was correctly refused, while on a
monsoon-driven project the model scored 1.000 against a baseline of 0.501 and
was correctly promoted.

Training rows are sampled at fixed fractions (30/50/70%) of each activity's
planned window rather than near its finish, because an activity already past
its planned finish with work outstanding is trivially identifiable as late —
sampling there leaks the label.

The system reports which tier produced any given number. `PredictionMethod` is
stored on every prediction (`RULE_BASED_RATE`, `RANDOM_FOREST`,
`NOT_FORECASTABLE`) and never inferred by a client. "We don't know yet" is a
first-class answer rather than a low-risk one.

## Background work

Celery over Redis. Four tasks, all registered via `app.worker.TASK_MODULES`.

The job state machine is the part worth knowing about. `process_uploaded_file`
claims its job under `SELECT ... FOR UPDATE` before doing anything, and
re-reads under lock before recording a failure. Celery redelivers — on
`acks_late`, on a visibility timeout, on a manual retry — and without the claim
two workers process the same upload, the second trips the unique constraint on
`progress_reports.uploaded_file_id`, and marks the job `FAILED` *after* the
first already marked it `COMPLETED`. The API would then report a failure for a
document that processed fine.

Tasks are written **never to raise**. They return an error dict instead, because
a raising task takes the worker down or gets retried forever, and either way one
bad project stops every other project's jobs.

## Request middleware

Registered outermost-first in `app/main.py` (Starlette runs them in reverse
registration order):

| Order | Middleware | Why there |
|---|---|---|
| 1 | `CORSMiddleware` | A rejected preflight must still carry CORS headers |
| 2 | `RateLimitMiddleware` | Reject floods before any body is read |
| 3 | `BodySizeLimitMiddleware` | Reject oversized bodies before routing |
| 4 | `SecurityHeadersMiddleware` | Wraps the app so error responses get headers too |
| 5 | `RequestContextMiddleware` | Innermost; correlation id available to handlers |

Every response carries a correlation id in `X-Request-ID` and every log line
carries it, which is how one request is traced across the access log, the
service layer and a worker.

## Configuration

Two settings objects, both `pydantic-settings` reading the environment and
`.env`:

- `app.core.config.Settings` — the application.
- `app.core.hardening.HardeningSettings` — Phase 11 rate limits, body caps,
  header policy and log redaction. Separate because Phase 11 was under
  instruction not to modify any Phase 9/10 file, and `config.py` was one; the
  deployment contract is unchanged by where the class lives.

`SECRET_KEY` is validated as required outside local. Rate limiting defaults
**off** under `ENVIRONMENT=test`, because a test suite is indistinguishable from
an attacker to a rate limiter — every request from one client with no pause —
and leaving it on broke 30+ unrelated tests with 429 where they asserted 401.

## Known architectural gaps

Stated rather than glossed, because they are the things a reviewer should ask
about.

1. **The two provider webhooks fail open.** `META_APP_SECRET` and `VAPI_SECRET`
   both default to `None`, and both handlers treat "no secret configured" as
   "allow". An unauthenticated caller can read project data and inject forged
   progress reports. Reproduced; see `PHASE9-10-AUDIT.md` findings 1 and 2.
   Setting both secrets closes it today with no code change.
2. **WhatsApp ingestion is not idempotent.** The WhatsApp message id is
   available and unused, so a redelivered message is ingested again — and the
   handler returns 500 when the broker is down, which is precisely what makes
   Meta redeliver. Findings 5 and 6.
3. **Caller identity on the voice/WhatsApp path is a phone-number substring
   match**, resolved with `.first()`. Findings 11 and 12.
4. **The S-curve is still ~1.8 s** on a 5,000-activity schedule with three
   months of reporting. It genuinely needs full history, so the next step is
   caching or a materialised rollup rather than a query tweak. See
   `PERFORMANCE.md`.
5. **In-process rate limiting.** Counters are per-worker, so the effective
   limit is `workers x budget`. Adequate for credential stuffing and client
   loops; a shared Redis counter is a small change when it matters.
6. **No frontend Content-Security-Policy.** The API's CSP is deliberately
   permissive enough for Swagger UI. A browser client needs its own, tighter
   one.
