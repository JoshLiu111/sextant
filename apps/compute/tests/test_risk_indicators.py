"""Technical indicators on the price chart: POST /api/compute/risk/indicators."""

import pytest
from fastapi.testclient import TestClient

from data_fixtures import FixtureAdapter, price_frame, serving
from main import app

client = TestClient(app)

ENDPOINT = "/api/compute/risk/indicators"

# 100, 101, 102, ... on business days from 2024-01-01; 2024-03-01 is row 44.
LINEAR = {"LIN": price_frame("2024-01-01", [100.0 + i for i in range(200)])}


def indicators(**body):
    response = client.post(ENDPOINT, json={"ticker": "LIN", "start": "2024-03-01", "end": "2024-06-28", **body})
    assert response.status_code == 200, response.text
    return response.json()


def points(body, series_id):
    result = body["series"][series_id]
    assert result["status"] == "ok", result
    return result["points"]


def test_moving_average_is_defined_from_the_first_visible_date():
    with serving(FixtureAdapter(LINEAR)):
        body = indicators(sma={"window": 20})

    price = points(body, "price")
    sma = points(body, "sma")
    assert price[0] == {"x": "2024-03-01", "y": 144.0}
    assert price[-1]["x"] == "2024-06-28"
    # On a straight line the 20-day average lags the close by 9.5.
    assert [p["x"] for p in sma] == [p["x"] for p in price]
    assert all(p["y"] == pytest.approx(q["y"] - 9.5) for p, q in zip(sma, price))


def test_exponential_average_of_a_straight_line_lags_by_half_its_span_less_one():
    with serving(FixtureAdapter(LINEAR)):
        body = indicators(ema={"window": 10})

    price, ema = points(body, "price"), points(body, "ema")
    assert all(p["y"] == pytest.approx(q["y"] - 4.5) for p, q in zip(ema, price))


def test_bollinger_bands_sit_two_standard_deviations_around_the_average():
    with serving(FixtureAdapter(LINEAR)):
        body = indicators(bollinger={"window": 20, "width": 2})

    price = points(body, "price")
    # 20 consecutive integers have a population standard deviation of sqrt((20^2 - 1) / 12).
    spread = 2 * ((20**2 - 1) / 12) ** 0.5
    for p, upper, middle, lower in zip(
        price, points(body, "bollinger_upper"), points(body, "bollinger_middle"), points(body, "bollinger_lower")
    ):
        assert middle["y"] == pytest.approx(p["y"] - 9.5)
        assert upper["y"] == pytest.approx(middle["y"] + spread)
        assert lower["y"] == pytest.approx(middle["y"] - spread)


def test_rsi_is_100_while_prices_only_rise_and_0_while_they_only_fall():
    falling = {"DOWN": price_frame("2024-01-01", [500.0 - i for i in range(200)])}
    with serving(FixtureAdapter({**LINEAR, **falling})):
        rising = indicators(rsi={"window": 14})
        down = indicators(ticker="DOWN", rsi={"window": 14})

    assert {p["y"] for p in points(rising, "rsi")} == {100.0}
    assert {p["y"] for p in points(down, "rsi")} == {0.0}
    assert rising["series"]["rsi"]["y_unit"] == "index"


def test_rsi_of_alternating_two_up_one_down_starts_at_two_thirds():
    # Up 2, down 1, repeated: over any even window the average gain is twice the average loss.
    closes = [100.0]
    for i in range(199):
        closes.append(closes[-1] + (2 if i % 2 == 0 else -1))
    frames = {"ZIG": price_frame("2024-01-01", closes)}
    with serving(FixtureAdapter(frames)):
        body = indicators(ticker="ZIG", start="2024-01-01", rsi={"window": 14})

    rsi = points(body, "rsi")
    assert all(p["y"] is None for p in rsi[:14])
    assert rsi[14]["y"] == pytest.approx(100 - 100 / 3)


def test_macd_of_a_straight_line_is_the_gap_between_the_two_lags():
    with serving(FixtureAdapter(LINEAR)):
        body = indicators(start="2024-06-03", macd={"fast": 12, "slow": 26, "signal": 9})

    # EMA(n) of a line lags by (n - 1) / 2, so MACD = (26 - 1) / 2 - (12 - 1) / 2 = 7 everywhere.
    assert all(p["y"] == pytest.approx(7.0) for p in points(body, "macd"))
    assert all(p["y"] == pytest.approx(7.0) for p in points(body, "macd_signal"))
    assert all(p["y"] == pytest.approx(0.0, abs=1e-9) for p in points(body, "macd_histogram"))


def test_without_enough_history_the_first_values_are_null_but_the_price_is_still_shown():
    with serving(FixtureAdapter(LINEAR)):
        body = indicators(start="2024-01-01", sma={"window": 20})

    price, sma = points(body, "price"), points(body, "sma")
    assert price[0] == {"x": "2024-01-01", "y": 100.0}
    assert all(p["y"] is None for p in sma[:19])
    assert sma[19]["y"] == pytest.approx(109.5)


def test_only_the_requested_indicators_are_returned():
    with serving(FixtureAdapter(LINEAR)):
        body = indicators(sma={"window": 5})

    assert set(body["series"]) == {"price", "sma"}


def test_every_indicator_on_demo_data_is_defined_from_the_first_visible_date():
    body = indicators(
        ticker="DEMO-A",
        start="2021-01-04",
        end="2025-12-31",
        sma={"window": 200},
        ema={"window": 50},
        bollinger={"window": 20, "width": 2},
        rsi={"window": 14},
        macd={"fast": 12, "slow": 26, "signal": 9},
    )

    assert body["source"]["is_demo"] is True
    assert len(body["series"]) == 10
    for series_id, result in body["series"].items():
        assert result["points"][0]["x"] == "2021-01-04", series_id
        assert all(p["y"] is not None for p in result["points"]), series_id
    assert all(0 <= p["y"] <= 100 for p in points(body, "rsi"))


def test_fetched_lookback_does_not_change_a_warmed_up_exponential_average():
    later = indicators(ticker="DEMO-B", start="2023-01-03", end="2023-06-30", ema={"window": 20})
    earlier = indicators(ticker="DEMO-B", start="2022-01-03", end="2023-06-30", ema={"window": 20})

    same_day = {p["x"]: p["y"] for p in points(earlier, "ema")}
    first = points(later, "ema")[0]
    assert first["y"] == pytest.approx(same_day[first["x"]], rel=0.01)


@pytest.mark.parametrize(
    ("body", "field", "message"),
    [
        ({"sma": {"window": 1}}, "sma.window", "between 2 and 250"),
        ({"macd": {"fast": 26, "slow": 12, "signal": 9}}, "macd.slow", "longer than the fast"),
        ({"bollinger": {"window": 20, "width": 0}}, "bollinger.width", "between 0 and 5"),
        ({"end": "2024-01-01"}, "end", "End date must be after the start date."),
    ],
)
def test_invalid_parameters_are_reported_on_their_field(body, field, message):
    response = client.post(ENDPOINT, json={"ticker": "DEMO-A", "start": "2024-03-01", "end": "2024-06-28", **body})

    assert response.status_code == 422
    assert message in response.json()["error"]["fields"][field]


def test_an_unknown_ticker_is_reported_on_the_ticker_field():
    response = client.post(ENDPOINT, json={"ticker": "DEMO-ZZ", "start": "2024-03-01", "end": "2024-06-28"})

    assert response.status_code == 422
    assert "Unknown ticker DEMO-ZZ" in response.json()["error"]["fields"]["ticker"]
