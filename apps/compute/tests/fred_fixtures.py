"""Recorded FRED API responses, served without the network.

``tests/fixtures/fred/series/<ID>.json`` is the body of ``GET /fred/series`` and
``tests/fixtures/fred/observations/<ID>.json`` the body of
``GET /fred/series/observations`` for that series. The files are hand-crafted
from the documented v1 JSON shapes (see sextant-notes research/fred.md; a real
key was not available when they were made): field names, the ``seriess`` key,
string values with ``"."`` for missing observations and ``-05``/``-06``
timestamps are faithful; the numbers are approximate. The same files back the
e2e fake (``apps/web/e2e/fake-fred.mjs``), which applies the same routing rules
as ``RecordedFred`` below. Unknown series answer like FRED does: 400 "The series
does not exist."
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx

from sextant_compute.data.fred import FredAdapter, Throttle

FIXTURES = Path(__file__).parent / "fixtures" / "fred"
TEST_KEY = "0123456789abcdef0123456789abcdef"

SERIES_DOES_NOT_EXIST = {"error_code": 400, "error_message": "Bad Request.  The series does not exist."}


class RecordedFred:
    """An httpx transport answering from the fixture files; records every request.

    ``override(path, series_id) -> httpx.Response | None`` lets a test replace a
    response (e.g. a 500 or a 429) before the recording is consulted.
    """

    def __init__(self, override: Callable[[str, str], httpx.Response | None] | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.override = override
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        series_id = request.url.params.get("series_id", "")
        path = request.url.path
        if self.override and (response := self.override(path, series_id)) is not None:
            return response
        folder = {"/fred/series": "series", "/fred/series/observations": "observations"}.get(path)
        file = FIXTURES / folder / f"{series_id}.json" if folder else None
        if file is None or not file.is_file():
            return httpx.Response(400, json=SERIES_DOES_NOT_EXIST)
        return httpx.Response(200, json=json.loads(file.read_text()))

    def paths(self) -> list[str]:
        return [r.url.path for r in self.requests]


class FakeClock:
    """Monotonic clock + sleep for the throttle: sleeping advances time instantly."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def recorded_adapter(fred: RecordedFred | None = None, clock: FakeClock | None = None, **kwargs) -> FredAdapter:
    """A ``FredAdapter`` on the recordings, with a fake clock so tests never sleep."""
    fred = fred or RecordedFred()
    clock = clock or FakeClock()
    kwargs.setdefault("api_key", TEST_KEY)
    return FredAdapter(
        transport=fred.transport,
        throttle=Throttle(min_interval=0.5, clock=clock, sleep=clock.sleep),
        **kwargs,
    )
