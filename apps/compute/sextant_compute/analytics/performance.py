"""Return and volatility analytics on daily return series.

Inputs are pandas Series of *simple* periodic returns indexed by date (build them
with ``total_returns``). Annualization assumes ``periods_per_year`` periods
(252 trading days by default).
"""

from __future__ import annotations

import math

import pandas as pd

from sextant_compute.analytics.errors import MissingData
from sextant_compute.analytics.periods import period_name

TRADING_DAYS = 252


def total_returns(close: pd.Series, dividend: pd.Series | None = None) -> pd.Series:
    """Simple daily total returns: ``(close_t + dividend_t) / close_{t-1} - 1``.

    ``dividend_t`` is the cash dividend going ex on day t (0 otherwise); ``close``
    is the unadjusted price. The first day has no return and is dropped.
    """
    income = dividend if dividend is not None else 0.0
    return ((close + income) / close.shift(1) - 1).iloc[1:]


def total_return_index(close: pd.Series, dividend: pd.Series | None = None) -> pd.Series:
    """Wealth from investing 1 at the first close and reinvesting dividends (1.0 on day one)."""
    if close.empty:
        raise MissingData("needs at least 1 daily price")
    growth = (1 + total_returns(close, dividend)).cumprod()
    return pd.concat([pd.Series([1.0], index=close.index[:1]), growth])


def _require(returns: pd.Series, minimum: int, periods_per_year: int = TRADING_DAYS) -> pd.Series:
    clean = returns.dropna()
    if len(clean) < minimum:
        raise MissingData(f"needs at least {minimum} {period_name(periods_per_year)} returns, got {len(clean)}")
    return clean


def annualized_return(returns: pd.Series, periods_per_year: int = TRADING_DAYS) -> float:
    """Compound annual growth rate: ``prod(1 + r) ** (periods_per_year / n) - 1``."""
    r = _require(returns, 1, periods_per_year)
    growth = float((1 + r).prod())
    if growth <= 0:
        raise MissingData("the position was wiped out, so there is no compound annual rate")
    return growth ** (periods_per_year / len(r)) - 1


def annualized_volatility(returns: pd.Series, periods_per_year: int = TRADING_DAYS) -> float:
    """Sample standard deviation of returns (ddof=1) scaled by ``sqrt(periods_per_year)``."""
    r = _require(returns, 2, periods_per_year)
    return float(r.std(ddof=1)) * math.sqrt(periods_per_year)


def periodic_rate(annual_rate: float, periods_per_year: int = TRADING_DAYS) -> float:
    """De-annualize an effective annual rate: ``(1 + annual) ** (1 / periods_per_year) - 1``."""
    return (1 + annual_rate) ** (1 / periods_per_year) - 1


def _excess(returns: pd.Series, risk_free_rate: float, periods_per_year: int) -> pd.Series:
    return _require(returns, 2, periods_per_year) - periodic_rate(risk_free_rate, periods_per_year)


def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0, periods_per_year: int = TRADING_DAYS) -> float:
    """Annualized Sharpe ratio: ``mean(excess) / std(excess, ddof=1) * sqrt(periods_per_year)``.

    ``risk_free_rate`` is an effective annual rate (decimal), de-annualized with
    ``periodic_rate`` and subtracted from every return.
    """
    excess = _excess(returns, risk_free_rate, periods_per_year)
    std = float(excess.std(ddof=1))
    if std == 0:
        raise MissingData("returns do not vary, so the Sharpe ratio is undefined")
    return float(excess.mean()) / std * math.sqrt(periods_per_year)


def sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.0, periods_per_year: int = TRADING_DAYS) -> float:
    """Annualized Sortino ratio: ``mean(excess) / downside_deviation * sqrt(periods_per_year)``.

    Downside deviation = ``sqrt(mean(min(excess, 0) ** 2))`` over *all* observations
    (Sortino & Price 1994), with the risk-free rate as the target return.
    """
    excess = _excess(returns, risk_free_rate, periods_per_year)
    downside = math.sqrt(float((excess.clip(upper=0) ** 2).mean()))
    if downside == 0:
        raise MissingData("no daily return fell below the risk-free rate, so the Sortino ratio is undefined")
    return float(excess.mean()) / downside * math.sqrt(periods_per_year)
