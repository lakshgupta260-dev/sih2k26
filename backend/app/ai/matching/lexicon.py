"""Domain lexicon for bridging field shorthand to plan wording.

This is the single highest-leverage component for match accuracy. Plan
schedules say "Pipe Lowering and Backfilling"; a supervisor writes "L&B". No
amount of fuzzy string matching or embedding similarity recovers that, because
the two share almost no characters and no co-occurrence in a general corpus.

The map is curated Indian pipeline and station construction vocabulary. It is
data, not logic: extending it is how the matcher improves, and it deliberately
lives apart from the scoring code so a planner can review it.
"""
from __future__ import annotations

import re

# Field shorthand -> canonical plan words. Expansion is applied to BOTH sides,
# so the plan text is normalised the same way and nothing depends on which
# direction the abbreviation appears in.
ABBREVIATIONS: dict[str, str] = {
    # pipeline
    "l&b": "lowering backfilling",
    "l and b": "lowering backfilling",
    "rou": "right of use clearing grading",
    "row": "right of way clearing grading",
    "hdd": "horizontal directional drilling",
    "fjc": "field joint coating",
    "cl survey": "centre line survey staking",
    "c/l survey": "centre line survey staking",
    "jmc": "joint measurement crop compensation",
    # welding and NDT
    "rt": "radiographic testing radiography",
    "r.t.": "radiographic testing radiography",
    "ndt": "non destructive testing",
    "ut": "ultrasonic testing",
    "mpt": "magnetic particle testing",
    "dpt": "dye penetrant testing",
    "f&c": "fill cap pass welding",
    "fill & cap": "fill cap pass welding",
    "root run": "root pass welding",
    "rootpass": "root pass welding",
    # testing and pre-commissioning
    "ht": "hydrostatic testing hydrotest",
    "hydrotest": "hydrostatic testing",
    "pigging": "cleaning gauging pig run",
    "jeeping": "holiday detection",
    # electrical and instrumentation
    "g&t": "glanding termination",
    "e&i": "electrical instrumentation",
    "mcc": "motor control centre",
    "swgr": "switchgear",
    "trf": "transformer",
    "ups": "uninterruptible power supply",
    "ldb": "lighting distribution board",
    "dg": "diesel generator",
    "sld": "single line diagram",
    "jb": "junction box",
    "plc": "programmable logic controller",
    "loop check": "loop checking calibration",
    "imp. tubing": "impulse tubing fitting",
    "imp tubing": "impulse tubing fitting",
    # civil and structural
    "pcc": "plain cement concrete",
    "rcc": "reinforced cement concrete",
    "fdn": "foundation",
    "str steel": "structural steel",
    "str. steel": "structural steel",
    "bp grouting": "base plate grouting",
    "wp": "waterproofing",
    "blockwork": "block work plastering",
    # mechanical and piping
    "spool fab": "spool fabrication",
    "mrir": "material receipt inspection report",
    "itp": "inspection test plan",
    "rfi": "request for inspection",
    # general
    "instl": "installation",
    "instln": "installation",
    "erection": "erection installation",
    "fab": "fabrication",
    "exc": "excavation",
    "comp": "compaction",
    "nos": "numbers",
    "qty": "quantity",
}

# Tokens that carry no discriminating signal in this domain.
STOPWORDS: frozenset[str] = frozenset(
    """
    a an the of and or for to at in on by with from as per is are was were be
    been being work works site activity task today yesterday tomorrow date
    completed complete done finished closed started commenced start progress
    ongoing continuing under achieved cumulative executed total nos no number
    approved drawing dwg ref rev as
    """.split()
)

_TOKEN = re.compile(r"[a-z0-9]+")


def expand(text: str) -> str:
    """Replace known shorthand with canonical wording.

    Longest keys first, so "imp. tubing" is not partly consumed by "imp".
    """
    low = (text or "").lower()
    for key in sorted(ABBREVIATIONS, key=len, reverse=True):
        if key in low:
            low = low.replace(key, f" {ABBREVIATIONS[key]} ")
    return re.sub(r"\s+", " ", low).strip()


def content_tokens(text: str) -> set[str]:
    """Expanded, stopword-free tokens of length >= 2, used for keyword overlap."""
    return {
        token
        for token in _TOKEN.findall(expand(text))
        if len(token) >= 2 and token not in STOPWORDS
    }


def canonical(text: str) -> str:
    """Expanded text with stopwords removed, for fuzzy and vector comparison."""
    return " ".join(
        token
        for token in _TOKEN.findall(expand(text))
        if token not in STOPWORDS
    )
