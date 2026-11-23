import pandas as pd

from sextant_compute.data.synthetic import BENCHMARK, PERSONALITIES, generate_universe


def test_same_seed_gives_identical_series():
    first = generate_universe(seed=7)
    second = generate_universe(seed=7)

    assert first.keys() == second.keys()
    for ticker in first:
        pd.testing.assert_frame_equal(first[ticker], second[ticker])


def test_different_seeds_give_different_series():
    a = generate_universe(seed=7)["DEMO-A"]
    b = generate_universe(seed=8)["DEMO-A"]

    assert not a["close"].equals(b["close"])


def test_universe_is_fictional_tickers_only_with_daily_ohlcv_and_dividends():
    universe = generate_universe(seed=7)

    assert set(universe) == {"DEMO-A", "DEMO-B", "DEMO-C", "DEMO-D", "DEMO-E", "DEMO-F", "DEMO-G", "DEMO-MKT"}
    assert BENCHMARK == "DEMO-MKT"
    assert set(PERSONALITIES) == set(universe)
    for frame in universe.values():
        assert list(frame.columns) == ["open", "high", "low", "close", "volume", "dividend"]
        assert frame.index.is_monotonic_increasing
        assert (frame.index.day_of_week < 5).all()  # trading days only
        assert (frame["low"] <= frame[["open", "close"]].min(axis=1)).all()
        assert (frame["high"] >= frame[["open", "close"]].max(axis=1)).all()
        assert (frame[["open", "high", "low", "close"]] > 0).all().all()
        assert (frame["volume"] > 0).all()


def test_dividend_payers_pay_and_growth_names_do_not():
    universe = generate_universe(seed=7)

    for ticker, personality in PERSONALITIES.items():
        paid = universe[ticker]["dividend"].sum()
        if personality.dividend_yield > 0:
            assert paid > 0, ticker
        else:
            assert paid == 0, ticker
