"""Earnings calendar and dividend history (P7) on recorded EDGAR responses:
submissions (``fixtures/edgar/submissions/``, recorded 2026-11-22) and
companyfacts per-share dividend tags. "Today" is pinned to 2026-11-22."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app
from tests.data_fixtures import serving
from tests.edgar_fixtures import edgar_adapter, edgar_transport

client = TestClient(app)
EARNINGS = "/api/compute/screener/earnings"
DIVIDENDS = "/api/compute/screener/dividends"


@pytest.fixture(autouse=True)
def _today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCREENER_TODAY", "2026-11-22")


def post(path: str, body: dict, adapter=None):
    with serving(adapter or edgar_adapter(), "sec_edgar"):
        return client.post(path, json=body)


# --- Earnings calendar ---------------------------------------------------------


def test_default_calendar_lists_recent_earnings_8ks_and_upcoming_estimates() -> None:
    res = post(EARNINGS, {})

    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["start"], body["end"], body["as_of"]) == ("2026-10-23", "2027-01-21", "2026-11-22")
    reported = [(e["date"], e["ticker"]) for e in body["events"] if e["status"] == "reported"]
    assert reported == [
        ("2026-10-27", "KO"),
        ("2026-10-27", "V"),
        ("2026-10-28", "GOOGL"),
        ("2026-10-28", "MSFT"),
        ("2026-10-29", "AMZN"),
        ("2026-10-30", "XOM"),
        ("2026-11-02", "AAPL"),
        ("2026-11-17", "NVDA"),
        ("2026-11-19", "WMT"),
    ]
    aapl = next(e for e in body["events"] if e["ticker"] == "AAPL")
    assert aapl == {
        "ticker": "AAPL",
        "company": "Apple Inc.",
        "cik": 320193,
        "date": "2026-11-02",
        "status": "reported",
        "form": "8-K",
        "accession": "0000320193-26-000024",
        "url": "https://www.sec.gov/Archives/edgar/data/320193/000032019326000024/0000320193-26-000024-index.htm",
        "based_on": None,
    }
    assert body["meta"]["data_cutoff"] == "2026-11-19"


def test_upcoming_dates_are_projected_from_last_years_release() -> None:
    body = post(EARNINGS, {}).json()

    expected = [(e["date"], e["ticker"], e["based_on"]) for e in body["events"] if e["status"] == "expected"]
    # JPM reported 2026-01-13, so it is expected 52 weeks later, on the same weekday.
    assert ("2027-01-12", "JPM", "2026-01-13") in expected
    assert ("2027-01-21", "PG", "2026-01-22") in expected  # the range end is inclusive
    assert all(when > "2026-11-22" for when, _, _ in expected)
    jpm = next(e for e in body["events"] if e["ticker"] == "JPM")
    assert jpm["url"].endswith("/0001628280-26-001902-index.htm")  # last year's 8-K


def test_a_company_that_already_reported_early_is_not_expected_again() -> None:
    # NVDA reported 2025-11-19, projecting 2026-11-18; it reported 2026-11-17.
    body = post(EARNINGS, {"tickers": ["NVDA"], "start": "2026-11-01", "end": "2026-12-31"}).json()

    assert [(e["date"], e["status"]) for e in body["events"]] == [("2026-11-17", "reported")]


def test_the_calendar_filters_by_date_range_and_tickers() -> None:
    body = post(EARNINGS, {"tickers": "aapl, msft", "start": "2026-01-01", "end": "2026-06-30"}).json()

    assert body["tickers"] == ["AAPL", "MSFT"]
    assert [(e["date"], e["ticker"], e["status"]) for e in body["events"]] == [
        ("2026-01-28", "MSFT", "reported"),
        ("2026-01-29", "AAPL", "reported"),
        ("2026-04-29", "MSFT", "reported"),
        ("2026-04-30", "AAPL", "reported"),
    ]


def test_only_item_2_02_8ks_count_as_earnings() -> None:
    body = post(EARNINGS, {"tickers": ["AAPL"], "start": "2025-11-22", "end": "2026-11-22"}).json()

    # AAPL's other 8-Ks in the year (e.g. Items 8.01 / 5.07) are not releases.
    assert [e["date"] for e in body["events"]] == ["2026-01-29", "2026-04-30", "2026-07-30", "2026-11-02"]
    assert {e["form"] for e in body["events"]} == {"8-K"}


def test_an_unknown_ticker_is_shown_on_the_tickers_field() -> None:
    res = post(EARNINGS, {"tickers": ["AAPL", "ZZZZ"]})

    assert res.status_code == 422
    assert "Unknown ticker ZZZZ" in res.json()["error"]["fields"]["tickers"]


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"start": "2026-06-01", "end": "2026-01-01"}, "end"),
        ({"start": "2025-01-01", "end": "2026-06-01"}, "end"),
        ({"tickers": []}, "tickers"),
        ({"tickers": [f"T{i}" for i in range(21)]}, "tickers"),
        ({"start": "2027-06-01"}, "end"),  # after the default end
    ],
)
def test_invalid_calendar_inputs_name_the_field(body: dict, field: str) -> None:
    res = post(EARNINGS, body)

    assert res.status_code == 422
    assert field in res.json()["error"]["fields"]


def test_calendar_reuses_cached_submissions_and_shares_the_rate_limited_client() -> None:
    transport = edgar_transport()
    with serving(edgar_adapter(transport), "sec_edgar"):
        client.post(EARNINGS, json={"tickers": ["AAPL", "MSFT"]})
        client.post(EARNINGS, json={"tickers": ["AAPL", "MSFT"], "start": "2026-01-01", "end": "2026-03-31"})

    subs = [p for p in transport.paths() if p.startswith("/submissions/")]
    assert sorted(subs) == ["/submissions/CIK0000320193.json", "/submissions/CIK0000789019.json"]
    assert all(r.headers["user-agent"] == "Sextant test admin@example.com" for r in transport.requests)


def test_an_edgar_outage_is_a_503() -> None:
    res = post(EARNINGS, {"tickers": ["AAPL"]}, edgar_adapter(edgar_transport(status=503)))

    assert res.status_code == 503
    assert res.json()["error"]["code"] == "source_unavailable"


# --- Dividend history ------------------------------------------------------------


def test_dividend_history_lists_declared_dividends_per_share_by_period() -> None:
    res = post(DIVIDENDS, {"ticker": " jpm "})

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["company"] == {"ticker": "JPM", "cik": 19617, "name": "JPMORGAN CHASE & CO"}
    assert body["pays_dividends"] is True
    assert body["basis"] == "declared"
    assert body["note"] is None
    rows = [(p["label"], p["end"], p["value"], p["derived"]) for p in body["periods"][:9]]
    # JPM 10-Qs and 10-Ks: $1.40, $1.40, $1.50 then $1.50 (Q4 = $5.80 for the year less 9 months).
    assert rows == [
        ("Q3 FY2026", "2026-09-30", 1.65, False),
        ("Q2 FY2026", "2026-06-30", 1.5, False),
        ("Q1 FY2026", "2026-03-31", 1.5, False),
        ("FY2025", "2025-12-31", 5.8, False),
        ("Q4 FY2025", "2025-12-31", 1.5, True),
        ("Q3 FY2025", "2025-09-30", 1.5, False),
        ("Q2 FY2025", "2025-06-30", 1.4, False),
        ("Q1 FY2025", "2025-03-31", 1.4, False),
        ("FY2024", "2024-12-31", 4.8, False),
    ]
    fy2025 = body["periods"][3]
    assert fy2025["tag"] == "us-gaap:CommonStockDividendsPerShareDeclared"
    assert fy2025["filing"] == {
        "form": "10-K",
        "filed": "2026-02-13",
        "accession": "0001628280-26-008131",
        "url": "https://www.sec.gov/Archives/edgar/data/19617/000162828026008131/0001628280-26-008131-index.htm",
    }
    assert body["meta"]["data_cutoff"] == "2026-09-30"


def test_fiscal_years_follow_the_companys_own_calendar() -> None:
    periods = post(DIVIDENDS, {"ticker": "AAPL"}).json()["periods"]

    fy2026 = next(p for p in periods if p["label"] == "FY2026")
    assert (fy2026["start"], fy2026["end"], fy2026["value"]) == ("2025-09-28", "2026-09-26", 1.06)
    quarters = [(p["label"], p["value"]) for p in periods if p["kind"] == "quarter" and p["fiscal_year"] == 2026]
    assert quarters == [("Q4 FY2026", 0.27), ("Q3 FY2026", 0.27), ("Q2 FY2026", 0.26), ("Q1 FY2026", 0.26)]


def test_a_company_that_pays_no_dividend_says_so() -> None:
    res = post(DIVIDENDS, {"ticker": "AMZN"})

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["pays_dividends"] is False
    assert body["periods"] == []
    assert body["basis"] is None
    assert body["note"] == "AMAZON COM INC (AMZN) has reported no per-share dividends in its XBRL filings."


def test_dividends_for_an_unknown_ticker_or_one_without_xbrl_are_field_errors() -> None:
    unknown = post(DIVIDENDS, {"ticker": "ZZZZ"})
    assert unknown.status_code == 422
    assert "Unknown ticker ZZZZ" in unknown.json()["error"]["fields"]["ticker"]

    no_facts = post(DIVIDENDS, {"ticker": "BRK.B"})
    assert no_facts.status_code == 422
    assert no_facts.json()["error"]["fields"]["ticker"] == "SEC EDGAR has no XBRL financial data for BRK-B."


def test_dividends_are_cached() -> None:
    transport = edgar_transport()
    with serving(edgar_adapter(transport), "sec_edgar"):
        client.post(DIVIDENDS, json={"ticker": "AAPL"})
        client.post(DIVIDENDS, json={"ticker": "aapl"})

    assert transport.paths().count("/api/xbrl/companyfacts/CIK0000320193.json") == 1
