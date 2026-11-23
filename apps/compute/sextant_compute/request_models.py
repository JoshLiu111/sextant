"""Request-model building blocks shared by the tool endpoints.

- ``Ticker``: trimmed and upper-cased; blank is "Enter a ticker.".
  ``TickerOrBlank`` is the same without the check (blank means "any").
- ``PriceRangeRequest``: ``start``, ``end`` (after ``start``) and the price
  ``source`` (Demo data or the user's own provider) of a market-data request.
- ``EndOnOrAfterStart``: the check alone, for ranges whose ``end`` is optional
  and may equal ``start`` (macro tools, each with its own ``start`` bounds).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from sextant_compute.data.sources import DEMO_SOURCE, PriceSource
from sextant_compute.errors import INPUT_ERROR, check


def normalize_ticker(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


Ticker = Annotated[str, BeforeValidator(normalize_ticker), check(lambda v: v != "", "Enter a ticker.")]
TickerOrBlank = Annotated[str, BeforeValidator(normalize_ticker)]


class PriceRangeRequest(BaseModel):
    """The date range and price source of a market-data request."""

    start: date
    end: date
    source: PriceSource = DEMO_SOURCE
    """Demo data (``"synthetic"``) or the user's own provider (My data, e.g. ``"tiingo"``)."""

    @field_validator("end")
    @classmethod
    def _end_after_start(cls, end: date, info: ValidationInfo) -> date:
        start = info.data.get("start")
        if start is not None and end <= start:
            raise PydanticCustomError(INPUT_ERROR, "End date must be after the start date.")
        return end


class EndOnOrAfterStart(BaseModel):
    """Rejects an ``end`` before ``start``; ``end`` None (today) always passes.
    Declare ``start`` before ``end`` in the subclass."""

    @field_validator("end", check_fields=False)
    @classmethod
    def _end_on_or_after_start(cls, end: date | None, info: ValidationInfo) -> date | None:
        start = info.data.get("start")
        if end is not None and start is not None and end < start:
            raise PydanticCustomError(INPUT_ERROR, "End date must be on or after the start date.")
        return end
