import uuid
from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.core.constants import ActivityStatus
from app.models.progress import ActualProgress
from app.models.schedule import Activity
from app.models.user import User
from app.schemas.progress import ActualProgressCreate, ActivityProgressRollup
from app.schemas.analytics import SCurvePoint, AnalyticsSummary

class ProgressService:
    def __init__(self, db: Session):
        self.db = db

    def record_progress(
        self,
        activity_id: uuid.UUID,
        payload: ActualProgressCreate,
        current_user: User
    ) -> ActualProgress:
        activity = self.db.execute(
            select(Activity).where(Activity.id == activity_id)
        ).scalar_one_or_none()
        
        if not activity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activity not found")
            
        # Check if an entry for this date already exists
        existing = self.db.execute(
            select(ActualProgress).where(
                ActualProgress.activity_id == activity_id,
                ActualProgress.reporting_date == payload.reporting_date
            )
        ).scalar_one_or_none()
        
        if existing:
            existing.actual_quantity = payload.actual_quantity
            existing.percent_complete = payload.percent_complete
            existing.actual_start = payload.actual_start
            existing.actual_finish = payload.actual_finish
            existing.status = payload.status
            existing.notes = payload.notes
            existing.reported_by_id = current_user.id
            progress = existing
        else:
            progress = ActualProgress(
                activity_id=activity_id,
                reporting_date=payload.reporting_date,
                actual_quantity=payload.actual_quantity,
                percent_complete=payload.percent_complete,
                actual_start=payload.actual_start,
                actual_finish=payload.actual_finish,
                status=payload.status,
                notes=payload.notes,
                reported_by_id=current_user.id
            )
            self.db.add(progress)
            
        self.db.commit()
        self.db.refresh(progress)
        return progress

    def get_progress_history(self, activity_id: uuid.UUID) -> list[ActualProgress]:
        return list(self.db.execute(
            select(ActualProgress)
            .where(ActualProgress.activity_id == activity_id)
            .order_by(ActualProgress.reporting_date.desc())
        ).scalars())

    def get_project_rollup(self, schedule_id: uuid.UUID) -> list[ActivityProgressRollup]:
        # 1. Fetch all activities for the schedule
        activities = list(self.db.execute(
            select(Activity).where(Activity.schedule_id == schedule_id)
        ).scalars())
        
        if not activities:
            return []

        # 2. Fetch the LATEST progress entry per activity
        # (For a real system, we'd do a DISTINCT ON or window function. Using python dict here for simplicity)
        progress_entries = list(self.db.execute(
            select(ActualProgress)
            .join(Activity)
            .where(Activity.schedule_id == schedule_id)
            .order_by(ActualProgress.reporting_date.asc())
        ).scalars())
        
        latest_progress = {}
        for p in progress_entries:
            latest_progress[p.activity_id] = p
            
        # Build tree relationships
        children_map = {a.id: [] for a in activities}
        act_map = {a.id: a for a in activities}
        
        for a in activities:
            if a.parent_id and a.parent_id in children_map:
                children_map[a.parent_id].append(a.id)

        # Bottom-up calculation
        def calculate_node(node_id: uuid.UUID) -> tuple[float, float, bool]:
            # Returns (weighted_completion_sum, total_weight, is_delayed)
            act = act_map[node_id]
            children = children_map[node_id]
            
            if not children:
                # Leaf node
                prog = latest_progress.get(node_id)
                comp = 0.0
                delayed = False
                weight = act.budgeted_quantity if act.budgeted_quantity else 1.0
                
                if prog:
                    if act.budgeted_quantity and prog.actual_quantity:
                        comp = min(1.0, prog.actual_quantity / act.budgeted_quantity)
                    elif prog.percent_complete is not None:
                        comp = prog.percent_complete / 100.0
                    elif prog.status == ActivityStatus.COMPLETED:
                        comp = 1.0
                    
                    if act.planned_finish and prog.actual_finish and prog.actual_finish > act.planned_finish:
                        delayed = True
                    elif act.planned_finish and prog.status != ActivityStatus.COMPLETED and date.today() > act.planned_finish:
                        delayed = True
                else:
                    if act.planned_finish and date.today() > act.planned_finish:
                        delayed = True
                        
                return (comp * weight, weight, delayed)
                
            # Parent node
            total_sum = 0.0
            total_w = 0.0
            any_delayed = False
            for c_id in children:
                c_sum, c_w, c_del = calculate_node(c_id)
                total_sum += c_sum
                total_w += c_w
                any_delayed = any_delayed or c_del
                
            return (total_sum, total_w, any_delayed)

        rollups = []
        for a in activities:
            c_sum, c_w, delayed = calculate_node(a.id)
            comp_pct = (c_sum / c_w) if c_w > 0 else 0.0
            
            prog = latest_progress.get(a.id)
            status = prog.status if prog else ActivityStatus.NOT_STARTED
            
            rollups.append(ActivityProgressRollup(
                activity_id=a.id,
                activity_code=a.activity_code,
                name=a.name,
                wbs_path=a.wbs_path,
                level=a.level,
                completion_percentage=comp_pct * 100.0,
                status=status,
                is_delayed=delayed
            ))
            
        return sorted(rollups, key=lambda x: x.wbs_path)

    def generate_s_curve(self, schedule_id: uuid.UUID) -> list[SCurvePoint]:
        # For simplicity, returning a mock or basic calculated S-curve
        # A real S-curve groups by week/month and aggregates planned % vs actual %
        return [
            SCurvePoint(reporting_date=date(2026, 1, 1), planned_percentage=10.0, actual_percentage=8.0),
            SCurvePoint(reporting_date=date(2026, 2, 1), planned_percentage=30.0, actual_percentage=25.0),
            SCurvePoint(reporting_date=date(2026, 3, 1), planned_percentage=60.0, actual_percentage=55.0),
        ]
        
    def get_summary(self, schedule_id: uuid.UUID) -> AnalyticsSummary:
        rollups = self.get_project_rollup(schedule_id)
        if not rollups:
            return AnalyticsSummary(
                total_activities=0, completed_activities=0, delayed_activities=0,
                overall_completion_percentage=0.0, schedule_variance=0.0
            )
            
        leaves = [r for r in rollups if not any(c.wbs_path.startswith(f"{r.wbs_path}.") for c in rollups)]
        if not leaves:
            leaves = rollups
            
        total = len(leaves)
        completed = sum(1 for r in leaves if r.status == ActivityStatus.COMPLETED)
        delayed = sum(1 for r in leaves if r.is_delayed)
        
        # Get L1 overall completion
        l1s = [r for r in rollups if r.level == 1]
        overall = sum(r.completion_percentage for r in l1s) / len(l1s) if l1s else 0.0
        
        return AnalyticsSummary(
            total_activities=total,
            completed_activities=completed,
            delayed_activities=delayed,
            overall_completion_percentage=overall,
            schedule_variance=overall - 100.0 # simplified logic
        )
