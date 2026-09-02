"""Parsing Excel/CSV baseline schedules into activities and dependencies.

Two principles run through this module.

**Nothing is dropped silently.** A row skipped, a predecessor code that matched
no activity, a date that would not parse -- each is counted and named in the
parse summary returned to the caller and stored on the schedule. A schedule
that reports ``COMPLETED`` while a third of its dependency network was quietly
discarded is worse than one that fails, because nobody goes looking.

**Ambiguity is resolved in a fixed order, for the whole column.** ISO dates
are read as ISO, then what remains is read day-first, then anything still
unparsed gets one last generic attempt -- see :func:`_parse_date_column`. A
single file can therefore hold ISO and slash dates together without either
being misinterpreted, and nothing is left to per-value guesswork.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.core.constants import DependencyType, Discipline, JobStatus
from app.core.exceptions import UnprocessableFileError
from app.core.logging import get_logger
from app.models.schedule import Activity, ActivityDependency, Schedule
from app.schemas.schedule import ScheduleColumnMapping

logger = get_logger(__name__)


class ScheduleParserError(UnprocessableFileError):
    pass


ALIASES = {
    "civil": Discipline.CIVIL,
    "civil works": Discipline.CIVIL,
    "piping": Discipline.PIPING,
    "mechanical": Discipline.MECHANICAL,
    "electrical": Discipline.ELECTRICAL,
    "instrumentation": Discipline.INSTRUMENTATION,
    "e&i": Discipline.ELECTRICAL,
    "structural": Discipline.STRUCTURAL,
    "welding": Discipline.WELDING_NDT,
    "ndt": Discipline.WELDING_NDT,
    "survey": Discipline.SURVEY,
    "coating": Discipline.COATING,
    "testing": Discipline.TESTING_PRECOMMISSIONING,
    "pre-commissioning": Discipline.TESTING_PRECOMMISSIONING,
    "precommissioning": Discipline.TESTING_PRECOMMISSIONING,
    "commissioning": Discipline.TESTING_PRECOMMISSIONING,
    "hydrotesting": Discipline.TESTING_PRECOMMISSIONING,
}

# How many warnings to keep. A malformed file can generate one per row, and the
# summary is stored as JSON on the schedule -- the count stays exact, only the
# examples are capped.
_MAX_WARNINGS = 50


@dataclass(slots=True)
class ParseSummary:
    """What the parse actually did, including everything it could not use."""

    rows_read: int = 0
    activities_created: int = 0
    rows_skipped_blank: int = 0
    dependencies_created: int = 0
    dependencies_duplicate: int = 0
    predecessors_unresolved: int = 0
    dates_unparsed: int = 0
    parents_relinked_to_ancestor: int = 0
    warnings: list[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        if len(self.warnings) < _MAX_WARNINGS:
            self.warnings.append(message)

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "rows_read": self.rows_read,
            "activities_created": self.activities_created,
            "rows_skipped_blank": self.rows_skipped_blank,
            "dependencies_created": self.dependencies_created,
            "dependencies_duplicate": self.dependencies_duplicate,
            "predecessors_unresolved": self.predecessors_unresolved,
            "dates_unparsed": self.dates_unparsed,
            "parents_relinked_to_ancestor": self.parents_relinked_to_ancestor,
            "warnings": self.warnings,
        }
        if len(self.warnings) >= _MAX_WARNINGS:
            payload["warnings_truncated"] = True
        return payload


def _discipline(raw: str | None) -> Discipline | None:
    if raw is None or (not isinstance(raw, str) and pd.isna(raw)):
        return None
    if isinstance(raw, str) and not raw.strip():
        return None
    key = str(raw).strip().lower()
    try:
        return Discipline(str(raw).strip().upper().replace(" ", "_"))
    except ValueError:
        return ALIASES.get(key, Discipline.OTHER)


def _assert_acyclic(edges: dict[str, set[str]]) -> None:
    """Iterative depth-first cycle detection.

    Iterative rather than recursive because a linear finish-to-start chain of a
    few thousand activities is completely routine on a pipeline schedule, and
    recursion blows Python's stack at around a thousand -- surfacing as a
    ``RecursionError`` reported to the user as a file-content problem.
    """
    WHITE, GREY, BLACK = 0, 1, 2
    colour: dict[str, int] = {node: WHITE for node in edges}

    for root in list(edges):
        if colour.get(root, WHITE) != WHITE:
            continue
        # Each frame is (node, iterator over its successors). The path list
        # mirrors the stack so a detected cycle can be reported as a chain.
        stack: list[tuple[str, Any]] = [(root, iter(edges.get(root, ())))]
        path: list[str] = [root]
        colour[root] = GREY

        while stack:
            node, successors = stack[-1]
            advanced = False
            for nxt in successors:
                if colour.get(nxt, WHITE) == GREY:
                    chain = " -> ".join(path[path.index(nxt):] + [nxt])
                    raise ScheduleParserError(f"Circular dependency: {chain}")
                if colour.get(nxt, WHITE) == WHITE:
                    colour[nxt] = GREY
                    path.append(nxt)
                    stack.append((nxt, iter(edges.get(nxt, ()))))
                    advanced = True
                    break
            if not advanced:
                colour[node] = BLACK
                stack.pop()
                path.pop()


# Predecessor cell formats seen in real exports:
#   "A1010"          plain code, implicit finish-to-start, no lag
#   "A1010FS+3"      Primavera, no separator
#   "A1010 FS+3"     with a separator
#   "A1010SS-2"      start-to-start, negative lag
#   "12FS+3 days"    MS Project, with a unit suffix
#   "A1010FS+8h"     hours, which are NOT days
#
# The activity-code group is non-greedy and the pattern is anchored at the end,
# so the relationship type is claimed by its own group instead of being
# swallowed by the code. A greedy code group turns "A1FS+3" into the code
# "A1FS", which matches no activity, and the dependency is silently dropped.
_DEPENDENCY_RE = re.compile(
    r"""^\s*
        (?P<code>.+?)                          # activity code, non-greedy
        \s*
        (?P<type>FS|SS|FF|SF)?                  # relationship type
        \s*
        (?P<lag>[+-]\s*\d+(?:\.\d+)?)?        # signed lag
        \s*
        (?P<unit>d|day|days|h|hr|hrs|hour|hours|w|wk|week|weeks)?
        \s*$""",
    re.IGNORECASE | re.VERBOSE,
)

# ``ActivityDependency.lag`` is a float column in days with no unit of its own,
# so a stated unit has to be converted here. Storing "8h" as 8 makes every
# downstream consumer read it as eight days -- a 24x error on a real export.
_LAG_UNIT_DAYS: dict[str, float] = {
    "d": 1.0, "day": 1.0, "days": 1.0,
    "h": 1.0 / 24.0, "hr": 1.0 / 24.0, "hrs": 1.0 / 24.0,
    "hour": 1.0 / 24.0, "hours": 1.0 / 24.0,
    "w": 7.0, "wk": 7.0, "week": 7.0, "weeks": 7.0,
}


def _parse_dependency(dep_str: str) -> tuple[str, DependencyType, float]:
    """Split a predecessor cell into (activity_code, relationship, lag in days).

    An unrecognised cell is treated as a bare activity code with an implicit
    finish-to-start relationship and no lag, which is how a plain code column
    behaves. The lag is a float in days: a fractional lag is real (half a shift)
    and truncating it to an integer silently discards it.
    """
    dep_str = str(dep_str).strip()
    match = _DEPENDENCY_RE.match(dep_str)
    if not match:
        return dep_str, DependencyType.FINISH_TO_START, 0.0

    pred_code = match.group("code").strip()
    raw_type = match.group("type")
    lag_str = match.group("lag")
    unit = (match.group("unit") or "").lower()

    lag = 0.0
    if lag_str:
        try:
            lag = float(lag_str.replace(" ", "")) * _LAG_UNIT_DAYS.get(unit, 1.0)
        except ValueError:
            lag = 0.0

    try:
        dtype = (
            DependencyType(raw_type.upper()) if raw_type
            else DependencyType.FINISH_TO_START
        )
    except ValueError:
        dtype = DependencyType.FINISH_TO_START

    return pred_code, dtype, lag


def _parse_date_column(series: pd.Series, summary: ParseSummary, label: str) -> pd.Series:
    """Parse a whole date column, resolving ambiguity in a fixed order.

    Three passes, and the order is the whole point:

    1. **ISO 8601 first.** ``2026-05-01`` is unambiguous and must be read as
       1 May. Passing ``dayfirst=True`` at an ISO string makes pandas return
       5 January -- a silent four-month error on the most common export format
       there is.
    2. **Day-first for what is left.** ``03/04/2026`` in an Indian or European
       export means 3 April; month-first parsing turns that into a silent
       30-day error.
    3. **Anything else,** which picks up named months like ``01-Mar-2026``.

    Each pass only touches values the previous one could not read, so a single
    column can hold ISO and slash dates together without either being
    misinterpreted. Values that survive all three become null and are counted,
    so "the plan states no dates" stays distinguishable from "the dates were in
    a format we could not read".
    """
    parsed = pd.to_datetime(series, errors="coerce", format="ISO8601")
    for options in ({"dayfirst": True, "format": "mixed"}, {"format": "mixed"}):
        remaining = series.notna() & parsed.isna()
        if not remaining.any():
            break
        parsed.loc[remaining] = pd.to_datetime(
            series[remaining], errors="coerce", **options
        )

    unparsed = int((series.notna() & parsed.isna()).sum())
    if unparsed:
        summary.dates_unparsed += unparsed
        examples = series[series.notna() & parsed.isna()].astype(str).unique()[:3]
        summary.warn(
            f"{unparsed} value(s) in the {label} column could not be read as a "
            f"date and were stored as blank, e.g. {list(examples)}."
        )
    return parsed


class ScheduleParser:
    """Parses Excel/CSV schedules and maps them to our Activity models."""

    def __init__(self, db: Session, schedule: Schedule) -> None:
        self.db = db
        self.schedule = schedule

    # ------------------------------------------------------------------ read

    @staticmethod
    def _read_frame(file_content: bytes, filename: str, mapping: ScheduleColumnMapping):
        """Load the upload into a DataFrame.

        The extension test is case-insensitive: ``SCHEDULE.CSV`` is what Excel
        on Windows produces by default, and rejecting it as an unsupported
        format is a bug the user cannot work around.

        The engine is left to pandas rather than pinned to openpyxl, which
        cannot read the legacy BIFF ``.xls`` format at all -- pinning it made
        every ``.xls`` upload fail with "File is not a zip file" despite the
        extension being advertised as supported.
        """
        # Force text for the columns where pandas' type inference is actively
        # harmful: a WBS path of 1.10 must not become the float 1.1, and an
        # activity code of 001 must not become 1.
        str_cols = {
            c: str
            for c in (mapping.activity_code, mapping.wbs_path, mapping.predecessors)
            if c
        }
        lowered = filename.lower()
        if lowered.endswith(".csv"):
            return pd.read_csv(io.BytesIO(file_content), dtype=str_cols)
        if lowered.endswith((".xls", ".xlsx", ".xlsm")):
            return pd.read_excel(io.BytesIO(file_content), dtype=str_cols)
        raise ScheduleParserError(
            "Unsupported file format. Must be .csv, .xls, .xlsx or .xlsm."
        )

    # ----------------------------------------------------------------- parse

    def parse_file(
        self, file_content: bytes, filename: str, mapping: ScheduleColumnMapping
    ) -> ParseSummary:
        """Parse the file, create activities, and construct the hierarchy."""
        summary = ParseSummary()
        try:
            df = self._read_frame(file_content, filename, mapping)
        except ScheduleParserError:
            self._fail_schedule()
            raise
        except Exception as exc:  # noqa: BLE001 - any read failure is the file's
            self._fail_schedule()
            raise ScheduleParserError(f"Failed to read file: {exc}") from exc

        for col in (mapping.activity_code, mapping.name):
            if col not in df.columns:
                self._fail_schedule()
                raise ScheduleParserError(
                    f"Required column '{col}' not found in the file."
                )

        try:
            summary.rows_read = int(len(df))
            before = len(df)
            df = df.dropna(subset=[mapping.activity_code, mapping.name])
            summary.rows_skipped_blank = before - len(df)
            if summary.rows_skipped_blank:
                summary.warn(
                    f"{summary.rows_skipped_blank} row(s) had no activity code or "
                    f"no name and were skipped."
                )

            has = lambda col: bool(col) and col in df.columns  # noqa: E731

            # Dates are resolved column-wide, once, before the row loop.
            starts = (
                _parse_date_column(df[mapping.planned_start], summary, "planned start")
                if has(mapping.planned_start) else None
            )
            finishes = (
                _parse_date_column(df[mapping.planned_finish], summary, "planned finish")
                if has(mapping.planned_finish) else None
            )

            activities_to_create: list[Activity] = []
            seen_codes: set[str] = set()
            seen_paths: dict[str, str] = {}

            for index, row in df.iterrows():
                row_num = index + 2  # approximate spreadsheet row (1-indexed + header)

                act_code = str(row[mapping.activity_code]).strip()
                if not act_code or pd.isna(row[mapping.activity_code]):
                    summary.rows_skipped_blank += 1
                    continue
                if act_code in seen_codes:
                    raise ScheduleParserError(
                        f"Row {row_num}: Duplicate activity code '{act_code}'"
                    )
                seen_codes.add(act_code)

                name = str(row[mapping.name]).strip()

                wbs_path = (
                    str(row[mapping.wbs_path]).strip()
                    if has(mapping.wbs_path) and pd.notna(row[mapping.wbs_path])
                    else ""
                )
                if wbs_path:
                    # Duplicate paths make parent linking arbitrary: two rows
                    # claim the same node and whichever is seen last silently
                    # becomes the parent of everything beneath it.
                    if wbs_path in seen_paths:
                        raise ScheduleParserError(
                            f"Row {row_num}: WBS path '{wbs_path}' is already used by "
                            f"activity '{seen_paths[wbs_path]}'. Paths must be unique."
                        )
                    seen_paths[wbs_path] = act_code

                level = 1
                if has(mapping.level) and pd.notna(row[mapping.level]):
                    try:
                        level = int(float(row[mapping.level]))
                    except (ValueError, TypeError):
                        raise ScheduleParserError(
                            f"Row {row_num}: Cannot parse level "
                            f"'{row[mapping.level]}'"
                        ) from None
                    if not 1 <= level <= 6:
                        raise ScheduleParserError(
                            f"Row {row_num}: Level must be between 1 and 6, "
                            f"got {level}"
                        )

                discipline = _discipline(
                    row[mapping.discipline] if has(mapping.discipline) else None
                )

                planned_start = None
                planned_finish = None
                if starts is not None:
                    value = starts.loc[index]
                    planned_start = value.date() if pd.notna(value) else None
                if finishes is not None:
                    value = finishes.loc[index]
                    planned_finish = value.date() if pd.notna(value) else None
                if (
                    planned_start is not None
                    and planned_finish is not None
                    and planned_finish < planned_start
                ):
                    raise ScheduleParserError(
                        f"Row {row_num}: planned finish {planned_finish} is before "
                        f"planned start {planned_start}."
                    )

                budgeted_qty = None
                if has(mapping.budgeted_quantity) and pd.notna(
                    row[mapping.budgeted_quantity]
                ):
                    try:
                        budgeted_qty = float(row[mapping.budgeted_quantity])
                    except (ValueError, TypeError):
                        summary.warn(
                            f"Row {row_num}: quantity "
                            f"'{row[mapping.budgeted_quantity]}' is not a number "
                            f"and was stored as blank."
                        )
                    else:
                        if budgeted_qty < 0:
                            raise ScheduleParserError(
                                f"Row {row_num}: budgeted quantity cannot be "
                                f"negative ({budgeted_qty})."
                            )

                uom = (
                    str(row[mapping.uom]).strip()
                    if has(mapping.uom) and pd.notna(row[mapping.uom])
                    else None
                )

                activities_to_create.append(
                    Activity(
                        schedule_id=self.schedule.id,
                        activity_code=act_code,
                        name=name,
                        wbs_path=wbs_path,
                        level=level,
                        discipline=discipline,
                        planned_start=planned_start,
                        planned_finish=planned_finish,
                        budgeted_quantity=budgeted_qty,
                        uom=uom,
                    )
                )

            self.db.add_all(activities_to_create)
            self.db.flush()
            summary.activities_created = len(activities_to_create)

            if mapping.wbs_path:
                self._link_parents(activities_to_create, summary)

            if has(mapping.predecessors):
                self._link_dependencies(df, mapping, activities_to_create, summary)

            self.schedule.status = JobStatus.COMPLETED
            self.schedule.parse_summary = summary.as_dict()
            self.db.add(self.schedule)
            self.db.commit()
            logger.info(
                "schedule_parsed",
                extra={"schedule_id": str(self.schedule.id), **summary.as_dict()},
            )
            return summary

        except Exception as exc:
            self.db.rollback()
            self._fail_schedule(str(exc))
            if isinstance(exc, ScheduleParserError):
                raise
            raise ScheduleParserError(
                f"Failed to process schedule data: {exc}"
            ) from exc

    # ---------------------------------------------------------------- linking

    @staticmethod
    def _link_parents(activities: list[Activity], summary: ParseSummary) -> None:
        """Attach each activity to its nearest existing WBS ancestor.

        Walking up rather than looking only at the immediate parent matters:
        exports that list only leaf rows with full dotted paths have no row at
        ``1.2`` for a ``1.2.3`` to hang off. Taking the immediate parent alone
        leaves such a node with no parent, and it then surfaces as a top-level
        root in the tree next to genuine L1 nodes -- a flat tree presented as a
        hierarchy. Each relink is counted so the gap is visible.
        """
        by_path = {a.wbs_path: a for a in activities if a.wbs_path}
        for activity in activities:
            if not activity.wbs_path:
                continue
            parts = activity.wbs_path.split(".")
            for depth in range(len(parts) - 1, 0, -1):
                ancestor = by_path.get(".".join(parts[:depth]))
                if ancestor is not None and ancestor.id != activity.id:
                    activity.parent_id = ancestor.id
                    if depth != len(parts) - 1:
                        summary.parents_relinked_to_ancestor += 1
                        summary.warn(
                            f"Activity '{activity.activity_code}' at WBS "
                            f"'{activity.wbs_path}' has no row at "
                            f"'{'.'.join(parts[:-1])}'; it was attached to "
                            f"'{ancestor.wbs_path}' instead."
                        )
                    break

    def _link_dependencies(
        self,
        df: pd.DataFrame,
        mapping: ScheduleColumnMapping,
        activities: list[Activity],
        summary: ParseSummary,
    ) -> None:
        code_to_act = {a.activity_code: a for a in activities}
        deps_to_create: list[ActivityDependency] = []
        edges: dict[str, set[str]] = {a.activity_code: set() for a in activities}
        # A predecessor cell like "B1, B1FS" names the same edge twice; without
        # this any consumer counting predecessors double-counts.
        seen_edges: set[tuple[str, str, str]] = set()

        for index, row in df.iterrows():
            preds = row[mapping.predecessors]
            if pd.isna(preds):
                continue

            successor_code = str(row[mapping.activity_code]).strip()
            successor_act = code_to_act.get(successor_code)
            if successor_act is None:
                continue

            for p_str in (p.strip() for p in str(preds).split(",")):
                if not p_str:
                    continue

                pred_code, dtype, lag = _parse_dependency(p_str)
                pred_act = code_to_act.get(pred_code)
                if pred_act is None:
                    # Also try the cell verbatim: an activity code that
                    # genuinely ends in FS/SS/FF/SF is mis-split by the
                    # relationship-type group.
                    pred_act = code_to_act.get(p_str)
                    if pred_act is not None:
                        pred_code, dtype, lag = (
                            p_str, DependencyType.FINISH_TO_START, 0.0
                        )

                if pred_act is None:
                    summary.predecessors_unresolved += 1
                    summary.warn(
                        f"Activity '{successor_code}' lists predecessor "
                        f"'{p_str}', which matches no activity in this file. "
                        f"The dependency was not created."
                    )
                    continue

                if pred_act.id == successor_act.id:
                    raise ScheduleParserError(
                        f"Activity '{successor_code}' lists itself as a predecessor."
                    )

                key = (pred_code, successor_code, str(dtype))
                if key in seen_edges:
                    summary.dependencies_duplicate += 1
                    continue
                seen_edges.add(key)

                edges[pred_code].add(successor_code)
                deps_to_create.append(
                    ActivityDependency(
                        schedule_id=self.schedule.id,
                        predecessor_id=pred_act.id,
                        successor_id=successor_act.id,
                        dependency_type=dtype,
                        lag=lag,
                    )
                )

        _assert_acyclic(edges)
        self.db.add_all(deps_to_create)
        summary.dependencies_created = len(deps_to_create)
        if summary.dependencies_duplicate:
            summary.warn(
                f"{summary.dependencies_duplicate} duplicate dependency "
                f"reference(s) were collapsed."
            )

    # ------------------------------------------------------------------ fail

    def _fail_schedule(self, error: str | None = None) -> None:
        """Mark the schedule FAILED, never masking the original error.

        This runs from inside an ``except`` block, so a failure here would
        replace the exception the caller needs to see with a database error
        about the bookkeeping.
        """
        try:
            self.schedule.status = JobStatus.FAILED
            if error:
                self.schedule.parse_summary = {"error": error[:2000]}
            self.db.add(self.schedule)
            self.db.commit()
        except Exception:  # noqa: BLE001
            self.db.rollback()
            logger.exception(
                "schedule_fail_status_not_recorded",
                extra={"schedule_id": str(self.schedule.id)},
            )
