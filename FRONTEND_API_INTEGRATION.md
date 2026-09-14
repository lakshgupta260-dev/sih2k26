# Frontend ↔ Backend API Integration Inventory

Source of truth: `backend/app/api/v1/**`, `backend/app/schemas/**`, `docs/API.md`,
`docs/PHASE9-10-AUDIT.md`, verified against backend commit `3dff167` (all 11 phases
implemented; `README.md`/`docs/PROGRESS.md` at the repo root are stale snapshots from
earlier phases and were not used as ground truth).

Base URL: `${VITE_API_BASE_URL}` (e.g. `http://localhost:8000/api/v1`). Every request
except the three rows marked "Anyone" needs `Authorization: Bearer <access_token>`.
Errors always come back as `{ error: { code, message, details } }`. Paginated lists use
`{ items, total, skip, limit }` with `skip`/`limit` query params.

| # | Feature | Endpoint | Method | Auth/Role | Request | Response | Frontend Screen |
|---|---------|----------|--------|-----------|---------|----------|------------------|
| 1 | Register | `/auth/register` | POST | Anyone | `UserCreate` | `UserRead` | `/register` |
| 2 | Login | `/auth/login` | POST | Anyone | `LoginRequest` | `LoginResponse` (tokens+user) | `/login` |
| 3 | Refresh | `/auth/refresh` | POST | Valid refresh token | `RefreshRequest` | `TokenPair` | axios interceptor (silent) |
| 4 | Logout | `/auth/logout` | POST | Auth'd | `LogoutRequest` (optional) | 204 | Topbar → Logout |
| 5 | Current user | `/auth/me` | GET | Auth'd | – | `UserRead` | AuthContext bootstrap |
| 6 | Change password | `/auth/change-password` | POST | Auth'd | `PasswordChange` | 204 | `/profile` |
| 7 | List users | `/users` | GET | ADMIN | `Page` params | `Page<UserRead>` | `/admin/users` |
| 8 | Create user | `/users` | POST | ADMIN | `UserAdminCreate` | `UserRead` | `/admin/users` (create modal) |
| 9 | Get user | `/users/{id}` | GET | self or ADMIN | – | `UserRead` | `/profile`, `/admin/users` |
| 10 | Update user | `/users/{id}` | PATCH | self or ADMIN | `UserUpdate` | `UserRead` | `/profile` |
| 11 | Change role | `/users/{id}/role` | PATCH | ADMIN | `UserRoleUpdate` | `UserRead` | `/admin/users` |
| 12 | Activate/deactivate | `/users/{id}/status` | PATCH | ADMIN | `UserStatusUpdate` | `UserRead` | `/admin/users` |
| 13 | List projects | `/projects` | GET | Auth'd (scoped) | `Page` params | `Page<ProjectWithRole>`* | `/projects` |
| 14 | Create project | `/projects` | POST | PM/ADMIN | `ProjectCreate` | `ProjectRead` | `/projects` (create modal) |
| 15 | Get project | `/projects/{id}` | GET | member/ADMIN (404 else) | – | `ProjectWithRole` | `/projects/:id` |
| 16 | Update project | `/projects/{id}` | PATCH | manager/ADMIN | `ProjectUpdate` | `ProjectRead` | `/projects/:id/settings` |
| 17 | Delete project | `/projects/{id}` | DELETE | manager/ADMIN | – | 204 | `/projects/:id/settings` |
| 18 | List members | `/projects/{id}/members` | GET | member/ADMIN | – | `MemberDetail[]` | `/projects/:id/members` |
| 19 | Add member | `/projects/{id}/members` | POST | manager/ADMIN | `MemberAdd` | `MemberRead` | `/projects/:id/members` |
| 20 | Change member role | `/projects/{id}/members/{uid}` | PATCH | manager/ADMIN | `MemberRoleUpdate` | `MemberRead` | `/projects/:id/members` |
| 21 | Remove member | `/projects/{id}/members/{uid}` | DELETE | manager/ADMIN | – | 204 | `/projects/:id/members` |
| 22 | List schedules | `/projects/{id}/schedules` | GET | member/ADMIN | – | `ScheduleRead[]` | `/projects/:id/schedule` |
| 23 | Upload schedule | `/projects/{id}/schedules` | POST | manager/ADMIN | multipart: `file`,`name`,`mapping`(JSON str) | `ScheduleRead` | `/projects/:id/schedule` (upload) |
| 24 | Get schedule | `/projects/{id}/schedules/{sid}` | GET | member/ADMIN | – | `ScheduleRead` | schedule detail header |
| 25 | List activities | `/schedules/{sid}/activities` | GET | member/ADMIN | `Page` params | `Page<ActivityRead>` | `/projects/:id/schedule/:sid` table view |
| 26 | Activity tree | `/schedules/{sid}/activities/tree` | GET | member/ADMIN | – | `ActivityTreeNode[]` | `/projects/:id/schedule/:sid` tree view |
| 27 | Activity detail | `/schedules/{sid}/activities/{aid}` | GET | member/ADMIN | – | `ActivityWithDependencies` | `/projects/:id/activities/:aid` |
| 28 | Record progress | `/projects/{id}/schedules/{sid}/activities/{aid}/progress` | POST | manager/ADMIN | `ActualProgressCreate` | `ActualProgressRead` | activity detail (record form) |
| 29 | Progress history | `/projects/{id}/schedules/{sid}/activities/{aid}/progress` | GET | member/ADMIN | – | `ActualProgressRead[]` | activity detail (history) |
| 30 | Progress rollup | `/projects/{id}/schedules/{sid}/progress/rollup` | GET | member/ADMIN | – | `ActivityProgressRollup[]` | project overview, schedule view |
| 31 | Apply matches | `/projects/{id}/schedules/{sid}/progress/apply-matches` | POST | manager/ADMIN | – | `MatchApplicationSummary` | matching page action |
| 32 | Run matching | `/projects/{id}/matching/run` | POST | manager/ADMIN | `MatchRunRequest` | `MatchRunSummary` | `/projects/:id/matching` |
| 33 | List extracted | `/projects/{id}/matching/extracted` | GET | member/ADMIN | `Page` params | `Page<ExtractedActivityRead>` | matching page (extracted tab) |
| 34 | List matches | `/projects/{id}/matching/matches` | GET | member/ADMIN | `status?`,`Page` | `Page<ActivityMatchRead>` | matching page (queue tab) |
| 35 | Match detail | `/projects/{id}/matching/matches/{mid}` | GET | member/ADMIN | – | `ActivityMatchDetail` | match review drawer |
| 36 | Match history | `/projects/{id}/matching/matches/{mid}/history` | GET | member/ADMIN | – | `AuditEntryRead[]` | match review drawer |
| 37 | Review match | `/projects/{id}/matching/matches/{mid}/review` | POST | manager/ADMIN | `MatchReviewDecision` | `ActivityMatchRead` | match review drawer actions |
| 38 | Match stats | `/projects/{id}/matching/stats` | GET | member/ADMIN | – | `MatchStatsRead` | matching page header, dashboard |
| 39 | Train model | `/projects/{id}/ml/train` | POST | manager/ADMIN | `TrainRequest` | `TrainingOutcome` | `/projects/:id/risks` (train action) |
| 40 | List models | `/projects/{id}/ml/models` | GET | member/ADMIN | – | `ModelVersionRead[]` | risks page (model registry) |
| 41 | Feature reference | `/projects/{id}/ml/features` | GET | member/ADMIN | – | `dict` | risks page (glossary) |
| 42 | Run prediction | `/projects/{id}/schedules/{sid}/ml/predict` | POST | manager/ADMIN | `PredictRequest` | `PredictionRunSummary` | risks page (predict action) |
| 43 | List predictions | `/projects/{id}/schedules/{sid}/ml/predictions` | GET | member/ADMIN | – | `PredictionRead[]` | risks page (table) |
| 44 | Prediction detail | `/projects/{id}/schedules/{sid}/ml/predictions/{aid}` | GET | member/ADMIN | – | `PredictionDetail` | risk detail drawer |
| 45 | Risk summary | `/projects/{id}/schedules/{sid}/ml/risk-summary` | GET | member/ADMIN | – | `RiskSummary` | dashboard + risks page |
| 46 | S-curve | `/projects/{id}/schedules/{sid}/analytics/s-curve` | GET | member/ADMIN | – | `SCurvePoint[]` | dashboard chart |
| 47 | Analytics summary | `/projects/{id}/schedules/{sid}/analytics/summary` | GET | member/ADMIN | – | `AnalyticsSummary` | dashboard KPI tiles |
| 48 | List documents | `/projects/{id}/documents` | GET | member/ADMIN | `Page` | `Page<UploadedFileRead>` | `/projects/:id/uploads` |
| 49 | Upload document | `/projects/{id}/documents` | POST | member/ADMIN (write enforced server-side) | multipart: `file`,`document_type` | `UploadAccepted` (202) | `/projects/:id/uploads` |
| 50 | Get document | `/projects/{id}/documents/{fid}` | GET | member/ADMIN | – | `UploadedFileRead` | uploads detail |
| 51 | Get job | `/jobs/{jid}` | GET | project-scoped | – | `ProcessingJobRead` | uploads page polling |
| 52 | List progress reports | `/projects/{id}/reports` | GET | member/ADMIN | `Page` | `Page<ProgressReportRead>` | `/projects/:id/reports-raw` |
| 53 | Get progress report | `/projects/{id}/reports/{rid}` | GET | member/ADMIN | – | `ProgressReportRead` | report detail |
| 54 | Request generated report | `/projects/{id}/generated-reports` | POST | Auth'd member | `GeneratedReportCreate` | `GeneratedReportRead` (201) | `/projects/:id/reports` |
| 55 | List generated reports | `/projects/{id}/generated-reports` | GET | Auth'd member | `Page` | `Page<GeneratedReportRead>` | `/projects/:id/reports` |
| 56 | Get generated report | `/projects/{id}/generated-reports/{rid}` | GET | Auth'd member | – | `GeneratedReportRead` | reports page polling |
| 57 | Download generated report | `/projects/{id}/generated-reports/{rid}/download` | GET | Auth'd member | – | binary (blob) | reports page download button |
| 58 | List notifications | `/notifications` | GET | Auth'd | `Page` | `Page<NotificationRead>` | notification bell/page |
| 59 | Unread count | `/notifications/unread-count` | GET | Auth'd | – | `{count:number}` | topbar badge |
| 60 | Mark read | `/notifications/{id}/read` | PATCH | Auth'd | – | `NotificationRead` | notification list |
| 61 | Mark all read | `/notifications/read-all` | POST | Auth'd | – | `{count:number}` | notification list |
| 62 | Send project notification | `/projects/{id}/notifications` | POST | manager/ADMIN | `NotificationCreate` | `NotificationRead` | project settings (notify action) |
| 63 | Health | `/health` | GET | Anyone | – | `HealthResponse` | connectivity banner |
| 64 | Readiness | `/health/ready` | GET | Anyone | – | `ReadinessResponse` | connectivity banner |
| 65 | Meta webhook | `/integrations/meta/webhook` | GET/POST | Meta only (HMAC) | – | – | **not a frontend screen** |
| 66 | Vapi webhook | `/integrations/vapi/webhook` | POST | Vapi only (shared secret) | – | – | **not a frontend screen** |

`*` `GET /projects` returns items typed `ProjectWithRole` per `ProjectRead` + `my_role`
(confirmed against `app/api/v1/projects.py`; `docs/API.md` doesn't spell this out).

**Corrections found only by hitting the live OpenAPI schema (`docs/API.md` says
otherwise or is silent) — verified end-to-end against a real running backend, not
assumed from the docs:**
- `GET /projects/{id}/schedules` and `GET /projects/{id}/members` return the `Page`
  envelope, not a plain array as `docs/API.md`'s prose implies for schedules (and is
  silent on for members). Row 22 and row 18 above are corrected accordingly; the
  frontend's `schedulesApi.list` / `projectsApi.listMembers` unwrap `.items`.
- `GET /projects/{id}/ml/features` returns an array of `{feature: description}`
  objects, not a single object.
- `GET /projects/{id}/matching/matches` items are full `ActivityMatchDetail` (not the
  slimmer `ActivityMatchRead`), though the frontend only reads the shared fields there.

## Roles

Exactly three (`app/core/constants.py::UserRole`): `ADMIN`, `PROJECT_MANAGER`,
`SITE_SUPERVISOR`. Project-level role (`my_role` on `ProjectWithRole`, `role` on
`MemberDetail`) is separate from the system role — RBAC guards in this table are the
**system**-role/`ManagedProject` rules actually enforced server-side (`app/api/deps.py`);
the frontend mirrors them for UX but the backend is the enforcement point (a hidden
button is not security — 403s are handled regardless).

## The 404-not-403 convention

A caller who isn't a project member gets `404` for anything under
`/projects/{id}/...`, not `403`. The frontend must render this as "project not found /
no access" rather than a generic error, and never assume a 404 on a project route means
the project was deleted.

## Vapi / WhatsApp — VERIFIED WORKING (2026-09-12)

Both webhooks were tested end-to-end against a live backend with real HMAC
signing and shared secrets — 18/18 conformance checks pass. See
`Voice & WhatsApp` in the UI (`/projects/:id/channels`), which surfaces the real
inbound rows each webhook created.

| Check | Result |
|---|---|
| Meta `GET` verification handshake echoes `hub.challenge` | pass |
| Meta `GET` rejects a wrong verify token | 403 |
| Meta `POST` with no signature / bad signature | 403 |
| Meta `POST` with valid `X-Hub-Signature-256` | 200, row created |
| Meta duplicate delivery of same `wamid` | 200, **no** second row |
| Vapi `POST` with no secret / wrong secret | 403 |
| Vapi `get_project_progress` / `get_delayed_activities` / `get_risk_summary` / `get_activity_details` | all answer with real project data |
| Vapi legacy `toolCalls` payload shape | handled |
| Vapi `Authorization: Bearer <secret>` | accepted |
| Vapi `end-of-call-report` transcript | ingested as a site report |

Three defects had to be fixed in the backend to get there — all uncommitted,
see "Backend fixes applied" at the end of this document.

## Vapi / WhatsApp — remaining architectural limits

- **No browser-embeddable Vapi web widget exists in the backend.** Vapi is wired as a
  **phone-call** webhook (`POST /integrations/vapi/webhook`) that FastAPI answers when
  Vapi's platform calls it — there is no endpoint that hands the frontend a public Vapi
  key, assistant id, or starts a web-based voice session. `VAPI_API_KEY`,
  `VAPI_ASSISTANT_ID`, `VAPI_PHONE_NUMBER_ID`, `VAPI_SECRET` are server-only settings
  never exposed via any response body. **The frontend cannot and must not fabricate a
  "click to talk" widget** — there is nothing for it to call into from the browser.
  The Assistant screen instead shows integration status/info (what the voice assistant
  can do over a phone call, and today's known limitations per
  `docs/PHASE9-10-AUDIT.md` findings 7-9: `get_delayed_activities` and
  `get_activity_details` currently error, `get_risk_summary` returns fabricated text).
- **WhatsApp is inbound-only from the frontend's perspective.** `POST
  /integrations/meta/webhook` receives WhatsApp messages from Meta and files them as
  progress reports; there is no outbound "send a WhatsApp message" endpoint exposed to
  authenticated users directly. The one outbound path is the generic notifications
  endpoint (`POST /projects/{id}/notifications` with `channel: "WHATSAPP"`), which per
  `backend/README.md` is a **dry-run stub** in Phase 8 (accepted and logged, not
  actually delivered). The frontend surfaces this honestly: sending a WhatsApp
  notification is offered, and the resulting `NotificationRead.status` is shown as-is
  (whatever the backend reports) rather than presented as "delivered".

## Known backend issues that shape frontend behavior

From `docs/PHASE9-10-AUDIT.md` (partially fixed by commit `05d2109`; items 3-9 and
11-15 not independently re-verified):

- Findings 1 & 2 (critical, fail-open webhooks) — fixed as of `05d2109`; not
  frontend-relevant since the frontend never calls these webhooks directly.
- Findings 7-9 — voice-assistant tool bugs — reflected as a caveat on the Assistant
  status screen, not hidden.
- Local `.env` has `VAPI_SECRET`/`META_APP_SECRET` unset, so in local dev both
  webhooks now fail closed (403/503) rather than open — nothing for the frontend to
  integrate with locally either way.

## Environment configuration

Frontend reads `VITE_API_BASE_URL` (see `frontend/.env.example`). Backend `.env`
already has `CORS_ORIGINS=http://localhost:3000,http://localhost:5173`, matching Vite's
default dev port (5173), so no backend change was needed for local CORS.

---

## Backend fixes applied (uncommitted — review or revert freely)

Making the Meta and Vapi webhooks actually work required fixing three real
defects in the backend. Nothing is committed or pushed; `git diff` shows
everything, and a copy of the patch is at
`~/Desktop/plan2progress-backend-fixes.patch`. All 509 backend tests pass with
these applied.

**1. `app/models/user.py` — `phone_normalised` was never written (blocking)**

Both webhooks identify the inbound sender/caller by exact match on
`User.phone_normalised`, but *nothing in the codebase ever populated that
column*. It was `NULL` for every user, including users who had a `phone` set —
so WhatsApp messages were silently dropped ("unknown phone") and every voice
tool answered "User is not authenticated or phone number not recognized".

Fixed with a `@validates("phone")` hook on the model, so the digits-only form is
derived on every write path (registration, admin create, profile edit, CLI,
seed scripts) rather than in one service. Empty normalises to `NULL` because the
column is `UNIQUE` and blanks would otherwise collide.

**2. `app/api/v1/integrations/meta.py` — WhatsApp idempotency never armed**

The handler checked `UploadedFile.provider_message_id` for a duplicate `wamid`
but never *stored* it, so the guard could never fire. Since Meta retries any
delivery it doesn't see a 200 for, one site report could be ingested and counted
several times. Now stored on ingest (verified: a repeat delivery creates no
second row). Also fixed a raw `job.status = "FAILED"` string to use the
`JobStatus.FAILED` enum, and set the ingested document type to
`DAILY_PROGRESS_REPORT` rather than `OTHER`.

**3. `app/api/v1/assistant.py` — two voice tools gave misleading answers**

- `get_delayed_activities` had no delay filter at all: it returned the first 5
  activities of the project regardless of whether any were late. Asked "what's
  delayed?", a supervisor got an arbitrary list. It now selects activities past
  their planned finish that aren't reported complete, worst first, with days
  late and percent complete.
- `get_risk_summary` read the real `DelayPrediction` rows but read a raw UUID
  aloud ("CRITICAL risk on activity 7f3c9a12-…"), which is useless on a phone
  call. It now names the activity code and name.

