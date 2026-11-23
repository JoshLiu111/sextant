"""Currency conversion at historical rates (pure; knows nothing about data sources).

``rates`` is a ``pd.Series`` of daily exchange rates (units of the target
currency per unit of the source currency) on an ascending ``DatetimeIndex``.
A day without a rate (a weekend or holiday for some providers) uses the last
rate on or before it, never a later one.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from sextant_compute.analytics.errors import MissingData

PRICE_FIELDS = ("open", "high", "low", "close", "dividend")
"""Frame columns that are amounts of money (``volume`` is not)."""


def rate_on(rates: pd.Series, day: date | pd.Timestamp) -> float:
    """The rate for ``day``: the last one on or before it. ``MissingData`` if there is none."""
    known = rates.loc[: pd.Timestamp(day)]
    if known.empty:
        raise MissingData(f"there is no exchange rate on or before {pd.Timestamp(day).date().isoformat()}")
    return float(known.iloc[-1])


def convert_prices(frame: pd.DataFrame, rates: pd.Series) -> pd.DataFrame:
    """``frame`` with every money column converted at each row's date's rate."""
    if frame.empty:
        return frame.copy()
    rate_on(rates, frame.index[0])  # raises when the first day has no rate yet
    daily = rates.reindex(rates.index.union(frame.index)).ffill().loc[frame.index]
    out = frame.copy()
    for column in PRICE_FIELDS:
        if column in out:
            out[column] = out[column] * daily.to_numpy()
    return out
