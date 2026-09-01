"""Excel/CSV schedule parsing and hierarchy construction."""
from __future__ import annotations

import io
import uuid
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.core.constants import JobStatus
from app.models.schedule import Schedule, Activity, ActivityDependency
from app.schemas.schedule import ScheduleColumnMapping


from app.core.exceptions import UnprocessableFileError

class ScheduleParserError(UnprocessableFileError):
    pass


class ScheduleParser:
    """Parses Excel/CSV schedules and maps them to our Activity models."""

    def __init__(self, db: Session, schedule: Schedule) -> None:
        self.db = db
        self.schedule = schedule

    def parse_file(self, file_content: bytes, filename: str, mapping: ScheduleColumnMapping) -> None:
        """Parses the file, extracts activities, and constructs the hierarchy."""
        try:
            if filename.endswith(".csv"):
                df = pd.read_csv(io.BytesIO(file_content))
            elif filename.endswith((".xls", ".xlsx")):
                df = pd.read_excel(io.BytesIO(file_content), engine="openpyxl")
            else:
                raise ScheduleParserError("Unsupported file format. Must be .csv, .xls, or .xlsx")
        except Exception as e:
            self._fail_schedule()
            raise ScheduleParserError(f"Failed to read file: {e}")

        # Check required columns exist
        required_cols = [mapping.activity_code, mapping.name]
        for col in required_cols:
            if col not in df.columns:
                self._fail_schedule()
                raise ScheduleParserError(f"Required column '{col}' not found in the file.")

        try:
            # Drop empty rows
            df = df.dropna(subset=[mapping.activity_code, mapping.name])
            
            activities_to_create = []
            
            for index, row in df.iterrows():
                # Extract values using mapping
                act_code = str(row[mapping.activity_code]).strip()
                name = str(row[mapping.name]).strip()
                
                # Optionals
                wbs_path = str(row[mapping.wbs_path]).strip() if mapping.wbs_path and mapping.wbs_path in df.columns and pd.notna(row[mapping.wbs_path]) else ""
                level = int(row[mapping.level]) if mapping.level and mapping.level in df.columns and pd.notna(row[mapping.level]) else 1
                discipline = str(row[mapping.discipline]).strip() if mapping.discipline and mapping.discipline in df.columns and pd.notna(row[mapping.discipline]) else None
                
                start_val = row[mapping.planned_start] if mapping.planned_start and mapping.planned_start in df.columns else None
                finish_val = row[mapping.planned_finish] if mapping.planned_finish and mapping.planned_finish in df.columns else None
                
                planned_start = pd.to_datetime(start_val).date() if pd.notna(start_val) else None
                planned_finish = pd.to_datetime(finish_val).date() if pd.notna(finish_val) else None
                
                budgeted_qty = float(row[mapping.budgeted_quantity]) if mapping.budgeted_quantity and mapping.budgeted_quantity in df.columns and pd.notna(row[mapping.budgeted_quantity]) else None
                uom = str(row[mapping.uom]).strip() if mapping.uom and mapping.uom in df.columns and pd.notna(row[mapping.uom]) else None
                
                # Create activity instances (no DB flush yet to optimize)
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

            # Insert all activities
            self.db.add_all(activities_to_create)
            self.db.flush() # Now they have UUIDs

            # Pass 2: Reconstruct Hierarchy based on wbs_path and level (if applicable)
            # This is a basic implementation assuming wbs_path is like "1", "1.1", "1.1.1"
            # In a real scenario we'd do a more robust string match or rely on parent_id columns
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
            
            # Pass 3: Process Dependencies if provided (e.g. "A1000, A1010" comma separated predecessors)
            if mapping.predecessors and mapping.predecessors in df.columns:
                code_to_act = {a.activity_code: a for a in activities_to_create}
                deps_to_create = []
                for index, row in df.iterrows():
                    preds = row[mapping.predecessors]
                    if pd.isna(preds):
                        continue
                    
                    act_code = str(row[mapping.activity_code]).strip()
                    successor_act = code_to_act.get(act_code)
                    if not successor_act:
                        continue
                        
                    # Split by comma
                    pred_codes = [p.strip() for p in str(preds).split(",")]
                    for pcode in pred_codes:
                        pred_act = code_to_act.get(pcode)
                        if pred_act:
                            deps_to_create.append(
                                ActivityDependency(
                                    schedule_id=self.schedule.id,
                                    predecessor_id=pred_act.id,
                                    successor_id=successor_act.id
                                )
                            )
                
                self.db.add_all(deps_to_create)

            self.schedule.status = JobStatus.COMPLETED
            self.db.add(self.schedule)
            self.db.commit()

        except Exception as e:
            self.db.rollback()
            self._fail_schedule()
            raise ScheduleParserError(f"Failed to process schedule data: {e}")

    def _fail_schedule(self) -> None:
        self.schedule.status = JobStatus.FAILED
        self.db.add(self.schedule)
        self.db.commit()
