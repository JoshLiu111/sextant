"""FMP works wherever Tiingo does: My Portfolio (demo and saved portfolios, returns,
rebalancing, frontier) and the screener's price criteria on ``source: "fmp"``.

Risk & Performance on FMP is in ``test_risk_my_data_fmp.py``. The FMP fixtures
mirror the Tiingo ones after split adjustment (AAPL 100 -> 120 -> 108 -> 130,
MSFT ends at 402), so the expected numbers are the Tiingo tests' numbers.

For the screener, ``FakeFmp`` also serves the weekly Tiingo screener fixtures
(2025-11-14..2026-11-20) in FMP's shape: FMP's ``/full`` prices are
split-adjusted, which is Tiingo's ``adj*`` columns when no dividend is paid.
"""

from __future__ import annotations

import json

import pytest

from fmp_fixtures import FakeFmp
from sextant_compute.data.service import make_data_service
from sextant_compute.data.synthetic import SyntheticAdapter
from sextant_compute.keys.api import get_fmp
from tests.auth_helpers import bearer, sign_in
from tests.edgar_fixtures import edgar_adapter
from tiingo_fixtures import FIXTURES as TIINGO_DAILY

ALICE_FMP = "afmp111111111111111111111111111aaa"
TEST_KEY_SECRET = "test-provider-key-secret-not-for-production-0123456789"
RANGE = {"start": "2024-01-01", "end": "2024-12-31"}
MY_DATA = {"benchmark": "SPY", **RANGE, "source": "fmp"}
HOLDINGS = [
    {"ticker": "AAPL", "quantity": 10, "cost_price": 90, "currency": "USD"},
    {"ticker": "MSFT", "quantity": 5, "cost_price": 400, "currency": "USD"},
]
FMP = {"id": "fmp", "name": "FMP", "is_demo": False}


class ScreenerFakeFmp(FakeFmp):
    """``FakeFmp`` plus the Tiingo screener fixtures, converted to FMP's shape."""

    @staticmethod
    def _rows(dataset: str, symbol: str) -> list[dict]:
        rows = FakeFmp._rows(dataset, symbol)
        file = TIINGO_DAILY / f"{symbol.lower()}.json"
        if rows or dataset != "historical-price-eod" or not symbol or not file.exists():
            return rows
        tiingo = json.loads(file.read_text())
        return [
            {
                "symbol": symbol,
                "date": r["date"][:10],
                "open": r["adjOpen"],
                "high": r["adjHigh"],
                "low": r["adjLow"],
                "close": r["adjClose"],
                "volume": r["adjVolume"],
            }
            for r in reversed(tiingo)
        ]


@pytest.fixture
def fmp(client, monkeypatch) -> FakeFmp:
    monkeypatch.setenv("PROVIDER_KEY_SECRET", TEST_KEY_SECRET)
    monkeypatch.setenv("SCREENER_PRICES_AS_OF", "2026-11-20")
    fake = ScreenerFakeFmp({ALICE_FMP})
    adapter = fake.adapter()
    client.app.dependency_overrides[get_fmp] = lambda: adapter
    client.app.state.data_service = make_data_service(
        client.app.state.db, {"synthetic": SyntheticAdapter(), "sec_edgar": edgar_adapter(), "fmp": adapter}
    )
    return fake


@pytest.fixture
def alice(client, fmp) -> dict[str, str]:
    headers = bearer(sign_in(client, "sub-alice", email="alice@example.test"))
    saved = client.put("/api/compute/keys/fmp", json={"key": ALICE_FMP}, headers=headers)
    assert saved.status_code == 200, saved.text
    return headers


def saved_portfolio(client, headers, holdings=HOLDINGS) -> str:
    response = client.post("/api/compute/portfolios", json={"name": "Brokerage", "holdings": holdings}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_the_demo_portfolio_computes_on_fmp_prices(client, alice):
    holdings = [{"ticker": "AAPL", "weight": 1}]

    response = client.post("/api/compute/portfolio/metrics", json={"holdings": holdings, **MY_DATA}, headers=alice)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == FMP
    assert body["meta"]["data_cutoff"] == "2024-02-12"
    assert body["metrics"]["max_drawdown:portfolio"]["value"] == pytest.approx(0.10)
    # +30% on price, plus AAPL's two 0.24 dividends in the FMP fixture (Tiingo's has none).
    assert 0.30 < body["series"]["cumulative_return:portfolio"]["points"][-1]["y"] < 0.31


def test_a_saved_portfolio_values_its_positions_and_returns_at_fmp_closes(client, alice):
    portfolio_id = saved_portfolio(client, alice)

    metrics = client.post(f"/api/compute/portfolios/{portfolio_id}/metrics", json=MY_DATA, headers=alice)
    returns = client.post(f"/api/compute/portfolios/{portfolio_id}/returns", json={**RANGE, "source": "fmp"}, headers=alice)

    assert metrics.status_code == 200, metrics.text
    assert metrics.json()["source"] == FMP
    assert metrics.json()["metrics"]["market_value:AAPL"]["value"] == pytest.approx(1300)
    assert metrics.json()["metrics"]["market_value:MSFT"]["value"] == pytest.approx(2010)
    assert returns.status_code == 200, returns.text
    assert returns.json()["source"] == FMP


def test_demo_tickers_are_refused_on_fmp_without_asking_fmp(client, fmp, alice):
    holdings = [{"ticker": "AAPL", "weight": 0.5}, {"ticker": "DEMO-A", "weight": 0.5}]

    response = client.post("/api/compute/portfolio/metrics", json={"holdings": holdings, **MY_DATA}, headers=alice)

    assert response.status_code == 422
    assert "real tickers from FMP" in response.json()["error"]["fields"]["holdings.1.ticker"]
    assert not any("DEMO" in symbol for _, symbol in fmp.price_requests)


@pytest.mark.parametrize("view", ["rebalancing", "frontier"])
def test_rebalancing_and_frontier_run_on_fmp(client, alice, view):
    holdings = [{"ticker": "AAPL", "weight": 0.5}, {"ticker": "MSFT", "weight": 0.5}]

    response = client.post(f"/api/compute/portfolio/{view}", json={"holdings": holdings, **MY_DATA}, headers=alice)

    assert response.status_code == 200, response.text
    assert response.json()["source"] == FMP


def test_screener_price_criteria_run_on_fmp(client, alice):
    criteria = [
        {"metric": "revenue_growth", "op": "min", "value": 0.10},
        {"metric": "gross_margin", "op": "min", "value": 0.40},
        {"metric": "roe", "op": "min", "value": 0.15},
        {"metric": "change_52w", "op": "min", "value": 0.18},
    ]

    response = client.post(
        "/api/compute/screener/screen",
        json={"year": 2025, "criteria": criteria, "price_source": "fmp"},
        headers=alice,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    # Same as on Tiingo (test_screener_prices.py), AVGO's 4:1 split included.
    assert [r["ticker"] for r in body["rows"]] == ["AMZN", "GOOGL", "NVDA", "AVGO"]
    assert body["rows"][3]["values"]["change_52w"] == pytest.approx(0.2)
    assert body["price_source"] == FMP
    assert body["prices_as_of"] == "2026-11-20"


def test_screener_price_criteria_on_fmp_need_an_fmp_key(client, fmp):
    headers = bearer(sign_in(client, "sub-carol", email="carol@example.test"))
    criteria = [{"metric": "change_52w", "op": "min", "value": 0.18}]

    response = client.post(
        "/api/compute/screener/screen",
        json={"year": 2025, "criteria": criteria, "price_source": "fmp"},
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "key_required"
