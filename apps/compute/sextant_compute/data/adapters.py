"""What an adapter is: one per data provider, behind ``DataService``.

An adapter declares:

- ``source``: a ``DataSource`` whose ``id``/``name`` are the *real* provider
  (``"sec_edgar"``, ``"fred"``, ``"tiingo"``, ``"synthetic"``). Never label paid or
  user-keyed data as a public source.
- ``scope``: ``"shared"`` for public data (cached for everyone) or ``"user"`` for
  data fetched with the visitor's own key (cached per user, never shared).
- ``ttl``: dataset name -> cache TTL in seconds. A dataset missing here is not cached.
- ``version``: part of every cache key. Bump it when the adapter's output changes
  (new mapping, parser fix, new generator), because cached entries outlive deploys.

and implements the dataset methods it supports (see the protocols below). Each
method takes ``ctx`` first, does its own rate limiting / retries, and raises only
``SourceUnavailable`` or ``NoSuchData`` for provider problems.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Literal, Protocol

import pandas as pd

from sextant_compute.data.context import RequestContext
from sextant_compute.envelope import DataSource

Scope = Literal["shared", "user"]

PRICE_COLUMNS = ["open", "high", "low", "close", "volume", "dividend"]


class Adapter(Protocol):
    source: DataSource
    scope: Scope
    ttl: Mapping[str, int]
    version: str


class DailyPricesAdapter(Adapter, Protocol):
    def daily_prices(
        self, ctx: RequestContext, tickers: Sequence[str], start: date, end: date
    ) -> dict[str, pd.DataFrame]:
        """One frame per requested ticker: DatetimeIndex ``date`` (trading days within
        [start, end], ascending) and ``PRICE_COLUMNS``. ``dividend`` is the cash
        dividend with that ex-date (0 otherwise); ``close`` is not dividend-adjusted.
        Raises ``NoSuchData`` (``missing`` keyed by ticker) for unknown tickers or an
        empty range."""
        ...
