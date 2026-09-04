# Phase 9 / Phase 10 Audit

**Scope:** commits `1c65b6b`, `4c0f6e1`, `8c50471` — Meta/WhatsApp integration, Vapi voice
assistant, and the assistant tool layer.

**Status: no Phase 9/10 file was modified by Phase 11.** This document is a record of
findings only. Every item below was reproduced against a live `uvicorn` server on a real
PostgreSQL database and a real Redis broker before being written down. Nothing here is
inferred from reading the code alone; where a claim rests only on a code read, it says so.

**Update — commit `05d2109`:** the author of Phase 9/10 pushed a fix commit titled "Fix
all 15 audit issues for Phase 9 & 10 (Security & Stability)". Findings 1, 2, and 10 were
re-verified live against that commit and confirmed fixed: the Vapi webhook now returns
403 (not 200) with `VAPI_SECRET` unset, the Meta webhook now returns 503 (not 200) with
`META_APP_SECRET` unset, and `test_vapi_tool_call` passes. `tests/test_auth_boundary_matrix.py`
was updated accordingly (the test that pinned the fail-open vulnerability was replaced
with a regression guard for the fix), and the CI workflow's deselect/informational step
for the vapi test was removed. The remaining findings (3-9, 11-15) have not been
individually re-verified against `05d2109` — the commit message claims all 15 are fixed,
but that has not been checked here point-by-point and should not be assumed.

**Files audited (unchanged):**

```
backend/app/api/v1/integrations/meta.py
backend/app/api/v1/integrations/vapi.py
backend/app/api/v1/assistant.py
backend/app/notifications/whatsapp.py
backend/app/api/v1/router.py
backend/app/core/config.py
backend/seed_user.py
backend/send_report_whatsapp.py
backend/tests/api/test_integrations_meta.py
backend/tests/api/test_integrations_vapi.py
backend/tests/api/test_whatsapp_dispatcher.py
```

---

## Summary

| # | Severity | Finding | Evidence |
|---|----------|---------|----------|
| 1 | **Critical** | Vapi webhook is unauthenticated by default and returns project data to any caller | Reproduced |
| 2 | **Critical** | Meta webhook is unauthenticated by default and accepts forged progress reports | Reproduced |
| 3 | **High** | Meta verify token written to logs in plaintext | Reproduced |
| 4 | **High** | Full webhook payloads (phone numbers, message bodies) logged at WARNING | Reproduced |
| 5 | **High** | No idempotency on WhatsApp ingestion — one message counted N times | Reproduced |
| 6 | **High** | Broker down returns 500 to Meta, which guarantees retries, which duplicate | Reproduced |
| 7 | **Medium** | 2 of 5 voice tools crash on a column that does not exist | Reproduced |
| 8 | **Medium** | `get_risk_summary` returns fabricated risk text, ignoring the real predictor | Reproduced |
| 9 | **Medium** | `get_project_report` promises a report that is never generated | Reproduced |
| 10 | **Medium** | Payload key mismatch makes the suite red (`test_vapi_tool_call`) | Reproduced |
| 11 | **Medium** | Substring phone matching can resolve to the wrong user | Code read + partial repro |
| 12 | **Medium** | Multi-project users have reports filed against an arbitrary project | Code read |
| 13 | **Low** | Blocking sync HTTP call inside an `async` endpoint | Code read |
| 14 | **Low** | Vapi `phoneNumberId` / `assistantId` hardcoded in source | Code read |
| 15 | **Low** | `seed_user.py` hardcodes a project code, so it fails on second run | Observed |

The two Critical items are remotely exploitable with a single `curl` and no credentials.
They are the ones to fix first.

---

## 1. Critical — Vapi webhook is unauthenticated by default and leaks project data

`app/core/config.py` declares `VAPI_SECRET: str | None = None`, and
`app/api/v1/integrations/vapi.py:20-22` fails **open** when it is unset:

```python
def verify_vapi_secret(x_vapi_secret: str) -> bool:
    if not settings.VAPI_SECRET:
        return True  # If not configured, allow for testing/dev
    return x_vapi_secret == settings.VAPI_SECRET
```

Combined with substring phone matching (finding 11), an unauthenticated caller who
supplies a single digit as their phone number is treated as a real user.

Reproduction — no credentials, no headers:

```bash
curl -s -X POST http://HOST/api/v1/integrations/vapi/webhook \
  -H "Content-Type: application/json" \
  -d '{"message":{"type":"tool-calls",
       "call":{"customer":{"number":"+9"}},
       "toolWithToolCallList":[{"toolCall":{"id":"c1",
         "function":{"name":"get_project_progress","arguments":{}}}}]}}'
```

Observed response:

```json
{"results":[{"toolCallId":"c1",
  "result":"Project Plan2Progress Demo Project: Status is PLANNING. Start: None, Finish: None."}]}
```

A real project's name and status were returned to an anonymous caller whose only input
was the digit `9`. With `VAPI_SECRET` set, the same request correctly returns `403` —
confirming the vulnerability is precisely the fail-open default, not the comparison.

**Suggested fix:** fail closed. Refuse to serve the webhook at all when `VAPI_SECRET` is
unset (or require it in non-local environments, as `SECRET_KEY` already is), and use
`hmac.compare_digest` for the comparison.

## 2. Critical — Meta webhook is unauthenticated by default and accepts forged reports

`META_APP_SECRET` also defaults to `None`, and the signature check at
`meta.py:67` is guarded by it:

```python
if settings.META_APP_SECRET:
    if not verify_meta_signature(payload, x_hub_signature_256):
        raise HTTPException(status_code=403, detail="Invalid signature")
```

With the secret unset there is no check at all, so anyone can inject site progress
reports attributed to a real user.

Reproduction — no signature header:

```bash
curl -s -X POST http://HOST/api/v1/integrations/meta/webhook \
  -H "Content-Type: application/json" \
  -d '{"object":"whatsapp_business_account","entry":[{"changes":[{"value":{
       "contacts":[{"wa_id":"919876543210"}],
       "messages":[{"from":"919876543210","type":"text",
         "text":{"body":"INJECTED BY ANONYMOUS CALLER: poured 500 cum concrete"}}]}}]}]}'
```

Observed: an `uploaded_files` row (`whatsapp_message.txt`, 53 bytes) and a
`processing_jobs` row were both committed, attributed to the matched user and their
project. The forged text then flows into the document-extraction and progress-matching
pipeline as if a supervisor had reported it.

**Suggested fix:** as above — fail closed, and treat a missing `META_APP_SECRET` in a
deployed environment as a startup error rather than a silent bypass.

## 3. High — The Meta verify token is written to the logs in plaintext

`meta.py:47`:

```python
logger.warning(f"Received token: {hub_verify_token}, expected: {settings.META_VERIFY_TOKEN}")
```

This runs unconditionally on every verification attempt, including attacker-driven ones.
Reproduction — one request with a guessed token:

```bash
curl "http://HOST/api/v1/integrations/meta/webhook?hub.mode=subscribe\
&hub.verify_token=attacker-guess&hub.challenge=CH123"
```

Observed log line:

```
WARNING app.api.v1.integrations.meta: Received token: attacker-guess,
        expected: super-secret-verify-token-abc123
```

The real shared secret is now in the log stream, and by extension in any log aggregator,
error tracker or support bundle. An attacker who cannot read logs can still spray the
endpoint to flood them with the secret.

**Suggested fix:** delete the line, or log only whether the comparison succeeded.

## 4. High — Full inbound payloads logged at WARNING

`meta.py:73` logs the entire webhook body, which contains sender phone numbers and
message text:

```python
logger.warning(f"Incoming Meta webhook: {data}")
```

That is personal data at WARNING level in ordinary operation. **Suggested fix:** drop to
DEBUG and log identifiers rather than bodies.

*Partly mitigated without touching this file:* Phase 11 adds a log-redaction filter
(`app/core/log_redaction.py`) that masks known secret and phone patterns on the way out.
That reduces blast radius; it does not remove the need to fix the call sites.

## 5. High — No idempotency on WhatsApp ingestion

The WhatsApp message id (`messages[].id`, e.g. `wamid.…`) is available in the payload and
never used. Every delivery of the same message creates fresh rows.

Reproduction — the same payload, same `wamid.STABLE_ID_123`, delivered three times:

```
delivery 1 -> HTTP 200
delivery 2 -> HTTP 200
delivery 3 -> HTTP 200

uploaded_files:  3
processing_jobs: 3
```

One site report became three, and each one flows independently into progress matching.

**Suggested fix:** persist the WhatsApp message id with a unique constraint and treat a
repeat delivery as a no-op. The `Notification.idempotency_key` pattern already in Phase 8
is a good model.

## 6. High — Broker down returns 500, which makes Meta retry, which duplicates

`meta.py:179` calls `process_uploaded_file.delay(str(job.id))` inline with no error
handling, *after* `db.commit()`. With Redis unreachable the endpoint raises and returns
`500` — reproduced:

```
HTTP 500 {"error":{"code":"INTERNAL_ERROR", ...}}
uploaded_files row: created
processing_jobs:    1   (left PENDING, no error recorded)
```

Meta retries deliveries that do not return 200, and each retry duplicates per finding 5.
So the two defects compound: a Redis blip turns one site report into several.

This is the same failure mode that Phase 3/4 already fixed for the document upload path
(broker failure marks the job `FAILED` with a reason instead of leaving it `PENDING`
forever) — see `app/services/document.py`. The new Meta path does not go through that
service and so reintroduces the original bug.

**Suggested fix:** wrap the dispatch, always return 200 to Meta, and record broker
failure on the job row the way `DocumentService` does.

## 7. Medium — Two of the five voice tools crash

`assistant.py:49` and `assistant.py:63` both filter on `Activity.project_id`:

```python
select(Activity).where(Activity.project_id.in_(project_ids))
```

`Activity` has no `project_id` column — an activity belongs to a *schedule*, and the
schedule belongs to the project (`app/models/schedule.py`). Verified directly:

```
Activity.project_id:         MISSING
Activity.status:             MISSING
Activity.actual_progress_pct: MISSING
Activity.planned_finish:     OK
```

Live result for both tools:

```json
{"results":[{"toolCallId":"c1",
  "error":"type object 'Activity' has no attribute 'project_id'"}]}
```

So a caller asking the voice assistant "what's delayed?" or "tell me about activity A1"
gets an error. `Activity.status` (:53, :67) and `Activity.actual_progress_pct` (:67) are
also absent and would fail immediately after the first line is fixed; status and
percent-complete live on `ActualProgress`, one row per activity per reporting date.

**Suggested fix:** join through `Schedule` (`Activity.schedule_id == Schedule.id`,
`Schedule.project_id.in_(...)`) and read status/progress from the latest `ActualProgress`
row — the same shape `app/services/progress.py` uses.

## 8. Medium — `get_risk_summary` returns fabricated risk text

`assistant.py:56` returns a hardcoded string:

```python
return ("Risk Summary: Currently, there are potential delays in concrete pouring due to "
        "weather, and a 10% risk of budget overrun in structural steel procurement.")
```

Reproduced: the same sentence comes back on every call, for every project, for every
user. The platform has a real predictor — Phase 7's `delay_predictions` table, with
per-activity probabilities, risk levels and slip days, plus the rule-based/ML method
that produced each one — and this tool consults none of it.

This matters beyond correctness: it is the reply a judge is most likely to trigger by
asking the voice assistant about risk, and it presents invented numbers as analysis. It
is the same class of defect as the Phase 8 report finding (fabricated risk bands) and the
project's no-fake-AI rule covers it directly.

**Suggested fix:** read `DelayPrediction` for the caller's projects and summarise the real
rows, saying plainly when no forecast exists yet.

## 9. Medium — `get_project_report` promises a report that is never generated

`assistant.py:70` tells the caller the report "will be generated and sent via WhatsApp
shortly" and enqueues nothing. Reproduced: the string is returned and no report row,
job or outbound message is created. Phase 8 has a working generator
(`ReportService.generate_report`) that this could call.

## 10. Medium — Payload key mismatch leaves the test suite red

`vapi.py:54` reads `message.toolWithToolCallList`; `tests/api/test_integrations_vapi.py`
sends `message.toolCalls`. Both halves reproduced against the live server:

```
toolCalls           -> {"results":[]}
toolWithToolCallList -> {"results":[{"toolCallId":"c1","result":"Project …"}]}
```

So `test_vapi_tool_call` fails (`assert 0 == 1`) and the full suite is **red** — 342
tests collected, 341 passing, this one failing:

```
FAILED tests/api/test_integrations_vapi.py::test_vapi_tool_call - assert 0 == 1
```

Vapi has used both shapes across API versions, so the safe fix is to read whichever is
present rather than picking one. Until this is resolved one way or the other, CI cannot
be green — see `.github/workflows/ci.yml`, which reports this failure explicitly as a
known Phase 9/10 issue rather than hiding it.

## 11. Medium — Substring phone matching can resolve to the wrong user

`meta.py:129` and `vapi.py:49`:

```python
select(User).where(User.phone.like(f"%{sender_wa_id}%"))  # → .first()
```

A substring match plus `.first()` means a short or partial number can match several
users and one is chosen arbitrarily. Partially reproduced in finding 1, where the digit
`9` matched a user. With two users whose numbers share a suffix, a call from either can
resolve to the other — and the assistant then answers with that other user's projects.

**Suggested fix:** normalise to E.164 on write and match with `==`.

## 12. Medium — Reports filed against an arbitrary project for multi-project users

`meta.py:137-145` takes the first `ProjectMembership` returned, and
`assistant.py:83` takes `project_ids[0]`, both with a `# MVP` comment. For a supervisor
on two projects, a WhatsApp report or call transcript is silently filed against whichever
row the database happens to return first, with no indication to the reporter.

**Suggested fix:** ask which project when the user has more than one, or key it off the
WhatsApp number the message arrived on.

## 13. Low — Blocking sync HTTP call inside an `async` endpoint

`meta.py:113-116` uses a synchronous `httpx.Client()` inside `async def receive_webhook`,
so the event loop is blocked for the duration of the outbound Vapi call. Under
concurrent webhook traffic this serialises the whole worker. **Suggested fix:**
`httpx.AsyncClient` with `await`, or move the call to a Celery task.

## 14. Low — Vapi identifiers hardcoded in source

`meta.py:103-104` embeds `phoneNumberId` and `assistantId` as literals. These differ per
environment and belong in settings alongside `VAPI_API_KEY`.

## 15. Low — `seed_user.py` cannot be run twice

The script always creates a project with code `TEST-01`, which violates the unique
constraint on the second run. Observed while seeding a second test user:

```
UniqueViolation … projects_code_key … 'code': 'TEST-01'
```

The user lookup is idempotent but the project creation is not.

---

## What Phase 11 does and does not do about this

Phase 11 changed **no** Phase 9/10 file. Two Phase 11 additions reduce the blast radius
of findings above without touching them:

- `app/core/log_redaction.py` masks secrets and phone numbers in log output, partially
  mitigating findings 3 and 4.
- `app/core/rate_limit.py` limits unauthenticated request rates, which slows — but does
  not close — exploitation of findings 1 and 2.

Neither is a substitute for fixing the call sites. The two Critical findings remain
exploitable until `VAPI_SECRET` and `META_APP_SECRET` are set in the deployed
environment, which is the fastest available mitigation and requires no code change at
all: **set both secrets and the two Critical findings are closed today.**
