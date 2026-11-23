"""Frankfurter exchange rates through DataService, on recorded responses (no network)."""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from frankfurter_fixtures import RecordedFrankfurter, recorded_adapter
from sextant_compute.data.cache import InMemoryCache
from sextant_compute.data.context import RequestContext
from sextant_compute.data.errors import NoSuchData, SourceUnavailable
from sextant_compute.data.service import DataService

ANON = RequestContext.anonymous()


def service_on(frankfurter: RecordedFrankfurter) -> DataService:
    return DataService({"frankfurter": recorded_adapter(frankfurter)}, shared_cache=InMemoryCache())


def test_daily_rates_are_parsed_in_date_order_across_calendar_years():
    frankfurter = RecordedFrankfurter()

    rates = service_on(frankfurter).fx_rates(
        ANON, "EUR", "USD", start=date(2023, 12, 29), end=date(2024, 1, 3), source="frankfurter"
    )

    # Values as recorded (blended rates, one per calendar day, weekends included).
    assert rates.rates == [
        (date(2023, 12, 29), 1.108),
        (date(2023, 12, 30), 1.1073),
        (date(2023, 12, 31), 1.107),
        (date(2024, 1, 1), 1.1067),
        (date(2024, 1, 2), 1.102),
        (date(2024, 1, 3), 1.0953),
    ]
    assert (rates.base, rates.quote) == ("EUR", "USD")
    assert rates.source.id == "frankfurter"
    assert rates.source.is_demo is False
    assert frankfurter.pairs() == [("EUR", "USD", "2023"), ("EUR", "USD", "2024")]


def test_rates_are_fetched_once_per_year_and_then_served_from_the_shared_cache():
    frankfurter = RecordedFrankfurter()
    service = service_on(frankfurter)

    first = service.fx_rates(ANON, "GBP", "USD", start=date(2024, 3, 1), end=date(2024, 3, 31), source="frankfurter")
    second = service.fx_rates(ANON, "GBP", "USD", start=date(2024, 6, 1), end=date(2024, 6, 30), source="frankfurter")

    assert frankfurter.pairs() == [("GBP", "USD", "2024")]
    assert first.rates[0][0] == date(2024, 3, 1)
    assert second.rates[-1][0] == date(2024, 6, 30)


def test_an_unsupported_currency_is_no_such_data_naming_the_currency():
    with pytest.raises(NoSuchData) as exc:
        service_on(RecordedFrankfurter()).fx_rates(
            ANON, "XYZ", "USD", start=date(2024, 1, 1), end=date(2024, 1, 31), source="frankfurter"
        )

    assert exc.value.missing == {"XYZ": "Frankfurter has no exchange rates for XYZ."}


def test_a_year_without_rates_is_empty_not_an_error():
    rates = service_on(RecordedFrankfurter()).fx_rates(
        ANON, "EUR", "USD", start=date(1990, 1, 1), end=date(1990, 12, 31), source="frankfurter"
    )

    assert rates.rates == []


def test_an_outage_after_retries_is_source_unavailable():
    down = RecordedFrankfurter(override=lambda request: httpx.Response(503, text="down"))

    with pytest.raises(SourceUnavailable):
        service_on(down).fx_rates(ANON, "EUR", "USD", start=date(2024, 1, 1), end=date(2024, 1, 31), source="frankfurter")

    assert len(down.requests) == 3
