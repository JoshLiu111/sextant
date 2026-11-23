"""Recorded World Bank Indicators API responses, served without the network.

Recorded from api.worldbank.org on 2026-11-23 and stored as returned:

- ``fixtures/world_bank/indicators/<ID>.json``: the body of
  ``/v2/country/ARG;AUS;BRA;CAN;CHN;DEU;EMU;ESP;FRA;GBR;IND;ITA;JPN;KOR;MEX;USA;ZAF/indicator/<ID>?format=json&date=2000:2026&per_page=1000``
  (17 economies, 2000-2025, one page; ``lastupdated`` 2026-11-11).
- ``fixtures/world_bank/metadata/<ID>.json``: the body of
  ``/v2/sources/2/series/<ID>/metadata?format=json`` (WDI metadata, including
  ``License_Type``).

Whatever countries or years a request names, the recording for its indicator is
served (the adapter filters by country and year itself). The e2e fake
(``apps/web/e2e/fake-world-bank.mjs``) applies the same routing rules.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import httpx

from sextant_compute.data.world_bank import WorldBankAdapter

FIXTURES = Path(__file__).parent / "fixtures" / "world_bank"
DATA_PATH = re.compile(r"^/v2/country/([^/]+)/indicator/([^/]+)$")
METADATA_PATH = re.compile(r"^/v2/sources/2/series/([^/]+)/metadata$")

# What World Bank answers for an indicator id it doesn't know (HTTP 200).
INVALID_VALUE = b'[{"message":[{"id":"120","key":"Invalid value","value":"The provided parameter value is not valid"}]}]'


class RecordedWorldBank:
    """An httpx transport answering from the fixture files; records every request.

    ``override(request) -> httpx.Response | None`` lets a test replace a response
    (a 500, a different license) before the recording is consulted.
    """

    def __init__(self, override: Callable[[httpx.Request], httpx.Response | None] | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.override = override
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.override and (response := self.override(request)) is not None:
            return response
        if request.url.params.get("format") != "json":
            return httpx.Response(400, text="format=json expected")
        path = request.url.path
        if match := DATA_PATH.match(path):
            file = FIXTURES / "indicators" / f"{match.group(2)}.json"
            body = file.read_bytes() if file.is_file() else INVALID_VALUE
            return httpx.Response(200, content=body, headers={"content-type": "application/json"})
        if match := METADATA_PATH.match(path):
            file = FIXTURES / "metadata" / f"{match.group(1)}.json"
            if not file.is_file():
                return httpx.Response(200, text="<wb:error>Data not found.</wb:error>")
            return httpx.Response(200, content=file.read_bytes(), headers={"content-type": "application/json"})
        return httpx.Response(404, text="Not found")

    def paths(self) -> list[str]:
        return [r.url.path for r in self.requests]


def recorded_adapter(world_bank: RecordedWorldBank | None = None, **kwargs) -> WorldBankAdapter:
    """A ``WorldBankAdapter`` on the recordings that never sleeps between retries."""
    world_bank = world_bank or RecordedWorldBank()
    kwargs.setdefault("sleep", lambda seconds: None)
    return WorldBankAdapter(transport=world_bank.transport, **kwargs)
