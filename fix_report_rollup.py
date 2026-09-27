import re

with open('backend/app/services/reporting.py', 'r', encoding='utf-8') as f:
    code = f.read()

# I will replace the block defining latest_progress and the _status_of/_percent_of functions.

replacement = '''
        from app.services.progress import ProgressService
        from app.models.project import Project
        
        project = self.db.get(Project, project_id)
        schedule = self.db.scalar(
            select(Schedule).where(Schedule.project_id == project_id).order_by(Schedule.created_at.desc())
        )
        
        rollup_map = {}
        if project and schedule:
            try:
                rollups = ProgressService(self.db).get_project_rollup(project, schedule.id)
                rollup_map = {r.activity_id: r for r in rollups}
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to fetch rollup for report: {e}")

        # Real delay-risk data lives in delay_predictions
        predictions_by_activity: dict[uuid.UUID, DelayPrediction] = {}
        if activity_ids:
            rows = self.db.scalars(
                select(DelayPrediction).where(DelayPrediction.activity_id.in_(activity_ids))
            ).all()
            predictions_by_activity = {p.activity_id: p for p in rows}

        today = date.today()

        def _status_of(activity: Activity) -> str:
            r = rollup_map.get(activity.id)
            return r.status if r else ActivityStatus.NOT_STARTED

        def _percent_of(activity: Activity) -> float:
            r = rollup_map.get(activity.id)
            return float(r.percent_complete) if r else 0.0

        def _is_delayed(activity: Activity) -> bool:
            r = rollup_map.get(activity.id)
            return r.is_delayed if r else False
'''

# Find the start and end of the block to replace
start_str = '        latest_progress: dict[uuid.UUID, ActualProgress] = {}'
end_str = '        def _is_delayed(activity: Activity) -> bool:\n            progress = latest_progress.get(activity.id)\n            if activity.planned_finish is None:\n                return False\n            if progress is not None and progress.actual_finish is not None:\n                return progress.actual_finish > activity.planned_finish\n            status = _status_of(activity)\n            return status != ActivityStatus.COMPLETED and activity.planned_finish < today'

import sys
if start_str not in code:
    print("Start string not found")
    sys.exit(1)
if end_str not in code:
    print("End string not found")
    sys.exit(1)

code = code[:code.find(start_str)] + replacement.lstrip() + code[code.find(end_str) + len(end_str):]

with open('backend/app/services/reporting.py', 'w', encoding='utf-8') as f:
    f.write(code)
