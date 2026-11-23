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
from pandas.api.typing import Rolling

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


def _rolling(returns: pd.Series, window: int) -> tuple[Rolling, np.ndarray]:
    """Rolling windows over the returns, and the returns they forecast.

    The statistic at position j covers r[j - window + 1 .. j] and forecasts r[j + 1],
    so ``stat[window - 1 : -1]`` lines up with the returned ``r[window:]``.
    """
    r = returns.dropna().reset_index(drop=True).astype(float)
    if len(r) < window + 1:
        raise MissingData(
            f"needs at least {window + 1} daily returns to backtest a {window}-day VaR, got {len(r)}"
        )
    return r.rolling(window), r.to_numpy()[window:]


def _forecasts(rolling: Rolling, method: VarMethod, confidence: float, window: int) -> np.ndarray:
    """One VaR per window, aligned with the returns they forecast (see ``_rolling``)."""
    alpha = 1 - confidence

    def aligned(stat: pd.Series) -> np.ndarray:
        return stat.to_numpy()[window - 1 : -1]

    if method == "historical":
        needed = math.ceil(round(1 / alpha, 9))
        if window < needed:
            raise MissingData(
                f"a {confidence:.1%} historical VaR needs at least {needed} returns per window; the window is {window}"
            )
        k = math.ceil(round(window * alpha, 9))
        # 'lower' takes sorted index floor((window - 1) * q); aiming at k - 1/2 makes that exactly k - 1.
        return -aligned(rolling.quantile((k - 0.5) / (window - 1), interpolation="lower"))
    mean = aligned(rolling.mean())
    std = aligned(rolling.std(ddof=1))
    z = NormalDist().inv_cdf(alpha)
    if method == "parametric":
        return -(mean + z * std)
    # pandas gives the bias-adjusted sample skewness G1 and excess kurtosis G2; convert them to
    # the population moments g1 = m3 / m2^1.5 and g2 = m4 / m2^2 - 3 that analytics.risk uses.
    n = window
    g1 = aligned(rolling.skew()) * (n - 2) / math.sqrt(n * (n - 1))
    g2 = (aligned(rolling.kurt()) * (n - 2) * (n - 3) / (n - 1) - 6) / (n + 1)
    if np.isnan(g1).any() or np.isnan(g2).any():
        raise MissingData("returns do not vary within an estimation window, so skewness and kurtosis are undefined")
    z_cf = z + (z**2 - 1) * g1 / 6 + (z**3 - 3 * z) * g2 / 24 - (2 * z**3 - 5 * z) * g1**2 / 36
    return -(mean + z_cf * std)


def backtest_var(returns: pd.Series, method: VarMethod, confidence: float = 0.95, window: int = WINDOW) -> Backtest:
    """Rolling one-day VaR backtest of ``method`` (see the module docstring)."""
    if not 0 < confidence < 1:
        raise ValueError(f"confidence must be between 0 and 1, got {confidence}")
    rolling, realized = _rolling(returns, window)
    var = _forecasts(rolling, method, confidence, window)
    return Backtest(
        method=method,
        window=window,
        observations=len(realized),
        breaches=int(np.sum(realized < -var)),
        confidence=confidence,
    )
