"""Deterministic synthetic market data for fictional tickers.

``generate_universe(seed)`` always returns the same daily OHLCV + dividend frames
for the same seed (numpy PCG64). The whole universe is generated together, in a
fixed order, so a ticker's series never depends on which other tickers a caller
asks for.

Model (per trading day t, log total return):

    market:  m_t = drift_m/252 + eps_m,t
    ticker:  r_t = drift/252 + beta * eps_m,t + eps_i,t + (jumps_t - E[jumps])

``eps`` are GARCH(1,1) shocks (volatility clustering) whose unconditional daily
variance is set so each ticker's *total* annualized volatility (market part +
idiosyncratic part + jumps) equals its configured ``annual_vol``. Correlation
with the benchmark follows from the one-factor structure:
``corr = beta * vol_market / annual_vol``.

A ``Crash`` replaces the returns in its window with a deterministic straight-line
fall (in log terms) of ``depth``, then a straight-line climb back to the pre-crash
level. Both windows are noise-free, so over a range containing them the max
drawdown is exactly ``depth`` (up to price rounding), peaking on the last trading
day before ``start`` and bottoming on the last crash day.

Dividends are paid quarterly (first trading day on or after the 15th of
Mar/Jun/Sep/Dec) at ``dividend_yield / 4`` of the previous close. The price drops
by the dividend on the ex-date, so ``(close_t + dividend_t) / close_{t-1}`` is the
modelled total return.

The published ``PERSONALITIES`` are the ground truth that tests check
analytics against. Change the generator and you change every demo number:
bump ``GENERATOR_VERSION`` (it is part of the cache key).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

GENERATOR_VERSION = 1
DEFAULT_SEED = 17
HISTORY_START = date(2016, 1, 4)
HISTORY_END = date(2025, 12, 31)
TRADING_DAYS = 252
BENCHMARK = "DEMO-MKT"

# GARCH(1,1) persistence shared by every series (alpha + beta = 0.96).
_GARCH_ALPHA = 0.06
_GARCH_BETA = 0.90

COLUMNS = ["open", "high", "low", "close", "volume", "dividend"]


@dataclass(frozen=True)
class Crash:
    """A deterministic fall of ``depth`` (0.45 = -45%) over ``days`` trading days from ``start``,
    then a deterministic climb back to the pre-crash peak over ``recovery_days`` trading days."""

    start: date
    days: int
    depth: float
    recovery_days: int


@dataclass(frozen=True)
class Personality:
    name: str
    description: str
    start_price: float
    drift: float
    """Expected annual log return outside the crash windows."""
    annual_vol: float
    """Total annualized volatility of daily returns outside the crash windows."""
    beta: float
    """Beta to the benchmark ``DEMO-MKT``."""
    dividend_yield: float = 0.0
    jumps_per_year: float = 0.0
    jump_mean: float = 0.0
    jump_std: float = 0.0
    crash: Crash | None = None


PERSONALITIES: dict[str, Personality] = {
    "DEMO-MKT": Personality(
        name="Demo Market Index",
        description="The demo benchmark: a broad, moderately volatile market.",
        start_price=1000.0,
        drift=0.07,
        annual_vol=0.16,
        beta=1.0,
        dividend_yield=0.015,
    ),
    "DEMO-A": Personality(
        name="Steady Blue Chip Co.",
        description="Low-volatility blue chip with a reliable dividend.",
        start_price=80.0,
        drift=0.06,
        annual_vol=0.14,
        beta=0.7,
        dividend_yield=0.03,
    ),
    "DEMO-B": Personality(
        name="Rocket Growth Inc.",
        description="High-volatility growth stock with occasional jumps; no dividend.",
        start_price=40.0,
        drift=0.15,
        annual_vol=0.45,
        beta=1.4,
        jumps_per_year=4.0,
        jump_mean=0.0,
        jump_std=0.06,
    ),
    "DEMO-C": Personality(
        name="Index Tracker Holdings",
        description="Moves almost one-for-one with the market (correlation about 0.94).",
        start_price=120.0,
        drift=0.07,
        annual_vol=0.17,
        beta=1.0,
        dividend_yield=0.015,
    ),
    "DEMO-D": Personality(
        name="Crash & Recovery Corp.",
        description="Ordinary large cap hit by one injected 45% crash in March 2022, recovered by late 2022.",
        start_price=60.0,
        drift=0.08,
        annual_vol=0.22,
        beta=1.0,
        dividend_yield=0.01,
        crash=Crash(start=date(2022, 3, 1), days=30, depth=0.45, recovery_days=150),
    ),
    "DEMO-E": Personality(
        name="Defensive Utilities Ltd.",
        description="Low beta, low volatility, high dividend; barely tied to the market.",
        start_price=30.0,
        drift=0.04,
        annual_vol=0.12,
        beta=0.2,
        dividend_yield=0.045,
    ),
    "DEMO-F": Personality(
        name="Speculative Biotech plc",
        description="Very volatile, frequent large jumps and a negative drift.",
        start_price=15.0,
        drift=-0.05,
        annual_vol=0.60,
        beta=0.8,
        jumps_per_year=8.0,
        jump_mean=-0.01,
        jump_std=0.12,
    ),
}

# Generation order is fixed: never reorder, only append (or bump GENERATOR_VERSION).
_ORDER = ["DEMO-MKT", "DEMO-A", "DEMO-B", "DEMO-C", "DEMO-D", "DEMO-E", "DEMO-F"]


def trading_days() -> pd.DatetimeIndex:
    return pd.bdate_range(HISTORY_START, HISTORY_END, name="date")


def _garch_shocks(rng: np.random.Generator, n: int, daily_var: float) -> np.ndarray:
    """Zero-mean GARCH(1,1) shocks with unconditional variance ``daily_var``."""
    z = rng.standard_normal(n)
    omega = daily_var * (1 - _GARCH_ALPHA - _GARCH_BETA)
    out = np.empty(n)
    h = daily_var
    for t in range(n):
        out[t] = np.sqrt(h) * z[t]
        h = omega + _GARCH_ALPHA * out[t] ** 2 + _GARCH_BETA * h
    return out


def _jumps(rng: np.random.Generator, n: int, p: Personality) -> np.ndarray:
    """Compensated compound-Poisson jumps (zero mean): k jumps on a day sum to N(k*mean, k*std^2)."""
    lam = p.jumps_per_year / TRADING_DAYS
    counts = rng.poisson(lam, n)
    z = rng.standard_normal(n)
    return counts * p.jump_mean + np.sqrt(counts) * p.jump_std * z - lam * p.jump_mean


def _jump_daily_var(p: Personality) -> float:
    return p.jumps_per_year / TRADING_DAYS * (p.jump_mean**2 + p.jump_std**2)


def _log_returns(
    rng: np.random.Generator, dates: pd.DatetimeIndex, p: Personality, market_shocks: np.ndarray | None
) -> tuple[np.ndarray, np.ndarray]:
    """Daily log total returns; also returns this series' own shocks (the market's are reused)."""
    n = len(dates)
    total_var = p.annual_vol**2 / TRADING_DAYS
    if market_shocks is None:  # the benchmark itself
        own = _garch_shocks(rng, n, total_var - _jump_daily_var(p))
        systematic = np.zeros(n)
    else:
        market_var = PERSONALITIES[BENCHMARK].annual_vol ** 2 / TRADING_DAYS
        idio_var = total_var - p.beta**2 * market_var - _jump_daily_var(p)
        if idio_var <= 0:
            raise ValueError("personality is inconsistent: beta * market vol exceeds total vol")
        own = _garch_shocks(rng, n, idio_var)
        systematic = p.beta * market_shocks
    returns = p.drift / TRADING_DAYS + systematic + own + _jumps(rng, n, p)
    if p.crash is not None:
        start = dates.searchsorted(pd.Timestamp(p.crash.start))
        fall = np.log(1 - p.crash.depth)
        returns[start : start + p.crash.days] = fall / p.crash.days
        bottom = start + p.crash.days
        returns[bottom : bottom + p.crash.recovery_days] = -fall / p.crash.recovery_days
    return returns, own


def _dividend_dates(dates: pd.DatetimeIndex) -> np.ndarray:
    """Mask of ex-dividend days: first trading day on/after the 15th of Mar/Jun/Sep/Dec."""
    mask = np.zeros(len(dates), dtype=bool)
    for year in range(dates[0].year, dates[-1].year + 1):
        for month in (3, 6, 9, 12):
            i = dates.searchsorted(pd.Timestamp(year, month, 15))
            if i < len(dates):
                mask[i] = True
    return mask


def _frame(rng: np.random.Generator, dates: pd.DatetimeIndex, p: Personality, log_r: np.ndarray) -> pd.DataFrame:
    n = len(dates)
    ex_div = _dividend_dates(dates) if p.dividend_yield > 0 else np.zeros(n, dtype=bool)
    close = np.empty(n)
    dividend = np.zeros(n)
    prev = p.start_price
    for t in range(n):
        gross = prev * np.exp(log_r[t])
        if ex_div[t]:
            dividend[t] = prev * p.dividend_yield / 4
        close[t] = gross - dividend[t]
        prev = close[t]
    prev_close = np.concatenate(([p.start_price], close[:-1])) - dividend
    daily_sd = p.annual_vol / np.sqrt(TRADING_DAYS)
    open_ = prev_close * np.exp(rng.normal(0, 0.25 * daily_sd, n))
    top = np.maximum(open_, close) * np.exp(np.abs(rng.normal(0, 0.5 * daily_sd, n)))
    bottom = np.minimum(open_, close) * np.exp(-np.abs(rng.normal(0, 0.5 * daily_sd, n)))
    volume = np.round(1_000_000 * np.exp(rng.normal(0, 0.3, n)) * (1 + 20 * np.abs(log_r))).astype(np.int64)
    return pd.DataFrame(
        {
            "open": open_.round(4),
            "high": top.round(4),
            "low": bottom.round(4),
            "close": close.round(4),
            "volume": volume,
            "dividend": dividend.round(4),
        },
        index=dates,
    )


def generate_universe(seed: int = DEFAULT_SEED) -> dict[str, pd.DataFrame]:
    """Daily OHLCV + dividend frames (DatetimeIndex ``date``) for every demo ticker."""
    rng = np.random.default_rng(seed)
    dates = trading_days()
    market_returns, market_shocks = _log_returns(rng, dates, PERSONALITIES[BENCHMARK], None)
    out = {BENCHMARK: _frame(rng, dates, PERSONALITIES[BENCHMARK], market_returns)}
    for ticker in _ORDER[1:]:
        p = PERSONALITIES[ticker]
        log_r, _ = _log_returns(rng, dates, p, market_shocks)
        out[ticker] = _frame(rng, dates, p, log_r)
    return out
