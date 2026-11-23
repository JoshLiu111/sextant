"""A stand-in for the FMP (Financial Modeling Prep) "stable" API, served without the network.

Recorded responses under ``tests/fixtures/fmp/``:

- ``historical-price-eod/<ticker>.json``: the body of
  ``GET /stable/historical-price-eod/full?symbol=<T>&from=&to=`` for 30 trading
  days from 2024-01-02, newest first, in the documented shape (``symbol, date,
  open, high, low, close, volume, change, changePercent, vwap``; a live AAPL
  recording from 2026-09 has exactly these fields). FMP's ``/full`` prices are
  split-adjusted (it serves ``/non-split-adjusted`` separately) and not
  dividend-adjusted. The numbers mirror the Tiingo fixtures after split
  adjustment, so AAPL's max drawdown is again exactly 10% (120 -> 108).
- ``dividends/<ticker>.json``: the body of ``GET /stable/dividends?symbol=<T>``,
  the whole history newest first (``date`` is the ex-date; ``dividend`` is the
  cash amount as paid, ``adjDividend`` the split-adjusted one). AAPL has a
  pre-split dividend inside the range (0.96 paid, 0.24 adjusted); SPY has 1.50
  on 2024-01-09; MSFT has none inside the range.

The numbers are made up (no real key was at hand); the field names and the
401 body for a bad key (probed 2026-11-22) are real. Unverified: an unknown
symbol answering 200 ``[]``, and the 402 body for a symbol the plan doesn't
cover. The e2e fake (``apps/web/e2e/fake-fmp.mjs``) serves the same files with
the same rules.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path

import httpx

from sextant_compute.data.fmp import FmpAdapter

FIXTURES = Path(__file__).parent / "fixtures" / "fmp"
FIRST_DAY, LAST_DAY = date(2024, 1, 2), date(2024, 2, 12)
INVALID_KEY_BODY = {
    "Error Message": "Invalid API KEY. Feel free to create a Free API Key or visit "
    "https://site.financialmodelingprep.com/faqs?search=why-is-my-api-key-invalid for more information."
}


def recorded(dataset: str, ticker: str) -> list[dict]:
    return json.loads((FIXTURES / dataset / f"{ticker.lower()}.json").read_text())


class FakeFmp:
    """Accepts the keys in ``valid`` (sent in the ``apikey`` header).
    ``status`` (e.g. 503, 429) makes every request answer that status instead.
    ``premium``: symbols the plan doesn't cover (402). ``price_requests``
    counts ``(key, ticker)`` pairs, so tests can see whose key reached FMP."""

    def __init__(self, valid: set[str]) -> None:
        self.valid = valid
        self.status: int | None = None
        self.premium: set[str] = set()
        self.requests: list[httpx.Request] = []
        self.price_requests: Counter[tuple[str, str]] = Counter()

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status is not None:
            return httpx.Response(self.status, text="Service Unavailable")
        key = request.headers.get("apikey", "")
        if key not in self.valid:
            return httpx.Response(401, json=INVALID_KEY_BODY)
        symbol = request.url.params.get("symbol", "").upper()
        path = request.url.path
        if symbol in self.premium:
            return httpx.Response(
                402,
                json={"Error Message": f"Premium Query Parameter: '{symbol}' is not available under your plan."},
            )
        if path == "/stable/quote":
            return httpx.Response(200, json=[{"symbol": symbol, "price": 130.0}] if symbol else [])
        if path == "/stable/historical-price-eod/full":
            self.price_requests[(key, symbol)] += 1
            start = request.url.params.get("from", "0000")
            end = request.url.params.get("to", "9999")
            return httpx.Response(200, json=[r for r in self._rows("historical-price-eod", symbol) if start <= r["date"] <= end])
        if path == "/stable/dividends":
            return httpx.Response(200, json=self._rows("dividends", symbol))
        return httpx.Response(404, json={"Error Message": "Not found."})

    @staticmethod
    def _rows(dataset: str, symbol: str) -> list[dict]:
        file = FIXTURES / dataset / f"{symbol.lower()}.json"
        return json.loads(file.read_text()) if symbol and file.exists() else []

    def adapter(self) -> FmpAdapter:
        return FmpAdapter(base_url="https://fmp.test", transport=httpx.MockTransport(self.handler), sleep=lambda _s: None)
