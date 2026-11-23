"""FRED search and visitor-chosen series on recorded responses (no network):
only public-domain series are offered or served (spec stories 78, 94)."""

from datetime import date

import pytest

from fred_fixtures import RecordedFred, recorded_adapter
from sextant_compute.data.context import RequestContext
from sextant_compute.data.errors import NoSuchData

CTX = RequestContext.anonymous()
START = date(2015, 1, 1)


def test_search_excludes_a_series_whose_notes_carry_a_copyright():
    hits = recorded_adapter().search_series(CTX, "unemployment", limit=20)

    # The recording also holds LRUN64TTUSM156S, whose notes say "Copyright, 2016, OECD".
    assert [h.id for h in hits] == ["UNRATE", "UNRATENSA"]


def test_a_search_matching_only_copyrighted_series_offers_nothing():
    # BAMLH0A0HYM2's notes: "Copyright, 2023, ICE Data Indices."
    assert recorded_adapter().search_series(CTX, "High yield", limit=20) == []


def test_search_asks_fred_for_public_domain_series_only():
    fred = RecordedFred()
    recorded_adapter(fred).search_series(CTX, "  unemployment ", limit=20)

    (request,) = fred.requests
    assert request.url.path == "/fred/series/search"
    params = request.url.params
    assert params["search_text"] == "unemployment"
    assert params["tag_names"] == "public domain: citation requested"
    assert params["file_type"] == "json"


def test_a_search_hit_carries_what_the_picker_shows():
    hits = recorded_adapter().search_series(CTX, "payroll", limit=20)

    (hit,) = hits
    assert hit.id == "PAYEMS"
    assert hit.title == "All Employees, Total Nonfarm"
    assert hit.units == "Thousands of Persons"
    assert hit.frequency == "Monthly"
    assert hit.seasonal_adjustment == "SA"
    assert hit.last_updated == "2026-11-06T07:48:03-06:00"
    assert hit.observation_end == "2026-10-01"


def test_search_returns_at_most_the_limit():
    fred = RecordedFred()
    hits = recorded_adapter(fred).search_series(CTX, "unemployment", limit=1)

    assert [h.id for h in hits] == ["UNRATE"]


def test_a_public_domain_series_off_the_allowlist_is_served_with_its_agency_from_the_tags():
    fred = RecordedFred()
    series = recorded_adapter(fred).economic_series(CTX, "PAYEMS", START)

    assert series.meta.source == "U.S. Bureau of Labor Statistics"
    assert series.meta.units == "Thousands of Persons"
    assert series.meta.frequency == "Monthly"
    assert series.latest == (date(2026, 10, 1), 157995.0)
    assert fred.paths() == ["/fred/series", "/fred/series/tags", "/fred/series/observations"]


def test_a_series_without_the_public_domain_tag_is_rejected_even_with_clean_notes():
    fred = RecordedFred()

    # T10Y2Y is tagged "copyrighted: citation required"; its notes never say "Copyright".
    with pytest.raises(NoSuchData) as exc:
        recorded_adapter(fred).economic_series(CTX, "T10Y2Y", START)

    assert "public domain" in exc.value.message
    assert "T10Y2Y" in exc.value.missing
    assert "/fred/series/observations" not in fred.paths()


def test_a_copyrighted_series_found_elsewhere_is_rejected_before_its_tags_or_data():
    fred = RecordedFred()

    with pytest.raises(NoSuchData) as exc:
        recorded_adapter(fred).economic_series(CTX, "LRUN64TTUSM156S", START)

    assert "copyright" in exc.value.message.lower()
    assert fred.paths() == ["/fred/series"]


def test_allowlisted_series_skip_the_tags_lookup():
    fred = RecordedFred()
    recorded_adapter(fred).economic_series(CTX, "UNRATE", START)

    assert fred.paths() == ["/fred/series", "/fred/series/observations"]
