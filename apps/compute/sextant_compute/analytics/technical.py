"""Technical indicators and return correlation: pure functions on date-indexed Series.

Each indicator takes a price Series (sorted by date) and returns a Series on the
same index, NaN where the indicator is not yet defined. Callers fetch
``lookback(...)`` extra trading days before the visible start so the values are
defined (and warmed up) from the first visible date.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np
import pandas as pd

from sextant_compute.analytics.errors import MissingData

# Exponential averages are seeded with a simple average, then need a few spans of
# history before the seed's influence fades (after 3 spans it is below 0.3%).
WARMUP_SPANS = 3


def sma(close: pd.Series, window: int) -> pd.Series:
    """Simple moving average of the last ``window`` closes."""
    return close.rolling(window, min_periods=window).mean()


def ema(values: pd.Series, span: int) -> pd.Series:
    """Exponential moving average, alpha = 2 / (span + 1), seeded with the SMA of the first ``span`` values.

    Leading NaNs (e.g. an input that is itself an indicator) are skipped.
    """
    out = pd.Series(np.nan, index=values.index, dtype=float)
    valid = values.dropna()
    if len(valid) < span:
        return out
    alpha = 2.0 / (span + 1)
    raw = valid.to_numpy(dtype=float)
    smoothed = np.empty(len(raw) - span + 1)
    smoothed[0] = raw[:span].mean()
    for i, x in enumerate(raw[span:], start=1):
        smoothed[i] = alpha * x + (1 - alpha) * smoothed[i - 1]
    out.loc[valid.index[span - 1 :]] = smoothed
    return out


def bollinger(close: pd.Series, window: int, width: float) -> tuple[pd.Series, pd.Series, pd.Series]:
    """(upper, middle, lower): the ``window``-day SMA plus/minus ``width`` population standard deviations."""
    middle = sma(close, window)
    spread = close.rolling(window, min_periods=window).std(ddof=0) * width
    return middle + spread, middle, middle - spread


def rsi(close: pd.Series, window: int) -> pd.Series:
    """Wilder's relative strength index (0 to 100).

    Average gain and loss start as the simple mean of the first ``window`` daily
    changes, then update as ``(prev * (window - 1) + today) / window``.
    """
    out = pd.Series(np.nan, index=close.index, dtype=float)
    change = close.diff().to_numpy(dtype=float)[1:]
    if len(change) < window:
        return out
    gains = np.clip(change, 0, None)
    losses = np.clip(-change, 0, None)
    avg_gain = gains[:window].mean()
    avg_loss = losses[:window].mean()
    values = [_rsi(avg_gain, avg_loss)]
    for g, loss in zip(gains[window:], losses[window:]):
        avg_gain = (avg_gain * (window - 1) + g) / window
        avg_loss = (avg_loss * (window - 1) + loss) / window
        values.append(_rsi(avg_gain, avg_loss))
    out.iloc[window:] = values
    return out


def _rsi(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 50.0 if avg_gain == 0 else 100.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def macd(close: pd.Series, fast: int, slow: int, signal: int) -> tuple[pd.Series, pd.Series, pd.Series]:
    """(MACD line, signal line, histogram): EMA(fast) - EMA(slow), its EMA(signal), and their difference."""
    line = ema(close, fast) - ema(close, slow)
    signal_line = ema(line, signal)
    return line, signal_line, line - signal_line


def lookback(
    *,
    sma_window: int | None = None,
    ema_span: int | None = None,
    bollinger_window: int | None = None,
    rsi_window: int | None = None,
    macd_spans: tuple[int, int, int] | None = None,
) -> int:
    """Trading days of history needed before the first visible date for every requested indicator."""
    needs = [0]
    if sma_window:
        needs.append(sma_window - 1)
    if bollinger_window:
        needs.append(bollinger_window - 1)
    if ema_span:
        needs.append(WARMUP_SPANS * ema_span)
    if rsi_window:
        needs.append(WARMUP_SPANS * rsi_window)
    if macd_spans:
        _, slow, signal = macd_spans
        needs.append(WARMUP_SPANS * (slow + signal))
    return max(needs)


def calendar_days(trading_days: int) -> int:
    """Calendar days that surely contain ``trading_days`` trading days (5 per week, plus holidays)."""
    return math.ceil(trading_days * 7 / 5) + 10 if trading_days else 0


def correlation(returns: Mapping[str, pd.Series], a: str, b: str) -> float:
    """Pearson correlation of two daily return series on their shared dates."""
    joined = pd.concat([returns[a].rename("a"), returns[b].rename("b")], axis=1, join="inner").dropna()
    if len(joined) < 3:
        raise MissingData(f"needs at least 3 shared daily returns, got {len(joined)}")
    if joined["a"].std() == 0 or joined["b"].std() == 0:
        flat = a if joined["a"].std() == 0 else b
        raise MissingData(f"{flat}'s returns do not vary, so its correlation is undefined")
    return float(np.corrcoef(joined["a"], joined["b"])[0, 1])
