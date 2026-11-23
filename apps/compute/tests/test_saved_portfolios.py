"""Saved portfolios (P4): CRUD scoped to the signed-in user, and their metrics."""

from __future__ import annotations

import pytest

from data_fixtures import FixtureAdapter, price_frame, serving
from tests.auth_helpers import bearer, sign_in
from tests.test_portfolio import RISK_METRICS

BASE = "/api/compute/portfolios"

HOLDINGS = [
    {"ticker": "DEMO-A", "quantity": 10, "cost_price": 95.5, "currency": "USD"},
    {"ticker": "DEMO-B", "quantity": 2.5, "cost_price": 40, "currency": "USD"},
]
ANALYSIS = {"benchmark": "DEMO-MKT", "start": "2021-01-01", "end": "2025-12-31"}


@pytest.fixture
def alice(client):
    return bearer(sign_in(client, "sub-alice", email="alice@example.test"))


@pytest.fixture
def bob(client):
    return bearer(sign_in(client, "sub-bob", email="bob@example.test"))


def create(client, headers, name="Retirement", holdings=HOLDINGS):
    response = client.post(BASE, json={"name": name, "holdings": holdings}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_a_created_portfolio_reads_back_with_its_holdings_in_order(client, alice):
    created = create(client, alice)

    got = client.get(f"{BASE}/{created['id']}", headers=alice)

    assert got.status_code == 200
    body = got.json()
    assert body["name"] == "Retirement"
    assert body["holdings"] == HOLDINGS
    assert body == created


def test_the_list_shows_the_users_portfolios_oldest_first(client, alice):
    first = create(client, alice, name="Retirement")
    second = create(client, alice, name="Trading")

    listed = client.get(BASE, headers=alice).json()

    assert [(p["id"], p["name"]) for p in listed] == [(first["id"], "Retirement"), (second["id"], "Trading")]


def test_a_portfolio_can_be_renamed_and_its_holdings_replaced(client, alice):
    created = create(client, alice)
    new_holdings = [{"ticker": "DEMO-E", "quantity": 3, "cost_price": 20, "currency": "EUR"}]

    updated = client.put(
        f"{BASE}/{created['id']}", json={"name": "Pension", "holdings": new_holdings}, headers=alice
    )

    assert updated.status_code == 200, updated.text
    got = client.get(f"{BASE}/{created['id']}", headers=alice).json()
    assert got["name"] == "Pension"
    assert got["holdings"] == new_holdings
    assert got["updated_at"] > created["updated_at"]


def test_a_deleted_portfolio_is_gone(client, alice):
    kept = create(client, alice, name="Kept")
    deleted = create(client, alice, name="Deleted")

    assert client.delete(f"{BASE}/{deleted['id']}", headers=alice).status_code == 204

    assert client.get(f"{BASE}/{deleted['id']}", headers=alice).status_code == 404
    assert [p["id"] for p in client.get(BASE, headers=alice).json()] == [kept["id"]]


def test_one_user_can_never_read_or_modify_another_users_portfolios(client, alice, bob):
    alices = create(client, alice, name="Alice's")
    url = f"{BASE}/{alices['id']}"
    replacement = {"name": "Hijacked", "holdings": [{"ticker": "DEMO-F", "quantity": 1, "cost_price": 1}]}

    assert client.get(BASE, headers=bob).json() == []
    responses = {
        "read": client.get(url, headers=bob),
        "update": client.put(url, json=replacement, headers=bob),
        "delete": client.delete(url, headers=bob),
        "metrics": client.post(f"{url}/metrics", json=ANALYSIS, headers=bob),
    }

    # Someone else's portfolio looks exactly like one that does not exist.
    assert {action: r.status_code for action, r in responses.items()} == dict.fromkeys(responses, 404)
    assert all(r.json()["error"]["code"] == "not_found" for r in responses.values())
    assert client.get(url, headers=alice).json() == alices


def test_signed_out_callers_get_401_from_every_portfolio_endpoint(client, alice):
    url = f"{BASE}/{create(client, alice)['id']}"
    body = {"name": "X", "holdings": HOLDINGS}

    statuses = [
        client.get(BASE).status_code,
        client.post(BASE, json=body).status_code,
        client.get(url).status_code,
        client.put(url, json=body).status_code,
        client.delete(url).status_code,
        client.post(f"{url}/metrics", json=ANALYSIS).status_code,
    ]

    assert statuses == [401] * 6


def test_invalid_holdings_are_reported_on_their_fields(client, alice):
    response = client.post(
        BASE,
        json={
            "name": "  ",
            "holdings": [
                {"ticker": "DEMO-A", "quantity": 0, "cost_price": -1, "currency": "dollars"},
                {"ticker": "", "quantity": "ten", "cost_price": 5},
            ],
        },
        headers=alice,
    )

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == {
        "name": "Enter a name.",
        "holdings.0.quantity": "Enter a quantity greater than 0.",
        "holdings.0.cost_price": "Enter a cost price of 0 or more.",
        "holdings.0.currency": "Enter a 3-letter currency code, like USD.",
        "holdings.1.ticker": "Enter a ticker.",
        "holdings.1.quantity": "Enter a number.",
    }


def test_tickers_and_currencies_are_normalized_and_duplicates_rejected(client, alice):
    saved = create(client, alice, holdings=[{"ticker": " demo-a ", "quantity": 1, "cost_price": 1, "currency": "usd"}])
    duplicate = client.post(
        BASE,
        json={"name": "Dup", "holdings": [{"ticker": "DEMO-A", "quantity": 1, "cost_price": 1}] * 2},
        headers=alice,
    )

    assert saved["holdings"] == [{"ticker": "DEMO-A", "quantity": 1, "cost_price": 1, "currency": "USD"}]
    assert duplicate.json()["error"]["fields"] == {"holdings": "Each ticker can only be listed once."}


# --- Performance and risk of a saved portfolio -------------------------------------------------


def metrics(client, headers, portfolio, **analysis):
    response = client.post(f"{BASE}/{portfolio['id']}/metrics", json={**ANALYSIS, **analysis}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def points(body, series_id):
    result = body["series"][series_id]
    assert result["status"] == "ok", result
    return [(p["x"], p["y"]) for p in result["points"]]


def value(body, metric_id):
    result = body["metrics"][metric_id]
    assert result["status"] == "ok", result
    return result["value"]


def test_a_saved_portfolio_is_valued_buy_and_hold_with_dividends_reinvested(client, alice):
    # AAA: 100, 110, 99, 99 with a 1.98 dividend on the last day (a +2% day). BBB: 50, 49, 49.98, 52.479.
    frames = {
        "AAA": price_frame("2024-01-01", [100.0, 110.0, 99.0, 99.0], dividends={3: 1.98}),
        "BBB": price_frame("2024-01-01", [50.0, 49.0, 49.98, 52.479]),
    }
    portfolio = create(
        client,
        alice,
        holdings=[
            {"ticker": "AAA", "quantity": 2, "cost_price": 90, "currency": "USD"},
            {"ticker": "BBB", "quantity": 4, "cost_price": 55, "currency": "USD"},
        ],
    )

    with serving(FixtureAdapter(frames), on=client.app):
        body = metrics(client, alice, portfolio, benchmark="BBB", start="2024-01-01", end="2024-01-31")

    # Both holdings start at 200. AAA's value: 200, 220, 198, 198 * 1.02 = 201.96.
    # BBB's value: 200, 196, 199.92, 209.916. Total: 400, 416, 397.92, 411.876. No daily rebalancing.
    got = points(body, "cumulative_return:portfolio")
    assert [x for x, _ in got] == ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]
    assert [y for _, y in got] == pytest.approx([0.0, 0.04, -0.0052, 0.02969], abs=1e-12)
    # Holdings today: 2 x 99 + 4 x 52.479 = 407.916, bought for 2 x 90 + 4 x 55 = 400.
    assert value(body, "market_value:portfolio") == pytest.approx(407.916)
    assert value(body, "cost_basis:portfolio") == pytest.approx(400.0)
    assert value(body, "unrealized_pnl:portfolio") == pytest.approx(7.916)
    assert value(body, "unrealized_return:portfolio") == pytest.approx(7.916 / 400)
    assert body["metrics"]["market_value:portfolio"]["unit"] == "money"
    assert body["metrics"]["market_value:portfolio"]["details"] == {"currency": "USD"}
    assert body["source"]["id"] == "fixture"
    assert body["tool"] == "portfolio"


@pytest.mark.parametrize("ticker", ["DEMO-B", "DEMO-D"])
def test_a_saved_portfolio_of_one_ticker_has_the_same_risk_metrics_as_p3(client, alice, ticker):
    portfolio = create(client, alice, holdings=[{"ticker": ticker, "quantity": 7, "cost_price": 10}])
    params = {"confidence": 0.99, "risk_free_rate": 0.02}

    body = metrics(client, alice, portfolio, **params)
    p3 = client.post("/api/compute/risk/metrics", json={"tickers": [ticker], **ANALYSIS, **params}).json()

    for name in RISK_METRICS:
        for who, p3_id in [("portfolio", ticker), ("benchmark", "DEMO-MKT")]:
            got, want = body["metrics"][f"{name}:{who}"], p3["metrics"][f"{name}:{p3_id}"]
            assert got["value"] == pytest.approx(want["value"], rel=1e-9), (name, who)
            assert got["details"] == want["details"]
    assert body["source"]["is_demo"] is True


def test_an_unknown_saved_ticker_is_reported_on_its_holding_row(client, alice):
    portfolio = create(
        client, alice, holdings=[*HOLDINGS, {"ticker": "DEMO-ZZ", "quantity": 1, "cost_price": 1, "currency": "USD"}]
    )

    response = client.post(f"{BASE}/{portfolio['id']}/metrics", json=ANALYSIS, headers=alice)

    assert response.status_code == 422
    assert list(response.json()["error"]["fields"]) == ["holdings.2.ticker"]


def test_holdings_in_more_than_one_currency_are_not_valued_until_fx_conversion_exists(client, alice):
    portfolio = create(
        client,
        alice,
        holdings=[
            {"ticker": "DEMO-A", "quantity": 1, "cost_price": 1, "currency": "USD"},
            {"ticker": "DEMO-B", "quantity": 1, "cost_price": 1, "currency": "EUR"},
        ],
    )

    response = client.post(f"{BASE}/{portfolio['id']}/metrics", json=ANALYSIS, headers=alice)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "mixed_currencies"
    assert "EUR, USD" in response.json()["error"]["message"]


def test_analysis_settings_are_validated_like_the_demo_portfolio(client, alice):
    portfolio = create(client, alice)

    response = client.post(
        f"{BASE}/{portfolio['id']}/metrics",
        json={"benchmark": "DEMO-MKT", "start": "2024-01-01", "end": "2023-01-01"},
        headers=alice,
    )

    assert response.json()["error"]["fields"] == {"end": "End date must be after the start date."}
