"""Matching signals, combination and thresholds. No database."""
from __future__ import annotations

import pytest

from app.ai.matching import signals as sig
from app.ai.matching.engine import EXACT_CODE_FLOOR, ActivityMatcher
from app.ai.matching.lexicon import canonical, expand
from app.ai.schemas import (
    ActivityRef,
    ChainageRange,
    EventType,
    ExtractedItem,
    JointRange,
)
from app.core.constants import MatchMethod, MatchStatus


def item(text: str, **kw) -> ExtractedItem:
    kw.setdefault("event_type", EventType.ACTUAL_FINISH)
    return ExtractedItem(raw_text=text, source_ref="t:1", description=text, **kw)


PLAN = [
    ActivityRef("a1", "A1010", "Pipe Lowering and Backfilling KP 12.000 - 14.500",
                "1.1.1.1", 6, "PIPING", ChainageRange(12000, 14500)),
    ActivityRef("a2", "A1020", "Pipe Lowering and Backfilling KP 22.500 - 24.000",
                "1.1.1.2", 6, "PIPING", ChainageRange(22500, 24000)),
    ActivityRef("a3", "A2010", "Radiographic Testing of Girth Joints J-0340 to J-0380",
                "1.2.1.1", 6, "WELDING_NDT", None, JointRange(340, 380)),
    ActivityRef("a4", "A2020", "Weld Repair and Re-Radiography J-0340 to J-0380",
                "1.2.1.2", 6, "WELDING_NDT", None, JointRange(340, 380)),
    ActivityRef("a5", "A3010", "Cable Glanding and Termination at MCC-03",
                "2.1.1.1", 6, "ELECTRICAL"),
    ActivityRef("a6", "A4010", "Foundation Concreting M30 Pump Shed",
                "2.2.1.1", 6, "CIVIL"),
    ActivityRef("a9", "A0010", "Cross-Country Pipeline", "1", 1, None),
]


# -------------------------------------------------------------------- lexicon
@pytest.mark.parametrize(
    "shorthand,expected_token",
    [
        ("L&B", "lowering"),
        ("RT of joints", "radiographic"),
        ("G&T at MCC-03", "glanding"),
        ("fdn concreting", "foundation"),
        ("FJC done", "coating"),
        ("HDD crossing", "directional"),
    ],
)
def test_abbreviations_expand(shorthand: str, expected_token: str) -> None:
    """Without this, no amount of fuzzy matching bridges 'L&B' to 'Lowering'."""
    assert expected_token in expand(shorthand)


def test_canonical_drops_stopwords() -> None:
    assert "the" not in canonical("completion of the trench works").split()


# -------------------------------------------------------------------- signals
def test_exact_code_is_negative_evidence_on_mismatch() -> None:
    """A stated code that is not this activity is evidence against, not absence."""
    assert sig.score_exact_code(item("A1010 done", activity_code="A1010"), PLAN[0]) == 1.0
    assert sig.score_exact_code(item("A1010 done", activity_code="A1010"), PLAN[1]) == 0.0


def test_absent_signals_are_none_not_zero() -> None:
    """An unstated discipline must not be scored like a wrong one."""
    assert sig.score_exact_code(item("no code here"), PLAN[0]) is None
    assert sig.score_discipline(item("no discipline cue"), PLAN[0]) is None
    assert sig.score_location(item("no location"), PLAN[0]) is None


def test_discipline_agreement() -> None:
    assert sig.score_discipline(item("x", discipline="PIPING"), PLAN[0]) == 1.0
    assert sig.score_discipline(item("x", discipline="CIVIL"), PLAN[0]) == 0.0


def test_unlabelled_plan_discipline_is_not_a_disagreement() -> None:
    """OTHER means "could not classify", not a discipline that can conflict.

    A plan whose discipline column the schedule parser could not map must not
    penalise a correctly inferred field discipline.
    """
    unlabelled = ActivityRef("x", "X1", "Pre-Test Cleaning and Gauging Pig Run",
                             "1.3.1", 6, "OTHER")
    assert sig.score_discipline(
        item("pigging cleaning gauging", discipline="TESTING_PRECOMMISSIONING"),
        unlabelled,
    ) is None


def test_location_compares_like_with_like() -> None:
    """A chainage is never compared against a joint band."""
    chain = item("x", chainage=ChainageRange(12000, 14500))
    joints = item("x", joints=JointRange(340, 380))
    assert sig.score_location(chain, PLAN[0]) == pytest.approx(1.0)
    assert sig.score_location(joints, PLAN[0]) is None
    assert sig.score_location(joints, PLAN[2]) == pytest.approx(1.0)


def test_hierarchy_prefers_granular_nodes() -> None:
    deep = sig.score_hierarchy(item("x"), PLAN[0])
    shallow = sig.score_hierarchy(item("x"), PLAN[-1])
    assert deep is not None and shallow is not None
    assert deep > shallow


def test_combine_renormalises_over_available_signals() -> None:
    """Two present signals at 1.0 must give 1.0, whatever is missing."""
    weights = {"fuzzy": 0.8, "location": 0.6, "discipline": 0.35}
    score, _ = sig.combine({"fuzzy": 1.0, "location": 1.0, "discipline": None}, weights)
    assert score == pytest.approx(1.0)


def test_combine_with_no_signals_is_zero_not_a_crash() -> None:
    score, explanation = sig.combine({"fuzzy": None}, {"fuzzy": 0.8})
    assert score == 0.0
    assert explanation


# --------------------------------------------------------------------- engine
def test_shorthand_line_matches_the_right_activity() -> None:
    matcher = ActivityMatcher(PLAN)
    outcome = matcher.match(
        item("L&B done from 12.0 to 14.5 km completed. Total 2500 m.",
             chainage=ChainageRange(12000, 14500), discipline=None)
    )
    assert outcome.best is not None
    assert outcome.best.activity.activity_code == "A1010"
    assert outcome.status == MatchStatus.AUTO_MATCHED


def test_discriminates_between_activities_sharing_a_location() -> None:
    """Same joint band, different work. Location cannot decide; wording must."""
    matcher = ActivityMatcher(PLAN)
    rt = matcher.match(item("RT of jt 340-380 completed", joints=JointRange(340, 380)))
    repair = matcher.match(
        item("Weld repair and re-RT jt 340-380 done", joints=JointRange(340, 380))
    )
    assert rt.best and repair.best
    assert rt.best.activity.activity_code == "A2010"
    assert repair.best.activity.activity_code == "A2020"


def test_exact_code_is_decisive() -> None:
    """An explicit unique identifier outranks any amount of text similarity."""
    outcome = ActivityMatcher(PLAN).match(
        item("Activity A1020 lowering backfilling completed", activity_code="A1020")
    )
    assert outcome.best is not None
    assert outcome.best.activity.activity_code == "A1020"
    assert outcome.best.score >= EXACT_CODE_FLOOR
    assert outcome.best.method == MatchMethod.EXACT_CODE
    assert outcome.status == MatchStatus.AUTO_MATCHED


def test_future_intent_is_never_linked() -> None:
    """However well it would score, future intent must not be booked."""
    outcome = ActivityMatcher(PLAN).match(
        item(
            "L&B 22+500 to 24+000 to be taken up tomorrow",
            event_type=EventType.PLANNED_NOT_ACTUAL,
            chainage=ChainageRange(22500, 24000),
        )
    )
    assert outcome.status == MatchStatus.UNMATCHED
    assert outcome.best is None
    assert "future intent" in outcome.reason


def test_non_event_is_never_linked() -> None:
    outcome = ActivityMatcher(PLAN).match(
        item("Toolbox talk conducted", event_type=EventType.NONE)
    )
    assert outcome.status == MatchStatus.UNMATCHED


def test_thresholds_are_honoured() -> None:
    """The same candidate lands in different buckets as thresholds move.

    Uses a line with one clearly best candidate, so the ambiguity guard does
    not fire and the thresholds are what is actually under test.
    """
    line = item("foundation concreting M30 pump shed completed", discipline="CIVIL")
    permissive = ActivityMatcher(PLAN, auto_threshold=0.05, review_threshold=0.0)
    strict = ActivityMatcher(PLAN, auto_threshold=0.999, review_threshold=0.998)
    assert permissive.match(line).status == MatchStatus.AUTO_MATCHED
    assert strict.match(line).status == MatchStatus.UNMATCHED


def test_ambiguous_top_two_goes_to_review() -> None:
    """Two indistinguishable candidates are a human's decision, not a guess."""
    twins = [
        ActivityRef("t1", "T1", "Trench Excavation KP 5.000 - 6.000", "1.1", 6, "PIPING",
                    ChainageRange(5000, 6000)),
        ActivityRef("t2", "T2", "Trench Excavation KP 5.000 - 6.000", "1.2", 6, "PIPING",
                    ChainageRange(5000, 6000)),
    ]
    outcome = ActivityMatcher(twins, auto_threshold=0.3, review_threshold=0.1).match(
        item("Trench excavation KP 5.000 - 6.000 completed",
             chainage=ChainageRange(5000, 6000), discipline="PIPING")
    )
    assert outcome.status == MatchStatus.NEEDS_REVIEW
    assert "ambiguous" in outcome.reason


def test_empty_schedule_is_unmatched_not_an_error() -> None:
    outcome = ActivityMatcher([]).match(item("L&B completed"))
    assert outcome.status == MatchStatus.UNMATCHED


def test_candidates_are_capped_and_explained() -> None:
    matcher = ActivityMatcher(PLAN, max_candidates=3)
    outcome = matcher.match(item("lowering backfilling completed"))
    assert 0 < len(outcome.candidates) <= 3
    assert outcome.candidates[0].explanation
    # Descending score order matters: the review queue relies on it.
    scores = [c.score for c in outcome.candidates]
    assert scores == sorted(scores, reverse=True)


def test_match_all_carries_hierarchy_context_forward() -> None:
    """Confident matches bias later lines toward the same branch of the tree."""
    items = [
        item("Activity A1010 lowering backfilling completed", activity_code="A1010"),
        item("backfilling continued"),
    ]
    outcomes = ActivityMatcher(PLAN).match_all(items)
    assert outcomes[0].best.activity.activity_code == "A1010"
    assert outcomes[1].best is not None
