"""Recorded ECB Data Portal responses, served without the network.

``fixtures/ecb/<FLOW>/<KEY>.csv`` is the body of
``data-api.ecb.europa.eu/service/data/<FLOW>/<KEY>?format=csvdata``, recorded on
2026-11-23 and stored as returned (CRLF line endings). The three key ECB
interest rates (``FM/B.U2.EUR.4F.KR.{DFR,MRR_FR,MLFR}.LEV``) are their full
change histories since 1999; the euro area HICP annual rate
(``HICP/M.U2.N.000000.4D0.ANR``) was recorded with ``startPeriod=1999-01`` and
runs to 2026-10. ``fixtures/ecb/last_modified.json`` holds each response's
``Last-Modified`` header, which the recording replays.

The recording is served whatever ``startPeriod`` a request sends (the adapter
filters by date itself). The e2e fake (``apps/web/e2e/fake-ecb.mjs``) applies
the same routing rules.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

import httpx

from sextant_compute.data.ecb import EcbAdapter

FIXTURES = Path(__file__).parent / "fixtures" / "ecb"
DATA_PATH = re.compile(r"^/service/data/([A-Z0-9_]+)/([A-Za-z0-9_.]+)$")
LAST_MODIFIED: dict[str, str] = json.loads((FIXTURES / "last_modified.json").read_text())

# What the ECB answers for a series key with no data (HTTP 404, JSON body).
NO_SERIES = '{"detail":"No Series was returned for the query","status":404,"title":"Not Found"}'


class RecordedEcb:
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
        match = DATA_PATH.match(request.url.path)
        if not match or request.url.params.get("format") != "csvdata":
            return httpx.Response(400, text="Bad request")
        flow, key = match.groups()
        file = FIXTURES / flow / f"{key}.csv"
        if not file.is_file():
            return httpx.Response(404, text=NO_SERIES, headers={"content-type": "application/json"})
        headers = {"content-type": "text/csv"}
        if modified := LAST_MODIFIED.get(f"{flow}/{key}"):
            headers["last-modified"] = modified
        return httpx.Response(200, content=file.read_bytes(), headers=headers)

    def paths(self) -> list[str]:
        return [r.url.path for r in self.requests]


def recorded_adapter(ecb: RecordedEcb | None = None, **kwargs) -> EcbAdapter:
    """An ``EcbAdapter`` on the recordings that never sleeps between retries."""
    ecb = ecb or RecordedEcb()
    kwargs.setdefault("sleep", lambda seconds: None)
    return EcbAdapter(transport=ecb.transport, **kwargs)
