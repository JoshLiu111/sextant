"""Input guards shared by the ratio analytics (company ratios and the screener)."""

from __future__ import annotations

from sextant_compute.analytics.errors import MetricError


def positive(value: float, what: str, ratio: str = "the ratio") -> float:
    """``value`` if it is above zero. A zero or negative denominator (negative
    equity, a loss year's EPS) is reported but makes ``ratio`` meaningless, so it
    is a ``MetricError`` (status ``error``), not missing data."""
    if value <= 0:
        raise MetricError(f"{what} is zero or negative, so {ratio} isn't meaningful.")
    return value
