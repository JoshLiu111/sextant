"""Importing transactions from CSV into a saved portfolio (P4, story 49)."""

from __future__ import annotations

import pytest

from tests.auth_helpers import bearer, sign_in

BASE = "/api/compute/portfolios"

BROKER_CSV = """Trade Date,Symbol,Action,Quantity,Price,Commission,Currency
2024-01-05,DEMO-A,Buy,10,100.00,1.00,USD
2024-02-01,DEMO-B,BUY,4,"1,250.50",0,USD
2024-03-01,DEMO-A,Sell,4,120,1,USD
"""


@pytest.fixture
def alice(client):
    return bearer(sign_in(client, "sub-alice", email="alice@example.test"))


@pytest.fixture
def bob(client):
    return bearer(sign_in(client, "sub-bob", email="bob@example.test"))


def new_portfolio(client, headers, holdings=None):
    holdings = holdings or [{"ticker": "DEMO-C", "quantity": 1, "cost_price": 50, "currency": "USD"}]
    response = client.post(BASE, json={"name": "Brokerage", "holdings": holdings}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def preview(client, headers, portfolio_id, csv, mapping=None):
    body = {"csv": csv} if mapping is None else {"csv": csv, "mapping": mapping}
    return client.post(f"{BASE}/{portfolio_id}/transactions/preview", json=body, headers=headers)


def test_the_preview_shows_the_first_rows_and_guesses_the_mapping_of_a_broker_export(client, alice):
    portfolio_id = new_portfolio(client, alice)

    response = preview(client, alice, portfolio_id, BROKER_CSV)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["columns"] == ["Trade Date", "Symbol", "Action", "Quantity", "Price", "Commission", "Currency"]
    assert body["sample"][0] == {"line": 2, "cells": ["2024-01-05", "DEMO-A", "Buy", "10", "100.00", "1.00", "USD"]}
    assert len(body["sample"]) == 3
    assert body["mapping"] == {
        "date": "Trade Date",
        "ticker": "Symbol",
        "side": "Action",
        "quantity": "Quantity",
        "price": "Price",
        "fees": "Commission",
        "currency": "Currency",
    }
    assert body["missing_fields"] == []
    assert body["errors"] == []
    assert [(t["line"], t["ticker"], t["side"], t["quantity"], t["price"]) for t in body["transactions"]] == [
        (2, "DEMO-A", "buy", 10, 100.0),
        (3, "DEMO-B", "buy", 4, 1250.5),
        (4, "DEMO-A", "sell", 4, 120.0),
    ]


def importing(client, headers, portfolio_id, csv, mapping=None):
    body = {"csv": csv} if mapping is None else {"csv": csv, "mapping": mapping}
    return client.post(f"{BASE}/{portfolio_id}/transactions", json=body, headers=headers)


BAD_ROWS_CSV = """Date,Ticker,Side,Quantity,Price,Fees
2024-01-05,DEMO-A,buy,10,100,0
2024-13-40,DEMO-A,buy,1,100,0
2024-01-06,DEMO-A,hold,1,100,0
2024-01-07,DEMO-A,buy,ten,100,0
2024-01-08,DEMO-A,buy,1,n/a,0

2024-01-09,DEMO-A,buy,1,100,free
2024-01-10,DEMO-A,sell,50,100,0
"""


def test_rows_with_bad_dates_sides_or_amounts_are_listed_by_line_and_not_imported(client, alice):
    portfolio_id = new_portfolio(client, alice)

    body = preview(client, alice, portfolio_id, BAD_ROWS_CSV).json()

    assert [(e["line"], e["field"]) for e in body["errors"]] == [
        (3, "date"),
        (4, "side"),
        (5, "quantity"),
        (6, "price"),
        (8, "fees"),
        (9, "quantity"),  # sells more than is held
    ]
    assert "hold" in body["errors"][1]["message"]
    assert [t["line"] for t in body["transactions"]] == [2]

    response = importing(client, alice, portfolio_id, BAD_ROWS_CSV)

    assert response.status_code == 201, response.text
    result = response.json()
    assert result["imported"] == 1
    assert [e["line"] for e in result["errors"]] == [3, 4, 5, 6, 8, 9]
    stored = client.get(f"{BASE}/{portfolio_id}/transactions", headers=alice).json()
    assert [(t["line"], t["ticker"], t["quantity"]) for t in stored] == [(2, "DEMO-A", 10)]


UNFAMILIAR_CSV = """When,What,Direction,How many,At,Money
05/01/2024,demo-e,S,2,30,EUR
"""


def test_the_user_maps_unfamiliar_columns_and_required_fields_must_be_mapped(client, alice):
    portfolio_id = new_portfolio(
        client, alice, [{"ticker": "DEMO-E", "quantity": 5, "cost_price": 20, "currency": "EUR"}]
    )

    guessed = preview(client, alice, portfolio_id, UNFAMILIAR_CSV).json()
    assert guessed["missing_fields"] == ["date", "ticker", "side", "quantity", "price"]
    assert guessed["holdings_after"] is None
    refused = importing(client, alice, portfolio_id, UNFAMILIAR_CSV)
    assert refused.status_code == 422
    assert set(refused.json()["error"]["fields"]) == {
        "mapping.date", "mapping.ticker", "mapping.side", "mapping.quantity", "mapping.price"
    }

    mapping = {
        "date": "When", "ticker": "What", "side": "Direction", "quantity": "How many", "price": "At",
        "currency": "Money",
    }
    mapped = preview(client, alice, portfolio_id, UNFAMILIAR_CSV, mapping).json()
    assert mapped["missing_fields"] == []
    assert mapped["transactions"] == [{
        "line": 2, "date": "2024-05-01", "ticker": "DEMO-E", "side": "sell", "quantity": 2, "price": 30,
        "fees": 0, "currency": "EUR",
    }]
    assert mapped["holdings_after"] == [{"ticker": "DEMO-E", "quantity": 3, "cost_price": 20, "currency": "EUR"}]

    wrong = preview(client, alice, portfolio_id, UNFAMILIAR_CSV, {**mapping, "fees": "Commission"})
    assert wrong.status_code == 422
    assert wrong.json()["error"]["fields"] == {"mapping.fees": 'The file has no column named "Commission".'}


def test_an_import_updates_the_holdings_at_average_cost_including_fees(client, alice):
    portfolio_id = new_portfolio(client, alice)

    response = importing(client, alice, portfolio_id, BROKER_CSV)

    assert response.status_code == 201, response.text
    assert response.json()["imported"] == 3
    # DEMO-A: bought 10 @ 100 + 1 fee (average 100.1), then sold 4; DEMO-B: 4 @ 1,250.50.
    expected = [
        {"ticker": "DEMO-C", "quantity": 1, "cost_price": 50, "currency": "USD"},
        {"ticker": "DEMO-A", "quantity": 6, "cost_price": pytest.approx(100.1), "currency": "USD"},
        {"ticker": "DEMO-B", "quantity": 4, "cost_price": 1250.5, "currency": "USD"},
    ]
    assert response.json()["portfolio"]["holdings"] == expected
    assert client.get(f"{BASE}/{portfolio_id}", headers=alice).json()["holdings"] == expected
    stored = client.get(f"{BASE}/{portfolio_id}/transactions", headers=alice).json()
    assert [(t["date"], t["ticker"], t["side"], t["fees"]) for t in stored] == [
        ("2024-01-05", "DEMO-A", "buy", 1),
        ("2024-02-01", "DEMO-B", "buy", 0),
        ("2024-03-01", "DEMO-A", "sell", 1),
    ]
    assert len({t["import_id"] for t in stored}) == 1


def test_a_preview_stores_nothing_and_a_refused_import_changes_nothing(client, alice):
    portfolio_id = new_portfolio(client, alice)
    before = client.get(f"{BASE}/{portfolio_id}", headers=alice).json()
    many = "Date,Ticker,Side,Quantity,Price\n" + "".join(
        f"2024-01-{i + 1:02d},TICK{i},buy,1,10\n" for i in range(25)
    )

    preview(client, alice, portfolio_id, many)
    refused = importing(client, alice, portfolio_id, many)

    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "too_many_holdings"
    assert client.get(f"{BASE}/{portfolio_id}", headers=alice).json() == before
    assert client.get(f"{BASE}/{portfolio_id}/transactions", headers=alice).json() == []


def test_an_import_with_no_good_rows_or_an_unreadable_file_is_refused(client, alice):
    portfolio_id = new_portfolio(client, alice)

    nothing = importing(client, alice, portfolio_id, "Date,Ticker,Side,Quantity,Price\nyesterday,DEMO-A,buy,1,1\n")
    empty = preview(client, alice, portfolio_id, "")
    header_only = preview(client, alice, portfolio_id, "Date,Ticker,Side,Quantity,Price\n")

    assert nothing.status_code == 422
    assert nothing.json()["error"]["code"] == "nothing_to_import"
    assert empty.status_code == 422
    assert "csv" in empty.json()["error"]["fields"]
    assert header_only.status_code == 422
    assert "no transactions" in header_only.json()["error"]["fields"]["csv"]


def test_one_user_can_never_preview_import_into_or_read_another_users_transactions(client, alice, bob):
    portfolio_id = new_portfolio(client, alice)
    importing(client, alice, portfolio_id, BROKER_CSV)
    before = client.get(f"{BASE}/{portfolio_id}", headers=alice).json()

    assert preview(client, bob, portfolio_id, BROKER_CSV).status_code == 404
    assert importing(client, bob, portfolio_id, BROKER_CSV).status_code == 404
    assert client.get(f"{BASE}/{portfolio_id}/transactions", headers=bob).status_code == 404
    assert client.get(f"{BASE}/{portfolio_id}", headers=alice).json() == before
    client.cookies.clear()
    assert client.post(f"{BASE}/{portfolio_id}/transactions/preview", json={"csv": BROKER_CSV}).status_code == 401
    assert client.post(f"{BASE}/{portfolio_id}/transactions", json={"csv": BROKER_CSV}).status_code == 401
    assert client.get(f"{BASE}/{portfolio_id}/transactions").status_code == 401


def test_deleting_a_portfolio_removes_its_transactions(client, alice):
    portfolio_id = new_portfolio(client, alice)
    importing(client, alice, portfolio_id, BROKER_CSV)

    assert client.delete(f"{BASE}/{portfolio_id}", headers=alice).status_code == 204

    assert client.get(f"{BASE}/{portfolio_id}/transactions", headers=alice).status_code == 404
