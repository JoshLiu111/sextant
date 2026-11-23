"""The source ids a request model may name for daily prices (the Demo / My data toggle).

``"synthetic"`` is Demo data (shared, anyone). Every other id is a "My data"
provider: a user-scope adapter that runs on the visitor's own key, so a request
naming it without a key answers 403 ``key_required`` (``DataService``).

This module is the provider registry: a new provider is a ``DataSource`` in
``MY_DATA_SOURCES`` and its id in ``MyDataProvider`` (checked to match at
import), plus its adapter in ``default_adapters()`` and its key verifier in
``keys.api.get_verifiers``. Settings (``keys.api``) accepts keys for exactly
these providers. The web mirror is ``PROVIDER_NAMES`` in
``apps/web/src/lib/providerKeys.ts``. With several keys the user picks the
provider per request; the envelope's ``source`` names the one actually used.
"""

from __future__ import annotations

from typing import Literal, get_args

from sextant_compute.envelope import DataSource

TIINGO = DataSource(id="tiingo", name="Tiingo", is_demo=False)
FMP = DataSource(id="fmp", name="FMP", is_demo=False)

MY_DATA_SOURCES: dict[str, DataSource] = {s.id: s for s in (TIINGO, FMP)}
"""Every My data provider, by id, in the order Settings lists them."""

MyDataProvider = Literal["tiingo", "fmp"]
PriceSource = Literal["synthetic", MyDataProvider]

DEMO_SOURCE = "synthetic"

assert set(get_args(MyDataProvider)) == set(MY_DATA_SOURCES), "MyDataProvider must list MY_DATA_SOURCES"

DEMO_TICKER_PREFIX = "DEMO-"
"""Every Demo data ticker starts with this (``DEMO-MKT``, ``DEMO-A``...)."""


def is_demo_ticker(ticker: str) -> bool:
    """A made-up Demo data ticker, which no My data provider has."""
    return ticker.upper().startswith(DEMO_TICKER_PREFIX)
