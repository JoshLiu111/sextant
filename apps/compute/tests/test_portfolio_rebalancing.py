import pytest
from fastapi.testclient import TestClient

from data_fixtures import FixtureAdapter, price_frame, serving
from main import app

client = TestClient(app)

ENDPOINT = "/api/compute/portfolio/rebalancing"
RANGE = {"start": "2021-01-01", "end": "2025-12-31"}
RISK_METRICS = ["annualized_return", "annualized_volatility", "max_drawdown", "var", "cvar", "sharpe", "sortino", "beta"]
DEMO_HOLDINGS = [
    {"ticker": "DEMO-A", "weight": 0.4},
    {"ticker": "DEMO-B", "weight": 0.3},
    {"ticker": "DEMO-E", "weight": 0.3},
]


def post(**body):
    return client.post(ENDPOINT, json={"benchmark": "DEMO-MKT", **RANGE, **body})


def ok(**body):
    response = post(**body)
    assert response.status_code == 200, response.text
    return response.json()


def curve(body, who):
    result = body["series"][f"cumulative_return:{who}"]
    assert result["status"] == "ok", result
    assert result["x_unit"] == "date" and result["y_unit"] == "decimal"
    return [(p["x"], p["y"]) for p in result["points"]]


# AAA: +10%, -10%, 0. BBB: 0, 0, +10%. Jan 31 is the last trading day of January.
TWO_ASSETS = {
    "AAA": price_frame("2024-01-30", [100.0, 110.0, 99.0, 99.0]),
    "BBB": price_frame("2024-01-30", [100.0, 100.0, 100.0, 110.0]),
}
HALF_HALF = [{"ticker": "AAA", "weight": 0.5}, {"ticker": "BBB", "weight": 0.5}]
FIXTURE_RANGE = {"benchmark": "BBB", "start": "2024-01-01", "end": "2024-02-29"}


def test_a_monthly_rule_resets_the_target_weights_at_each_month_end_and_buy_and_hold_never_does():
    with serving(FixtureAdapter(TWO_ASSETS)):
        body = ok(holdings=HALF_HALF, rule="monthly", **FIXTURE_RANGE)

    dates = ["2024-01-30", "2024-01-31", "2024-02-01", "2024-02-02"]
    # Buy and hold: 50 + 50 -> 55 + 50 -> 49.5 + 50 -> 49.5 + 55.
    held = curve(body, "buy_and_hold")
    assert [x for x, _ in held] == dates
    assert [y for _, y in held] == pytest.approx([0.0, 0.05, -0.005, 0.045], abs=1e-12)
    # Rebalanced at the Jan 31 close back to 52.5 + 52.5 -> 47.25 + 52.5 -> 47.25 + 57.75.
    rebalanced = curve(body, "rebalanced")
    assert [x for x, _ in rebalanced] == dates
    assert [y for _, y in rebalanced] == pytest.approx([0.0, 0.05, -0.0025, 0.05], abs=1e-12)

    metrics = body["metrics"]
    assert metrics["rebalance_count:rebalanced"] == {
        "value": 1.0,
        "status": "ok",
        "reason": None,
        "unit": "count",
        "details": {"last": "2024-01-31"},
    }
    # Weights had drifted to 55/105 and 50/105: half of the total absolute trade is 2.5/105.
    assert metrics["turnover:rebalanced"]["value"] == pytest.approx(2.5 / 105, abs=1e-12)
    assert metrics["turnover:rebalanced"]["unit"] == "decimal"


def test_a_drift_rule_rebalances_only_once_a_weight_moves_past_the_threshold():
    with serving(FixtureAdapter(TWO_ASSETS)):
        tight = ok(holdings=HALF_HALF, rule="drift", drift_threshold=0.02, **FIXTURE_RANGE)
        loose = ok(holdings=HALF_HALF, rule="drift", drift_threshold=0.03, **FIXTURE_RANGE)

    # AAA drifts to 52.4% on Jan 31 (past a 2-point threshold, inside a 3-point one); after the reset
    # to 52.5 + 52.5 it falls to 47.25 / 99.75 = 47.4% on Feb 1, so the tight rule resets again to
    # 49.875 + 49.875 -> 49.875 + 54.8625.
    assert [y for _, y in curve(tight, "rebalanced")] == pytest.approx([0.0, 0.05, -0.0025, 0.047375], abs=1e-12)
    assert tight["metrics"]["rebalance_count:rebalanced"]["value"] == 2
    assert tight["metrics"]["rebalance_count:rebalanced"]["details"] == {"last": "2024-02-01"}
    assert curve(loose, "rebalanced") == curve(loose, "buy_and_hold")
    assert loose["metrics"]["rebalance_count:rebalanced"]["value"] == 0
    assert loose["metrics"]["turnover:rebalanced"]["value"] == 0


def test_with_no_drift_between_the_holdings_rebalancing_changes_nothing():
    closes = [100.0, 103.0, 98.0, 101.0, 107.0, 104.0]
    frames = {t: price_frame("2024-03-26", closes) for t in ["AAA", "BBB", "CCC"]}
    holdings = [{"ticker": t, "weight": w} for t, w in [("AAA", 0.5), ("BBB", 0.3), ("CCC", 0.2)]]

    with serving(FixtureAdapter(frames)):
        body = ok(holdings=holdings, rule="monthly", benchmark="AAA", start="2024-01-01", end="2024-12-31")

    rebalanced, held = curve(body, "rebalanced"), curve(body, "buy_and_hold")
    assert [x for x, _ in rebalanced] == [x for x, _ in held]
    assert [y for _, y in rebalanced] == pytest.approx([y for _, y in held], abs=1e-12)
    for name in RISK_METRICS:
        got, want = body["metrics"][f"{name}:rebalanced"], body["metrics"][f"{name}:buy_and_hold"]
        assert got["status"] == want["status"], name
        assert got["value"] == pytest.approx(want["value"], abs=1e-12), name
    assert body["metrics"]["turnover:rebalanced"]["value"] == pytest.approx(0, abs=1e-12)


@pytest.mark.parametrize("rule", ["monthly", "quarterly", "yearly", "drift"])
def test_the_demo_backtest_scores_both_strategies_side_by_side_on_demo_data(rule):
    body = ok(holdings=DEMO_HOLDINGS, rule=rule)

    assert body["tool"] == "portfolio"
    assert body["source"]["is_demo"] is True
    assert len(curve(body, "rebalanced")) == len(curve(body, "buy_and_hold"))
    for who in ["rebalanced", "buy_and_hold"]:
        for name in RISK_METRICS:
            assert body["metrics"][f"{name}:{who}"]["status"] == "ok", (name, who)
    assert curve(body, "rebalanced") != curve(body, "buy_and_hold")


def test_calendar_rules_rebalance_once_per_period():
    counts = {rule: ok(holdings=DEMO_HOLDINGS, rule=rule)["metrics"]["rebalance_count:rebalanced"] for rule in
              ["monthly", "quarterly", "yearly"]}

    # Five years of month, quarter and year ends, less the final one (the backtest ends there).
    assert counts["monthly"]["value"] == 59
    assert counts["quarterly"]["value"] == 19
    assert counts["yearly"]["value"] == 4
    assert counts["yearly"]["details"] == {"last": "2024-12-31"}


def test_rule_and_threshold_are_validated():
    response = post(holdings=DEMO_HOLDINGS, rule="weekly", drift_threshold=0)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["fields"] == {
        "rule": "Choose one of the listed options.",
        "drift_threshold": "Enter a drift threshold above 0% and up to 50%.",
    }


def test_holdings_are_validated_like_the_demo_portfolio():
    response = post(holdings=[{"ticker": "DEMO-A", "weight": 0.5}], rule="monthly")
    assert response.status_code == 422, response.text
    assert response.json()["error"]["fields"] == {"holdings": "Weights must add up to 100% (they add up to 50%)."}
