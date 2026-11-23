"""FRED adapter on recorded responses (no network): parsing, metadata, the
public-domain filter, error classification and the 2 requests/second limit."""

from datetime import date

import httpx
import pytest

from fred_fixtures import TEST_KEY, FakeClock, RecordedFred, recorded_adapter
from sextant_compute.data.context import RequestContext
from sextant_compute.data.errors import NoSuchData, SourceUnavailable

CTX = RequestContext.anonymous()
START = date(2015, 1, 1)


def test_unemployment_rate_metadata_and_observations_are_parsed():
    series = recorded_adapter().economic_series(CTX, "UNRATE", START)

    meta = series.meta
    assert meta.id == "UNRATE"
    assert meta.title == "Unemployment Rate"
    assert meta.source == "U.S. Bureau of Labor Statistics"
    assert meta.units == "Percent"
    assert meta.frequency == "Monthly"
    assert meta.seasonal_adjustment == "SA"
    assert meta.last_updated == "2026-11-06T07:48:02-06:00"
    assert series.source.id == "fred" and series.source.is_demo is False

    assert series.observations[0] == (date(2015, 1, 1), 5.7)
    assert series.observations[-1] == (date(2026, 10, 1), 4.5)
    assert len(series.observations) == 142


def test_missing_observations_come_back_as_none_and_latest_skips_them():
    series = recorded_adapter().economic_series(CTX, "UNRATE", START)

    by_date = dict(series.observations)
    # October 2025 was never published (government shutdown); FRED sends "."
    assert by_date[date(2025, 10, 1)] is None
    assert by_date[date(2025, 11, 1)] == 4.6
    assert series.latest == (date(2026, 10, 1), 4.5)


def test_requests_send_the_key_json_format_start_and_units():
    fred = RecordedFred()
    recorded_adapter(fred).economic_series(CTX, "CPIAUCSL", START, units="pc1")

    assert fred.paths() == ["/fred/series", "/fred/series/observations"]
    meta_req, obs_req = fred.requests
    assert meta_req.url.host == "api.stlouisfed.org"
    for req in fred.requests:
        assert req.url.params["api_key"] == TEST_KEY
        assert req.url.params["file_type"] == "json"
        assert req.url.params["series_id"] == "CPIAUCSL"
    assert obs_req.url.params["observation_start"] == "2015-01-01"
    assert obs_req.url.params["units"] == "pc1"


def test_a_transformed_series_reports_the_transformation_as_its_units():
    series = recorded_adapter().economic_series(CTX, "CPIAUCSL", START, units="pc1")

    # The metadata says "Index 1982-1984=100"; the observations are year-over-year changes.
    assert series.meta.units == "Percent Change from Year Ago"
    assert series.meta.source == "U.S. Bureau of Labor Statistics"
    assert series.latest == (date(2026, 10, 1), 2.6)


def test_quarterly_gdp_growth_parses_negative_values():
    series = recorded_adapter().economic_series(CTX, "A191RL1Q225SBEA", START)

    assert series.meta.frequency == "Quarterly"
    assert series.meta.units == "Percent Change from Preceding Period"
    assert series.meta.source == "U.S. Bureau of Economic Analysis"
    assert dict(series.observations)[date(2020, 4, 1)] == -28.0
    assert series.latest == (date(2026, 7, 1), 2.3)


def test_a_series_whose_notes_carry_a_copyright_is_rejected_before_its_data_is_fetched():
    fred = RecordedFred()
    # Even if someone wrongly allowlisted it, the notes filter still rejects it.
    adapter = recorded_adapter(fred, allowlist={"BAMLH0A0HYM2": "ICE Data Indices"})

    with pytest.raises(NoSuchData) as exc:
        adapter.economic_series(CTX, "BAMLH0A0HYM2", START)

    assert "copyright" in exc.value.message.lower()
    assert "BAMLH0A0HYM2" in exc.value.missing
    assert fred.paths() == ["/fred/series"]


def test_a_series_outside_the_public_domain_allowlist_is_rejected_even_with_clean_notes():
    fred = RecordedFred()

    # T10Y2Y is "Copyrighted: Citation Required" on FRED, but its notes never say "Copyright".
    with pytest.raises(NoSuchData) as exc:
        recorded_adapter(fred).economic_series(CTX, "T10Y2Y", START)

    assert "public-domain" in exc.value.message
    assert fred.requests == []


def test_an_unknown_series_is_no_such_data():
    adapter = recorded_adapter(allowlist={"NOPE": "Nobody"})

    with pytest.raises(NoSuchData) as exc:
        adapter.economic_series(CTX, "NOPE", START)

    assert "NOPE" in exc.value.missing


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, json={"error_code": 500, "error_message": "Internal Server Error"}),
        httpx.Response(200, text="<html>maintenance</html>"),
        httpx.Response(
            400,
            json={"error_code": 400, "error_message": "Bad Request.  The value for variable api_key is not registered."},
        ),
    ],
    ids=["server-error", "garbage", "bad-key"],
)
def test_provider_failures_are_source_unavailable(response):
    fred = RecordedFred(override=lambda path, sid: response)

    with pytest.raises(SourceUnavailable):
        recorded_adapter(fred).economic_series(CTX, "UNRATE", START)


def test_network_errors_are_source_unavailable_and_never_echo_the_key():
    def refuse(path, sid):
        raise httpx.ConnectError(f"connection refused for ...?api_key={TEST_KEY}")

    with pytest.raises(SourceUnavailable) as exc:
        recorded_adapter(RecordedFred(override=refuse)).economic_series(CTX, "UNRATE", START)

    assert TEST_KEY not in exc.value.message


def test_without_an_api_key_fred_is_unavailable():
    with pytest.raises(SourceUnavailable):
        recorded_adapter(api_key=None).economic_series(CTX, "UNRATE", START)


def test_a_rate_limited_request_backs_off_and_retries():
    attempts = {"n": 0}

    def limited_once(path, sid):
        if path == "/fred/series" and attempts["n"] == 0:
            attempts["n"] += 1
            return httpx.Response(429, json={"error_code": 429, "error_message": "Too Many Requests."})
        return None

    clock = FakeClock()
    series = recorded_adapter(RecordedFred(override=limited_once), clock).economic_series(CTX, "UNRATE", START)

    assert series.meta.id == "UNRATE"
    assert max(clock.sleeps) >= 1.0


def test_requests_are_spaced_to_at_most_two_per_second():
    fred, clock = RecordedFred(), FakeClock()
    stamps: list[float] = []
    original = fred._handle

    def stamped(request):
        stamps.append(clock.now)
        return original(request)

    fred.transport = httpx.MockTransport(stamped)
    adapter = recorded_adapter(fred, clock)

    adapter.economic_series(CTX, "UNRATE", START)
    adapter.economic_series(CTX, "FEDFUNDS", START)

    assert len(stamps) == 4
    assert all(b - a >= 0.5 for a, b in zip(stamps, stamps[1:]))
