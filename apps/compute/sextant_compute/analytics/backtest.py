"""VaR backtesting: rolling one-day VaR forecasts, breach counts and Kupiec's test.

Each day t after the first ``window`` returns gets a VaR forecast estimated from
the ``window`` returns before it (no look-ahead). A breach is a day whose loss
exceeds that forecast (``r_t < -VaR_t``, strictly). The three methods match the
static ones in ``analytics.risk``:

- ``historical``: ``-r_(k)``, the k-th worst return of the window, k = ceil(window * (1 - c)).
- ``parametric``: ``-(mean + z * std)`` (normal, std ddof=1).
- ``cornish_fisher``: the normal quantile adjusted for the window's population
  skewness and excess kurtosis.

Kupiec's proportion-of-failures test (1995): with n forecast days, x breaches and
expected breach rate p = 1 - c,

    LR = -2 ln[(1 - p)^(n - x) p^x] + 2 ln[(1 - x/n)^(n - x) (x/n)^x]

is chi-squared with 1 degree of freedom under the null that the model's breach
rate is p. The p-value is ``erfc(sqrt(LR / 2))`` (the chi2(1) survival function).
The model is rejected when the p-value is below ``1 - c``: the test is read at
the same confidence level as the VaR.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist
from typing import Literal

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from sextant_compute.analytics.errors import MissingData

VarMethod = Literal["historical", "parametric", "cornish_fisher"]
VAR_METHODS: tuple[VarMethod, ...] = ("historical", "parametric", "cornish_fisher")

WINDOW = 250
"""Estimation window in trading days (about one year), the Basel convention."""


@dataclass(frozen=True)
class Backtest:
    method: VarMethod
    window: int
    observations: int
    """Forecast days tested (n)."""
    breaches: int
    """Days whose loss exceeded the forecast VaR (x)."""
    confidence: float

    @property
    def expected_breaches(self) -> float:
        return self.observations * (1 - self.confidence)

    @property
    def breach_rate(self) -> float:
        return self.breaches / self.observations

    @property
    def kupiec_statistic(self) -> float:
        n, x, p = self.observations, self.breaches, 1 - self.confidence
        observed = x / n

        def log_likelihood(rate: float) -> float:
            # 0 * ln(0) = 0: a rate of 0 (or 1) with no breaches (or no non-breaches) is certain.
            hits = x * math.log(rate) if x else 0.0
            misses = (n - x) * math.log(1 - rate) if n - x else 0.0
            return hits + misses

        return max(0.0, -2 * (log_likelihood(p) - log_likelihood(observed)))

    @property
    def p_value(self) -> float:
        return math.erfc(math.sqrt(self.kupiec_statistic / 2))

    @property
    def significance(self) -> float:
        return 1 - self.confidence

    @property
    def rejected(self) -> bool:
        return self.p_value < self.significance


def _windows(returns: pd.Series, window: int) -> tuple[np.ndarray, np.ndarray]:
    """(estimation windows, the return each one forecasts): row i is r[i:i+window], forecasting r[i+window]."""
    r = returns.dropna().to_numpy(dtype=float)
    if len(r) < window + 1:
        raise MissingData(
            f"needs at least {window + 1} daily returns to backtest a {window}-day VaR, got {len(r)}"
        )
    return sliding_window_view(r[:-1], window), r[window:]


def _forecasts(windows: np.ndarray, method: VarMethod, confidence: float) -> np.ndarray:
    alpha = 1 - confidence
    size = windows.shape[1]
    if method == "historical":
        needed = math.ceil(round(1 / alpha, 9))
        if size < needed:
            raise MissingData(
                f"a {confidence:.1%} historical VaR needs at least {needed} returns per window; the window is {size}"
            )
        k = math.ceil(round(size * alpha, 9))
        return -np.partition(windows, k - 1, axis=1)[:, k - 1]
    mean = windows.mean(axis=1)
    std = windows.std(axis=1, ddof=1)
    z = NormalDist().inv_cdf(alpha)
    if method == "parametric":
        return -(mean + z * std)
    centered = windows - mean[:, None]
    m2 = (centered**2).mean(axis=1)
    if np.any(m2 == 0):
        raise MissingData("returns do not vary within an estimation window, so skewness and kurtosis are undefined")
    s = (centered**3).mean(axis=1) / m2**1.5
    k = (centered**4).mean(axis=1) / m2**2 - 3
    z_cf = z + (z**2 - 1) * s / 6 + (z**3 - 3 * z) * k / 24 - (2 * z**3 - 5 * z) * s**2 / 36
    return -(mean + z_cf * std)


def backtest_var(returns: pd.Series, method: VarMethod, confidence: float = 0.95, window: int = WINDOW) -> Backtest:
    """Rolling one-day VaR backtest of ``method`` (see the module docstring)."""
    if not 0 < confidence < 1:
        raise ValueError(f"confidence must be between 0 and 1, got {confidence}")
    windows, realized = _windows(returns, window)
    var = _forecasts(windows, method, confidence)
    return Backtest(
        method=method,
        window=window,
        observations=len(realized),
        breaches=int(np.sum(realized < -var)),
        confidence=confidence,
    )
