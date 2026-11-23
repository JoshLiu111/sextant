"""HTTP access to SEC EDGAR: User-Agent, rate limit, retries, error classification.

SEC fair-access rules (https://www.sec.gov/os/webmaster-faq,
https://www.sec.gov/about/developer-resources):

- At most 10 requests/second in total. ``EDGAR_RATE_LIMITER`` is shared by every
  ``EdgarClient`` in the process and allows ``EDGAR_MAX_PER_SECOND`` (5), leaving
  headroom for a second serverless instance. It is per process: SEC counts per
  IP/user across machines, so keep EDGAR calls cached (DataService does).
- A declared User-Agent with a contact is required (403 otherwise). It is read
  from the ``SEC_USER_AGENT`` env var and never committed.

Every failure leaves as ``SourceUnavailable`` (down, timeout, 403/429/5xx,
missing User-Agent, unparsable body) or as ``NotFound`` (HTTP 404), which callers
turn into ``NoSuchData``.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

import httpx

from sextant_compute.data.errors import SourceUnavailable
from sextant_compute.data.retry import get_with_retries

log = logging.getLogger(__name__)

SOURCE_ID = "sec_edgar"
EDGAR_MAX_PER_SECOND = 5
USER_AGENT_ENV = "SEC_USER_AGENT"
BASE_URL_ENV = "EDGAR_BASE_URL"
WWW_URL = "https://www.sec.gov"
DATA_URL = "https://data.sec.gov"
RETRIES = 2
RETRY_BACKOFF = 0.5  # seconds, doubled per retry
TIMEOUT_SECONDS = 20.0


class RateLimiter:
    """At most ``max_per_second`` grants in any one-second window (sliding window).

    Thread-safe; waiters queue on the lock, so concurrent callers share the limit.
    """

    def __init__(
        self,
        max_per_second: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._max = max_per_second
        self._clock = clock
        self._sleep = sleep
        self._grants: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> float:
        """Block until a request may go out; returns the (clock) time it was granted."""
        with self._lock:
            while True:
                now = self._clock()
                while self._grants and now - self._grants[0] >= 1.0:
                    self._grants.popleft()
                if len(self._grants) < self._max:
                    self._grants.append(now)
                    return now
                self._sleep(self._grants[0] + 1.0 - now)


EDGAR_RATE_LIMITER = RateLimiter(EDGAR_MAX_PER_SECOND)


class NotFound(Exception):
    """EDGAR answered 404."""


class EdgarClient:
    """GET JSON from EDGAR within the fair-access rules.

    ``transport`` lets tests serve recorded responses (``httpx.MockTransport``).
    ``base_url`` (env ``EDGAR_BASE_URL``, e2e tests only) replaces both
    www.sec.gov and data.sec.gov so a fake EDGAR server can stand in.
    """

    def __init__(
        self,
        *,
        user_agent: str | None = None,
        base_url: str | None = None,
        transport: httpx.BaseTransport | None = None,
        limiter: RateLimiter = EDGAR_RATE_LIMITER,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._user_agent = user_agent
        self._base_url = base_url
        self._transport = transport
        self._limiter = limiter
        self._sleep = sleep
        self._http: httpx.Client | None = None

    def _client(self) -> httpx.Client:
        if self._http is None:
            ua = self._user_agent if self._user_agent is not None else os.environ.get(USER_AGENT_ENV, "")
            if not ua.strip():
                log.error("%s is not set; EDGAR requires a declared User-Agent with a contact", USER_AGENT_ENV)
                raise SourceUnavailable(SOURCE_ID, f"{USER_AGENT_ENV} is not configured")
            self._http = httpx.Client(
                headers={"User-Agent": ua.strip(), "Accept-Encoding": "gzip, deflate"},
                timeout=TIMEOUT_SECONDS,
                transport=self._transport,
                follow_redirects=True,
            )
        return self._http

    def url(self, host: str, path: str) -> str:
        base = self._base_url or os.environ.get(BASE_URL_ENV) or host
        return f"{base.rstrip('/')}{path}"

    def get_json(self, host: str, path: str) -> Any:
        """GET ``host + path`` (``WWW_URL`` or ``DATA_URL``) and parse the JSON body."""
        res = self._get(host, path)
        try:
            return res.json()
        except ValueError as exc:
            raise SourceUnavailable(SOURCE_ID, f"unparsable JSON from {res.request.url}") from exc

    def get_text(self, host: str, path: str) -> str:
        """GET ``host + path`` and return the decoded body (e.g. the Atom feed)."""
        return self._get(host, path).text

    def _get(self, host: str, path: str) -> httpx.Response:
        client = self._client()
        url = self.url(host, path)
        try:
            res = get_with_retries(
                lambda: client.get(url),
                attempts=RETRIES + 1,
                backoff=RETRY_BACKOFF,
                sleep=self._sleep,
                before_attempt=self._limiter.acquire,
                retry_transport_errors=True,
            )
        except httpx.HTTPError as exc:
            raise SourceUnavailable(SOURCE_ID, f"{type(exc).__name__}: {exc} from {url}") from exc
        if res.status_code == 404:
            raise NotFound(url)
        if res.status_code != 200:
            # 403 means a missing/undeclared User-Agent or an IP block; retrying won't help.
            raise SourceUnavailable(SOURCE_ID, f"HTTP {res.status_code} from {url}")
        return res
