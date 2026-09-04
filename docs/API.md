# Backend API Reference

SIH 2026 problem statement 26122 — AI-Powered Planning-to-Execution Project Progress
Intelligence Platform (Oil India Limited). This document describes the FastAPI backend
that bridges planned L1–L6 project schedules with actual site progress: schedule ingestion,
progress recording, automated matching of field reports to plan activities, delay
prediction, reporting, and the WhatsApp/voice integrations that feed it from the field.

It is generated from, and should be kept in sync with, the live OpenAPI schema and the
source under `backend/app/`. Where this document and the code disagree, the code wins.

## Base URL and versioning

All routes are mounted under a single version prefix:

```
/api/v1
```

There is no unversioned surface and no `v2` yet. Interactive docs (Swagger UI) are served
at `/docs` when the deployment has not disabled them; the OpenAPI document itself is at
`/api/v1/openapi.json` (or wherever `main.py` mounts it).

## Authentication

Authentication is JWT bearer. Obtain a token pair from `POST /api/v1/auth/login`:

```bash
curl -s -X POST https://HOST/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "supervisor@oil-india.example", "password": "correct horse battery staple"}'
```

Response:

```json
{
  "access_token": "eyJhbGciOi...",
  "refresh_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": { "id": "...", "email": "...", "role": "SITE_SUPERVISOR", "...": "..." }
}
```

Send the access token on every subsequent request:

```
Authorization: Bearer <access_token>
```

`POST /api/v1/auth/token` is an OAuth2-password-form-encoded variant of the same login,
present only so the Swagger UI "Authorize" button works (send the email in the `username`
field). Application clients should use `/auth/login`.

### Token lifetimes

From `app/core/config.py`:

| Token | Lifetime | Setting |
|---|---|---|
| Access token | 30 minutes | `ACCESS_TOKEN_EXPIRE_MINUTES = 30` |
| Refresh token | 7 days | `REFRESH_TOKEN_EXPIRE_DAYS = 7` |

Signing algorithm is `HS256` (`ALGORITHM`), keyed by `SECRET_KEY`. In `production` or
`staging` `SECRET_KEY` must be set explicitly and at least 32 characters; if unset outside
those environments the app generates an ephemeral key at startup, which means tokens issued
by one process instance will not validate against another.

### Refreshing and revoking

`POST /api/v1/auth/refresh` exchanges a refresh token for a new pair. Refresh tokens are
**rotated**: the presented token is revoked as it is used, and a new one issued. Replaying
an already-revoked refresh token revokes every session belonging to that user, on the
assumption that a revoked token being replayed means it was stolen.

`POST /api/v1/auth/logout` revokes one session (pass `refresh_token`) or, if the body omits
it, every session for the caller.

`POST /api/v1/auth/change-password` revokes every other session on success.

## Roles and authorization

The platform recognizes exactly three system roles (`app/core/constants.py`,
`UserRole`):

| Role | Typical capability |
|---|---|
| `ADMIN` | Full system access. Manage users (create, change role, activate/deactivate), and administer any project regardless of membership. |
| `PROJECT_MANAGER` | Create projects; administer projects they manage (update, delete, manage members); run matching; train models; generate reports; write progress on projects they are a member of. |
| `SITE_SUPERVISOR` | Read/write within projects they are a member of — record progress, upload documents/schedules, view schedules, activities, matches, predictions; cannot administer project settings or membership. |

Authorization is enforced through two layers of FastAPI dependency, both declared in
`app/api/deps.py`:

- **System-role guards** — `require_roles(*allowed)`, with convenience aliases
  `RequireAdmin` (ADMIN only) and `RequireManager` (ADMIN or PROJECT_MANAGER). Used for
  routes gated purely on the caller's global role (e.g. user administration, project
  creation).
- **Project-scoped guards** — resolved per request from the `project_id` path parameter:
  - `AccessibleProject` (`get_project_for_user`) — loads a project the caller can *see*
    (any member, or an admin). Used on every read endpoint under a project.
  - `ManagedProject` (`require_project_admin`) — loads a project the caller may
    *administer or write to* (the project's manager, or an admin). Used on write
    endpoints: recording progress, uploading schedules, running matching, training
    models, updating project/member settings.

A route with no guard at all is unauthenticated by construction; this makes the access
rules auditable purely by reading router signatures.

### The 404-not-403 convention

**A caller with no membership of a project receives `404 Not Found`, not `403 Forbidden`,
for anything under `/projects/{project_id}/...`.** This is deliberate: returning 403 would
confirm to an unauthorized caller that a project with that ID exists at all. Both
`AccessibleProject` and `ManagedProject` implement this — a project outside the caller's
visibility is treated as if it does not exist, and a project the caller can *see* but not
*administer* returns 403 from `ManagedProject` (since existence is already established at
that point). This convention is called out explicitly in the docstrings of
`app/api/v1/progress.py` and enforced by `ProjectService.get_for_user` /
`require_project_admin`.

## Error envelope

Every error response — ours, FastAPI's request-validation errors, unhandled exceptions,
and even plain Starlette HTTP exceptions — is rendered through the same JSON shape
(`app/core/exceptions.py`):

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "The requested resource was not found.",
    "details": {}
  }
}
```

| Exception | HTTP status | `code` |
|---|---|---|
| `NotFoundError` | 404 | `NOT_FOUND` |
| `ConflictError` | 409 | `CONFLICT` |
| `ValidationError` | 422 | `VALIDATION_ERROR` |
| `AuthenticationError` | 401 | `UNAUTHENTICATED` |
| `PermissionDeniedError` | 403 | `PERMISSION_DENIED` |
| `UnprocessableFileError` | 400 | `UNPROCESSABLE_FILE` |
| `ExternalServiceError` | 502 | `EXTERNAL_SERVICE_ERROR` |
| Pydantic/FastAPI request validation failure | 422 | `VALIDATION_ERROR` (details include the raw pydantic error list under `details.errors`) |
| Unmapped Starlette `HTTPException` | its own status | `HTTP_<status>` |
| `SQLAlchemyError` | 500 | `DATABASE_ERROR` |
| Anything else unhandled | 500 | `INTERNAL_ERROR` |

`code` values from specific application errors (e.g. `INVALID_COLUMN_MAPPING`,
`NOT_AUTHENTICATED`) may override the class default via the `code=` keyword; treat `code`
as the stable machine-readable field and `message` as human-readable prose that may change.

## Pagination

Collection endpoints accept `skip` and `limit` query parameters
(`app/schemas/common.py::PaginationParams`, wired in via the `Pagination` dependency):

- `skip`: integer ≥ 0, default `0`.
- `limit`: integer, 1–200, default `50`.

Paginated responses use the `Page[T]` envelope:

```json
{
  "items": [ /* T ... */ ],
  "total": 137,
  "skip": 0,
  "limit": 50
}
```

`total` is the count across the whole filtered collection, not just this page; a client
can tell whether more pages remain from `skip + len(items) < total`.

Not every list endpoint returns `Page[T]` — some (e.g. activity trees, progress history)
return plain arrays because they are inherently bounded to one schedule or one activity.
Check the per-endpoint tables below.

## Rate limiting

A fixed-window limiter (`app/core/rate_limit.py`) applies per client (by IP, or by the
left-most `X-Forwarded-For` entry when `TRUST_PROXY_HEADERS` is enabled) and per path
class:

| Path class | Budget | Window |
|---|---|---|
| Default (everything else) | 300 requests | 60 seconds |
| Auth paths — any path containing `/auth/login`, `/auth/register`, `/auth/refresh`, `/auth/password` | 10 requests | 60 seconds |
| `/health`, `/health/ready` | exempt — never limited | — |

The Meta and Vapi webhook endpoints are **not** exempt and fall under the default
(300/60s) budget, not the tighter auth budget — see the Integrations section for why this
only partially mitigates their auth findings.

Exceeding the budget returns:

```
HTTP/1.1 429 Too Many Requests
Retry-After: 37
X-RateLimit-Limit: 300
X-RateLimit-Remaining: 0
```

```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Too many requests. Retry in 37 second(s).",
    "details": {"retry_after_seconds": 37}
  }
}
```

Every response, limited or not, carries `X-RateLimit-Limit` and `X-RateLimit-Remaining`.
State is per-process and in-memory, so with N worker processes the effective budget is
`N x` the advertised figure.

## Security response headers

Every response (unless disabled via `SECURITY_HEADERS_ENABLED=false`) carries
(`app/core/security_headers.py`):

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
Content-Security-Policy: default-src 'self'; script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; img-src 'self' data: https://fastapi.tiangolo.com; font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
Permissions-Policy: geolocation=(), microphone=(), camera=()
Cache-Control: no-store
```

The CSP is deliberately loose enough for Swagger UI (`/docs`) to keep working — it is not
a substitute for a stricter CSP on whatever browser front end consumes this API.
`Strict-Transport-Security` is added only when `HSTS_ENABLED=true` (off by default; only
meaningful behind TLS). A header a route sets explicitly (e.g. a file download's own
`Cache-Control`/`Content-Disposition`) is never overwritten — these are applied with
`setdefault`.

## Request body size limit

A hard ceiling of **64 MiB** (`MAX_REQUEST_BODY_BYTES = 64 * 1024 * 1024`) applies to every
request body, ahead of any per-endpoint upload validation. A declared `Content-Length`
above the limit is rejected before the body is read; a chunked body with no declared length
is metered as it streams and cut off the moment the limit is passed. Either way:

```
HTTP/1.1 413 Payload Too Large
```

```json
{
  "error": {
    "code": "PAYLOAD_TOO_LARGE",
    "message": "Request body exceeds the 67108864 byte limit.",
    "details": {"limit_bytes": 67108864}
  }
}
```

This is a backstop; upload endpoints additionally enforce their own smaller, type-aware
caps (e.g. `MAX_UPLOAD_SIZE_MB = 50` for document uploads).

## Domain enumerations

Selected enums from `app/core/constants.py`, used throughout request/response bodies:

- **`ActivityStatus`**: `NOT_STARTED`, `IN_PROGRESS`, `COMPLETED`, `SUSPENDED`
- **`WBSLevel`**: `L1` (coarsest) … `L6` (finest)
- **`MatchStatus`**: `AUTO_MATCHED`, `NEEDS_REVIEW`, `UNMATCHED`, `MANUALLY_CONFIRMED`, `MANUALLY_REJECTED`
- **`MatchMethod`**: `EXACT_ID`, `EXACT_CODE`, `KEYWORD`, `FUZZY`, `SEMANTIC`, `HYBRID`, `MANUAL`
- **`Discipline`**: `CIVIL`, `PIPING`, `ELECTRICAL`, `MECHANICAL`, `INSTRUMENTATION`, `STRUCTURAL`, `WELDING_NDT`, `SURVEY`, `COATING`, `TESTING_PRECOMMISSIONING`, `OTHER`
- **`RiskLevel`**: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`
- **`PredictionMethod`**: `RULE_BASED_RATE` (deterministic, always available), `RANDOM_FOREST` (fitted, only after passing held-out evaluation), `NOT_FORECASTABLE`
- **`DocumentType`**: `SCHEDULE`, `DAILY_PROGRESS_REPORT`, `SITE_DIARY`, `DISCIPLINE_SHEET`, `OTHER`
- **`GeneratedReportFormat`**: `PDF`, `XLSX`
- **`JobStatus`**: `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`
- **`ProjectStatus`**: `PLANNING`, `ACTIVE`, `ON_HOLD`, `COMPLETED`, `CANCELLED`
- **`NotificationChannel`**: `IN_APP`, `EMAIL`, `WHATSAPP`, `VAPI`

## Endpoints

All 68 routes below are drawn from the live OpenAPI schema, grouped exactly as the API
groups them by tag. "Who may call it" is the effective rule after both guard layers.

### auth

| Method | Path | Description | Who may call it |
|---|---|---|---|
| POST | `/api/v1/auth/register` | Register a new account | Anyone (unauthenticated) |
| POST | `/api/v1/auth/login` | Log in | Anyone (unauthenticated) |
| POST | `/api/v1/auth/token` | Log in (OAuth2 form) | Anyone (unauthenticated) |
| POST | `/api/v1/auth/refresh` | Exchange a refresh token for a new token pair | Anyone holding a valid, unrevoked refresh token |
| POST | `/api/v1/auth/logout` | Revoke one session, or all of them | Authenticated caller |
| GET | `/api/v1/auth/me` | The authenticated user | Authenticated caller |
| POST | `/api/v1/auth/change-password` | Change your password | Authenticated caller |

Self-registration always creates a `SITE_SUPERVISOR`; only an admin can grant a higher
role (via `PATCH /users/{user_id}/role`). `/auth/token` exists solely so the Swagger
"Authorize" dialog works — real clients should use `/auth/login`, which also returns the
user record.

### users

| Method | Path | Description | Who may call it |
|---|---|---|---|
| GET | `/api/v1/users` | List users | Admin only |
| POST | `/api/v1/users` | Create a user with an explicit role | Admin only |
| GET | `/api/v1/users/{user_id}` | Fetch a user | Self, or any user if admin |
| PATCH | `/api/v1/users/{user_id}` | Update a profile | Self, or any user if admin |
| PATCH | `/api/v1/users/{user_id}/role` | Change a system role | Admin only |
| PATCH | `/api/v1/users/{user_id}/status` | Activate or deactivate an account | Admin only |

### projects

| Method | Path | Description | Who may call it |
|---|---|---|---|
| GET | `/api/v1/projects` | List projects visible to you | Authenticated; scoped to memberships (admins see all) |
| POST | `/api/v1/projects` | Create a project | `PROJECT_MANAGER` or `ADMIN` |
| GET | `/api/v1/projects/{project_id}` | Fetch a project | Any project member, or admin (404 otherwise) |
| PATCH | `/api/v1/projects/{project_id}` | Update a project | Project manager or admin (`ManagedProject`) |
| DELETE | `/api/v1/projects/{project_id}` | Soft-delete a project | Project manager or admin |
| GET | `/api/v1/projects/{project_id}/members` | List project members | Any project member, or admin |
| POST | `/api/v1/projects/{project_id}/members` | Add a member | Project manager or admin |
| PATCH | `/api/v1/projects/{project_id}/members/{user_id}` | Change a member's project role | Project manager or admin |
| DELETE | `/api/v1/projects/{project_id}/members/{user_id}` | Remove a member | Project manager or admin |

Project creation requires a short, unique `code` (pattern `^[A-Za-z0-9][A-Za-z0-9._-]*$`)
in addition to `name`; `planned_finish` cannot precede `planned_start`.

### schedules

| Method | Path | Description | Who may call it |
|---|---|---|---|
| GET | `/api/v1/projects/{project_id}/schedules` | List project schedules | Any project member, or admin |
| POST | `/api/v1/projects/{project_id}/schedules` | Upload a baseline schedule | Project manager or admin |
| GET | `/api/v1/projects/{project_id}/schedules/{schedule_id}` | Get schedule details | Any project member, or admin |

Upload is `multipart/form-data`: a file (`.csv`, `.xls`, `.xlsx`, `.xlsm` — narrower than
the global upload allowlist, since anything else cannot be parsed as a schedule), a `name`
field, and a `mapping` field containing a JSON-encoded column mapping (our field name →
your column header). The mapping is validated *before* the schedule row is created, so a
malformed mapping fails with `422`/`INVALID_COLUMN_MAPPING` rather than leaving a row stuck
in `PENDING` forever. `ScheduleRead.parse_summary` reports exactly what the import did:
rows read, activities created, and every row/date/dependency it had to drop.

### activities

| Method | Path | Description | Who may call it |
|---|---|---|---|
| GET | `/api/v1/schedules/{schedule_id}/activities` | List schedule activities | Any member of the owning project |
| GET | `/api/v1/schedules/{schedule_id}/activities/tree` | Activities as a hierarchical tree | Any member of the owning project |
| GET | `/api/v1/schedules/{schedule_id}/activities/{activity_id}` | Activity details including dependencies | Any member of the owning project |

Note this router is mounted at `/schedules/...`, not `/projects/{project_id}/schedules/...`
— project membership is still resolved and enforced internally from the schedule's owning
project, but the project id does not appear in the path.

### progress

| Method | Path | Description | Who may call it |
|---|---|---|---|
| POST | `/api/v1/projects/{project_id}/schedules/{schedule_id}/activities/{activity_id}/progress` | Record or correct progress for an activity on a date | Project manager or admin (`ManagedProject`) |
| GET | `/api/v1/projects/{project_id}/schedules/{schedule_id}/activities/{activity_id}/progress` | Progress history for an activity, newest first | Any project member, or admin |
| GET | `/api/v1/projects/{project_id}/schedules/{schedule_id}/progress/rollup` | Quantity-weighted WBS progress rollup | Any project member, or admin |
| POST | `/api/v1/projects/{project_id}/schedules/{schedule_id}/progress/apply-matches` | Book confirmed matches as actual progress | Project manager or admin |

Progress is one record per activity per reporting date: posting the same date again
corrects that day's figure rather than appending a contradictory second one, and the
superseded value is kept in the audit trail. The rollup weights completion by budgeted
quantity per WBS node rather than treating every activity as equal weight, and is ordered
by WBS path numerically.

### matching

| Method | Path | Description | Who may call it |
|---|---|---|---|
| POST | `/api/v1/projects/{project_id}/matching/run` | Extract activity events from progress reports and link them | Project manager or admin |
| GET | `/api/v1/projects/{project_id}/matching/extracted` | List extracted field items, including non-events | Any project member, or admin |
| GET | `/api/v1/projects/{project_id}/matching/matches` | List matches, optionally filtered by status | Any project member, or admin |
| GET | `/api/v1/projects/{project_id}/matching/matches/{match_id}` | Fetch one match with its signals, candidates and source text | Any project member, or admin |
| GET | `/api/v1/projects/{project_id}/matching/matches/{match_id}/history` | Complete review history for one match | Any project member, or admin |
| POST | `/api/v1/projects/{project_id}/matching/matches/{match_id}/review` | Confirm, reject or reassign a proposed match | Project manager or admin |
| GET | `/api/v1/projects/{project_id}/matching/stats` | Queue counters and measured matcher precision | Any project member, or admin |

`POST /matching/run` runs synchronously for a single report (`progress_report_id`); omit it
to process every unprocessed report in the project, and optionally pass `schedule_id` to
match against a schedule other than the project's latest. Every response states which
extractor and embedding provider actually ran and whether an LLM was available, so a result
is never ambiguous about how it was produced. `POST /matches/{match_id}/review` takes a
`decision` of `confirm`, `reject`, or `reassign` (the latter requires `activity_id`).
Thresholds that decide `AUTO_MATCHED` vs `NEEDS_REVIEW` vs `UNMATCHED` are configurable
(`MATCH_AUTO_THRESHOLD` default 0.82, `MATCH_REVIEW_THRESHOLD` default 0.55).

### prediction

| Method | Path | Description | Who may call it |
|---|---|---|---|
| POST | `/api/v1/projects/{project_id}/ml/train` | Fit a delay model on completed activities, or explain the refusal | Project manager or admin |
| GET | `/api/v1/projects/{project_id}/ml/models` | Model registry, newest first | Any project member, or admin |
| GET | `/api/v1/projects/{project_id}/ml/features` | What each model feature means | Any project member, or admin |
| POST | `/api/v1/projects/{project_id}/schedules/{schedule_id}/ml/predict` | Forecast a late finish for every activity in the schedule | Project manager or admin |
| GET | `/api/v1/projects/{project_id}/schedules/{schedule_id}/ml/predictions` | Stored forecasts, highest probability first | Any project member, or admin |
| GET | `/api/v1/projects/{project_id}/schedules/{schedule_id}/ml/predictions/{activity_id}` | One forecast with its drivers, caveats and inputs | Any project member, or admin |
| GET | `/api/v1/projects/{project_id}/schedules/{schedule_id}/ml/risk-summary` | Risk bands and the worst activities on the schedule | Any project member, or admin |

Every prediction response states which tier produced it (`PredictionMethod`) — there is no
code path that returns a probability without naming its method. `train` trains on
activities with both a planned and an actual finish, built as-at the day *before* the
activity finished (so the outcome can never leak into the features); `trained: false` is a
normal, expected outcome early in a project, not an error — `reason` explains which floor
was not met (`ML_MIN_TRAINING_SAMPLES=40`, `ML_MIN_MINORITY_SAMPLES=8`,
`ML_MIN_HELDOUT_ROC_AUC=0.60`, and the model must beat the rule-based baseline by
`ML_BASELINE_MARGIN=0.02` in ROC AUC to be promoted). `predict` accepts an optional `as_of`
date to reproduce a past run, and `force_rule_based` to bypass a fitted model. Risk bands
use `ML_RISK_MEDIUM_THRESHOLD=0.35`, `ML_RISK_HIGH_THRESHOLD=0.60`,
`ML_RISK_CRITICAL_THRESHOLD=0.80` on predicted probability.

### analytics

| Method | Path | Description | Who may call it |
|---|---|---|---|
| GET | `/api/v1/projects/{project_id}/schedules/{schedule_id}/analytics/s-curve` | Cumulative planned vs actual completion over time | Any project member, or admin |
| GET | `/api/v1/projects/{project_id}/schedules/{schedule_id}/analytics/summary` | Headline schedule health figures | Any project member, or admin |

### documents

| Method | Path | Description | Who may call it |
|---|---|---|---|
| GET | `/api/v1/projects/{project_id}/documents` | List documents | Any project member, or admin |
| POST | `/api/v1/projects/{project_id}/documents` | Upload document | Any project member, or admin (write access enforced at the service layer) |
| GET | `/api/v1/projects/{project_id}/documents/{file_id}` | Get document | Any project member, or admin |

Upload is subject to `ALLOWED_UPLOAD_EXTENSIONS` (`.pdf .xlsx .xls .csv .txt .png .jpg
.jpeg .xer .xml`) and `MAX_UPLOAD_SIZE_MB` (default 50 MB), independent of the global 64
MiB body cap.

### progress reports

| Method | Path | Description | Who may call it |
|---|---|---|---|
| GET | `/api/v1/projects/{project_id}/reports` | List reports | Any project member, or admin |
| GET | `/api/v1/projects/{project_id}/reports/{report_id}` | Get report | Any project member, or admin |

These are the raw ingested site progress reports (e.g. parsed daily progress reports,
WhatsApp submissions) — distinct from **generated reports** below, which are PDF/XLSX
artifacts the platform produces.

### generated reports

| Method | Path | Description | Who may call it |
|---|---|---|---|
| POST | `/api/v1/projects/{project_id}/generated-reports` | Request report | Authenticated project member (route has no explicit project guard beyond `CurrentUser`; consult `ReportService` for the exact enforcement) |
| GET | `/api/v1/projects/{project_id}/generated-reports` | List generated reports | Authenticated caller, scoped by `ReportService` |
| GET | `/api/v1/projects/{project_id}/generated-reports/{report_id}` | Get generated report | Authenticated caller, scoped by `ReportService` |
| GET | `/api/v1/projects/{project_id}/generated-reports/{report_id}/download` | Download generated report | Authenticated caller, scoped by `ReportService` |

Requests take `report_type`, `output_format` (`PDF` or `XLSX`), an optional `as_of` date,
and a free-form `parameters` object. Generation may be asynchronous — poll `GET
.../generated-reports/{report_id}` for `status` (`PENDING`, `GENERATING`, `COMPLETED`,
`FAILED`) before calling `/download`.

### notifications

| Method | Path | Description | Who may call it |
|---|---|---|---|
| GET | `/api/v1/notifications` | List notifications | Authenticated caller (own notifications) |
| GET | `/api/v1/notifications/unread-count` | Get unread count | Authenticated caller |
| PATCH | `/api/v1/notifications/{notification_id}/read` | Mark notification read | Authenticated caller, own notification |
| POST | `/api/v1/notifications/read-all` | Mark all notifications read | Authenticated caller |
| POST | `/api/v1/projects/{project_id}/notifications` | Send project notification | Project manager or admin |

### processing jobs

| Method | Path | Description | Who may call it |
|---|---|---|---|
| GET | `/api/v1/jobs/{job_id}` | Get processing job | Caller with access to the job's owning project |

Used to poll the status (`JobStatus`) of an asynchronous ingestion job started by a
document, schedule, or WhatsApp upload.

### health

| Method | Path | Description | Who may call it |
|---|---|---|---|
| GET | `/api/v1/health` | Liveness probe | Anyone (unauthenticated); exempt from rate limiting |
| GET | `/api/v1/health/ready` | Readiness probe (verifies database connectivity) | Anyone (unauthenticated); exempt from rate limiting |

### integrations

| Method | Path | Description | Who may call it |
|---|---|---|---|
| GET | `/api/v1/integrations/meta/webhook` | Verify webhook | Meta's webhook verification handshake (query-string token, no bearer auth) |
| POST | `/api/v1/integrations/meta/webhook` | Receive webhook | Meta/WhatsApp Cloud API (HMAC signature, no bearer auth) |
| POST | `/api/v1/integrations/vapi/webhook` | Vapi webhook | Vapi voice platform (shared-secret header, no bearer auth) |

These three routes are the only ones in the API that do **not** use JWT bearer
authentication — see the dedicated section below. They are not exempt from rate limiting
(they fall under the default 300/60s budget, not the tighter auth budget).

## Integrations: authentication model and known issues

The Meta and Vapi webhooks authenticate callers by shared secret / HMAC signature, not by
bearer token, because the caller is an external platform, not a logged-in user of this
application.

- **Meta webhook** (`POST /api/v1/integrations/meta/webhook`) verifies the
  `X-Hub-Signature-256` header as an HMAC-SHA256 of the raw body, keyed by
  `META_APP_SECRET`, using `hmac.compare_digest`. The `GET` verification handshake checks
  `hub.verify_token` against `META_VERIFY_TOKEN`.
- **Vapi webhook** (`POST /api/v1/integrations/vapi/webhook`) checks an `X-Vapi-Secret`
  header against `VAPI_SECRET` with a plain `==` comparison.

**Critical: both checks fail open.** `META_APP_SECRET` and `VAPI_SECRET` both default to
`None` in `app/core/config.py`. When either is unset:

```python
# app/api/v1/integrations/vapi.py
def verify_vapi_secret(x_vapi_secret: str) -> bool:
    if not settings.VAPI_SECRET:
        return True  # If not configured, allow for testing/dev
    return x_vapi_secret == settings.VAPI_SECRET
```

```python
# app/api/v1/integrations/meta.py
if settings.META_APP_SECRET:
    if not verify_meta_signature(payload, x_hub_signature_256):
        raise HTTPException(status_code=403, detail="Invalid signature")
```

With the secret unset, both endpoints accept **any** unauthenticated caller — no header,
no credentials. This is documented as Critical findings 1 and 2 in
`docs/PHASE9-10-AUDIT.md`, both reproduced live: the Vapi webhook returned real project
name and status to an anonymous curl request, and the Meta webhook committed a forged
site-progress report (as an `uploaded_files` + `processing_jobs` row) attributed to a real
user and project, purely from an unsigned request body. **Deploying this API with either
secret unset means both webhooks are open to the internet.** The audit's stated fix is to
require both secrets outside local development (the same way `SECRET_KEY` is already
required in production/staging) and to fail closed rather than open when they are missing
— this has not been implemented as of this document.

### Vapi voice assistant tools

The Vapi webhook dispatches `tool-calls` messages to functions in `app/api/v1/assistant.py`.
Per `docs/PHASE9-10-AUDIT.md` findings 7 and 8:

- **`get_delayed_activities`** and **`get_activity_details`** currently return an error on
  every call. Both filter on `Activity.project_id`, a column that does not exist —
  `Activity` belongs to a schedule, not directly to a project, and status/percent-complete
  live on `ActualProgress`, not `Activity`. The live reproduction returns
  `{"error": "type object 'Activity' has no attribute 'project_id'"}` for both tools.
- **`get_risk_summary`** does not consult the real delay-prediction data
  (`delay_predictions` / `DelayPrediction`) at all. It returns a hardcoded string —
  the same sentence for every project and every caller — describing fabricated concrete-
  pouring and steel-procurement risks that have no relationship to the project asked
  about.

Callers of the voice assistant should treat these three tools as non-functional (the first
two) or fabricated (the third) until fixed; the other two of the five tools are not
reported as broken by the audit.

## curl examples

Set a base URL and, after login, export the access token:

```bash
export BASE=https://HOST/api/v1
```

### Log in

```bash
curl -s -X POST $BASE/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "pm@oil-india.example", "password": "hunter2-but-better"}' \
  | tee /tmp/login.json

export TOKEN=$(python3 -c "import json;print(json.load(open('/tmp/login.json'))['access_token'])")
```

### Upload a baseline schedule

```bash
curl -s -X POST "$BASE/projects/$PROJECT_ID/schedules" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@baseline_L1_L6.xlsx" \
  -F "name=Baseline Schedule Rev 0" \
  -F 'mapping={"activity_id":"Activity ID","activity_name":"Activity Name","wbs_path":"WBS","planned_start":"Start","planned_finish":"Finish"}'
```

### List activities in a schedule

```bash
curl -s "$BASE/schedules/$SCHEDULE_ID/activities?skip=0&limit=50" \
  -H "Authorization: Bearer $TOKEN"
```

### Record progress for an activity

```bash
curl -s -X POST \
  "$BASE/projects/$PROJECT_ID/schedules/$SCHEDULE_ID/activities/$ACTIVITY_ID/progress" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "reporting_date": "2026-09-03",
    "percent_complete": 62.5,
    "status": "IN_PROGRESS",
    "notes": "Concrete pour completed for segment B; formwork in progress."
  }'
```

### Run matching over a progress report

```bash
curl -s -X POST "$BASE/projects/$PROJECT_ID/matching/run" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"progress_report_id": "'"$REPORT_ID"'"}'
```

### Train the delay model

```bash
curl -s -X POST "$BASE/projects/$PROJECT_ID/ml/train" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Predict delays for a schedule

```bash
curl -s -X POST "$BASE/projects/$PROJECT_ID/schedules/$SCHEDULE_ID/ml/predict" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Generate a report

```bash
curl -s -X POST "$BASE/projects/$PROJECT_ID/generated-reports" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "report_type": "monthly_progress",
    "output_format": "PDF",
    "as_of": "2026-08-31"
  }'

# then poll and download:
curl -s "$BASE/projects/$PROJECT_ID/generated-reports/$REPORT_ID" \
  -H "Authorization: Bearer $TOKEN"

curl -s -OJ "$BASE/projects/$PROJECT_ID/generated-reports/$REPORT_ID/download" \
  -H "Authorization: Bearer $TOKEN"
```

## What could not be fully verified from the code alone

See the closing note in the final response for a summary of gaps (exact response schemas
for a few nested detail endpoints, and the precise service-layer authorization on the
generated-reports router, were not traced line-by-line and are flagged as such above
rather than asserted).
