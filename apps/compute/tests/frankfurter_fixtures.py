"""Recorded Frankfurter responses, served without the network.

``tests/fixtures/frankfurter/<BASE>-<QUOTE>-<YEAR>.json`` is the body of
``GET /v2/rates?from=<YEAR>-01-01&to=<YEAR>-12-31&base=<BASE>&quotes=<QUOTE>``,
fetched from api.frankfurter.dev on 2026-11-22 and stored as returned (one row
per calendar day, blended rates). ``invalid-XYZ.json`` is the 422 body for an
unsupported currency. A year without a file answers like Frankfurter does for a
year with no rates (before the currency existed, or in the future): 200 ``[]``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx

from sextant_compute.data.frankfurter import FrankfurterAdapter

FIXTURES = Path(__file__).parent / "fixtures" / "frankfurter"
SUPPORTED = {"EUR", "USD", "GBP", "JPY", "CHF", "CAD"}
"""Currencies the recorded API accepts (a subset of Frankfurter's list); others answer the recorded 422."""


class RecordedFrankfurter:
    """An httpx transport answering from the fixture files; records every request.

    ``override(request) -> httpx.Response | None`` lets a test replace a response.
    """

    def __init__(self, override: Callable[[httpx.Request], httpx.Response | None] | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.override = override
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.override and (response := self.override(request)) is not None:
            return response
        if request.url.path != "/v2/rates":
            return httpx.Response(404, json={"status": 404, "message": "not found"})
        params = request.url.params
        base, quote = params.get("base", "").upper(), params.get("quotes", "").upper()
        for code in (base, quote):
            if code not in SUPPORTED:
                body = (FIXTURES / "invalid-XYZ.json").read_text().replace("XYZ", code)
                return httpx.Response(422, content=body.encode(), headers={"content-type": "application/json"})
        year = params.get("from", "")[:4]
        file = FIXTURES / f"{base}-{quote}-{year}.json"
        body = file.read_bytes() if file.is_file() else b"[]"
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    def pairs(self) -> list[tuple[str, str, str]]:
        """``(base, quote, year)`` of every rates request, in order."""
        return [
            (r.url.params.get("base", ""), r.url.params.get("quotes", ""), r.url.params.get("from", "")[:4])
            for r in self.requests
            if r.url.path == "/v2/rates"
        ]


def recorded_adapter(frankfurter: RecordedFrankfurter | None = None, **kwargs) -> FrankfurterAdapter:
    """A ``FrankfurterAdapter`` on the recordings that never sleeps between retries."""
    frankfurter = frankfurter or RecordedFrankfurter()
    kwargs.setdefault("sleep", lambda seconds: None)
    return FrankfurterAdapter(transport=frankfurter.transport, **kwargs)
