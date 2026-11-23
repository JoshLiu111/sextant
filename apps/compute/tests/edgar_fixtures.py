"""Recorded SEC EDGAR responses for tests (no network).

``tests/fixtures/edgar/`` holds trimmed real responses, recorded with
``scripts/record_edgar_fixtures.py``: the ticker map (AAPL, MSFT, JPM, WMT,
GOOGL/GOOG, BRK-B, plus the screener's 37-company universe), companyfacts for
AAPL, MSFT, JPM and WMT, frames (``frames/``, CY2024/CY2025, universe rows only),
the getcurrent Atom feed (``getcurrent/all.atom``, ``getcurrent/10-K.atom``) and
submissions for AAPL and MSFT (``submissions/``).

    adapter = edgar_adapter()                       # serves the fixtures
    adapter = edgar_adapter(edgar_transport(status=503))  # EDGAR is down
    adapter = edgar_adapter(edgar_transport(facts_override={"AAPL": without_tags(load_facts("AAPL"), "us-gaap:Assets")}))
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import httpx

from sextant_compute.data.edgar import EdgarAdapter
from sextant_compute.data.edgar.client import EdgarClient, RateLimiter

FIXTURES = Path(__file__).parent / "fixtures" / "edgar"
TEST_USER_AGENT = "Sextant test admin@example.com"
CIKS = {"AAPL": 320193, "MSFT": 789019, "JPM": 19617, "WMT": 104169}


def load_facts(ticker: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"CIK{CIKS[ticker]:010d}.json").read_text())


def without_tags(facts: dict[str, Any], *tags: str) -> dict[str, Any]:
    """A copy of a companyfacts body with the given ``taxonomy:Tag`` concepts removed."""
    out = copy.deepcopy(facts)
    for tag in tags:
        taxonomy, name = tag.split(":")
        out["facts"].get(taxonomy, {}).pop(name, None)
    return out


class EdgarTransport(httpx.MockTransport):
    """Serves the recorded files by URL path; records every request it sees."""

    def __init__(
        self,
        *,
        status: int | None = None,
        error: Exception | None = None,
        facts_override: Mapping[str, dict[str, Any]] | None = None,
        on_request: Callable[[httpx.Request], None] | None = None,
    ) -> None:
        self.requests: list[httpx.Request] = []
        overrides = {f"CIK{CIKS[t]:010d}.json": body for t, body in (facts_override or {}).items()}

        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            if on_request:
                on_request(request)
            if error is not None:
                raise error
            if status is not None:
                return httpx.Response(status, text="unavailable")
            path = request.url.path
            if path == "/files/company_tickers.json":
                return httpx.Response(200, content=(FIXTURES / "company_tickers.json").read_bytes())
            if path.startswith("/api/xbrl/frames/"):
                file = FIXTURES / path.removeprefix("/api/xbrl/")
                if file.exists():
                    return httpx.Response(200, content=file.read_bytes())
            if path.startswith("/submissions/"):
                file = FIXTURES / path.lstrip("/")
                if file.exists():
                    return httpx.Response(200, content=file.read_bytes())
            if path == "/cgi-bin/browse-edgar":
                file = FIXTURES / "getcurrent" / f"{request.url.params.get('type') or 'all'}.atom"
                if file.exists():
                    return httpx.Response(
                        200, content=file.read_bytes(), headers={"content-type": "application/atom+xml; charset=ISO-8859-1"}
                    )
            if path.startswith("/api/xbrl/companyfacts/"):
                name = path.rsplit("/", 1)[-1]
                if name in overrides:
                    return httpx.Response(200, json=overrides[name])
                file = FIXTURES / name
                if file.exists():
                    return httpx.Response(200, content=file.read_bytes())
            return httpx.Response(404, text="Not found")

        super().__init__(handle)

    def paths(self) -> list[str]:
        return [r.url.path for r in self.requests]


def edgar_transport(**kwargs: Any) -> EdgarTransport:
    return EdgarTransport(**kwargs)


def edgar_adapter(
    transport: EdgarTransport | None = None,
    *,
    user_agent: str | None = TEST_USER_AGENT,
    limiter: RateLimiter | None = None,
) -> EdgarAdapter:
    client = EdgarClient(
        user_agent=user_agent,
        transport=transport or edgar_transport(),
        limiter=limiter or RateLimiter(1000),
        sleep=lambda _s: None,
    )
    return EdgarAdapter(client=client)
