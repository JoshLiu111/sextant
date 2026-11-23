"""American options on a binomial tree: POST /options/american."""

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

AMERICAN = "/api/compute/options/american"
SINGLE = "/api/compute/options/price"

DEFAULTS = {
    "spot": 100.0,
    "strike": 100.0,
    "time_to_expiry": 1.0,
    "volatility": 0.2,
    "risk_free_rate": 0.05,
    "dividend_yield": 0.0,
}


def american(**overrides):
    response = client.post(AMERICAN, json={**DEFAULTS, **overrides})
    assert response.status_code == 200, response.text
    return response.json()


def value(body, metric_id):
    result = body["metrics"][metric_id]
    assert result["status"] == "ok", result
    return result["value"]


def bs(kind, **inputs):
    response = client.post(SINGLE, json={**DEFAULTS, **inputs})
    return value(response.json(), f"{kind}_price")


@pytest.mark.parametrize("kind", ["call", "put"])
@pytest.mark.parametrize(
    "inputs",
    [{}, {"spot": 90.0, "dividend_yield": 0.03}, {"strike": 120.0, "volatility": 0.4, "time_to_expiry": 0.5}],
)
def test_european_tree_price_converges_to_black_scholes_as_steps_increase(kind, inputs):
    target = bs(kind, **inputs)

    errors = [abs(value(american(**inputs, steps=n), f"european_{kind}_tree") - target) for n in (25, 100, 1000)]

    assert errors[0] > errors[2]
    assert errors[2] < 0.01
    # The response also shows the Black-Scholes price next to the tree.
    assert value(american(**inputs, steps=25), f"european_{kind}") == pytest.approx(target, abs=1e-12)


def test_american_put_on_a_dividend_free_stock_is_worth_at_least_the_european_put():
    body = american(spot=90.0, steps=500)

    put, european = value(body, "american_put"), value(body, "european_put")
    assert put >= european
    assert value(body, "put_early_exercise_premium") > 0
    # The premium is measured on the same tree, so discretisation error cancels.
    assert value(body, "put_early_exercise_premium") == pytest.approx(
        put - value(body, "european_put_tree"), abs=1e-12
    )
    # Never worth less than exercising now.
    assert put >= 100.0 - 90.0


def test_american_call_without_dividends_is_never_exercised_early():
    body = american(steps=500)

    assert value(body, "american_call") == pytest.approx(value(body, "european_call_tree"), abs=1e-9)
    assert value(body, "call_early_exercise_premium") == pytest.approx(0.0, abs=1e-9)


def test_american_call_with_a_high_dividend_yield_carries_an_early_exercise_premium():
    body = american(spot=120.0, dividend_yield=0.08, steps=500)

    assert value(body, "call_early_exercise_premium") > 0.05


def test_known_american_put_value():
    # Hull, Options, Futures and Other Derivatives: S=50, K=50, T=5 months, r=10%, sigma=40%.
    # The converged American put value is about 4.28 (a 5-step tree gives 4.49).
    body = american(spot=50.0, strike=50.0, time_to_expiry=5 / 12, risk_free_rate=0.1, volatility=0.4, steps=5)
    assert value(body, "american_put") == pytest.approx(4.49, abs=0.005)

    body = american(spot=50.0, strike=50.0, time_to_expiry=5 / 12, risk_free_rate=0.1, volatility=0.4, steps=2000)
    assert value(body, "american_put") == pytest.approx(4.28, abs=0.01)


def test_convergence_series_shows_the_tree_price_by_number_of_steps():
    body = american(steps=200)
    points = body["series"]["american_put_by_steps"]["points"]
    xs = [p["x"] for p in points]

    assert xs == sorted(xs) and xs[-1] == 200 and xs[0] >= 1
    assert points[-1]["y"] == pytest.approx(value(body, "american_put"), abs=1e-12)
    euro = body["series"]["european_put_tree_by_steps"]["points"]
    assert [p["x"] for p in euro] == xs
    assert all(p["y"] > 0 for p in euro)


@pytest.mark.parametrize("steps, words", [(0, "at least 1"), (5001, "at most")])
def test_steps_out_of_range_is_reported_against_the_field(steps, words):
    response = client.post(AMERICAN, json={**DEFAULTS, "steps": steps})

    assert response.status_code == 422
    assert words in response.json()["error"]["fields"]["steps"]
