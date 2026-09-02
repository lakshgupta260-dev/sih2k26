"""The rule-based forecast, tested as arithmetic.

Each case is one whose answer can be worked out by hand, because that is the
whole point of this tier: if a planner cannot check it, it is not doing its
job.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.core.constants import ActivityStatus, RiskLevel
from app.ml import baseline
from app.ml.features import FEATURE_NAMES, ActivityFeatures

BANDS = {"medium": 0.35, "high": 0.60, "critical": 0.80}


def _row(**overrides) -> ActivityFeatures:
    """A feature row with everything unset, then the fields a case needs."""
    values = {name: 0.0 for name in FEATURE_NAMES}
    values.update(overrides.pop("values", {}))
    row = ActivityFeatures(
        activity_id=uuid.uuid4(),
        activity_code=overrides.pop("activity_code", "A100"),
        name=overrides.pop("name", "Trenching"),
        wbs_path=overrides.pop("wbs_path", "1.1"),
        values=values,
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def _forecast(row, as_of=date(2026, 3, 1)):
    return baseline.forecast(row, as_of=as_of, **BANDS)


# ------------------------------------------------------------- no plan dates

def test_an_activity_with_no_planned_finish_gets_no_forecast():
    """Nothing to be late against, so nothing is asserted."""
    result = _forecast(_row(planned_finish=None))
    assert result.probability == 0.0
    assert result.predicted_late is False
    assert result.forecast_finish is None
    assert any("no finish date" in c for c in result.caveats)


# ------------------------------------------------------------------ complete

def test_a_completed_activity_is_judged_on_its_actual_finish():
    late = _forecast(_row(
        planned_finish=date(2026, 2, 1), actual_finish=date(2026, 2, 20),
        completed_fraction=1.0, status=ActivityStatus.COMPLETED,
    ))
    assert late.predicted_late is True
    assert late.probability == 1.0
    assert late.forecast_slip_days == 19
    assert late.risk_level == RiskLevel.CRITICAL

    early = _forecast(_row(
        planned_finish=date(2026, 2, 28), actual_finish=date(2026, 2, 1),
        completed_fraction=1.0, status=ActivityStatus.COMPLETED,
    ))
    assert early.predicted_late is False
    assert early.probability == 0.0
    assert early.risk_level == RiskLevel.LOW


# ---------------------------------------------------------------- rate maths

def test_a_rate_short_of_what_is_required_forecasts_a_slip():
    """50% done with 20 days left, achieving 1%/day: the remaining 50% needs
    50 days, so the finish lands 30 days late."""
    row = _row(
        planned_finish=date(2026, 3, 21),
        completed_fraction=0.5,
        achieved_rate=0.01,
        required_rate=0.025,
        days_remaining=20,
        report_count=4,
        budgeted_quantity=1000.0,
        uom="m",
        values={"planned_duration_days": 80.0, "progress_deficit": -0.2},
    )
    result = _forecast(row)
    assert result.forecast_finish == date(2026, 4, 20)
    assert result.forecast_slip_days == 30
    assert result.predicted_late is True
    assert result.probability > BANDS["medium"]
    # The explanation states the arithmetic in the plan's own units.
    detail = result.drivers[0]["detail"]
    assert "m/day" in detail
    assert "500 m remaining" in detail


def test_a_rate_comfortably_ahead_forecasts_an_early_finish():
    row = _row(
        planned_finish=date(2026, 3, 31),
        completed_fraction=0.5,
        achieved_rate=0.05,
        required_rate=0.0167,
        days_remaining=30,
        report_count=5,
        values={"planned_duration_days": 60.0},
    )
    result = _forecast(row)
    assert result.forecast_slip_days < 0
    assert result.predicted_late is False
    assert result.risk_level == RiskLevel.LOW


def test_running_exactly_on_pace_is_uncertain_rather_than_safe():
    """No float left means a single bad day misses the date, so this must not
    come back as low risk."""
    row = _row(
        planned_finish=date(2026, 3, 31),
        completed_fraction=0.5,
        achieved_rate=0.0167,
        required_rate=0.0167,
        days_remaining=30,
        report_count=5,
    )
    result = _forecast(row)
    assert 0.2 < result.probability < 0.6


def test_reported_but_unmoving_progress_is_high_risk():
    row = _row(
        planned_finish=date(2026, 3, 31),
        completed_fraction=0.4,
        achieved_rate=0.0,
        required_rate=0.02,
        days_remaining=30,
        report_count=6,
    )
    result = _forecast(row)
    assert result.probability >= 0.85
    assert result.forecast_finish is None
    assert any(d["factor"] == "no measurable progress" for d in result.drivers)


# ------------------------------------------------------------------- overdue

def test_past_the_planned_finish_with_work_left_is_critical():
    row = _row(
        planned_finish=date(2026, 2, 1),
        completed_fraction=0.7,
        achieved_rate=0.01,
        days_remaining=-28,
        report_count=8,
    )
    result = _forecast(row)
    assert result.probability == 1.0
    assert result.risk_level == RiskLevel.CRITICAL
    # 30% left at 1%/day = 30 days from 1 Mar = 31 Mar, 58 days past 1 Feb.
    assert result.forecast_finish == date(2026, 3, 31)
    assert result.forecast_slip_days == 58


def test_overdue_with_no_measurable_rate_leaves_the_date_blank():
    """The overdue days are a floor, not a projection, and it says so."""
    row = _row(
        planned_finish=date(2026, 2, 1), completed_fraction=0.1,
        achieved_rate=None, days_remaining=-28,
    )
    result = _forecast(row)
    assert result.forecast_finish is None
    assert result.forecast_slip_days == 28
    assert any("not a forecast" in c for c in result.caveats)


# --------------------------------------------------------------- not started

def test_an_activity_that_never_started_carries_its_late_start_forward():
    row = _row(
        planned_start=date(2026, 2, 1),
        planned_finish=date(2026, 4, 1),
        report_count=0,
        days_remaining=31,
        values={"planned_duration_days": 59.0},
    )
    result = _forecast(row)
    assert result.forecast_slip_days == 28
    assert result.forecast_finish == date(2026, 4, 29)
    assert any(d["factor"] == "not started" for d in result.drivers)
    assert any("keeps its planned duration" in c for c in result.caveats)


# ------------------------------------------------------------- one report only

def test_a_single_report_is_a_plan_comparison_and_says_so():
    row = _row(
        planned_finish=date(2026, 3, 31),
        completed_fraction=0.1,
        achieved_rate=None,
        days_remaining=30,
        report_count=1,
        values={"progress_deficit": -0.4, "planned_percent_complete": 0.5},
    )
    result = _forecast(row)
    assert result.forecast_finish is None
    assert any("no rate could be measured" in c for c in result.caveats)
    assert result.probability > BANDS["medium"]


# ------------------------------------------------------------- adjustments

def test_predecessor_slip_and_stale_reporting_raise_the_probability():
    base_kwargs = dict(
        planned_finish=date(2026, 3, 31), completed_fraction=0.5,
        achieved_rate=0.02, required_rate=0.0167, days_remaining=30,
        report_count=5,
    )
    plain = _forecast(_row(**base_kwargs))
    aggravated = _forecast(_row(
        **base_kwargs,
        max_predecessor_slip=12,
        values={"days_since_last_report": 30.0},
    ))
    assert aggravated.probability > plain.probability
    factors = {d["factor"] for d in aggravated.drivers}
    assert "predecessor slip" in factors
    assert "stale reporting" in factors
    assert any("may be out of date" in c for c in aggravated.caveats)


def test_probability_never_leaves_the_unit_interval():
    row = _row(
        planned_finish=date(2026, 3, 31), completed_fraction=0.01,
        achieved_rate=0.0001, required_rate=0.5, days_remaining=2,
        report_count=9, max_predecessor_slip=90,
        values={"days_since_last_report": 120.0, "is_monsoon_finish": 1.0},
    )
    result = _forecast(row)
    assert 0.0 <= result.probability <= 1.0


# ------------------------------------------------------------- risk banding

@pytest.mark.parametrize(
    "probability,expected",
    [
        (0.00, RiskLevel.LOW),
        (0.34, RiskLevel.LOW),
        (0.35, RiskLevel.MEDIUM),
        (0.59, RiskLevel.MEDIUM),
        (0.60, RiskLevel.HIGH),
        (0.79, RiskLevel.HIGH),
        (0.80, RiskLevel.CRITICAL),
        (1.00, RiskLevel.CRITICAL),
    ],
)
def test_risk_bands_are_inclusive_at_the_lower_bound(probability, expected):
    assert baseline.risk_level(probability, 0.35, 0.60, 0.80) == expected
