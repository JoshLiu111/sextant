import pytest
from fastapi.testclient import TestClient

from data_fixtures import FixtureAdapter, price_frame, serving
from main import app

client = TestClient(app)

ENDPOINT = "/api/compute/portfolio/metrics"
RISK_ENDPOINT = "/api/compute/risk/metrics"
RANGE = {"start": "2021-01-01", "end": "2025-12-31"}
RISK_METRICS = [
    "annualized_return",
    "annualized_volatility",
    "max_drawdown",
    "var",
    "cvar",
    "sharpe",
    "sortino",
    "beta",
]


def post(**body):
    return client.post(ENDPOINT, json={"benchmark": "DEMO-MKT", **RANGE, **body})


def ok(**body):
    response = post(**body)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("ticker", ["DEMO-B", "DEMO-D"])
def test_a_portfolio_of_one_ticker_has_the_same_risk_metrics_as_p3(ticker):
    params = {"confidence": 0.99, "risk_free_rate": 0.02}
    portfolio = ok(holdings=[{"ticker": ticker, "weight": 1.0}], **params)
    p3 = client.post(RISK_ENDPOINT, json={"tickers": [ticker], "benchmark": "DEMO-MKT", **RANGE, **params}).json()

    for name in RISK_METRICS:
        got = portfolio["metrics"][f"{name}:portfolio"]
        want = p3["metrics"][f"{name}:{ticker}"]
        assert got["status"] == "ok", got
        assert got["value"] == pytest.approx(want["value"], rel=1e-12), name
        assert got["unit"] == want["unit"]
        assert got["details"] == want["details"]


def points(body, series_id):
    result = body["series"][series_id]
    assert result["status"] == "ok", result
    assert result["x_unit"] == "date" and result["y_unit"] == "decimal"
    return [(p["x"], p["y"]) for p in result["points"]]


def test_a_two_asset_portfolio_return_series_is_the_weighted_daily_returns():
    # AAA: +10%, -10%, +2% (a 1.98 dividend on a flat close). BBB: -2%, +2%, +5%.
    frames = {
        "AAA": price_frame("2024-01-01", [100.0, 110.0, 99.0, 99.0], dividends={3: 1.98}),
        "BBB": price_frame("2024-01-01", [50.0, 49.0, 49.98, 52.479]),
    }
    with serving(FixtureAdapter(frames)):
        body = ok(
            holdings=[{"ticker": "AAA", "weight": 0.6}, {"ticker": "BBB", "weight": 0.4}],
            benchmark="BBB",
            start="2024-01-01",
            end="2024-01-31",
        )

    # Rebalanced daily: 0.6*10% + 0.4*-2% = 5.2%, then -5.2%, then 3.2%, compounded.
    expected = [
        ("2024-01-01", 0.0),
        ("2024-01-02", 0.052),
        ("2024-01-03", 1.052 * 0.948 - 1),
        ("2024-01-04", 1.052 * 0.948 * 1.032 - 1),
    ]
    got = points(body, "cumulative_return:portfolio")
    assert [x for x, _ in got] == [x for x, _ in expected]
    assert [y for _, y in got] == pytest.approx([y for _, y in expected], abs=1e-12)
    assert [y for _, y in points(body, "cumulative_return:benchmark")] == pytest.approx(
        [0.0, -0.02, 0.98 * 1.02 - 1, 0.98 * 1.02 * 1.05 - 1], abs=1e-12
    )


def field_errors(**body):
    response = post(**body)
    assert response.status_code == 422, response.text
    return response.json()["error"]["fields"]


def test_weights_that_do_not_add_up_to_100_percent_are_rejected_with_the_total():
    fields = field_errors(holdings=[{"ticker": "DEMO-A", "weight": 0.5}, {"ticker": "DEMO-B", "weight": 0.4}])

    assert fields == {"holdings": "Weights must add up to 100% (they add up to 90%)."}


def test_weights_within_rounding_of_100_percent_are_accepted():
    third = {"weight": 0.3333}
    body = ok(holdings=[{"ticker": t, **third} for t in ["DEMO-A", "DEMO-B"]] + [{"ticker": "DEMO-E", "weight": 0.3334}])

    assert body["metrics"]["annualized_volatility:portfolio"]["status"] == "ok"


def test_each_bad_holding_is_reported_on_its_own_row():
    fields = field_errors(
        holdings=[
            {"ticker": "DEMO-A", "weight": 1.0},
            {"ticker": " ", "weight": 0.0},
            {"ticker": "DEMO-B", "weight": "lots"},
        ]
    )

    assert fields == {
        "holdings.1.ticker": "Enter a ticker.",
        "holdings.1.weight": "Enter a weight above 0% and up to 100%.",
        "holdings.2.weight": "Enter a number.",
    }


def test_a_ticker_listed_twice_is_rejected():
    fields = field_errors(holdings=[{"ticker": "demo-a", "weight": 0.5}, {"ticker": "DEMO-A", "weight": 0.5}])

    assert fields == {"holdings": "Each ticker can only be listed once."}


def test_an_unknown_ticker_is_reported_on_its_row():
    fields = field_errors(holdings=[{"ticker": "DEMO-A", "weight": 0.5}, {"ticker": "DEMO-ZZ", "weight": 0.5}])

    assert list(fields) == ["holdings.1.ticker"]
    assert "DEMO-ZZ" in fields["holdings.1.ticker"]


def test_result_is_flagged_as_demo_data_and_scores_the_benchmark_too():
    body = ok(holdings=[{"ticker": "DEMO-A", "weight": 0.6}, {"ticker": "DEMO-E", "weight": 0.4}])

    assert body["tool"] == "portfolio"
    assert body["source"]["is_demo"] is True
    assert body["meta"]["data_cutoff"] == "2025-12-31"
    assert body["metrics"]["beta:benchmark"]["value"] == pytest.approx(1.0)
    # A blend of a 0.7-beta and a 0.2-beta stock has a beta near 0.6 * 0.7 + 0.4 * 0.2 = 0.5.
    assert body["metrics"]["beta:portfolio"]["value"] == pytest.approx(0.5, abs=0.08)
