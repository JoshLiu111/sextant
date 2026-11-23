"""The Tiingo adapter. Every request uses the signed-in user's own key.

Tiingo's terms forbid showing its data to anyone but the key holder, so the
adapter's scope is ``"user"``: ``DataService`` caches what it fetches under that
user only, never in the shared cache.

For now it only checks keys (``verify_key``, used by Settings before a key is
saved). The price datasets come with Risk & Performance on My data.

``GET /api/test`` is the lightweight check. Checked 2026-11-22: it answers
HTTP 200 for every token and says in ``message`` whether the token worked:

- ``"You successfully sent a request"``: the token is valid.
- ``"Auth Token was not correct"``: the token is wrong.

A 401/403 (what the data endpoints answer, with ``{"detail": "Invalid token."}``)
also means the token is wrong. Anything else (429, 5xx, a network error, a body
we can't read) is ``SourceUnavailable``: we don't know whether the key is good.
The key is never logged or put in an error message.
"""

from __future__ import annotations

import os
import time

import httpx

from sextant_compute.data.adapters import Scope
from sextant_compute.data.errors import SourceUnavailable
from sextant_compute.data.retry import get_with_retries
from sextant_compute.envelope import DataSource

TIINGO = DataSource(id="tiingo", name="Tiingo", is_demo=False)

BASE_URL = "https://api.tiingo.com"
ATTEMPTS = 2
BACKOFF = 0.5  # seconds


class TiingoAdapter:
    source = TIINGO
    scope: Scope = "user"
    ttl: dict[str, int] = {}
    version = "1"

    def __init__(self, *, base_url: str = BASE_URL, transport: httpx.BaseTransport | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(transport=transport, timeout=10.0)

    @classmethod
    def from_env(cls) -> TiingoAdapter:
        """``TIINGO_BASE_URL`` (optional; e2e tests point it at a fake)."""
        return cls(base_url=os.environ.get("TIINGO_BASE_URL") or BASE_URL)

    def verify_key(self, key: str) -> bool:
        """True if Tiingo accepts ``key``, False if it rejects it.

        Raises ``SourceUnavailable`` when Tiingo can't tell us either way.
        """
        try:
            response = get_with_retries(
                lambda: self._client.get(
                    f"{self._base_url}/api/test",
                    headers={"Authorization": f"Token {key}", "Content-Type": "application/json"},
                ),
                attempts=ATTEMPTS,
                backoff=BACKOFF,
                sleep=time.sleep,
            )
        except httpx.HTTPError as exc:
            raise SourceUnavailable(TIINGO.id, f"Tiingo request failed ({type(exc).__name__}).") from None
        if response.status_code in (401, 403):
            return False
        if response.status_code != 200:
            raise SourceUnavailable(TIINGO.id, f"Tiingo answered HTTP {response.status_code}.")
        try:
            body = response.json()
        except ValueError:
            raise SourceUnavailable(TIINGO.id, "Tiingo returned a response that is not JSON.") from None
        message = str(body.get("message", "")).lower() if isinstance(body, dict) else ""
        if "successfully" in message:
            return True
        if "not correct" in message or "invalid" in message:
            return False
        raise SourceUnavailable(TIINGO.id, "Tiingo returned an unexpected response to the key check.")
