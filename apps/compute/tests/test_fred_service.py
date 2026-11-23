"""FRED through DataService: public data lands in the shared cache with the dataset TTL."""

import uuid
from datetime import date

import httpx
import pytest

from fred_fixtures import RecordedFred, recorded_adapter
from sextant_compute.data.cache import InMemoryCache
from sextant_compute.data.context import RequestContext
from sextant_compute.data.errors import SourceUnavailable
from sextant_compute.data.service import DataService

START = date(2015, 1, 1)
ANON = RequestContext.anonymous()


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


def service_on(fred: RecordedFred, clock: Clock | None = None) -> DataService:
    return DataService({"fred": recorded_adapter(fred)}, shared_cache=InMemoryCache(clock=clock or Clock()))


def test_a_repeated_series_request_is_served_from_the_shared_cache_with_identical_data():
    fred = RecordedFred()
    service = service_on(fred)

    first = service.economic_series(ANON, "UNRATE", start=START, source="fred")
    second = service.economic_series(ANON, "UNRATE", start=START, source="fred")

    assert len(fred.requests) == 2  # metadata + observations, once
    assert second == first


def test_cached_series_are_shared_between_visitors():
    fred = RecordedFred()
    service = service_on(fred)

    service.economic_series(ANON, "UNRATE", start=START, source="fred")
    service.economic_series(RequestContext(user_id=uuid.uuid4()), "UNRATE", start=START, source="fred")

    assert len(fred.requests) == 2


def test_different_units_are_different_entries():
    fred = RecordedFred()
    service = service_on(fred)

    service.economic_series(ANON, "CPIAUCSL", start=START, units="pc1", source="fred")
    service.economic_series(ANON, "CPIAUCSL", start=START, units="lin", source="fred")

    assert len(fred.requests) == 4


def test_the_entry_expires_after_six_hours():
    fred, clock = RecordedFred(), Clock()
    service = service_on(fred, clock)

    service.economic_series(ANON, "UNRATE", start=START, source="fred")
    clock.now += 6 * 3600 - 1
    service.economic_series(ANON, "UNRATE", start=START, source="fred")
    assert len(fred.requests) == 2
    clock.now += 2
    service.economic_series(ANON, "UNRATE", start=START, source="fred")
    assert len(fred.requests) == 4


def test_an_outage_is_not_cached():
    down = {"on": True}
    fred = RecordedFred(override=lambda path, sid: httpx.Response(503) if down["on"] else None)
    service = service_on(fred)

    with pytest.raises(SourceUnavailable):
        service.economic_series(ANON, "UNRATE", start=START, source="fred")
    down["on"] = False
    series = service.economic_series(ANON, "UNRATE", start=START, source="fred")

    assert series.meta.id == "UNRATE"
