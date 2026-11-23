"""Tiingo daily prices: parsing recorded responses and classifying failures."""

from __future__ import annotations

from datetime import date

import pytest

from sextant_compute.data.context import RequestContext
from sextant_compute.data.errors import KeyRequired, NoSuchData, SourceUnavailable
from tiingo_fixtures import FIRST_DAY, LAST_DAY, FakeTiingo, recorded_prices

KEY = "0123456789abcdef0123456789abcdef0123abcd"
ALICE = RequestContext(user_id=None, keys={"tiingo": KEY})


@pytest.fixture
def fake() -> FakeTiingo:
    return FakeTiingo({KEY})


def test_prices_are_split_adjusted_but_not_dividend_adjusted(fake):
    frames = fake.adapter().daily_prices(ALICE, ["AAPL", "SPY"], FIRST_DAY, LAST_DAY)

    aapl = frames["AAPL"]
    assert list(aapl.columns) == ["open", "high", "low", "close", "volume", "dividend"]
    assert aapl.index.name == "date"
    assert aapl.index[0].date() == FIRST_DAY and aapl.index[-1].date() == LAST_DAY
    # Before the 4:1 split on 2024-01-30 the raw close is 4x; adjusted it matches the post-split scale.
    assert recorded_prices("aapl")[0]["close"] == 400.0
    assert aapl["close"].iloc[0] == pytest.approx(100.0)
    assert aapl.loc["2024-01-16", "close"] == pytest.approx(120.0)
    assert aapl.loc["2024-01-30", "close"] == pytest.approx(recorded_prices("aapl")[20]["close"])
    assert aapl["volume"].iloc[0] == pytest.approx(200_000_000)

    spy = frames["SPY"]
    assert spy.loc["2024-01-09", "dividend"] == pytest.approx(1.5)
    assert spy["dividend"].sum() == pytest.approx(1.5)
    assert spy["close"].tolist() == pytest.approx([r["close"] for r in recorded_prices("spy")])


def test_requests_carry_the_users_key_and_the_start_date(fake):
    fake.adapter().daily_prices(ALICE, ["MSFT"], date(2024, 1, 3), date(2024, 1, 10))

    request = fake.requests[-1]
    assert request.url.path == "/tiingo/daily/msft/prices"
    assert request.url.params["startDate"] == "2024-01-03"
    # No end date: Tiingo answers up to the latest day, so later splits are known.
    assert "endDate" not in request.url.params
    assert request.headers["authorization"] == f"Token {KEY}"


def test_unknown_tickers_and_empty_ranges_are_no_such_data_per_ticker(fake):
    with pytest.raises(NoSuchData) as unknown:
        fake.adapter().daily_prices(ALICE, ["AAPL", "ZZZZ"], FIRST_DAY, LAST_DAY)
    assert set(unknown.value.missing) == {"ZZZZ"}
    assert "ZZZZ" in unknown.value.missing["ZZZZ"]

    with pytest.raises(NoSuchData) as empty:
        fake.adapter().daily_prices(ALICE, ["AAPL"], date(2023, 1, 1), date(2023, 6, 30))
    assert "No Tiingo prices for AAPL" in empty.value.missing["AAPL"]


@pytest.mark.parametrize("status", [503, 500, 429])
def test_outages_and_rate_limits_are_source_unavailable(fake, status):
    fake.status = status

    with pytest.raises(SourceUnavailable):
        fake.adapter().daily_prices(ALICE, ["AAPL"], FIRST_DAY, LAST_DAY)


def test_a_key_tiingo_no_longer_accepts_asks_for_a_new_key(fake):
    fake.valid = set()

    with pytest.raises(KeyRequired) as exc:
        fake.adapter().daily_prices(ALICE, ["AAPL"], FIRST_DAY, LAST_DAY)
    assert "Settings" in exc.value.message
    assert KEY not in exc.value.message


def test_without_a_key_nothing_is_sent(fake):
    with pytest.raises(KeyRequired):
        fake.adapter().daily_prices(RequestContext.anonymous(), ["AAPL"], FIRST_DAY, LAST_DAY)
    assert fake.requests == []


def test_a_range_ending_before_a_later_split_is_still_in_todays_share_count(fake):
    # The 4:1 split on 2024-01-30 is after this range, but holdings are in today's share
    # count, so prices must be divided by it too: the 400 raw close is 100.
    frames = fake.adapter().daily_prices(ALICE, ["AAPL"], FIRST_DAY, date(2024, 1, 23))

    aapl = frames["AAPL"]
    assert aapl.index[-1].date() == date(2024, 1, 23)
    assert aapl["close"].iloc[0] == pytest.approx(100.0)
    assert aapl.loc["2024-01-16", "close"] == pytest.approx(120.0)
    assert aapl.loc["2024-01-23", "close"] == pytest.approx(108.0)
    assert aapl["volume"].iloc[0] == pytest.approx(200_000_000)
