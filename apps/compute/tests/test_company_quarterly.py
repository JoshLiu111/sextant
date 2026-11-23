"""Company Health Check (P1): quarterly statements and ratios, and the ratio
drill-down, on recorded EDGAR fixtures (10-K and 10-Q facts).

AAPL fiscal 2026 from its 10-Qs and 10-K (USD millions):

    quarter (end)          revenue   operating cash flow (YTD)   total assets
    Q1 FY2026 2025-12-27   143,756    53,925                     379,297
    Q2 FY2026 2026-03-28   111,184    82,627 (6 months)          371,082
    Q3 FY2026 2026-06-27   109,417   116,996 (9 months)          383,266
    FY2026    2026-09-26   478,834   145,097 (10-K)              404,548
    9 months to Q3         364,357

Q4 = the year minus the nine months: revenue 478,834 - 364,357 = 114,477;
operating cash flow 145,097 - 116,996 = 28,101. Cash flows are year to date in
10-Qs, so Q2 = 82,627 - 53,925 = 28,702 and Q3 = 116,996 - 82,627 = 34,369.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from pytest import approx

from main import app
from tests.data_fixtures import serving
from tests.edgar_fixtures import edgar_adapter

client = TestClient(app)
STATEMENTS = "/api/compute/company/statements"
Q1, Q2, Q3, Q4 = "2025-12-27", "2026-03-28", "2026-06-27", "2026-09-26"


def post(path: str, body: dict) -> dict:
    with serving(edgar_adapter(), "sec_edgar"):
        res = client.post(path, json=body)
    assert res.status_code == 200, res.text
    return res.json()


def test_quarterly_statements_are_labelled_by_fiscal_quarter() -> None:
    body = post(STATEMENTS, {"ticker": "AAPL", "frequency": "quarterly", "quarters": 4})

    assert [p["label"] for p in body["periods"]] == ["Q1 FY2026", "Q2 FY2026", "Q3 FY2026", "Q4 FY2026"]
    assert [p["id"] for p in body["periods"]] == [Q1, Q2, Q3, Q4]
    assert [p["fiscal_quarter"] for p in body["periods"]] == [1, 2, 3, 4]
    assert [p["form"] for p in body["periods"]] == ["10-Q", "10-Q", "10-Q", "10-K"]
    assert body["periods"][1]["start"] == "2025-12-28"


def test_q4_flows_are_the_year_minus_the_first_three_quarters() -> None:
    body = post(STATEMENTS, {"ticker": "AAPL", "frequency": "quarterly", "quarters": 4})
    metrics = body["metrics"]

    revenue = [metrics[f"revenue:{q}"]["value"] / 1e6 for q in (Q1, Q2, Q3, Q4)]
    assert revenue == [143_756, 111_184, 109_417, 114_477]
    assert sum(revenue) == 478_834  # the four quarters add up to the year, nothing counted twice
    ocf = [metrics[f"operating_cash_flow:{q}"]["value"] / 1e6 for q in (Q1, Q2, Q3, Q4)]
    assert ocf == [53_925, 28_702, 34_369, 28_101]
    assert sum(ocf) == 145_097

    q4 = metrics[f"revenue:{Q4}"]["details"]
    assert q4["form"] == "10-K"
    assert q4["derived_from"] == "FY2026 (10-K filed 2026-11-03) minus the nine months to 2026-06-27 (10-Q filed 2026-07-31)"
    assert metrics[f"revenue:{Q2}"]["details"]["form"] == "10-Q"
    assert metrics[f"revenue:{Q2}"]["details"]["derived_from"] is None
    assert metrics[f"total_assets:{Q2}"]["value"] == 371_082_000_000


# Q4 share counts and EPS, AAPL FY2026 (diluted). The year (10-K) is 364 days, the
# nine months to Q3 (10-Q) 273 and Q4 91. A weighted-average share count is the
# day-weighted average of its parts, so
#   Q4 shares = (FY x 364 - 9M x 273) / 91 = 4 x 14,720,306,000 - 3 x 14,750,302,000
#             = 14,630,318,000
# EPS x weighted shares = the earnings behind the EPS, so
#   Q4 EPS = (8.98 x 14,720,306,000 - 6.88 x 14,750,302,000) / 14,630,318,000
#          = 30,706,270,120 / 14,630,318,000 = 2.09881
# (Q4 net income 132,175 - 101,464 = 30,711 million over the same shares: 2.0991.)
Q4_SHARES_DILUTED = 14_630_318_000
Q4_EPS_DILUTED = 30_706_270_120 / 14_630_318_000


def test_q4_share_counts_and_eps_are_derived_from_the_year_and_the_nine_months() -> None:
    body = post(STATEMENTS, {"ticker": "AAPL", "frequency": "quarterly", "quarters": 4})
    metrics = body["metrics"]

    assert metrics[f"eps_diluted:{Q3}"]["value"] == 2.02
    shares = metrics[f"shares_diluted:{Q4}"]
    assert shares["status"] == "ok"
    assert shares["value"] == approx(Q4_SHARES_DILUTED)
    assert shares["details"]["form"] == "10-K"
    assert "weighted by days" in shares["details"]["derived_from"]
    assert "nine months to 2026-06-27 (10-Q filed 2026-07-31)" in shares["details"]["derived_from"]
    eps = metrics[f"eps_diluted:{Q4}"]
    assert eps["status"] == "ok"
    assert eps["value"] == approx(Q4_EPS_DILUTED, abs=1e-6)
    assert "EPS x weighted shares" in eps["details"]["derived_from"]
    assert metrics[f"shares_basic:{Q4}"]["value"] == approx(4 * 14_661_935_000 - 3 * 14_692_515_000)


def test_quarterly_pe_and_the_q4_dilution_signal_now_compute() -> None:
    body = post(
        RATIOS, {"companies": [{"ticker": "AAPL", "price": 250.0}], "frequency": "quarterly", "quarters": 4}
    )
    metrics = body["metrics"]

    # TTM diluted EPS to Q4 FY2026: 2.84 + 2.01 + 2.02 + 2.09881 = 8.96881.
    pe = metrics[f"price_to_earnings:AAPL:{Q4}"]
    assert pe["status"] == "ok", pe["reason"]
    assert pe["value"] == approx(250.0 / (2.84 + 2.01 + 2.02 + Q4_EPS_DILUTED))
    # Q4 FY2026 basic shares (14,570,195,000) vs Q4 FY2025's: fewer, so the signal is 1.
    dilution = metrics[f"piotroski_no_dilution:AAPL:{Q4}"]
    assert dilution["status"] == "ok", dilution["reason"]
    assert dilution["value"] == 1
    assert metrics[f"piotroski_f:AAPL:{Q4}"]["status"] == "ok"


def test_annual_stays_the_default() -> None:
    body = post(STATEMENTS, {"ticker": "AAPL"})
    assert [p["label"] for p in body["periods"]] == ["FY2022", "FY2023", "FY2024", "FY2025", "FY2026"]
    assert body["periods"][-1]["fiscal_quarter"] is None


# --- Ratios on quarterly data ----------------------------------------------------
#
# Flows are trailing twelve months (TTM): the four quarters to the quarter end.
# Balances are the quarter end; averages use the year-earlier quarter end.
#   TTM revenue to Q3 FY2026 = Q4 FY2025 (416,161 - 313,695 = 102,466)
#                            + 143,756 + 111,184 + 109,417 = 466,823
#   total assets 2025-06-28 = 331,495; 2026-06-27 = 383,266 (average 357,380.5)
#   asset turnover = 466,823 / 357,380.5 = 1.30624

RATIOS = "/api/compute/company/ratios"
INPUTS = "/api/compute/company/ratios/inputs"
Q3_FY25 = "2025-06-28"


def test_quarterly_ratios_use_trailing_twelve_months_and_say_so() -> None:
    body = post(RATIOS, {"companies": [{"ticker": "AAPL"}], "frequency": "quarterly", "quarters": 4})

    assert [p["label"] for p in body["companies"][0]["periods"]] == ["Q1 FY2026", "Q2 FY2026", "Q3 FY2026", "Q4 FY2026"]
    turnover = body["metrics"][f"asset_turnover:AAPL:{Q3}"]
    assert turnover["value"] == approx(466_823 / 357_380.5)
    assert turnover["details"]["basis"] == "ttm"
    basis = {r["id"]: r["basis"] for r in [*body["ratios"], *body["models"]]}
    assert basis["asset_turnover"] == "ttm"
    assert basis["return_on_equity"] == "ttm"
    assert basis["current_ratio"] == "quarter_end"
    assert basis["debt_to_equity"] == "quarter_end"
    assert body["metrics"][f"current_ratio:AAPL:{Q3}"]["details"]["basis"] == "quarter_end"


def test_ttm_ratios_at_q4_match_the_fiscal_year() -> None:
    quarterly = post(RATIOS, {"companies": [{"ticker": "AAPL"}], "frequency": "quarterly", "quarters": 4})
    annual = post(RATIOS, {"companies": [{"ticker": "AAPL"}]})

    for ratio in ("asset_turnover", "return_on_equity", "net_margin", "days_sales_outstanding", "altman_z"):
        q4 = quarterly["metrics"][f"{ratio}:AAPL:{Q4}"]["value"]
        assert q4 == approx(annual["metrics"][f"{ratio}:AAPL:{Q4}"]["value"]), ratio
    assert annual["metrics"][f"asset_turnover:AAPL:{Q4}"]["details"] == {}
    assert {r["basis"] for r in annual["ratios"]} == {"fiscal_year"}


def test_frequency_and_quarters_are_validated() -> None:
    with serving(edgar_adapter(), "sec_edgar"):
        res = client.post(RATIOS, json={"frequency": "monthly", "quarters": 0})
    assert res.status_code == 422
    assert set(res.json()["error"]["fields"]) >= {"frequency", "quarters"}


# --- Drill-down ------------------------------------------------------------------


def test_drill_down_shows_each_input_and_the_filing_it_came_from() -> None:
    body = post(INPUTS, {"ticker": "AAPL", "ratio": "current_ratio", "period": Q4})

    assert body["ratio"] == {"id": "current_ratio", "category": "liquidity", "unit": "ratio", "basis": "fiscal_year"}
    assert body["period"]["label"] == "FY2026"
    result = body["metrics"][f"current_ratio:AAPL:{Q4}"]
    assert result["value"] == approx(173_857 / 169_915, abs=1e-3)
    assert [(i["item"], i["period_label"]) for i in body["inputs"]] == [
        ("current_assets", "FY2026"),
        ("current_liabilities", "FY2026"),
    ]
    assets = body["inputs"][0]
    assert assets["label"] == "Total Current Assets"
    assert round(assets["value"] / 1e6) == 173_857
    [source] = assets["sources"]
    assert (source["form"], source["filed"]) == ("10-K", "2026-11-03")
    assert source["url"].startswith("https://www.sec.gov/Archives/edgar/data/320193/")


def test_drill_down_on_a_ttm_ratio_lists_the_four_quarters() -> None:
    body = post(INPUTS, {"ticker": "AAPL", "ratio": "asset_turnover", "period": Q3, "frequency": "quarterly"})

    assert body["ratio"]["basis"] == "ttm"
    assert body["metrics"][f"asset_turnover:AAPL:{Q3}"]["value"] == approx(466_823 / 357_380.5)
    inputs = {(i["item"], i["period_id"]): i for i in body["inputs"]}
    assert set(inputs) == {("revenue", Q3), ("total_assets", Q3_FY25), ("total_assets", Q3)}
    revenue = inputs[("revenue", Q3)]
    assert revenue["basis"] == "ttm"
    assert round(revenue["value"] / 1e6) == 466_823
    assert [s["period_label"] for s in revenue["sources"]] == ["Q4 FY2025", "Q1 FY2026", "Q2 FY2026", "Q3 FY2026"]
    assert [s["form"] for s in revenue["sources"]] == ["10-K", "10-Q", "10-Q", "10-Q"]
    assert revenue["sources"][0]["derived_from"].startswith("FY2025 (10-K filed 2025-10-31) minus the nine months")
    assert inputs[("total_assets", Q3_FY25)]["sources"][0]["filed"] == "2025-08-01"


def test_drill_down_rejects_an_unknown_ratio_or_period() -> None:
    with serving(edgar_adapter(), "sec_edgar"):
        res = client.post(INPUTS, json={"ticker": "AAPL", "ratio": "nope", "period": Q4})
        assert res.status_code == 422
        assert "ratio" in res.json()["error"]["fields"]
        res = client.post(INPUTS, json={"ticker": "AAPL", "ratio": "current_ratio", "period": "2026-01-01"})
        assert res.status_code == 422
        assert "period" in res.json()["error"]["fields"]
