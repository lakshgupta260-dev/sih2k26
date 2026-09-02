# SIH26122 Backend — Progress Intelligence Platform

FastAPI backend bridging planned L1–L6 project schedules with actual site
progress. Built as a modular monolith.

## Status

| Phase | Scope | State |
|---|---|---|
| 1 | Scaffolding, config, DB, Alembic, Docker | **Done, validated** |
| 2 | Auth, RBAC, users, projects | **Done, validated** |
| 3 | Schedule upload, Excel/CSV parsing, L1–L6, dependencies | **Done** |
| 4 | Report upload, document processing, processing jobs | **Done** |
| 5 | AI extraction, matching, confidence, human review | **Done, validated** |
| 6 | Progress engine, planned-vs-actual analytics | Not started |
| 7 | ML delay prediction, risk, explainability | Not started |
| 8 | Report generation, notifications | Not started |
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

The suite runs without a database. `test_readiness_reports_database_state`
accepts either 200 or 503 so it is meaningful in both situations.

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
