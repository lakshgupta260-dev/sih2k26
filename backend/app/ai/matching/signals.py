"""Individual match signals.

Each scorer returns a value in 0..1, or ``None`` when the signal does not
apply. ``None`` matters: an absent signal must not be scored as zero, or an
extracted line that simply never mentioned a discipline would be penalised as
though it had mentioned the wrong one. The combiner renormalises over whichever
signals were actually available.
"""
from __future__ import annotations

from rapidfuzz import fuzz

from app.ai.extraction.base import residual_text
from app.ai.matching.lexicon import canonical, content_tokens
from app.ai.schemas import ActivityRef, ExtractedItem


def lexical_text(text: str) -> str:
    """Text prepared for lexical comparison.

    Location expressions are stripped before tokenising, because chainage and
    joint numbers are scored by their own signal. Leaving "KP 12.000 - 14.500"
    in the plan name dilutes the keyword and fuzzy scores with digits that
    carry no lexical meaning, which pushes correct matches below the automatic
    threshold. Each signal should measure exactly one thing.
    """
    return canonical(residual_text(text or ""))


def lexical_tokens(text: str) -> set[str]:
    return content_tokens(residual_text(text or ""))

# Field reports describe granular work, so a deep node is a better candidate
# than a rolled-up parent. An L1 milestone almost never corresponds to one line
# of a daily report.
LEVEL_PREFERENCE: dict[int, float] = {6: 1.0, 5: 0.92, 4: 0.62, 3: 0.4, 2: 0.22, 1: 0.1}


def normalise_code(code: str | None) -> str:
    return (code or "").strip().upper().replace(" ", "").replace("_", "-")


def score_exact_code(item: ExtractedItem, activity: ActivityRef) -> float | None:
    """1.0 on an exact activity-code hit, 0.0 on a clear mismatch."""
    extracted = normalise_code(item.activity_code)
    if not extracted:
        return None
    plan = normalise_code(activity.activity_code)
    if not plan:
        return None
    if extracted == plan:
        return 1.0
    # A code was stated and it is not this activity: genuine negative evidence.
    return 0.0


def score_keyword(item: ExtractedItem, activity: ActivityRef) -> float | None:
    """How much of the plan activity's vocabulary the field line covers.

    Containment against the plan side, not Jaccard. A field line legitimately
    carries words a plan name never has -- "completed today", quantities, crew
    notes -- and Jaccard would penalise it for that. The question worth asking
    is whether the line mentions what the activity is about.
    """
    left = lexical_tokens(item.description or item.raw_text)
    right = lexical_tokens(activity.name)
    if not left or not right:
        return None
    return len(left & right) / len(right)


def score_fuzzy(item: ExtractedItem, activity: ActivityRef) -> float | None:
    """Token-set ratio on expanded text.

    ``token_set_ratio`` is chosen over plain ratio because field lines carry
    extra words ("completed today", quantities) that a plan name never has, and
    token-set ignores that asymmetry.
    """
    left = lexical_text(item.description or item.raw_text)
    right = lexical_text(activity.name)
    if not left or not right:
        return None
    return max(
        fuzz.token_set_ratio(left, right),
        fuzz.partial_ratio(left, right) * 0.9,
    ) / 100.0


# "OTHER" is what the schedule parser stores when it cannot classify a
# discipline label. That is an absence of information, not a discipline that
# can disagree, so it must score as None rather than 0.0 -- otherwise a plan
# whose discipline column is poorly labelled actively penalises correct
# matches. Observed in practice: a plan row labelled "Testing" landed as OTHER,
# scored 0.0 against a correctly inferred TESTING_PRECOMMISSIONING, and pushed
# a right answer out of automatic matching and into the review queue.
UNLABELLED_DISCIPLINES = frozenset({"OTHER", ""})


def score_discipline(item: ExtractedItem, activity: ActivityRef) -> float | None:
    """Agreement on discipline, or ``None`` when either side is unlabelled.

    Meaningful only because Phase 3 normalises the plan-side discipline to the
    enum; against free text it would be noise.
    """
    left = (item.discipline or "").upper()
    right = (activity.discipline or "").upper()
    if left in UNLABELLED_DISCIPLINES or right in UNLABELLED_DISCIPLINES:
        return None
    return 1.0 if left == right else 0.0


def score_location(item: ExtractedItem, activity: ActivityRef) -> float | None:
    """Overlap of chainage ranges, or of joint bands.

    A strong, almost unambiguous signal on linear works: two activities rarely
    cover the same kilometres. Compared like-with-like only -- a chainage is
    never compared against a joint band.
    """
    if item.chainage and activity.chainage:
        return item.chainage.overlap_ratio(activity.chainage)
    if item.joints and activity.joints:
        return item.joints.overlap_ratio(activity.joints)
    return None


def score_hierarchy(
    item: ExtractedItem, activity: ActivityRef, *, context_wbs: str | None = None
) -> float | None:
    """Prefer granular nodes, and nodes near others already matched nearby.

    ``context_wbs`` is the WBS path of a confident match elsewhere in the same
    document. Reports are written section by section, so a neighbouring line
    usually belongs to the same branch of the tree.
    """
    base = LEVEL_PREFERENCE.get(activity.level)
    if base is None:
        return None
    if context_wbs and activity.wbs_path:
        if activity.wbs_path.startswith(context_wbs) or context_wbs.startswith(
            activity.wbs_path
        ):
            base = min(1.0, base + 0.2)
    return base


def combine(
    signals: dict[str, float | None], weights: dict[str, float]
) -> tuple[float, list[str]]:
    """Weighted mean over the signals that were available.

    Renormalising by the weight of present signals is what keeps a line with no
    discipline or location from being punished relative to one that has both.
    Returns the score and a human-readable explanation for the review UI.
    """
    total_weight = 0.0
    accumulated = 0.0
    explanation: list[str] = []

    for name, value in signals.items():
        if value is None:
            continue
        weight = weights.get(name, 0.0)
        if weight <= 0:
            continue
        total_weight += weight
        accumulated += weight * value
        explanation.append(f"{name}={value:.2f} (w={weight:g})")

    if total_weight == 0.0:
        return 0.0, ["no applicable signals"]
    return accumulated / total_weight, explanation
