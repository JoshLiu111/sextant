"""The source ids a request model may name for daily prices (the Demo / My data toggle).

``"synthetic"`` is Demo data (shared, anyone). Every other id is a "My data"
provider: a user-scope adapter that runs on the visitor's own key, so a request
naming it without a key answers 403 ``key_required`` (``DataService``). A new
provider goes here, in ``default_adapters()`` and in ``keys.api.Provider`` (plus
a key verifier in ``keys.api.get_verifiers``). The web mirror is
``apps/web/src/lib/myData.ts``. With several keys the user picks the provider
per request; the envelope's ``source`` names the one actually used.
"""

from __future__ import annotations

from typing import Literal

PriceSource = Literal["synthetic", "tiingo", "fmp"]

DEMO_SOURCE = "synthetic"
