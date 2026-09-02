from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field

class SCurvePoint(BaseModel):
    reporting_date: date
    planned_percentage: float
    actual_percentage: float

class AnalyticsSummary(BaseModel):
    total_activities: int
    completed_activities: int
    delayed_activities: int
    overall_completion_percentage: float
    schedule_variance: float  # Difference between planned and actual
