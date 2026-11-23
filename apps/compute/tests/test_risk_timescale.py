"""Risk & Performance time-scale views (#24): return periods, rolling metrics,
the marked underwater chart and the return distribution. All through the HTTP API."""

import math

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from data_fixtures import FixtureAdapter, price_frame, serving
from main import app
from sextant_compute.data.synthetic import HISTORY_END, HISTORY_START, PERSONALITIES

client = TestClient(app)

ENDPOINT = "/api/compute/risk/metrics"
FULL_HISTORY = {"start": HISTORY_START.isoformat(), "end": HISTORY_END.isoformat()}


def post(**body):
    return client.post(ENDPOINT, json={"benchmark": "DEMO-MKT", **FULL_HISTORY, **body})


def metrics(**body):
    response = post(**body)
    assert response.status_code == 200, response.text
    return response.json()


def value(body, metric_id):
    result = body["metrics"][metric_id]
    assert result["status"] == "ok", result
    return result["value"]


# --- Return periods ---

# Three period returns of +10%, -10% and +20% (prices 100 -> 110 -> 99 -> 118.8).
# Sample mean 0.2/3, sample standard deviation sqrt(0.07/3) = 0.152753.
STEP_RETURNS_STD = math.sqrt(0.07 / 3)
STEP_RETURNS_MEAN = 0.2 / 3
PERIOD_CODES = {"weekly": ("W-FRI", 52), "monthly": ("M", 12), "quarterly": ("Q", 4), "yearly": ("Y", 1)}


def stepped_frame(period_code: str, start: str = "2024-01-01") -> pd.DataFrame:
    """Daily closes that move only on the last trading day of each period (then stay flat)."""
    targets = [110.0, 99.0, 118.8]
    days = pd.bdate_range(start, periods=400 * 3)
    periods = days.to_period(period_code)
    first_three = periods.unique()[:3]
    days = days[periods.isin(first_three)]
    periods = days.to_period(period_code)
    closes = []
    for i, p in enumerate(periods):
        k = list(first_three).index(p)
        last_day_of_first = i + 1 == len(days) or periods[i + 1] != p
        closes.append(100.0 if k == 0 and not last_day_of_first else targets[k])
    return price_frame(start, closes)


@pytest.mark.parametrize("period", list(PERIOD_CODES))
def test_volatility_and_sharpe_use_period_returns_annualized_for_the_period(period):
    code, per_year = PERIOD_CODES[period]
    frames = {"STEP": stepped_frame(code)}

    with serving(FixtureAdapter(frames)):
        body = metrics(tickers=["STEP"], benchmark="STEP", start="2024-01-01", end="2027-12-31", period=period)

    assert value(body, "annualized_volatility:STEP") == pytest.approx(STEP_RETURNS_STD * math.sqrt(per_year))
    assert value(body, "sharpe:STEP") == pytest.approx(STEP_RETURNS_MEAN / STEP_RETURNS_STD * math.sqrt(per_year))
    assert body["meta"]["parameters"]["period"] == period


@pytest.mark.parametrize("period", ["weekly", "monthly"])
def test_the_configured_annual_volatility_is_recovered_at_longer_periods(period):
    body = metrics(tickers=["DEMO-A"], period=period)

    assert value(body, "annualized_volatility:DEMO-A") == pytest.approx(PERSONALITIES["DEMO-A"].annual_vol, rel=0.15)
    assert value(body, "beta:DEMO-A") == pytest.approx(PERSONALITIES["DEMO-A"].beta, abs=0.15)


def test_switching_the_period_changes_the_period_statistics_but_not_return_or_drawdown():
    daily = metrics(tickers=["DEMO-B"], period="daily")
    monthly = metrics(tickers=["DEMO-B"], period="monthly")

    period_dependent = (
        "annualized_volatility",
        *("sharpe", "sortino", "treynor", "information_ratio"),
        *("var", "cvar", "parametric_var", "parametric_cvar", "cornish_fisher_var", "cornish_fisher_cvar"),
        *("beta", "alpha", "upside_capture", "downside_capture"),
    )
    for name in period_dependent:
        assert value(daily, f"{name}:DEMO-B") != pytest.approx(value(monthly, f"{name}:DEMO-B"), rel=1e-6), name
    for name in ("annualized_return", "max_drawdown"):
        assert value(daily, f"{name}:DEMO-B") == value(monthly, f"{name}:DEMO-B")
    # A one-month loss is larger than a one-day loss.
    assert value(monthly, "var:DEMO-B") > value(daily, "var:DEMO-B")


def test_the_period_defaults_to_daily():
    assert metrics(tickers=["DEMO-A"])["meta"]["parameters"]["period"] == "daily"


def test_too_few_period_returns_name_the_period():
    body = metrics(tickers=["DEMO-A"], start="2021-01-01", end="2025-12-31", period="yearly")

    reason = body["metrics"]["var:DEMO-A"]["reason"]
    assert body["metrics"]["var:DEMO-A"]["status"] == "missing_data"
    assert "needs at least 20 yearly returns" in reason and "got 5" in reason
    assert body["metrics"]["annualized_volatility:DEMO-A"]["status"] == "ok"


def test_an_unknown_period_is_a_field_error():
    response = post(tickers=["DEMO-A"], period="hourly")

    assert response.status_code == 422
    assert response.json()["error"]["fields"]["period"] == "Choose one of the listed options."


# --- Rolling metrics ---

YEAR = 252


def zigzag_frames():
    """Daily returns alternating exactly +1% and -1%, starting 2024-01-01."""
    closes = [100.0]
    for i in range(YEAR):
        closes.append(closes[-1] * (1.01 if i % 2 == 0 else 0.99))
    return {"ZIG": price_frame("2024-01-01", closes)}


def test_rolling_volatility_sharpe_and_beta_over_the_chosen_window():
    with serving(FixtureAdapter(zigzag_frames())):
        body = metrics(tickers=["ZIG"], benchmark="ZIG", start="2024-01-01", end="2025-12-31", rolling_window=20)

    vol = body["series"]["rolling_volatility:ZIG"]
    assert vol["status"] == "ok" and vol["x_unit"] == "date" and vol["y_unit"] == "decimal"
    # Every 20-day window holds ten +1% and ten -1% days: std = 0.01 * sqrt(20 / 19).
    assert len(vol["points"]) == YEAR - 20 + 1
    assert vol["points"][0]["x"] == pd.bdate_range("2024-01-02", periods=20)[-1].date().isoformat()
    assert all(p["y"] == pytest.approx(0.01 * math.sqrt(20 / 19) * math.sqrt(YEAR), abs=1e-5) for p in vol["points"])
    assert vol["details"]["window"] == 20
    sharpe = body["series"]["rolling_sharpe:ZIG"]
    assert sharpe["y_unit"] == "ratio"
    assert all(p["y"] == pytest.approx(0.0, abs=1e-9) for p in sharpe["points"])
    beta = body["series"]["rolling_beta:ZIG"]
    assert all(p["y"] == pytest.approx(1.0, abs=1e-5) for p in beta["points"])


def test_a_longer_window_gives_fewer_rolling_points():
    short = metrics(tickers=["DEMO-B"], start="2021-01-01", end="2025-12-31", rolling_window=21)
    long = metrics(tickers=["DEMO-B"], start="2021-01-01", end="2025-12-31", rolling_window=126)

    assert len(short["series"]["rolling_volatility:DEMO-B"]["points"]) - 105 == len(
        long["series"]["rolling_volatility:DEMO-B"]["points"]
    )


def test_rolling_beta_tracks_the_configured_beta():
    body = metrics(tickers=["DEMO-B"], rolling_window=252)

    ys = [p["y"] for p in body["series"]["rolling_beta:DEMO-B"]["points"]]
    assert sum(ys) / len(ys) == pytest.approx(PERSONALITIES["DEMO-B"].beta, abs=0.1)


def test_the_rolling_window_defaults_to_63_trading_days():
    body = metrics(tickers=["DEMO-A"], start="2021-01-01", end="2025-12-31")

    assert body["meta"]["parameters"]["rolling_window"] == 63
    assert body["series"]["rolling_volatility:DEMO-A"]["details"]["window"] == 63


def test_a_window_longer_than_the_range_is_missing_data_for_the_rolling_curves_only():
    body = metrics(tickers=["DEMO-A"], start="2025-01-01", end="2025-03-31", rolling_window=252)

    for name in ("rolling_volatility", "rolling_sharpe", "rolling_beta"):
        result = body["series"][f"{name}:DEMO-A"]
        assert result["status"] == "missing_data"
        assert "252-day rolling window" in result["reason"]
    assert body["metrics"]["annualized_volatility:DEMO-A"]["status"] == "ok"


@pytest.mark.parametrize("window", [1, 19, 757])
def test_an_out_of_range_window_is_a_field_error(window):
    response = post(tickers=["DEMO-A"], rolling_window=window)

    assert response.status_code == 422
    assert response.json()["error"]["fields"]["rolling_window"] == "Enter a window between 20 and 756 trading days."


# --- Return distribution ---

# 40 daily returns: 36 gains of 1% and four losses of 2%, 4%, 6% and 10%.
TAIL_RETURNS = [0.01] * 18 + [-0.06, -0.02] + [0.01] * 18 + [-0.10, -0.04]


def tail_metrics(**body):
    closes = [100.0]
    for r in TAIL_RETURNS:
        closes.append(closes[-1] * (1 + r))
    with serving(FixtureAdapter({"TAIL": price_frame("2024-01-01", closes)})):
        return metrics(tickers=["TAIL"], benchmark="TAIL", start="2024-01-01", end="2024-12-31", **body)


def test_skewness_and_excess_kurtosis_of_the_returns():
    body = tail_metrics()

    # Adjusted Fisher-Pearson G1 and the bias-corrected excess kurtosis G2 (as in Excel's SKEW/KURT),
    # worked out by hand from the 40 returns above.
    assert value(body, "skewness:TAIL") == pytest.approx(-3.7249198598, rel=1e-9)
    assert value(body, "excess_kurtosis:TAIL") == pytest.approx(14.2928007540, rel=1e-9)
    assert body["metrics"]["skewness:TAIL"]["unit"] == "ratio"


def test_the_histogram_counts_every_return_once():
    body = tail_metrics()

    hist = body["series"]["return_distribution:TAIL"]
    assert hist["status"] == "ok" and hist["x_unit"] == "decimal" and hist["y_unit"] == "count"
    counts = [p["y"] for p in hist["points"]]
    # ceil(sqrt(40)) = 7 equal bins from the worst (-10%) to the best (+1%) return.
    assert len(counts) == 7
    assert sum(counts) == 40
    assert counts[0] == 1 and counts[-1] == 36
    assert hist["details"]["bin_width"] == pytest.approx(0.11 / 7)
    assert hist["details"]["observations"] == 40
    assert hist["points"][0]["x"] == pytest.approx(-0.10 + 0.11 / 14)


def test_the_fat_tailed_demo_ticker_has_positive_excess_kurtosis():
    body = metrics(tickers=["DEMO-F"], start="2021-01-01", end="2025-12-31")

    assert value(body, "excess_kurtosis:DEMO-F") > 1


def test_the_distribution_follows_the_return_period():
    daily = metrics(tickers=["DEMO-A"], start="2021-01-01", end="2025-12-31")
    monthly = metrics(tickers=["DEMO-A"], start="2021-01-01", end="2025-12-31", period="monthly")

    assert monthly["series"]["return_distribution:DEMO-A"]["details"]["observations"] == 60
    assert daily["series"]["return_distribution:DEMO-A"]["details"]["observations"] > 1000
    assert value(daily, "skewness:DEMO-A") != value(monthly, "skewness:DEMO-A")


def test_too_few_returns_for_kurtosis_is_missing_data():
    with serving(FixtureAdapter({"T": price_frame("2024-01-01", [100.0, 101.0, 99.0, 100.0])})):
        body = metrics(tickers=["T"], benchmark="T", start="2024-01-01", end="2024-12-31")

    assert body["metrics"]["excess_kurtosis:T"]["status"] == "missing_data"
    assert "needs at least 4 daily returns" in body["metrics"]["excess_kurtosis:T"]["reason"]
    assert body["metrics"]["skewness:T"]["status"] == "ok"


# --- Underwater chart ---


def test_the_underwater_chart_shades_the_max_drawdown_from_peak_to_recovery():
    body = metrics(tickers=["DEMO-D"], start="2021-01-01", end="2025-12-31")

    mdd = body["metrics"]["max_drawdown:DEMO-D"]["details"]
    assert mdd["trough"] == "2022-04-11"
    assert mdd["recovery"] is not None
    bands = body["series"]["drawdown:DEMO-D"]["bands"]
    assert bands == [{"start": mdd["peak"], "end": mdd["recovery"], "label": "max_drawdown"}]


def test_an_unrecovered_max_drawdown_is_shaded_to_the_end_of_the_range():
    body = metrics(tickers=["DEMO-D"], start="2022-02-28", end="2022-04-11")

    bands = body["series"]["drawdown:DEMO-D"]["bands"]
    assert bands == [{"start": "2022-02-28", "end": "2022-04-11", "label": "max_drawdown"}]
