"""Macro Dashboard cross-country comparison on recorded World Bank responses."""

import json

import httpx
from fastapi.testclient import TestClient

from data_fixtures import serving
from main import app
from world_bank_fixtures import FIXTURES, RecordedWorldBank, recorded_adapter

client = TestClient(app)

ENDPOINT = "/api/compute/macro/countries"
INDICATORS = ("gdp_growth", "inflation", "unemployment_rate")


def compare(world_bank: RecordedWorldBank | None = None, **body):
    with serving(recorded_adapter(world_bank), "world_bank"):
        return client.post(ENDPOINT, json=body)


def test_each_selected_country_gets_its_latest_value_of_every_indicator():
    response = compare(countries=["USA", "DEU", "JPN"])
    assert response.status_code == 200, response.text
    body = response.json()

    metrics = body["metrics"]
    assert set(metrics) == {f"latest:{i}:{c}" for i in INDICATORS for c in ("USA", "DEU", "JPN")}
    germany_gdp = metrics["latest:gdp_growth:DEU"]
    assert germany_gdp["status"] == "ok"
    assert germany_gdp["unit"] == "percent"
    assert round(germany_gdp["value"], 4) == 0.2396
    assert round(metrics["latest:unemployment_rate:JPN"]["value"], 3) == 2.451
    assert body["source"] == {"id": "world_bank", "name": "World Bank", "is_demo": False}
    assert body["meta"]["data_cutoff"] == "2025-12-31"


def test_the_latest_value_falls_back_to_the_last_year_published():
    usa = compare(countries=["USA"]).json()["metrics"]["latest:inflation:USA"]

    # The recording has no 2025 US CPI inflation yet.
    assert usa["details"]["year"] == 2024
    assert round(usa["value"], 2) == 2.95


def test_each_latest_value_carries_the_series_source_units_frequency_and_last_update():
    details = compare(countries=["JPN"]).json()["metrics"]["latest:inflation:JPN"]["details"]

    assert details == {
        "year": 2025,
        "country": "JPN",
        "country_name": "Japan",
        "indicator_id": "FP.CPI.TOTL.ZG",
        "title": "Inflation, consumer prices (annual % growth)",
        "source": "International Monetary Fund, International Financial Statistics",
        "units": "Percent change from a year earlier",
        "frequency": "Annual",
        "last_updated": "2026-11-11",
    }


def test_the_history_runs_from_the_start_year_by_calendar_year():
    series = compare(countries=["USA"], start_year=2018).json()["series"]["history:gdp_growth:USA"]

    assert series["x_unit"] == "year" and series["y_unit"] == "percent"
    assert [p["x"] for p in series["points"]] == list(range(2018, 2026))
    assert round({p["x"]: p["y"] for p in series["points"]}[2020], 2) == -2.08


def test_the_default_selection_compares_four_large_economies_since_2000():
    body = compare().json()

    assert body["meta"]["parameters"]["countries"] == ["USA", "DEU", "JPN", "GBR"]
    assert body["series"]["history:unemployment_rate:GBR"]["points"][0]["x"] == 2000


def test_the_euro_area_aggregate_can_be_compared_like_a_country():
    metric = compare(countries=["EMU", "USA"]).json()["metrics"]["latest:unemployment_rate:EMU"]

    assert metric["details"]["country_name"] == "Euro area"
    assert round(metric["value"], 2) == 6.28


def test_changing_the_selection_is_served_from_the_cache():
    world_bank = RecordedWorldBank()
    with serving(recorded_adapter(world_bank), "world_bank"):
        first = client.post(ENDPOINT, json={"countries": ["USA"]})
        calls = len(world_bank.requests)
        second = client.post(ENDPOINT, json={"countries": ["CHN", "IND"]})

    assert first.status_code == second.status_code == 200
    assert calls == 6  # metadata + data for each of the three indicators
    assert len(world_bank.requests) == calls
    assert round(second.json()["metrics"]["latest:gdp_growth:IND"]["value"], 2) == 7.57


def test_a_country_without_data_only_blanks_its_own_values():
    def without_brazil(request: httpx.Request):
        if "/indicator/SL.UEM.TOTL.ZS" not in request.url.path:
            return None
        header, rows = json.loads((FIXTURES / "indicators" / "SL.UEM.TOTL.ZS.json").read_text())
        return httpx.Response(200, json=[header, [r for r in rows if r["countryiso3code"] != "BRA"]])

    body = compare(RecordedWorldBank(override=without_brazil), countries=["BRA", "USA"]).json()

    assert body["metrics"]["latest:unemployment_rate:BRA"]["status"] == "missing_data"
    assert "BRA" in body["metrics"]["latest:unemployment_rate:BRA"]["reason"]
    assert body["series"]["history:unemployment_rate:BRA"]["status"] == "missing_data"
    assert body["metrics"]["latest:unemployment_rate:USA"]["status"] == "ok"
    assert body["metrics"]["latest:gdp_growth:BRA"]["status"] == "ok"


def test_an_indicator_that_is_no_longer_cc_by_only_blanks_that_indicator():
    meta = json.loads((FIXTURES / "metadata" / "FP.CPI.TOTL.ZG.json").read_text())
    for item in meta["source"][0]["concept"][0]["variable"][0]["metatype"]:
        if item["id"] == "License_Type":
            item["value"] = "Custom license"

    def restricted(request: httpx.Request):
        return httpx.Response(200, json=meta) if request.url.path.endswith("FP.CPI.TOTL.ZG/metadata") else None

    body = compare(RecordedWorldBank(override=restricted), countries=["USA"]).json()

    assert body["metrics"]["latest:inflation:USA"]["status"] == "missing_data"
    assert body["series"]["history:inflation:USA"]["status"] == "missing_data"
    assert body["metrics"]["latest:gdp_growth:USA"]["status"] == "ok"


def test_a_world_bank_outage_asks_to_retry():
    response = compare(RecordedWorldBank(override=lambda request: httpx.Response(503)), countries=["USA"])

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "source_unavailable"


def test_country_selection_validation():
    for body, field in [
        ({"countries": []}, "countries"),
        ({"countries": ["USA", "DEU", "JPN", "GBR", "FRA", "ITA", "CAN"]}, "countries"),
        ({"countries": ["USA", "XXX"]}, "countries.1"),
        ({"start_year": 1959}, "start_year"),
    ]:
        response = compare(**body)
        assert response.status_code == 422, body
        assert field in response.json()["error"]["fields"], response.json()


def test_country_codes_are_normalized_and_duplicates_dropped():
    body = compare(countries=["usa", "USA", " deu "]).json()

    assert body["meta"]["parameters"]["countries"] == ["USA", "DEU"]
