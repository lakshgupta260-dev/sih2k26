"""Extractor contract and shared text helpers."""
from __future__ import annotations

import re
from datetime import date
from typing import Protocol, runtime_checkable

from app.ai.schemas import ChainageRange, EventType, ExtractedItem, JointRange


@runtime_checkable
class ActivityExtractor(Protocol):
    """Turns a document's text into candidate activity events."""

    name: str

    def extract(self, raw_text: str, *, source: str = "document") -> list[ExtractedItem]: ...


# --------------------------------------------------------------- normalisation
_WS = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Lowercase, collapse whitespace, strip surrounding punctuation."""
    return _WS.sub(" ", text or "").strip().strip(" .,;:-").lower()


def split_lines(raw_text: str) -> list[tuple[int, str]]:
    """Split a document into numbered candidate lines.

    Numbered-list markers, bullets and leading section letters are stripped so
    that "  3. L&B completed." and "- L&B completed." normalise to the same
    payload while keeping the original index for traceability.
    """
    out: list[tuple[int, str]] = []
    for index, line in enumerate(raw_text.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        stripped = re.sub(r"^[\-\*•]\s*", "", stripped)
        stripped = re.sub(r"^\(?\d{1,3}[\.\)]\s*", "", stripped)
        stripped = re.sub(r"^[A-Z][\.\)]\s+", "", stripped)
        if len(stripped) < 4:
            continue
        out.append((index, stripped))
    return out


# ------------------------------------------------------------------ chainage
# A bare "340-380" must NOT be read as a chainage: it is far more often a joint
# band or part of a date. Every pattern therefore requires an explicit unit
# marker, either before the range (KP/km/ch) or after it (km).
_KM_RANGE_PREFIXED = re.compile(
    r"(?:kp|km|ch(?:ainage)?)\.?\s*(\d{1,3}(?:\.\d{1,3})?)\s*(?:-|to|–|—)\s*"
    r"(?:kp|km)?\.?\s*(\d{1,3}(?:\.\d{1,3})?)",
    re.IGNORECASE,
)
_KM_RANGE_SUFFIXED = re.compile(
    r"(\d{1,3}(?:\.\d{1,3})?)\s*(?:-|to|–|—)\s*(\d{1,3}(?:\.\d{1,3})?)\s*kms?\b",
    re.IGNORECASE,
)
# "ch 22500-24000" -- plain metres
_M_RANGE = re.compile(
    r"ch(?:ainage)?\.?\s*(\d{3,6})\s*(?:-|to|–|—)\s*(\d{3,6})", re.IGNORECASE
)
# "22+500 to 24+000" -- station notation
_STATION_RANGE = re.compile(
    r"(\d{1,3})\s*\+\s*(\d{3})\s*(?:-|to|–|—)\s*(\d{1,3})\s*\+\s*(\d{3})"
)
# A joint or weld marker immediately before the numbers means this is a joint
# band, not a location.
_JOINT_MARKER_NEAR = re.compile(
    r"(?:j|jt|jts|joint|joints|weld)\s*(?:no\.?)?\s*[-# ]?\s*\d", re.IGNORECASE
)
# d-m-y / y-m-d, so a date is never mistaken for a range.
_DATE_LIKE = re.compile(
    r"\b\d{1,4}[-/.]\d{1,2}[-/.]\d{2,4}\b"
)


def _blank(text: str, start: int, end: int) -> str:
    return text[:start] + " " * (end - start) + text[end:]


def _mask_dates(text: str) -> str:
    """Blank out date-like substrings so range parsers cannot consume them."""
    masked = text
    for m in _DATE_LIKE.finditer(text):
        masked = _blank(masked, m.start(), m.end())
    return masked


def find_chainage(text: str) -> tuple[ChainageRange, int, int] | None:
    """Parse a linear location into metres, returning the matched span too.

    Returns ``None`` when the text carries a joint marker, since a joint band
    and a chainage compete for the same digits and the joint reading wins.
    """
    if _JOINT_MARKER_NEAR.search(text):
        return None
    masked = _mask_dates(text)

    m = _STATION_RANGE.search(masked)
    if m:
        a = int(m.group(1)) * 1000 + int(m.group(2))
        b = int(m.group(3)) * 1000 + int(m.group(4))
        return ChainageRange(float(min(a, b)), float(max(a, b))), m.start(), m.end()

    m = _M_RANGE.search(masked)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        if a != b:
            return ChainageRange(min(a, b), max(a, b)), m.start(), m.end()

    for pattern in (_KM_RANGE_PREFIXED, _KM_RANGE_SUFFIXED):
        m = pattern.search(masked)
        if m:
            a, b = float(m.group(1)) * 1000, float(m.group(2)) * 1000
            if a != b:
                return ChainageRange(min(a, b), max(a, b)), m.start(), m.end()
    return None


def parse_chainage(text: str) -> ChainageRange | None:
    found = find_chainage(text)
    return found[0] if found else None


# -------------------------------------------------------------------- joints
_JOINT_RANGE = re.compile(
    r"(?:j|jt|jts|joint|joints|weld(?:\s*no\.?)?)\s*[-# ]?\s*0*(\d{1,5})\s*"
    r"(?:-|to|–|—)\s*(?:j|jt|joint)?\s*[-# ]?\s*0*(\d{1,5})",
    re.IGNORECASE,
)
# "40 nos joints (from 340)"
_JOINT_COUNT_FROM = re.compile(
    r"(\d{1,4})\s*nos?\s*joints?\s*\(?\s*from\s*0*(\d{1,5})", re.IGNORECASE
)


def find_joints(text: str) -> tuple[JointRange, int, int] | None:
    masked = _mask_dates(text)
    m = _JOINT_COUNT_FROM.search(masked)
    if m:
        count, start = int(m.group(1)), int(m.group(2))
        return JointRange(start, start + count), m.start(), m.end()
    m = _JOINT_RANGE.search(masked)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return JointRange(min(a, b), max(a, b)), m.start(), m.end()
    return None


def parse_joints(text: str) -> JointRange | None:
    found = find_joints(text)
    return found[0] if found else None


def residual_text(text: str) -> str:
    """Text with date, joint and chainage spans blanked out.

    Quantity parsing runs on this, so "12.0 to 14.5 km ... Total 2500 m" yields
    2500 m rather than 14.5 km -- the chainage digits are no longer visible.
    """
    out = _mask_dates(text)
    joints = find_joints(out)
    if joints:
        out = _blank(out, joints[1], joints[2])
    chain = find_chainage(out)
    if chain:
        out = _blank(out, chain[1], chain[2])
    return out


# ------------------------------------------------------------ activity codes
# Plan-side codes look like A1010, ACT-12, 1.2.3, PROJ-OIL-PL02.SEC-1
_ACTIVITY_CODE = re.compile(
    r"\b(?:activity|act|id|code|ref)\.?\s*[:#-]?\s*"
    r"([A-Z]{1,6}[-_]?\d{2,6}(?:[.\-][A-Z0-9]{1,6})*)\b",
    re.IGNORECASE,
)
_BARE_CODE = re.compile(r"\b([A-Z]{2,6}[-_]?\d{3,6})\b")


def parse_activity_code(text: str) -> str | None:
    m = _ACTIVITY_CODE.search(text)
    if m:
        return m.group(1).upper()
    m = _BARE_CODE.search(text)
    if m:
        return m.group(1).upper()
    return None


# ------------------------------------------------------------------ measures
# The word-boundary applies only to the spelled-out forms: "\b" after a
# literal "%" never matches, because "%" and the following space are both
# non-word characters.
_PERCENT = re.compile(
    r"(\d{1,3}(?:\.\d)?)\s*(?:%|percent\b|pct\b)", re.IGNORECASE
)
_QUANTITY = re.compile(
    r"(\d{1,7}(?:\.\d{1,3})?)\s*"
    r"(m|mtr|metres?|meters?|km|nos?|joints?|sqm|cum|m2|m3|tonnes?|kg|ltr|litres?)\b",
    re.IGNORECASE,
)

_UOM_CANON = {
    "m": "m", "mtr": "m", "metre": "m", "metres": "m", "meter": "m", "meters": "m",
    "km": "km", "no": "no.", "nos": "no.", "joint": "joints", "joints": "joints",
    "sqm": "m2", "m2": "m2", "cum": "m3", "m3": "m3",
    "tonne": "t", "tonnes": "t", "kg": "kg", "ltr": "l", "litre": "l", "litres": "l",
}


def parse_percent(text: str) -> float | None:
    m = _PERCENT.search(text)
    if not m:
        return None
    value = float(m.group(1))
    return value if 0.0 <= value <= 100.0 else None


def parse_quantity(text: str) -> tuple[float, str] | None:
    for m in _QUANTITY.finditer(text):
        # Skip a number that is really a percentage or a chainage
        span_before = text[max(0, m.start() - 3):m.start()]
        if "+" in span_before:
            continue
        value = float(m.group(1))
        uom = _UOM_CANON.get(m.group(2).lower(), m.group(2).lower())
        return value, uom
    return None


# --------------------------------------------------------------------- dates
_DATE_PATTERNS = (
    (re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), ("y", "m", "d")),
    (re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b"), ("d", "m", "y")),
    (re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2})\b"), ("d", "m", "yy")),
)


def parse_date(text: str) -> date | None:
    for pattern, order in _DATE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        parts = dict(zip(order, m.groups()))
        try:
            year = int(parts.get("y") or 0)
            if "yy" in parts:
                year = 2000 + int(parts["yy"])
            return date(year, int(parts["m"]), int(parts["d"]))
        except (ValueError, KeyError):
            continue
    return None
