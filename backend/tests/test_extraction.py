"""Rule-based extraction: classification and field parsing.

No database. The extraction layer works on plain value objects precisely so it
can be tested this cheaply.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.ai.extraction.base import (
    parse_activity_code,
    parse_chainage,
    parse_date,
    parse_joints,
    parse_percent,
    parse_quantity,
    residual_text,
)
from app.ai.extraction.rules import RuleBasedExtractor, classify_event
from app.ai.schemas import EventType


# ------------------------------------------------------------ classification
@pytest.mark.parametrize(
    "line,expected",
    [
        ("L&B done from 12.0 to 14.5 km completed.", EventType.ACTUAL_FINISH),
        ("RT of jt 340-380 completed, 2 repairs.", EventType.ACTUAL_FINISH),
        ("fdn concreting M-30 commenced today.", EventType.ACTUAL_START),
        ("Trench excavation taken up at KP 5.0-6.0.", EventType.ACTUAL_START),
        ("Cable pulling in progress - 60% achieved.", EventType.PROGRESS_UPDATE),
        ("Spool erection under progress.", EventType.PROGRESS_UPDATE),
    ],
)
def test_actual_events_are_classified(line: str, expected: EventType) -> None:
    event, confidence, _ = classify_event(line)
    assert event == expected
    assert confidence > 0.5


@pytest.mark.parametrize(
    "line",
    [
        "L&B - to be taken up tomorrow.",
        "RT of joints 400 to 440 will be started.",
        "Hydrotest planned for next week.",
        "Backfilling scheduled to commence shortly.",
        "Cable pulling shall be completed by Friday.",
    ],
)
def test_future_intent_is_never_an_actual(line: str) -> None:
    """The single most damaging misclassification in this domain.

    These read exactly like progress. Booking them would move a schedule on
    work that has not happened.
    """
    event, _, reason = classify_event(line)
    assert event == EventType.PLANNED_NOT_ACTUAL, reason


@pytest.mark.parametrize(
    "line",
    [
        "No progress today due to labour unrest.",
        "Trench excavation not started, front not available.",
        "Hydrotest not completed, awaiting clearance.",
        "ROU not handed over, forest clearance pending.",
    ],
)
def test_negation_is_not_an_event(line: str) -> None:
    event, _, _ = classify_event(line)
    assert event == EventType.NONE


@pytest.mark.parametrize(
    "line",
    [
        "Toolbox talk conducted on working at height. 32 nos attended.",
        "Safety induction training conducted for 14 new workmen.",
        "Diesel bowser refilled - 4000 litres received.",
        "Progress review meeting held with client engineer.",
    ],
)
def test_site_administration_is_not_an_event(line: str) -> None:
    event, _, _ = classify_event(line)
    assert event == EventType.NONE


def test_forward_plan_section_switches_every_following_line() -> None:
    """A "Planned for tomorrow" heading changes the meaning of what follows.

    Individual lines under it may carry no future cue of their own.
    """
    dpr = """
    A. WORK EXECUTED TODAY
      1. L&B completed KP 12.000 - 14.500.
    C. PLANNED FOR TOMORROW
      - Trench excavation KP 15.000 - 16.000.
      - Radiography of girth joints J-0400 to J-0440.
    """
    items = RuleBasedExtractor().extract(dpr)
    executed = [i for i in items if i.event_type == EventType.ACTUAL_FINISH]
    planned = [i for i in items if i.event_type == EventType.PLANNED_NOT_ACTUAL]
    assert len(executed) == 1
    assert len(planned) == 2, [i.raw_text for i in items]


# ----------------------------------------------------------------- chainage
@pytest.mark.parametrize(
    "text,expected",
    [
        ("Lowering KP 22.500 - 24.000 done", (22500.0, 24000.0)),
        ("L&B from 22.5 to 24 km", (22500.0, 24000.0)),
        ("backfill ch 22500-24000 complete", (22500.0, 24000.0)),
        ("L&B 22+500 to 24+000 completed", (22500.0, 24000.0)),
        ("padding km 12.0 - 14.5", (12000.0, 14500.0)),
    ],
)
def test_chainage_formats(text: str, expected: tuple[float, float]) -> None:
    chainage = parse_chainage(text)
    assert chainage is not None, text
    assert (chainage.from_m, chainage.to_m) == expected


def test_bare_number_range_is_not_a_chainage() -> None:
    """Without a KP/km/ch marker, "340-380" is far more often a joint band."""
    assert parse_chainage("welding of 340-380 completed") is None


def test_a_date_is_never_read_as_a_chainage() -> None:
    assert parse_chainage("Activity A1010 completed on 12-03-2026.") is None


def test_joint_band_wins_over_chainage() -> None:
    assert parse_chainage("RT of jt 340-380 completed") is None
    joints = parse_joints("RT of jt 340-380 completed")
    assert joints is not None
    assert (joints.from_no, joints.to_no) == (340, 380)


# -------------------------------------------------------------------- joints
@pytest.mark.parametrize(
    "text,expected",
    [
        ("RT of J-0340 to J-0380", (340, 380)),
        ("radiography jt 340-380", (340, 380)),
        ("joints 340 to 380 completed", (340, 380)),
        ("weld no. 340 to 380 done", (340, 380)),
        ("40 nos joints (from 340) coated", (340, 380)),
    ],
)
def test_joint_formats(text: str, expected: tuple[int, int]) -> None:
    joints = parse_joints(text)
    assert joints is not None, text
    assert (joints.from_no, joints.to_no) == expected


# ------------------------------------------------------------------ measures
def test_quantity_ignores_the_chainage_figure() -> None:
    """The bug this guards: "14.5 km" being read as the day's quantity."""
    text = "L&B done from 12.0 to 14.5 km completed. Total 2500 m."
    quantity = parse_quantity(residual_text(text))
    assert quantity == (2500.0, "m")


def test_percent_and_code_and_date() -> None:
    assert parse_percent("60% achieved cumulative") == 60.0
    assert parse_percent("achieved 105%") is None
    assert parse_activity_code("Activity A1010 completed") == "A1010"
    assert parse_date("completed on 12-03-2026") == date(2026, 3, 12)
    assert parse_date("completed on 2026-03-12") == date(2026, 3, 12)


# ----------------------------------------------------------------- overlaps
def test_chainage_overlap_ratio() -> None:
    a = parse_chainage("KP 12.000 - 14.000")
    b = parse_chainage("KP 12.000 - 14.000")
    c = parse_chainage("KP 20.000 - 22.000")
    assert a and b and c
    assert a.overlap_ratio(b) == pytest.approx(1.0)
    assert a.overlap_ratio(c) == pytest.approx(0.0)


def test_extractor_records_provenance() -> None:
    items = RuleBasedExtractor().extract("L&B KP 1.000 - 2.000 completed.", source="DPR")
    assert items
    assert items[0].extractor == "rule_based"
    assert items[0].source_ref.startswith("DPR:line:")
    assert "classification_reason" in items[0].notes
