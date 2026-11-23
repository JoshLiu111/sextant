"""The FRED adapter: ``economic_series`` from the FRED v1 JSON API.

Compliance (FRED API Terms of Use, spec story 94):

- Only public-domain series. A series must be in ``PUBLIC_DOMAIN_SERIES`` (IDs
  whose status tag "Public Domain: Citation Requested" was checked on the FRED
  site) *and* its metadata notes must not contain "copyright". The notes check
  alone is not enough: T10Y2Y is "Copyrighted: Citation Required" with clean
  notes. Add an ID to the allowlist only after checking its tag on FRED.
- Pages using FRED show the required notice and a link to the Terms of Use
  (web: the ``fred`` attribution in ``src/lib/attributions.ts``).
- At most 2 requests/second (``Throttle``, shared by every adapter instance in
  the process), with backoff on 429.
- The key comes from env ``FRED_API_KEY`` and is never logged or echoed: error
  messages never include the request URL.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Mapping
from datetime import date, datetime
from typing import Any

import httpx

from sextant_compute.data.adapters import EconomicSeries, Scope, SeriesMeta
from sextant_compute.data.context import RequestContext
from sextant_compute.data.errors import NoSuchData, SourceUnavailable
from sextant_compute.envelope import DataSource

FRED = DataSource(id="fred", name="FRED, Federal Reserve Bank of St. Louis", is_demo=False)

BASE_URL = "https://api.stlouisfed.org/fred"
TERMS_OF_USE_URL = "https://fred.stlouisfed.org/docs/api/terms_of_use.html"

BEA = "U.S. Bureau of Economic Analysis"
BLS = "U.S. Bureau of Labor Statistics"
FED_BOARD = "Board of Governors of the Federal Reserve System"

PUBLIC_DOMAIN_SERIES: Mapping[str, str] = {
    # series id -> publishing agency. Each tag checked on fred.stlouisfed.org
    # (2026-11-22): "Public Domain: Citation Requested".
    "A191RL1Q225SBEA": BEA,  # Real GDP, % change from preceding period, SAAR
    "CPIAUCSL": BLS,  # CPI-U, all items
    "UNRATE": BLS,  # Unemployment rate
    "FEDFUNDS": FED_BOARD,  # Effective federal funds rate, monthly
    "DFF": FED_BOARD,  # Effective federal funds rate, daily
    "DGS1MO": FED_BOARD,  # Treasury constant maturity, 1 month
    "DGS2": FED_BOARD,  # 2 year
    "DGS10": FED_BOARD,  # 10 year
}

# FRED's labels for its server-side transformations (the ``units`` parameter).
UNITS_LABELS: Mapping[str, str | None] = {
    "lin": None,  # as published: use the metadata's units
    "chg": "Change",
    "ch1": "Change from Year Ago",
    "pch": "Percent Change",
    "pc1": "Percent Change from Year Ago",
    "pca": "Compounded Annual Rate of Change",
    "cch": "Continuously Compounded Rate of Change",
    "cca": "Continuously Compounded Annual Rate of Change",
    "log": "Natural Log",
}

MIN_INTERVAL = 0.5  # seconds between requests: FRED allows up to 2 per second
ATTEMPTS = 3
BACKOFF = 1.0  # seconds, doubled per retry


class Throttle:
    """Spaces calls to ``wait()`` at least ``min_interval`` apart (thread-safe)."""

    def __init__(
        self,
        min_interval: float = MIN_INTERVAL,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_interval = min_interval
        self.clock = clock
        self.sleep = sleep
        self._lock = threading.Lock()
        self._next = float("-inf")

    def wait(self) -> None:
        with self._lock:
            now = self.clock()
            if now < self._next:
                self.sleep(self._next - now)
                now = self.clock()
            self._next = now + self.min_interval


_PROCESS_THROTTLE = Throttle()


class FredAdapter:
    source = FRED
    scope: Scope = "shared"
    # Daily series (DGS*, DFF) update once per business day; monthly and
    # quarterly ones only on release days. 6h keeps daily series fresh enough.
    ttl = {"economic_series": 6 * 3600}
    version = "1"

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = BASE_URL,
        allowlist: Mapping[str, str] = PUBLIC_DOMAIN_SERIES,
        transport: httpx.BaseTransport | None = None,
        throttle: Throttle = _PROCESS_THROTTLE,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._allowlist = dict(allowlist)
        self._throttle = throttle
        self._client = httpx.Client(transport=transport, timeout=10.0)

    @classmethod
    def from_env(cls) -> FredAdapter:
        """``FRED_API_KEY`` (required to fetch; the app starts without it) and
        ``FRED_API_BASE_URL`` (optional; e2e tests point it at a fake)."""
        return cls(
            api_key=os.environ.get("FRED_API_KEY") or None,
            base_url=os.environ.get("FRED_API_BASE_URL") or BASE_URL,
        )

    def economic_series(
        self, ctx: RequestContext, series_id: str, start: date, units: str = "lin"
    ) -> EconomicSeries:
        if units not in UNITS_LABELS:
            raise ValueError(f"Unknown FRED units transformation {units!r}")
        agency = self._allowlist.get(series_id)
        if agency is None:
            raise NoSuchData(
                FRED.id,
                f"{series_id} is not on Sextant's list of verified public-domain FRED series.",
                {series_id: f"{series_id} is not a verified public-domain series."},
            )
        raw = self._get("/series", series_id=series_id)
        meta = _only_series(raw, series_id)
        if "copyright" in str(meta.get("notes") or "").lower():
            raise NoSuchData(
                FRED.id,
                f"{series_id} is copyrighted by its owner, so Sextant does not republish it.",
                {series_id: f"{series_id} is a copyrighted series."},
            )
        obs = self._get(
            "/series/observations", series_id=series_id, observation_start=start.isoformat(), units=units
        )
        try:
            return EconomicSeries(
                source=FRED,
                meta=SeriesMeta(
                    id=series_id,
                    title=str(meta["title"]),
                    source=agency,
                    units=UNITS_LABELS[units] or str(meta["units"]),
                    frequency=str(meta["frequency"]),
                    seasonal_adjustment=str(meta["seasonal_adjustment_short"]),
                    last_updated=datetime.fromisoformat(str(meta["last_updated"])).isoformat(),
                ),
                observations=[
                    (date.fromisoformat(o["date"]), None if o["value"] == "." else float(o["value"]))
                    for o in obs["observations"]
                ],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SourceUnavailable(FRED.id, f"FRED returned an unexpected response for {series_id}.") from exc

    def _get(self, path: str, **params: str) -> dict[str, Any]:
        if not self._api_key:
            raise SourceUnavailable(FRED.id, "FRED_API_KEY is not configured.")
        query = {**params, "api_key": self._api_key, "file_type": "json"}
        series_id = params.get("series_id", "")
        for attempt in range(ATTEMPTS):
            self._throttle.wait()
            try:
                response = self._client.get(f"{self._base_url}{path}", params=query)
            except httpx.HTTPError as exc:
                # Never include the URL: it carries the API key.
                raise SourceUnavailable(FRED.id, f"FRED request failed ({type(exc).__name__}).") from None
            if response.status_code == 429 or response.status_code >= 500:
                if attempt + 1 < ATTEMPTS:
                    self._throttle.sleep(BACKOFF * 2**attempt)
                    continue
                raise SourceUnavailable(FRED.id, f"FRED answered HTTP {response.status_code}.")
            try:
                body = response.json()
            except ValueError:
                raise SourceUnavailable(FRED.id, "FRED returned a response that is not JSON.") from None
            if response.status_code == 200 and isinstance(body, dict):
                return body
            message = str(body.get("error_message", "")) if isinstance(body, dict) else ""
            if response.status_code in (400, 404) and "does not exist" in message.lower():
                raise NoSuchData(FRED.id, f"FRED has no series {series_id}.", {series_id: f"Unknown series {series_id}."})
            # Bad or missing key, bad parameters: our problem, not the visitor's.
            raise SourceUnavailable(FRED.id, f"FRED answered HTTP {response.status_code}.")
        raise AssertionError("unreachable")


def _only_series(raw: Mapping[str, Any], series_id: str) -> Mapping[str, Any]:
    seriess = raw.get("seriess")  # sic: FRED's key
    if not isinstance(seriess, list) or not seriess or not isinstance(seriess[0], dict):
        raise SourceUnavailable(FRED.id, f"FRED returned no metadata for {series_id}.")
    return seriess[0]
