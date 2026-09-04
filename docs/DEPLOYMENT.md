# Deployment Guide

Backend for Smart India Hackathon 2026 problem statement 26122 — AI-Powered
Planning-to-Execution Project Progress Intelligence Platform, for Oil India
Limited. FastAPI + SQLAlchemy 2.x + Alembic + PostgreSQL 16 + Celery/Redis +
scikit-learn.

This document covers local setup, Docker Compose, the full environment
variable contract, and the checks to run before anything goes near a public
network. Read the **Pre-Production Security Checklist** before deploying to
staging or production — two of its items are unauthenticated-access holes,
not hardening suggestions.

## 1. Prerequisites

| Component | Version | Notes |
|---|---|---|
| Python | 3.11 | Matches the Docker base image (`python:3.11-slim`) and CI (`PYTHON_VERSION: "3.11"`). |
| PostgreSQL | 16 | `postgres:16-alpine` in Compose, `postgres:16` in CI. |
| Redis | 7 | Celery broker and result backend. |
| Docker / Docker Compose | current | For the containerised path. |
| pip packages | pinned in `requirements.txt` | FastAPI 0.115.6, SQLAlchemy 2.0.36, Alembic 1.14.0, psycopg 3.2.3, scikit-learn 1.6.0, PyJWT 2.10.1, passlib 1.7.4 + bcrypt 4.0.1 (pinned together — see the comment in `requirements.txt`), rapidfuzz 3.10.1. |

Optional: `sentence-transformers==3.3.1` if you want `EMBEDDING_PROVIDER=sentence_transformer`
instead of the default lexical TF-IDF (adds roughly 1–2 GB to the environment;
the matcher falls back to TF-IDF automatically if it is not installed).

## 2. Local setup from a clean clone

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env
# Edit .env: at minimum set POSTGRES_PASSWORD if you're not using the
# development default, and CORS_ORIGINS for your frontend's origin.

# Create the database (native Postgres, not Compose):
createdb -h localhost -U postgres sih26122
# or: psql -h localhost -U postgres -c "CREATE DATABASE sih26122;"

alembic upgrade head

uvicorn app.main:app --reload
# API on http://localhost:8000, docs at /docs, OpenAPI at /api/v1/openapi.json
```

In a second terminal, run a Celery worker (needed for document processing,
matching runs and model training — anything dispatched via `.delay()`):

```bash
source .venv/bin/activate
celery -A app.worker.celery_app worker --loglevel=INFO
```

The worker and the API process both read the same `.env` / environment and
must agree on `DATABASE_URL` / `POSTGRES_*` and `REDIS_URL`, since the worker
opens its own `SessionLocal()` per task rather than sharing the API's
connection.

If `SECRET_KEY` is left blank locally, `Settings` auto-generates an ephemeral
one per process (`app/core/config.py`, `_validate_secret`). That means tokens
issued by the API process will not validate if verified by a separately
started worker process expecting its own ephemeral key — for any local
scenario where JWTs need to survive across processes, set `SECRET_KEY`
explicitly even locally.

## 3. Docker Compose path

```bash
cd backend
cp .env.example .env
docker compose up --build
```

What's actually in `docker-compose.yml`:

- **`db`** — `postgres:16-alpine`, health-checked with `pg_isready`, persisted
  to a named volume `pgdata`, port `5432` exposed on the host.
- **`redis`** — `redis:7-alpine`, health-checked with `redis-cli ping`.
- **`api`** — built from the local `Dockerfile`, waits on both health checks
  (`depends_on: condition: service_healthy`), overrides `POSTGRES_HOST=db`
  and `REDIS_URL=redis://redis:6379/0` regardless of what `.env` says (the
  container-to-container hostnames always win), mounts `./uploads` and
  `./generated_reports` from the host, and runs:
  ```
  alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
  ```
  i.e. **migrations are applied automatically on container start.** `--reload`
  is present in the committed command — appropriate for a hackathon/demo
  Compose file, not for a production image (see the checklist below).
- **`worker`** — same image, same env overrides, mounts `./uploads` only (not
  `generated_reports`), runs `celery -A app.worker.celery_app worker --loglevel=INFO`.

The `Dockerfile` itself (`backend/Dockerfile`):

- `python:3.11-slim` base, `PYTHONUNBUFFERED=1`, `PIP_NO_CACHE_DIR=1`.
- Installs `build-essential`, `curl`, `libpq5`, then `pip install -r requirements.txt`.
- Copies the app, creates a non-root user `appuser` (uid 1000), creates and
  chowns `/app/uploads` and `/app/generated_reports`, then `USER appuser`.
- `HEALTHCHECK` hits `curl -fsS http://localhost:8000/api/v1/health` every
  30s (start period 20s, 3 retries) — this is the **liveness** endpoint, not
  readiness; see section 6.
- Default `CMD` runs plain `uvicorn` with no `--reload` — Compose overrides
  this with its own `command:` that adds `--reload`, so a production image
  built from this Dockerfile without Compose's override does the right
  thing already.

## 4. Environment variable reference

All settings are read by two Pydantic `BaseSettings` classes: `app.core.config.Settings`
(business/general config) and `app.core.hardening.HardeningSettings` (Phase 11
rate limiting, body caps, headers). Both read from `.env` and the process
environment, case-insensitively. Defaults below are the real class defaults
(from source, not aspirational).

### General

| Variable | Default | Required in production? | Notes |
|---|---|---|---|
| `ENVIRONMENT` | `local` | Yes — set explicitly | One of `local`, `development`, `staging`, `production`, `test`. Gates the `SECRET_KEY` requirement and disables rate limiting only under `test`. |
| `DEBUG` | `false` (`.env.example` ships `true` for local) | Yes — must be `false` | Never run with `DEBUG=true` outside local/dev. |
| `LOG_LEVEL` | `INFO` | No | Standard `logging` level name. |
| `LOG_JSON` | `false` | Recommended `true` | Switches to one-JSON-object-per-line output for log shippers; see OPERATIONS.md. |

### Security

| Variable | Default | Required in production? | Notes |
|---|---|---|---|
| `SECRET_KEY` | `""` | **Yes — enforced** | `Settings._validate_secret` raises `ValueError` at startup if empty and `ENVIRONMENT` is `staging` or `production`. If non-empty but under 32 characters in those environments, it also raises. Generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Left blank in `local`/`development`/`test`, an ephemeral per-process key is generated instead (tokens won't survive a restart or be shared across processes). |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | No | JWT access token lifetime. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | No | |
| `ALGORITHM` | `HS256` | No | Not exposed in `.env.example`; change only with a matching code review. |
| `BCRYPT_ROUNDS` | `12` | No | |

### Database

| Variable | Default | Required in production? | Notes |
|---|---|---|---|
| `POSTGRES_HOST` | `localhost` | Yes (set to real host) | `db` inside Compose. |
| `POSTGRES_PORT` | `5432` | No | |
| `POSTGRES_USER` | `postgres` | Yes (set to real value) | |
| `POSTGRES_PASSWORD` | `postgres` | **Yes — change from default** | `.env.example` ships `change-me`. Never leave at `postgres`. |
| `POSTGRES_DB` | `sih26122` | No | |
| `DATABASE_URL` | `None` | Optional | Full SQLAlchemy URL; overrides the `POSTGRES_*` parts when set (`sqlalchemy_database_uri` computed field). Used directly by CI and is the simplest override for managed Postgres (RDS, Cloud SQL, etc). |
| `DB_POOL_SIZE` | `10` | No | |
| `DB_MAX_OVERFLOW` | `20` | No | |
| `DB_POOL_PRE_PING` | `true` | No | |
| `DB_ECHO` | `false` | No — keep `false` | Logs every SQL statement; do not enable in production. |

### Redis / Celery

| Variable | Default | Required in production? | Notes |
|---|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | Yes (set to real host) | Used as both Celery broker and result backend unless overridden. |
| `CELERY_BROKER_URL` | `None` | No | Overrides `REDIS_URL` for the broker only (`celery_broker` computed field). |
| `CELERY_RESULT_BACKEND` | `None` | No | Overrides `REDIS_URL` for the backend only. |

### CORS / uploads

| Variable | Default | Required in production? | Notes |
|---|---|---|---|
| `CORS_ORIGINS` | `["http://localhost:3000"]` | **Yes — set to real frontend origin(s)** | Comma-separated in `.env` (`_split_csv` validator); JSON array also accepted. `allow_credentials=True` is set in `main.py`, so this must never be `*` in production. |
| `UPLOAD_DIR` | `uploads` | No | Created at startup if missing (`_ensure_runtime_dirs`). Back this up (see OPERATIONS.md). |
| `GENERATED_REPORTS_DIR` | `generated_reports` | No | Same. |
| `MAX_UPLOAD_SIZE_MB` | `50` | No | Type-aware cap enforced by the upload endpoints; see also `MAX_REQUEST_BODY_BYTES` below, which is a separate, larger backstop. |
| `ALLOWED_UPLOAD_EXTENSIONS` | `.pdf,.xlsx,.xls,.csv,.txt,.png,.jpg,.jpeg,.xer,.xml` | No | Comma-separated. |

### ML / matching / providers

| Variable | Default | Required in production? | Notes |
|---|---|---|---|
| `LLM_PROVIDER` | `none` | No | `none` \| `anthropic` \| `openai`. With `none`, extraction uses the deterministic rule-based extractor and says so in every response — nothing is fabricated. |
| `LLM_MODEL` | `""` | Only if `LLM_PROVIDER` set | |
| `LLM_API_KEY` | `""` | Only if `LLM_PROVIDER` set | Treat as a secret; masked by log redaction if configured (see OPERATIONS.md). |
| `LLM_TIMEOUT_SECONDS` | `30` | No | |
| `LLM_MAX_LINES_PER_CALL` | `40` | No | |
| `EMBEDDING_PROVIDER` | `tfidf` | No | `tfidf` \| `sentence_transformer`. Falls back to `tfidf` automatically if `sentence-transformers` isn't installed. |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | No | |
| `OCR_PROVIDER` | `noop` | No | |
| `MATCH_AUTO_THRESHOLD` | `0.82` | No | Must be ≥ `MATCH_REVIEW_THRESHOLD` (validated). |
| `MATCH_REVIEW_THRESHOLD` | `0.55` | No | |
| `MATCH_MAX_CANDIDATES` | `5` | No | |
| `MATCH_BLOCKING_LIMIT` | `400` | No | |
| `MATCH_WEIGHT_EXACT_CODE` | `1.00` | No | |
| `MATCH_WEIGHT_KEYWORD` | `0.55` | No | |
| `MATCH_WEIGHT_FUZZY` | `0.80` | No | |
| `MATCH_WEIGHT_EMBEDDING` | `0.70` | No | |
| `MATCH_WEIGHT_DISCIPLINE` | `0.35` | No | |
| `MATCH_WEIGHT_LOCATION` | `0.60` | No | |
| `MATCH_WEIGHT_HIERARCHY` | `0.25` | No | |
| `ML_MODEL_DIR` | `storage/models` | No | Fitted model artefacts, one file per version. Back this up if trained models matter operationally. |
| `ML_MIN_TRAINING_SAMPLES` | `40` | No | Training refuses below this (counted in distinct completed activities). |
| `ML_MIN_MINORITY_SAMPLES` | `8` | No | |
| `ML_MIN_HELDOUT_ROC_AUC` | `0.60` | No | Promotion floor. |
| `ML_CV_FOLDS` | `5` | No | |
| `ML_BASELINE_MARGIN` | `0.02` | No | Margin a new model must beat the rule-based forecast by, in ROC AUC, to be promoted. |
| `ML_N_ESTIMATORS` | `300` | No | |
| `ML_MAX_DEPTH` | `8` | No | |
| `ML_MIN_SAMPLES_LEAF` | `3` | No | |
| `ML_RANDOM_STATE` | `42` | No | |
| `ML_RISK_MEDIUM_THRESHOLD` | `0.35` | No | Must increase: MEDIUM ≤ HIGH ≤ CRITICAL (validated). |
| `ML_RISK_HIGH_THRESHOLD` | `0.60` | No | |
| `ML_RISK_CRITICAL_THRESHOLD` | `0.80` | No | |

### Meta / WhatsApp integration

| Variable | Default | Required in production? | Notes |
|---|---|---|---|
| `META_VERIFY_TOKEN` | `None` | Yes, if the Meta webhook is exposed | Used for the GET verification handshake. |
| `META_APP_SECRET` | `None` | **CRITICAL — yes, if the Meta webhook is exposed** | See the security checklist below. Fails **open** (no signature check at all) when unset. |
| `META_ACCESS_TOKEN` | `None` | Yes, if sending WhatsApp messages | |
| `META_PHONE_NUMBER_ID` | `None` | Yes, if sending WhatsApp messages | |

### Vapi / voice assistant

| Variable | Default | Required in production? | Notes |
|---|---|---|---|
| `VAPI_SECRET` | `None` | **CRITICAL — yes, if the Vapi webhook is exposed** | See the security checklist below. Fails **open** (any caller is treated as authenticated) when unset. |
| `VAPI_API_KEY` | `None` | Yes, if calling out to Vapi | |

### Phase 11 hardening (`app.core.hardening.HardeningSettings`)

| Variable | Default | Required in production? | Notes |
|---|---|---|---|
| `RATE_LIMIT_ENABLED` | `true` | Recommended `true` | Auto-disabled under `ENVIRONMENT=test` unless explicitly set in the environment (see `_disable_rate_limiting_under_test`). In-memory, per-process — with N workers the effective sustained budget is `N × RATE_LIMIT_REQUESTS`. |
| `RATE_LIMIT_REQUESTS` | `300` | No | Sustained budget per client per window. |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | No | |
| `RATE_LIMIT_AUTH_REQUESTS` | `10` | No | Tighter budget for auth paths. |
| `RATE_LIMIT_AUTH_WINDOW_SECONDS` | `60` | No | |
| `RATE_LIMIT_AUTH_PATHS` | `/auth/login,/auth/register,/auth/refresh,/auth/password` | No | Not read from `.env.example`; a code-level tuple. Override only if you know you need to. |
| `RATE_LIMIT_EXEMPT_PATHS` | `/health,/health/ready` | No | Never rate limit liveness/readiness. |
| `TRUST_PROXY_HEADERS` | `false` | **Conditional — see checklist** | Only `true` when genuinely behind a trusted reverse proxy that sets `X-Forwarded-For` itself and strips any client-supplied copy. |
| `MAX_REQUEST_BODY_BYTES` | `67108864` (64 MiB) | No | Hard backstop ahead of routing; upload endpoints enforce their own smaller, type-aware caps via `MAX_UPLOAD_SIZE_MB`. |
| `SECURITY_HEADERS_ENABLED` | `true` | Yes — keep `true` | CSP, `X-Frame-Options`, `Referrer-Policy`, etc. CSP is deliberately permissive enough for Swagger UI at `/docs` to keep working. |
| `HSTS_ENABLED` | `false` | **Yes, once behind TLS** | See checklist. |
| `HSTS_MAX_AGE_SECONDS` | `31536000` (1 year) | No | |
| `LOG_REDACTION_ENABLED` | `true` | Yes — keep `true` | Mitigation for confirmed log leaks; see OPERATIONS.md. |

## 5. Pre-production security checklist

Work through this before any deployment that is reachable outside your own
machine. The first three items are not optional hardening — they are open,
reproduced, remotely-exploitable holes documented in
`docs/PHASE9-10-AUDIT.md`.

- [ ] **`SECRET_KEY` is set to a real, ≥32-character value**, and is different
      per environment. This is enforced by `Settings._validate_secret` for
      `ENVIRONMENT=staging` and `ENVIRONMENT=production` — the app will
      refuse to start otherwise. Do not rely on the enforcement alone;
      generate and store it properly (secrets manager, not a checked-in
      `.env`).

- [ ] **`META_APP_SECRET` is set if the Meta/WhatsApp webhook is reachable.**
      `app/api/v1/integrations/meta.py` only checks the `X-Hub-Signature-256`
      header **when `META_APP_SECRET` is configured** (`if settings.META_APP_SECRET: ...`).
      Left unset, the webhook accepts any POST with no signature at all. This
      is **PHASE9-10-AUDIT.md finding 2 (Critical)**, reproduced with a plain
      `curl` that injects a fabricated progress report attributed to a real
      user, which then flows into document extraction and matching as if a
      site supervisor had filed it. There is currently no code-level
      enforcement of this like there is for `SECRET_KEY` — the operator must
      set it.

- [ ] **`VAPI_SECRET` is set if the Vapi voice webhook is reachable.**
      `app/api/v1/integrations/vapi.py` has the same fail-open shape:
      `if not settings.VAPI_SECRET: return True`. This is
      **PHASE9-10-AUDIT.md finding 1 (Critical)**, reproduced with an
      unauthenticated `curl` that retrieved a real project's name and status.
      Combined with substring phone matching elsewhere in that code path
      (finding 11), a caller can plausibly be treated as a real user with
      almost no input. Same operator responsibility as above — not
      code-enforced.

- [ ] **`HSTS_ENABLED=true`, only once you are genuinely serving over TLS.**
      HSTS tells browsers to refuse plain HTTP to this host for
      `HSTS_MAX_AGE_SECONDS`; turning it on without TLS in front of the app,
      or before TLS is reliably working, can lock out browsers that cached
      the header. Set it at the load balancer / reverse proxy layer if that
      is where TLS terminates, alongside setting it here.

- [ ] **`TRUST_PROXY_HEADERS=true` only when a trusted reverse proxy sits in
      front of this service and itself sets `X-Forwarded-For`** (overwriting,
      not appending to, any client-supplied value). `RateLimitMiddleware`
      uses the left-most entry of that header as the rate-limit key when this
      is `true`. If there is no such proxy — or the proxy passes through a
      client-supplied header unmodified — a client can set an arbitrary
      `X-Forwarded-For` on each request and get a fresh rate-limit bucket
      every time, defeating the limiter entirely, including on
      `/auth/login`. When in doubt, leave this `false` and key on the
      connecting socket's address.

- [ ] `DEBUG=false`.
- [ ] `POSTGRES_PASSWORD` changed from the default (`postgres` in code,
      `change-me` in `.env.example`).
- [ ] `CORS_ORIGINS` set to the real frontend origin(s) only — never `*`,
      since `allow_credentials=True` is set.
- [ ] `LOG_REDACTION_ENABLED=true` (default) — mitigates, but does not fix,
      the plaintext-secret and full-payload log leaks in
      `PHASE9-10-AUDIT.md` findings 3 and 4. See OPERATIONS.md.
- [ ] Do not run the Compose file's `api` service (with its `--reload` flag)
      as the production entry point; build a plain image from the
      `Dockerfile` (its default `CMD` has no `--reload`) or override the
      command.
- [ ] Be aware: `docs/PHASE9-10-AUDIT.md` finding 6 documents that a broker
      outage returns HTTP 500 to Meta on webhook delivery, which Meta then
      retries, duplicating ingestion (see also finding 5, no idempotency on
      WhatsApp message ids). Not fixed by any of the above — see
      OPERATIONS.md's troubleshooting section for what to do when it happens.

## 6. Migration workflow

Alembic reads the database URL from application settings, not `alembic.ini`
(`alembic/env.py` calls `settings.sqlalchemy_database_uri` and imports
`app.models` so every table on `Base.metadata` is visible to autogenerate).

**Create a migration:**

```bash
alembic revision --autogenerate -m "add xyz column"
```

Always **review the generated file** in `alembic/versions/` before committing
— autogenerate is a diff tool, not a design tool, and needs a human check for
things it gets structurally wrong (renamed columns showing as drop+add, data
migrations it can't infer, etc).

**Apply migrations:**

```bash
alembic upgrade head
```

This is what both the Compose `api` service and a plain deploy should run
before starting `uvicorn`.

**Roll back one revision:**

```bash
alembic downgrade -1
```

**Two invariants CI enforces on every push**, and how to check them yourself
before opening a PR:

1. **Single head.** A split head means two migrations claim the same parent —
   the app still starts, but `alembic upgrade head` then fails with an
   ambiguity error, usually from an un-noticed merge.

   ```bash
   alembic heads
   # CI asserts exactly one line ends in "(head)"
   ```

2. **Zero schema drift.** If autogenerate finds anything against a freshly
   migrated database, a model changed without a matching migration.

   ```bash
   alembic upgrade head
   alembic revision --autogenerate -m ci_drift_probe
   # CI fails if the generated file contains any `op.` call; delete the
   # probe file afterwards either way.
   ```

CI (`.github/workflows/ci.yml`) runs both of these against a fresh
`postgres:16` service container on every push and pull request, before the
test suite runs at all.

There are currently 13 migration files under `backend/alembic/versions/`.

## 7. Health and readiness endpoints

| Endpoint | Purpose | What it checks |
|---|---|---|
| `GET /api/v1/health` | Liveness | Process is up. Always returns `200` with `{"status": "ok", "environment": ..., "version": "0.1.0"}`. This is what the Dockerfile's `HEALTHCHECK` calls. |
| `GET /api/v1/health/ready` | Readiness | Calls `check_database_connection()`. Returns `200` with `status: "ok", database: "up"` when the DB is reachable, or `503` with `status: "degraded", database: "down"` otherwise. |

**Important orchestration note:** a failed database check at startup does
**not** abort the application (`app/main.py`'s `lifespan`, by explicit
design — logged as `database_connection_failed_at_startup` and nothing more).
The process comes up and serves traffic even if Postgres is not yet reachable.
This means:

- Container orchestrators (Kubernetes, ECS, etc.) must gate traffic on
  **readiness** (`/health/ready`), not liveness. Point the readiness probe at
  `/api/v1/health/ready` and the liveness probe at `/api/v1/health`.
- A liveness probe pointed at `/health` alone will never catch "DB is down" —
  it will report the process as healthy indefinitely while readiness fails,
  which is exactly the intended split (don't crash-loop the API just because
  the database is slow to come up; hold traffic instead).
- Both paths are exempt from rate limiting (`RATE_LIMIT_EXEMPT_PATHS`), so an
  orchestrator polling aggressively will not trip the limiter.

## 8. Reference: what CI proves on every push

Useful to know when diagnosing "it works locally but the pipeline is red":

- Single migration head and zero schema drift (section 6).
- Full test suite with coverage, gated by a skip-guard (more than 20 skips
  fails the build outright — see OPERATIONS.md for what this catches).
- One known, deliberately deselected failing test
  (`tests/api/test_integrations_vapi.py::test_vapi_tool_call`, tracked as
  `PHASE9-10-AUDIT.md` finding 10) still runs informationally with
  `continue-on-error: true` so it stays visible on the dashboard.
- Coverage floor: `coverage report --fail-under=85`.
- Every module under `app/` imports cleanly with no database (`static-checks`
  job) — catches circular imports and syntax errors in modules no test
  happens to touch.
- `.env.example` carries no non-empty value for `SECRET_KEY`,
  `META_APP_SECRET`, `META_ACCESS_TOKEN`, `VAPI_SECRET`, or `VAPI_API_KEY`.
