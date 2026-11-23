"""The Tiingo adapter. Every request uses the signed-in user's own key.

Tiingo's terms forbid showing its data to anyone but the key holder, so the
adapter's scope is ``"user"``: ``DataService`` caches what it fetches under that
user only, never in the shared cache, and only while the user has a key.

Its jobs:

- ``verify_key``: Settings checks a key before saving it.
- ``daily_prices``: end-of-day prices for Risk & Performance on My data (and
  every later "My data" tool), with ``ctx.key_for("tiingo")``.
- ``latest_close``: the last close, for the Valuation Calculator's margin of
  safety. The same URL without ``startDate``/``endDate`` answers only the latest
  day (checked with a real key on 2026-11-23).
- ``splits``: the stock splits since a date (Portfolio returns turn a past trade
  into today's share count), from the ``splitFactor`` of the prices up to today.
  Portfolio returns ask for them right after the prices, so the rows of a
  price request are remembered for ``RECENT_SECONDS`` (per key and ticker) and a
  split lookup inside them reuses them instead of fetching the prices again.

Key check: ``GET /api/test``. Checked 2026-11-22: it answers HTTP 200 for every
token and says in ``message`` whether the token worked:

- ``"You successfully sent a request"``: the token is valid.
- ``"Auth Token was not correct"``: the token is wrong.

Prices: ``GET /tiingo/daily/<ticker>/prices?startDate=&format=json``,
one request per ticker, answering a JSON list of ``{date, open, high, low,
close, volume, adjOpen, ..., adjClose, adjVolume, divCash, splitFactor}``
(documented shape). ``close`` is raw; ``divCash`` is the cash dividend on its
ex-date; ``splitFactor`` is the split ratio on the split date (4.0 for 4:1),
1.0 otherwise. We return prices *split*-adjusted to today's share count (so a
split is not a crash, and the prices match holdings, which are in today's share
count): ``daily_prices`` asks for ``startDate`` only, so Tiingo answers up to
the latest day and every later split is in the rows, then drops the rows after
the range's end. Prices are not dividend-adjusted (``DailyPricesAdapter``'s
contract: tools add the dividends back themselves). Data URLs answer 403 ``{"detail":"Invalid token."}``
for a bad token (probed 2026-11-22). Checked with a real key on 2026-11-23: an
unknown ticker answers 404 ``{"detail":"Error: Ticker 'X' not found"}``, a
range without prices (e.g. a weekend) answers ``[]``, and prices are only
published after the close (on a Monday morning the latest day was Friday).
Unverified: the hourly/daily request limits answering 429. Any other unexpected
answer is ``SourceUnavailable``.

The key is never logged or put in an error message.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from collections.abc import Callable, Sequence
from datetime import date
from typing import Any
from urllib.parse import quote

import httpx
import pandas as pd

from sextant_compute.data.adapters import PRICE_COLUMNS
from sextant_compute.data.context import RequestContext
from sextant_compute.data.errors import KeyRequired, NoSuchData, SourceUnavailable
from sextant_compute.data.sources import TIINGO
from sextant_compute.data.user_key_http import UserKeyHttpAdapter

BASE_URL = "https://api.tiingo.com"

NO_KEY_MESSAGE = "My data needs your own Tiingo key. Add one in Settings."
REJECTED_KEY_MESSAGE = "Tiingo no longer accepts your saved key. Replace it in Settings."

RECENT_SECONDS = 60.0
"""How long a price request's rows are reused for a split lookup (about one request)."""
RECENT_LIMIT = 64
"""At most this many (key, ticker) rows are remembered."""

Rows = list[dict[str, Any]]


def _no_ticker(ticker: str) -> NoSuchData:
    message = f"Tiingo has no ticker {ticker}."
    return NoSuchData(TIINGO.id, message, {ticker: message})


class TiingoAdapter(UserKeyHttpAdapter):
    source = TIINGO
    no_key_message = NO_KEY_MESSAGE
    # End-of-day data changes once a day; half a day keeps a user's repeat requests
    # off their hourly Tiingo quota without serving yesterday's close for long.
    ttl: dict[str, int] = {"daily_prices": 12 * 3600, "latest_close": 12 * 3600, "splits": 12 * 3600}
    # 2: prices are split-adjusted to today's share count (cached series may not be).
    version = "2"

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        super().__init__(base_url=base_url, transport=transport, sleep=sleep)
        self._recent: dict[tuple[str, str], tuple[float, date, Rows | None]] = {}
        self._recent_lock = threading.Lock()

    @classmethod
    def from_env(cls) -> TiingoAdapter:
        """``TIINGO_BASE_URL`` (optional; e2e tests point it at a fake)."""
        return cls(base_url=os.environ.get("TIINGO_BASE_URL") or BASE_URL)

    def _tiingo_get(self, path: str, key: str, params: dict[str, str] | None = None) -> httpx.Response:
        return self._get(path, params, {"Authorization": f"Token {key}", "Content-Type": "application/json"})

    def verify_key(self, key: str) -> bool:
        """True if Tiingo accepts ``key``, False if it rejects it.

        Raises ``SourceUnavailable`` when Tiingo can't tell us either way.
        """
        response = self._tiingo_get("/api/test", key)
        if response.status_code in (401, 403):
            return False
        if response.status_code != 200:
            raise SourceUnavailable(TIINGO.id, f"Tiingo answered HTTP {response.status_code}.")
        body = self._json(response)
        message = str(body.get("message", "")).lower() if isinstance(body, dict) else ""
        if "successfully" in message:
            return True
        if "not correct" in message or "invalid" in message:
            return False
        raise SourceUnavailable(TIINGO.id, "Tiingo returned an unexpected response to the key check.")

    def daily_prices(
        self, ctx: RequestContext, tickers: Sequence[str], start: date, end: date
    ) -> dict[str, pd.DataFrame]:
        """See ``DailyPricesAdapter``. One Tiingo request per ticker; every unknown
        ticker (or one with no prices in the range) is collected into one ``NoSuchData``."""
        key = self._key(ctx)

        def fetch(ticker: str) -> pd.DataFrame | str:
            # Up to today, not just ``end``: a split after ``end`` still changes the share count.
            rows = self._rows_to_today(key, ticker, start)
            if rows is None:
                return _no_ticker(ticker).message
            frame = _frame(rows).loc[: pd.Timestamp(end)] if rows else None
            if frame is None or frame.empty:
                return f"No Tiingo prices for {ticker} between {start} and {end}."
            return frame

        return self._per_ticker(tickers, fetch)

    def splits(self, ctx: RequestContext, ticker: str, start: date) -> list[tuple[date, float]]:
        """See ``SplitsAdapter``. The ``splitFactor`` of every row from ``start`` to the latest day."""
        rows = self._rows_to_today(self._key(ctx), ticker, start)
        if rows is None:
            raise _no_ticker(ticker)
        split = _raw(rows)["split"] if rows else pd.Series(dtype=float)
        return [(d.date(), float(ratio)) for d, ratio in split.items() if ratio != 1.0]

    def latest_close(self, ctx: RequestContext, ticker: str) -> tuple[date, float]:
        """See ``LatestCloseAdapter``. Tiingo's prices URL without dates answers the latest day."""
        rows = self._prices(self._key(ctx), ticker, None, None)
        if rows is None:
            raise _no_ticker(ticker)
        if not rows:
            message = f"Tiingo has no recent prices for {ticker}."
            raise NoSuchData(TIINGO.id, message, {ticker: message})
        last = _frame(rows[-1:])
        return last.index[-1].date(), float(last["close"].iloc[-1])

    def _rows_to_today(self, key: str, ticker: str, start: date) -> Rows | None:
        """The rows from ``start`` up to the latest day (None: unknown ticker), reusing
        a request made in the last ``RECENT_SECONDS`` with the same key from an
        earlier or equal start."""
        slot = (hashlib.sha256(key.encode()).hexdigest(), ticker.upper())
        now = time.monotonic()
        with self._recent_lock:
            recent = self._recent.get(slot)
        if recent is not None:
            fetched_at, fetched_from, rows = recent
            if now - fetched_at < RECENT_SECONDS and fetched_from <= start:
                return None if rows is None else [r for r in rows if str(r.get("date", ""))[:10] >= start.isoformat()]
        rows = self._prices(key, ticker, start, None)
        with self._recent_lock:
            self._recent = {k: v for k, v in self._recent.items() if now - v[0] < RECENT_SECONDS}
            if len(self._recent) >= RECENT_LIMIT:
                self._recent.pop(next(iter(self._recent)))
            self._recent[slot] = (now, start, rows)
        return rows

    def _prices(self, key: str, ticker: str, start: date | None, end: date | None) -> Rows | None:
        """The raw rows, or None for a ticker Tiingo doesn't know. No dates: the latest day;
        a start without an end: up to the latest day."""
        params = {"format": "json"}
        if start is not None:
            params["startDate"] = start.isoformat()
        if end is not None:
            params["endDate"] = end.isoformat()
        response = self._tiingo_get(f"/tiingo/daily/{quote(ticker.lower(), safe='')}/prices", key, params)
        if response.status_code in (401, 403):
            raise KeyRequired(TIINGO.id, REJECTED_KEY_MESSAGE)
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise SourceUnavailable(TIINGO.id, f"Tiingo answered HTTP {response.status_code}.")
        body = self._json(response)
        if not isinstance(body, list) or not all(isinstance(r, dict) for r in body):
            raise SourceUnavailable(TIINGO.id, "Tiingo returned prices in an unexpected shape.")
        return body


def _frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Rows -> a ``PRICE_COLUMNS`` frame, split-adjusted to the last row's share count
    (today's, when the rows run up to the latest day)."""
    raw = _raw(rows)
    # A row's prices are divided by every split that happens *after* it.
    later_splits = raw["split"][::-1].cumprod()[::-1].shift(-1, fill_value=1.0)
    out = raw[PRICE_COLUMNS].copy()
    for column in ("open", "high", "low", "close", "dividend"):
        out[column] = raw[column] / later_splits
    out["volume"] = raw["volume"] * later_splits
    return out


def _raw(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Rows -> ``PRICE_COLUMNS`` as Tiingo sent them, plus ``split``, oldest first."""
    try:
        raw = pd.DataFrame(
            {
                "open": [float(r["open"]) for r in rows],
                "high": [float(r["high"]) for r in rows],
                "low": [float(r["low"]) for r in rows],
                "close": [float(r["close"]) for r in rows],
                "volume": [float(r["volume"]) for r in rows],
                "dividend": [float(r.get("divCash") or 0.0) for r in rows],
                "split": [float(r.get("splitFactor") or 1.0) for r in rows],
            },
            index=pd.DatetimeIndex([pd.Timestamp(r["date"][:10]) for r in rows], name="date"),
        ).sort_index()
    except (KeyError, TypeError, ValueError):
        raise SourceUnavailable(TIINGO.id, "Tiingo returned prices in an unexpected shape.") from None
    return raw
