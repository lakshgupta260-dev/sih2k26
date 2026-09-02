"""The matching engine.

Two stages, for cost as much as accuracy:

1. **Blocking** — cheap deterministic keys shortlist candidates. An exact
   activity code short-circuits to a single candidate; otherwise chainage or
   joint overlap, then discipline, then token overlap narrow the field. On a
   5,000-activity schedule this is the difference between scoring 5,000
   candidates per line and scoring a few dozen.

2. **Scoring** — the shortlist is scored on every applicable signal and ranked.
   Thresholds then decide automatic linking, human review, or unmatched.

Nothing here touches the database. The engine consumes ``ActivityRef`` and
``ExtractedItem`` value objects, which makes it directly unit-testable and
keeps the ORM out of the scoring path.
"""
from __future__ import annotations

import numpy as np

from app.ai.matching import signals as sig
from app.ai.matching.signals import lexical_text, lexical_tokens
from app.ai.providers.embeddings import EmbeddingProvider, get_embedding_provider
from app.ai.schemas import (
    ActivityRef,
    EventType,
    ExtractedItem,
    MatchCandidate,
    MatchOutcome,
    MatchSignals,
)
from app.core.config import settings
from app.core.constants import MatchMethod, MatchStatus
from app.core.logging import get_logger

logger = get_logger(__name__)

# Confidence assigned when the field line names an activity code that exists
# in the schedule. Not 1.0: a typo can still produce a valid-looking code, so
# the link stays reviewable, but it is well clear of the automatic threshold.
EXACT_CODE_FLOOR = 0.95


class ActivityMatcher:
    """Links extracted field items to plan activities."""

    def __init__(
        self,
        activities: list[ActivityRef],
        *,
        embedding_provider: EmbeddingProvider | None = None,
        auto_threshold: float | None = None,
        review_threshold: float | None = None,
        weights: dict[str, float] | None = None,
        max_candidates: int | None = None,
        blocking_limit: int | None = None,
    ) -> None:
        self.activities = activities
        self.auto_threshold = (
            auto_threshold if auto_threshold is not None else settings.MATCH_AUTO_THRESHOLD
        )
        self.review_threshold = (
            review_threshold
            if review_threshold is not None
            else settings.MATCH_REVIEW_THRESHOLD
        )
        self.max_candidates = max_candidates or settings.MATCH_MAX_CANDIDATES
        self.blocking_limit = blocking_limit or settings.MATCH_BLOCKING_LIMIT
        self.weights = weights or {
            "exact_code": settings.MATCH_WEIGHT_EXACT_CODE,
            "keyword": settings.MATCH_WEIGHT_KEYWORD,
            "fuzzy": settings.MATCH_WEIGHT_FUZZY,
            "embedding": settings.MATCH_WEIGHT_EMBEDDING,
            "discipline": settings.MATCH_WEIGHT_DISCIPLINE,
            "location": settings.MATCH_WEIGHT_LOCATION,
            "hierarchy": settings.MATCH_WEIGHT_HIERARCHY,
        }

        self._by_code = {
            sig.normalise_code(a.activity_code): a
            for a in activities
            if a.activity_code
        }
        self._tokens = {a.id: lexical_tokens(a.name) for a in activities}

        self.embeddings = embedding_provider or get_embedding_provider()
        self._vectors: np.ndarray | None = None
        self._index: dict[str, int] = {}
        self._fit_embeddings()

    # ------------------------------------------------------------ embeddings
    def _fit_embeddings(self) -> None:
        corpus = [lexical_text(a.name) for a in self.activities]
        if not corpus:
            return
        try:
            self.embeddings.fit(corpus)
            self._vectors = self.embeddings.encode(corpus)
            self._index = {a.id: i for i, a in enumerate(self.activities)}
        except Exception as exc:  # noqa: BLE001 - embeddings are an enhancement
            logger.warning(
                "embedding_provider_failed_continuing_without",
                extra={"provider": getattr(self.embeddings, "name", "?"), "error": str(exc)},
            )
            self._vectors = None

    def _embedding_scores(self, item: ExtractedItem, refs: list[ActivityRef]) -> dict[str, float]:
        if self._vectors is None or not refs:
            return {}
        text = lexical_text(item.description or item.raw_text)
        if not text:
            return {}
        try:
            query = self.embeddings.encode([text])
        except Exception:  # noqa: BLE001
            return {}
        if query.shape[1] != self._vectors.shape[1]:
            return {}
        rows = [self._index[r.id] for r in refs if r.id in self._index]
        if not rows:
            return {}
        sims = (self._vectors[rows] @ query[0]).clip(0.0, 1.0)
        ordered = [r for r in refs if r.id in self._index]
        return {r.id: float(s) for r, s in zip(ordered, sims)}

    # -------------------------------------------------------------- blocking
    def _candidates(self, item: ExtractedItem) -> list[ActivityRef]:
        """Shortlist plausible activities using cheap deterministic keys."""
        code = sig.normalise_code(item.activity_code)
        if code and code in self._by_code:
            # An exact code is decisive; no need to consider anything else.
            return [self._by_code[code]]

        pool: list[ActivityRef] = []
        seen: set[str] = set()

        def add(ref: ActivityRef) -> None:
            if ref.id not in seen:
                seen.add(ref.id)
                pool.append(ref)

        # Location is the strongest cheap key on linear works.
        if item.chainage or item.joints:
            for ref in self.activities:
                if sig.score_location(item, ref):
                    add(ref)

        item_tokens = lexical_tokens(item.description or item.raw_text)
        if item_tokens:
            for ref in self.activities:
                if len(item_tokens & self._tokens.get(ref.id, set())) >= 1:
                    add(ref)
                if len(pool) >= self.blocking_limit:
                    break

        if item.discipline and len(pool) < self.blocking_limit:
            for ref in self.activities:
                if ref.discipline == item.discipline:
                    add(ref)
                if len(pool) >= self.blocking_limit:
                    break

        # Nothing keyed: fall back to the whole schedule, bounded.
        if not pool:
            pool = list(self.activities[: self.blocking_limit])
        return pool[: self.blocking_limit]

    # --------------------------------------------------------------- scoring
    def match(
        self, item: ExtractedItem, *, context_wbs: str | None = None
    ) -> MatchOutcome:
        """Score one extracted item and apply the thresholds."""
        # Future intent and non-events are never linked, however well they
        # would score. Booking "to be taken up tomorrow" corrupts the schedule.
        if item.event_type == EventType.PLANNED_NOT_ACTUAL:
            return MatchOutcome(
                item=item,
                candidates=[],
                status=MatchStatus.UNMATCHED,
                reason="line states future intent, not an actual event",
            )
        if item.event_type == EventType.NONE:
            return MatchOutcome(
                item=item,
                candidates=[],
                status=MatchStatus.UNMATCHED,
                reason="line is not an activity event",
            )

        refs = self._candidates(item)
        if not refs:
            return MatchOutcome(
                item=item,
                candidates=[],
                status=MatchStatus.UNMATCHED,
                reason="no candidate activities in this schedule",
            )

        embedding_scores = self._embedding_scores(item, refs)
        scored: list[MatchCandidate] = []

        for ref in refs:
            signals = MatchSignals(
                exact_code=sig.score_exact_code(item, ref),
                keyword=sig.score_keyword(item, ref),
                fuzzy=sig.score_fuzzy(item, ref),
                embedding=embedding_scores.get(ref.id),
                discipline=sig.score_discipline(item, ref),
                location=sig.score_location(item, ref),
                hierarchy=sig.score_hierarchy(item, ref, context_wbs=context_wbs),
            )
            score, explanation = sig.combine(signals.__dict__, self.weights)
            scored.append(
                MatchCandidate(
                    activity=ref,
                    score=round(score, 4),
                    signals=signals,
                    method=self._method_for(signals),
                    explanation=explanation,
                )
            )

        scored.sort(key=lambda c: c.score, reverse=True)
        top = scored[: self.max_candidates]
        best = top[0]

        # An explicit activity code that exists in this schedule is a unique
        # identifier, and stronger evidence than any amount of text similarity.
        # Averaging it in with weaker lexical signals would send a definitively
        # identified line to a human, so it is floored instead.
        if best.signals.exact_code == 1.0:
            best.score = max(best.score, EXACT_CODE_FLOOR)
            best.method = MatchMethod.EXACT_CODE
            best.explanation.append(
                f"activity code stated explicitly and unique in schedule; "
                f"score floored to {EXACT_CODE_FLOOR:g}"
            )

        if best.score >= self.auto_threshold:
            status, reason = MatchStatus.AUTO_MATCHED, "score at or above the automatic threshold"
        elif best.score >= self.review_threshold:
            status, reason = MatchStatus.NEEDS_REVIEW, "score in the review band"
        else:
            status, reason = MatchStatus.UNMATCHED, "best score below the review threshold"

        # Two near-identical candidates are ambiguous even when the score is
        # high, so send them to a human rather than guessing.
        if status == MatchStatus.AUTO_MATCHED and len(top) > 1:
            runner_up = top[1].score
            if runner_up > 0 and (best.score - runner_up) < 0.05:
                status = MatchStatus.NEEDS_REVIEW
                reason = (
                    f"top two candidates are within 0.05 "
                    f"({best.score:.3f} vs {runner_up:.3f}); ambiguous"
                )

        return MatchOutcome(
            item=item, candidates=top, status=status, best=best, reason=reason
        )

    @staticmethod
    def _method_for(signals: MatchSignals) -> str:
        """Label the dominant evidence, for auditability."""
        if signals.exact_code == 1.0:
            return MatchMethod.EXACT_CODE
        present = signals.as_dict()
        strong = [k for k, v in present.items() if v >= 0.8]
        if len(strong) > 1:
            return MatchMethod.HYBRID
        if signals.embedding is not None and signals.embedding >= 0.8:
            return MatchMethod.SEMANTIC
        if signals.fuzzy is not None and signals.fuzzy >= 0.8:
            return MatchMethod.FUZZY
        if signals.keyword is not None and signals.keyword >= 0.5:
            return MatchMethod.KEYWORD
        return MatchMethod.HYBRID

    def match_all(self, items: list[ExtractedItem]) -> list[MatchOutcome]:
        """Match a document's items, feeding confident matches forward as context."""
        outcomes: list[MatchOutcome] = []
        context_wbs: str | None = None
        for item in items:
            outcome = self.match(item, context_wbs=context_wbs)
            outcomes.append(outcome)
            if outcome.best and outcome.status == MatchStatus.AUTO_MATCHED:
                # Use the confident match's parent branch as context for the
                # lines that follow.
                path = outcome.best.activity.wbs_path
                context_wbs = path.rsplit(".", 1)[0] if "." in path else path
        return outcomes
