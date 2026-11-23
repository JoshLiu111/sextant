"""The ECB adapter: ``economic_series`` from the ECB Data Portal SDMX REST API
(``data-api.ecb.europa.eu/service/data/<FLOW>/<KEY>?format=csvdata``). No key.

Terms (ADR 0004): the ECB statistics reuse policy allows free reuse, commercial
or not, provided the source is quoted ("Source: ECB statistics.") and the data
are not modified; it does not cover third-party data without the originator's
permission. The key ECB interest rates are the ECB's own. The euro area HICP is
compiled by Eurostat, whose copyright notice authorises reuse of its statistics
"for commercial or non-commercial purposes ... provided the source is
acknowledged". So only ``ALLOWED_SERIES`` (each checked by hand) are fetched,
and pages credit the ECB, and Eurostat for HICP (web: the ``ecb`` attribution).

CSV shape (one row per observation): ``KEY,FREQ,...,TIME_PERIOD,OBS_VALUE,...,
TITLE,TITLE_COMPL,UNIT,UNIT_MULT``. ``TIME_PERIOD`` is ``YYYY-MM-DD`` for daily
and business series (the key rates list only the days they changed) and
``YYYY-MM`` for monthly ones. The portal publishes no revision timestamp in
the data, so ``last_updated`` is the response's ``Last-Modified`` header (the
fetch time if absent). A key with no data answers 404. The portal's bot wall
answers an HTML page, which is ``SourceUnavailable``.
"""

from __future__ import annotations

import csv
import io
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime

import httpx

from sextant_compute.data.adapters import EconomicSeries, Scope, SeriesMeta
from sextant_compute.data.context import RequestContext
from sextant_compute.data.errors import NoSuchData, SourceUnavailable
from sextant_compute.data.retry import get_with_retries
from sextant_compute.envelope import DataSource

ECB = DataSource(id="ecb", name="European Central Bank", is_demo=False)

BASE_URL = "https://data-api.ecb.europa.eu"
USER_AGENT = "Mozilla/5.0 (compatible; Sextant/0.1; open-source finance tools)"

ATTEMPTS = 3
BACKOFF = 1.0  # seconds, doubled per retry


@dataclass(frozen=True)
class AllowedSeries:
    source: str
    """Who compiles the data (the ECB, or Eurostat for HICP)."""
    units: str
    frequency: str
    seasonal_adjustment: str = ""


_KEY_RATE = AllowedSeries("European Central Bank", "Percent per annum", "On change (Governing Council decisions)")

# Series we may republish (ECB reuse policy, Eurostat copyright notice; checked 2026-11-23).
ALLOWED_SERIES: Mapping[str, AllowedSeries] = {
    "FM/B.U2.EUR.4F.KR.DFR.LEV": _KEY_RATE,
    "FM/B.U2.EUR.4F.KR.MRR_FR.LEV": _KEY_RATE,
    "FM/B.U2.EUR.4F.KR.MLFR.LEV": _KEY_RATE,
    # Replaced ICP/M.U2.N.000000.4.ANR, which the ECB discontinued in February 2026.
    "HICP/M.U2.N.000000.4D0.ANR": AllowedSeries(
        "Eurostat (via the ECB)", "Annual rate of change, percent", "Monthly", "NSA"
    ),
}


class EcbAdapter:
    source = ECB
    scope: Scope = "shared"
    # Rates change on Governing Council dates and HICP monthly; responses say max-age=30.
    ttl = {"economic_series": 6 * 3600}
    version = "1"

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        transport: httpx.BaseTransport | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._now = now
        self._sleep = sleep
        self._client = httpx.Client(transport=transport, timeout=20.0, headers={"User-Agent": USER_AGENT})

    @classmethod
    def from_env(cls) -> EcbAdapter:
        """``ECB_BASE_URL`` (optional; e2e tests point it at a fake)."""
        return cls(base_url=os.environ.get("ECB_BASE_URL") or BASE_URL)

    def economic_series(self, ctx: RequestContext, series_id: str, start: date, units: str = "lin") -> EconomicSeries:
        if units != "lin":
            raise ValueError(f"The ECB adapter serves published values only (units='lin'), not {units!r}")
        allowed = ALLOWED_SERIES.get(series_id)
        if allowed is None:
            raise NoSuchData(
                ECB.id,
                f"{series_id} is not on Sextant's list of ECB series it may republish.",
                {series_id: "Not an ECB series Sextant may republish."},
            )
        response = self._get(series_id, start)
        if response.status_code == 404:
            raise NoSuchData(ECB.id, f"The ECB has no data for {series_id}.", {series_id: "No such ECB series."})
        if response.status_code != 200:
            raise SourceUnavailable(ECB.id, f"The ECB answered HTTP {response.status_code}.")

        title, observations = _parse(response.text, series_id)
        meta = SeriesMeta(
            id=series_id,
            title=title,
            source=allowed.source,
            units=allowed.units,
            frequency=allowed.frequency,
            seasonal_adjustment=allowed.seasonal_adjustment,
            last_updated=self._last_modified(response).isoformat(timespec="seconds"),
        )
        return EconomicSeries(
            source=ECB, meta=meta, observations=[(when, value) for when, value in observations if when >= start]
        )

    def _get(self, series_id: str, start: date) -> httpx.Response:
        url = f"{self._base_url}/service/data/{series_id}"
        params = {"format": "csvdata", "startPeriod": start.isoformat()}
        try:
            return get_with_retries(
                lambda: self._client.get(url, params=params), attempts=ATTEMPTS, backoff=BACKOFF, sleep=self._sleep
            )
        except httpx.HTTPError as exc:
            raise SourceUnavailable(ECB.id, f"ECB request failed ({type(exc).__name__}).") from None

    def _last_modified(self, response: httpx.Response) -> datetime:
        header = response.headers.get("last-modified")
        if header:
            try:
                return parsedate_to_datetime(header).astimezone(UTC)
            except (TypeError, ValueError):
                pass
        return self._now()


def _period_start(period: str) -> date:
    """``2026-09-16`` -> that day; ``2026-10`` -> 2026-10-01."""
    return date.fromisoformat(period if len(period) == 10 else f"{period}-01")


def _parse(text: str, series_id: str) -> tuple[str, list[tuple[date, float | None]]]:
    rows = csv.DictReader(io.StringIO(text))
    if not rows.fieldnames or "TIME_PERIOD" not in rows.fieldnames or "OBS_VALUE" not in rows.fieldnames:
        raise SourceUnavailable(ECB.id, f"The ECB returned an unexpected response for {series_id}.")
    title = ""
    observations: list[tuple[date, float | None]] = []
    try:
        for row in rows:
            title = title or (row.get("TITLE") or "").strip()
            value = (row["OBS_VALUE"] or "").strip()
            observations.append((_period_start(row["TIME_PERIOD"].strip()), float(value) if value else None))
    except (TypeError, ValueError) as exc:
        raise SourceUnavailable(ECB.id, f"The ECB returned an unexpected response for {series_id}.") from exc
    observations.sort(key=lambda o: o[0])
    return title or series_id, observations
