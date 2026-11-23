"""Risk analytics: drawdowns on a wealth series; VaR, CVaR, beta, alpha and capture on return series.

A wealth series is any positive value-over-time series where dividends are
reinvested: a total-return index, a portfolio value. Its first value is the
starting point, so a loss on the first day already counts as a drawdown.

Return series are simple periodic (daily) returns indexed by date, as built by
``performance.total_returns``; a portfolio's return series works the same way.
VaR and CVaR are one-period (daily) figures reported as positive losses.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from statistics import NormalDist

import pandas as pd

from sextant_compute.analytics.errors import MissingData
from sextant_compute.analytics.performance import TRADING_DAYS, periodic_rate


def _require(wealth: pd.Series) -> pd.Series:
    clean = wealth.dropna()
    if len(clean) < 2:
        raise MissingData(f"needs at least 2 daily prices, got {len(clean)}")
    return clean


def drawdown(wealth: pd.Series) -> pd.Series:
    """Underwater curve: wealth / running peak - 1 (0 at a new high, negative below it)."""
    w = _require(wealth)
    return w / w.cummax() - 1


@dataclass(frozen=True)
class MaxDrawdown:
    depth: float
    """Largest peak-to-trough fall as a positive decimal (0.45 = a 45% fall)."""
    peak: date
    """Last high before the fall (the drawdown's start)."""
    trough: date
    """Lowest point (the drawdown's end)."""
    recovery: date | None
    """First day back at the peak level, or None if not recovered within the series."""


def max_drawdown(wealth: pd.Series) -> MaxDrawdown:
    underwater = drawdown(wealth)
    trough_ts = underwater.idxmin()
    before = underwater.loc[:trough_ts]
    peak_ts = before[before >= 0].index[-1]
    after = underwater.loc[trough_ts:]
    recovered = after[after >= 0]
    return MaxDrawdown(
        depth=-float(underwater.loc[trough_ts]),
        peak=pd.Timestamp(peak_ts).date(),
        trough=pd.Timestamp(trough_ts).date(),
        recovery=pd.Timestamp(recovered.index[0]).date() if not recovered.empty else None,
    )


def aligned(returns: pd.Series, benchmark_returns: pd.Series) -> tuple[pd.Series, pd.Series]:
    """The two return series on the dates where both have a value (at least 2 of them)."""
    both = pd.concat([returns, benchmark_returns], axis=1, join="inner").dropna()
    if len(both) < 2:
        raise MissingData(f"needs at least 2 daily returns on dates shared with the benchmark, got {len(both)}")
    return both.iloc[:, 0], both.iloc[:, 1]


def beta(returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """OLS beta of ``returns`` on ``benchmark_returns``: Cov(r, b) / Var(b), both ddof=1.

    Raw (not excess) simple returns, on the dates where both series have a value.
    """
    r, b = aligned(returns, benchmark_returns)
    variance = float(b.var(ddof=1))
    if variance == 0:
        raise MissingData("the benchmark's returns do not vary, so beta is undefined")
    return float(r.cov(b, ddof=1)) / variance


def capm_alpha(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = TRADING_DAYS,
) -> float:
    """Annualized CAPM (Jensen's) alpha: ``(mean(r - rf) - beta * mean(b - rf)) * periods_per_year``.

    The intercept of the OLS regression of excess returns on the benchmark's excess
    returns, on shared dates. ``risk_free_rate`` is an effective annual rate (see
    ``performance.periodic_rate``).
    """
    r, b = aligned(returns, benchmark_returns)
    slope = beta(r, b)
    rf = periodic_rate(risk_free_rate, periods_per_year)
    return (float((r - rf).mean()) - slope * float((b - rf).mean())) * periods_per_year


def _capture(returns: pd.Series, benchmark_returns: pd.Series, *, up: bool) -> float:
    r, b = aligned(returns, benchmark_returns)
    days = b > 0 if up else b < 0
    if not days.any():
        side = "rose" if up else "fell"
        raise MissingData(f"the benchmark never {side} on a shared date, so the capture ratio is undefined")
    return float(r[days].mean()) / float(b[days].mean())


def upside_capture(returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """Mean return on the benchmark's up days over the benchmark's mean return on those days.

    Arithmetic daily means (1.0 = moves fully with the benchmark on up days).
    """
    return _capture(returns, benchmark_returns, up=True)


def downside_capture(returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """Mean return on the benchmark's down days over the benchmark's mean return on those days.

    Below 1.0 means the ticker fell less than the benchmark on its down days.
    """
    return _capture(returns, benchmark_returns, up=False)


def treynor_ratio(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = TRADING_DAYS,
) -> float:
    """Annualized mean excess return per unit of beta: ``mean(r - rf) * periods_per_year / beta``.

    Mean and beta on the dates shared with the benchmark.
    """
    r, b = aligned(returns, benchmark_returns)
    slope = beta(r, b)
    if slope == 0:
        raise MissingData("beta to the benchmark is 0, so the Treynor ratio is undefined")
    rf = periodic_rate(risk_free_rate, periods_per_year)
    return float((r - rf).mean()) * periods_per_year / slope


def information_ratio(
    returns: pd.Series, benchmark_returns: pd.Series, periods_per_year: int = TRADING_DAYS
) -> float:
    """Annualized mean active return over tracking error.

    Active return a = r - b on shared dates; IR = ``mean(a) / std(a, ddof=1) * sqrt(periods_per_year)``.
    """
    r, b = aligned(returns, benchmark_returns)
    active = r - b
    tracking_error = float(active.std(ddof=1))
    if tracking_error == 0:
        raise MissingData("returns match the benchmark exactly (no tracking error), so the information ratio is undefined")
    return float(active.mean()) / tracking_error * math.sqrt(periods_per_year)


def _tail(returns: pd.Series, confidence: float) -> pd.Series:
    """The ``k = ceil(n * (1 - confidence))`` worst returns, worst first."""
    if not 0 < confidence < 1:
        raise ValueError(f"confidence must be between 0 and 1, got {confidence}")
    clean = returns.dropna()
    tail_probability = 1 - confidence
    # Round away float noise so that e.g. 20 * 0.05 counts as exactly 1 observation.
    needed = math.ceil(round(1 / tail_probability, 9))
    if len(clean) < needed:
        raise MissingData(
            f"needs at least {needed} daily returns for a {confidence:.1%} VaR, got {len(clean)}"
        )
    k = math.ceil(round(len(clean) * tail_probability, 9))
    return clean.sort_values().iloc[:k]


def historical_var(returns: pd.Series, confidence: float = 0.95) -> float:
    """Historical Value at Risk over one period, as a positive loss (0.03 = a 3% loss).

    The empirical (1 - confidence) quantile without interpolation: with n returns
    sorted ascending, VaR = -r_(k) where k = ceil(n * (1 - confidence)). Needs
    k >= 1, i.e. at least 1 / (1 - confidence) returns. Negative if even the
    tail return is a gain.
    """
    return -float(_tail(returns, confidence).iloc[-1])


def historical_cvar(returns: pd.Series, confidence: float = 0.95) -> float:
    """Historical CVaR (expected shortfall): minus the mean of the k worst returns.

    Same k and sign convention as ``historical_var``, so CVaR >= VaR always.
    """
    return -float(_tail(returns, confidence).mean())


_NORMAL = NormalDist()


@dataclass(frozen=True)
class _Moments:
    mean: float
    std: float
    """Sample standard deviation (ddof=1)."""
    skew: float
    """Population skewness m3 / m2^1.5."""
    excess_kurtosis: float
    """Population excess kurtosis m4 / m2^2 - 3."""


def _moments(returns: pd.Series, *, higher: bool) -> _Moments:
    clean = returns.dropna()
    needed = 4 if higher else 2
    if len(clean) < needed:
        raise MissingData(f"needs at least {needed} daily returns, got {len(clean)}")
    mean = float(clean.mean())
    std = float(clean.std(ddof=1))
    if not higher:
        return _Moments(mean, std, 0.0, 0.0)
    centered = clean - mean
    m2 = float((centered**2).mean())
    if m2 == 0:
        raise MissingData("returns do not vary, so skewness and kurtosis are undefined")
    m3 = float((centered**3).mean())
    m4 = float((centered**4).mean())
    return _Moments(mean, std, m3 / m2**1.5, m4 / m2**2 - 3)


def _tail_z(confidence: float) -> tuple[float, float, float]:
    """``(z, phi(z), alpha)`` for the lower tail: alpha = 1 - confidence, z = Phi^-1(alpha) < 0."""
    if not 0 < confidence < 1:
        raise ValueError(f"confidence must be between 0 and 1, got {confidence}")
    alpha = 1 - confidence
    z = _NORMAL.inv_cdf(alpha)
    return z, _NORMAL.pdf(z), alpha


def _cornish_fisher(x: float, m: _Moments) -> float:
    """Cornish-Fisher adjusted quantile of a standardized return for standard normal quantile ``x``."""
    s, k = m.skew, m.excess_kurtosis
    return x + (x**2 - 1) * s / 6 + (x**3 - 3 * x) * k / 24 - (2 * x**3 - 5 * x) * s**2 / 36


def parametric_var(returns: pd.Series, confidence: float = 0.95) -> float:
    """Normal (variance-covariance) VaR as a positive loss: ``-(mean + z * std)``, z = Phi^-1(1 - confidence).

    Sample mean and standard deviation (ddof=1) of the returns.
    """
    m = _moments(returns, higher=False)
    z, _, _ = _tail_z(confidence)
    return -(m.mean + z * m.std)


def parametric_cvar(returns: pd.Series, confidence: float = 0.95) -> float:
    """Normal expected shortfall as a positive loss: ``-(mean - std * phi(z) / (1 - confidence))``."""
    m = _moments(returns, higher=False)
    z, density, alpha = _tail_z(confidence)
    return -(m.mean - m.std * density / alpha)


def cornish_fisher_var(returns: pd.Series, confidence: float = 0.95) -> float:
    """Modified VaR: the normal quantile adjusted for sample skewness S and excess kurtosis K.

    ``z_cf = z + (z^2 - 1) S / 6 + (z^3 - 3z) K / 24 - (2z^3 - 5z) S^2 / 36``;
    VaR = ``-(mean + z_cf * std)``. Equal to ``parametric_var`` when S = K = 0.
    """
    m = _moments(returns, higher=True)
    z, _, _ = _tail_z(confidence)
    return -(m.mean + _cornish_fisher(z, m) * m.std)


def cornish_fisher_cvar(returns: pd.Series, confidence: float = 0.95) -> float:
    """Modified expected shortfall: the mean of the Cornish-Fisher quantile over the lower tail.

    ``E[z_cf(Z) | Z < z]`` for a standard normal Z, from the truncated normal moments
    ``E[Z | Z < z] = -phi/alpha``, ``E[Z^2 | .] = 1 - z phi/alpha``, ``E[Z^3 | .] = -(z^2 + 2) phi/alpha``.
    CVaR = ``-(mean + E[z_cf] * std)``. Equal to ``parametric_cvar`` when S = K = 0.
    """
    m = _moments(returns, higher=True)
    z, density, alpha = _tail_z(confidence)
    m1 = -density / alpha
    m2 = 1 - z * density / alpha
    m3 = -(z**2 + 2) * density / alpha
    s, k = m.skew, m.excess_kurtosis
    expected = m1 + (m2 - 1) * s / 6 + (m3 - 3 * m1) * k / 24 - (2 * m3 - 5 * m1) * s**2 / 36
    return -(m.mean + expected * m.std)
