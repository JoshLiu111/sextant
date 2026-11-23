"""World Bank adapter on recorded responses (no network): parsing, metadata, the
CC BY 4.0 license check and error classification."""

import json

import httpx
import pytest

from sextant_compute.data.context import RequestContext
from sextant_compute.data.errors import NoSuchData, SourceUnavailable
from world_bank_fixtures import FIXTURES, RecordedWorldBank, recorded_adapter

CTX = RequestContext.anonymous()
GDP = "NY.GDP.MKTP.KD.ZG"
CPI = "FP.CPI.TOTL.ZG"
UNEMPLOYMENT = "SL.UEM.TOTL.ZS"


def fetch(indicator=GDP, countries=("USA", "DEU", "JPN"), start_year=2000, end_year=2026, world_bank=None):
    return recorded_adapter(world_bank).country_indicator(CTX, indicator, countries, start_year, end_year)


def test_gdp_growth_is_parsed_per_country_oldest_year_first():
    found = fetch()

    assert set(found.countries) == {"USA", "DEU", "JPN"}
    germany = found.countries["DEU"]
    assert germany.name == "Germany"
    assert germany.observations[0] == (2000, 2.8765231247659)
    assert germany.observations[-1] == (2025, 0.239578342117881)
    assert len(germany.observations) == 26
    assert dict(germany.observations)[2020] == -4.13191443239947
    assert found.source.id == "world_bank" and found.source.is_demo is False


def test_metadata_carries_the_indicator_title_source_units_frequency_and_last_update():
    meta = fetch(CPI).meta

    assert meta.id == CPI
    assert meta.title == "Inflation, consumer prices (annual % growth)"
    assert meta.source == "International Monetary Fund, International Financial Statistics"
    assert meta.units == "Percent change from a year earlier"
    assert meta.frequency == "Annual"
    assert meta.last_updated == "2026-11-11"


def test_a_year_without_a_value_is_none_and_latest_skips_it():
    usa = fetch(CPI).countries["USA"]

    assert dict(usa.observations)[2025] is None
    assert usa.latest == (2024, 2.94952520485207)


def test_only_the_requested_countries_and_years_come_back():
    found = fetch(UNEMPLOYMENT, countries=("JPN",), start_year=2020, end_year=2024)

    assert list(found.countries) == ["JPN"]
    assert found.countries["JPN"].observations == [(2020, 2.809), (2021, 2.808), (2022, 2.614), (2023, 2.6), (2024, 2.5)]


def test_the_request_names_the_countries_years_and_asks_for_json_in_one_page():
    world_bank = RecordedWorldBank()
    fetch(countries=("usa", "DEU"), start_year=2010, end_year=2025, world_bank=world_bank)

    assert world_bank.paths() == [f"/v2/sources/2/series/{GDP}/metadata", f"/v2/country/DEU;USA/indicator/{GDP}"]
    data = world_bank.requests[1]
    assert data.url.host == "api.worldbank.org"
    assert data.url.params["format"] == "json"
    assert data.url.params["date"] == "2010:2025"
    assert int(data.url.params["per_page"]) >= 1000


def test_more_pages_are_fetched_until_the_last():
    body = json.loads((FIXTURES / "indicators" / f"{GDP}.json").read_text())
    header, rows = body
    pages = [rows[:200], rows[200:400], rows[400:]]

    def paged(request: httpx.Request):
        if "/indicator/" not in request.url.path:
            return None
        page = int(request.url.params.get("page", "1"))
        return httpx.Response(200, json=[{**header, "page": page, "pages": 3}, pages[page - 1]])

    world_bank = RecordedWorldBank(override=paged)
    found = fetch(world_bank=world_bank)

    assert [r.url.params.get("page", "1") for r in world_bank.requests[1:]] == ["1", "2", "3"]
    assert found.countries["USA"].observations[-1] == (2025, 2.16138195623856)
    assert len(found.countries["DEU"].observations) == 26


def test_an_indicator_outside_the_cc_by_allowlist_is_refused_before_any_request():
    world_bank = RecordedWorldBank()

    with pytest.raises(NoSuchData) as err:
        fetch("NY.GDP.PCAP.CD", world_bank=world_bank)

    assert "NY.GDP.PCAP.CD" in err.value.missing
    assert world_bank.requests == []


def test_an_indicator_whose_metadata_is_not_cc_by_is_refused_before_its_data_is_fetched():
    meta = json.loads((FIXTURES / "metadata" / f"{CPI}.json").read_text())
    for item in meta["source"][0]["concept"][0]["variable"][0]["metatype"]:
        if item["id"] == "License_Type":
            item["value"] = "Custom license"

    def restricted(request: httpx.Request):
        return httpx.Response(200, json=meta) if request.url.path.endswith("/metadata") else None

    world_bank = RecordedWorldBank(override=restricted)
    with pytest.raises(NoSuchData) as err:
        fetch(CPI, world_bank=world_bank)

    assert "license" in err.value.missing[CPI].lower()
    assert world_bank.paths() == [f"/v2/sources/2/series/{CPI}/metadata"]


def test_a_world_bank_error_message_for_the_data_is_no_such_data():
    def invalid(request: httpx.Request):
        if "/indicator/" in request.url.path:
            return httpx.Response(200, json=[{"message": [{"id": "120", "key": "Invalid value", "value": "Not valid"}]}])
        return None

    with pytest.raises(NoSuchData) as err:
        fetch(world_bank=RecordedWorldBank(override=invalid))
    assert GDP in err.value.missing


def test_server_errors_are_retried_then_reported_as_source_unavailable():
    world_bank = RecordedWorldBank(override=lambda request: httpx.Response(503, text="busy"))

    with pytest.raises(SourceUnavailable):
        fetch(world_bank=world_bank)
    assert len(world_bank.requests) == 3


def test_a_transient_server_error_is_retried():
    calls = {"n": 0}

    def flaky(request: httpx.Request):
        calls["n"] += 1
        return httpx.Response(502, text="bad gateway") if calls["n"] == 1 else None

    found = fetch(world_bank=RecordedWorldBank(override=flaky))
    assert found.countries["USA"].latest == (2025, 2.16138195623856)


def test_garbage_and_network_errors_are_source_unavailable():
    def garbage(request: httpx.Request):
        return httpx.Response(200, text="<html>maintenance</html>")

    def down(request: httpx.Request):
        raise httpx.ConnectError("refused")

    for override in (garbage, down):
        with pytest.raises(SourceUnavailable):
            fetch(world_bank=RecordedWorldBank(override=override))
