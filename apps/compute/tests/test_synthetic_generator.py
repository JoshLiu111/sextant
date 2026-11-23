import pandas as pd

from sextant_compute.data.synthetic import BENCHMARK, PERSONALITIES, generate_factors, generate_universe


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

    assert set(universe) == {"DEMO-A", "DEMO-B", "DEMO-C", "DEMO-D", "DEMO-E", "DEMO-F", "DEMO-G", "DEMO-H", "DEMO-I", "DEMO-MKT"}
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


FACTOR_COLUMNS = ["Mkt-RF", "SMB", "HML", "MOM", "RF"]


def test_factor_series_are_deterministic_daily_decimals_on_the_trading_days():
    first = generate_factors(seed=7)
    second = generate_factors(seed=7)
    other = generate_factors(seed=8)

    pd.testing.assert_frame_equal(first, second)
    assert list(first.columns) == FACTOR_COLUMNS
    assert first.index.equals(generate_universe(seed=7)[BENCHMARK].index[1:])
    assert not first["SMB"].equals(other["SMB"])
    assert first.notna().all().all()
    # Daily decimals: a long-short factor moves well under 5% a day; RF is a few basis points.
    assert first[["SMB", "HML", "MOM"]].abs().max().max() < 0.05
    assert ((first["RF"] > 0) & (first["RF"] < 0.0005)).all()


def test_the_market_factor_is_the_demo_market_total_return_above_the_risk_free_rate():
    universe = generate_universe(seed=7)
    factors = generate_factors(seed=7)
    market = universe[BENCHMARK]

    total = (market["close"] + market["dividend"]) / market["close"].shift(1) - 1
    expected = (total.iloc[1:] - factors["RF"]).rename("Mkt-RF")
    pd.testing.assert_series_equal(factors["Mkt-RF"], expected)


def test_factor_tilted_tickers_are_appended_without_changing_the_existing_series():
    universe = generate_universe(seed=17)

    # DEMO-MKT..G keep their seed-17 values from GENERATOR_VERSION 2.
    assert universe["DEMO-A"]["close"].iloc[0] == 80.4399
    assert universe["DEMO-G"]["close"].iloc[-1] == 184.3315
    assert PERSONALITIES["DEMO-H"].smb > 0.5 and PERSONALITIES["DEMO-H"].hml > 0.3
    assert PERSONALITIES["DEMO-I"].mom > 0.5
