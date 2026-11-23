"""Rolling-window statistics on daily return series.

Each value covers the ``window`` most recent daily returns up to and including
its date, so the first value lands on the window's last day. Same conventions as
the full-range metrics: volatility and Sharpe annualized with 252 trading days,
the risk-free rate de-annualized geometrically, beta as Cov / Var with ddof=1.
"""

from __future__ import annotations

import math

import pandas as pd

from sextant_compute.analytics.errors import MissingData
from sextant_compute.analytics.performance import TRADING_DAYS, periodic_rate


def _require(returns: pd.Series, window: int) -> pd.Series:
    clean = returns.dropna()
    if len(clean) < window:
        raise MissingData(f"needs at least {window} daily returns for a {window}-day rolling window, got {len(clean)}")
    return clean


def rolling_volatility(returns: pd.Series, window: int) -> pd.Series:
    r = _require(returns, window)
    return (r.rolling(window).std(ddof=1) * math.sqrt(TRADING_DAYS)).dropna()


def rolling_sharpe(returns: pd.Series, window: int, risk_free_rate: float = 0.0) -> pd.Series:
    """Annualized Sharpe ratio per window; windows whose returns do not vary are dropped."""
    excess = _require(returns, window) - periodic_rate(risk_free_rate)
    rolling = excess.rolling(window)
    std = rolling.std(ddof=1)
    sharpe = rolling.mean() / std.where(std > 0) * math.sqrt(TRADING_DAYS)
    return sharpe.dropna()


def rolling_beta(returns: pd.Series, benchmark_returns: pd.Series, window: int) -> pd.Series:
    """Beta per window, on the dates both series share; flat-benchmark windows are dropped."""
    both = pd.concat([returns, benchmark_returns], axis=1, join="inner").dropna()
    _require(both.iloc[:, 0], window)
    r, b = both.iloc[:, 0], both.iloc[:, 1]
    variance = b.rolling(window).var(ddof=1)
    return (r.rolling(window).cov(b, ddof=1) / variance.where(variance > 0)).dropna()
