import io
import re
import uuid
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.core.constants import JobStatus, Discipline, DependencyType
from app.models.schedule import Schedule, Activity, ActivityDependency
from app.schemas.schedule import ScheduleColumnMapping
from app.core.exceptions import UnprocessableFileError


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
}


def _discipline(raw: str | None) -> Discipline | None:
    if not raw or pd.isna(raw):
        return None
    key = str(raw).strip().lower()
    try:
        return Discipline(str(raw).strip().upper().replace(" ", "_"))
    except ValueError:
        return ALIASES.get(key, Discipline.OTHER)


def _assert_acyclic(edges: dict[str, set[str]]) -> None:
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {node: WHITE for node in edges}
    
    def visit(node: str, path: list[str]) -> None:
        colour[node] = GREY
        for nxt in edges.get(node, ()):
            if colour.get(nxt) == GREY:
                chain = " -> ".join(path[path.index(nxt):] + [nxt])
                raise ScheduleParserError(f"Circular dependency: {chain}")
            if colour.get(nxt, WHITE) == WHITE:
                visit(nxt, path + [nxt])
        colour[node] = BLACK

    for node in list(edges):
        if colour.get(node, WHITE) == WHITE:
            visit(node, [node])


# Predecessor cell formats seen in real exports:
#   "A1010"          plain code, implicit finish-to-start, no lag
#   "A1010FS+3"      Primavera, no separator
#   "A1010 FS+3"     with a separator
#   "A1010SS-2"      start-to-start, negative lag
#   "12FS+3 days"    MS Project, with a unit suffix
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
        (?:d|day|days|h|hr|hrs|hour|hours|w|wk|week|weeks)?   # unit suffix
        \s*$""",
    re.IGNORECASE | re.VERBOSE,
)


def _parse_dependency(dep_str: str) -> tuple[str, DependencyType, int]:
    """Split a predecessor cell into (activity_code, relationship, lag).

    An unrecognised cell is treated as a bare activity code with an implicit
    finish-to-start relationship and no lag, which is how a plain code column
    behaves.
    """
    dep_str = str(dep_str).strip()
    match = _DEPENDENCY_RE.match(dep_str)
    if not match:
        return dep_str, DependencyType.FINISH_TO_START, 0

    pred_code = match.group("code").strip()
    raw_type = match.group("type")
    lag_str = match.group("lag")

    lag = 0
    if lag_str:
        try:
            lag = int(float(lag_str.replace(" ", "")))
        except ValueError:
            lag = 0

    try:
        dtype = DependencyType(raw_type.upper()) if raw_type else DependencyType.FINISH_TO_START
    except ValueError:
        dtype = DependencyType.FINISH_TO_START

    return pred_code, dtype, lag


class ScheduleParser:
    """Parses Excel/CSV schedules and maps them to our Activity models."""

    def __init__(self, db: Session, schedule: Schedule) -> None:
        self.db = db
        self.schedule = schedule

    def parse_file(self, file_content: bytes, filename: str, mapping: ScheduleColumnMapping) -> None:
        """Parses the file, extracts activities, and constructs the hierarchy."""
        try:
            str_cols = {c: str for c in (mapping.activity_code, mapping.wbs_path, mapping.predecessors) if c}
            if filename.endswith(".csv"):
                df = pd.read_csv(io.BytesIO(file_content), dtype=str_cols)
            elif filename.endswith((".xls", ".xlsx")):
                df = pd.read_excel(io.BytesIO(file_content), engine="openpyxl", dtype=str_cols)
            else:
                raise ScheduleParserError("Unsupported file format. Must be .csv, .xls, or .xlsx")
        except Exception as e:
            self._fail_schedule()
            raise ScheduleParserError(f"Failed to read file: {e}")

        required_cols = [mapping.activity_code, mapping.name]
        for col in required_cols:
            if col not in df.columns:
                self._fail_schedule()
                raise ScheduleParserError(f"Required column '{col}' not found in the file.")

        try:
            df = df.dropna(subset=[mapping.activity_code, mapping.name])
            
            activities_to_create = []
            seen_codes = set()
            
            for index, row in df.iterrows():
                row_num = index + 2  # Approximate Excel row (1-indexed + header)
                
                act_code = str(row[mapping.activity_code]).strip()
                if not act_code or pd.isna(row[mapping.activity_code]):
                    continue
                if act_code in seen_codes:
                    raise ScheduleParserError(f"Row {row_num}: Duplicate activity code '{act_code}'")
                seen_codes.add(act_code)
                
                name = str(row[mapping.name]).strip()
                
                wbs_path = str(row[mapping.wbs_path]).strip() if mapping.wbs_path and mapping.wbs_path in df.columns and pd.notna(row[mapping.wbs_path]) else ""
                level = 1
                if mapping.level and mapping.level in df.columns and pd.notna(row[mapping.level]):
                    try:
                        level = int(float(row[mapping.level]))
                        if not (1 <= level <= 6):
                            raise ScheduleParserError(f"Row {row_num}: Level must be between 1 and 6, got {level}")
                    except ValueError:
                        raise ScheduleParserError(f"Row {row_num}: Cannot parse level '{row[mapping.level]}'")
                
                disc_val = row[mapping.discipline] if mapping.discipline and mapping.discipline in df.columns else None
                discipline = _discipline(disc_val)
                
                start_val = row[mapping.planned_start] if mapping.planned_start and mapping.planned_start in df.columns else None
                finish_val = row[mapping.planned_finish] if mapping.planned_finish and mapping.planned_finish in df.columns else None
                
                start_dt = pd.to_datetime(start_val, errors="coerce") if pd.notna(start_val) else None
                finish_dt = pd.to_datetime(finish_val, errors="coerce") if pd.notna(finish_val) else None
                planned_start = start_dt.date() if (start_dt is not None and pd.notna(start_dt)) else None
                planned_finish = finish_dt.date() if (finish_dt is not None and pd.notna(finish_dt)) else None
                
                try:
                    budgeted_qty = float(row[mapping.budgeted_quantity]) if mapping.budgeted_quantity and mapping.budgeted_quantity in df.columns and pd.notna(row[mapping.budgeted_quantity]) else None
                except (ValueError, TypeError):
                    budgeted_qty = None
                uom = str(row[mapping.uom]).strip() if mapping.uom and mapping.uom in df.columns and pd.notna(row[mapping.uom]) else None
                
                act = Activity(
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
                activities_to_create.append(act)

            self.db.add_all(activities_to_create)
            self.db.flush()

            if mapping.wbs_path:
                wbs_to_act = {a.wbs_path: a for a in activities_to_create if a.wbs_path}
                for a in activities_to_create:
                    if not a.wbs_path:
                        continue
                    parts = a.wbs_path.split(".")
                    if len(parts) > 1:
                        parent_path = ".".join(parts[:-1])
                        parent_act = wbs_to_act.get(parent_path)
                        if parent_act:
                            a.parent_id = parent_act.id
            
            if mapping.predecessors and mapping.predecessors in df.columns:
                code_to_act = {a.activity_code: a for a in activities_to_create}
                deps_to_create = []
                edges = {a.activity_code: set() for a in activities_to_create}
                
                for index, row in df.iterrows():
                    preds = row[mapping.predecessors]
                    if pd.isna(preds):
                        continue
                    
                    successor_code = str(row[mapping.activity_code]).strip()
                    successor_act = code_to_act.get(successor_code)
                    if not successor_act:
                        continue
                        
                    pred_strings = [p.strip() for p in str(preds).split(",")]
                    for p_str in pred_strings:
                        if not p_str:
                            continue
                        
                        pred_code, dtype, lag = _parse_dependency(p_str)
                        pred_act = code_to_act.get(pred_code)
                        if pred_act:
                            if pred_act.id == successor_act.id:
                                raise ScheduleParserError(f"Activity '{successor_code}' lists itself as a predecessor.")
                                
                            edges[pred_code].add(successor_code)
                            
                            deps_to_create.append(
                                ActivityDependency(
                                    schedule_id=self.schedule.id,
                                    predecessor_id=pred_act.id,
                                    successor_id=successor_act.id,
                                    dependency_type=dtype,
                                    lag=lag
                                )
                            )
                
                _assert_acyclic(edges)
                self.db.add_all(deps_to_create)

            self.schedule.status = JobStatus.COMPLETED
            self.db.add(self.schedule)
            self.db.commit()

        except Exception as e:
            self.db.rollback()
            self._fail_schedule()
            if isinstance(e, ScheduleParserError):
                raise e
            raise ScheduleParserError(f"Failed to process schedule data: {e}")

    def _fail_schedule(self) -> None:
        self.schedule.status = JobStatus.FAILED
        self.db.add(self.schedule)
        self.db.commit()
