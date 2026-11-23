"""Position P&L of a saved portfolio (P4, story 50): realized P&L by FIFO lots, per-position value and weight."""

from __future__ import annotations

import pytest

from data_fixtures import FixtureAdapter, price_frame, serving
from tests.auth_helpers import bearer, sign_in

BASE = "/api/compute/portfolios"


@pytest.fixture
def alice(client):
    return bearer(sign_in(client, "sub-alice", email="alice@example.test"))


def create(client, headers, holdings, name="Brokerage"):
    response = client.post(BASE, json={"name": name, "holdings": holdings}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def importing(client, headers, portfolio_id, csv):
    response = client.post(f"{BASE}/{portfolio_id}/transactions", json={"csv": csv}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def stored(client, headers, portfolio_id):
    return client.get(f"{BASE}/{portfolio_id}/transactions", headers=headers).json()


def holding(client, headers, portfolio_id, ticker):
    holdings = client.get(f"{BASE}/{portfolio_id}", headers=headers).json()["holdings"]
    return next(h for h in holdings if h["ticker"] == ticker)


OPENING = [
    {"ticker": "AAA", "quantity": 5, "cost_price": 80, "currency": "USD"},
    {"ticker": "CCC", "quantity": 2, "cost_price": 50, "currency": "USD"},
]

FIRST_IMPORT = """Date,Ticker,Side,Quantity,Price,Fees
2024-01-02,AAA,buy,10,100,2
2024-01-03,AAA,buy,10,120,0
2024-01-04,AAA,sell,12,130,3
2024-01-05,BBB,buy,4,50,0
2024-01-08,BBB,sell,4,45,1
"""

SECOND_IMPORT = """Date,Ticker,Side,Quantity,Price,Fees
2024-02-01,AAA,sell,5,140,0
"""


def test_realized_pnl_is_booked_first_in_first_out_across_imports(client, alice):
    portfolio_id = create(client, alice, OPENING)

    importing(client, alice, portfolio_id, FIRST_IMPORT)

    # AAA lots, oldest first: 5 @ 80 (entered by hand), 10 @ 100.2 (100 + 2 fee / 10), 10 @ 120.
    # Sell 12 @ 130 less 3 fee = 1,557 proceeds; FIFO cost 5 x 80 + 7 x 100.2 = 1,101.4; realized 455.6.
    # BBB: bought 4 @ 50 = 200, sold 4 @ 45 less 1 fee = 179; realized -21.
    assert [(t["ticker"], t["side"], t["realized_pnl"]) for t in stored(client, alice, portfolio_id)] == [
        ("AAA", "buy", None),
        ("AAA", "buy", None),
        ("AAA", "sell", pytest.approx(455.6)),
        ("BBB", "buy", None),
        ("BBB", "sell", pytest.approx(-21.0)),
    ]
    # Left: 3 @ 100.2 + 10 @ 120 = 1,500.6 for 13 units.
    aaa = holding(client, alice, portfolio_id, "AAA")
    assert (aaa["quantity"], aaa["cost_price"]) == (13, pytest.approx(1500.6 / 13))

    # Renaming (holdings unchanged) keeps the lots, so the next import still sells the oldest first.
    renamed = client.put(f"{BASE}/{portfolio_id}", json={"name": "Renamed", "holdings": [
        {"ticker": "CCC", "quantity": 2, "cost_price": 50, "currency": "USD"},
        aaa,
    ]}, headers=alice)
    assert renamed.status_code == 200, renamed.text
    importing(client, alice, portfolio_id, SECOND_IMPORT)

    # Sell 5 @ 140 = 700; FIFO cost 3 x 100.2 + 2 x 120 = 540.6; realized 159.4 (average cost would give 122.85).
    assert stored(client, alice, portfolio_id)[-1]["realized_pnl"] == pytest.approx(159.4)
    aaa = holding(client, alice, portfolio_id, "AAA")
    assert (aaa["quantity"], aaa["cost_price"]) == (8, pytest.approx(120.0))


def test_a_hand_edited_holding_starts_again_as_one_lot_and_keeps_its_booked_realized_pnl(client, alice):
    portfolio_id = create(client, alice, OPENING)
    importing(client, alice, portfolio_id, FIRST_IMPORT)

    # The user corrects AAA by hand to 10 units at 110: its lot history no longer applies.
    edited = client.put(f"{BASE}/{portfolio_id}", json={"name": "Brokerage", "holdings": [
        {"ticker": "AAA", "quantity": 10, "cost_price": 110, "currency": "USD"},
        {"ticker": "CCC", "quantity": 2, "cost_price": 50, "currency": "USD"},
    ]}, headers=alice)
    assert edited.status_code == 200, edited.text
    importing(client, alice, portfolio_id, SECOND_IMPORT)

    realized = [t["realized_pnl"] for t in stored(client, alice, portfolio_id) if t["side"] == "sell"]
    # Earlier sells keep what they booked; the new sell uses the hand-entered cost: 5 x (140 - 110) = 150.
    assert realized == [pytest.approx(455.6), pytest.approx(-21.0), pytest.approx(150.0)]
    aaa = holding(client, alice, portfolio_id, "AAA")
    assert (aaa["quantity"], aaa["cost_price"]) == (5, pytest.approx(110.0))


def metrics(client, headers, portfolio_id, frames, benchmark):
    with serving(FixtureAdapter(frames), on=client.app):
        response = client.post(
            f"{BASE}/{portfolio_id}/metrics",
            json={"benchmark": benchmark, "start": "2024-03-01", "end": "2024-03-31"},
            headers=headers,
        )
    assert response.status_code == 200, response.text
    return response.json()["metrics"]


POSITION_METRICS = ["quantity", "cost_basis", "market_value", "weight", "unrealized_pnl", "realized_pnl"]


def positions(body):
    """``{ticker: (quantity, cost basis, market value, weight, unrealized, realized)}`` in the envelope's order."""
    tickers = [key.split(":", 1)[1] for key in body if key.startswith("quantity:")]
    out = {}
    for ticker in tickers:
        results = [body[f"{name}:{ticker}"] for name in POSITION_METRICS]
        assert all(r["status"] == "ok" for r in results), results
        out[ticker] = tuple(r["value"] for r in results)
    return out


def test_each_position_shows_value_weight_and_unrealized_and_realized_pnl(client, alice):
    portfolio_id = create(client, alice, OPENING)
    importing(client, alice, portfolio_id, FIRST_IMPORT)
    importing(client, alice, portfolio_id, SECOND_IMPORT)
    frames = {"AAA": price_frame("2024-03-01", [140.0, 150.0]), "CCC": price_frame("2024-03-01", [380.0, 400.0])}

    body = metrics(client, alice, portfolio_id, frames, benchmark="CCC")

    # AAA: 8 left @ 120 = 960, worth 8 x 150 = 1,200; realized 455.6 + 159.4 = 615.
    # CCC: 2 @ 50 = 100, worth 2 x 400 = 800. BBB: sold out, realized -21. Total value 2,000.
    got = positions(body)
    assert list(got) == ["AAA", "CCC", "BBB"]
    assert got["AAA"] == pytest.approx((8, 960, 1200, 0.6, 240, 615))
    assert got["CCC"] == pytest.approx((2, 100, 800, 0.4, 700, 0))
    assert got["BBB"] == pytest.approx((0, 0, 0, 0, 0, -21))
    assert sum(body[f"weight:{t}"]["value"] for t in got) == pytest.approx(1.0)
    for name in ["cost_basis", "market_value", "unrealized_pnl", "realized_pnl"]:
        total = body[f"{name}:portfolio"]["value"]
        assert total == pytest.approx(sum(body[f"{name}:{t}"]["value"] for t in got)), name
    assert body["realized_pnl:portfolio"]["value"] == pytest.approx(594.0)
    assert body["realized_pnl:portfolio"]["details"] == {"currency": "USD"}
    assert body["weight:AAA"]["unit"] == "decimal"
    assert body["market_value:AAA"]["unit"] == "money"


def test_without_imported_sells_realized_pnl_is_zero(client, alice):
    portfolio_id = create(client, alice, OPENING)
    frames = {"AAA": price_frame("2024-03-01", [100.0, 100.0]), "CCC": price_frame("2024-03-01", [50.0, 50.0])}

    body = metrics(client, alice, portfolio_id, frames, benchmark="CCC")

    assert body["realized_pnl:portfolio"]["value"] == 0
    assert positions(body)["AAA"] == pytest.approx((5, 400, 500, 500 / 600, 100, 0))


def test_realized_pnl_in_another_currency_is_not_added_to_the_total(client, alice):
    portfolio_id = create(client, alice, OPENING)
    importing(
        client,
        alice,
        portfolio_id,
        "Date,Ticker,Side,Quantity,Price,Currency\n2024-01-02,EEE,buy,1,10,EUR\n2024-01-03,EEE,sell,1,12,EUR\n",
    )
    frames = {"AAA": price_frame("2024-03-01", [100.0, 100.0]), "CCC": price_frame("2024-03-01", [50.0, 50.0])}

    body = metrics(client, alice, portfolio_id, frames, benchmark="CCC")

    assert body["realized_pnl:EEE"]["value"] == pytest.approx(2.0)
    assert body["realized_pnl:EEE"]["details"] == {"currency": "EUR"}
    assert body["realized_pnl:portfolio"]["status"] == "missing_data"
    assert "EUR" in body["realized_pnl:portfolio"]["reason"]
    assert body["market_value:portfolio"]["status"] == "ok"
