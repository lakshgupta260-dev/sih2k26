# Operations Runbook

For an engineer on call for the SIH 2026 problem statement 26122 backend
(Oil India Limited progress intelligence platform). Read `DEPLOYMENT.md`
first if you haven't deployed this service before — this document assumes
the environment variables and endpoints described there.

## 1. Daily operational checks

- `GET /api/v1/health` — process is up (liveness).
- `GET /api/v1/health/ready` — database is reachable (readiness); `200`
  means `database: "up"`, `503` means `database: "down"`. Remember: the app
  does **not** crash on a DB outage at startup, so this is the only signal
  that traffic should not be routed here — see DEPLOYMENT.md section 7.
- Celery worker(s) alive and consuming: `celery -A app.worker.celery_app
  inspect active` / `inspect ping` from a shell with the same environment.
- Redis reachable: `redis-cli -u "$REDIS_URL" ping`.
- Disk space under `UPLOAD_DIR` and `GENERATED_REPORTS_DIR` — these grow
  unboundedly with uploads and generated reports and are not pruned
  automatically.
- Migration state matches the deployed code:
  `alembic current` should show the same revision as `alembic heads`.
- No unexpected spike in `rate_limit_exceeded` (429) or
  `request_body_too_large` (413) log lines — see the troubleshooting
  entries below for what each means.

## 2. Logs

### Format

Configured in `app/core/logging.py`, controlled by `LOG_LEVEL` and
`LOG_JSON`.

**Plain (`LOG_JSON=false`, the local/dev default):**

```
14:32:07 INFO     [a1b2c3d4e5f6a7b8] app.access: request
```

Format string: `%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s`.

**JSON (`LOG_JSON=true`, recommended for any environment with a log
shipper):**

```json
{"ts": "2026-09-04T14:32:07+0000", "level": "INFO", "logger": "app.access", "message": "request", "request_id": "a1b2c3d4e5f6a7b8", "method": "GET", "path": "/api/v1/health/ready", "status": 200, "duration_ms": 4.21}
```

One JSON object per line. Every extra field passed via `logger.info(...,
extra={...})` is flattened into the top-level object (anything not in the
formatter's reserved-key set), so `method`, `path`, `status`, `duration_ms`
and similar fields ride alongside the standard ones.

Both formatters share a `RequestIdFilter` that stamps every record with the
current request id (`-` if none is set, e.g. in a context with no active
request).

`uvicorn.access` is disabled entirely (`configure_logging` clears and
disables it) because `RequestContextMiddleware` already emits a richer
`request` log line per call with request id and duration — leaving both on
would double every access line.

### Correlation id / `X-Request-ID`

`RequestContextMiddleware` (`app/core/middleware.py`) assigns a request id
for every inbound request: it honours an incoming `X-Request-ID` header if
the caller sent one, otherwise generates one (`uuid4().hex[:16]`). The id is:

- stored in a `ContextVar` (`request_id_ctx`) for the duration of the
  request, so every log line emitted while handling it — including from
  code called deep inside a service — carries the same `request_id`;
- set on `request.state.request_id`, so route handlers can read it;
- echoed back to the caller in the `X-Request-ID` response header (also
  listed in `expose_headers` on the CORS middleware, so browser JS can read
  it);
- logged again on any unhandled exception (`request_failed`) with method,
  path and duration, while the context var is still set, so a crash log line
  is still correlated with its request.

**To trace one request end to end:** get the `X-Request-ID` value from the
client (browser network tab, API client, or the header on the response you
have), then grep the logs for it:

```bash
grep '"request_id": "a1b2c3d4e5f6a7b8"' app.log   # JSON mode
grep '\[a1b2c3d4e5f6a7b8\]' app.log                # plain mode
```

Because the same id threads through everything logged while that request's
context var is set — including calls into services — this recovers the full
sequence of log lines for one request without needing distributed tracing
infrastructure. It does **not** automatically extend into an async Celery
task dispatched from that request: the task's log lines get the worker's own
request id context (`-`, since it's not itself an HTTP request), not the
originating request's id. If you need to correlate a dispatched task back to
its triggering request, look for the project/job id logged in both places
(e.g. `job_id` in the document task logs) rather than the request id.

### Log redaction

`app/core/log_redaction.py` installs a `logging.Filter` (attached to every
root logger handler, not the loggers themselves, so it also catches records
propagating up from child loggers) when `LOG_REDACTION_ENABLED=true`
(default). It masks, in every log record before it reaches a handler:

- Any configured secret value at least 8 characters long: `SECRET_KEY`,
  `META_VERIFY_TOKEN`, `META_APP_SECRET`, `META_ACCESS_TOKEN`,
  `VAPI_SECRET`, `VAPI_API_KEY`, `POSTGRES_PASSWORD` — exact substring match,
  longest values first so one secret that happens to contain another is
  masked whole.
- Phone-number-shaped strings (9–15 digits, optional `+`, not adjacent to
  another alphanumeric character so it doesn't clip request ids, UUIDs, or
  hashes) — replaced with all but the last two digits masked.
- `Bearer <token>` headers appearing in log text.

**This is explicitly mitigation, not a fix.** It was added because the
Phase 9/10 audit (`docs/PHASE9-10-AUDIT.md`, findings 3 and 4) confirmed
`app/api/v1/integrations/meta.py` logs the real `META_VERIFY_TOKEN` in
plaintext on every webhook verification attempt, and separately logs the
entire inbound webhook body (phone numbers, message text) at `WARNING`.
Phase 11 was under instruction not to modify Phase 9/10 files, so the filter
intercepts the leak one layer down instead of at the source. Consequences to
keep in mind:

- It is a substring/regex match, not a redaction-aware log call — it can only
  mask a secret it was told about at filter-construction time, so a *new*
  hardcoded credential or an unrelated leak it wasn't built for will not be
  caught.
- The underlying call sites (`meta.py:47`, `meta.py:73`) are still logging
  the raw values into the logging pipeline; the filter runs after that,
  before the handler. If a future refactor adds a second handler that the
  filter isn't attached to (`install_log_redaction` only attaches to
  handlers present on the root logger at call time), the leak reappears.
- `request_id` is **deliberately never masked**, even though it looks like
  it could match the phone-number pattern in some cases — the boundary
  check in `_PHONE_RE` and the explicit exclusion of `request_id` in the
  filter's reserved-key set exist specifically so tracing a request (section
  2 above) keeps working. Do not "fix" this by adding `request_id` to the
  masked set.

## 3. Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| `/health/ready` returns 503, `/health` returns 200 | Database unreachable — wrong host/credentials, Postgres down, network partition, or connection pool exhausted. | Check `check_database_connection()`'s target: `POSTGRES_HOST`/`POSTGRES_PORT` or `DATABASE_URL`. Confirm Postgres is up (`pg_isready -h <host> -p <port>`). Check `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` against actual concurrent load. Remember the app does not crash-loop on this — it will sit "alive but not ready" until the DB comes back, which is by design (DEPLOYMENT.md section 7). |
| Meta webhook (or any endpoint that dispatches a Celery task) returns 500 | Redis/broker unreachable. `meta.py` calls `.delay()` inline with no error handling, after `db.commit()` — this is documented in `PHASE9-10-AUDIT.md` finding 6. Since it happens after commit, the DB rows (uploaded file, processing job) are already persisted even though the response is a 500. | Confirm Redis: `redis-cli -u "$REDIS_URL" ping`. If down, bring it back and Meta will retry the webhook delivery automatically — **but each retry re-runs the whole handler and creates a fresh `uploaded_files`/`processing_jobs` row**, because there is no idempotency on the WhatsApp message id (finding 5). After a broker outage with retries, expect duplicate ingestion for messages delivered during the outage window and be ready to manually de-duplicate `progress_reports` for the affected time range. |
| Jobs stuck in `PENDING` (never move to `PROCESSING`) | Celery worker not running, not consuming the right queue, or crashed silently. | `celery -A app.worker.celery_app inspect active` / `inspect registered` from an environment with the same config. Confirm the worker process is actually up (`docker compose ps worker`, or your process supervisor). Confirm it's pointed at the same `REDIS_URL`/broker as the API that enqueued the job. |
| `alembic upgrade head` fails with an ambiguous / multiple-heads error | Two migrations both claim the same parent revision — usually an un-noticed merge. | `alembic heads` — CI enforces exactly one head on every push (DEPLOYMENT.md section 6); if you're seeing this outside CI, someone bypassed or predates that check. Merge the heads with `alembic merge -m "merge heads" <rev1> <rev2>` and review the generated merge migration. |
| CI's drift-check step fails ("schema drift detected") | A SQLAlchemy model changed without a corresponding Alembic migration. | Run `alembic revision --autogenerate -m "<description>"` locally against a freshly-migrated database, review the generated file, commit it. |
| A burst of `429` responses / `RATE_LIMITED` errors | Either genuine abuse (credential stuffing on `/auth/login`, a scripted client loop), or `TRUST_PROXY_HEADERS` misconfigured relative to your actual network path. | Check `X-RateLimit-Limit` / `X-RateLimit-Remaining` on responses and the `rate_limit_exceeded` log line's `path` field — auth paths (`/auth/login`, `/auth/register`, `/auth/refresh`, `/auth/password`) get a much tighter budget (10/min by default) than everything else (300/min by default). If a single legitimate client behind a load balancer is being uniformly throttled, and there is a trusted reverse proxy in front of the app, check whether `TRUST_PROXY_HEADERS` should be `true`. If it's `true` and there is *not* a trusted proxy actually setting `X-Forwarded-For`, an attacker can rotate that header to dodge the limiter entirely — see DEPLOYMENT.md's security checklist. Remember the limiter is in-memory per-process: with N uvicorn workers the effective ceiling is `N × RATE_LIMIT_REQUESTS`. |
| `413` (`PAYLOAD_TOO_LARGE`) responses | Request body exceeds `MAX_REQUEST_BODY_BYTES` (64 MiB default), or the upload's own type-aware cap (`MAX_UPLOAD_SIZE_MB`, 50 MB default) for upload endpoints specifically. | Check the `request_body_too_large` log line for `path`, `bytes`, `limit`. If it's a legitimate large file that should be allowed, raise `MAX_UPLOAD_SIZE_MB` (and `MAX_REQUEST_BODY_BYTES` if needed) rather than disabling the check. |
| Report generation fails | Multiple possible causes: the underlying data query failing, disk full under `GENERATED_REPORTS_DIR`, or a dependency (e.g. a template renderer) erroring. | Check the request's correlation id in the logs for the actual exception (`request_failed` log line, or the service-level exception logged by the report code) — trace via `X-Request-ID` as in section 2. Confirm `GENERATED_REPORTS_DIR` exists, is writable by the running user (`appuser`, uid 1000, in the Docker image), and has free space. |
| ML training refuses to promote a new model | **This is correct behaviour, not a bug.** Training refuses to promote a model that doesn't clear `ML_MIN_HELDOUT_ROC_AUC` (0.6 default) or that fails to beat the rule-based baseline by `ML_BASELINE_MARGIN` (0.02 default ROC AUC) — the baseline-comparison guard exists specifically because a homogeneous training set can produce a flattering cross-validated score that a floor alone wouldn't catch. Also refuses outright below `ML_MIN_TRAINING_SAMPLES` (40) or `ML_MIN_MINORITY_SAMPLES` (8), where any reported accuracy would be noise. | Do not treat this as an incident. The rule-based rate forecast continues to serve predictions in the meantime, and every prediction response says which tier (model vs. rule-based) produced it. If promotion is expected to succeed and isn't, check the training run's logged metrics (`train_task_failed` / the training outcome dict) for the actual ROC AUC and sample counts against the thresholds above — the fix, if any, is more/better training data, not lowering the thresholds to force a promotion. |

### The known trap: "119 passed, 200 skipped" looks like a partial pass — it is total failure

If PostgreSQL is unreachable when running the test suite, pytest's fixtures
that need a database **skip** rather than error, and the summary line reads
something like:

```
119 passed, 200 skipped
```

This *reads* like "most things passed, a chunk got skipped for some minor
reason" — it is not. It means the database-dependent fixtures never even ran,
so effectively nothing meaningful was tested. This exact failure mode is
called out explicitly in `.github/workflows/ci.yml`'s comments as one of the
three things the pipeline exists to prevent, and CI has a hard guard for it:

```yaml
- name: Fail if tests were skipped wholesale
  run: |
    skipped=$(grep -oE '[0-9]+ skipped' pytest-output.txt | grep -oE '[0-9]+' | head -1 || echo 0)
    if [ "$skipped" -gt 20 ]; then
      echo "::error::$skipped tests skipped -- the test database was probably unreachable"
      exit 1
    fi
```

If you ever see a large skip count locally (well above the small number
expected from genuinely optional-dependency tests, e.g. the
`sentence_transformer` embedding path when that package isn't installed),
your first move is to check `POSTGRES_HOST`/`POSTGRES_PORT` connectivity, not
to assume the code is 85%+ working. A skip count above 20 is CI's exact
threshold for treating this as a hard failure.

## 4. Backup and restore

**What must be backed up:**

1. **The PostgreSQL database** — schedules, activities, progress reports,
   users, matching results, delay predictions, audit logs. Standard
   `pg_dump`/`pg_basebackup`/managed-service snapshot practices apply; no
   special handling is documented in this codebase beyond that.
2. **`UPLOAD_DIR`** (default `uploads/`) — original uploaded files
   (schedules, progress documents, WhatsApp-ingested attachments).
3. **`GENERATED_REPORTS_DIR`** (default `generated_reports/`) — generated
   report artefacts.

**Why all three, together, matter:** rows in the database (`uploaded_files`,
`processing_jobs`, generated report records) reference files on disk **by
path**, not by embedding the file content. A database-only restore leaves
these rows pointing at files that no longer exist — the metadata says a
report or upload exists, but any attempt to open, re-process, or re-download
it will fail. Back up and restore the database and both directories
**together, from consistent points in time**, or treat any restore that
skips the directories as producing dangling references that need manual
reconciliation (e.g. flagging affected rows, or asking users to re-upload).

If you're also running model training, consider whether `ML_MODEL_DIR`
(default `storage/models/`) needs to be part of your backup scope — it holds
one fitted-model file per version, and delay predictions are traceable back
to the exact model that produced them by this path.

## 5. Celery worker operation

**Starting a worker** (native):

```bash
celery -A app.worker.celery_app worker --loglevel=INFO
```

Same command inside Docker Compose's `worker` service. The Celery app
(`app/worker.py`) is configured with `task_track_started=True`, JSON
serialization for tasks and results, and UTC timezone throughout. It only
explicitly registers `app.tasks.document_tasks` via `include=[...]` — but the
other task modules (`matching_tasks.py`, `prediction_tasks.py`) register
their tasks via the `@celery_app.task(...)` decorator at import time, so they
become available once anything imports them (they are imported by the API
code paths that dispatch them).

**Queue:** a single default Celery queue — no custom queue routing is
configured. All three task types (document processing, matching runs, model
training/prediction) share it. There is no separate high/low priority queue,
so a burst of one task type (e.g. a bulk document upload) can delay another
(e.g. a matching run) behind it if there's only one worker process/concurrency
slot. Scale worker concurrency (`-c <N>` or `--autoscale`) or run dedicated
worker pools per queue if that becomes an issue — neither is currently
configured.

**Registered tasks:**

| Task name | Module | Purpose |
|---|---|---|
| `documents.process_uploaded_file` | `app/tasks/document_tasks.py` | Parses one stored upload into a `ProgressReport`. Claims the job row with `SELECT ... FOR UPDATE` before processing, specifically to survive Celery's at-least-once redelivery semantics (acks_late, visibility timeout, manual retry) without double-processing. |
| `matching.run_project_matching` | `app/tasks/matching_tasks.py` | Runs extraction and matching for every unprocessed report in a project. Reloads the acting user by id inside its own DB session so the run is attributed correctly. |
| `prediction.train_delay_model` | `app/tasks/prediction_tasks.py` | Fits the delay-prediction model for a project (CPU-bound: a few-hundred-tree forest); kept off the request path so a planner's click doesn't hold an HTTP connection through the fit. |

**Tasks are written to never raise.** Each of the above wraps its body in
`try/except Exception` and, on failure, rolls back its session, logs via
`logger.exception(...)`, and **returns an error dict** (e.g.
`{"error": str(exc)}`) rather than letting the exception propagate and mark
the Celery task `FAILED`. Operational implications:

- Do not rely on Celery's own failure/retry machinery (e.g. `task.state ==
  "FAILURE"`) to detect a failed matching run or training run — check the
  returned dict's `error` key instead, or check application-level state
  (e.g. `ProcessingJob.status`, which document tasks do set to `FAILED`
  explicitly on the job row itself even though the Celery task "succeeds").
- Monitoring/alerting built on Celery task state alone will under-report
  failures here. Alert on the `*_task_failed` log events
  (`matching_task_failed`, `train_task_failed`) instead, or on the
  application-level status columns these tasks write.

## 6. Capacity notes

From `docs/PERFORMANCE.md`, measured against a 5,000-activity, ~91,470-row
progress-history dataset shaped like a real Oil India L1–L6 schedule
(pyramid WBS, ~60% of rows at L6, 3,049 leaf activities), on a single
container with PostgreSQL 16 over a unix socket:

| Read path | Median time | Queries |
|---|---|---|
| Progress rollup (whole schedule) | 422.3 ms | 5 |
| Progress summary | 323.8 ms | 5 |
| S-curve (planned vs actual) | 1,789.1 ms | 5 |
| `_latest_progress` (internal) | 127.3 ms | 2 |
| Delete one user | 5.5 ms | — |

Notes for capacity planning:

- Query counts are flat (2–5) and independent of project size on the
  measured paths — there is no known N+1 to budget for.
- The S-curve is deliberately the slowest of these (~1.8 s at this scale)
  because, unlike the rollup, it needs the full reporting history to answer
  "what was true as of each past sample date" — it cannot be reduced to one
  row per activity the way the rollup was. `PERFORMANCE.md` records this as
  accepted for now (not on the critical path of a site supervisor filing a
  report) with three documented options if it later needs to be faster:
  caching per `(schedule, as-of-week)` in Redis, materializing cumulative
  earned value per activity per week on write, or pushing the interpolation
  into a SQL window function.
- These numbers scale with **reporting history**, not just project size —
  a project that has been running for years with dense daily reporting will
  be slower on the S-curve than a same-size project with sparse reporting,
  even though the rollup paths (fixed at "latest row per activity") stay
  flat.
- The benchmark's own reproduction commands, if you need to re-measure after
  a schema or query change:
  ```bash
  cd backend
  python -m perf.seed_perf_data --activities 5000 --reports-per-activity 30
  python -m perf.benchmark
  ```
  `tests/test_performance_regressions.py` (8 tests) guards the *properties*
  that keep these numbers this way (e.g. that `_latest_progress` still
  issues exactly one `DISTINCT ON` statement) rather than asserting
  wall-clock thresholds, specifically because a timing assertion in CI is
  flaky on a loaded runner.
