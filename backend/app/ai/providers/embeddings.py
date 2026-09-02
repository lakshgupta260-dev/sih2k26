"""Embedding provider abstraction.

Two real implementations, no stubs:

* :class:`TfidfEmbeddingProvider` — the default. Character and word n-gram
  TF-IDF fitted on the schedule's own activity names, compared by cosine. This
  is **lexical**, not semantic: it is strong on abbreviations and typos because
  of the character n-grams, and blind to synonyms that share no characters. It
  is named accordingly rather than being passed off as semantic AI.
* :class:`SentenceTransformerEmbeddingProvider` — true sentence embeddings,
  which do capture synonymy. Opt-in, because torch adds 1-2 GB to the image.
  Imported lazily so the dependency is genuinely optional.

Both expose the same ``fit`` / ``encode`` contract, so the matcher does not know
or care which is active. The provider reports its own name, which is stored on
every match for auditability.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str
    is_semantic: bool

    def fit(self, corpus: list[str]) -> None:
        """Prepare against the plan-side corpus. May be a no-op."""

    def encode(self, texts: list[str]) -> np.ndarray:
        """Return an (n, d) L2-normalised matrix."""


def _normalise_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


class TfidfEmbeddingProvider:
    """Lexical vector similarity. Cheap, deterministic, no model download."""

    name = "tfidf"
    is_semantic = False

    def __init__(self) -> None:
        self._vectoriser = None
        self._fitted = False

    def fit(self, corpus: list[str]) -> None:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.pipeline import FeatureUnion

        if not corpus:
            self._fitted = False
            return
        # Word n-grams catch phrase overlap; character n-grams survive
        # abbreviation and misspelling ("L&B" vs "lowering backfill").
        self._vectoriser = FeatureUnion(
            [
                ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=1)),
                ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1)),
            ]
        )
        self._vectoriser.fit(corpus)
        self._fitted = True

    def encode(self, texts: list[str]) -> np.ndarray:
        if not self._fitted or self._vectoriser is None or not texts:
            return np.zeros((len(texts), 1), dtype=np.float32)
        matrix = self._vectoriser.transform(texts)
        dense = np.asarray(matrix.todense(), dtype=np.float32)
        return _normalise_rows(dense)


class SentenceTransformerEmbeddingProvider:
    """True sentence embeddings. Requires the optional dependency."""

    name = "sentence_transformer"
    is_semantic = True

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = None

    def _load(self):  # noqa: ANN202
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # lazy

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def fit(self, corpus: list[str]) -> None:
        # Pre-trained; nothing to fit. Load eagerly so a missing dependency
        # surfaces before scoring starts rather than midway through.
        self._load()

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 1), dtype=np.float32)
        vectors = self._load().encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return _normalise_rows(np.asarray(vectors, dtype=np.float32))


def get_embedding_provider() -> EmbeddingProvider:
    """Build the configured provider, falling back to TF-IDF if unavailable."""
    kind = (settings.EMBEDDING_PROVIDER or "tfidf").strip().lower()
    if kind in ("sentence_transformer", "sentence-transformers", "st"):
        try:
            import sentence_transformers  # noqa: F401
        except ImportError:
            logger.warning(
                "sentence_transformers_not_installed_falling_back_to_tfidf",
                extra={"requested": kind},
            )
            return TfidfEmbeddingProvider()
        return SentenceTransformerEmbeddingProvider(settings.EMBEDDING_MODEL)
    if kind not in ("tfidf", "none", "noop"):
        logger.warning("unknown_embedding_provider", extra={"provider": kind})
    return TfidfEmbeddingProvider()
