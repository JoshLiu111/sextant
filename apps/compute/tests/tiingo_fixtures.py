"""A stand-in for the Tiingo API, served without the network.

``tests/fixtures/tiingo/daily/<ticker>.json`` is the body of
``GET /tiingo/daily/<ticker>/prices`` for 30 trading days from 2024-01-02. The
files are hand-crafted from the documented JSON shape (tiingo.com/documentation/
end-of-day; no real key was available when they were made): field names, the
ISO dates, raw vs ``adj*`` prices, ``divCash`` on the ex-date and
``splitFactor`` on the split date are faithful; the numbers are made up:

- ``aapl``: a 4:1 split on 2024-01-30 (row 20; raw closes before it are 4x).
  Split-adjusted, the close goes 100 -> 120 (2024-01-16) -> 108 (2024-01-23)
  -> 130, so its max drawdown is exactly 10%.
- ``msft``: no split, no dividend.
- ``spy``: a 1.50 dividend on 2024-01-09 (row 5).

For the screener's price criteria (tests/test_screener_prices.py), seven of the
default screen's matches have *weekly* rows (Fridays 2025-11-14..2026-11-20, 54
rows, piecewise-linear closes; real Tiingo is daily, the code doesn't care).
Split-adjusted close on 2025-11-21 -> highest close -> close on 2026-11-20:
``nvda`` 100 -> 180 -> 150, ``amzn`` 200 -> 260 -> 240, ``googl`` 150 -> 210 (ends
on its high), ``meta`` 600 -> 700 -> 540, ``lly`` 800 -> 1000 -> 920, ``nflx``
1000 -> 1100 -> 900, ``avgo`` 250 -> 320 -> 300 with a 4:1 split on 2026-05-08
(raw closes before it are 4x). The 2025-11-14 row differs from the base on
purpose. ``msft`` has no rows in that window and ``adbe`` has no file.

The same files back the e2e fake (``apps/web/e2e/fake-tiingo.mjs``), which
follows the same rules as ``FakeTiingo`` below. Unknown tickers answer 404
``{"detail": "Error: Ticker 'X' not found"}`` and a token Tiingo doesn't know
answers 403 ``{"detail": "Invalid token."}`` (probed 2026-11-22 on a data URL).
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path

import httpx

from sextant_compute.data.tiingo import TiingoAdapter

FIXTURES = Path(__file__).parent / "fixtures" / "tiingo" / "daily"
FIRST_DAY, LAST_DAY = date(2024, 1, 2), date(2024, 2, 12)


def recorded_prices(ticker: str) -> list[dict]:
    return json.loads((FIXTURES / f"{ticker.lower()}.json").read_text())


class FakeTiingo:
    """Accepts the tokens in ``valid``. ``status`` (e.g. 503, 429) makes every
    request answer that status instead. ``price_requests`` counts
    ``(token, ticker)`` pairs, so tests can see which user's key reached Tiingo."""

    def __init__(self, valid: set[str]) -> None:
        self.valid = valid
        self.status: int | None = None
        self.requests: list[httpx.Request] = []
        self.price_requests: Counter[tuple[str, str]] = Counter()

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status is not None:
            return httpx.Response(self.status, text="Service Unavailable")
        token = request.headers.get("authorization", "").removeprefix("Token ")
        path = request.url.path
        if path == "/api/test":
            if not token:
                return httpx.Response(200, json={"message": "'AUTHORIZATION header' was not set"})
            if token in self.valid:
                return httpx.Response(200, json={"message": "You successfully sent a request"})
            return httpx.Response(200, json={"message": "Auth Token was not correct"})
        parts = path.strip("/").split("/")
        if len(parts) != 4 or parts[:2] != ["tiingo", "daily"] or parts[3] != "prices":
            return httpx.Response(404, json={"detail": "Not found."})
        if token not in self.valid:
            return httpx.Response(403, json={"detail": "Invalid token."})
        ticker = parts[2]
        self.price_requests[(token, ticker)] += 1
        file = FIXTURES / f"{ticker}.json"
        if not file.exists():
            return httpx.Response(404, json={"detail": f"Error: Ticker '{ticker}' not found"})
        rows = json.loads(file.read_text())
        if "startDate" not in request.url.params and "endDate" not in request.url.params:
            return httpx.Response(200, json=rows[-1:])  # no dates: Tiingo answers the latest day only
        start = request.url.params.get("startDate", "0000")
        end = request.url.params.get("endDate", "9999")
        return httpx.Response(200, json=[r for r in rows if start <= r["date"][:10] <= end])

    def adapter(self) -> TiingoAdapter:
        return TiingoAdapter(
            base_url="https://tiingo.test", transport=httpx.MockTransport(self.handler), sleep=lambda _s: None
        )
