"""DataService behaviour: whole-request caching, TTLs, per-user isolation, error passthrough."""

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pandas as pd
import pytest

from data_fixtures import DownAdapter, FixtureAdapter, price_frame
from sextant_compute.data.cache import InMemoryCache
from sextant_compute.data.context import RequestContext
from sextant_compute.data.cross_section import CrossSection
from sextant_compute.data.errors import KeyRequired, NoSuchData, SourceUnavailable
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

    assert adapter.calls == 2
    assert len(shared) == 0


def test_user_keyed_sources_need_the_visitors_own_key_even_on_a_cached_entry():
    adapter = FixtureAdapter(FRAMES, source=USER_KEYED, scope="user")
    service, _ = service_with(adapter, user_cache=InMemoryCache(clock=Clock()))
    user_id = uuid.uuid4()

    service.daily_prices(RequestContext(user_id=user_id, keys={"tiingo": "k"}), ["AAA"], START, END, source="src")
    for ctx in (ANON, RequestContext(user_id=user_id)):  # anonymous; the same user after deleting the key
        with pytest.raises(KeyRequired):
            service.daily_prices(ctx, ["AAA"], START, END, source="src")
    assert adapter.calls == 1


def test_partial_prices_report_unknown_tickers_and_cache_the_rest_per_ticker():
    adapter = FixtureAdapter(FRAMES)
    service, _ = service_with(adapter)

    prices = service.daily_prices(ANON, ["AAA", "ZZZ", "BBB"], START, END, source="src", partial=True)

    assert list(prices.frames) == ["AAA", "BBB"]
    assert prices.missing == {"ZZZ": "Unknown ticker ZZZ."}
    service.daily_prices(ANON, ["BBB"], START, END, source="src")
    assert adapter.calls == 3  # one per ticker; the plain BBB request reused the partial one's entry


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
    assert adapter.calls == 2
    assert len(shared) == 0


def test_sources_without_a_ttl_for_the_dataset_are_not_cached():
    adapter = FixtureAdapter(FRAMES)
    adapter.ttl = {}
    service = DataService({"src": adapter}, shared_cache=InMemoryCache(clock=Clock()))

    service.daily_prices(ANON, ["AAA"], START, END, source="src")
    service.daily_prices(ANON, ["AAA"], START, END, source="src")

    assert adapter.calls == 2


class GatedCrossSections:
    """A cross-sections adapter whose calls block until ``release`` is set."""

    source = DataSource(id="xs", name="Cross sections", is_demo=False)
    scope = "shared"
    ttl = {"cross_sections": 3600}
    version = "1"

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.entered = threading.Event()
        self.release = threading.Event()

    def cross_sections(self, ctx, item_ids, year):
        self.calls.append(tuple(item_ids))
        self.entered.set()
        self.release.wait(5)
        return {i: CrossSection(item_id=i, label=i, year=year, values={}) for i in item_ids}


def test_a_cross_section_still_being_fetched_is_waited_for_not_fetched_again():
    # The first fetch is still running (nothing cached yet) when a second
    # request for an overlapping set of items arrives.
    adapter = GatedCrossSections()
    service = DataService({"xs": adapter}, shared_cache=InMemoryCache(clock=Clock()))

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(service.cross_sections, ANON, ["revenue", "net_income"], 2025, source="xs")
        assert adapter.entered.wait(5)
        second = pool.submit(service.cross_sections, ANON, ["revenue", "assets"], 2025, source="xs")
        time.sleep(0.05)  # let the second request reach the in-flight fetch
        adapter.release.set()
        a, b = first.result(5), second.result(5)

    assert adapter.calls == [("revenue", "net_income"), ("assets",)]
    assert list(a) == ["revenue", "net_income"] and list(b) == ["revenue", "assets"]
    # Followers decode their own copy, so callers never share mutable values.
    assert b["revenue"] == a["revenue"] and b["revenue"] is not a["revenue"]
