"""Macro Dashboard (P5) endpoint on recorded FRED responses."""

import time
from concurrent.futures import ThreadPoolExecutor

import httpx
from fastapi.testclient import TestClient

from data_fixtures import serving
from fred_fixtures import RecordedFred, recorded_adapter
from main import app
from sextant_compute.data.service import default_adapters

client = TestClient(app)

ENDPOINT = "/api/compute/macro/indicators"
INDICATORS = ["gdp_growth", "cpi_inflation", "unemployment_rate", "fed_funds_rate"]


def indicators(fred: RecordedFred | None = None, **body):
    with serving(recorded_adapter(fred), "fred"):
        return client.post(ENDPOINT, json=body)


def test_the_four_headline_indicators_have_a_latest_value_and_a_history():
    response = indicators()
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["tool"] == "macro"
    assert body["source"] == {"id": "fred", "name": "FRED, Federal Reserve Bank of St. Louis", "is_demo": False}
    for key in INDICATORS:
        latest = body["metrics"][f"latest:{key}"]
        assert latest["status"] == "ok", latest
        assert latest["unit"] == "percent"
        history = body["series"][f"history:{key}"]
        assert history["status"] == "ok"
        assert history["x_unit"] == "date" and history["y_unit"] == "percent"
        assert history["points"][0]["x"] == "2015-01-01"


def test_latest_values_come_from_the_recorded_observations():
    body = indicators().json()

    values = {key: body["metrics"][f"latest:{key}"]["value"] for key in INDICATORS}
    assert values == {"gdp_growth": 2.3, "cpi_inflation": 2.6, "unemployment_rate": 4.5, "fed_funds_rate": 3.58}
    assert body["metrics"]["latest:gdp_growth"]["details"]["date"] == "2026-07-01"
    assert body["metrics"]["latest:unemployment_rate"]["details"]["date"] == "2026-10-01"
    assert body["meta"]["data_cutoff"] == "2026-10-01"


def test_each_indicator_carries_its_source_units_frequency_and_last_update():
    body = indicators().json()

    assert body["metrics"]["latest:cpi_inflation"]["details"] == {
        "date": "2026-10-01",
        "series_id": "CPIAUCSL",
        "title": "Consumer Price Index for All Urban Consumers: All Items in U.S. City Average",
        "source": "U.S. Bureau of Labor Statistics",
        "units": "Percent Change from Year Ago",
        "frequency": "Monthly",
        "seasonal_adjustment": "SA",
        "last_updated": "2026-11-13T07:38:02-06:00",
    }
    details = {key: body["metrics"][f"latest:{key}"]["details"] for key in INDICATORS}
    assert details["gdp_growth"]["source"] == "U.S. Bureau of Economic Analysis"
    assert details["gdp_growth"]["frequency"] == "Quarterly"
    assert details["fed_funds_rate"]["source"] == "Board of Governors of the Federal Reserve System"
    assert details["fed_funds_rate"]["series_id"] == "FEDFUNDS"
    assert details["unemployment_rate"]["units"] == "Percent"


def test_unpublished_periods_are_gaps_in_the_history():
    body = indicators().json()

    points = {p["x"]: p["y"] for p in body["series"]["history:unemployment_rate"]["points"]}
    assert points["2025-10-01"] is None
    assert points["2020-04-01"] == 14.8


def test_concurrent_requests_on_a_cold_cache_fetch_each_series_once():
    # Each response takes a moment, so the four requests all miss the cache together.
    fred = RecordedFred(override=lambda path, sid: time.sleep(0.02))
    with serving(recorded_adapter(fred), "fred"), ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: client.post(ENDPOINT, json={}), range(4)))

    assert all(r.status_code == 200 for r in results)
    assert len({r.json()["metrics"]["latest:gdp_growth"]["value"] for r in results}) == 1
    # Four indicators, each one metadata and one observations request: 8 in total.
    assert len(fred.requests) == 8


def test_a_fred_outage_is_a_503_asking_to_retry():
    fred = RecordedFred(override=lambda path, sid: httpx.Response(500))

    response = indicators(fred)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "source_unavailable"


def test_without_fred_api_key_in_the_environment_fred_is_unavailable(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)

    with serving(default_adapters()["fred"], "fred"):
        response = client.post(ENDPOINT, json={})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "source_unavailable"
