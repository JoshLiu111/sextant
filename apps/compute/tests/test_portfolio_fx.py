"""Reporting currency (P4, story 51): holdings in other currencies are converted at
each date's Frankfurter rate (recorded responses), never today's rate.

EUR -> USD rates used below, as recorded (tests/fixtures/frankfurter):
2023-01-02 1.0671, 2024-01-02 1.102, 2024-01-03 1.0953, 2024-01-15 1.0958,
2024-02-01 1.0823, 2024-03-01 1.0824, 2024-03-04 1.084, 2025-01-01 1.0415.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from data_fixtures import FixtureAdapter, price_frame, serving
from frankfurter_fixtures import RecordedFrankfurter, recorded_adapter
from tests.auth_helpers import bearer, sign_in

BASE = "/api/compute/portfolios"
MARCH = {"start": "2024-03-01", "end": "2024-03-31"}
NOT_PUBLISHED = "Frankfurter has no exchange rates for XYZ."


@pytest.fixture
def alice(client, monkeypatch):
    # Holdings entered by hand are dated the day they are saved; pin that day.
    monkeypatch.setattr("sextant_compute.portfolio.saved.today", lambda: date(2024, 1, 15))
    return bearer(sign_in(client, "sub-alice", email="alice@example.test"))


def create(client, headers, holdings):
    response = client.post(BASE, json={"name": "Brokerage", "holdings": holdings}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def importing(client, headers, portfolio_id, csv):
    response = client.post(f"{BASE}/{portfolio_id}/transactions", json={"csv": csv}, headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()["errors"] == []


def post(client, headers, path, frames, body, frankfurter=None):
    fx = recorded_adapter(frankfurter or RecordedFrankfurter())
    with serving(FixtureAdapter(frames), on=client.app, also={"frankfurter": fx}):
        response = client.post(f"{BASE}/{path}", json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def held(ticker, quantity, cost_price, currency):
    return {"ticker": ticker, "quantity": quantity, "cost_price": cost_price, "currency": currency}


def test_holdings_in_other_currencies_are_valued_at_each_dates_rate(client, alice):
    portfolio_id = create(client, alice, [held("AAA", 10, 100, "USD"), held("EEE", 4, 50, "EUR")])
    frames = {"AAA": price_frame("2024-03-01", [100.0, 110.0]), "EEE": price_frame("2024-03-01", [60.0, 70.0])}

    body = post(client, alice, f"{portfolio_id}/metrics", frames, {**MARCH, "benchmark": "AAA", "reporting_currency": "USD"})
    m = body["metrics"]

    # EEE, held 4 @ 50 EUR, entered on 2024-01-15: cost 200 EUR x 1.0958 = 219.16 USD.
    # Worth 4 x 70 EUR on 2024-03-04 x 1.084 = 303.52 USD. AAA: cost 1,000, worth 1,100.
    assert m["cost_basis:EEE"]["value"] == pytest.approx(219.16)
    assert m["market_value:EEE"]["value"] == pytest.approx(303.52)
    assert m["unrealized_pnl:EEE"]["value"] == pytest.approx(84.36)
    assert m["market_value:EEE"]["details"]["currency"] == "USD"
    assert m["market_value:portfolio"]["value"] == pytest.approx(1403.52)
    assert m["cost_basis:portfolio"]["value"] == pytest.approx(1219.16)
    assert m["weight:EEE"]["value"] == pytest.approx(303.52 / 1403.52)
    # The value series converts each day at that day's rate:
    # 2024-03-01: 1,000 + 4 x 60 x 1.0824 = 1,259.776; 2024-03-04: 1,403.52.
    last = body["series"]["cumulative_return:portfolio"]["points"][-1]["y"]
    assert last == pytest.approx(1403.52 / 1259.776 - 1)
    assert body["meta"]["parameters"]["reporting_currency"] == "USD"


def test_imported_lots_and_realized_pnl_convert_at_their_trade_dates(client, alice):
    portfolio_id = create(client, alice, [held("AAA", 10, 100, "USD")])
    importing(client, alice, portfolio_id, (
        "Date,Ticker,Side,Quantity,Price,Currency\n"
        "2024-01-02,EEE,buy,4,50,EUR\n"
        "2024-02-01,EEE,buy,2,55,EUR\n"
        "2024-03-01,EEE,sell,1,60,EUR\n"
    ))
    frames = {"AAA": price_frame("2024-03-01", [100.0, 100.0]), "EEE": price_frame("2024-03-01", [60.0, 60.0])}

    m = post(client, alice, f"{portfolio_id}/metrics", frames, {**MARCH, "benchmark": "AAA", "reporting_currency": "USD"})[
        "metrics"
    ]

    # Open lots: 3 @ 50 bought 2024-01-02 (x 1.102) and 2 @ 55 bought 2024-02-01 (x 1.0823):
    # 165.3 + 119.053 = 284.353 USD. The sell closed 1 @ 50 for 60: 10 EUR on 2024-03-01 x 1.0824.
    assert m["cost_basis:EEE"]["value"] == pytest.approx(284.353)
    assert m["realized_pnl:EEE"]["value"] == pytest.approx(10.824)
    assert m["realized_pnl:portfolio"]["value"] == pytest.approx(10.824)
    assert m["realized_pnl:portfolio"]["details"] == {"currency": "USD"}


def test_the_reporting_currency_defaults_to_the_first_holdings_currency(client, alice):
    portfolio_id = create(client, alice, [held("EEE", 1, 50, "EUR"), held("AAA", 1, 100, "USD")])
    frames = {"AAA": price_frame("2024-03-01", [100.0, 100.0]), "EEE": price_frame("2024-03-01", [60.0, 60.0])}

    body = post(client, alice, f"{portfolio_id}/metrics", frames, {**MARCH, "benchmark": "AAA"})

    assert body["metrics"]["market_value:EEE"]["value"] == pytest.approx(60.0)
    assert body["metrics"]["market_value:portfolio"]["details"] == {"currency": "EUR"}
    assert body["meta"]["parameters"]["reporting_currency"] == "EUR"


def test_a_currency_frankfurter_does_not_publish_is_missing_data_with_the_reason(client, alice):
    portfolio_id = create(client, alice, [held("AAA", 10, 100, "USD"), held("XXX", 1, 10, "XYZ")])
    frames = {"AAA": price_frame("2024-03-01", [100.0, 110.0]), "XXX": price_frame("2024-03-01", [10.0, 11.0])}

    body = post(client, alice, f"{portfolio_id}/metrics", frames, {**MARCH, "benchmark": "AAA", "reporting_currency": "USD"})
    m = body["metrics"]

    assert m["market_value:AAA"]["value"] == pytest.approx(1100)
    for key in ["market_value:XXX", "cost_basis:XXX", "weight:AAA", "market_value:portfolio", "annualized_volatility:portfolio"]:
        assert m[key]["status"] == "missing_data", key
        assert NOT_PUBLISHED in m[key]["reason"], key
    assert body["series"]["cumulative_return:portfolio"]["status"] == "missing_data"
    assert m["max_drawdown:benchmark"]["status"] == "ok"


def yearly(closes):
    index = pd.DatetimeIndex(["2023-01-02", "2024-01-02", "2025-01-01"], name="date")
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes, "volume": 1000, "dividend": 0.0}, index=index
    )


def test_returns_convert_values_and_trades_at_each_dates_rate(client, alice):
    # 1 EEE held from the start, 1 more bought on 2024-01-02; the price stays 100 EUR.
    portfolio_id = create(client, alice, [held("EEE", 1, 100, "EUR")])
    importing(client, alice, portfolio_id, "Date,Ticker,Side,Quantity,Price,Currency\n2024-01-02,EEE,buy,1,100,EUR\n")
    body = {"start": "2023-01-01", "end": "2025-01-31", "reporting_currency": "USD"}

    m = post(client, alice, f"{portfolio_id}/returns", {"EEE": yearly([100.0, 100.0, 100.0])}, body)["metrics"]

    # In USD: 106.71 -> (220.4 with 110.2 paid in) -> 208.3. Held in EUR nothing moved,
    # so the time-weighted return is the euro's: 1.0415 / 1.0671 - 1.
    assert m["twr:portfolio"]["value"] == pytest.approx(1.0415 / 1.0671 - 1)
    assert m["twr:portfolio"]["details"]["start_value"] == pytest.approx(106.71)
    assert m["twr:portfolio"]["details"]["currency"] == "USD"
    # IRR: -106.71 at year 0, -110.2 at year 1, +208.3 at year 2.
    r = m["irr:portfolio"]["value"]
    assert -106.71 - 110.2 / (1 + r) + 208.3 / (1 + r) ** 2 == pytest.approx(0, abs=1e-6)


def test_returns_with_a_currency_frankfurter_does_not_publish_are_missing_data(client, alice):
    portfolio_id = create(client, alice, [held("XXX", 1, 100, "XYZ")])
    body = {"start": "2023-01-01", "end": "2025-01-31", "reporting_currency": "USD"}

    m = post(client, alice, f"{portfolio_id}/returns", {"XXX": yearly([100.0, 100.0, 100.0])}, body)["metrics"]

    for key in ["twr:portfolio", "twr_annualized:portfolio", "irr:portfolio"]:
        assert m[key]["status"] == "missing_data"
        assert NOT_PUBLISHED in m[key]["reason"]
