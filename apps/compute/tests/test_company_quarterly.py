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
