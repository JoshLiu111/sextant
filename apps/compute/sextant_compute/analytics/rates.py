"""Yield-curve analytics: picking curves by date, the term spread and inversions.

A curve maps maturity in months to a yield in percent (see ``data.adapters.Curve``).
"""

from __future__ import annotations

import calendar
from collections.abc import Mapping, Sequence
from datetime import date

from sextant_compute.analytics.errors import MissingData

TEN_YEARS = 120.0
TWO_YEARS = 24.0


def curve_points(curve: Mapping[float, float]) -> list[tuple[float, float]]:
    """``(maturity in years, yield)`` from the shortest maturity to the longest."""
    return [(months / 12, curve[months]) for months in sorted(curve)]


def months_before(d: date, months: int) -> date:
    """The same day ``months`` calendar months earlier, clamped to the month's end
    (2026-03-31 minus 1 month is 2026-02-28)."""
    index = d.year * 12 + d.month - 1 - months
    year, month = divmod(index, 12)
    day = min(d.day, calendar.monthrange(year, month + 1)[1])
    return date(year, month + 1, day)


def curve_on_or_before(
    curves: Sequence[tuple[date, Mapping[float, float]]], target: date
) -> tuple[date, Mapping[float, float]]:
    """The newest curve dated on or before ``target`` (the previous business day
    when ``target`` is a weekend or holiday). ``curves`` is ascending."""
    found = None
    for when, curve in curves:
        if when > target:
            break
        if curve:
            found = (when, curve)
    if found is None:
        raise MissingData(f"No Treasury yield curve on or before {target.isoformat()}.")
    return found


def term_spread(
    curves: Sequence[tuple[date, Mapping[float, float]]],
    long_months: float = TEN_YEARS,
    short_months: float = TWO_YEARS,
) -> list[tuple[date, float | None]]:
    """Long minus short yield per day, in percentage points. None on a day that
    lacks either maturity."""
    out: list[tuple[date, float | None]] = []
    for when, curve in curves:
        long, short = curve.get(long_months), curve.get(short_months)
        # Inputs carry two decimals; rounding drops float noise (4.92 - 4.63).
        out.append((when, None if long is None or short is None else round(long - short, 6)))
    return out


def inversion_periods(spread: Sequence[tuple[date, float | None]]) -> list[tuple[date, date]]:
    """Runs of consecutive observations with a negative spread, as (first, last)
    inverted date. A day without a value neither starts nor ends a run."""
    periods: list[tuple[date, date]] = []
    run: tuple[date, date] | None = None
    for when, value in spread:
        if value is None:
            continue
        if value < 0:
            run = (run[0], when) if run else (when, when)
        elif run:
            periods.append(run)
            run = None
    if run:
        periods.append(run)
    return periods
