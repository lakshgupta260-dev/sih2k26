"""Delay prediction.

Two tiers live here. :mod:`app.ml.baseline` is deterministic rate arithmetic
that always works and can be checked by hand; :mod:`app.ml.model` is a fitted
scikit-learn classifier that is only promoted once it has been shown to beat
that arithmetic on the same data. :mod:`app.ml.features` builds the inputs for
both from ingested plan dates and booked progress.

Nothing in this package is an LLM, and nothing in it invents a number.
"""
