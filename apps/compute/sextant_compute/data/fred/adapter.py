"""The FRED adapter: ``economic_series`` and ``search_series`` from the FRED v1 JSON API.

Compliance (FRED API Terms of Use, spec story 94):

- Only public-domain series (ADR 0006). A series' metadata notes must not
  contain "copyright", *and* it must either be in ``PUBLIC_DOMAIN_SERIES`` (IDs
  whose status tag was checked by hand on the FRED site: the headline
  indicators) or carry FRED's ``PUBLIC_DOMAIN_TAG`` when fetched (any series a
  visitor picks). The notes check alone is not enough: T10Y2Y is "Copyrighted:
  Citation Required" with clean notes. Search asks FRED for public-domain-tagged
  series only and drops any hit whose notes mention a copyright.
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

from sextant_compute.data.adapters import EconomicSeries, Scope, SeriesMeta, SeriesSummary
from sextant_compute.data.context import RequestContext
from sextant_compute.data.errors import NoSuchData, SourceUnavailable
from sextant_compute.data.retry import get_with_retries, is_retryable
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

# FRED's status tag (group "cc") on public-domain series. The others are
# "copyrighted: citation required" and "copyrighted: pre-approval required".
PUBLIC_DOMAIN_TAG = "public domain: citation requested"

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
    ttl = {"economic_series": 6 * 3600, "series_search": 24 * 3600}
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
        """``FRED_API_KEY`` (required to fetch; the app starts without it),
        ``FRED_API_BASE_URL`` (optional; e2e tests point it at a fake) and
        ``FRED_MIN_INTERVAL_SECONDS`` (optional; only for a fake FRED, which has
        no rate limit: real FRED needs the default 0.5 s)."""
        interval = os.environ.get("FRED_MIN_INTERVAL_SECONDS")
        return cls(
            api_key=os.environ.get("FRED_API_KEY") or None,
            base_url=os.environ.get("FRED_API_BASE_URL") or BASE_URL,
            throttle=Throttle(float(interval)) if interval else _PROCESS_THROTTLE,
        )

    def economic_series(
        self, ctx: RequestContext, series_id: str, start: date, units: str = "lin"
    ) -> EconomicSeries:
        if units not in UNITS_LABELS:
            raise ValueError(f"Unknown FRED units transformation {units!r}")
        raw = self._get("/series", series_id=series_id)
        meta = _only_series(raw, series_id)
        if _mentions_copyright(meta):
            raise NoSuchData(
                FRED.id,
                f"{series_id} is copyrighted by its owner, so Sextant does not republish it.",
                {series_id: f"{series_id} is a copyrighted series."},
            )
        agency = self._allowlist.get(series_id) or self._public_domain_agency(series_id)
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

    def search_series(self, ctx: RequestContext, query: str, limit: int) -> list[SeriesSummary]:
        raw = self._get("/series/search", search_text=query.strip(), tag_names=PUBLIC_DOMAIN_TAG, limit=str(limit))
        hits = raw.get("seriess")  # sic
        try:
            if not isinstance(hits, list):
                raise TypeError("seriess")
            return [
                SeriesSummary(
                    id=str(hit["id"]),
                    title=str(hit["title"]),
                    units=str(hit["units"]),
                    frequency=str(hit["frequency"]),
                    seasonal_adjustment=str(hit["seasonal_adjustment_short"]),
                    last_updated=datetime.fromisoformat(str(hit["last_updated"])).isoformat(),
                    observation_end=str(hit["observation_end"]),
                )
                for hit in hits
                if not _mentions_copyright(hit)
            ][:limit]
        except (KeyError, TypeError, ValueError) as exc:
            raise SourceUnavailable(FRED.id, "FRED returned an unexpected search response.") from exc

    def _public_domain_agency(self, series_id: str) -> str:
        """The publishing agency of a series FRED tags as public domain (from its
        ``src`` tags). ``NoSuchData`` when the series lacks the public-domain tag."""
        tags = self._get("/series/tags", series_id=series_id).get("tags")
        if not isinstance(tags, list) or not all(isinstance(t, dict) for t in tags):
            raise SourceUnavailable(FRED.id, f"FRED returned no tags for {series_id}.")
        if PUBLIC_DOMAIN_TAG not in {str(t.get("name", "")).lower() for t in tags}:
            raise NoSuchData(
                FRED.id,
                f"{series_id} is not in the public domain on FRED, so Sextant does not republish it.",
                {series_id: f"{series_id} is not a public domain series."},
            )
        sources = [_source_name(t) for t in tags if t.get("group_id") == "src"]
        return " / ".join(s for s in sources if s) or "Unknown agency"

    def _get(self, path: str, **params: str) -> dict[str, Any]:
        if not self._api_key:
            raise SourceUnavailable(FRED.id, "FRED_API_KEY is not configured.")
        query = {**params, "api_key": self._api_key, "file_type": "json"}
        series_id = params.get("series_id", "")
        try:
            response = get_with_retries(
                lambda: self._client.get(f"{self._base_url}{path}", params=query),
                attempts=ATTEMPTS,
                backoff=BACKOFF,
                sleep=self._throttle.sleep,
                before_attempt=self._throttle.wait,
            )
        except httpx.HTTPError as exc:
            # Never include the URL: it carries the API key.
            raise SourceUnavailable(FRED.id, f"FRED request failed ({type(exc).__name__}).") from None
        if is_retryable(response.status_code):
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


def _mentions_copyright(series: Mapping[str, Any]) -> bool:
    """FRED's terms: "Copyrighted series contain the word 'Copyright' in their notes"."""
    return "copyright" in str(series.get("notes") or "").lower()


def _source_name(tag: Mapping[str, Any]) -> str:
    """A ``src`` tag's full name: its notes ("U.S. Bureau of Labor Statistics (source)")
    without the suffix, else the short tag name ("bls")."""
    notes = str(tag.get("notes") or "").strip().removesuffix("(source)").strip()
    return notes or str(tag.get("name") or "").strip()


def _only_series(raw: Mapping[str, Any], series_id: str) -> Mapping[str, Any]:
    seriess = raw.get("seriess")  # sic: FRED's key
    if not isinstance(seriess, list) or not seriess or not isinstance(seriess[0], dict):
        raise SourceUnavailable(FRED.id, f"FRED returned no metadata for {series_id}.")
    return seriess[0]
