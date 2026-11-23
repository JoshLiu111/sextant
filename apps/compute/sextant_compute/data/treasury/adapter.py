"""The US Treasury adapter: ``yield_curves`` from the Daily Treasury Par Yield
Curve Rates CSV on home.treasury.gov (one request per calendar year).

Terms (ADR 0002): the rates are a US Government work (17 U.S.C. 105), and
Treasury publishes no terms of use, license or rate limit for them (pages
re-checked 2026-11-22). Pages using them cite Treasury and say Treasury does
not endorse Sextant (web: the ``treasury`` attribution). No API key.

CSV shape: header ``Date,"1 Mo","1.5 Month",...,"30 Yr"``, rows newest first,
dates ``MM/DD/YYYY``, values in percent, an empty cell when a maturity was not
published that day. The column set changes over the years (no ``4 Mo`` before
late 2022, no ``1.5 Month`` before 2025), so columns are parsed by name.
A year with no data yet answers 200 with an empty body.
"""

from __future__ import annotations

import csv
import io
import os
import re
import time
from collections.abc import Callable
from datetime import UTC, date, datetime

import httpx

from sextant_compute.data.adapters import Curve, Scope, SeriesMeta, YieldCurves
from sextant_compute.data.context import RequestContext
from sextant_compute.data.errors import SourceUnavailable
from sextant_compute.data.retry import get_with_retries
from sextant_compute.envelope import DataSource

TREASURY = DataSource(id="treasury", name="U.S. Department of the Treasury", is_demo=False)

BASE_URL = "https://home.treasury.gov"
CSV_PATH = "/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{year}/all"
PAGE_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "TextView?type=daily_treasury_yield_curve"
)
USER_AGENT = "Mozilla/5.0 (compatible; Sextant/0.1; open-source finance tools)"

TITLE = "Daily Treasury Par Yield Curve Rates"
UNITS = "Percent"
FREQUENCY = "Daily (business days)"

ATTEMPTS = 3
BACKOFF = 1.0  # seconds, doubled per retry

_TENOR = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(mo|month|months|yr|year|years)\s*$", re.IGNORECASE)


def tenor_months(header: str) -> float | None:
    """``"1 Mo"`` -> 1, ``"1.5 Month"`` -> 1.5, ``"10 Yr"`` -> 120; None for other columns."""
    match = _TENOR.match(header)
    if not match:
        return None
    n = float(match.group(1))
    return n * 12 if match.group(2).lower().startswith("y") else n


class TreasuryAdapter:
    source = TREASURY
    scope: Scope = "shared"
    # Treasury publishes one new curve per business day (about 3:30 PM ET quotes).
    # Its responses say ``cache-control: no-cache``, so caching is ours to do.
    ttl = {"yield_curves": 6 * 3600}
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
        self._client = httpx.Client(transport=transport, timeout=15.0, headers={"User-Agent": USER_AGENT})

    @classmethod
    def from_env(cls) -> TreasuryAdapter:
        """``TREASURY_BASE_URL`` (optional; e2e tests point it at a fake)."""
        return cls(base_url=os.environ.get("TREASURY_BASE_URL") or BASE_URL)

    def yield_curves(self, ctx: RequestContext, year: int) -> YieldCurves:
        text = self._get_csv(year)
        meta = SeriesMeta(
            id="daily_treasury_yield_curve",
            title=TITLE,
            source=TREASURY.name,
            units=UNITS,
            frequency=FREQUENCY,
            seasonal_adjustment="NSA",
            last_updated=self._now().isoformat(timespec="seconds"),
        )
        return YieldCurves(source=TREASURY, meta=meta, curves=_parse(text, year))

    def _get_csv(self, year: int) -> str:
        params = {"type": "daily_treasury_yield_curve", "field_tdr_date_value": str(year), "page": "", "_format": "csv"}
        url = f"{self._base_url}{CSV_PATH.format(year=year)}"
        try:
            response = get_with_retries(
                lambda: self._client.get(url, params=params), attempts=ATTEMPTS, backoff=BACKOFF, sleep=self._sleep
            )
        except httpx.HTTPError as exc:
            raise SourceUnavailable(TREASURY.id, f"Treasury request failed ({type(exc).__name__}).") from None
        if response.status_code != 200:
            raise SourceUnavailable(TREASURY.id, f"Treasury answered HTTP {response.status_code}.")
        return response.text


def _parse(text: str, year: int) -> list[tuple[date, Curve]]:
    if not text.strip():
        return []
    rows = csv.reader(io.StringIO(text))
    header = next(rows)
    if not header or header[0].strip().lstrip("﻿") != "Date":
        raise SourceUnavailable(TREASURY.id, f"Treasury returned an unexpected CSV for {year}.")
    tenors = [tenor_months(h) for h in header]
    curves: list[tuple[date, Curve]] = []
    try:
        for row in rows:
            if not row:
                continue
            when = datetime.strptime(row[0].strip(), "%m/%d/%Y").date()
            curve: Curve = {}
            for months, cell in zip(tenors, row, strict=False):
                if months is not None and cell.strip():
                    curve[months] = float(cell)
            curves.append((when, curve))
    except ValueError as exc:
        raise SourceUnavailable(TREASURY.id, f"Treasury returned an unexpected CSV for {year}.") from exc
    curves.sort(key=lambda c: c[0])
    return curves
