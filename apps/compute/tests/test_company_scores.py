"""Company Health Check (P1): Piotroski F-Score, Beneish M-Score and DuPont
decomposition on recorded EDGAR fixtures, through ``POST /company/ratios``.

Expected values are hand-computed from the 10-K figures (USD millions). AAPL:

    item                     FY2023    FY2024    FY2025    FY2026
    revenue                 383,285   391,035   416,161   478,834
    gross profit            169,148   180,683   195,201   233,602
    SG&A                     24,932    26,097    27,601    29,774
    operating income        114,301   123,216   133,050   158,063
    pretax income           113,736   123,485   132,729   159,237
    net income               96,995    93,736   112,010   132,175
    basic shares (wtd, M)    15,744    15,344    14,949    14,662
    receivables              29,508    33,410    39,777    43,817
    current assets          143,566   152,987   147,957   173,857
    PP&E (net)               43,715    45,680    49,834    52,084
    total assets            352,583   364,980   359,241   404,548
    current liabilities     145,308   176,392   165,631   169,915
    long-term debt           95,281    85,750    78,328    68,208
    total equity             62,146    56,950    73,733   112,093
    operating cash flow     110,543   118,254   111,482   145,097
    D&A                      11,519    11,445    11,698    13,423
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from pytest import approx

from main import app
from tests.data_fixtures import serving
from tests.edgar_fixtures import edgar_adapter, edgar_transport, load_facts, without_tags

client = TestClient(app)
PATH = "/api/compute/company/ratios"
AAPL_FY26 = "2026-09-26"
AAPL_FY25 = "2025-09-27"
SIGNALS = (
    "piotroski_roa",
    "piotroski_cfo",
    "piotroski_delta_roa",
    "piotroski_accrual",
    "piotroski_delta_leverage",
    "piotroski_delta_current_ratio",
    "piotroski_no_dilution",
    "piotroski_delta_gross_margin",
    "piotroski_delta_asset_turnover",
)


def post(body: dict | None = None, adapter=None):
    with serving(adapter or edgar_adapter(), "sec_edgar"):
        res = client.post(PATH, json=body if body is not None else {})
    assert res.status_code == 200, res.text
    return res.json()


def m(body: dict, model: str, ticker: str, period: str) -> dict:
    return body["metrics"][f"{model}:{ticker}:{period}"]


def test_the_envelope_lists_the_scores_signals_and_dupont_components() -> None:
    body = post()

    models = {r["id"]: r for r in body["models"]}
    assert [r["id"] for r in body["models"] if r["category"] == "scores"] == ["altman_z", "piotroski_f", "beneish_m"]
    assert [r["id"] for r in body["models"] if r["category"] == "piotroski"] == list(SIGNALS)
    assert models["dupont_tax_burden"]["category"] == "dupont"
    assert models["dupont_interest_burden"]["category"] == "dupont"
    assert models["piotroski_f"]["unit"] == "score"
    assert models["piotroski_roa"]["unit"] == "signal"
    for p in body["companies"][0]["periods"]:
        for r in body["models"]:
            assert f"{r['id']}:AAPL:{p['id']}" in body["metrics"]


def test_piotroski_signals_and_score_match_a_hand_computation() -> None:
    body = post()

    # FY2025 against FY2024 (and FY2023 for FY2024's ROA and asset turnover):
    # 1 ROA 112,010 / 364,980 = 0.307 > 0          -> 1
    # 2 OCF 111,482 > 0                             -> 1
    # 3 ROA rose from 93,736 / 352,583 = 0.266      -> 1
    # 4 OCF / opening assets 0.3054 < ROA 0.3069    -> 0 (accruals)
    # 5 LTD / avg assets 0.2163 < 0.2390            -> 1
    # 6 current ratio 0.893 > 0.867                 -> 1
    # 7 basic shares 14,949 < 15,344                -> 1
    # 8 gross margin 0.4691 > 0.4621                -> 1
    # 9 asset turnover 416,161 / 364,980 = 1.140 > 391,035 / 352,583 = 1.109 -> 1
    expected = dict(zip(SIGNALS, (1, 1, 1, 0, 1, 1, 1, 1, 1), strict=True))
    for signal, passed in expected.items():
        result = m(body, signal, "AAPL", AAPL_FY25)
        assert result["status"] == "ok", signal
        assert result["value"] == passed, signal
    accrual = m(body, "piotroski_accrual", "AAPL", AAPL_FY25)["details"]
    assert accrual["measure"] == approx(111_482 / 364_980)
    assert accrual["compared_with"] == approx(112_010 / 364_980)
    roa = m(body, "piotroski_delta_roa", "AAPL", AAPL_FY25)["details"]
    assert roa["measure"] == approx(112_010 / 364_980)
    assert roa["compared_with"] == approx(93_736 / 352_583)

    f = m(body, "piotroski_f", "AAPL", AAPL_FY25)
    assert f["status"] == "ok"
    assert f["value"] == 8
    assert f["details"]["zone"] == "strong"
    assert m(body, "piotroski_f", "AAPL", AAPL_FY26)["value"] == 9


def test_beneish_m_matches_a_hand_computation_and_names_its_zone() -> None:
    body = post()

    # FY2026 against FY2025:
    # DSRI = (43,817 / 478,834) / (39,777 / 416,161)                     = 0.9574
    # GMI  = (195,201 / 416,161) / (233,602 / 478,834)                   = 0.9615
    # AQI  = (1 - (173,857 + 52,084) / 404,548) / (1 - (147,957 + 49,834) / 359,241) = 0.9824
    # SGI  = 478,834 / 416,161                                           = 1.1506
    # DEPI = (11,698 / (11,698 + 49,834)) / (13,423 / (13,423 + 52,084)) = 0.9278
    # SGAI = (29,774 / 478,834) / (27,601 / 416,161)                     = 0.9375
    # TATA = (132,175 - 145,097) / 404,548                               = -0.0319
    # LVGI = ((169,915 + 68,208) / 404,548) / ((165,631 + 78,328) / 359,241) = 0.8668
    # M = -4.84 + 0.920·DSRI + 0.528·GMI + 0.404·AQI + 0.892·SGI + 0.115·DEPI
    #     - 0.172·SGAI + 4.679·TATA - 0.327·LVGI                        = -2.5158
    beneish = m(body, "beneish_m", "AAPL", AAPL_FY26)
    assert beneish["status"] == "ok"
    assert beneish["unit"] == "score"
    assert beneish["value"] == approx(-2.515793, abs=1e-5)
    details = beneish["details"]
    assert details["zone"] == "unlikely"
    for index, expected in {
        "dsri": 0.957386,
        "gmi": 0.961455,
        "aqi": 0.982373,
        "sgi": 1.150598,
        "depi": 0.927788,
        "sgai": 0.937538,
        "tata": -0.031942,
        "lvgi": 0.866763,
    }.items():
        assert details[index] == approx(expected, abs=1e-5), index


def test_dupont_components_multiply_back_to_roe_every_year() -> None:
    body = post({"companies": [{"ticker": "AAPL"}, {"ticker": "MSFT"}], "years": 5})

    # FY2026: tax burden = 132,175 / 159,237; interest burden = 159,237 / 158,063 (EBIT).
    assert m(body, "dupont_tax_burden", "AAPL", AAPL_FY26)["value"] == approx(0.830052, rel=1e-6)
    assert m(body, "dupont_interest_burden", "AAPL", AAPL_FY26)["value"] == approx(1.007427, rel=1e-6)
    assert m(body, "dupont_tax_burden", "AAPL", AAPL_FY26)["unit"] == "ratio"
    for company in body["companies"]:
        for p in company["periods"]:
            v = {k: m(body, k, company["ticker"], p["id"])["value"] for k in (
                "return_on_equity", "net_margin", "asset_turnover", "equity_multiplier",
                "dupont_tax_burden", "dupont_interest_burden", "operating_margin",
            )}
            assert v["net_margin"] * v["asset_turnover"] * v["equity_multiplier"] == approx(v["return_on_equity"])
            five = (
                v["dupont_tax_burden"] * v["dupont_interest_burden"] * v["operating_margin"]
                * v["asset_turnover"] * v["equity_multiplier"]
            )
            assert five == approx(v["return_on_equity"])
