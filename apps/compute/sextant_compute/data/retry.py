"""The retry loop the HTTP adapters share: back off and retry on 429 and 5xx.

Each adapter still classifies the final response itself (FRED, Treasury and
EDGAR word their errors differently); this only decides when to try again.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx


def is_retryable(status_code: int) -> bool:
    """Rate limited (429) or a server error (5xx): worth another try."""
    return status_code == 429 or status_code >= 500


def get_with_retries(
    get: Callable[[], httpx.Response],
    *,
    attempts: int,
    backoff: float,
    sleep: Callable[[float], None],
    before_attempt: Callable[[], None] | None = None,
    retry_transport_errors: bool = False,
) -> httpx.Response:
    """Call ``get`` up to ``attempts`` times while it answers 429/5xx.

    Waits ``backoff``, then ``2 × backoff``, ... between attempts, and calls
    ``before_attempt`` (a rate limiter) before each one. Returns the last
    response, which can still be a 429/5xx when the attempts ran out. An
    ``httpx.HTTPError`` propagates at once, or only after the last attempt when
    ``retry_transport_errors`` is set.
    """
    for attempt in range(attempts):
        if attempt:
            sleep(backoff * 2 ** (attempt - 1))
        if before_attempt is not None:
            before_attempt()
        try:
            response = get()
        except httpx.HTTPError:
            if retry_transport_errors and attempt + 1 < attempts:
                continue
            raise
        if not is_retryable(response.status_code) or attempt + 1 == attempts:
            return response
    raise ValueError("attempts must be at least 1")
