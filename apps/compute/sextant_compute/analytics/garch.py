"""GARCH(1,1) conditional volatility of a daily return series.

Model (Bollerslev 1986), on simple daily returns r_t:

    r_t = mu + e_t,   e_t = sqrt(h_t) * z_t,   z_t ~ N(0, 1)
    h_t = omega + alpha * e_{t-1}^2 + beta * h_{t-1}

``mu`` is the sample mean; ``omega``, ``alpha`` and ``beta`` maximise the Gaussian
log-likelihood, with ``h_1`` set to the sample variance. The search runs over
``omega > 0``, ``alpha, beta >= 0`` and ``alpha + beta < 1`` (covariance
stationary), so the long-run variance ``omega / (1 - alpha - beta)`` always exists.

The optimiser is a small Nelder-Mead (numpy only; the service has no scipy).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from sextant_compute.analytics.errors import MetricError, MissingData
from sextant_compute.analytics.performance import TRADING_DAYS

MIN_OBSERVATIONS = 250
"""About one trading year: fewer returns cannot separate alpha from beta."""

# Returns are fitted in percent, so omega is O(0.01..1) instead of O(1e-6).
_SCALE = 100.0
_BLOCK = 32


@dataclass(frozen=True)
class GarchFit:
    omega: float
    """Constant term of the daily variance recursion, in decimal^2 (daily)."""
    alpha: float
    """Weight on yesterday's squared shock (reaction)."""
    beta: float
    """Weight on yesterday's variance (memory)."""
    log_likelihood: float
    conditional_variance: pd.Series
    """h_t for each return date: the variance of r_t given the returns before it."""
    next_variance: float
    """The one-day-ahead forecast h_{T+1} after the last return."""
    observations: int

    @property
    def persistence(self) -> float:
        return self.alpha + self.beta

    @property
    def long_run_variance(self) -> float:
        """Unconditional daily variance ``omega / (1 - alpha - beta)``."""
        return self.omega / (1 - self.persistence)


def _variances(e2: np.ndarray, omega: float, alpha: float, beta: float, h0: float) -> np.ndarray:
    """h_0 = h0, h_t = beta * h_{t-1} + x_t with x_t = omega + alpha * e2_{t-1}, in blocks of numpy.

    Within a block of _BLOCK steps starting after h_s, h_{s+1+j} = beta^(j+1) h_s + y_j with
    y_j = sum_{i<=j} beta^(j-i) x_{s+1+i}: one matrix product for every block at once, then a
    short loop carries h_s from block to block. Same numbers as the plain loop, ~20x faster.
    """
    n = len(e2)
    x = omega + alpha * e2[:-1]  # x_1 .. x_{n-1}
    blocks = -(-len(x) // _BLOCK)
    padded = np.zeros(blocks * _BLOCK)
    padded[: len(x)] = x
    lag = np.arange(_BLOCK)[:, None] - np.arange(_BLOCK)[None, :]
    decay = np.where(lag >= 0, beta ** np.maximum(lag, 0), 0.0)  # decay[j, i] = beta^(j-i), i <= j
    local = padded.reshape(blocks, _BLOCK) @ decay.T
    lead = beta ** np.arange(1, _BLOCK + 1)
    out = np.empty((blocks, _BLOCK))
    carry = h0
    for k in range(blocks):
        out[k] = lead * carry + local[k]
        carry = out[k, -1]
    return np.concatenate(([h0], out.ravel()[: n - 1]))


def _negative_log_likelihood(e2: np.ndarray, omega: float, alpha: float, beta: float, h0: float) -> float:
    h = _variances(e2, omega, alpha, beta, h0)
    return 0.5 * float(np.sum(np.log(h) + e2 / h) + len(e2) * math.log(2 * math.pi))


def _params(u: np.ndarray) -> tuple[float, float, float]:
    """Unconstrained (log omega, logit persistence, logit alpha share) -> (omega, alpha, beta)."""
    omega = math.exp(u[0])
    persistence = 1 / (1 + math.exp(-u[1]))
    share = 1 / (1 + math.exp(-u[2]))
    return omega, persistence * share, persistence * (1 - share)


def _logit(p: float) -> float:
    return math.log(p / (1 - p))


def _nelder_mead(f: Callable[[np.ndarray], float], x0: np.ndarray, step: float = 0.5,
                 max_iter: int = 2000, tol: float = 1e-9) -> tuple[np.ndarray, float, bool]:
    """Minimise ``f``; returns ``(x, f(x), converged)``."""
    n = len(x0)
    simplex = [x0] + [x0 + step * np.eye(n)[i] for i in range(n)]
    values = [f(x) for x in simplex]
    for _ in range(max_iter):
        order = np.argsort(values)
        simplex = [simplex[i] for i in order]
        values = [values[i] for i in order]
        if abs(values[-1] - values[0]) <= tol * (1 + abs(values[0])):
            return simplex[0], values[0], True
        centroid = np.mean(simplex[:-1], axis=0)
        worst = simplex[-1]
        reflected = centroid + (centroid - worst)
        fr = f(reflected)
        if fr < values[0]:
            expanded = centroid + 2 * (centroid - worst)
            fe = f(expanded)
            simplex[-1], values[-1] = (expanded, fe) if fe < fr else (reflected, fr)
        elif fr < values[-2]:
            simplex[-1], values[-1] = reflected, fr
        else:
            inside = fr >= values[-1]
            contracted = centroid + 0.5 * ((worst if inside else reflected) - centroid)
            fc = f(contracted)
            if fc < min(fr, values[-1]):
                simplex[-1], values[-1] = contracted, fc
            else:
                best = simplex[0]
                simplex = [best] + [best + 0.5 * (x - best) for x in simplex[1:]]
                values = [values[0]] + [f(x) for x in simplex[1:]]
    best = int(np.argmin(values))
    return simplex[best], values[best], False


def fit_garch(returns: pd.Series) -> GarchFit:
    """Maximum-likelihood GARCH(1,1) fit (see the module docstring)."""
    clean = returns.dropna()
    if len(clean) < MIN_OBSERVATIONS:
        raise MissingData(
            f"needs at least {MIN_OBSERVATIONS} daily returns for a GARCH(1,1) fit, got {len(clean)}"
        )
    scaled = (clean - clean.mean()) * _SCALE
    variance = float((scaled**2).mean())
    if variance == 0:
        raise MissingData("returns do not vary, so there is no volatility to model")
    e2 = scaled.to_numpy(dtype=float) ** 2

    def objective(u: np.ndarray) -> float:
        omega, alpha, beta = _params(u)
        return _negative_log_likelihood(e2, omega, alpha, beta, variance)

    start = np.array([math.log(variance * 0.05), _logit(0.95), _logit(0.05 / 0.95)])
    u, nll, converged = _nelder_mead(objective, start)
    if not converged or not math.isfinite(nll):
        raise MetricError("the GARCH(1,1) likelihood search did not converge")
    omega, alpha, beta = _params(u)
    h = _variances(e2, omega, alpha, beta, variance)
    next_h = omega + alpha * e2[-1] + beta * h[-1]
    s2 = _SCALE**2
    return GarchFit(
        omega=omega / s2,
        alpha=alpha,
        beta=beta,
        # Back to decimal returns: density(r) = density(r * _SCALE) * _SCALE.
        log_likelihood=-nll + len(e2) * math.log(_SCALE),
        conditional_variance=pd.Series(h / s2, index=clean.index),
        next_variance=next_h / s2,
        observations=len(e2),
    )


def annualized_volatility(daily_variance: float | pd.Series, periods_per_year: int = TRADING_DAYS):
    """sqrt(daily variance * periods_per_year), for a number or a Series."""
    if isinstance(daily_variance, pd.Series):
        return np.sqrt(daily_variance * periods_per_year)
    return math.sqrt(daily_variance * periods_per_year)
