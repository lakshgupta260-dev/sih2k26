"""Analytics response shapes.

Optional fields here are load-bearing. ``None`` means "not measurable from the
data present", which is a different statement from ``0.0`` and must not be
collapsed into it -- a client rendering 0% behind schedule when the plan simply
carries no dates would be reporting a measurement that was never made.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class SCurvePoint(BaseModel):
    reporting_date: date
    planned_percentage: float = Field(
        description="Cumulative planned completion, weighted by budgeted quantity."
    )
    actual_percentage: float | None = Field(
        default=None,
        description=(
            "Cumulative reported completion, or null for samples outside the "
            "reported window. Null is not zero: it means nothing was measured "
            "at that date."
        ),
    )


class AnalyticsSummary(BaseModel):
    as_of: date = Field(description="Date the figures were evaluated at.")
    total_activities: int
    leaf_activities: int = Field(
        description="Activities with no children -- the ones work is booked against."
    )
    completed_activities: int
    delayed_activities: int
    overall_completion_percentage: float = Field(
        description="Quantity-weighted roll-up across the whole WBS."
    )
    planned_completion_percentage: float | None = Field(
        default=None,
        description=(
            "Where the plan says we should be as of `as_of`; null if the plan "
            "carries no dates."
        ),
    )
    schedule_variance: float | None = Field(
        default=None,
        description=(
            "actual minus planned completion, in percentage points. Negative is "
            "behind plan. Null when the plan carries no dates to compare against."
        ),
    )
    activities_with_progress: int = Field(
        description="Leaf activities that have at least one progress record."
    )
    last_reported_on: date | None = Field(
        default=None, description="Most recent reporting date on record."
    )
