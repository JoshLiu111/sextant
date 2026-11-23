"""Company Health Check (P1) API: standardized statements on recorded EDGAR fixtures."""

from __future__ import annotations

from fastapi.testclient import TestClient

from main import app
from tests.data_fixtures import serving
from tests.edgar_fixtures import edgar_adapter, edgar_transport

client = TestClient(app)
PATH = "/api/compute/company/statements"


def post(body: dict | None = None):
    return client.post(PATH, json=body if body is not None else {})


def test_the_default_ticker_shows_five_fiscal_years_of_all_three_statements() -> None:
    with serving(edgar_adapter(), "sec_edgar"):
        res = post()

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["tool"] == "company"
    assert body["source"] == {"id": "sec_edgar", "name": "SEC EDGAR", "is_demo": False}
    assert body["company"] == {"ticker": "AAPL", "cik": 320193, "name": "Apple Inc."}
    assert [p["label"] for p in body["periods"]] == ["FY2022", "FY2023", "FY2024", "FY2025", "FY2026"]
    assert {i["statement"] for i in body["items"]} == {"income", "balance", "cash_flow"}
    revenue = body["metrics"]["revenue:2026-09-26"]
    assert revenue["status"] == "ok"
    assert revenue["value"] == 478_834_000_000
    assert revenue["unit"] == "currency"
    assert body["metrics"]["eps_diluted:2026-09-26"]["unit"] == "per_share"
    assert body["metrics"]["shares_outstanding:2026-09-26"]["unit"] == "shares"
    assert body["metrics"]["total_assets:2026-09-26"]["value"] == 404_548_000_000
    assert body["metrics"]["operating_cash_flow:2026-09-26"]["value"] == 145_097_000_000
    assert body["meta"]["data_cutoff"] == "2026-11-03"


def test_every_value_links_to_its_source_filing() -> None:
    with serving(edgar_adapter(), "sec_edgar"):
        body = post({"ticker": "AAPL"}).json()

    details = body["metrics"]["revenue:2026-09-26"]["details"]
    assert details["form"] == "10-K"
    assert details["filed"] == "2026-11-03"
    assert details["accession"] == "0000320193-26-000026"
    assert details["url"].startswith("https://www.sec.gov/Archives/edgar/data/320193/000032019326000026/")
    assert details["tag"] == "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
    latest = body["periods"][-1]
    assert (latest["form"], latest["filed"], latest["end"]) == ("10-K", "2026-11-03", "2026-09-26")
    assert latest["url"] == details["url"]
    for result in body["metrics"].values():
        if result["status"] == "ok":
            assert result["details"]["url"].startswith("https://www.sec.gov/Archives/edgar/data/")
            assert result["details"]["form"] and result["details"]["filed"]


def test_missing_line_items_say_not_reported_and_the_rest_still_render() -> None:
    with serving(edgar_adapter(), "sec_edgar"):
        body = post({"ticker": "JPM"}).json()

    cogs = body["metrics"]["cost_of_revenue:2025-12-31"]
    assert cogs["status"] == "missing_data"
    assert cogs["value"] is None
    assert cogs["reason"] == "Cost of Revenue is not reported by this company."
    assert cogs["details"] == {"missing": "not_reported"}
    assert body["metrics"]["net_income:2025-12-31"]["status"] == "ok"
    assert body["metrics"]["total_assets:2025-12-31"]["status"] == "ok"


def test_years_selects_how_many_recent_fiscal_years() -> None:
    with serving(edgar_adapter(), "sec_edgar"):
        body = post({"ticker": "msft", "years": 3}).json()

    assert [p["label"] for p in body["periods"]] == ["FY2024", "FY2025", "FY2026"]
    assert body["company"]["ticker"] == "MSFT"
    assert not [m for m in body["metrics"] if m.endswith(":2023-06-30")]


def test_an_unknown_ticker_is_an_inline_error_on_the_ticker_field() -> None:
    with serving(edgar_adapter(), "sec_edgar"):
        res = post({"ticker": "ZZZZ"})

    assert res.status_code == 422
    error = res.json()["error"]
    assert error["code"] == "no_such_data"
    assert "Unknown ticker ZZZZ" in error["fields"]["ticker"]


def test_a_blank_ticker_and_out_of_range_years_are_field_errors() -> None:
    with serving(edgar_adapter(), "sec_edgar"):
        res = post({"ticker": "  ", "years": 0})

    assert res.status_code == 422
    fields = res.json()["error"]["fields"]
    assert fields["ticker"] == "Enter a ticker."
    assert fields["years"] == "Choose between 1 and 10 years."


def test_an_edgar_outage_is_source_unavailable() -> None:
    with serving(edgar_adapter(edgar_transport(status=503)), "sec_edgar"):
        res = post()

    assert res.status_code == 503
    assert res.json()["error"]["code"] == "source_unavailable"


def test_statements_are_served_from_the_shared_cache() -> None:
    transport = edgar_transport()
    with serving(edgar_adapter(transport), "sec_edgar") as service:
        first = post({"ticker": "AAPL", "years": 5}).json()
        hits = len(transport.requests)
        second = post({"ticker": "aapl", "years": 3}).json()

    assert len(transport.requests) == hits  # no EDGAR traffic the second time
    assert len(service.shared_cache) == 1  # type: ignore[arg-type]
    assert second["metrics"]["revenue:2026-09-26"] == first["metrics"]["revenue:2026-09-26"]
