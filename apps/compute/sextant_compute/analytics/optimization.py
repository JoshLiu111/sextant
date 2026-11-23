"""Long-only mean-variance optimisation (Markowitz) on historical daily returns.

Inputs are estimated from simple daily returns and annualized with 252 days:
expected return ``mu = mean * 252`` (arithmetic) and covariance ``S = cov(ddof=1) * 252``.
A portfolio's expected return is ``w . mu``, its volatility ``sqrt(w' S w)`` and its
Sharpe ratio ``(w . mu - rf) / volatility`` with ``rf`` an annual decimal.

Every portfolio is long-only and fully invested (``w >= 0``, ``sum w = 1``). Weights
from the solver are clipped at 0 and renormalized, so they hold exactly.

- Minimum variance: ``min w' S w``.
- Maximum Sharpe: the convex reformulation ``min y' S y`` s.t. ``(mu - rf) . y = 1``,
  ``y >= 0``, then ``w = y / sum y``. It exists only if some holding's expected return
  beats ``rf``.
- Frontier: minimum variance at evenly spaced target returns from the minimum-variance
  portfolio's return up to the highest single-asset return (where the frontier ends at
  100% in that asset).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from sextant_compute.analytics.errors import MissingData
from sextant_compute.analytics.performance import TRADING_DAYS

FRONTIER_POINTS = 30
_TOLERANCE = 1e-12


@dataclass(frozen=True)
class Allocation:
    weights: pd.Series
    """Long-only weights by ticker, summing to 1."""
    expected_return: float
    volatility: float

    def sharpe(self, risk_free_rate: float) -> float:
        if self.volatility <= 0:
            raise MissingData("the portfolio does not vary")
        return (self.expected_return - risk_free_rate) / self.volatility


@dataclass(frozen=True)
class Inputs:
    mu: np.ndarray
    cov: np.ndarray
    tickers: tuple[str, ...]

    def allocation(self, w: np.ndarray) -> Allocation:
        w = np.clip(w, 0, None)
        w = w / w.sum()
        variance = max(float(w @ self.cov @ w), 0.0)
        return Allocation(pd.Series(w, index=list(self.tickers)), float(w @ self.mu), variance**0.5)


def estimate(returns: pd.DataFrame) -> Inputs:
    """Annualized mean returns and covariance from simple daily returns (one column per asset)."""
    clean = returns.dropna()
    if returns.shape[1] < 2:
        raise MissingData("needs at least two holdings")
    if len(clean) < 2:
        raise MissingData(f"needs at least 2 daily returns, got {len(clean)}")
    return Inputs(
        mu=clean.mean().to_numpy() * TRADING_DAYS,
        cov=clean.cov(ddof=1).to_numpy() * TRADING_DAYS,
        tickers=tuple(clean.columns),
    )


def _min_quadratic(cov: np.ndarray, constraints: list[dict], start: np.ndarray) -> np.ndarray | None:
    """``min x' cov x`` for ``x >= 0`` under ``constraints``; None if the solver fails."""
    scale = float(np.trace(cov)) / len(cov) or 1.0
    q = cov / scale  # well-conditioned objective for the solver's absolute tolerance
    result = minimize(
        lambda x: x @ q @ x,
        start,
        jac=lambda x: 2 * q @ x,
        bounds=[(0, None)] * len(start),
        constraints=constraints,
        method="SLSQP",
        options={"ftol": 1e-15, "maxiter": 1000},
    )
    return result.x if result.success else None


def _fully_invested(n: int) -> dict:
    return {"type": "eq", "fun": lambda w: w.sum() - 1, "jac": lambda w: np.ones(n)}


def min_variance(inputs: Inputs) -> Allocation:
    n = len(inputs.tickers)
    w = _min_quadratic(inputs.cov, [_fully_invested(n)], np.full(n, 1 / n))
    if w is None:
        raise MissingData("the optimiser did not converge on a minimum-variance portfolio")
    return inputs.allocation(w)


def max_sharpe(inputs: Inputs, risk_free_rate: float) -> Allocation:
    excess = inputs.mu - risk_free_rate
    if not (excess > _TOLERANCE).any():
        raise MissingData("no holding's expected return beats the risk-free rate")
    n = len(inputs.tickers)
    start = np.where(excess > 0, 1.0, 0.0)
    start = start / (excess @ start)
    scaled_to_one = {"type": "eq", "fun": lambda y: excess @ y - 1, "jac": lambda y: excess}
    y = _min_quadratic(inputs.cov, [scaled_to_one], start)
    if y is None or y.sum() <= 0:
        raise MissingData("the optimiser did not converge on a maximum-Sharpe portfolio")
    best = inputs.allocation(y)
    # Never report a "maximum" that some single holding beats (guards against solver slack).
    for i in range(n):
        single = inputs.allocation(np.eye(n)[i])
        if single.volatility > 0 and single.sharpe(risk_free_rate) > best.sharpe(risk_free_rate):
            best = single
    return best


def frontier(inputs: Inputs, lowest: Allocation, points: int = FRONTIER_POINTS) -> list[Allocation]:
    """The efficient frontier from ``lowest`` (the minimum-variance portfolio) up to the top-return asset.

    Sorted by volatility; the first point is ``lowest`` itself.
    """
    n = len(inputs.tickers)
    top = float(inputs.mu.max())
    out = [lowest]
    if top - lowest.expected_return <= _TOLERANCE * max(1.0, abs(top)):
        return out
    previous = lowest.weights.to_numpy()
    for target in np.linspace(lowest.expected_return, top, points)[1:-1]:
        on_target = {"type": "eq", "fun": lambda w, t=target: inputs.mu @ w - t, "jac": lambda w: inputs.mu}
        w = _min_quadratic(inputs.cov, [_fully_invested(n), on_target], previous)
        if w is None:
            continue
        previous = w
        out.append(inputs.allocation(w))
    out.append(inputs.allocation(np.eye(n)[int(np.argmax(inputs.mu))]))  # the top end: all in the top asset
    return sorted(out, key=lambda a: a.volatility)
