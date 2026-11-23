"""Time-weighted and money-weighted (IRR) returns of a saved portfolio (P4, story 52).

The expected numbers are worked by hand in each test's comments.
"""

from __future__ import annotations

import pandas as pd
import pytest

from data_fixtures import FixtureAdapter, price_frame, serving
from tests.auth_helpers import bearer, sign_in

BASE = "/api/compute/portfolios"
RANGE = {"start": "2023-01-01", "end": "2025-01-31"}

# Three closes exactly 365 days apart, so the IRR's year fractions are 0, 1 and 2.
DATES = ["2023-01-02", "2024-01-02", "2025-01-01"]


def yearly(closes: list[float], dividends: list[float] | None = None) -> pd.DataFrame:
    index = pd.DatetimeIndex(DATES, name="date")
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": 1000,
            "dividend": dividends or [0.0] * len(closes),
        },
        index=index,
    )


@pytest.fixture
def alice(client):
    return bearer(sign_in(client, "sub-alice", email="alice@example.test"))


@pytest.fixture
def bob(client):
    return bearer(sign_in(client, "sub-bob", email="bob@example.test"))


def new_portfolio(client, headers, holdings):
    response = client.post(BASE, json={"name": "Brokerage", "holdings": holdings}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def import_csv(client, headers, portfolio_id, csv):
    response = client.post(f"{BASE}/{portfolio_id}/transactions", json={"csv": csv}, headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()["errors"] == []


def returns(client, headers, portfolio_id, frames, body=RANGE):
    with serving(FixtureAdapter(frames), on=client.app):
        return client.post(f"{BASE}/{portfolio_id}/returns", json=body, headers=headers)


def holding(ticker, quantity, cost_price=100):
    return {"ticker": ticker, "quantity": quantity, "cost_price": cost_price, "currency": "USD"}


def test_a_large_deposit_before_a_rally_lifts_the_irr_but_not_the_time_weighted_return(client, alice):
    # 10 shares at 100 (worth 1000), the price halves to 50, then 100 more shares are
    # bought at 50 (5000 in) and the price doubles back to 100 (110 shares, worth 11000).
    # TWR: (50/100) x (100/50) - 1 = 0 (the manager's choices of what to hold did nothing).
    # IRR: -1000 - 5000/(1+r) + 11000/(1+r)^2 = 0, so 1/(1+r) = (5000 + sqrt(69e6)) / 22000
    # = 0.604846, r = 65.33% a year (the investor's own timing made money).
    portfolio_id = new_portfolio(client, alice, [holding("DEMO-A", 10)])
    import_csv(client, alice, portfolio_id, "date,ticker,side,quantity,price\n2024-01-02,DEMO-A,buy,100,50\n")

    response = returns(client, alice, portfolio_id, {"DEMO-A": yearly([100, 50, 100])})

    assert response.status_code == 200, response.text
    metrics = response.json()["metrics"]
    assert metrics["twr:portfolio"]["status"] == "ok"
    assert metrics["twr:portfolio"]["value"] == pytest.approx(0, abs=1e-12)
    assert metrics["twr_annualized:portfolio"]["value"] == pytest.approx(0, abs=1e-12)
    assert metrics["irr:portfolio"]["status"] == "ok"
    assert metrics["irr:portfolio"]["value"] == pytest.approx(0.653312, abs=1e-6)
    assert metrics["irr:portfolio"]["unit"] == "decimal"


def test_cash_flows_with_no_rate_of_return_give_missing_data_for_the_irr_only(client, alice):
    # 10 DEMO-A worth 1000 at the start; a year later all are sold at 200 (+2000 out);
    # a year after that 1 DEMO-B is bought at 1 with 1099 fees (1100 in), worth 1 at the end.
    # Flows: -1000, +2000, -1100 + 1 = -1099. -1000 + 2000x - 1099x^2 has no real root
    # (2000^2 - 4 x 1099 x 1000 < 0), so no rate makes them net to zero.
    # TWR still exists: (2000 / 1000) x (1 / 1100) - 1.
    portfolio_id = new_portfolio(client, alice, [holding("DEMO-A", 10)])
    import_csv(
        client,
        alice,
        portfolio_id,
        "date,ticker,side,quantity,price,fees\n2024-01-02,DEMO-A,sell,10,200,0\n2025-01-01,DEMO-B,buy,1,1,1099\n",
    )

    response = returns(
        client, alice, portfolio_id, {"DEMO-A": yearly([100, 200, 300]), "DEMO-B": yearly([1, 1, 1])}
    )

    assert response.status_code == 200, response.text
    metrics = response.json()["metrics"]
    assert metrics["irr:portfolio"]["status"] == "missing_data"
    assert "no rate" in metrics["irr:portfolio"]["reason"]
    assert metrics["twr:portfolio"]["value"] == pytest.approx(2 / 1100 - 1)


def test_without_transactions_both_returns_are_the_holdings_own_return(client, alice):
    # 4 shares from 100 to 121 over two years, no trades and no dividends:
    # TWR = 21%, and both annualize to 10% a year (1.1^2 = 1.21).
    portfolio_id = new_portfolio(client, alice, [holding("DEMO-A", 4)])

    response = returns(client, alice, portfolio_id, {"DEMO-A": yearly([100, 110, 121])})

    metrics = response.json()["metrics"]
    assert metrics["twr:portfolio"]["value"] == pytest.approx(0.21)
    assert metrics["twr_annualized:portfolio"]["value"] == pytest.approx(0.10)
    assert metrics["irr:portfolio"]["value"] == pytest.approx(0.10)


def test_dividends_count_as_money_paid_out(client, alice):
    # 1 share at 100 pays a 10 dividend in year 1 and stays at 100: +10% in year 1, 0% in year 2.
    # TWR = 1.1 x 1.0 - 1 = 10%. IRR: -100 + 10/(1+r) + 100/(1+r)^2 = 0 -> 1/(1+r) = 0.951249, r = 5.125%.
    portfolio_id = new_portfolio(client, alice, [holding("DEMO-A", 1)])

    response = returns(client, alice, portfolio_id, {"DEMO-A": yearly([100, 100, 100], [0, 10, 0])})

    metrics = response.json()["metrics"]
    assert metrics["twr:portfolio"]["value"] == pytest.approx(0.10)
    assert metrics["irr:portfolio"]["value"] == pytest.approx(0.051249, abs=1e-6)


def test_trades_before_the_range_are_part_of_the_starting_value(client, alice):
    # Bought 5 more DEMO-A in 2024; a range starting after that holds 15 from its first day.
    portfolio_id = new_portfolio(client, alice, [holding("DEMO-A", 10)])
    import_csv(client, alice, portfolio_id, "date,ticker,side,quantity,price\n2024-02-01,DEMO-A,buy,5,90\n")
    frames = {"DEMO-A": price_frame("2025-01-01", [100, 102, 105])}

    response = returns(client, alice, portfolio_id, frames, {"start": "2025-01-01", "end": "2025-01-31"})

    metrics = response.json()["metrics"]
    assert metrics["twr:portfolio"]["value"] == pytest.approx(0.05)
    assert metrics["twr:portfolio"]["details"]["start_value"] == pytest.approx(1500)
    assert metrics["twr:portfolio"]["details"]["end_value"] == pytest.approx(1575)


def test_holdings_edited_by_hand_below_the_traded_amount_give_missing_data(client, alice):
    # The import bought 100 DEMO-A in 2024, then the holding was edited down to 10 by hand,
    # so before that buy the portfolio would have held -90 shares.
    portfolio_id = new_portfolio(client, alice, [holding("DEMO-A", 10)])
    import_csv(client, alice, portfolio_id, "date,ticker,side,quantity,price\n2024-01-02,DEMO-A,buy,100,50\n")
    put = client.put(f"{BASE}/{portfolio_id}", json={"name": "Brokerage", "holdings": [holding("DEMO-A", 10)]}, headers=alice)
    assert put.status_code == 200

    response = returns(client, alice, portfolio_id, {"DEMO-A": yearly([100, 50, 100])})

    metrics = response.json()["metrics"]
    for metric_id in ("twr:portfolio", "twr_annualized:portfolio", "irr:portfolio"):
        assert metrics[metric_id]["status"] == "missing_data"
        assert "DEMO-A" in metrics[metric_id]["reason"]


def test_mixed_currencies_are_refused(client, alice):
    portfolio_id = new_portfolio(
        client, alice, [holding("DEMO-A", 1), {**holding("DEMO-B", 1), "currency": "EUR"}]
    )

    response = returns(client, alice, portfolio_id, {"DEMO-A": yearly([1, 1, 1]), "DEMO-B": yearly([1, 1, 1])})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "mixed_currencies"


def test_returns_are_private_to_the_owner(client, alice, bob):
    portfolio_id = new_portfolio(client, alice, [holding("DEMO-A", 1)])
    frames = {"DEMO-A": yearly([1, 1, 1])}

    assert returns(client, bob, portfolio_id, frames).status_code == 404
    assert returns(client, {}, portfolio_id, frames).status_code == 401


def test_the_end_must_be_after_the_start(client, alice):
    portfolio_id = new_portfolio(client, alice, [holding("DEMO-A", 1)])

    response = returns(client, alice, portfolio_id, {}, {"start": "2025-01-31", "end": "2025-01-01"})

    assert response.status_code == 422
    assert "end" in response.json()["error"]["fields"]
