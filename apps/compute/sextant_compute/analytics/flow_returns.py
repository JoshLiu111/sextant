"""Time-weighted and money-weighted (IRR) returns of a traded portfolio (pure).

The portfolio is its holdings; trades move money in and out of it:

- A buy puts money in: ``quantity * price + fees``.
- A sell takes money out: ``quantity * price - fees``.
- A dividend takes money out: dividend per share times the quantity held at the
  previous close (it is paid to the investor, not reinvested).

Daily values are ``sum_i quantity_i * close_i`` at each close. A trade counts at
the close of its trading day (a trade on a non-trading day counts on the next
one).

**Time-weighted return (TWR)** chains daily returns, so money moving in or out
does not change it: it measures what the holdings did. With flows at the end of
day ``t``: ``r_t = (V_t + out_t - in_t) / V_t-1 - 1``. On a day that starts from
nothing, the money put in that day is the starting value instead:
``r_t = (V_t + out_t) / in_t - 1``. Days with nothing held are skipped.

**Money-weighted return (IRR)** is the yearly rate ``r`` at which the cash flows
net to zero: ``sum_k cf_k / (1 + r)^(t_k)`` with ``t_k`` in years (actual days /
365). The flows are the starting value (put in on the first day), the trades and
dividends, and the ending value (taken out on the last day). It rewards or
punishes the timing of deposits and withdrawals. When no rate (or more than one)
solves the equation, it raises ``MissingData``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date

import numpy as np
import pandas as pd

from sextant_compute.analytics.errors import MissingData

DAYS_PER_YEAR = 365
_DUST = 1e-9
# The IRR is searched over log(1 + r) in this range: r from -99.995% to about 2.2 million % a year.
_LOG_GROWTH_RANGE = (-10.0, 10.0)
_GRID = 4001


@dataclass(frozen=True)
class Trade:
    date: date
    ticker: str
    quantity: float
    """Signed: positive for a buy, negative for a sell."""
    cash_in: float
    """Money put into the portfolio: buy cost including fees, or minus the sell proceeds net of fees."""


@dataclass(frozen=True)
class Book:
    """The portfolio day by day, on the price dates."""

    value: pd.Series
    cash_in: pd.Series
    """Money put in by trades on each day (0 on the first day; trades up to then are in its value)."""
    cash_out: pd.Series
    """Money taken out by sells and dividends on each day."""


def daily_book(
    prices: Mapping[str, pd.DataFrame],
    holdings: Mapping[str, float],
    trades: Sequence[Trade],
    splits: Mapping[str, Sequence[tuple[date, float]]] | None = None,
) -> Book:
    """Rebuild each day's holdings from today's ``holdings`` by undoing ``trades`` backwards.

    ``prices`` frames have ``close`` and ``dividend`` columns on the same dates and
    cover every held or traded ticker. Trades up to the first date are part of the
    first day's value; trades after the last date are undone and ignored.

    ``holdings`` and ``prices`` are in today's share count; a trade's quantity is in
    the share count of its date. ``splits`` (ticker -> ``(ex-date, new shares per
    old share)``) turns each trade into today's share count: its quantity times
    every split after its date. A trade's cash does not change.
    """
    trades = [_in_todays_shares(t, (splits or {}).get(t.ticker, ())) for t in trades]
    dates = next(iter(prices.values())).index
    first, last = dates[0].date(), dates[-1].date()
    quantity = dict.fromkeys(prices, 0.0) | dict(holdings)
    for t in trades:
        if t.date > first:
            quantity[t.ticker] -= t.quantity
    _check_not_short(quantity, f"on {first.isoformat()}")

    by_day: dict[int, list[Trade]] = {}
    positions = dates.searchsorted(pd.DatetimeIndex([pd.Timestamp(t.date) for t in trades]))
    for t, i in zip(trades, positions, strict=True):
        if first < t.date <= last:
            by_day.setdefault(int(i), []).append(t)

    value, cash_in, cash_out = [], [], []
    for i, day in enumerate(dates):
        paid_in = paid_out = 0.0
        if i > 0:
            paid_out += sum(q * float(prices[s]["dividend"].iloc[i]) for s, q in quantity.items())
            for t in by_day.get(i, []):
                quantity[t.ticker] += t.quantity
                if t.cash_in >= 0:
                    paid_in += t.cash_in
                else:
                    paid_out -= t.cash_in
            _check_not_short(quantity, f"after the trades of {day.date().isoformat()}")
        value.append(sum(q * float(prices[s]["close"].iloc[i]) for s, q in quantity.items()))
        cash_in.append(paid_in)
        cash_out.append(paid_out)
    return Book(pd.Series(value, index=dates), pd.Series(cash_in, index=dates), pd.Series(cash_out, index=dates))


def _in_todays_shares(trade: Trade, splits: Sequence[tuple[date, float]]) -> Trade:
    # A trade on the ex-date is already at the new share count.
    factor = math.prod(ratio for ex_date, ratio in splits if ex_date > trade.date)
    return trade if factor == 1 else replace(trade, quantity=trade.quantity * factor)


def _check_not_short(quantity: Mapping[str, float], when: str) -> None:
    for ticker, q in quantity.items():
        if q < -_DUST:
            raise MissingData(
                f"the holdings and the transactions do not match: {ticker} would be {q:,.6g} {when}. "
                "Edit the holdings or re-import the transactions"
            )


def time_weighted_return(book: Book) -> tuple[float, int]:
    """Cumulative TWR, and the calendar days from the start of the first day with money in."""
    growth, start = 1.0, None
    for i in range(1, len(book.value)):
        before, now = book.value.iloc[i - 1], book.value.iloc[i]
        paid_in, paid_out = book.cash_in.iloc[i], book.cash_out.iloc[i]
        if before > _DUST:
            factor = (now + paid_out - paid_in) / before
        elif paid_in > _DUST:
            factor = (now + paid_out) / paid_in
        else:
            continue
        if factor < 0:
            raise MissingData(f"the trades of {book.value.index[i].date().isoformat()} lost more than the portfolio was worth")
        growth *= factor
        if start is None:
            start = book.value.index[i - 1]
    if start is None:
        raise MissingData("the portfolio held nothing in this date range")
    return growth - 1, (book.value.index[-1] - start).days


def annualize(total_return: float, days: int) -> float:
    if days <= 0:
        raise MissingData("needs at least one day between the first and last values")
    return (1 + total_return) ** (DAYS_PER_YEAR / days) - 1


def cash_flows(book: Book) -> list[tuple[date, float]]:
    """The investor's cash flows: negative when money goes in, positive when it comes out."""
    dates = book.value.index
    flows = [(dates[0].date(), -float(book.value.iloc[0]))]
    flows += [(d.date(), float(o - i)) for d, i, o in zip(dates[1:], book.cash_in.iloc[1:], book.cash_out.iloc[1:], strict=True)]
    flows.append((dates[-1].date(), float(book.value.iloc[-1])))
    return [(d, cf) for d, cf in flows if abs(cf) > _DUST]


def irr(flows: Sequence[tuple[date, float]]) -> float:
    """The yearly rate that nets ``flows`` to zero (dates in actual days / 365)."""
    if not any(cf > 0 for _, cf in flows) or not any(cf < 0 for _, cf in flows):
        raise MissingData("there is no rate of return: the cash flows need money both going in and coming out")
    start = min(d for d, _ in flows)
    years = np.array([(d - start).days / DAYS_PER_YEAR for d, _ in flows])
    amounts = np.array([cf for _, cf in flows])
    scale = np.abs(amounts).max()

    def npv(log_growth: float | np.ndarray) -> np.ndarray:
        return (amounts / scale * np.exp(-np.multiply.outer(log_growth, years))).sum(axis=-1)

    grid = np.linspace(*_LOG_GROWTH_RANGE, _GRID)
    signs = np.sign(npv(grid))
    signs[signs == 0] = 1
    crossings = np.flatnonzero(signs[:-1] != signs[1:])
    if len(crossings) == 0:
        raise MissingData("there is no rate of return at which these cash flows net to zero")
    if len(crossings) > 1:
        raise MissingData("more than one rate of return nets these cash flows to zero, so the IRR is not defined")
    lo, hi = grid[crossings[0]], grid[crossings[0] + 1]
    lo_sign = signs[crossings[0]]
    for _ in range(100):
        mid = (lo + hi) / 2
        if (1 if npv(mid) >= 0 else -1) == lo_sign:
            lo = mid
        else:
            hi = mid
    return math.expm1((lo + hi) / 2)
