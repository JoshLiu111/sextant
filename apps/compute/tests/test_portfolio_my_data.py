"""My Portfolio on My data: the demo and saved portfolios priced by the user's own Tiingo key.

Tiingo is ``FakeTiingo`` (tests/tiingo_fixtures.py) answering from the recorded
responses; the data service is the real one (Postgres per-user cache included).
Split-adjusted, AAPL goes 100 -> 120 -> 108 -> 130 (max drawdown 10%, +30% overall)
and ends at 130; MSFT ends at 402.
"""

from __future__ import annotations

import psycopg
import pytest

from tests.test_risk_my_data import ALICE_KEY, BOB_KEY, tiingo, user_with_key  # noqa: F401 (fixture)

DEMO = "/api/compute/portfolio/metrics"
SAVED = "/api/compute/portfolios"
RANGE = {"start": "2024-01-01", "end": "2024-12-31"}
MY_DATA = {"benchmark": "SPY", **RANGE, "source": "tiingo"}
HOLDINGS = [
    {"ticker": "AAPL", "quantity": 10, "cost_price": 90, "currency": "USD"},
    {"ticker": "MSFT", "quantity": 5, "cost_price": 400, "currency": "USD"},
]


@pytest.fixture
def alice(client, tiingo):  # noqa: F811
    return user_with_key(client, "alice", ALICE_KEY)


def demo_portfolio(client, headers, holdings, **changes):
    return client.post(DEMO, json={"holdings": holdings, **MY_DATA, **changes}, headers=headers)


def saved_portfolio(client, headers, holdings=HOLDINGS) -> str:
    response = client.post(SAVED, json={"name": "Brokerage", "holdings": holdings}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_the_demo_portfolio_computes_on_tiingo_prices_against_a_real_benchmark(client, alice):
    response = demo_portfolio(client, alice, [{"ticker": "AAPL", "weight": 1}])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == {"id": "tiingo", "name": "Tiingo", "is_demo": False}
    assert body["meta"]["parameters"]["source"] == "tiingo"
    assert body["meta"]["data_cutoff"] == "2024-02-12"
    assert body["metrics"]["max_drawdown:portfolio"]["value"] == pytest.approx(0.10)
    assert body["series"]["cumulative_return:portfolio"]["points"][-1]["y"] == pytest.approx(0.30)
    assert body["metrics"]["beta:benchmark"]["value"] == pytest.approx(1.0)


def test_a_saved_portfolio_values_its_positions_at_tiingo_closes(client, alice):
    portfolio_id = saved_portfolio(client, alice)

    response = client.post(f"{SAVED}/{portfolio_id}/metrics", json=MY_DATA, headers=alice)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"]["id"] == "tiingo"
    assert body["metrics"]["market_value:AAPL"]["value"] == pytest.approx(1300)
    assert body["metrics"]["market_value:MSFT"]["value"] == pytest.approx(2010)
    assert body["metrics"]["market_value:portfolio"]["value"] == pytest.approx(3310)
    assert body["metrics"]["annualized_volatility:portfolio"]["status"] == "ok"


def test_a_saved_portfolios_returns_compute_on_tiingo_prices(client, alice):
    portfolio_id = saved_portfolio(client, alice, [HOLDINGS[0]])

    response = client.post(f"{SAVED}/{portfolio_id}/returns", json={**RANGE, "source": "tiingo"}, headers=alice)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"]["id"] == "tiingo"
    assert body["metrics"]["twr:portfolio"]["value"] == pytest.approx(0.30)


def test_demo_tickers_are_rejected_on_my_data_without_asking_tiingo(client, tiingo, alice):  # noqa: F811
    demo = demo_portfolio(
        client, alice, [{"ticker": "AAPL", "weight": 0.5}, {"ticker": "DEMO-A", "weight": 0.5}], benchmark="DEMO-MKT"
    )

    assert demo.status_code == 422
    fields = demo.json()["error"]["fields"]
    assert set(fields) == {"holdings.1.ticker", "benchmark"}
    assert "DEMO-A is a demo ticker" in fields["holdings.1.ticker"]
    assert "Demo data" in fields["holdings.1.ticker"]

    portfolio_id = saved_portfolio(
        client, alice, [{"ticker": "DEMO-A", "quantity": 1, "cost_price": 1, "currency": "USD"}]
    )
    saved = client.post(f"{SAVED}/{portfolio_id}/metrics", json=MY_DATA, headers=alice)
    returns = client.post(f"{SAVED}/{portfolio_id}/returns", json={**RANGE, "source": "tiingo"}, headers=alice)
    for response in (saved, returns):
        assert response.status_code == 422
        assert "DEMO-A is a demo ticker" in response.json()["error"]["message"]
    assert tiingo.price_requests == {}


def test_an_unknown_real_ticker_is_an_error_on_its_holding(client, alice):
    response = demo_portfolio(client, alice, [{"ticker": "AAPL", "weight": 0.5}, {"ticker": "ZZZZ", "weight": 0.5}])

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == {"holdings.1.ticker": "Tiingo has no ticker ZZZZ."}


def test_my_data_portfolio_prices_are_cached_per_user(client, tiingo, alice, db_url):  # noqa: F811
    bob = user_with_key(client, "bob", BOB_KEY)
    holdings = [{"ticker": "AAPL", "weight": 0.5}, {"ticker": "MSFT", "weight": 0.5}]

    assert demo_portfolio(client, alice, holdings).status_code == 200
    portfolio_id = saved_portfolio(client, alice)
    assert client.post(f"{SAVED}/{portfolio_id}/metrics", json=MY_DATA, headers=alice).status_code == 200
    assert tiingo.price_requests[(ALICE_KEY, "aapl")] == 1  # the saved portfolio reused Alice's cached prices

    assert demo_portfolio(client, bob, holdings).status_code == 200
    assert tiingo.price_requests[(BOB_KEY, "aapl")] == 1

    visitor = demo_portfolio(client, None, holdings)
    assert visitor.status_code == 403
    assert visitor.json()["error"]["code"] == "key_required"

    assert len(client.app.state.data_service.shared_cache) == 0
    with psycopg.connect(db_url) as conn:
        owners = conn.execute("SELECT DISTINCT u.email FROM user_data_cache c JOIN users u ON u.id = c.user_id")
        assert sorted(email for (email,) in owners) == ["alice@example.test", "bob@example.test"]
