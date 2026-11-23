"""Multi-leg strategies: POST /options/strategy."""

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

STRATEGY = "/api/compute/options/strategy"
SINGLE = "/api/compute/options/price"

MARKET = {
    "spot": 100.0,
    "time_to_expiry": 0.5,
    "volatility": 0.25,
    "risk_free_rate": 0.04,
    "dividend_yield": 0.01,
}

GREEKS = ["delta", "gamma", "vega", "theta", "rho"]


def strategy(legs, **overrides):
    response = client.post(STRATEGY, json={**MARKET, **overrides, "legs": legs})
    assert response.status_code == 200, response.text
    return response.json()


def single(**inputs):
    response = client.post(SINGLE, json={**MARKET, **inputs})
    assert response.status_code == 200, response.text
    return response.json()


def value(body, metric_id):
    result = body["metrics"][metric_id]
    assert result["status"] == "ok", result
    return result["value"]


def curve(body, series_id):
    result = body["series"][series_id]
    assert result["status"] == "ok", result
    return {p["x"]: p["y"] for p in result["points"]}


def single_leg(instrument, strike, spot):
    """Price, Greeks and expiry payoff of one long option from the single-option endpoint."""
    body = single(spot=spot, strike=strike)
    out = {
        "price": value(body, f"{instrument}_price"),
        "delta": value(body, f"{instrument}_delta"),
        "gamma": value(body, "gamma"),
        "vega": value(body, "vega"),
        "theta": value(body, f"{instrument}_theta"),
        "rho": value(body, f"{instrument}_rho"),
    }
    out["payoff"] = max(spot - strike, 0.0) if instrument == "call" else max(strike - spot, 0.0)
    return out


MIXED = [
    {"instrument": "call", "position": "long", "quantity": 2, "strike": 95.0},
    {"instrument": "put", "position": "short", "quantity": 1, "strike": 105.0},
    {"instrument": "call", "position": "short", "quantity": 1.5, "strike": 120.0},
]


def test_strategy_greeks_and_cost_are_the_signed_sum_of_its_legs():
    body = strategy(MIXED)

    legs = [(leg, single_leg(leg["instrument"], leg["strike"], MARKET["spot"])) for leg in MIXED]

    def signed_sum(key):
        return sum((1 if leg["position"] == "long" else -1) * leg["quantity"] * r[key] for leg, r in legs)

    assert value(body, "net_cost") == pytest.approx(signed_sum("price"), abs=1e-9)
    for greek in GREEKS:
        assert value(body, greek) == pytest.approx(signed_sum(greek), abs=1e-9), greek


def test_strategy_curves_are_the_signed_sum_of_its_legs_at_each_spot():
    body = strategy(MIXED)
    at_expiry, today = curve(body, "profit_at_expiry"), curve(body, "profit_today")
    cost = value(body, "net_cost")
    assert at_expiry.keys() == today.keys()
    assert min(at_expiry) < 95.0 and max(at_expiry) > 120.0

    grid = sorted(at_expiry)
    for spot in [*grid[::25], grid[-1], 95.0, 100.0, 105.0, 120.0]:
        assert spot in at_expiry
        legs = [(leg, single_leg(leg["instrument"], leg["strike"], spot)) for leg in MIXED]
        sign = {"long": 1, "short": -1}
        payoff = sum(sign[leg["position"]] * leg["quantity"] * r["payoff"] for leg, r in legs)
        worth = sum(sign[leg["position"]] * leg["quantity"] * r["price"] for leg, r in legs)
        assert at_expiry[spot] == pytest.approx(payoff - cost, abs=1e-9)
        assert today[spot] == pytest.approx(worth - cost, abs=1e-9)


def leg(instrument, position, strike=None, quantity=1):
    return {"instrument": instrument, "position": position, "quantity": quantity, "strike": strike}


def test_iron_condor_has_capped_gain_and_loss_set_by_its_credit_and_wing_width():
    condor = [
        leg("put", "long", 80.0),
        leg("put", "short", 90.0),
        leg("call", "short", 110.0),
        leg("call", "long", 120.0),
    ]
    body = strategy(condor)
    credit = -value(body, "net_cost")
    at_expiry = curve(body, "profit_at_expiry")

    assert credit > 0
    # Between the short strikes every option expires worthless: keep the credit.
    assert value(body, "max_profit") == pytest.approx(credit, abs=1e-9)
    assert at_expiry[100.0] == pytest.approx(credit, abs=1e-9)
    # Beyond a long wing the loss is the 10-point wing width less the credit.
    assert value(body, "max_loss") == pytest.approx(10.0 - credit, abs=1e-9)
    assert at_expiry[min(at_expiry)] == pytest.approx(credit - 10.0, abs=1e-9)
    assert at_expiry[max(at_expiry)] == pytest.approx(credit - 10.0, abs=1e-9)


def test_bull_call_spread_gains_above_the_upper_strike_and_loses_its_debit_below():
    spread = [leg("call", "long", 95.0), leg("call", "short", 105.0)]
    body = strategy(spread)
    debit = value(body, "net_cost")
    at_expiry = curve(body, "profit_at_expiry")

    assert 0 < debit < 10
    assert value(body, "max_loss") == pytest.approx(debit, abs=1e-9)
    assert value(body, "max_profit") == pytest.approx(10.0 - debit, abs=1e-9)
    assert at_expiry[95.0] == pytest.approx(-debit, abs=1e-9)
    assert at_expiry[105.0] == pytest.approx(10.0 - debit, abs=1e-9)
    assert value(body, "delta") > 0


@pytest.mark.parametrize("put_strike, call_strike", [(100.0, 100.0), (90.0, 110.0)])
def test_long_straddle_and_strangle_lose_at_most_the_premium_and_profit_without_limit(put_strike, call_strike):
    body = strategy([leg("put", "long", put_strike), leg("call", "long", call_strike)])
    premium = value(body, "net_cost")
    at_expiry = curve(body, "profit_at_expiry")

    assert value(body, "max_loss") == pytest.approx(premium, abs=1e-9)
    assert at_expiry[100.0] == pytest.approx(-premium, abs=1e-9)
    # Unlimited is a valid answer, not a failure: ok, no number, and flagged as unlimited.
    unlimited = body["metrics"]["max_profit"]
    assert unlimited["status"] == "ok" and unlimited["value"] is None
    assert unlimited["details"]["bound"] == "unlimited"
    assert "rises" in unlimited["details"]["why"]
    # A V shape: the payoff rises on both sides away from the strikes.
    assert at_expiry[min(at_expiry)] > -premium and at_expiry[max(at_expiry)] > -premium
    assert value(body, "gamma") > 0 and value(body, "vega") > 0


def test_short_call_reports_an_unlimited_loss_and_the_underlying_leg_has_delta_one():
    naked = strategy([leg("call", "short", 100.0)])
    unlimited = naked["metrics"]["max_loss"]
    assert unlimited["status"] == "ok" and unlimited["value"] is None and unlimited["reason"] is None
    assert unlimited["details"]["bound"] == "unlimited"
    assert value(naked, "max_profit") == pytest.approx(-value(naked, "net_cost"), abs=1e-9)

    covered = strategy([leg("underlying", "long"), leg("call", "short", 110.0)])
    call = single(strike=110.0)
    assert value(covered, "delta") == pytest.approx(1.0 - value(call, "call_delta"), abs=1e-9)
    assert value(covered, "net_cost") == pytest.approx(MARKET["spot"] - value(call, "call_price"), abs=1e-9)
    # Covered call: capped upside, loss bounded by the stock going to zero.
    assert value(covered, "max_profit") == pytest.approx(110.0 - value(covered, "net_cost"), abs=1e-9)
    assert value(covered, "max_loss") == pytest.approx(value(covered, "net_cost"), abs=1e-9)


@pytest.mark.parametrize("greek", GREEKS)
def test_greek_curves_pass_through_the_greeks_at_the_current_inputs(greek):
    body = strategy(MIXED)

    vs_spot, vs_time = curve(body, f"{greek}_vs_spot"), curve(body, f"{greek}_vs_time")

    assert vs_spot[MARKET["spot"]] == pytest.approx(value(body, greek), abs=1e-12)
    assert vs_time[MARKET["time_to_expiry"]] == pytest.approx(value(body, greek), abs=1e-12)
    assert body["series"][f"{greek}_vs_time"]["x_unit"] == "years"
    assert body["series"][f"{greek}_vs_spot"]["y_unit"] == body["metrics"][greek]["unit"]


def test_greek_curves_match_a_fresh_strategy_priced_at_another_spot_or_expiry():
    body = strategy(MIXED)
    vs_spot, vs_time = curve(body, "delta_vs_spot"), curve(body, "theta_vs_time")
    other_spot = sorted(vs_spot)[10]
    other_time = sorted(vs_time)[5]

    assert vs_spot[other_spot] == pytest.approx(value(strategy(MIXED, spot=other_spot), "delta"), abs=1e-12)
    assert vs_time[other_time] == pytest.approx(
        value(strategy(MIXED, time_to_expiry=other_time), "theta"), abs=1e-12
    )
    # Time runs from about a day to twice the current time to expiry.
    assert min(vs_time) <= 1 / 365 and max(vs_time) == pytest.approx(2 * MARKET["time_to_expiry"])


def invalid(body):
    response = client.post(STRATEGY, json=body)
    assert response.status_code == 422, response.text
    return response.json()["error"]["fields"]


def test_invalid_legs_are_reported_against_the_leg_field():
    fields = invalid(
        {
            **MARKET,
            "legs": [
                leg("call", "long", None),
                leg("put", "short", -5.0),
                leg("call", "long", 100.0, quantity=0),
                leg("underlying", "long"),
            ],
        }
    )

    assert fields["legs.0.strike"] == "Enter a strike price for this option."
    assert "greater than 0" in fields["legs.1.strike"]
    assert "greater than 0" in fields["legs.2.quantity"]
    assert not any(f.startswith("legs.3") for f in fields)


def test_a_strategy_needs_at_least_one_leg():
    assert "at least one leg" in invalid({**MARKET, "legs": []})["legs"]
