"""A stock split, provider-neutral (``SplitsAdapter``, ``analytics.flow_returns``)."""

from __future__ import annotations

from datetime import date
from typing import NamedTuple


class Split(NamedTuple):
    ex_date: date
    ratio: float
    """New shares per old share: 4.0 for a 4:1 split, 0.1 for a 1:10 reverse split."""
