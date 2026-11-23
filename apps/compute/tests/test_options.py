import math
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

ENDPOINT = "/api/compute/options/price"

DEFAULTS = {
    "spot": 100.0,
    "strike": 100.0,
    "time_to_expiry": 1.0,
    "volatility": 0.2,
    "risk_free_rate": 0.05,
    "dividend_yield": 0.0,
}


def price(**overrides):
    response = client.post(ENDPOINT, json={**DEFAULTS, **overrides})
    assert response.status_code == 200, response.text
    return response.json()


def value(body, metric):
    result = body["metrics"][metric]
    assert result["status"] == "ok", result
    return result["value"]


def test_textbook_black_scholes_prices():
    # Hull's classic at-the-money example: S=K=100, T=1, r=5%, sigma=20%.
    body = price()

    assert value(body, "call_price") == pytest.approx(10.4506, abs=1e-4)
    assert value(body, "put_price") == pytest.approx(5.5735, abs=1e-4)


@pytest.mark.parametrize(
    "inputs",
    [
        {},
        {"spot": 80.0, "strike": 110.0, "dividend_yield": 0.03},
        {"spot": 130.0, "strike": 90.0, "time_to_expiry": 0.25, "volatility": 0.6},
        {"risk_free_rate": -0.01, "dividend_yield": 0.02, "time_to_expiry": 3.0},
    ],
)
def test_put_call_parity_holds(inputs):
    params = {**DEFAULTS, **inputs}
    body = price(**inputs)

    call, put = value(body, "call_price"), value(body, "put_price")
    s, k, t = params["spot"], params["strike"], params["time_to_expiry"]
    r, q = params["risk_free_rate"], params["dividend_yield"]
    assert call - put == pytest.approx(s * math.exp(-q * t) - k * math.exp(-r * t), abs=1e-9)


GREEK_CASES = [
    {},
    {"spot": 85.0, "strike": 100.0, "dividend_yield": 0.02, "time_to_expiry": 0.5},
    {"spot": 120.0, "strike": 100.0, "volatility": 0.45, "risk_free_rate": 0.03},
]


def central_difference(kind, param, h, inputs):
    base = {**DEFAULTS, **inputs}
    up = value(price(**{**inputs, param: base[param] + h}), f"{kind}_price")
    down = value(price(**{**inputs, param: base[param] - h}), f"{kind}_price")
    return (up - down) / (2 * h)


@pytest.mark.parametrize("inputs", GREEK_CASES)
@pytest.mark.parametrize("kind", ["call", "put"])
def test_first_order_greeks_match_finite_differences(kind, inputs):
    body = price(**inputs)

    # Delta: per $1 move in spot.
    assert value(body, f"{kind}_delta") == pytest.approx(
        central_difference(kind, "spot", 0.01, inputs), abs=1e-6
    )
    # Vega: per 1 volatility point (0.01), same for calls and puts.
    assert value(body, "vega") == pytest.approx(
        central_difference(kind, "volatility", 1e-4, inputs) / 100, abs=1e-6
    )
    # Rho: per 1 percentage point (0.01) of the risk-free rate.
    assert value(body, f"{kind}_rho") == pytest.approx(
        central_difference(kind, "risk_free_rate", 1e-4, inputs) / 100, abs=1e-6
    )
    # Theta: value change per calendar day as time passes (expiry gets closer).
    assert value(body, f"{kind}_theta") == pytest.approx(
        -central_difference(kind, "time_to_expiry", 1e-4, inputs) / 365, abs=1e-6
    )


@pytest.mark.parametrize("inputs", GREEK_CASES)
@pytest.mark.parametrize("kind", ["call", "put"])
def test_gamma_matches_second_difference_of_price(kind, inputs):
    h = 0.01
    spot = {**DEFAULTS, **inputs}["spot"]
    up = value(price(**{**inputs, "spot": spot + h}), f"{kind}_price")
    mid = value(price(**inputs), f"{kind}_price")
    down = value(price(**{**inputs, "spot": spot - h}), f"{kind}_price")

    assert value(price(**inputs), "gamma") == pytest.approx((up - 2 * mid + down) / h**2, abs=1e-5)


@pytest.mark.parametrize("kind", ["call", "put"])
@pytest.mark.parametrize(
    "inputs",
    [
        {"volatility": 0.2},
        {"volatility": 0.05, "spot": 95.0},
        {"volatility": 0.85, "strike": 140.0, "time_to_expiry": 2.0, "dividend_yield": 0.01},
    ],
)
def test_implied_volatility_recovers_the_volatility_behind_a_bs_price(kind, inputs):
    market_price = value(price(**inputs), f"{kind}_price")

    body = price(**{**inputs, "volatility": 0.4, "option_type": kind, "market_price": market_price})

    assert value(body, "implied_volatility") == pytest.approx(inputs["volatility"], abs=1e-6)
    assert body["metrics"]["implied_volatility"]["unit"] == "decimal"


def test_implied_volatility_without_a_market_price_is_missing_data():
    result = price()["metrics"]["implied_volatility"]

    assert result["status"] == "missing_data"
    assert result["value"] is None
    assert "market price" in result["reason"].lower()


@pytest.mark.parametrize(
    "market_price, reason_word",
    [(0.5, "intrinsic"), (150.0, "upper bound")],
)
def test_price_with_no_iv_solution_only_fails_that_metric(market_price, reason_word):
    # ITM call: intrinsic (discounted) is ~24.9 for S=130, K=100; the upper bound is S.
    body = price(spot=130.0, option_type="call", market_price=market_price)

    iv = body["metrics"]["implied_volatility"]
    assert iv["status"] == "error"
    assert iv["value"] is None
    assert reason_word in iv["reason"].lower()
    assert body["metrics"]["call_price"]["status"] == "ok"
    assert body["metrics"]["vega"]["status"] == "ok"


def curve(body, series_id):
    result = body["series"][series_id]
    assert result["status"] == "ok", result
    return {p["x"]: p["y"] for p in result["points"]}


@pytest.mark.parametrize("kind", ["call", "put"])
def test_chart_series_show_payoff_at_expiry_and_current_value(kind):
    body = price(spot=105.0, strike=100.0, option_type=kind)
    payoff, current = curve(body, "payoff_at_expiry"), curve(body, "theoretical_value")

    # Both curves span the strike and the spot, on the same spot grid.
    assert payoff.keys() == current.keys()
    assert min(payoff) < 100.0 < 105.0 < max(payoff)
    assert len(payoff) >= 50
    # Payoff at expiry is intrinsic value: max(S-K, 0) for a call, max(K-S, 0) for a put.
    assert payoff[100.0] == 0.0
    assert payoff[105.0] == (5.0 if kind == "call" else 0.0)
    # The current value curve passes through today's price at today's spot.
    assert current[105.0] == pytest.approx(value(body, f"{kind}_price"), abs=1e-12)
    assert body["series"]["payoff_at_expiry"]["x_unit"] == "currency"
    assert body["series"]["theoretical_value"]["y_unit"] == "currency"


def test_response_follows_the_unified_result_envelope():
    first = price(market_price=11.0)
    second = price(market_price=11.0)

    assert first["calculation_id"].startswith("calc_")
    assert first["calculation_id"] != second["calculation_id"]
    assert first["tool"] == "options"
    assert first["source"] == {"id": "user_input", "name": "User input", "is_demo": False}
    assert first["meta"]["parameters"] == {**DEFAULTS, "option_type": "call", "market_price": 11.0}
    assert datetime.fromisoformat(first["meta"]["computed_at"]).tzinfo is not None
    assert first["meta"]["data_cutoff"] is None
    for result in first["metrics"].values():
        assert set(result) == {"value", "status", "reason", "unit", "details"}


def invalid(**overrides):
    response = client.post(ENDPOINT, json={**DEFAULTS, **overrides})
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["message"]
    return error["fields"]


@pytest.mark.parametrize(
    "field, bad, words",
    [
        ("volatility", -0.2, "greater than 0%"),
        ("volatility", 0.0, "greater than 0%"),
        ("time_to_expiry", -0.5, "expired"),
        ("time_to_expiry", 0.0, "expired"),
        ("spot", -10.0, "greater than 0"),
        ("strike", 0.0, "greater than 0"),
        ("market_price", -1.0, "greater than 0"),
        ("risk_free_rate", 2.0, "between"),
    ],
)
def test_invalid_input_is_reported_against_its_field(field, bad, words):
    fields = invalid(**{field: bad})

    assert list(fields) == [field]
    assert words in fields[field].lower()


def test_every_invalid_field_is_reported_at_once():
    fields = invalid(volatility=-1.0, time_to_expiry=0.0)

    assert set(fields) == {"volatility", "time_to_expiry"}


def test_missing_and_non_numeric_inputs_are_reported_against_their_field():
    body = {**DEFAULTS, "spot": "abc"}
    del body["strike"]
    response = client.post(ENDPOINT, json=body)

    assert response.status_code == 422
    assert set(response.json()["error"]["fields"]) == {"spot", "strike"}


def test_greeks_report_their_units():
    metrics = price()["metrics"]

    assert metrics["call_delta"]["unit"] == "per_dollar"
    assert metrics["gamma"]["unit"] == "per_dollar"
    assert metrics["vega"]["unit"] == "per_vol_point"
    assert metrics["call_theta"]["unit"] == "per_day"
    assert metrics["put_rho"]["unit"] == "per_rate_point"
