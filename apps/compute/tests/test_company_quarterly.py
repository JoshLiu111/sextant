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


def test_per_share_amounts_are_not_derived_for_q4() -> None:
    body = post(STATEMENTS, {"ticker": "AAPL", "frequency": "quarterly", "quarters": 4})
    metrics = body["metrics"]

    assert metrics[f"eps_diluted:{Q3}"]["value"] == 2.02
    q4 = metrics[f"eps_diluted:{Q4}"]
    assert q4["status"] == "missing_data"
    assert "Q4 FY2026" in q4["reason"] and "per-share" in q4["reason"]


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
