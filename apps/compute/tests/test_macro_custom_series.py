"""Macro Dashboard: search FRED and add series (spec stories 77, 78, 94), through
the HTTP API on recorded FRED responses."""

import httpx
from fastapi.testclient import TestClient

from data_fixtures import serving
from fred_fixtures import RecordedFred, recorded_adapter
from main import app

client = TestClient(app)

SEARCH = "/api/compute/macro/search"
SERIES = "/api/compute/macro/series"


def post(path: str, fred: RecordedFred | None = None, **body):
    with serving(recorded_adapter(fred), "fred"):
        return client.post(path, json=body)


# --- search -------------------------------------------------------------------


def test_search_offers_public_domain_series_only():
    response = post(SEARCH, query="unemployment")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["tool"] == "macro"
    assert body["source"]["id"] == "fred"
    assert body["query"] == "unemployment"
    # LRUN64TTUSM156S (OECD, "Copyright, 2016, OECD") is in FRED's answer but not offered.
    assert [r["id"] for r in body["results"]] == ["UNRATE", "UNRATENSA"]


def test_a_search_result_shows_units_frequency_and_last_update():
    (hit,) = post(SEARCH, query="payroll").json()["results"]

    assert hit == {
        "id": "PAYEMS",
        "title": "All Employees, Total Nonfarm",
        "units": "Thousands of Persons",
        "frequency": "Monthly",
        "seasonal_adjustment": "SA",
        "last_updated": "2026-11-06T07:48:03-06:00",
        "observation_end": "2026-10-01",
    }


def test_a_search_with_only_copyrighted_matches_returns_no_results():
    assert post(SEARCH, query="high yield").json()["results"] == []


def test_a_blank_search_is_a_field_error():
    response = post(SEARCH, query="   ")

    assert response.status_code == 422
    assert "query" in response.json()["error"]["fields"]


def test_a_fred_outage_during_search_is_503():
    fred = RecordedFred(override=lambda path, sid: httpx.Response(500, json={"error_code": 500}))

    response = post(SEARCH, fred, query="unemployment")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "source_unavailable"


# --- added series ---------------------------------------------------------------


def test_added_series_have_a_latest_value_history_and_metadata():
    response = post(SERIES, series=["PAYEMS", "UNRATENSA"])
    assert response.status_code == 200, response.text
    body = response.json()

    payroll = body["metrics"]["latest:PAYEMS"]
    assert payroll["status"] == "ok"
    assert payroll["value"] == 157995.0
    assert payroll["unit"] is None  # thousands of persons: shown with details.units
    assert payroll["details"] == {
        "date": "2026-10-01",
        "series_id": "PAYEMS",
        "title": "All Employees, Total Nonfarm",
        "source": "U.S. Bureau of Labor Statistics",
        "units": "Thousands of Persons",
        "frequency": "Monthly",
        "seasonal_adjustment": "SA",
        "last_updated": "2026-11-06T07:48:03-06:00",
    }
    unemployment = body["metrics"]["latest:UNRATENSA"]
    assert unemployment["unit"] == "percent"
    assert unemployment["details"]["seasonal_adjustment"] == "NSA"

    history = body["series"]["history:PAYEMS"]
    assert history["status"] == "ok" and history["x_unit"] == "date"
    assert history["points"][0] == {"x": "2015-01-01", "y": 140765.0}
    assert list(body["metrics"]) == ["latest:PAYEMS", "latest:UNRATENSA"]
    assert body["meta"]["data_cutoff"] == "2026-10-01"


def test_series_ids_are_upper_cased_and_deduplicated():
    body = post(SERIES, series=["payems", "PAYEMS"]).json()

    assert list(body["metrics"]) == ["latest:PAYEMS"]
    assert body["meta"]["parameters"]["series"] == ["PAYEMS"]


def test_the_start_date_cuts_the_history():
    fred = RecordedFred()
    post(SERIES, fred, series=["PAYEMS"], start="2020-01-01")

    obs = [r for r in fred.requests if r.url.path.endswith("/observations")]
    assert obs[0].url.params["observation_start"] == "2020-01-01"


def test_a_series_that_is_not_public_domain_is_missing_data_on_its_own():
    # A shared link could name any id: T10Y2Y is copyrighted on FRED, so it's refused.
    body = post(SERIES, series=["T10Y2Y", "PAYEMS"]).json()

    refused = body["metrics"]["latest:T10Y2Y"]
    assert refused["status"] == "missing_data"
    assert "public domain" in refused["reason"]
    assert body["series"]["history:T10Y2Y"]["status"] == "missing_data"
    assert body["metrics"]["latest:PAYEMS"]["status"] == "ok"


def test_a_copyrighted_or_unknown_series_is_missing_data():
    body = post(SERIES, series=["LRUN64TTUSM156S", "NOSUCHSERIES"]).json()

    assert "copyright" in body["metrics"]["latest:LRUN64TTUSM156S"]["reason"].lower()
    assert body["metrics"]["latest:NOSUCHSERIES"]["status"] == "missing_data"


def test_the_series_list_is_validated():
    for bad in ([], ["PAYEMS; DROP"], [f"S{i}" for i in range(9)]):
        response = post(SERIES, series=bad)
        assert response.status_code == 422, bad
        assert "series" in response.json()["error"]["fields"]


def test_a_fred_outage_fails_the_added_series_with_503():
    fred = RecordedFred(override=lambda path, sid: httpx.Response(503, json={"error_code": 503}))

    assert post(SERIES, fred, series=["PAYEMS"]).status_code == 503
