"""Factor regressions: Fama-French 3-factor and Carhart 4-factor OLS.

Pure: a return series and a factor frame in, coefficients out. It knows nothing
about where the factors came from (the synthetic demo generator, or a factor file
a user uploaded), only their layout:

- ``returns``: simple periodic returns indexed by date.
- ``factors``: a DataFrame indexed by date with decimal (not percent) columns
  ``Mkt-RF``, ``SMB``, ``HML``, ``MOM`` (Carhart only) and ``RF``, one row per
  period, at the same frequency as ``returns``.

The regression is ``r - RF = a + sum(b_f * f) + e`` over the dates both have,
with classical (homoskedastic) OLS standard errors.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from sextant_compute.analytics.errors import MissingData
from sextant_compute.analytics.performance import TRADING_DAYS

MARKET = "Mkt-RF"
RISK_FREE = "RF"
FF3: tuple[str, ...] = ("Mkt-RF", "SMB", "HML")
CARHART: tuple[str, ...] = (*FF3, "MOM")

MIN_OBSERVATIONS = 24
"""Fewest overlapping returns a regression runs on (two years of monthly data)."""

_PERIOD = {TRADING_DAYS: "daily", 12: "monthly"}


@dataclass(frozen=True)
class FactorRegression:
    alpha: float
    """Intercept, annualized (per-period intercept x periods per year)."""
    loadings: dict[str, float]
    """Factor column -> coefficient."""
    t_stats: dict[str, float | None]
    """``"alpha"`` and each factor column -> t-statistic (None when the fit is exact)."""
    r_squared: float
    observations: int


def factor_regression(
    returns: pd.Series,
    factors: pd.DataFrame,
    model: Sequence[str],
    *,
    periods_per_year: int = TRADING_DAYS,
) -> FactorRegression:
    """OLS of excess returns on the ``model`` factor columns (e.g. ``FF3`` or ``CARHART``)."""
    columns = list(model)
    absent = [c for c in (*columns, RISK_FREE) if c not in factors.columns]
    if absent:
        raise MissingData(f"the factor data has no {', '.join(absent)} column")
    data = pd.concat([returns.rename("__r"), factors[[*columns, RISK_FREE]]], axis=1, join="inner").dropna()
    n = len(data)
    period = _PERIOD.get(periods_per_year, "periodic")
    if n < MIN_OBSERVATIONS:
        raise MissingData(f"needs at least {MIN_OBSERVATIONS} {period} returns that overlap the factor data, got {n}")
    y = (data["__r"] - data[RISK_FREE]).to_numpy()
    x = np.column_stack([np.ones(n), data[columns].to_numpy()])
    if np.linalg.matrix_rank(x) < x.shape[1]:
        raise MissingData("the factors do not vary independently over this range")
    total = float(((y - y.mean()) ** 2).sum())
    if total == 0:
        raise MissingData("the excess returns do not vary over this range")
    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    residual = y - x @ coef
    ssr = float(residual @ residual)
    dof = n - x.shape[1]
    variance = ssr / dof
    se = np.sqrt(variance * np.diag(np.linalg.inv(x.T @ x)))
    names = ["alpha", *columns]
    t_stats = {name: (float(b / s) if s > 0 else None) for name, b, s in zip(names, coef, se, strict=True)}
    return FactorRegression(
        alpha=float(coef[0]) * periods_per_year,
        loadings={c: float(b) for c, b in zip(columns, coef[1:], strict=True)},
        t_stats=t_stats,
        r_squared=1 - ssr / total,
        observations=n,
    )
