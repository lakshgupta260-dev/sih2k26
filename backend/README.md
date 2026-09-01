# SIH26122 Backend — Progress Intelligence Platform

FastAPI backend bridging planned L1–L6 project schedules with actual site
progress. Built as a modular monolith.

## Status

| Phase | Scope | State |
|---|---|---|
| 1 | Scaffolding, config, DB, Alembic, Docker | **Done, validated** |
| 2 | Auth, RBAC, users, projects | Not started |
| 3 | Schedule upload, Excel/CSV parsing, L1–L6, dependencies | Not started |
| 4 | Report upload, document processing, processing jobs | Not started |
| 5 | AI extraction, matching, confidence, human review | Not started |
| 6 | Progress engine, planned-vs-actual analytics | Not started |
| 7 | ML delay prediction, risk, explainability | Not started |
| 8 | Report generation, notifications | Not started |
| 9 | Meta / WhatsApp | Not started |
| 10 | Vapi, AI project assistant | Not started |
| 11 | Testing, hardening, performance, docs | Not started |

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

## Endpoints (Phase 1)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/health` | Liveness. Always 200 while the process is up. |
| GET | `/api/v1/health/ready` | Readiness. 200 when the DB is reachable, 503 otherwise. |

Every response carries `X-Request-ID`; supply your own to trace a call through
the logs.
