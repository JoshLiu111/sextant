"""A stock split, provider-neutral (``SplitsAdapter``, ``analytics.flow_returns``, ``portfolio.imports``)."""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import date
from typing import NamedTuple


class Split(NamedTuple):
    ex_date: date
    ratio: float
    """New shares per old share: 4.0 for a 4:1 split, 0.1 for a 1:10 reverse split."""


def shares_today(splits: Iterable[Split], on: date) -> float:
    """Today's shares per share held on ``on``: the product of every later split's ratio.
    A trade on the ex-date is already at the new share count."""
    return math.prod(s.ratio for s in splits if s.ex_date > on)
