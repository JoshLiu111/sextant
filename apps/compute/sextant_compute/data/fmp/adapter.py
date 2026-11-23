"""The FMP (Financial Modeling Prep) adapter. Every request uses the signed-in user's own key.

Like Tiingo, FMP's free terms don't allow showing its data to anyone but the key
holder, so the adapter's scope is ``"user"``: ``DataService`` caches what it
fetches under that user only, and only while the user has an FMP key.

Two jobs:

- ``verify_key``: Settings checks a key before saving it.
- ``daily_prices``: end-of-day prices for the My data tools, with
  ``ctx.key_for("fmp")``.
- ``latest_close``: the newest close (the Valuation Calculator's share price).

All calls go to the "stable" API with the key in the ``apikey`` header (never
in the URL, so it can't leak into a logged URL):

- Key check: ``GET /stable/quote?symbol=AAPL``. A bad key answers 401
  ``{"Error Message": "Invalid API KEY. ..."}`` (probed 2026-11-22, also on
  every data URL).
- Prices: ``GET /stable/historical-price-eod/full?symbol=&from=&to=``, newest
  first, ``{symbol, date, open, high, low, close, volume, change, changePercent,
  vwap}``. These are split-adjusted (FMP serves ``/non-split-adjusted``
  separately) and not dividend-adjusted, which is ``DailyPricesAdapter``'s
  contract as is.
- Dividends: ``GET /stable/dividends?symbol=``, the whole history newest first;
  ``date`` is the ex-date and ``adjDividend`` the split-adjusted cash amount
  (on the same scale as the prices). Filtered to the range here.
- Latest close: the same prices URL without ``from``/``to`` (FMP then answers
  its default recent range, newest first); the newest row's close. Split-adjusted
  closes are in today's share count, so the newest one is the raw close.

Free plans don't cover every symbol: such a symbol answers 402 and is reported
as missing for that ticker only. Unverified (no real key at hand): an unknown
symbol answering 200 ``[]`` (so it reads as "no prices in the range"), the 402
body, and the 429 on the daily request limit. A 200 carrying ``{"Error
Message": ...}`` (FMP's older API answered limits that way) is read as a
rejected key when it says so, else as ``SourceUnavailable``.

The key is never logged or put in an error message.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Sequence
from datetime import date
from typing import Any

import httpx
import pandas as pd

from sextant_compute.data.adapters import PRICE_COLUMNS, Scope
from sextant_compute.data.context import RequestContext
from sextant_compute.data.errors import KeyRequired, NoSuchData, SourceUnavailable
from sextant_compute.data.retry import get_with_retries
from sextant_compute.envelope import DataSource

FMP = DataSource(id="fmp", name="FMP", is_demo=False)

BASE_URL = "https://financialmodelingprep.com"
ATTEMPTS = 2
BACKOFF = 0.5  # seconds
KEY_CHECK_SYMBOL = "AAPL"

NO_KEY_MESSAGE = "My data needs your own FMP key. Add one in Settings."
REJECTED_KEY_MESSAGE = "FMP no longer accepts your saved key. Replace it in Settings."


class _NotInPlan(Exception):
    """FMP answered 402 for this symbol."""


class FmpAdapter:
    source = FMP
    scope: Scope = "user"
    # Same reasoning as Tiingo: end-of-day data, and a free key has a small daily quota.
    ttl: dict[str, int] = {"daily_prices": 12 * 3600, "latest_close": 12 * 3600}
    version = "1"

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(transport=transport, timeout=10.0)
        self._sleep = sleep

    @classmethod
    def from_env(cls) -> FmpAdapter:
        """``FMP_BASE_URL`` (optional; e2e tests point it at a fake)."""
        return cls(base_url=os.environ.get("FMP_BASE_URL") or BASE_URL)

    def _get(self, path: str, key: str, params: dict[str, str]) -> httpx.Response:
        try:
            return get_with_retries(
                lambda: self._client.get(f"{self._base_url}{path}", params=params, headers={"apikey": key}),
                attempts=ATTEMPTS,
                backoff=BACKOFF,
                sleep=self._sleep,
            )
        except httpx.HTTPError as exc:
            raise SourceUnavailable(FMP.id, f"FMP request failed ({type(exc).__name__}).") from None

    def verify_key(self, key: str) -> bool:
        """True if FMP accepts ``key``, False if it rejects it.

        Raises ``SourceUnavailable`` when FMP can't tell us either way."""
        response = self._get("/stable/quote", key, {"symbol": KEY_CHECK_SYMBOL})
        if response.status_code in (401, 403):
            return False
        if response.status_code == 402:  # the key works; the plan just doesn't cover the symbol
            return True
        if response.status_code != 200:
            raise SourceUnavailable(FMP.id, f"FMP answered HTTP {response.status_code}.")
        body = _json(response)
        if isinstance(body, list):
            return True
        if _rejects_key(body):
            return False
        raise SourceUnavailable(FMP.id, "FMP returned an unexpected response to the key check.")

    def daily_prices(
        self, ctx: RequestContext, tickers: Sequence[str], start: date, end: date
    ) -> dict[str, pd.DataFrame]:
        """See ``DailyPricesAdapter``. Two FMP requests per ticker (prices, dividends);
        every ticker without prices is collected into one ``NoSuchData``."""
        key = ctx.key_for(FMP.id)
        if not key:
            raise KeyRequired(FMP.id, NO_KEY_MESSAGE)
        frames: dict[str, pd.DataFrame] = {}
        missing: dict[str, str] = {}
        for ticker in tickers:
            try:
                rows = self._list(
                    "/stable/historical-price-eod/full",
                    key,
                    {"symbol": ticker, "from": start.isoformat(), "to": end.isoformat()},
                )
                if not rows:
                    missing[ticker] = f"No FMP prices for {ticker} between {start} and {end}."
                    continue
                dividends = self._list("/stable/dividends", key, {"symbol": ticker})
            except _NotInPlan:
                missing[ticker] = f"Your FMP plan does not include {ticker}."
                continue
            frames[ticker] = _frame(rows, dividends)
        if missing:
            raise NoSuchData(FMP.id, " ".join(missing.values()), missing)
        return frames

    def latest_close(self, ctx: RequestContext, ticker: str) -> tuple[date, float]:
        """See ``LatestCloseAdapter``. One request: the prices URL without dates."""
        key = ctx.key_for(FMP.id)
        if not key:
            raise KeyRequired(FMP.id, NO_KEY_MESSAGE)
        try:
            rows = self._list("/stable/historical-price-eod/full", key, {"symbol": ticker})
        except _NotInPlan:
            message = f"Your FMP plan does not include {ticker}."
        else:
            if rows:
                newest = max(rows, key=lambda r: str(r.get("date", "")))
                last = _frame([newest], [])
                return last.index[-1].date(), float(last["close"].iloc[-1])
            # FMP answers an unknown symbol the same way: an empty list.
            message = f"FMP has no recent prices for {ticker}."
        raise NoSuchData(FMP.id, message, {ticker: message})

    def _list(self, path: str, key: str, params: dict[str, str]) -> list[dict[str, Any]]:
        response = self._get(path, key, params)
        if response.status_code in (401, 403):
            raise KeyRequired(FMP.id, REJECTED_KEY_MESSAGE)
        if response.status_code == 402:
            raise _NotInPlan
        if response.status_code != 200:
            raise SourceUnavailable(FMP.id, f"FMP answered HTTP {response.status_code}.")
        body = _json(response)
        if _rejects_key(body):
            raise KeyRequired(FMP.id, REJECTED_KEY_MESSAGE)
        if not isinstance(body, list) or not all(isinstance(r, dict) for r in body):
            raise SourceUnavailable(FMP.id, "FMP returned data in an unexpected shape.")
        return body


def _rejects_key(body: Any) -> bool:
    return isinstance(body, dict) and "invalid api key" in str(body.get("Error Message", "")).lower()


def _json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        raise SourceUnavailable(FMP.id, "FMP returned a response that is not JSON.") from None


def _frame(rows: list[dict[str, Any]], dividends: list[dict[str, Any]]) -> pd.DataFrame:
    """Price rows (any order) + the dividend history -> a ``PRICE_COLUMNS`` frame, oldest first."""
    try:
        out = pd.DataFrame(
            {
                "open": [float(r["open"]) for r in rows],
                "high": [float(r["high"]) for r in rows],
                "low": [float(r["low"]) for r in rows],
                "close": [float(r["close"]) for r in rows],
                "volume": [float(r["volume"]) for r in rows],
                "dividend": 0.0,
            },
            index=pd.DatetimeIndex([pd.Timestamp(r["date"][:10]) for r in rows], name="date"),
        ).sort_index()
        for d in dividends:
            when = pd.Timestamp(d["date"][:10])
            if when in out.index:
                amount = d.get("adjDividend")
                out.loc[when, "dividend"] += float(amount if amount is not None else d["dividend"])
    except (KeyError, TypeError, ValueError):
        raise SourceUnavailable(FMP.id, "FMP returned prices in an unexpected shape.") from None
    return out[PRICE_COLUMNS]
