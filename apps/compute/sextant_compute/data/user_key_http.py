"""Plumbing shared by the bring-your-own-key price providers (Tiingo, FMP).

Each provider adapter subclasses ``UserKeyHttpAdapter`` and keeps only what is
its own: URLs, how its answers say "bad key" or "unknown ticker", and the row
shape. The base class holds the rest:

- ``_key``: the signed-in user's key for this provider, or ``KeyRequired`` with
  the provider's "add a key in Settings" message.
- ``_get``: a GET with the shared retry policy (``data.retry``); a transport
  failure is ``SourceUnavailable`` naming the provider.
- ``_json``: the body, or ``SourceUnavailable`` when it is not JSON.
- ``_per_ticker``: fetch each ticker on its own, collecting every ticker without
  prices into one ``NoSuchData`` (``DailyPricesAdapter``'s contract).

The key is never logged or put in an error message.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import httpx
import pandas as pd

from sextant_compute.data.adapters import Scope
from sextant_compute.data.context import RequestContext
from sextant_compute.data.errors import KeyRequired, NoSuchData, SourceUnavailable
from sextant_compute.data.retry import get_with_retries
from sextant_compute.envelope import DataSource

ATTEMPTS = 2
BACKOFF = 0.5  # seconds


class UserKeyHttpAdapter:
    """Base for a price provider read with the user's own key (``scope = "user"``)."""

    source: DataSource
    scope: Scope = "user"
    no_key_message: str
    """Shown when the user has no key for this provider."""

    def __init__(
        self,
        *,
        base_url: str,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(transport=transport, timeout=10.0)
        self._sleep = sleep

    @property
    def _name(self) -> str:
        return self.source.name

    def _key(self, ctx: RequestContext) -> str:
        key = ctx.key_for(self.source.id)
        if not key:
            raise KeyRequired(self.source.id, self.no_key_message)
        return key

    def _get(
        self, path: str, params: Mapping[str, str] | None = None, headers: Mapping[str, str] | None = None
    ) -> httpx.Response:
        try:
            return get_with_retries(
                lambda: self._client.get(f"{self._base_url}{path}", params=params, headers=headers),
                attempts=ATTEMPTS,
                backoff=BACKOFF,
                sleep=self._sleep,
            )
        except httpx.HTTPError as exc:
            raise SourceUnavailable(self.source.id, f"{self._name} request failed ({type(exc).__name__}).") from None

    def _json(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            raise SourceUnavailable(self.source.id, f"{self._name} returned a response that is not JSON.") from None

    def _per_ticker(
        self, tickers: Sequence[str], fetch: Callable[[str], pd.DataFrame | str]
    ) -> dict[str, pd.DataFrame]:
        """``fetch`` answers one ticker's frame, or why it has none; any missing
        ticker raises one ``NoSuchData`` naming them all."""
        frames: dict[str, pd.DataFrame] = {}
        missing: dict[str, str] = {}
        for ticker in tickers:
            out = fetch(ticker)
            if isinstance(out, str):
                missing[ticker] = out
            else:
                frames[ticker] = out
        if missing:
            raise NoSuchData(self.source.id, " ".join(missing.values()), missing)
        return frames
