"""The request context every DataService method takes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from uuid import UUID


@dataclass(frozen=True)
class RequestContext:
    """Who is asking, and with which of their own provider keys.

    ``user_id`` is None for anonymous visitors. ``keys`` maps a provider id (the
    adapter's ``source.id``, e.g. ``"tiingo"``) to that user's decrypted API key.
    Data fetched with a user's key is cached under that user only (see
    ``DataService``); it never reaches the shared cache.
    """

    user_id: UUID | None = None
    keys: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    @classmethod
    def anonymous(cls) -> RequestContext:
        return cls()

    def key_for(self, provider: str) -> str | None:
        return self.keys.get(provider)
