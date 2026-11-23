"""DataService behaviour: whole-request caching, TTLs, per-user isolation, error passthrough."""

import uuid
from datetime import date

import pandas as pd
import pytest

from data_fixtures import DownAdapter, FixtureAdapter, price_frame
from sextant_compute.data.cache import InMemoryCache
from sextant_compute.data.context import RequestContext
from sextant_compute.data.errors import NoSuchData, SourceUnavailable
from sextant_compute.data.service import DataService
from sextant_compute.envelope import DataSource

START, END = date(2024, 1, 1), date(2024, 12, 31)
ANON = RequestContext.anonymous()
FRAMES = {
    "AAA": price_frame("2024-01-01", [100.0, 101.5, 99.25, 102.125], dividends={2: 0.5}),
    "BBB": price_frame("2024-01-01", [50.0, 49.0, 51.0, 52.0]),
}


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


def service_with(adapter, ttl=3600, clock=None, **kwargs):
    adapter.ttl = {"daily_prices": ttl}
    cache = InMemoryCache(clock=clock or Clock())
    return DataService({"src": adapter}, shared_cache=cache, **kwargs), cache


def test_repeated_identical_request_is_served_from_the_cache_with_identical_data():
    adapter = FixtureAdapter(FRAMES)
    service, _ = service_with(adapter)

    first = service.daily_prices(ANON, ["AAA", "BBB"], START, END, source="src")
    second = service.daily_prices(ANON, ["AAA", "BBB"], START, END, source="src")

    assert adapter.calls == 1
    assert second.source == first.source
    for ticker in ("AAA", "BBB"):
        pd.testing.assert_frame_equal(second.frames[ticker], first.frames[ticker], check_freq=False)


def test_equivalent_requests_share_a_cache_entry():
    adapter = FixtureAdapter(FRAMES)
    service, _ = service_with(adapter)

    service.daily_prices(ANON, ["AAA", "BBB"], START, END, source="src")
    service.daily_prices(ANON, ["BBB", "AAA"], START, END, source="src")

    assert adapter.calls == 1


def test_different_parameters_miss_the_cache():
    adapter = FixtureAdapter(FRAMES)
    service, _ = service_with(adapter)

    service.daily_prices(ANON, ["AAA"], START, END, source="src")
    service.daily_prices(ANON, ["AAA"], START, date(2024, 6, 30), source="src")
    service.daily_prices(ANON, ["BBB"], START, END, source="src")

    assert adapter.calls == 3


def test_entries_expire_after_the_dataset_ttl():
    adapter, clock = FixtureAdapter(FRAMES), Clock()
    service, _ = service_with(adapter, ttl=60, clock=clock)

    service.daily_prices(ANON, ["AAA"], START, END, source="src")
    clock.now += 59
    service.daily_prices(ANON, ["AAA"], START, END, source="src")
    assert adapter.calls == 1

    clock.now += 2
    service.daily_prices(ANON, ["AAA"], START, END, source="src")
    assert adapter.calls == 2


def test_errors_are_not_cached():
    down = DownAdapter()
    service, cache = service_with(down)

    for _ in range(2):
        with pytest.raises(SourceUnavailable):
            service.daily_prices(ANON, ["AAA"], START, END, source="src")
    assert len(cache) == 0

    adapter = FixtureAdapter(FRAMES)
    service, cache = service_with(adapter)
    for _ in range(2):
        with pytest.raises(NoSuchData):
            service.daily_prices(ANON, ["ZZZ"], START, END, source="src")
    assert adapter.calls == 2


USER_KEYED = DataSource(id="tiingo", name="Tiingo", is_demo=False)


def test_user_keyed_data_never_enters_the_shared_cache():
    adapter = FixtureAdapter(FRAMES, source=USER_KEYED, scope="user")
    service, shared = service_with(adapter)
    alice = RequestContext(user_id=uuid.uuid4(), keys={"tiingo": "alice-key"})
    bob = RequestContext(user_id=uuid.uuid4(), keys={"tiingo": "bob-key"})

    service.daily_prices(alice, ["AAA"], START, END, source="src")
    service.daily_prices(bob, ["AAA"], START, END, source="src")
    service.daily_prices(ANON, ["AAA"], START, END, source="src")

    assert adapter.calls == 3
    assert len(shared) == 0


def test_user_keyed_data_is_cached_per_user_when_a_user_cache_is_configured():
    adapter = FixtureAdapter(FRAMES, source=USER_KEYED, scope="user")
    user_cache = InMemoryCache(clock=Clock())
    service, shared = service_with(adapter, user_cache=user_cache)
    alice = RequestContext(user_id=uuid.uuid4(), keys={"tiingo": "alice-key"})
    bob = RequestContext(user_id=uuid.uuid4(), keys={"tiingo": "bob-key"})

    service.daily_prices(alice, ["AAA"], START, END, source="src")
    service.daily_prices(alice, ["AAA"], START, END, source="src")
    assert adapter.calls == 1

    service.daily_prices(bob, ["AAA"], START, END, source="src")
    service.daily_prices(ANON, ["AAA"], START, END, source="src")
    assert adapter.calls == 3
    assert len(shared) == 0


def test_sources_without_a_ttl_for_the_dataset_are_not_cached():
    adapter = FixtureAdapter(FRAMES)
    adapter.ttl = {}
    service = DataService({"src": adapter}, shared_cache=InMemoryCache(clock=Clock()))

    service.daily_prices(ANON, ["AAA"], START, END, source="src")
    service.daily_prices(ANON, ["AAA"], START, END, source="src")

    assert adapter.calls == 2
