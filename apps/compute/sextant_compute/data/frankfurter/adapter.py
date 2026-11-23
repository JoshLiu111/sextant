"""The Frankfurter adapter: ``fx_rates`` from api.frankfurter.dev (v2, blended rates).

One request per currency pair and calendar year::

    GET /v2/rates?from=YYYY-01-01&to=YYYY-12-31&base=EUR&quotes=USD
    -> [{"date": "2024-01-02", "base": "EUR", "quote": "USD", "rate": 1.102}, ...]

Rates are daily mid-market reference rates (one row per calendar day, weekends
included in recent years), blended by Frankfurter across central banks. A year
with no rates (before the currency existed, or in the future) answers ``[]``.
An unsupported currency answers 422 ``{"message": "invalid currency: XYZ"}``
(404 on some routes).

Terms (frankfurter.dev FAQ, checked 2026-11-22): free, including commercial use;
no API key; blended rates are Frankfurter's own calculation, so central-bank
terms do not carry over; caching is encouraged; credit is appreciated, not
required ("Exchange rates: Frankfurter (frankfurter.dev)"). Pages using it
credit it in the footer (web: the ``frankfurter`` attribution). The v1 API is
deprecated in favour of v2.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable
from datetime import date

import httpx

from sextant_compute.data.adapters import FxRates, Scope
from sextant_compute.data.context import RequestContext
from sextant_compute.data.errors import NoSuchData, SourceUnavailable
from sextant_compute.data.retry import get_with_retries
from sextant_compute.envelope import DataSource

FRANKFURTER = DataSource(id="frankfurter", name="Frankfurter", is_demo=False)

BASE_URL = "https://api.frankfurter.dev"
USER_AGENT = "Mozilla/5.0 (compatible; Sextant/0.1; open-source finance tools)"

ATTEMPTS = 3
BACKOFF = 1.0  # seconds, doubled per retry

_INVALID = re.compile(r"invalid currency:\s*([A-Za-z]+)")


def unsupported(code: str) -> str:
    return f"Frankfurter has no exchange rates for {code}."


class FrankfurterAdapter:
    source = FRANKFURTER
    scope: Scope = "shared"
    # Past years never change much (blends can shift in the last decimals); the
    # current year gains a rate every day. Frankfurter itself caches for a day.
    ttl = {"fx_rates": 12 * 3600}
    version = "1"

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._sleep = sleep
        self._client = httpx.Client(transport=transport, timeout=15.0, headers={"User-Agent": USER_AGENT})

    @classmethod
    def from_env(cls) -> FrankfurterAdapter:
        """``FRANKFURTER_BASE_URL`` (optional; e2e tests point it at a fake)."""
        return cls(base_url=os.environ.get("FRANKFURTER_BASE_URL") or BASE_URL)

    def fx_rates(self, ctx: RequestContext, base: str, quote: str, year: int) -> FxRates:
        params = {"from": f"{year}-01-01", "to": f"{year}-12-31", "base": base, "quotes": quote}
        try:
            response = get_with_retries(
                lambda: self._client.get(f"{self._base_url}/v2/rates", params=params),
                attempts=ATTEMPTS,
                backoff=BACKOFF,
                sleep=self._sleep,
            )
        except httpx.HTTPError as exc:
            raise SourceUnavailable(FRANKFURTER.id, f"Frankfurter request failed ({type(exc).__name__}).") from None
        if response.status_code in (404, 422):
            code = _unsupported_code(response, base, quote)
            raise NoSuchData(FRANKFURTER.id, unsupported(code), {code: unsupported(code)})
        if response.status_code != 200:
            raise SourceUnavailable(FRANKFURTER.id, f"Frankfurter answered HTTP {response.status_code}.")
        return FxRates(source=FRANKFURTER, base=base, quote=quote, rates=_parse(response, base, quote))


def _unsupported_code(response: httpx.Response, base: str, quote: str) -> str:
    try:
        message = str(response.json().get("message", ""))
    except ValueError:
        message = ""
    match = _INVALID.search(message)
    return match.group(1).upper() if match else f"{base}/{quote}"


def _parse(response: httpx.Response, base: str, quote: str) -> list[tuple[date, float]]:
    try:
        rows = response.json()
        rates = [
            (date.fromisoformat(row["date"]), float(row["rate"]))
            for row in rows
            if row["base"] == base and row["quote"] == quote
        ]
    except (ValueError, KeyError, TypeError) as exc:
        raise SourceUnavailable(FRANKFURTER.id, "Frankfurter returned an unexpected response.") from exc
    rates.sort(key=lambda r: r[0])
    return rates
