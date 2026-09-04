# Performance

Every number here was measured, on a stated dataset, with a script committed in
this repository. Nothing is extrapolated and nothing is rounded in our favour.

## How to reproduce

```bash
cd backend
python -m perf.seed_perf_data --activities 5000 --reports-per-activity 30
python -m perf.benchmark
```

`perf/seed_perf_data.py` seeds with a fixed random seed, so two runs produce the
same dataset and a before/after comparison measures the code change rather than
a different shape of data. `perf/benchmark.py` warms caches once, then reports
the **median** of five runs — a mean would be dragged around by connection-pool
setup on the first call.

## The benchmark dataset

Chosen to match the shape of a real Oil India L1–L6 schedule rather than the
handful of rows a unit test creates. A query that looks instant over 20
activities can be the one that times out over 5,000.

| | |
|---|---|
| Activities | 5,000 |
| WBS shape | pyramid, L1→L6, ~60% of rows at L6 |
| Leaf activities | 3,049 |
| Progress rows | 91,470 (30 reports per leaf) |
| Dependencies | 3,048 (finish-to-start chain) |
| Hardware | single container, PostgreSQL 16 over a unix socket |

The unix socket matters when reading the query counts below: it makes
per-statement overhead almost free, so an N+1 that looks acceptable here would
be far worse across a real network hop. That is why query counts are reported
alongside timings.

## Results

Median of five runs, after warm-up.

| Read path | Before | After | Change | Queries |
|---|---|---|---|---|
| Progress rollup (whole schedule) | 2,542.8 ms | **422.3 ms** | **6.0× faster** | 5 |
| Progress summary | 2,539.2 ms | **323.8 ms** | **7.8× faster** | 5 |
| S-curve (planned vs actual) | 4,379.4 ms | **1,789.1 ms** | **2.4× faster** | 5 |
| `_latest_progress` (internal) | 2,391.0 ms | **127.3 ms** | **18.8× faster** | 2 |
| Delete one user | 12.6 ms | **5.5 ms** | **2.3× faster** | — |

Query counts were already low before this work — there was no N+1 to find. The
problem was row *volume* and algorithmic shape, which is why the fixes are query
rewrites rather than eager-loading hints.

## What was actually wrong

### 1. `_latest_progress` fetched the whole history to compute the latest row

`app/services/progress.py`. The rollup, the summary and the delay-risk report
all need one thing: the current status of every activity. The original
implementation selected **every** progress row for the schedule ordered
ascending, then let later rows overwrite earlier ones in a Python dict:

```python
stmt = select(ActualProgress).join(Activity).where(...).order_by(
    ActualProgress.reporting_date.asc()
)
latest = {}
for row in self.db.execute(stmt).scalars():
    latest[row.activity_id] = row   # last write wins
```

Correct, and it built **91,470 ORM instances to produce 3,049 values**. At
2,391 ms it was about **94%** of the entire 2,543 ms rollup.

The shape is what makes this serious: the cost grows with reporting *history*,
not with the size of the project. It is fast in a demo and slower every single
day a real project runs.

The fix pushes the reduction into PostgreSQL:

```sql
SELECT DISTINCT ON (activity_id) ...
ORDER BY activity_id, reporting_date DESC
```

There is no tie to break — `uq_progress_activity_date` already makes
`(activity_id, reporting_date)` unique — and that same index serves the
ordering, so **no new index was needed**. `DISTINCT ON` is PostgreSQL-specific,
which is acceptable: this project targets PostgreSQL and already relies on
JSONB throughout.

Verified equivalent, not just faster. A differential check ran both
implementations over the benchmark schedule at four `as_of` dates including one
before the project started:

```
as_of=None:       keys=3049/3049  keys_match=True  rows_match=True
as_of=2026-02-01: keys=3049/3049  keys_match=True  rows_match=True
as_of=2026-03-15: keys=3049/3049  keys_match=True  rows_match=True
as_of=2020-01-01: keys=0/0        keys_match=True  rows_match=True
```

### 2. The S-curve recomputed loop-invariant work, per sample

Two separate problems in `generate_s_curve`.

**A loop-invariant `min()` inside the sample loop.** This line ran once per
sample point:

```python
if last_report is not None and at >= min(r.reporting_date for r in rows):
```

A full pass over all 91,470 rows, for each of ~150 samples: **13.7 million
redundant comparisons** for a value that cannot change. Hoisted out.

**A nested re-scan of every activity's history, per sample.** For each sample
the code walked every leaf's full history looking for the latest row at or
before that date — `O(samples × leaves × history)`.

Because samples ascend and the rows are already date-ordered, this becomes a
single forward pass shared across all samples, maintaining a running earned
total and adjusting it by the delta when an activity reports again:
`O(history + samples)`, with each row visited exactly once overall.

### 3. The S-curve hydrated ORM entities it did not need

After the algorithmic fix the curve was still 3,099 ms, so it was profiled
rather than guessed at:

```
9,084,176 function calls in 5.449 seconds
  3.365s  sqlalchemy/engine/result.py:526(iterrows)      <- ORM hydration
  1.374s  psycopg/types/uuid.py:44(load)                 <- 289,362 UUIDs
  1.035s  uuid.py:139(__init__)
```

**3.34 s of 5.24 s was SQLAlchemy building `ActualProgress` instances**, and
1.37 s of that was parsing 289,362 UUIDs — three per row, when the curve reads
one. The curve touches exactly five fields, so it now selects those five
columns instead of whole entities. A SQLAlchemy `Row` exposes them under the
same attribute names, so `_completion()` needed no adapter and still works
unchanged with real ORM instances elsewhere.

That took the S-curve from 3,099 ms to 1,609 ms.

Verified equivalent across all 46 sample points of the benchmark schedule:

```
old points: 46   new points: 46
max planned delta: 0.000000000000
max actual  delta: 0.000000000000
None-ness mismatches: 0
IDENTICAL
```

### 4. Six foreign keys to `users` had no index

None of `reported_by_id`, `uploaded_by_id`, `reviewed_by_id`, `trained_by_id`
or `generated_by_id` is used as a query filter — they are audit columns, written
once and read back with their row. Indexing them for read speed would have been
cargo-cult, and the codebase was checked to confirm it before adding anything.

They are indexed for a different reason: all are `ON DELETE SET NULL`, so
PostgreSQL must locate referencing rows when a user is deleted, and without an
index that is a sequential scan of each child table. `actual_progress` is the
largest and fastest-growing table in the schema.

Measured, median of three runs: **12.6 ms → 5.5 ms** per user deletion.

A small absolute saving, recorded as such. What justifies it is the shape: the
unindexed cost scales with table size, so the same delete against a few million
progress rows becomes a multi-second scan per child table, while the indexed
cost stays flat. Migration `82904d0d199d`.

## Guarding against regression

`tests/test_performance_regressions.py` — 8 tests, and deliberately **not**
timing assertions. A wall-clock threshold in CI is a flaky test: it fails on a
loaded runner, and the usual response is to loosen it until it never catches
anything.

Instead each test asserts the *property* that made the code fast, which is
deterministic and meaningful even on a 72-row fixture:

- `_latest_progress` issues exactly one statement, and that statement contains
  `DISTINCT ON`
- it returns one row per activity, not the whole history
- it returns the **newest** row (a `DISTINCT ON` ordered `ASC` by mistake would
  have the right shape, the right row count, and silently stale data)
- the S-curve issues a small fixed number of statements regardless of sample
  count
- the S-curve's progress read does not select `actual_progress.id`, which is the
  tell that entity loading has crept back in
- the S-curve's running total stays monotonic and within 0–100% over a
  monotonic history, which is how faulty delta bookkeeping would show up
- no foreign key to `users` is unindexed — asserted as a property against
  `pg_constraint`, so an audit column added in a later phase is caught too

These guards were themselves verified by reverting `_latest_progress` to its
original implementation and confirming the suite goes red with a useful message:

```
FAILED test_latest_progress_returns_one_row_per_activity_not_the_whole_history
AssertionError: latest-progress no longer uses DISTINCT ON; it is probably
fetching the full history again -- see docs/PERFORMANCE.md
```

A guard that passes against the code it is meant to reject is worse than no
guard, so this check is part of the work rather than an afterthought.

## Known remaining cost

The S-curve is still the slowest read at ~1.8 s on a 5,000-activity schedule
with three months of daily reporting. The remaining time is genuine work: the
curve needs the full history because each sample point asks what was true on a
different past date, so unlike the rollup it cannot be reduced to one row per
activity.

Stated plainly rather than tuned further, because the next step is a design
decision rather than an optimisation. Options, roughly in order of
attractiveness:

1. **Cache per (schedule, as-of-week).** The curve only changes when new
   progress is reported, so it is a good caching candidate; `REDIS_URL` is
   already configured for Celery.
2. **Materialise cumulative earned value per activity per week** on write, and
   read the curve from that. Fastest, and the largest change.
3. **Push the interpolation into SQL** with a window function over reporting
   dates. Keeps it stateless, at the cost of a substantially harder query.

Not attempted in Phase 11: 1.8 s is acceptable for a chart that is not on the
critical path of a site supervisor filing a report, and none of these should be
built before there is a real user-facing reason to prefer one.

## Also checked, and fine

- **No N+1 anywhere on the measured paths.** Query counts are 2–5 per read path
  and independent of project size. The `raiseload()` guards added in Phase 3/4
  (on `Activity.children` / `Activity.parent`) are doing their job: a stray lazy
  load raises instead of quietly issuing thousands of statements.
- **Core table indexing was already sound** before this work — `activities`,
  `actual_progress`, `activity_dependencies`, `schedules` and
  `delay_predictions` all carry indexes on the columns actually filtered and
  ordered on. Only the audit foreign keys were missing.
- **Bulk seeding of 5,000 activities and 91,470 progress rows takes 6.3 s**
  through SQLAlchemy Core, which is why `perf/seed_perf_data.py` uses Core
  inserts rather than the ORM.
