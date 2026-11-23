"""EDGAR adapter on recorded companyfacts: line-item mapping, provenance, errors.

Expected values are the figures printed in each company's 10-K (in USD).
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from sextant_compute.analytics.errors import MissingData
from sextant_compute.data.context import RequestContext
from sextant_compute.data.edgar.client import EDGAR_MAX_PER_SECOND, RateLimiter
from sextant_compute.data.errors import NoSuchData, SourceUnavailable
from sextant_compute.data.statements import Missing, Reported
from tests.edgar_fixtures import edgar_adapter, edgar_transport, load_facts
from tests.test_edgar_rate_limit import FakeClock, max_in_any_second

CTX = RequestContext.anonymous()


def reported(cell) -> Reported:
    assert isinstance(cell, Reported), cell
    return cell


def test_revenue_resolves_for_two_companies_that_use_different_xbrl_tags() -> None:
    adapter = edgar_adapter()

    apple = adapter.financial_statements(CTX, "AAPL")
    walmart = adapter.financial_statements(CTX, "WMT")

    apple_fy2026 = reported(apple.cell("revenue", "2026-09-26"))
    assert apple_fy2026.value == 478_834_000_000
    assert apple_fy2026.tag == "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
    walmart_fy2026 = reported(walmart.cell("revenue", "2026-01-31"))
    assert walmart_fy2026.value == 713_163_000_000
    assert walmart_fy2026.tag == "us-gaap:Revenues"


def test_the_tag_is_chosen_per_period_so_a_stale_tag_does_not_hide_newer_years() -> None:
    # Apple tagged revenue as us-gaap:Revenues until FY2018, then switched tags.
    # Revenues is first in priority, so a per-company choice would stop at 2018.
    apple = edgar_adapter().financial_statements(CTX, "AAPL")

    fy2018 = reported(apple.cell("revenue", "2018-09-29"))
    assert fy2018.value == 265_595_000_000
    assert fy2018.tag == "us-gaap:Revenues"
    assert reported(apple.cell("revenue", "2025-09-27")).value == 416_161_000_000


def test_periods_are_fiscal_years_with_their_filing() -> None:
    apple = edgar_adapter().financial_statements(CTX, "AAPL")

    latest = apple.periods[-1]
    assert latest.label == "FY2026"
    assert (latest.start, latest.end) == (date(2025, 9, 28), date(2026, 9, 26))
    assert latest.filing.form == "10-K"
    assert latest.filing.filed == date(2026, 11, 3)
    assert latest.filed == date(2026, 11, 3)
    assert [p.end for p in apple.periods] == sorted(p.end for p in apple.periods)
    # A column's date is its own 10-K's, even when a later 10-K first tagged some
    # item for that year (that cell then carries the later filing).
    fy2024 = next(p for p in apple.periods if p.label == "FY2024")
    assert fy2024.filed == date(2024, 11, 1)
    later = [
        c for row in apple.cells.values() if isinstance(c := row[fy2024.id], Reported) and c.filing.filed > fy2024.filed
    ]
    assert later, "fixture should contain an item first reported in a later filing"
    # Walmart's fiscal 2026 ends in January 2026.
    walmart = edgar_adapter().financial_statements(CTX, "WMT")
    assert (walmart.periods[-1].label, walmart.periods[-1].end) == ("FY2026", date(2026, 1, 31))


def test_every_value_carries_its_source_filing() -> None:
    apple = edgar_adapter().financial_statements(CTX, "AAPL")

    cell = reported(apple.cell("revenue", "2026-09-26"))
    assert cell.filing.accession == "0000320193-26-000026"
    assert cell.filing.form == "10-K"
    assert cell.filing.filed == date(2026, 11, 3)
    assert cell.filing.url == (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019326000026/0000320193-26-000026-index.htm"
    )
    # Values are as first reported: FY2025 revenue comes from the FY2025 10-K,
    # not from the FY2026 10-K that repeats it as a comparative.
    assert reported(apple.cell("revenue", "2025-09-27")).filing.filed == date(2025, 10, 31)


def test_balance_sheet_items_are_year_end_instants() -> None:
    apple = edgar_adapter().financial_statements(CTX, "AAPL")

    assert reported(apple.cell("total_liabilities", "2026-09-26")).value == 292_455_000_000
    assert reported(apple.cell("current_assets", "2025-09-27")).value == 147_957_000_000


def test_an_item_the_company_never_reports_is_missing_with_an_explicit_reason() -> None:
    bank = edgar_adapter().financial_statements(CTX, "JPM")

    cell = bank.cell("cost_of_revenue", bank.periods[-1].id)
    assert isinstance(cell, Missing)
    assert cell.reason == "not_reported"
    assert cell.message == "Cost of Revenue is not reported by this company."
    # Tools read values through .value(), which raises MissingData naming the item.
    with pytest.raises(MissingData, match="Cost of Revenue"):
        bank.value("cost_of_revenue", bank.periods[-1].id)
    # The rest of the statements are unaffected.
    assert bank.value("net_income", bank.periods[-1].id) > 0


def test_an_item_missing_for_one_period_says_which_period() -> None:
    facts = load_facts("AAPL")
    rows = facts["facts"]["us-gaap"]["Assets"]["units"]["USD"]
    facts["facts"]["us-gaap"]["Assets"]["units"]["USD"] = [r for r in rows if r["end"] != "2025-09-27"]
    apple = edgar_adapter(edgar_transport(facts_override={"AAPL": facts})).financial_statements(CTX, "AAPL")

    cell = apple.cell("total_assets", "2025-09-27")
    assert isinstance(cell, Missing)
    assert cell.reason == "not_reported_for_period"
    assert cell.message == "Total Assets is not reported by this company for FY2025."
    assert isinstance(apple.cell("total_assets", "2026-09-26"), Reported)


def test_an_item_without_a_tag_is_derived_when_the_mapping_says_how() -> None:
    # Walmart tags neither GrossProfit nor Liabilities.
    walmart = edgar_adapter().financial_statements(CTX, "WMT")

    gross = reported(walmart.cell("gross_profit", "2026-01-31"))
    assert gross.value == 713_163_000_000 - 535_395_000_000
    assert gross.tag is None
    assert gross.derived_from == "revenue - cost_of_revenue"
    assert gross.filing.form == "10-K"
    liabilities = reported(walmart.cell("total_liabilities", "2026-01-31"))
    assert liabilities.derived_from == "total_liabilities_and_equity - total_equity_including_nci"
    # Microsoft reports sales & marketing and G&A separately.
    microsoft = edgar_adapter().financial_statements(CTX, "MSFT")
    assert microsoft.value("selling_general_administrative", "2026-06-30") == 26_710_000_000 + 7_956_000_000


def test_tickers_are_normalized() -> None:
    adapter = edgar_adapter()

    assert adapter.financial_statements(CTX, " aapl ").company.ticker == "AAPL"
    assert adapter.resolve(CTX, "brk.b").cik == 1067983


def test_an_unknown_ticker_is_no_such_data_keyed_by_the_ticker() -> None:
    with pytest.raises(NoSuchData) as exc:
        edgar_adapter().financial_statements(CTX, "ZZZZ")

    assert list(exc.value.missing) == ["ZZZZ"]
    assert "Unknown ticker ZZZZ" in exc.value.missing["ZZZZ"]


def test_a_company_without_xbrl_financials_is_no_such_data() -> None:
    # BRK-B is in the ticker map, but no companyfacts are recorded for it (EDGAR answers 404).
    with pytest.raises(NoSuchData) as exc:
        edgar_adapter().financial_statements(CTX, "BRK-B")

    assert "no annual US-GAAP financial statements for BRK-B" in exc.value.missing["BRK-B"]


@pytest.mark.parametrize(
    "transport",
    [
        pytest.param(lambda: edgar_transport(status=503), id="5xx"),
        pytest.param(lambda: edgar_transport(status=429), id="rate-limited"),
        pytest.param(lambda: edgar_transport(status=403), id="forbidden"),
        pytest.param(lambda: edgar_transport(error=httpx.ConnectTimeout("timed out")), id="timeout"),
    ],
)
def test_an_edgar_outage_is_source_unavailable(transport) -> None:
    with pytest.raises(SourceUnavailable):
        edgar_adapter(transport()).financial_statements(CTX, "AAPL")


def test_transient_errors_are_retried() -> None:
    calls = {"n": 0}

    def flaky(request: httpx.Request) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("reset")

    statements = edgar_adapter(edgar_transport(on_request=flaky)).financial_statements(CTX, "MSFT")
    assert statements.company.name == "MICROSOFT CORP"


def test_the_user_agent_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEC_USER_AGENT", "Sextant env-test admin@example.com")
    transport = edgar_transport()

    edgar_adapter(transport, user_agent=None).financial_statements(CTX, "AAPL")

    assert transport.requests
    assert {r.headers["user-agent"] for r in transport.requests} == {"Sextant env-test admin@example.com"}


def test_without_a_user_agent_no_request_is_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    transport = edgar_transport()

    with pytest.raises(SourceUnavailable):
        edgar_adapter(transport, user_agent=None).financial_statements(CTX, "AAPL")
    assert transport.requests == []


def test_adapter_traffic_goes_through_the_rate_limiter() -> None:
    clock = FakeClock()
    sent: list[float] = []
    transport = edgar_transport(on_request=lambda _r: sent.append(clock.time()))
    limiter = RateLimiter(EDGAR_MAX_PER_SECOND, clock=clock.time, sleep=clock.sleep)
    adapter = edgar_adapter(transport, limiter=limiter)

    for _ in range(4):
        for ticker in ("AAPL", "MSFT", "JPM", "WMT"):
            adapter.financial_statements(CTX, ticker)

    assert len(sent) == 17  # one ticker map (kept in process) + 16 companyfacts
    assert max_in_any_second(sent) <= EDGAR_MAX_PER_SECOND < 10
