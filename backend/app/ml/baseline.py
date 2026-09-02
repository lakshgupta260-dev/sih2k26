"""Rule-based delay forecasting: arithmetic a planner can check by hand.

This is the tier that always works. It needs no training data, no history and
no model artefact, so it produces a usable forecast on the first day of a
project -- exactly when a trained model has nothing to learn from.

It answers one question: *at the rate this activity has actually been
progressing, will it reach 100% by its planned finish?* Everything else --
predecessor slip, a stalled reporting cadence, a plan with no dates -- is
layered on as an explicit adjustment with a stated reason.

The output is deliberately the same shape as the model's, so a caller never
has to branch on which tier produced it, and the ``method`` field always says
which one did.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.core.constants import RiskLevel
from app.ml.features import ActivityFeatures

# A reporting gap longer than this on a started, unfinished activity is itself
# a warning sign: on a job filing daily reports, silence usually means the
# front has stopped rather than that the paperwork is late.
_STALE_REPORT_DAYS = 14


@dataclass(slots=True)
class Forecast:
    """A delay forecast with the reasoning that produced it."""

    probability: float
    predicted_late: bool
    forecast_finish: date | None
    forecast_slip_days: int | None
    risk_level: RiskLevel
    drivers: list[dict[str, object]]
    caveats: list[str]

    def as_explanation(self) -> dict[str, object]:
        return {
            "drivers": self.drivers,
            "caveats": self.caveats,
            "forecast_slip_days": self.forecast_slip_days,
        }


def risk_level(
    probability: float, medium: float, high: float, critical: float
) -> RiskLevel:
    if probability >= critical:
        return RiskLevel.CRITICAL
    if probability >= high:
        return RiskLevel.HIGH
    if probability >= medium:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def forecast(
    row: ActivityFeatures,
    *,
    as_of: date,
    medium: float,
    high: float,
    critical: float,
) -> Forecast:
    """Forecast one activity from its measured rate of progress."""
    drivers: list[dict[str, object]] = []
    caveats: list[str] = []

    # ---------------------------------------------------------- no plan dates
    if row.planned_finish is None:
        caveats.append(
            "The ingested plan gives this activity no finish date, so there is "
            "nothing to be late against. No forecast is made."
        )
        return Forecast(
            probability=0.0,
            predicted_late=False,
            forecast_finish=None,
            forecast_slip_days=None,
            risk_level=RiskLevel.LOW,
            drivers=drivers,
            caveats=caveats,
        )

    # ------------------------------------------------------------- completed
    if row.completed_fraction >= 1.0:
        late = row.actual_finish is not None and row.actual_finish > row.planned_finish
        slip = (
            (row.actual_finish - row.planned_finish).days
            if row.actual_finish and late
            else 0
        )
        drivers.append({
            "factor": "already complete",
            "detail": (
                f"Reported complete on {row.actual_finish.isoformat()}"
                if row.actual_finish else "Reported complete."
            ),
            "direction": "increases risk" if late else "resolved",
        })
        return Forecast(
            probability=1.0 if late else 0.0,
            predicted_late=late,
            forecast_finish=row.actual_finish,
            forecast_slip_days=slip if late else 0,
            risk_level=RiskLevel.CRITICAL if late else RiskLevel.LOW,
            drivers=drivers,
            caveats=caveats,
        )

    remaining_fraction = max(0.0, 1.0 - row.completed_fraction)
    days_left = row.days_remaining if row.days_remaining is not None else 0

    # ------------------------------------------- already past planned finish
    if days_left < 0:
        overdue = -days_left
        drivers.append({
            "factor": "past the planned finish",
            "detail": (
                f"The planned finish was {row.planned_finish.isoformat()}, "
                f"{overdue} days ago, with "
                f"{remaining_fraction * 100:.0f}% of the work outstanding."
            ),
            "direction": "increases risk",
        })
        slip: int | None = overdue
        forecast_finish: date | None = None
        if row.achieved_rate and row.achieved_rate > 0:
            needed = int(round(remaining_fraction / row.achieved_rate))
            forecast_finish = date.fromordinal(as_of.toordinal() + needed)
            slip = (forecast_finish - row.planned_finish).days
            drivers.append({
                "factor": "achieved rate",
                "detail": _rate_sentence(row, needed),
                "direction": "increases risk",
            })
        else:
            caveats.append(
                "No rate of progress could be measured, so the projected "
                "finish date is left blank; the overdue days are a floor, not "
                "a forecast."
            )
        return Forecast(
            probability=1.0,
            predicted_late=True,
            forecast_finish=forecast_finish,
            forecast_slip_days=slip,
            risk_level=RiskLevel.CRITICAL,
            drivers=drivers,
            caveats=caveats,
        )

    # ------------------------------------------------------- not yet started
    if not row.report_count and row.planned_start and as_of > row.planned_start:
        late_start = (as_of - row.planned_start).days
        # A late start eats the float directly: the remaining window is what is
        # left, and the plan assumed the whole duration.
        duration = row.values.get("planned_duration_days", 0.0) or 1.0
        shortfall = late_start / duration
        probability = min(0.95, 0.25 + shortfall)
        drivers.append({
            "factor": "not started",
            "detail": (
                f"Planned to start {late_start} days ago on "
                f"{row.planned_start.isoformat()} with nothing reported. "
                f"That is {shortfall * 100:.0f}% of the planned duration "
                f"already gone."
            ),
            "direction": "increases risk",
        })
        forecast_finish = date.fromordinal(
            row.planned_finish.toordinal() + late_start
        )
        return Forecast(
            probability=probability,
            predicted_late=probability >= 0.5,
            forecast_finish=forecast_finish,
            forecast_slip_days=late_start,
            risk_level=risk_level(probability, medium, high, critical),
            drivers=drivers,
            caveats=[
                "Assumes the activity keeps its planned duration once it "
                "starts, so the slip shown is the late start carried forward."
            ],
        )

    # -------------------------------------------------------- rate arithmetic
    if row.achieved_rate is None:
        # Started but no measurable rate yet -- typically one report only.
        deficit = row.values.get("progress_deficit", 0.0)
        probability = min(0.9, max(0.05, 0.3 - deficit))
        caveats.append(
            "Fewer than two progress reports, so no rate could be measured. "
            "This is a comparison against the plan's expected position, not a "
            "rate-based projection."
        )
        drivers.append({
            "factor": "position against plan",
            "detail": (
                f"Reported {row.completed_fraction * 100:.0f}% complete where "
                f"the plan expects "
                f"{row.values['planned_percent_complete'] * 100:.0f}% by now."
            ),
            "direction": "increases risk" if deficit < 0 else "reduces risk",
        })
        return Forecast(
            probability=probability,
            predicted_late=probability >= 0.5,
            forecast_finish=None,
            forecast_slip_days=None,
            risk_level=risk_level(probability, medium, high, critical),
            drivers=drivers,
            caveats=caveats,
        )

    required = row.required_rate if row.required_rate else 0.0
    if row.achieved_rate <= 0:
        drivers.append({
            "factor": "no measurable progress",
            "detail": (
                "Progress has been reported but the completed figure has not "
                "moved between reports."
            ),
            "direction": "increases risk",
        })
        probability = 0.9
        forecast_finish = None
        slip = None
    else:
        needed_days = remaining_fraction / row.achieved_rate
        forecast_finish = date.fromordinal(as_of.toordinal() + int(round(needed_days)))
        slip = (forecast_finish - row.planned_finish).days
        ratio = row.achieved_rate / required if required > 0 else 3.0
        # Map the rate ratio to a probability. 1.0 means exactly on pace, which
        # is genuinely uncertain rather than safe -- an activity running at
        # precisely the required rate has no float left for a single bad day.
        if ratio >= 1.5:
            probability = 0.05
        elif ratio >= 1.0:
            probability = 0.05 + (1.5 - ratio) * 0.6
        elif ratio >= 0.5:
            probability = 0.35 + (1.0 - ratio) * 0.9
        else:
            probability = min(0.97, 0.8 + (0.5 - ratio) * 0.34)
        drivers.append({
            "factor": "achieved rate against required rate",
            "detail": _rate_sentence(row, int(round(needed_days))),
            "direction": "increases risk" if ratio < 1.0 else "reduces risk",
        })

    # ------------------------------------------------------ adjustments
    if row.max_predecessor_slip and row.max_predecessor_slip > 0:
        probability = min(0.98, probability + 0.10)
        drivers.append({
            "factor": "predecessor slip",
            "detail": (
                f"A predecessor finished {row.max_predecessor_slip} days after "
                f"its planned finish, so this activity started against a "
                f"compressed window."
            ),
            "direction": "increases risk",
        })

    gap = int(row.values.get("days_since_last_report", 0.0))
    if row.report_count and gap > _STALE_REPORT_DAYS:
        probability = min(0.98, probability + 0.08)
        drivers.append({
            "factor": "stale reporting",
            "detail": (
                f"No progress reported for {gap} days. On a job filing regular "
                f"reports, that usually means the front has stopped."
            ),
            "direction": "increases risk",
        })
        caveats.append(
            f"The last report was {gap} days old, so the completion figure "
            f"behind this forecast may be out of date."
        )

    if row.values.get("is_monsoon_finish", 0.0) and row.completed_fraction < 0.9:
        drivers.append({
            "factor": "monsoon finish",
            "detail": (
                "The planned finish falls between June and September, when "
                "productivity on outdoor works typically drops."
            ),
            "direction": "increases risk",
        })

    probability = max(0.0, min(1.0, probability))
    return Forecast(
        probability=probability,
        predicted_late=probability >= 0.5,
        forecast_finish=forecast_finish,
        forecast_slip_days=slip,
        risk_level=risk_level(probability, medium, high, critical),
        drivers=drivers,
        caveats=caveats,
    )


def _rate_sentence(row: ActivityFeatures, needed_days: int) -> str:
    """State the rate arithmetic in the plan's own units where possible."""
    remaining_fraction = max(0.0, 1.0 - row.completed_fraction)
    if row.budgeted_quantity and row.budgeted_quantity > 0 and row.uom:
        unit = row.uom
        remaining_qty = remaining_fraction * row.budgeted_quantity
        rate_qty = (row.achieved_rate or 0.0) * row.budgeted_quantity
        head = (
            f"Achieving about {rate_qty:.1f} {unit}/day with "
            f"{remaining_qty:.0f} {unit} remaining"
        )
    else:
        head = (
            f"Achieving about {(row.achieved_rate or 0.0) * 100:.2f}% per day "
            f"with {remaining_fraction * 100:.0f}% remaining"
        )
    tail = f"needs about {needed_days} days"
    if row.days_remaining is not None:
        tail += f", against {row.days_remaining} days left in the plan"
    return f"{head} {tail}."
