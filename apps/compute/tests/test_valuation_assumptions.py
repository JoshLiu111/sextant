"""Saved valuation assumptions: a signed-in user's named DCF/WACC inputs per ticker."""

from __future__ import annotations

from tests.auth_helpers import bearer, sign_in

PATH = "/api/compute/valuation/assumptions"
BULLISH = {
    "forecast_years": 7,
    "growth_rate": 0.12,
    "terminal_growth": 0.03,
    "discount_rate": None,
    "risk_free_rate": 0.04,
    "beta": 1.2,
    "equity_risk_premium": 0.055,
    "cost_of_equity": None,
    "cost_of_debt": 0.05,
    "tax_rate": 0.18,
    "debt_weight": None,
    "share_price": 410.0,
}


def headers(client, name: str = "alice") -> dict[str, str]:
    return bearer(sign_in(client, f"sub-{name}", email=f"{name}@example.test"))


def save(client, who, *, ticker="MSFT", name="Bullish", assumptions=BULLISH):
    return client.post(PATH, json={"ticker": ticker, "name": name, "assumptions": assumptions}, headers=who)


def test_a_saved_set_lists_with_every_input_for_its_ticker(client):
    alice = headers(client)

    saved = save(client, alice, ticker=" msft ")

    assert saved.status_code == 201, saved.text
    body = saved.json()
    assert (body["ticker"], body["name"], body["assumptions"]) == ("MSFT", "Bullish", BULLISH)
    listed = client.get(PATH, params={"ticker": "msft"}, headers=alice).json()
    assert [(s["id"], s["name"], s["assumptions"]) for s in listed] == [(body["id"], "Bullish", BULLISH)]


def test_the_list_is_per_ticker_and_in_saved_order(client):
    alice = headers(client)
    save(client, alice, name="Base")
    save(client, alice, name="Bear", assumptions={**BULLISH, "growth_rate": 0.0})
    save(client, alice, ticker="AAPL", name="Apple base")

    msft = client.get(PATH, params={"ticker": "MSFT"}, headers=alice).json()

    assert [s["name"] for s in msft] == ["Base", "Bear"]
    assert msft[1]["assumptions"]["growth_rate"] == 0.0


def test_saving_under_an_existing_name_replaces_that_set(client):
    alice = headers(client)
    first = save(client, alice).json()

    second = save(client, alice, assumptions={**BULLISH, "growth_rate": 0.2})

    assert second.status_code == 201
    listed = client.get(PATH, params={"ticker": "MSFT"}, headers=alice).json()
    assert [(s["id"], s["assumptions"]["growth_rate"]) for s in listed] == [(first["id"], 0.2)]


def test_a_saved_set_can_be_deleted(client):
    alice = headers(client)
    saved = save(client, alice).json()

    assert client.delete(f"{PATH}/{saved['id']}", headers=alice).status_code == 204

    assert client.get(PATH, params={"ticker": "MSFT"}, headers=alice).json() == []
    assert client.delete(f"{PATH}/{saved['id']}", headers=alice).status_code == 404


def test_one_user_never_sees_or_deletes_another_users_sets(client):
    alice, bob = headers(client, "alice"), headers(client, "bob")
    saved = save(client, alice).json()

    assert client.get(PATH, params={"ticker": "MSFT"}, headers=bob).json() == []
    assert client.delete(f"{PATH}/{saved['id']}", headers=bob).status_code == 404
    assert len(client.get(PATH, params={"ticker": "MSFT"}, headers=alice).json()) == 1


def test_visitors_must_sign_in(client):
    assert client.get(PATH, params={"ticker": "MSFT"}).status_code == 401
    assert save(client, None).status_code == 401


def test_invalid_sets_are_reported_per_field(client):
    alice = headers(client)

    response = save(client, alice, name="  ", assumptions={**BULLISH, "growth_rate": 3, "forecast_years": 0})

    assert response.status_code == 422
    fields = response.json()["error"]["fields"]
    assert set(fields) >= {"name", "assumptions.growth_rate", "assumptions.forecast_years"}

