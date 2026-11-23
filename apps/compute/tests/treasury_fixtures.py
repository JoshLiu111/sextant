"""Recorded US Treasury responses, served without the network.

``tests/fixtures/treasury/<YEAR>.csv`` is the body of the Daily Treasury Par
Yield Curve CSV for that year, fetched from home.treasury.gov on 2026-11-22 and
stored as returned (newest date first, no trailing newline; 2018-2024 have no
``1.5 Month`` column, 2018-2021 no ``4 Mo``). A year without a file answers like
Treasury does for a year with no data yet: 200 with an empty body. The same
files back the e2e fake (``apps/web/e2e/fake-treasury.mjs``), which applies the
same routing rules as ``RecordedTreasury`` below.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import httpx

from sextant_compute.data.treasury import TreasuryAdapter

FIXTURES = Path(__file__).parent / "fixtures" / "treasury"
CSV_PATH = re.compile(r"^/resource-center/data-chart-center/interest-rates/daily-treasury-rates\.csv/(\d{4})/all$")


class RecordedTreasury:
    """An httpx transport answering from the fixture files; records every request.

    ``override(year) -> httpx.Response | None`` lets a test replace the response
    for a year (a 500, a hand-made CSV) before the recording is consulted.
    """

    def __init__(self, override: Callable[[int], httpx.Response | None] | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.override = override
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        match = CSV_PATH.match(request.url.path)
        params = request.url.params
        if not match or params.get("type") != "daily_treasury_yield_curve" or params.get("_format") != "csv":
            return httpx.Response(404, text="Not found")
        year = int(match.group(1))
        if self.override and (response := self.override(year)) is not None:
            return response
        file = FIXTURES / f"{year}.csv"
        body = file.read_bytes() if file.is_file() else b""
        return httpx.Response(200, content=body, headers={"content-type": "text/csv; charset=UTF-8"})

    def years(self) -> list[int]:
        out = []
        for r in self.requests:
            match = CSV_PATH.match(r.url.path)
            if match:
                out.append(int(match.group(1)))
        return out


def csv_response(text: str) -> httpx.Response:
    return httpx.Response(200, content=text.encode(), headers={"content-type": "text/csv; charset=UTF-8"})


def recorded_adapter(treasury: RecordedTreasury | None = None, **kwargs) -> TreasuryAdapter:
    """A ``TreasuryAdapter`` on the recordings that never sleeps between retries."""
    treasury = treasury or RecordedTreasury()
    kwargs.setdefault("sleep", lambda seconds: None)
    return TreasuryAdapter(transport=treasury.transport, **kwargs)
