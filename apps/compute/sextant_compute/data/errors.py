"""The two kinds of data error every adapter classifies its failures into.

- ``SourceUnavailable``: the provider is down, timing out, rate limiting us or
  returning garbage. Not the visitor's fault; retrying later may work. The API
  answers 503 ``source_unavailable`` and the UI says "data source temporarily
  unavailable, please retry".
- ``NoSuchData``: the provider answered, and what was asked for doesn't exist
  (unknown ticker, no prices in the range). The visitor should change the input.
  ``missing`` maps each missing identifier (e.g. a ticker) to a human message, so
  the API layer can attach it to the request field that named it.

Adapters must raise one of these for every provider failure (wrap network and
HTTP errors in ``SourceUnavailable``). Anything else escaping an adapter is a bug.
"""

from __future__ import annotations

from collections.abc import Mapping


class DataError(Exception):
    def __init__(self, source: str, message: str) -> None:
        super().__init__(message)
        self.source = source
        self.message = message


class SourceUnavailable(DataError):
    """The provider failed; retry later."""


class NoSuchData(DataError):
    """The provider has no such data. ``missing``: identifier -> message."""

    def __init__(self, source: str, message: str, missing: Mapping[str, str] | None = None) -> None:
        super().__init__(source, message)
        self.missing = dict(missing or {})
